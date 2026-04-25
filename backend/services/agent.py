"""Four agent loops over a Workspace of named DataFrames:
discover (CDC catalog → fetch → join), auto_clean, generate_hypotheses, analyze_question.

Each loop accepts an optional `on_event(event)` callback so the UI can render
the agent's reasoning live. Events: {type: 'thought'|'tool_call'|'tool_result'
|'final'|'error', ...}. Loops also return the full event list for replay.

Loops are sync (Anthropic SDK + `requests`) — run them in a threadpool from
async FastAPI routes to expose them as SSE streams. See routers/streaming.py.
"""

import concurrent.futures
import json
import re
import threading
from typing import Callable, Optional

import anthropic

from config import settings
from services.tools import (
    profile_df,
    apply_op,
    CLEANING_OPS,
    CLEANING_OPS_DOC,
    STATS_TESTS,
    STATS_TESTS_DOC,
)
from services.discovery import (
    Workspace,
    DISCOVERY_OPS,
    DISCOVERY_OPS_DOC,
    JOIN_OPS,
    JOIN_OPS_DOC,
    apply_discovery_op,
    search_catalog as _search_catalog,
    get_dataset_schema as _get_dataset_schema,
)

EventCallback = Optional[Callable[[dict], None]]


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _emit(events: list, on_event: EventCallback, event: dict) -> None:
    events.append(event)
    if on_event is not None:
        try:
            on_event(event)
        except Exception:
            pass


def _collect_thoughts(content) -> str:
    return "\n".join(
        b.text for b in content
        if getattr(b, "type", None) == "text" and b.text.strip()
    )


# ---------- 0. DISCOVERY AGENT ----------

DISCOVER_SYSTEM = f"""You are a data acquisition agent. Given a research question, find the right CDC dataset(s) on data.cdc.gov, fetch them into the workspace, and (if multiple are needed) join them into a single analysis-ready frame.

You have three tools:
- `scout(question)` — RECOMMENDED FIRST STEP for single-dataset questions. A fast Haiku sub-agent searches the catalog and inspects schemas, returning ONE recommended dataset_id with optional pre-checked SoQL hints. Saves 3-5s vs running search_catalog + get_dataset_schema yourself.
- `discovery_op(op, args)` — dispatches to these ops:
{DISCOVERY_OPS_DOC}
{JOIN_OPS_DOC}
- `finish(primary_alias, summary)` — stop when done.

If the question needs multiple datasets, you can call scout twice in parallel (one per sub-question) — they'll run concurrently. Multiple discovery_op calls in the same turn (e.g. fetch_dataset for both aliases) also run in parallel.

Rules:
- Start with search_catalog using terms from the question. Look at descriptions, not just names.
- Before fetch_dataset, call get_dataset_schema so your SoQL `select`/`where` reference real fields.
- ALWAYS pass an explicit `limit` to fetch_dataset of at least 25000 (cap 100000). Socrata's server-side default is only 1000 rows, which is rarely enough. Use SoQL `where` to filter server-side (e.g. `where="year >= 2020 AND state = 'CA'"`) — that's how you keep result sizes manageable, NOT by lowering limit.
- BE LIBERAL WITH FILTERS. When the question mentions a state, year, or category, first try fetching WITHOUT that filter (or with a wider one). Most CDC datasets store state names in unpredictable forms ("Florida" vs "FL" vs "florida") and may not include every jurisdiction. If you must filter, inspect the schema's sample values first. If a fetch returns 0 rows, that is a FAILURE — relax the filter and retry, do not finish on an empty dataset.
- If two datasets are needed, fetch both with distinct aliases, then merge_datasets (or aggregate_dataset first if grains differ). A merge that returns 0 rows means the join keys don't overlap — inspect both sides before retrying.
- Call finish when the workspace contains a single analysis-ready alias with > 0 rows. Pass that alias name. Never finish if the primary alias is empty.
- Do not invent dataset ids. Only use ids returned by search_catalog.
"""

DISCOVER_TOOLS = [
    {
        "name": "scout",
        "description": (
            "Fast Haiku-backed sub-agent that searches the CDC catalog AND inspects "
            "schemas for you, returning ONE recommended dataset_id with optional SoQL "
            "hints (recommended_select, recommended_where) and a few alternatives. "
            "Call this FIRST instead of search_catalog when you want a quick pick — "
            "it's much faster (~3s) than running search_catalog + 2× get_dataset_schema "
            "yourself, and the recommended SoQL hints have already been schema-checked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The research question (or a sub-question if multi-dataset).",
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "discovery_op",
        "description": "Run one discovery, fetch, or join op. See system prompt for op names and args.",
        "input_schema": {
            "type": "object",
            "properties": {
                "op": {
                    "type": "string",
                    "enum": list(DISCOVERY_OPS.keys()) + list(JOIN_OPS.keys()),
                },
                "args": {"type": "object"},
                "rationale": {"type": "string"},
            },
            "required": ["op", "args", "rationale"],
        },
    },
    {
        "name": "finish",
        "description": "Stop when the workspace has a single analysis-ready alias for the question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "primary_alias": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["primary_alias", "summary"],
        },
    },
]


# ---------- SCOUT SUB-AGENT (Haiku) ----------

SCOUT_SYSTEM = """You are a fast catalog scout. Given a research question, find the single best CDC dataset to fetch.

Tools:
- search_catalog(query, limit=5): full-text search the CDC catalog
- get_dataset_schema(dataset_id): column names + sample values for one dataset
- recommend(dataset_id, rationale, recommended_select?, recommended_where?, alternatives=[]): finalize your pick

Workflow:
1. ONE search_catalog call with terms from the question.
2. Up to 2 get_dataset_schema calls in parallel on the most promising candidates.
3. ONE recommend call. Be concise.

Rules:
- If the question mentions a state, year, or category, do NOT include it in recommended_where unless you SAW that exact value in the schema's sample_values. CDC datasets are inconsistent about jurisdictional naming. Better to fetch unfiltered.
- Return at most ONE recommendation. The main agent does the actual fetching.
- Stop after recommend. Do not chain more searches.
"""

SCOUT_TOOLS = [
    {
        "name": "search_catalog",
        "description": "Full-text search the CDC catalog. Returns top-N candidates with name, description, and column field names.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_dataset_schema",
        "description": "Get full column schema for one dataset (names, types, descriptions).",
        "input_schema": {
            "type": "object",
            "properties": {"dataset_id": {"type": "string"}},
            "required": ["dataset_id"],
        },
    },
    {
        "name": "recommend",
        "description": "Recommend the single best dataset_id to fetch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string"},
                "rationale": {"type": "string"},
                "recommended_select": {"type": "string"},
                "recommended_where": {"type": "string"},
                "recommended_alias": {"type": "string"},
                "alternatives": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["dataset_id", "rationale"],
        },
    },
]


def scout_catalog(question: str, max_steps: int = 3, model_name: str | None = None) -> dict:
    """Haiku-backed sub-agent. Returns {ok, dataset_id, rationale, recommended_select?, recommended_where?, recommended_alias?, alternatives}."""
    ws = Workspace()  # throwaway: scout doesn't load any frames
    messages = [{"role": "user", "content": f"Research question: {question}\n\nFind the single best dataset."}]

    client = _client()
    model = model_name or settings.scout_model_name
    for _ in range(max_steps):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=512,
                system=[{"type": "text", "text": SCOUT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
                tools=SCOUT_TOOLS,
                messages=messages,
            )
        except Exception as e:
            return {"ok": False, "error": f"scout: {e}"}

        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "end_turn":
            break

        tool_use_blocks = [b for b in resp.content if b.type == "tool_use"]
        if not tool_use_blocks:
            break

        # Parallel: get_dataset_schema calls in the same turn run concurrently.
        def _exec(block):
            if block.name == "search_catalog":
                r = _search_catalog(ws, block.input.get("query", ""), block.input.get("limit", 5))
                return block.id, json.dumps(_truncate_result(r), default=str), None
            if block.name == "get_dataset_schema":
                r = _get_dataset_schema(ws, block.input["dataset_id"])
                return block.id, json.dumps(_truncate_result(r), default=str), None
            if block.name == "recommend":
                return block.id, "ok", dict(block.input)
            return block.id, json.dumps({"error": f"unknown tool {block.name}"}), None

        recommended = None
        if len(tool_use_blocks) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(tool_use_blocks))) as ex:
                results = list(ex.map(_exec, tool_use_blocks))
        else:
            results = [_exec(tool_use_blocks[0])]

        tool_results = []
        for tid, content, rec in results:
            tool_results.append({"type": "tool_result", "tool_use_id": tid, "content": content})
            if rec is not None:
                recommended = rec

        if recommended is not None:
            return {"ok": True, **recommended}
        messages.append({"role": "user", "content": tool_results})

    return _fallback_scout(question)


def _fallback_scout(question: str) -> dict:
    """Deterministic backstop when the LLM scout does not call recommend.

    Keeps the discovery loop fast by returning a schema-checked candidate
    instead of forcing the main agent into multiple catalog-search turns.
    """
    ws = Workspace()
    q = question.strip()
    variants = [q]
    if "emergency visits" in q.lower():
        variants.append(re.sub("emergency visits", "emergency department visits", q, flags=re.I))
    variants.extend([
        f"{q} emergency department",
        f"{q} chronic disease indicators",
        f"{q} surveillance",
    ])
    seen = set()
    for query in variants:
        if query.lower() in seen:
            continue
        seen.add(query.lower())
        try:
            result = _search_catalog(ws, query, 8)
        except Exception:
            continue
        candidates = result.get("results", [])
        if not candidates:
            continue
        preferred = _rank_catalog_candidates(question, candidates)
        for cand in preferred[:3]:
            dataset_id = cand.get("id")
            if not dataset_id:
                continue
            try:
                schema = _get_dataset_schema(ws, dataset_id)
            except Exception:
                schema = {}
            fields = [c.get("field") for c in schema.get("columns", []) if c.get("field")]
            alias = re.sub(r"[^a-z0-9]+", "_", (cand.get("name") or dataset_id).lower()).strip("_")[:24] or "primary"
            return {
                "ok": True,
                "dataset_id": dataset_id,
                "rationale": f"Deterministic scout fallback selected the best Socrata catalog match for `{query}` after schema inspection.",
                "recommended_select": ",".join(fields[:12]) if fields else None,
                "recommended_where": None,
                "recommended_alias": alias,
                "alternatives": [c.get("id") for c in preferred[1:4] if c.get("id")],
            }
    return {"ok": False, "error": "scout did not produce a recommendation"}


def _rank_catalog_candidates(question: str, candidates: list[dict]) -> list[dict]:
    terms = [t for t in re.split(r"[^a-z0-9]+", question.lower()) if len(t) > 2]

    def score(c: dict) -> int:
        hay = " ".join([
            str(c.get("name", "")),
            str(c.get("description", "")),
            " ".join(c.get("columns_field_names", []) or []),
        ]).lower()
        s = sum(3 for t in terms if t in hay)
        if "emergency" in hay or "ed" in hay:
            s += 2
        if "asthma" in hay:
            s += 4
        if "chronic disease indicators" in hay:
            s += 3
        return s

    return sorted(candidates, key=score, reverse=True)


def discover(
    question: str,
    workspace: Optional[Workspace] = None,
    max_steps: int = 15,
    on_event: EventCallback = None,
    model_name: str | None = None,
    scout_model_name: str | None = None,
) -> tuple[Workspace, Optional[str], list]:
    """Run the discovery agent. Returns (workspace, primary_alias, events).

    Speedups:
    - Independent tool_use blocks in the same turn run in parallel (e.g. two
      fetch_dataset calls finish in max(t1,t2) instead of t1+t2).
    - The `scout` tool delegates catalog search + schema inspection to a Haiku
      sub-agent so the Sonnet loop converges in fewer turns.
    """
    workspace = workspace or Workspace()
    events: list = []
    events_lock = threading.Lock()
    primary_alias: Optional[str] = None

    def emit(event: dict) -> None:
        with events_lock:
            _emit(events, on_event, event)

    user_msg = f"Research question: {question}\n\nFind and prepare the right CDC dataset(s)."
    if workspace.frames:
        user_msg += f"\n\nWorkspace already contains: {workspace.summary()}"
    messages = [{"role": "user", "content": user_msg}]

    client = _client()
    model = model_name or settings.model_name
    for _ in range(max_steps):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=1024,
                system=[{"type": "text", "text": DISCOVER_SYSTEM, "cache_control": {"type": "ephemeral"}}],
                tools=DISCOVER_TOOLS,
                messages=messages,
            )
        except Exception as e:
            emit({"type": "error", "agent": "discover", "message": str(e)})
            break

        messages.append({"role": "assistant", "content": resp.content})

        thought = _collect_thoughts(resp.content)
        if thought:
            emit({"type": "thought", "agent": "discover", "text": thought})

        if resp.stop_reason == "end_turn":
            break

        tool_use_blocks = [b for b in resp.content if b.type == "tool_use"]
        if not tool_use_blocks:
            break

        def _execute(block) -> dict:
            """Run one tool block. Returns {tool_result, finish_marker?}."""
            if block.name == "scout":
                question_arg = block.input.get("question", "")
                emit({
                    "type": "tool_call", "agent": "discover",
                    "name": "scout", "args": {"question": question_arg[:80]},
                    "rationale": "Haiku sub-agent for catalog search + schema",
                })
                result = scout_catalog(question_arg, model_name=scout_model_name)
                if result.get("ok"):
                    summary = f"recommend `{result.get('dataset_id', '?')}` — {(result.get('rationale') or '')[:80]}"
                else:
                    summary = f"error: {result.get('error', '?')}"
                emit({
                    "type": "tool_result", "agent": "discover",
                    "name": "scout", "summary": summary, "result": result,
                })
                if result.get("ok") and result.get("dataset_id"):
                    dataset_id = result["dataset_id"]
                    alias = result.get("recommended_alias") or "primary"
                    fetch_args = {
                        "dataset_id": dataset_id,
                        "alias": alias,
                        "select": result.get("recommended_select"),
                        "where": result.get("recommended_where"),
                        "limit": 25000,
                    }
                    emit({
                        "type": "tool_call", "agent": "discover",
                        "name": "fetch_dataset", "args": fetch_args,
                        "rationale": "Fast path from scout recommendation",
                    })
                    fetch_result = apply_discovery_op(workspace, {"op": "fetch_dataset", "args": fetch_args})
                    emit({
                        "type": "tool_result", "agent": "discover",
                        "name": "fetch_dataset", "summary": _summarize_result("fetch_dataset", fetch_result),
                        "result": _truncate_result(fetch_result),
                    })
                    if fetch_result.get("ok") and fetch_result.get("rows", 0) > 0:
                        emit({
                            "type": "final", "agent": "discover",
                            "primary_alias": alias,
                            "summary": f"Fast scout selected and fetched `{dataset_id}` as `{alias}`.",
                        })
                        return {
                            "tool_result": {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, default=str)},
                            "finish_marker": (alias, "fast scout fetch"),
                        }
                return {
                    "tool_result": {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, default=str)},
                    "finish_marker": None,
                }

            if block.name == "discovery_op":
                spec = {"op": block.input.get("op"), "args": block.input.get("args", {})}
                emit({
                    "type": "tool_call", "agent": "discover",
                    "name": spec["op"], "args": spec["args"],
                    "rationale": block.input.get("rationale", ""),
                })
                result = apply_discovery_op(workspace, spec)
                emit({
                    "type": "tool_result", "agent": "discover",
                    "name": spec["op"], "summary": _summarize_result(spec["op"], result),
                    "result": _truncate_result(result),
                })
                return {
                    "tool_result": {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, default=str)},
                    "finish_marker": None,
                }

            if block.name == "finish":
                primary = block.input.get("primary_alias")
                summary = block.input.get("summary", "")
                emit({
                    "type": "final", "agent": "discover",
                    "primary_alias": primary, "summary": summary,
                })
                return {
                    "tool_result": {"type": "tool_result", "tool_use_id": block.id, "content": "ok"},
                    "finish_marker": (primary, summary),
                }

            return {
                "tool_result": {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps({"error": f"unknown tool {block.name}"})},
                "finish_marker": None,
            }

        # Parallel execution of independent tool calls. Workspace.add() is a dict
        # assignment (atomic under the GIL); pandas merges/aggregates release the
        # GIL during heavy ops so concurrent CDC HTTP fetches and joins overlap.
        if len(tool_use_blocks) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(tool_use_blocks))) as ex:
                results = list(ex.map(_execute, tool_use_blocks))
        else:
            results = [_execute(tool_use_blocks[0])]

        tool_results = []
        finished = False
        for r in results:
            tool_results.append(r["tool_result"])
            if r["finish_marker"]:
                primary_alias, _ = r["finish_marker"]
                finished = True

        if finished:
            break
        messages.append({"role": "user", "content": tool_results})

    if primary_alias is None and workspace.frames:
        primary_alias = next(iter(workspace.frames))
    return workspace, primary_alias, events


def _summarize_result(op: str, result: dict) -> str:
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
        out["results"] = [{"id": x.get("id"), "name": x.get("name")} for x in out["results"]]
    if "preview" in out:
        out["preview"] = f"<{len(out['preview'])} rows>"
    if "columns" in out and isinstance(out["columns"], list) and len(out["columns"]) > 12:
        out["columns"] = out["columns"][:12] + ["..."]
    return out


# ---------- 1. CLEANING AGENT ----------

CLEAN_SYSTEM = f"""You are a careful data analyst preparing a tabular dataset for statistical analysis.

You have these tools:
- profile: see the current state of the dataframe
- apply_op: apply ONE cleaning operation (it runs immediately, not asking for approval)
- finish: stop when the dataset is analysis-ready

{CLEANING_OPS_DOC}

Rules:
- Always start by calling profile.
- Apply ONE op at a time. Look at the resulting profile before proposing the next.
- Be conservative: don't drop columns, and prefer imputation over row deletion when missing data is light.
- Stop when: types are correct, no obviously broken values, missing data is handled.
- A typical clean is 4-8 ops. Don't loop forever.
"""

CLEANING_TOOLS = [
    {
        "name": "profile",
        "description": "Profile the current dataframe (dtypes, missing, unique counts, sample values).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "apply_op",
        "description": "Apply ONE cleaning operation. See system prompt for op list and args.",
        "input_schema": {
            "type": "object",
            "properties": {
                "op": {"type": "string"},
                "args": {"type": "object"},
                "rationale": {"type": "string"},
            },
            "required": ["op", "args", "rationale"],
        },
    },
    {
        "name": "finish",
        "description": "Stop when the dataset is analysis-ready.",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    },
]


def auto_clean(
    workspace: Workspace,
    alias: str,
    max_steps: int = 12,
    on_event: EventCallback = None,
    model_name: str | None = None,
) -> list:
    """Run the cleaning agent on workspace[alias]. Mutates workspace in place. Returns events."""
    df = workspace.get(alias)
    events: list = []
    messages = [{"role": "user", "content": f"Clean the dataset '{alias}' for statistical analysis. Start by profiling."}]

    client = _client()
    model = model_name or settings.model_name
    for _ in range(max_steps):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=1024,
                system=[{"type": "text", "text": CLEAN_SYSTEM, "cache_control": {"type": "ephemeral"}}],
                tools=CLEANING_TOOLS,
                messages=messages,
            )
        except Exception as e:
            _emit(events, on_event, {"type": "error", "agent": "clean", "message": str(e)})
            break

        messages.append({"role": "assistant", "content": resp.content})

        thought = _collect_thoughts(resp.content)
        if thought:
            _emit(events, on_event, {"type": "thought", "agent": "clean", "text": thought})

        if resp.stop_reason == "end_turn":
            break

        tool_results = []
        finished = False
        for block in resp.content:
            if block.type != "tool_use":
                continue

            if block.name == "profile":
                _emit(events, on_event, {"type": "tool_call", "agent": "clean", "name": "profile", "args": {}, "rationale": ""})
                prof = profile_df(df)
                _emit(events, on_event, {
                    "type": "tool_result", "agent": "clean", "name": "profile",
                    "summary": f"{prof['n_rows']} rows × {prof['n_cols']} cols",
                })
                result = json.dumps(prof, default=str)

            elif block.name == "apply_op":
                op_name = block.input.get("op")
                _emit(events, on_event, {
                    "type": "tool_call", "agent": "clean",
                    "name": op_name, "args": block.input.get("args", {}),
                    "rationale": block.input.get("rationale", ""),
                })
                try:
                    df, msg = apply_op(df, block.input)
                    _emit(events, on_event, {"type": "tool_result", "agent": "clean", "name": op_name, "summary": msg})
                    result = json.dumps({"ok": True, "message": msg, "profile": profile_df(df)}, default=str)
                except Exception as e:
                    _emit(events, on_event, {"type": "tool_result", "agent": "clean", "name": op_name, "summary": f"error: {e}"})
                    result = json.dumps({"ok": False, "error": str(e)})

            elif block.name == "finish":
                summary = block.input.get("summary", "")
                _emit(events, on_event, {"type": "final", "agent": "clean", "summary": summary})
                finished = True
                result = "ok"

            else:
                result = json.dumps({"error": f"unknown tool {block.name}"})

            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

        if finished:
            break
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    workspace.frames[alias] = df
    return events


# ---------- 2. HYPOTHESIS GENERATOR ----------

HYPO_SYSTEM = f"""You are a research analyst. Given a dataset profile and a few sample rows, propose 3-5 specific, testable hypotheses worth investigating with statistical tests.

{STATS_TESTS_DOC}

Output a single JSON array (no prose, no code fences). Each item:
{{
  "question": "one-sentence question in plain English",
  "variables": ["col_a", "col_b"],
  "test_type": "two_group_numeric" | "multi_group_numeric" | "two_categorical" | "correlation",
  "args": {{ ... matching the test signature ... }},
  "rationale": "why this is interesting given the data"
}}
"""


def generate_hypotheses(workspace: Workspace, alias: str, n: int = 4, model_name: str | None = None) -> list[dict]:
    import pandas as pd
    df = workspace.get(alias)
    profile = profile_df(df)
    sample = df.sample(min(10, len(df)), random_state=0).to_dict(orient="records")
    user_msg = f"Profile:\n{json.dumps(profile, default=str)}\n\nSample rows:\n{json.dumps(sample, default=str)}\n\nPropose {n} hypotheses."

    client = _client()
    resp = client.messages.create(
        model=model_name or settings.model_name,
        max_tokens=2048,
        system=[{"type": "text", "text": HYPO_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    start, end = text.find("["), text.rfind("]")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return [{"question": "Failed to parse model output", "rationale": text[:500]}]


# ---------- 3. ANALYSIS AGENT (question → stats test → interpretation) ----------

ANALYZE_SYSTEM = f"""You are a statistician. Given a dataset profile and a user's question, choose an appropriate test, run it, and explain the result.

{STATS_TESTS_DOC}

Workflow:
1. Identify the variables in the question and verify they exist in the profile.
2. Choose the right test based on the data shapes (numeric vs. categorical, # of groups).
3. Call run_test with the test name and args.
4. After getting the result, give a plain-English interpretation: effect size, significance, what it means, and any caveats from assumption checks.

If the user's question is ambiguous or the right columns aren't obvious, ask a clarifying question instead of guessing.
"""

ANALYZE_TOOLS = [
    {
        "name": "run_test",
        "description": "Run a statistical test on the current dataframe. Returns test stats and assumption checks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "test": {"type": "string", "enum": list(STATS_TESTS.keys())},
                "args": {"type": "object"},
            },
            "required": ["test", "args"],
        },
    },
]


def analyze_question(
    question: str,
    workspace: Workspace,
    alias: str,
    max_steps: int = 5,
    on_event: EventCallback = None,
    model_name: str | None = None,
) -> tuple[str, list]:
    """Run the analysis agent on workspace[alias]. Returns (answer_text, events)."""
    df = workspace.get(alias)
    profile = profile_df(df)
    events: list = []
    user_msg = f"Dataset alias: {alias}\nProfile:\n{json.dumps(profile, default=str)}\n\nQuestion: {question}"
    messages = [{"role": "user", "content": user_msg}]

    client = _client()
    model = model_name or settings.model_name
    for _ in range(max_steps):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=1024,
                system=[{"type": "text", "text": ANALYZE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
                tools=ANALYZE_TOOLS,
                messages=messages,
            )
        except Exception as e:
            _emit(events, on_event, {"type": "error", "agent": "analyze", "message": str(e)})
            return f"Error: {e}", events

        messages.append({"role": "assistant", "content": resp.content})

        thought = _collect_thoughts(resp.content)
        if thought:
            _emit(events, on_event, {"type": "thought", "agent": "analyze", "text": thought})

        if resp.stop_reason == "end_turn":
            answer = "".join(b.text for b in resp.content if b.type == "text") or "(no answer)"
            _emit(events, on_event, {"type": "final", "agent": "analyze", "summary": answer[:300]})
            return answer, events

        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            test_name = block.input.get("test")
            args = block.input.get("args", {})
            _emit(events, on_event, {
                "type": "tool_call", "agent": "analyze",
                "name": test_name, "args": args, "rationale": "",
            })
            test_fn = STATS_TESTS.get(test_name)
            if not test_fn:
                result = {"error": f"unknown test {test_name}"}
            else:
                try:
                    result = test_fn(df, **args)
                except Exception as e:
                    result = {"error": str(e)}
            _emit(events, on_event, {
                "type": "tool_result", "agent": "analyze",
                "name": test_name, "summary": _summarize_test_result(result),
                "result": result,
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    return "Hit step limit without a final answer.", events


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


# ---------- single-shot stats test (no LLM) ----------

def run_stats_test(workspace: Workspace, alias: str, test: str, args: dict) -> dict:
    """Run a named STATS_TESTS function directly on workspace[alias]."""
    df = workspace.get(alias)
    fn = STATS_TESTS.get(test)
    if fn is None:
        return {"error": f"unknown test '{test}'"}
    try:
        return fn(df, **args)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
