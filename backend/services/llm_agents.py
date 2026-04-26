"""Pydantic AI agent definitions backing services/agent.py and services/ai_service.py.

This module owns all LLM interaction. Provider selection is via Pydantic AI's
`provider:model` strings in `config.settings`:
  - "anthropic:claude-sonnet-4-6" / "anthropic:claude-haiku-4-5"
  - "openai-responses:gpt-5.5"  (Responses API; recommended by OpenAI for tool loops)

Each agent emits SSE-shaped events through `deps.emit({...})` from within tool
bodies, so the public sync wrappers in services/agent.py preserve the
{thought, tool_call, tool_result, final, error} contract the frontend expects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from config import settings
from services.tools import (
    profile_df,
    apply_op,
    CLEANING_OPS_DOC,
    STATS_TESTS,
    STATS_TESTS_DOC,
)
from services.discovery import (
    Workspace,
    DISCOVERY_OPS_DOC,
    JOIN_OPS_DOC,
    SOCRATA_PORTALS_DOC,
    DEFAULT_DOMAIN,
    apply_discovery_op,
    search_catalog as _search_catalog,
    get_dataset_schema as _get_dataset_schema,
)
from services.literature import (
    LITERATURE_OPS_DOC,
    apply_literature_op,
)


EventEmit = Callable[[dict], None]


# ---------- Output types (replace the old `finish` tools) ----------


class CleanResult(BaseModel):
    """Final result produced by the cleaning agent."""
    summary: str = Field(description="One-paragraph summary of what was cleaned.")


class DiscoverResult(BaseModel):
    """Final result produced by the discovery agent."""
    primary_alias: str = Field(description="Workspace alias holding the analysis-ready dataset.")
    summary: str = Field(description="One-paragraph summary of what was fetched/joined.")


class ScoutRecommendation(BaseModel):
    """Final pick from the catalog scout sub-agent."""
    dataset_id: str
    domain: str = Field(default=DEFAULT_DOMAIN, description="Socrata portal that owns the dataset, e.g. data.cdc.gov, data.cityofnewyork.us.")
    rationale: str
    recommended_select: Optional[str] = None
    recommended_where: Optional[str] = None
    recommended_alias: Optional[str] = None
    alternatives: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    question: str
    variables: list[str] = Field(default_factory=list)
    test_type: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class FindingsReport(BaseModel):
    findings: str
    limitations: str
    follow_up: str


class LiteratureArticle(BaseModel):
    pmid: str
    title: str
    authors: list[str] = Field(default_factory=list)
    journal: str = ""
    year: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    relevance: str = Field(default="", description="Why this paper is relevant to the question.")


class LiteratureReport(BaseModel):
    summary: str = Field(description="One-paragraph overview of what the literature says about the question.")
    articles: list[LiteratureArticle] = Field(default_factory=list)


class CodeAnalysisResult(BaseModel):
    summary: str = Field(description="One-paragraph plain-English summary of what was done and what was found.")
    findings: str = Field(description="3-5 paragraph narrative of key findings, citing specific numbers from the printed output.")
    limitations: str = Field(description="Bullet list (using •) of limitations.")
    follow_up: str = Field(description="Numbered list of follow-up research questions or experiments.")


# ---------- Per-agent dependency dataclasses ----------


@dataclass
class CleanDeps:
    workspace: Workspace
    alias: str
    emit: EventEmit


@dataclass
class DiscoverDeps:
    workspace: Workspace
    emit: EventEmit


@dataclass
class ScoutDeps:
    pass  # scout uses a throwaway internal workspace; nothing needed


@dataclass
class AnalyzeDeps:
    workspace: Workspace
    alias: str
    emit: EventEmit


@dataclass
class LiteratureDeps:
    emit: EventEmit


@dataclass
class CodeDeps:
    csv_path: str
    work_dir: str
    emit: EventEmit
    steps: list[dict]  # accumulated {rationale, code, stdout, stderr, charts, ok}


# ---------- System prompts ----------


CLEAN_SYSTEM = f"""You are a careful data analyst preparing a tabular dataset for statistical analysis.

You have these tools:
- profile: see the current state of the dataframe
- apply_op: apply ONE cleaning operation (it runs immediately, not asking for approval)

When the dataset is analysis-ready, return a CleanResult with a one-paragraph summary.

{CLEANING_OPS_DOC}

Rules:
- Always start by calling profile.
- Apply ONE op at a time. Look at the resulting profile before proposing the next.
- Be conservative: don't drop columns, and prefer imputation over row deletion when missing data is light.
- Stop when: types are correct, no obviously broken values, missing data is handled.
- A typical clean is 4-8 ops. Don't loop forever.
"""

DISCOVER_SYSTEM = f"""You are a data acquisition agent. Given a research question, find the right Socrata-hosted dataset(s), fetch them into the workspace, and (if multiple are needed) join them into a single analysis-ready frame.

You can search across MANY open-data portals — federal (CDC, CMS, HHS, DOE), states (NY, CA, TX, WA), and cities (NYC, Chicago, LA, SF, Seattle, Austin, Boston, DC). Pick the portal whose mission matches the question.

{SOCRATA_PORTALS_DOC}

You have two tools:
- `scout(question)` — RECOMMENDED FIRST STEP for single-dataset questions. A fast Haiku sub-agent searches across ALL portals and inspects schemas, returning ONE recommended (domain, dataset_id) with optional pre-checked SoQL hints. Saves 3-5s vs running search_catalog + get_dataset_schema yourself.
- `discovery_op(op, args, rationale)` — dispatches to these ops:
{DISCOVERY_OPS_DOC}
{JOIN_OPS_DOC}

When the workspace contains a single analysis-ready alias for the question, return a DiscoverResult with that alias and a summary.

If the question needs multiple datasets (potentially from different portals — e.g. CDC vaccination + NYC 311), you can call scout multiple times in parallel. Multiple discovery_op calls in the same turn (e.g. fetch_dataset for both aliases) also run in parallel.

Rules:
- Use the portal list above to narrow search. For an NYC-specific question, search `domain='data.cityofnewyork.us'`. For a federal-health question, try `domain='data.cdc.gov,data.cms.gov,healthdata.gov'`. When unsure, omit `domain` and search all.
- search_catalog results include a `domain` field — ALWAYS pass that same `domain` to get_dataset_schema and fetch_dataset for that dataset, otherwise you'll hit the wrong host and get 404s.
- Before fetch_dataset, call get_dataset_schema so your SoQL `select`/`where` reference real fields.
- ALWAYS pass an explicit `limit` to fetch_dataset of at least 25000 (cap 100000). Socrata's server-side default is only 1000 rows, which is rarely enough. Use SoQL `where` to filter server-side (e.g. `where="year >= 2020 AND state = 'CA'"`) — that's how you keep result sizes manageable, NOT by lowering limit.
- BE LIBERAL WITH FILTERS. When the question mentions a state, year, or category, first try fetching WITHOUT that filter (or with a wider one). Datasets store state/borough/category names in unpredictable forms ("Florida" vs "FL", "MANHATTAN" vs "Manhattan"). If you must filter, inspect the schema's sample values first. If a fetch returns 0 rows, that is a FAILURE — relax the filter and retry, do not finish on an empty dataset.
- If two datasets are needed, fetch both with distinct aliases, then merge_datasets (or aggregate_dataset first if grains differ). A merge that returns 0 rows means the join keys don't overlap — inspect both sides before retrying.
- SoQL WHERE syntax: use LIKE with % wildcards for fuzzy matching (e.g. `dimension LIKE '%6 Month%'`). Do NOT use ILIKE — Socrata does not support it and will return a 400 error.
- For LARGE datasets (millions of rows: FHV/taxi trips, 311, crime), AGGREGATE SERVER-SIDE instead of fetching raw rows. Pass aggregations via fetch_dataset's `group` and `having` arguments — NEVER embed `group by ...` inside the `select` string (Socrata returns a 400). Correct example: `select="borough, date_extract_hh(pickup_datetime) as hr, count(*) as n", group="borough, date_extract_hh(pickup_datetime)"`. Every non-aggregate column in `select` must also appear in `group` (referenced as the EXPRESSION, not the `as` alias).
- Before finishing, sanity-check the output row count. If a merge of A rows × B rows on key K produced far more rows than max(A, B), the join is a cartesian product — you are missing a key column (e.g. a year or season field).
- Never finish if the primary alias is empty or the row count is suspicious.
- Do not invent dataset ids or domains. Only use values returned by search_catalog.
"""

SCOUT_SYSTEM = f"""You are a fast catalog scout. Given a research question, find the single best Socrata dataset to fetch — ACROSS ALL approved open-data portals (federal, state, city), not just CDC.

{SOCRATA_PORTALS_DOC}

Tools:
- search_catalog(query, limit=5, domain=None): full-text search. Pass `domain=None` for cross-portal search, or a specific domain when the question clearly maps to one (e.g. NYC question → 'data.cityofnewyork.us'). You can also pass a comma-separated subset (e.g. 'data.cdc.gov,data.cms.gov').
- get_dataset_schema(dataset_id, domain): column names + sample values for one dataset. `domain` MUST match the portal returned by search_catalog.

Workflow:
1. ONE search_catalog call with terms from the question, picking the right `domain` scope from the portal list above.
2. Up to 2 get_dataset_schema calls in parallel on the most promising candidates (using each candidate's `domain` from the search results).
3. Return a ScoutRecommendation including BOTH dataset_id AND domain. Be concise.

Rules:
- If the question mentions a state, city, year, or category, do NOT include it in recommended_where unless you SAW that exact value in the schema's sample_values. Datasets are inconsistent about naming.
- Always set the `domain` field on your recommendation to the portal that owns the dataset. The main agent will pass it through to fetch_dataset.
- Return at most ONE recommendation. The main agent does the actual fetching.
- Stop after returning the recommendation. Do not chain more searches.
"""

ANALYZE_SYSTEM = f"""You are a statistician. Given a dataset profile and a user's question, choose an appropriate test, run it, and explain the result.

{STATS_TESTS_DOC}

Workflow:
1. Identify the variables in the question and verify they exist in the profile.
2. Choose the right test based on the data shapes (numeric vs. categorical, # of groups).
3. Call run_test with the test name and args.
4. After getting the result, give a plain-English interpretation: effect size, significance, what it means, and any caveats from assumption checks.

If the user's question is ambiguous or the right columns aren't obvious, ask a clarifying question instead of guessing.
"""

HYPO_SYSTEM = f"""You are a research analyst. Given a dataset profile and a few sample rows, propose 3-5 specific, testable hypotheses worth investigating with statistical tests.

{STATS_TESTS_DOC}

Each hypothesis must include:
- question: one-sentence question in plain English
- variables: the column names involved
- test_type: one of "two_group_numeric", "multi_group_numeric", "two_categorical", "correlation"
- args: dict matching the test signature
- rationale: why this is interesting given the data
"""

CODE_SYSTEM = """You are a public-health data scientist. You have a cleaned dataset and a research question. Investigate the question by writing real Python, running it, and interpreting the printed output.

You have ONE tool:
- `run_python(code, rationale)` — executes `code` in a Python subprocess. The variable `df` is already loaded from the cleaned CSV. `pandas as pd`, `numpy as np`, `from scipy import stats`, and `matplotlib.pyplot as plt` are pre-imported. The tool returns `{ok, stdout, stderr, charts}` where `charts` lists `*.png` files saved during the call (use `plt.savefig('descriptive_name.png')`).

Workflow:
1. ONE exploration call first: print `df.shape`, `df.dtypes`, `df.head(3)`, and `value_counts(dropna=False).head(10)` for important categorical columns. Do not load extra packages.
2. Then write 3-5 substantive analyses tailored to the research question:
   - Group comparisons (Welch t-test, Mann-Whitney, ANOVA, Kruskal — pick what fits) using `scipy.stats`.
   - Correlations between numeric columns relevant to the question.
   - Stratified analyses (by site, age_group, sex, race/ethnicity, season, year) when the question implies disparities.
   - Time-series aggregation (resample, groupby month/season) when temporal columns exist.
3. EVERY analytical call should ALSO produce at least one chart via `plt.savefig('foo.png')`. Empty `charts` on an analysis step is a failure.
4. Print numeric results clearly with f-strings: include test name, statistic, p-value, sample sizes, effect size where applicable.
5. If a call errors or returns surprising output (NaN, 0 rows after filter, unexpected dtype), diagnose and retry.
6. Stop after 5-8 successful run_python calls. Then return a CodeAnalysisResult whose `findings` cites the actual numbers your code printed.

CRITICAL constraints:
- Subprocess state does NOT persist across calls. Every call starts fresh with `df` re-loaded from CSV. Do all setup you need inside each call.
- Do NOT redefine `df` or re-read the CSV — `df = pd.read_csv(...)` is already done for you.
- Keep each `code` block focused on one task — short and readable beats sprawling.
- Use REAL column names from the profile and from your initial exploration call. Do not invent columns.
- If the dataset has aggregate "Overall" rows mixed with stratified rows, FILTER THEM OUT before group comparisons (e.g. `df[df['age_group'] != 'Overall']`).
- Save charts with descriptive lowercase filenames like `weekly_rate_by_age_group.png`, not `chart1.png`.
- The `findings` you return at the end MUST reference specific numbers (statistics, p-values, group means) from your printed output. Vague summaries are unacceptable."""

LITERATURE_SYSTEM = f"""You are a research librarian. Given a public-health research question, find prior peer-reviewed work on the topic by searching PubMed, then summarize each relevant paper's contribution.

You have these tools:
- `literature_op(op, args, rationale)` — dispatches to:
{LITERATURE_OPS_DOC}

Workflow:
1. Call search_pubmed with terms drawn from the question. If the first query returns <3 hits, broaden it (drop a modifier, swap to a synonym). If it returns >15, narrow it.
2. Call fetch_pubmed once on the top 6-10 pmids — one batch is enough.
3. From the abstracts, return a LiteratureReport with:
   - `summary`: a 3-5 sentence plain-English synthesis of what the literature collectively says about the question (consensus, disagreements, gaps).
   - `articles`: 4-8 articles you actually consider relevant, each with a one-sentence `relevance` field explaining the connection to the question. Drop articles whose abstract clearly does not address the question.

Rules:
- Do not invent pmids, titles, or authors. Use only what fetch_pubmed returned.
- Prefer recent work (last 10 years) unless the question is historical.
- If the first search returns 0 results, try a broader query before giving up.
- Be concise — short rationales beat long ones.
- Never finish without at least one search_pubmed + one fetch_pubmed call.
"""

CHAT_SYSTEM = """You are HealthLab Agent, an autonomous public health research assistant. Your role is to inspect public health datasets, clean them, run exploratory analysis, generate charts and tables, explain findings in plain English, and suggest follow-up research questions or experiments.

Always be careful with public health claims. Do not provide medical advice. Do not claim causation from observational data unless the study design supports it. Always mention missing data, limitations, uncertainty, and possible confounders. Prefer simple, interpretable analysis first. Make your work reproducible by explaining cleaning steps and analysis methods.

When responding:
- Be concise and precise
- Use plain English accessible to non-statisticians
- Clearly distinguish between correlation and causation
- Always mention data quality limitations
- Suggest specific, actionable follow-up research questions
- Format responses in clean markdown when appropriate"""


# ---------- Agent instantiation ----------


def _scout_settings() -> ModelSettings:
    """ModelSettings for the scout sub-agent: low reasoning effort, tight max_tokens.

    `reasoning_effort` is consumed by OpenAI reasoning models and ignored by
    Anthropic providers, so the same settings work for both."""
    return ModelSettings(
        max_tokens=512,
        reasoning_effort=settings.scout_reasoning_effort,  # type: ignore[arg-type]
    )


clean_agent: Agent[CleanDeps, CleanResult] = Agent(
    settings.agent_model,
    deps_type=CleanDeps,
    output_type=CleanResult,
    instructions=CLEAN_SYSTEM,
    model_settings=ModelSettings(max_tokens=1024),
)

discover_agent: Agent[DiscoverDeps, DiscoverResult] = Agent(
    settings.agent_model,
    deps_type=DiscoverDeps,
    output_type=DiscoverResult,
    instructions=DISCOVER_SYSTEM,
    model_settings=ModelSettings(max_tokens=1024),
)

scout_agent: Agent[ScoutDeps, ScoutRecommendation] = Agent(
    settings.scout_model,
    deps_type=ScoutDeps,
    output_type=ScoutRecommendation,
    instructions=SCOUT_SYSTEM,
    model_settings=_scout_settings(),
)

analyze_agent: Agent[AnalyzeDeps, str] = Agent(
    settings.agent_model,
    deps_type=AnalyzeDeps,
    output_type=str,
    instructions=ANALYZE_SYSTEM,
    model_settings=ModelSettings(max_tokens=1024),
)

hypo_agent: Agent[None, list[Hypothesis]] = Agent(
    settings.agent_model,
    output_type=list[Hypothesis],
    instructions=HYPO_SYSTEM,
    model_settings=ModelSettings(max_tokens=2048),
)

plan_agent: Agent[None, str] = Agent(
    settings.agent_model,
    output_type=str,
    instructions=CHAT_SYSTEM,
    model_settings=ModelSettings(max_tokens=1024),
)

findings_agent: Agent[None, FindingsReport] = Agent(
    settings.agent_model,
    output_type=FindingsReport,
    instructions=CHAT_SYSTEM,
    model_settings=ModelSettings(max_tokens=2048),
)

literature_agent: Agent[LiteratureDeps, LiteratureReport] = Agent(
    settings.agent_model,
    deps_type=LiteratureDeps,
    output_type=LiteratureReport,
    instructions=LITERATURE_SYSTEM,
    model_settings=ModelSettings(max_tokens=4096),
)

code_agent: Agent[CodeDeps, CodeAnalysisResult] = Agent(
    settings.agent_model,
    deps_type=CodeDeps,
    output_type=CodeAnalysisResult,
    instructions=CODE_SYSTEM,
    model_settings=ModelSettings(max_tokens=4096),
)


def chat_agent_with_context(dataset_context: str) -> Agent[None, str]:
    """Build an ad-hoc chat agent with the dataset context baked into instructions."""
    return Agent(
        settings.agent_model,
        output_type=str,
        instructions=CHAT_SYSTEM + f"\n\nCurrent dataset context:\n{dataset_context}",
        model_settings=ModelSettings(max_tokens=1024),
    )


# ---------- Tool definitions ----------


# Cleaning agent tools


@clean_agent.tool
async def clean_profile(ctx: RunContext[CleanDeps]) -> str:
    """Profile the current dataframe (dtypes, missing, unique counts, sample values)."""
    df = ctx.deps.workspace.get(ctx.deps.alias)
    ctx.deps.emit({"type": "tool_call", "agent": "clean", "name": "profile", "args": {}, "rationale": ""})
    prof = profile_df(df)
    ctx.deps.emit({
        "type": "tool_result", "agent": "clean", "name": "profile",
        "summary": f"{prof['n_rows']} rows × {prof['n_cols']} cols",
    })
    return json.dumps(prof, default=str)


@clean_agent.tool
async def clean_apply_op(
    ctx: RunContext[CleanDeps],
    op: str,
    args: dict[str, Any],
    rationale: str = "",
) -> str:
    """Apply ONE cleaning operation. See instructions for op names and args."""
    ctx.deps.emit({
        "type": "tool_call", "agent": "clean",
        "name": op, "args": args, "rationale": rationale,
    })
    df = ctx.deps.workspace.get(ctx.deps.alias)
    try:
        new_df, msg = apply_op(df, {"op": op, "args": args})
        ctx.deps.workspace.frames[ctx.deps.alias] = new_df
        ctx.deps.emit({"type": "tool_result", "agent": "clean", "name": op, "summary": msg})
        return json.dumps({"ok": True, "message": msg, "profile": profile_df(new_df)}, default=str)
    except Exception as e:
        ctx.deps.emit({"type": "tool_result", "agent": "clean", "name": op, "summary": f"error: {e}"})
        return json.dumps({"ok": False, "error": str(e)})


# Discovery agent tools


@discover_agent.tool
async def discover_scout(ctx: RunContext[DiscoverDeps], question: str) -> str:
    """Fast Haiku-backed sub-agent that searches the CDC catalog AND inspects schemas, returning ONE recommended dataset_id with optional SoQL hints. Call this FIRST instead of search_catalog when you want a quick pick."""
    ctx.deps.emit({
        "type": "tool_call", "agent": "discover",
        "name": "scout", "args": {"question": question[:80]},
        "rationale": f"{settings.scout_model} sub-agent for catalog search + schema",
    })
    try:
        result = await scout_agent.run(
            f"Research question: {question}\n\nFind the single best dataset.",
            deps=ScoutDeps(),
            usage_limits=UsageLimits(request_limit=4),
        )
        rec = result.output
        payload = rec.model_dump()
        payload["ok"] = True
        summary = f"recommend `{rec.dataset_id}` — {(rec.rationale or '')[:80]}"
    except Exception as e:
        payload = {"ok": False, "error": f"scout: {e}"}
        summary = f"error: {e}"
    ctx.deps.emit({
        "type": "tool_result", "agent": "discover",
        "name": "scout", "summary": summary, "result": payload,
    })
    return json.dumps(payload, default=str)


@discover_agent.tool
async def discover_op(
    ctx: RunContext[DiscoverDeps],
    op: str,
    args: dict[str, Any],
    rationale: str = "",
) -> str:
    """Run one discovery, fetch, or join op. See instructions for op names and args."""
    ctx.deps.emit({
        "type": "tool_call", "agent": "discover",
        "name": op, "args": args, "rationale": rationale,
    })
    spec = {"op": op, "args": args}
    result = apply_discovery_op(ctx.deps.workspace, spec)
    ctx.deps.emit({
        "type": "tool_result", "agent": "discover",
        "name": op, "summary": _summarize_discovery_result(op, result),
        "result": _truncate_result(result),
    })
    return json.dumps(result, default=str)


# Scout sub-agent tools


@scout_agent.tool
async def scout_search_catalog(
    ctx: RunContext[ScoutDeps],
    query: str,
    limit: int = 5,
    domain: Optional[str] = None,
) -> str:
    """Full-text search the Socrata catalog across one or many portals. Returns top-N candidates with name, description, domain, and column field names. Pass `domain=None` to search ALL approved portals, a single domain string, or a comma-separated list."""
    ws = Workspace()
    r = _search_catalog(ws, query, limit, domain=domain)
    return json.dumps(_truncate_result(r), default=str)


@scout_agent.tool
async def scout_get_schema(
    ctx: RunContext[ScoutDeps],
    dataset_id: str,
    domain: str = DEFAULT_DOMAIN,
) -> str:
    """Get full column schema for one dataset (names, types, descriptions). `domain` must match the Socrata portal that owns the dataset (use the `domain` field from search_catalog)."""
    ws = Workspace()
    r = _get_dataset_schema(ws, dataset_id, domain=domain)
    return json.dumps(_truncate_result(r), default=str)


# Analysis agent tool


@analyze_agent.tool
async def analyze_run_test(
    ctx: RunContext[AnalyzeDeps],
    test: str,
    args: dict[str, Any],
) -> str:
    """Run a statistical test on the current dataframe. Returns test stats and assumption checks."""
    df = ctx.deps.workspace.get(ctx.deps.alias)
    ctx.deps.emit({
        "type": "tool_call", "agent": "analyze",
        "name": test, "args": args, "rationale": "",
    })
    test_fn = STATS_TESTS.get(test)
    if not test_fn:
        result: dict = {"error": f"unknown test {test}"}
    else:
        try:
            result = test_fn(df, **args)
        except Exception as e:
            result = {"error": str(e)}
    ctx.deps.emit({
        "type": "tool_result", "agent": "analyze",
        "name": test, "summary": _summarize_test_result(result), "result": result,
    })
    return json.dumps(result, default=str)


# Code agent tool


@code_agent.tool
async def code_run_python(
    ctx: RunContext[CodeDeps],
    code: str,
    rationale: str = "",
) -> str:
    """Run `code` in a subprocess sandbox with `df` already loaded. See instructions for what's available."""
    from services.sandbox import run_python  # local import to avoid heavy deps at module load

    ctx.deps.emit({
        "type": "tool_call", "agent": "code",
        "name": "run_python",
        "args": {"chars": len(code), "lines": code.count("\n") + 1},
        "rationale": rationale,
    })
    result = run_python(code, ctx.deps.csv_path, ctx.deps.work_dir)
    step = {
        "rationale": rationale,
        "code": code,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "charts": result["charts"],
        "ok": result["ok"],
    }
    ctx.deps.steps.append(step)

    if result["ok"]:
        summary = (
            f"ok — {len(result['stdout'].splitlines())} lines stdout, "
            f"{len(result['charts'])} chart(s)"
        )
    else:
        summary = "FAILED: " + (result["stderr"].strip().splitlines()[-1] if result["stderr"].strip() else "non-zero exit")
    ctx.deps.emit({
        "type": "tool_result", "agent": "code",
        "name": "run_python", "summary": summary,
        "result": {
            "ok": result["ok"],
            "charts": result["charts"],
            "stdout_preview": result["stdout"][-400:],
            "stderr_preview": result["stderr"][-400:],
        },
    })
    return json.dumps(result, default=str)


# Literature agent tool


@literature_agent.tool
async def literature_op_tool(
    ctx: RunContext[LiteratureDeps],
    op: str,
    args: dict[str, Any],
    rationale: str = "",
) -> str:
    """Run one literature op. See instructions for op names and args."""
    ctx.deps.emit({
        "type": "tool_call", "agent": "literature",
        "name": op, "args": args, "rationale": rationale,
    })
    result = apply_literature_op({"op": op, "args": args})
    ctx.deps.emit({
        "type": "tool_result", "agent": "literature",
        "name": op, "summary": _summarize_literature_result(op, result),
        "result": _truncate_literature_result(op, result),
    })
    return json.dumps(result, default=str)


# ---------- Iterator helpers ----------


async def _emit_thoughts_from_node(node: Any, agent_name: str, emit: EventEmit) -> None:
    """If a node carries a model response, emit any text parts as thought events."""
    response = getattr(node, "model_response", None)
    if response is None:
        return
    parts = getattr(response, "parts", None) or []
    for part in parts:
        if getattr(part, "part_kind", None) == "text":
            text = getattr(part, "content", "") or ""
            if text.strip():
                emit({"type": "thought", "agent": agent_name, "text": text})


async def _run_with_events(
    agent: Agent,
    user_prompt: str,
    deps: Any,
    agent_name: str,
    *,
    request_limit: int,
):
    """Drive an Agent.iter() loop and emit thought events as we go.

    Tool-call / tool-result events are emitted by the @tool functions themselves
    via deps.emit, so they appear in execution order. The final-event emission
    is left to the caller because each agent's "final" payload differs.
    """
    try:
        async with agent.iter(
            user_prompt,
            deps=deps,
            usage_limits=UsageLimits(request_limit=request_limit),
        ) as run:
            async for node in run:
                await _emit_thoughts_from_node(node, agent_name, deps.emit)
            return run.result.output if run.result is not None else None
    except Exception as e:
        deps.emit({"type": "error", "agent": agent_name, "message": str(e)})
        return None


# ---------- Public async entry points used by services/agent.py ----------


async def clean_run(workspace: Workspace, alias: str, emit: EventEmit, max_steps: int = 12) -> Optional[CleanResult]:
    deps = CleanDeps(workspace=workspace, alias=alias, emit=emit)
    result = await _run_with_events(
        clean_agent,
        f"Clean the dataset '{alias}' for statistical analysis. Start by profiling.",
        deps,
        "clean",
        request_limit=max_steps,
    )
    if result is not None:
        emit({"type": "final", "agent": "clean", "summary": result.summary})
    return result


async def discover_run(
    question: str,
    workspace: Workspace,
    emit: EventEmit,
    max_steps: int = 15,
    selected_dataset_ids: list[str] | None = None,
) -> Optional[DiscoverResult]:
    deps = DiscoverDeps(workspace=workspace, emit=emit)
    user_msg = f"Research question: {question}\n\nFind and prepare the right CDC dataset(s)."
    if workspace.frames:
        user_msg += f"\n\nWorkspace already contains: {workspace.summary()}"
    if selected_dataset_ids:
        ids_str = ", ".join(f"`{did}`" for did in selected_dataset_ids)
        user_msg += (
            f"\n\nIMPORTANT: The user has pre-selected these CDC dataset IDs — fetch them directly "
            f"without calling the scout tool: {ids_str}. "
            "Call get_dataset_schema first to inspect each, then fetch_dataset for each ID. "
            "If multiple IDs are provided, join them appropriately after fetching."
        )
    result = await _run_with_events(
        discover_agent,
        user_msg,
        deps,
        "discover",
        request_limit=max_steps,
    )
    if result is not None:
        emit({
            "type": "final", "agent": "discover",
            "primary_alias": result.primary_alias, "summary": result.summary,
        })
    return result


async def analyze_run(question: str, workspace: Workspace, alias: str, emit: EventEmit, max_steps: int = 5) -> str:
    deps = AnalyzeDeps(workspace=workspace, alias=alias, emit=emit)
    user_msg = (
        f"Dataset alias: {alias}\n"
        f"Profile:\n{json.dumps(profile_df(workspace.get(alias)), default=str)}\n\n"
        f"Question: {question}"
    )
    result = await _run_with_events(
        analyze_agent,
        user_msg,
        deps,
        "analyze",
        request_limit=max_steps,
    )
    if result is None:
        return "Hit step limit without a final answer."
    emit({"type": "final", "agent": "analyze", "summary": result[:300]})
    return result


async def code_analysis_run(
    question: str,
    csv_path: str,
    work_dir: str,
    profile: dict,
    emit: EventEmit,
    max_steps: int = 10,
) -> tuple[Optional[CodeAnalysisResult], list[dict]]:
    """Drive the code agent against a cleaned dataset. Returns (result, recorded_steps)."""
    steps: list[dict] = []
    deps = CodeDeps(csv_path=csv_path, work_dir=work_dir, emit=emit, steps=steps)

    profile_brief = {
        "n_rows": profile.get("row_count") or profile.get("n_rows"),
        "n_cols": profile.get("col_count") or profile.get("n_cols"),
        "columns": [
            {
                "name": c.get("name"),
                "dtype": c.get("dtype_inferred") or c.get("dtype"),
                "n_unique": c.get("unique_count") or c.get("n_unique"),
                "missing_pct": c.get("missing_pct") or c.get("pct_missing"),
                "sample": (c.get("sample_values") or c.get("sample") or [])[:5],
            }
            for c in (profile.get("columns") or [])[:40]
        ],
    }

    user_msg = (
        f"Research question: {question or '(none provided — perform a thorough exploratory analysis)'}\n\n"
        f"Cleaned dataset profile:\n{json.dumps(profile_brief, indent=2, default=str)}\n\n"
        "Investigate the question with real statistical tests + charts. Save charts via `plt.savefig`."
    )
    result = await _run_with_events(
        code_agent, user_msg, deps, "code", request_limit=max_steps,
    )
    if result is not None:
        emit({"type": "final", "agent": "code", "summary": result.summary[:300]})
    return result, steps


async def literature_run(question: str, emit: EventEmit, max_steps: int = 12) -> Optional[LiteratureReport]:
    deps = LiteratureDeps(emit=emit)
    user_msg = (
        f"Research question: {question}\n\n"
        "Search PubMed, fetch the most relevant abstracts, and return a LiteratureReport."
    )
    result = await _run_with_events(
        literature_agent,
        user_msg,
        deps,
        "literature",
        request_limit=max_steps,
    )
    if result is not None:
        emit({
            "type": "final", "agent": "literature",
            "summary": result.summary[:300],
        })
    return result


async def hypotheses_run(workspace: Workspace, alias: str, n: int = 4) -> list[Hypothesis]:
    df = workspace.get(alias)
    profile = profile_df(df)
    sample = df.sample(min(10, len(df)), random_state=0).to_dict(orient="records")
    user_msg = (
        f"Profile:\n{json.dumps(profile, default=str)}\n\n"
        f"Sample rows:\n{json.dumps(sample, default=str)}\n\n"
        f"Propose {n} hypotheses."
    )
    result = await hypo_agent.run(user_msg)
    return result.output


async def plan_run(dataset_context: str) -> str:
    prompt = (
        f"{dataset_context}\n\n"
        "Based on this public health dataset, please propose a concise analysis plan with 5-7 numbered steps. "
        "For each step, briefly explain what will be done and why it matters for public health research. "
        "Focus on exploratory analysis appropriate for this dataset's structure. "
        "Keep the plan actionable and specific to the columns present."
    )
    result = await plan_agent.run(prompt)
    return result.output


async def plan_refine_run(current_plan: str, instruction: str) -> str:
    """Revise an existing analysis plan according to a user instruction."""
    prompt = (
        f"Here is the current analysis plan:\n\n{current_plan}\n\n"
        f"The user wants to change it with the following instruction:\n{instruction}\n\n"
        "Please rewrite the full analysis plan incorporating the requested change. "
        "Keep the same numbered-steps format. Only output the revised plan — no preamble or commentary."
    )
    result = await plan_agent.run(prompt)
    return result.output


async def findings_run(
    dataset_context: str,
    chart_specs: list[dict[str, Any]],
    stats: list[dict[str, Any]],
    cleaning_steps: list[str],
) -> FindingsReport:
    chart_summary = "\n".join(f"- {c['chart_type'].title()} chart: {c['title']}" for c in chart_specs)
    cleaning_summary = "\n".join(f"- {s}" for s in cleaning_steps)
    prompt = f"""{dataset_context}

CLEANING STEPS APPLIED:
{cleaning_summary}

CHARTS GENERATED:
{chart_summary}

Please write a research analysis report with three sections:
- findings: 3-5 paragraph plain-English narrative of the key findings. Describe what the data shows, notable patterns, group comparisons, and any correlations observed. Be specific about column names and values.
- limitations: A bullet-pointed list (using •) of 4-6 limitations of this analysis. Include data quality issues, observational study limitations, confounders, and generalizability concerns.
- follow_up: A numbered list of 5 specific follow-up research questions or experiments that would strengthen the analysis. Be concrete and reference the specific columns and findings.
"""
    result = await findings_agent.run(prompt)
    return result.output


# ---------- Helpers shared with agent.py ----------


def _summarize_discovery_result(op: str, result: dict) -> str:
    if not isinstance(result, dict):
        return str(result)[:120]
    if not result.get("ok", True):
        return f"error: {result.get('error', '?')}"
    if op == "search_catalog":
        names = [r.get("name", "?")[:60] for r in result.get("results", [])[:3]]
        return f"{result.get('n_results', 0)} results — top: {names}"
    if op == "get_dataset_schema":
        return f"{result.get('name', '?')[:60]} — {len(result.get('columns', []))} columns"
    if op == "fetch_dataset":
        return f"loaded `{result.get('alias')}` — {result.get('rows')} rows × {len(result.get('columns', []))} cols"
    if op in ("merge_datasets", "concat_datasets", "aggregate_dataset", "select_columns"):
        return f"`{result.get('alias')}` — {result.get('rows')} rows × {len(result.get('columns', []))} cols"
    if op == "list_workspace":
        return f"{len(result.get('datasets', []))} datasets in workspace"
    return "ok"


def _truncate_result(r: dict) -> dict:
    """Trim large fields out of the log for UI display (keep full payload for the model)."""
    if not isinstance(r, dict):
        return r
    out = dict(r)
    if "results" in out and isinstance(out["results"], list):
        out["results"] = [
            {"id": x.get("id"), "name": x.get("name"), "domain": x.get("domain")}
            for x in out["results"]
        ]
    if "preview" in out:
        out["preview"] = f"<{len(out['preview'])} rows>"
    if "columns" in out and isinstance(out["columns"], list) and len(out["columns"]) > 12:
        out["columns"] = out["columns"][:12] + ["..."]
    return out


def _summarize_literature_result(op: str, result: dict) -> str:
    if not isinstance(result, dict):
        return str(result)[:120]
    if not result.get("ok", True):
        return f"error: {result.get('error', '?')}"
    if op == "search_pubmed":
        return f"{result.get('n_results', 0)} pmids for `{result.get('query', '')[:60]}`"
    if op == "fetch_pubmed":
        n = result.get("n_articles", 0)
        sample = result.get("articles", [])[:1]
        first = sample[0]["title"][:60] if sample else ""
        return f"fetched {n} articles{' — ' + first if first else ''}"
    return "ok"


def _truncate_literature_result(op: str, result: dict) -> dict:
    """Trim large abstract text from the UI log; agent still sees full payload via tool return."""
    if not isinstance(result, dict):
        return result
    out = dict(result)
    if op == "fetch_pubmed" and isinstance(out.get("articles"), list):
        out["articles"] = [
            {
                "pmid": a.get("pmid"),
                "title": a.get("title"),
                "year": a.get("year"),
                "journal": a.get("journal"),
            }
            for a in out["articles"][:6]
        ]
    if op == "search_pubmed" and isinstance(out.get("pmids"), list):
        out["pmids"] = out["pmids"][:10]
    return out


def _summarize_test_result(r: dict) -> str:
    if not isinstance(r, dict) or "error" in r:
        return f"error: {r.get('error', '?')}" if isinstance(r, dict) else str(r)[:120]
    parts = [r.get("test", "?")]
    if "p_value" in r:
        try:
            parts.append(f"p={r['p_value']:.4g}")
        except Exception:
            parts.append(f"p={r['p_value']}")
    if "correlation" in r:
        try:
            parts.append(f"r={r['correlation']:.3f}")
        except Exception:
            pass
    if "cohens_d" in r:
        try:
            parts.append(f"d={r['cohens_d']:.3f}")
        except Exception:
            pass
    return " · ".join(parts)
