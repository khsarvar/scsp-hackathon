# HealthLab Agent

> **Turn public health data into reproducible insights.**

An autonomous AI-powered public health research assistant. Upload a CSV (or have
the agent **discover** a CDC dataset for you), and it auto-profiles, cleans,
analyzes, and explains your data — producing charts, tables, a research memo,
and assumption-aware statistical tests with their reasoning shown live.

This is a merge of two earlier branches:

- **`labloop`** — the Next.js + React + Tailwind UI and FastAPI backend skeleton (the polished UX).
- **`akbar/init`** — four agentic Anthropic tool-use loops over a multi-frame `Workspace`: CDC discovery, auto-clean, hypothesis generation, and assumption-aware statistical testing (the depth).

The merge keeps labloop's full upload → profile → plan → analyze → memo flow,
and adds, as additional step cards, the agentic capabilities from akbar/init:
**CDC Discover**, an **Agentic Cleaning** trace, **Testable Hypotheses**, and a
free-form **Statistical Test** panel with a live thought stream.

---

## Quick Start

### 1. Configure

```bash
cp .env.example backend/.env
# edit backend/.env and set ANTHROPIC_API_KEY
```

### 2. Backend (Python FastAPI)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Backend runs at <http://localhost:8000>; OpenAPI docs at <http://localhost:8000/docs>.

### 3. Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at <http://localhost:3000>.

---

## What you can do

Three data sources in the left sidebar:

- **CDC Discover** — type a research question. The discovery agent searches
  `data.cdc.gov`, fetches via SoQL, and (when needed) joins or aggregates
  multiple datasets into a single analysis-ready frame. The thought stream is
  live in the workspace.
- **Upload CSV** — drag-drop any CSV.
- **Demo datasets** — Asthma ER visits (CA counties 2020–2023) or a small
  intentionally-dirty treatment trial CSV.

Once a dataset is loaded, the workspace progresses through:

1. **Dataset Preview** — first 50 rows.
2. **Data Quality Report** — auto-detected types, missing %, IQR outliers.
3. **Proposed Analysis Plan** — Claude proposes a tailored 5–7-step plan; click *Run analysis* to materialise it.
4. **Agentic Cleaning** _(optional)_ — watch the cleaning agent decide each op live.
5. **Testable Hypotheses** — generate 3–5 specific hypotheses with test types and rationales; **Run this test** kicks off a deterministic stats test (with Shapiro normality check + non-parametric fallback).
6. **Statistical Test (free-form)** — ask any analytical question; the agent picks the right test, checks assumptions, and explains the result, all streamed.
7. **Run Analysis** results — cleaning summary, summary stats, charts, findings, limitations, follow-up, exportable Markdown memo.

The **right panel** is the AI chat agent, scoped to the active session and
streaming via SSE.

---

## Architecture

```
backend/
  main.py            FastAPI app — original + agentic routers
  config.py          env / settings
  models/
    schemas.py       request / response Pydantic shapes
    session.py       in-memory session store, now holding a Workspace + agent traces
  routers/
    upload.py        POST /api/upload
    profile.py       POST /api/profile  (uses ai_service.generate_analysis_plan)
    analyze.py       POST /api/analyze  (deterministic clean + charts + findings)
    chat.py          POST /api/chat     (SSE)
    export.py        GET  /api/export/{id}
    discover.py      POST /api/discover (SSE)        ← akbar/init agent
    agent_clean.py   POST /api/agent_clean (SSE)     ← akbar/init agent
    hypotheses.py    POST /api/hypotheses
    stats.py         POST /api/stats/run, POST /api/stats/ask (SSE)
    streaming.py     SSE bridge for sync agent loops
  services/
    ai_service.py    one-shot Claude calls (plan, findings, chat) — labloop
    profiler.py      labloop's column role inference + IQR outliers
    cleaner.py       labloop's deterministic clean (dedup → null fill → IQR cap)
    analyzer.py      summary stats + chart specs — labloop
    tools.py         CLEANING_OPS registry + STATS_TESTS dict — akbar/init
    discovery.py     Socrata catalog + Workspace + JOIN_OPS — akbar/init
    agent.py         four tool-use loops with on_event callback — akbar/init

frontend/
  src/app/page.tsx                 → AppShell (3 columns)
  src/app/api/                     Next.js proxies to FastAPI (incl. SSE)
  src/components/layout/
    LeftSidebar.tsx                CDC Discover, Upload, demos, history
    RightPanel.tsx                 Chat agent
  src/components/workspace/
    WorkspaceArea.tsx              Step-card driver
    ThoughtStream.tsx              Renders agent events
    HypothesesPanel.tsx            Generate + run hypothesis tests
    StatsTestPanel.tsx             Free-form ask → streamed test
    (… plus the original labloop step cards)
  src/hooks/
    useSession.tsx                 Context + reducer (with agent state)
    useChat.ts                     Chat SSE consumer
    useAgentStream.ts              Generic agent-event SSE consumer
  src/lib/
    api.ts                         Fetch wrappers
    constants.ts
```

The agent loops (`backend/services/agent.py`) are deliberately sync — they call
the Anthropic SDK and `requests` directly — and the FastAPI SSE endpoints bridge
them through a thread + asyncio.Queue (`backend/routers/streaming.py`). Each
loop accepts an `on_event(event)` callback so the same code path works for both
synchronous tests (collect events into a list) and live streaming.

## Why this works

The LLM never writes pandas, scipy, or HTTP code. It picks named ops from small
fixed vocabularies (`CLEANING_OPS`, `STATS_TESTS`, `DISCOVERY_OPS`, `JOIN_OPS`)
and supplies arguments. The "agentic" part is the loops: each agent observes
state after every op, decides what to do next, and self-corrects when an op
fails — `{ok: false, error}` returns let the agent recover instead of crashing.

## Tweak guide

- **Add a cleaning op:** decorate a function in `backend/services/tools.py` with
  `@_op("name")` and append a line to `CLEANING_OPS_DOC`.
- **Add a statistical test:** add a function returning a dict with at least
  `test`, `p_value`, `interpretation` to `STATS_TESTS` and `STATS_TESTS_DOC`.
  The `analyze` tool's enum regenerates from `STATS_TESTS` on import.
- **Add a CDC / join op:** add a function `(workspace, **args) -> dict` to
  `DISCOVERY_OPS` or `JOIN_OPS` in `backend/services/discovery.py` and append a
  line to the matching `_DOC`. The discover-loop tool's enum picks it up.
- **Change an agent's personality:** edit the system prompts at the top of each
  section in `backend/services/agent.py`.

## Notes / limits

- Sessions are in-memory only. A backend restart loses session state. Uploaded
  CSVs are persisted to `UPLOAD_DIR` (default `/tmp/healthlab_sessions`) and the
  Workspace is rehydrated from disk on demand.
- Socrata's server-side `$limit` default is 1000. The discover loop is prompted
  to ask for 25,000 rows per fetch; cap is 100,000. For larger pulls, filter
  server-side with SoQL `where=`.
- The hypothesis generator is single-shot (no tool loop) and emits JSON; if
  parsing fails the UI shows the raw text.
