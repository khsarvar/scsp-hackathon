# Data Analyst Agent

Drop in a dataset. The agent profiles it, cleans it, proposes hypotheses worth testing, and runs the right statistical test on demand — picking parametric or non-parametric versions based on assumption checks.

Three agent loops over a pandas dataframe:

1. **Auto-clean** — agent calls `profile`, then applies cleaning ops one at a time (whitespace, type coercion, dedup, imputation, outlier clipping, etc.), re-profiling between each step.
2. **Hypothesis generator** — given the clean dataset's profile + sample rows, proposes 3–5 specific testable hypotheses with the test type and rationale.
3. **Analyze** — natural-language question → picks the right test, checks assumptions, runs it (with non-parametric fallback if violated), interprets the result.

## Setup

```bash
cd data-analyst-agent
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
streamlit run app.py
```

Optional model override:

```bash
export ANTHROPIC_MODEL=claude-sonnet-4-5   # default
```

## Using your own datasets (CDC or otherwise)

Drop CSV/XLSX files into `./data/`. They'll appear in the sidebar under **Local datasets**.

A messy starter dataset (`sample_dirty.csv`) is included so you can demo the cleaner immediately — it has whitespace, mixed casing in categoricals, `"unknown"` strings in a numeric column, mixed date formats, a missing date, and a duplicate row.

## Demo flow (good for stage)

1. Pick `sample_dirty.csv` in the sidebar.
2. **1. Clean** → click **Auto-clean**. Watch the log fill in: strip whitespace → lowercase → coerce numeric → parse datetime → drop duplicates → impute median.
3. **2. Hypotheses** → click **Generate hypotheses**. The agent reads the cleaned profile and proposes 3–5 questions. Click **Run this** on the most interesting one.
4. **3. Analyze** → it lands in the question box, click **Analyze**. Agent picks a test, runs it, gives you a plain-English result.
5. Bonus: type your own question, e.g. *"Does BMI correlate with blood pressure?"*

## Architecture

```
app.py        Streamlit UI — sidebar source picker, three tabs
agent.py      Three agent loops (auto_clean, generate_hypotheses, analyze)
              Uses Anthropic tool use; LLM only chooses ops, never writes code
tools.py      Deterministic functions:
                profile_df()
                CLEANING_OPS  (11 named ops, fixed signatures)
                STATS_TESTS   (4 tests, each with assumption checks + fallback)
data/         Drop your CSV/XLSX files here
```

## Why this works

The LLM never writes pandas or scipy. It picks named ops and tests from a small fixed vocabulary and supplies arguments. That's why it's reliable enough to demo on stage. The "agentic" part is the loop: the agent observes the data after each op, decides what to do next, and self-corrects when an op fails.

## Tweak guide

- **Add a cleaning op**: decorate a function in `tools.py` with `@_op("name")` and add a line to `CLEANING_OPS_DOC`. The agent sees it on the next run.
- **Add a statistical test**: write a function returning a dict with `test`, `p_value`, `interpretation`, and any other fields you want shown; add it to `STATS_TESTS` and `STATS_TESTS_DOC`.
- **Change the agent's personality**: edit the system prompts at the top of each section in `agent.py`.
