# Data Analyst Agent

Ask a research question. The agent finds the right CDC dataset(s) (or use your own), pulls them, cleans them, proposes hypotheses, and runs the right statistical test — picking parametric or non-parametric versions based on assumption checks. Every step shows you its reasoning.

Four agent loops over a shared **Workspace** of named DataFrames:

1. **Discover** — given a research question, searches the CDC's Socrata catalog (`data.cdc.gov`), inspects schemas, fetches via SoQL, and (when needed) joins or aggregates two datasets into a single analysis-ready frame.
2. **Auto-clean** — applies cleaning ops one at a time (whitespace, type coercion, dedup, imputation, outlier clipping, etc.), re-profiling between each step.
3. **Hypothesis generator** — given a profile + sample rows, proposes 3–5 specific testable hypotheses with test type and rationale.
4. **Analyze** — natural-language question → picks the right test, checks assumptions, runs it (with non-parametric fallback if violated), interprets the result.

Each loop streams its **thought process** live: a compact feed of `💭 thought → 🔧 tool call → ✓ result → 🏁 done` in the UI.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
streamlit run app.py
```

Optional model override:

```bash
export ANTHROPIC_MODEL=claude-sonnet-4-5   # default
```

## Using it

Three data sources in the sidebar:

- **Discover (CDC)** — type a research question. The agent searches `data.cdc.gov`, picks dataset(s), pulls them via the SoQL API, and lands them in the workspace under short aliases. For multi-dataset questions it also joins/aggregates them.
- **Upload CSV/XLSX** — drag and drop. Loads as alias `main`.
- **Local datasets** — drop CSV/XLSX files into `./data/`. They appear in the picker.

The sidebar shows everything currently loaded in the workspace (alias → rows × cols → source). Pick the **active dataset** to point the Clean / Hypotheses / Analyze tabs at it. You can switch between aliases to inspect parents of a merge, parameters of an aggregation, etc.

The main pane shows the full active dataframe (virtualized scrolling) with a **Download CSV** button for the complete frame.

### Demo flows

**CDC end-to-end:** type *"How does flu vaccination coverage relate to influenza hospitalization rates by state?"* in **Discover**. The agent searches the catalog, fetches two datasets, merges on `state`+`season`, hands off the merged frame. Then **Auto-clean** → **Generate hypotheses** → **Run this** on the most interesting one.

**Local demo:** pick the bundled `sample_dirty.csv` (whitespace, mixed casing, `"unknown"` in a numeric column, mixed date formats, a duplicate row). **Auto-clean** turns it analysis-ready in 4–8 ops; **Hypotheses** then **Analyze** finishes the loop.

## Architecture

```
app.py         Streamlit UI — sidebar source picker, workspace switcher,
               live thought-process panels per agent
agent.py       Four agent loops: discover, auto_clean, generate_hypotheses,
               analyze. Each accepts an on_event callback for live streaming.
discovery.py   Socrata catalog search, SoQL fetch, multi-dataset Workspace,
               and join / concat / aggregate / select_columns ops.
tools.py       Deterministic functions:
                 profile_df()
                 CLEANING_OPS   (11 named ops, fixed signatures)
                 STATS_TESTS    (4 tests, each with assumption checks + fallback)
data/          Drop your CSV/XLSX files here
```

The **Workspace** (`discovery.Workspace`) replaces a single `df` in session state with `{alias: DataFrame}` plus light metadata (source, parents). All four loops take `(workspace, alias)`; the discover loop produces aliases, the others consume them.

## Why this works

The LLM never writes pandas, scipy, or HTTP code. It picks named ops from small fixed vocabularies (`CLEANING_OPS`, `STATS_TESTS`, `DISCOVERY_OPS`, `JOIN_OPS`) and supplies arguments. That's why it's reliable enough to demo. The "agentic" part is the loops: each agent observes state after every op, decides what to do next, and self-corrects when an op fails (HTTP errors, bad columns, sparse contingency tables, etc. all come back as `{ok: false, error}` rather than crashing).

## Multi-dataset patterns

The `JOIN_OPS` registry makes a few common patterns one tool call each:

- **Same grain, different metric** — vaccination coverage by state + flu hospitalization by state → `merge_datasets` on `state, season`.
- **Cross-grain alignment** — county-level mortality + state-level demographics → `aggregate_dataset(group_by="state", agg={"deaths": "sum"})` first, then merge.
- **Cross-time concat** — three yearly chronic-disease tables → `concat_datasets(["cdi_2022","cdi_2023","cdi_2024"])` (with a `_source_alias` column so the year survives).

The discover-loop system prompt tells the agent the recommended order: search → fetch each → align grain → merge → hand off.

## Tweak guide

- **Add a cleaning op**: decorate a function in `tools.py` with `@_op("name")` and add a line to `CLEANING_OPS_DOC`.
- **Add a statistical test**: write a function returning a dict with `test`, `p_value`, `interpretation`; add it to `STATS_TESTS` and `STATS_TESTS_DOC`. The `analyze` tool's enum is regenerated from `STATS_TESTS` on import.
- **Add a discovery / join op**: add a function `(workspace, **args) -> dict` to `DISCOVERY_OPS` or `JOIN_OPS` in `discovery.py` and append a line to the corresponding `_DOC`. The discover-loop tool's enum picks it up automatically.
- **Change an agent's personality / rules**: edit the system prompts at the top of each section in `agent.py`.
- **Surface a different live event style**: events are structured (`thought`, `tool_call`, `tool_result`, `final`); change `render_event` in `app.py`.

## Notes / limits

- Socrata's server-side default `$limit` is 1000. The discover loop is prompted (and code-defaulted) to ask for 25,000 rows per fetch; cap is 100,000. For larger pulls, filter server-side with SoQL `where=` rather than raising the cap.
- No app token is set, so you'll hit Socrata's anonymous rate limits on heavy use. Add `X-App-Token` to `_catalog_get` / requests in `discovery.py` if needed.
- The hypothesis generator is single-shot (no tool loop) and emits JSON; if parsing fails the UI shows the raw text.
