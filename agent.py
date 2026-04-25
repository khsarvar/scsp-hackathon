"""Three agent loops over a pandas dataframe: clean, hypothesize, analyze."""

import json
import os

from anthropic import Anthropic

from tools import (
    profile_df,
    apply_op,
    CLEANING_OPS,
    CLEANING_OPS_DOC,
    STATS_TESTS,
    STATS_TESTS_DOC,
)

client = Anthropic()
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")


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


def auto_clean(df, max_steps=12):
    """Run the cleaning agent autonomously. Returns (cleaned_df, log)."""
    log = []
    messages = [{"role": "user", "content": "Clean this dataset for statistical analysis. Start by profiling."}]

    for _ in range(max_steps):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=CLEAN_SYSTEM,
            tools=CLEANING_TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "end_turn":
            break

        tool_results = []
        finished = False
        for block in resp.content:
            if block.type != "tool_use":
                continue

            if block.name == "profile":
                result = json.dumps(profile_df(df), default=str)

            elif block.name == "apply_op":
                try:
                    df, msg = apply_op(df, block.input)
                    log.append({
                        "op": block.input.get("op"),
                        "args": block.input.get("args"),
                        "rationale": block.input.get("rationale"),
                        "result": msg,
                    })
                    result = json.dumps({"ok": True, "message": msg, "profile": profile_df(df)}, default=str)
                except Exception as e:
                    log.append({"op": block.input.get("op"), "args": block.input.get("args"), "error": str(e)})
                    result = json.dumps({"ok": False, "error": str(e)})

            elif block.name == "finish":
                log.append({"finish": block.input.get("summary", "")})
                finished = True
                result = "ok"

            else:
                result = json.dumps({"error": f"unknown tool {block.name}"})

            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

        if finished:
            break
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    return df, log


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


def generate_hypotheses(df, n=4):
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


def analyze(question, df, max_steps=5):
    """Run the analysis agent. Returns final text answer."""
    profile = profile_df(df)
    user_msg = f"Profile:\n{json.dumps(profile, default=str)}\n\nQuestion: {question}"
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

        if resp.stop_reason == "end_turn":
            return "".join(b.text for b in resp.content if b.type == "text") or "(no answer)"

        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            test_name = block.input.get("test")
            args = block.input.get("args", {})
            test_fn = STATS_TESTS.get(test_name)
            if not test_fn:
                result = {"error": f"unknown test {test_name}"}
            else:
                try:
                    result = test_fn(df, **args)
                except Exception as e:
                    result = {"error": str(e)}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    return "Hit step limit without a final answer."
