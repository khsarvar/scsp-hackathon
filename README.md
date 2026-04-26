# HealthLab Agent

A small workspace for exploring public-health datasets. Upload a CSV (or have
it pull one from the CDC / Socrata catalog), and it will profile, clean,
analyze, and produce a Markdown memo with charts.

## Team

- Akbar Khamidov
- Sarvar Khamidov
- Jonathan Bramsen

## Track

Autonomous Labs

## What we built

- A FastAPI backend with three LLM tool-use loops:
  - **Discovery** — search a Socrata catalog and fetch one or more datasets
    via SoQL.
  - **Cleaning** — pick from a fixed `CLEANING_OPS` registry (dedup, null
    fill, IQR cap, type coerce, …).
  - **Code analysis** — run a sandboxed code agent against the cleaned frame
    to produce summary stats, charts, findings, and follow-ups.
- A literature step that queries PubMed and summarizes relevant articles.
- A Next.js workspace UI with step cards, an event/thought stream, a chat
  panel, and Markdown export.

The LLM does not write pandas / scipy / HTTP directly in the discovery and
cleaning loops — it picks named ops from small fixed vocabularies. The code
analysis loop does write Python, scoped to a per-session sandbox.

## Datasets / APIs

- **Socrata Open Data API** — catalog (`/api/catalog/v1`) and SoQL fetch
  (`/resource/{id}.json`) across ~12 portals: `data.cdc.gov`,
  `healthdata.gov`, `data.cityofnewyork.us`, `data.cityofchicago.org`,
  `data.lacity.org`, `data.sfgov.org`, NY/WA/TX state. List in
  `backend/services/discovery.py:SOCRATA_PORTALS`.
- **OpenAI API** — agent loops and one-shot calls (analysis plan, chat).
  Set `OPENAI_API_KEY` in `backend/.env`.
- **PubMed E-utilities** — literature search/summarize.
- **User upload** — any CSV. Demo: `demo_asthma.csv` (CA county ER visits
  2020–2023), `sample_dirty.csv` (messy trial data).

## How to run

```bash
# 1. Configure
cp .env.example backend/.env
# edit backend/.env, set OPENAI_API_KEY

# 2. Backend (FastAPI)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 3. Frontend (Next.js) — in a second terminal
cd frontend
npm install
npm run dev
```

- Backend: <http://localhost:8000> (OpenAPI: `/docs`)
- Frontend: <http://localhost:3000>

## Workspace flow

1. **Source** — discover from a research question, upload a CSV, or pick a
   demo.
2. **Preview** — first 50 rows.
3. **Quality report** — types, missing %, IQR outliers.
4. **Analysis plan** — model-generated 5–7-step plan.
5. **Agentic clean** *(optional)* — event-by-event trace of cleaning ops.
6. **Run analysis** — summary stats, charts, findings, limitations,
   follow-ups, exportable memo.
7. **Literature** *(optional)* — PubMed search and summary.

The right panel is a session-scoped chat (SSE).

## Layout

```
backend/
  main.py                FastAPI app
  models/                schemas + in-memory session store
  routers/               upload, profile, analyze, chat, export,
                         discover, agent_clean, literature, streaming
  services/
    ai_service.py        one-shot LLM calls
    llm_agents.py        Pydantic-AI agents (clean, discover, analyze, code)
    agent.py             sync wrappers around the async loops
    profiler.py          column inference + IQR outliers
    cleaner.py           deterministic clean (dedup → fill → cap)
    analyzer.py          summary stats + chart specs
    tools.py             CLEANING_OPS + STATS_TESTS registries
    discovery.py         Socrata catalog + Workspace + JOIN_OPS

frontend/
  src/app/page.tsx               AppShell (3 columns)
  src/app/api/                   Next.js → FastAPI proxies (incl. SSE)
  src/components/layout/         LeftSidebar, RightPanel
  src/components/workspace/      step cards, ThoughtStream, tabs
  src/hooks/
    useSession.tsx               context + reducer
    useChat.ts                   chat SSE consumer
    useAgentStream.ts            generic agent-event SSE consumer
  src/lib/api.ts                 fetch wrappers
```

The agent loops are async (Pydantic-AI). The SSE bridge in
`backend/routers/streaming.py` runs the sync entry points in a worker thread
and always emits a terminal `result` event so the UI exits its loading state
on success and failure paths.

## Extending

- **Cleaning op** — add a function in `backend/services/tools.py` decorated
  with `@_op("name")`, then add a line to `CLEANING_OPS_DOC`.
- **Stat test** — add a function returning `{test, p_value, interpretation}`
  to `STATS_TESTS` and `STATS_TESTS_DOC`.
- **Discovery / join op** — add `(workspace, **args) -> dict` to
  `DISCOVERY_OPS` / `JOIN_OPS` in `backend/services/discovery.py`, then
  update the matching `_DOC`.

## Notes

- Sessions are in-memory; a backend restart loses state. Uploaded CSVs
  persist to `UPLOAD_DIR` (default `/tmp/healthlab_sessions`); the workspace
  rehydrates on demand.
- Socrata's `$limit` defaults to 1000. The discover loop is prompted to
  request 25,000 rows; cap is 100,000. For larger pulls, filter server-side
  with SoQL `where=`.
- `backend/routers/hypotheses.py` and `backend/routers/stats.py` exist but
  have no UI in the current build; they're reachable via OpenAPI for direct
  exercise.
