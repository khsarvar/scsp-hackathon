"""Four agent loops over a Workspace of named DataFrames:
discover (CDC catalog → fetch → join), clean, hypothesize, analyze.

Each loop accepts an optional `on_event(event)` callback so the UI can render
the agent's reasoning live. Events: {type: 'thought'|'tool_call'|'tool_result'
|'final', ...}. Loops also return the full event list for replay."""

import json
import os
from typing import Callable, Optional

from anthropic import Anthropic

EventCallback = Optional[Callable[[dict], None]]

from tools import (
    profile_df,
    apply_op,
    CLEANING_OPS,
    CLEANING_OPS_DOC,
    STATS_TESTS,
    STATS_TESTS_DOC,
)
from discovery import (
    Workspace,
    DISCOVERY_OPS,
    DISCOVERY_OPS_DOC,
    JOIN_OPS,
    JOIN_OPS_DOC,
    apply_discovery_op,
)

client = Anthropic()
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")


def _emit(events: list, on_event: EventCallback, event: dict) -> None:
    events.append(event)
    if on_event is not None:
        try:
            on_event(event)
        except Exception:
            pass


def _collect_thoughts(content) -> str:
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text" and b.text.strip())


# ---------- 0. DISCOVERY AGENT ----------

DISCOVER_SYSTEM = f"""You are a data acquisition agent. Given a research question, find the right CDC dataset(s) on data.cdc.gov, fetch them into the workspace, and (if multiple are needed) join them into a single analysis-ready frame.

You have one tool, `discovery_op`, which dispatches to these ops:

{DISCOVERY_OPS_DOC}

{JOIN_OPS_DOC}

Rules:
- Start with search_catalog using terms from the question. Look at descriptions, not just names.
- Before fetch_dataset, call get_dataset_schema so your SoQL `select`/`where` reference real fields.
- ALWAYS pass an explicit `limit` to fetch_dataset of at least 25000 (cap 100000). Socrata's server-side default is only 1000 rows, which is rarely enough. Use SoQL `where` to filter server-side (e.g. `where="year >= 2020 AND state = 'CA'"`) — that's how you keep result sizes manageable, NOT by lowering limit.
- If two datasets are needed, fetch both with distinct aliases, then merge_datasets (or aggregate_dataset first if grains differ).
- Call finish when the workspace contains a single analysis-ready alias for the question. Pass that alias name.
- Do not invent dataset ids. Only use ids returned by search_catalog.
"""

DISCOVER_TOOLS = [
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
                "primary_alias": {"type": "string", "description": "Alias the next stages should use"},
                "summary": {"type": "string"},
            },
            "required": ["primary_alias", "summary"],
        },
    },
]


def discover(
    question: str,
    workspace: Workspace | None = None,
    max_steps: int = 15,
    on_event: EventCallback = None,
) -> tuple[Workspace, str, list]:
    """Run the discovery agent. Returns (workspace, primary_alias, events)."""
    workspace = workspace or Workspace()
    events: list = []
    primary_alias = None

    user_msg = f"Research question: {question}\n\nFind and prepare the right CDC dataset(s)."
    if workspace.frames:
        user_msg += f"\n\nWorkspace already contains: {workspace.summary()}"
    messages = [{"role": "user", "content": user_msg}]

    for _ in range(max_steps):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=DISCOVER_SYSTEM,
            tools=DISCOVER_TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        thought = _collect_thoughts(resp.content)
        if thought:
            _emit(events, on_event, {"type": "thought", "agent": "discover", "text": thought})

        if resp.stop_reason == "end_turn":
            break

        tool_results = []
        finished = False
        for block in resp.content:
            if block.type != "tool_use":
                continue

            if block.name == "discovery_op":
                spec = {"op": block.input.get("op"), "args": block.input.get("args", {})}
                _emit(events, on_event, {
                    "type": "tool_call", "agent": "discover",
                    "name": spec["op"], "args": spec["args"],
                    "rationale": block.input.get("rationale", ""),
                })
                result = apply_discovery_op(workspace, spec)
                _emit(events, on_event, {
                    "type": "tool_result", "agent": "discover",
                    "name": spec["op"], "summary": _summarize_result(spec["op"], result),
                    "result": _truncate_result(result),
                })
                payload = json.dumps(result, default=str)

            elif block.name == "finish":
                primary_alias = block.input.get("primary_alias")
                summary = block.input.get("summary", "")
                _emit(events, on_event, {
                    "type": "final", "agent": "discover",
                    "primary_alias": primary_alias, "summary": summary,
                })
                finished = True
                payload = "ok"

            else:
                payload = json.dumps({"error": f"unknown tool {block.name}"})

            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": payload})

        if finished:
            break
        if tool_results:
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
                "op": {"type": "string", "description": "Op name"},
                "args": {"type": "object", "description": "Args for the op"},
                "rationale": {"type": "string", "description": "Why this op is needed"},
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


def auto_clean(workspace: Workspace, alias: str, max_steps: int = 12, on_event: EventCallback = None):
    """Run the cleaning agent on workspace[alias]. Mutates workspace in place. Returns events."""
    df = workspace.get(alias)
    events: list = []
    messages = [{"role": "user", "content": f"Clean the dataset '{alias}' for statistical analysis. Start by profiling."}]

    for _ in range(max_steps):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=CLEAN_SYSTEM,
            tools=CLEANING_TOOLS,
            messages=messages,
        )
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


def generate_hypotheses(workspace: Workspace, alias: str, n: int = 4):
    df = workspace.get(alias)
    profile = profile_df(df)
    sample = df.sample(min(10, len(df)), random_state=0).to_dict(orient="records")
    user_msg = f"Profile:\n{json.dumps(profile, default=str)}\n\nSample rows:\n{json.dumps(sample, default=str)}\n\nPropose {n} hypotheses."

    resp = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=HYPO_SYSTEM,
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


# ---------- 3. ANALYSIS AGENT ----------

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


def analyze(question: str, workspace: Workspace, alias: str, max_steps: int = 5, on_event: EventCallback = None):
    """Run the analysis agent on workspace[alias]. Returns (answer_text, events)."""
    df = workspace.get(alias)
    profile = profile_df(df)
    events: list = []
    user_msg = f"Dataset alias: {alias}\nProfile:\n{json.dumps(profile, default=str)}\n\nQuestion: {question}"
    messages = [{"role": "user", "content": user_msg}]

    for _ in range(max_steps):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=ANALYZE_SYSTEM,
            tools=ANALYZE_TOOLS,
            messages=messages,
        )
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
        parts.append(f"p={r['p_value']:.4g}")
    if "correlation" in r:
        parts.append(f"r={r['correlation']:.3f}")
    if "cohens_d" in r:
        parts.append(f"d={r['cohens_d']:.3f}")
    return " · ".join(parts)
