# HealthLab Agent

An autonomous public-health research assistant. Upload a CSV (or have the agent
discover one from CDC / Socrata), and it auto-profiles, cleans, analyzes, and
explains the data — producing charts, tables, a research memo, and
assumption-aware statistical tests with their reasoning streamed live.

## Team

- Akbar Khamidov
- Sarvar Khamidov
- Jonathan Bramsen

## Track

Autonomous Labs

## What we built

A FastAPI + Next.js workspace that wraps four agentic tool-use loops over a
multi-frame `Workspace`:

1. **Discovery** — Socrata catalog search, SoQL fetch, and join/aggregate over
   12+ public-health portals (CDC, HHS, NYC, Chicago, LA, etc.).
2. **Cleaning** — agent picks named ops from `CLEANING_OPS` (dedup, null fill,
   IQR cap, type coerce, …) and self-corrects on failure.
3. **Hypotheses** — single-shot generation of testable hypotheses with test
   types and rationales.
4. **Statistical testing** — agent picks a test from `STATS_TESTS`, validates
   assumptions (Shapiro normality + non-parametric fallback), and explains the
   result.

The LLM never writes pandas / scipy / HTTP. It picks named ops from small fixed
vocabularies and supplies arguments. Each loop accepts an `on_event` callback,
so the same code path serves both synchronous tests and live SSE streaming to
the workspace UI.

## Datasets / APIs

- **Socrata Open Data API** — catalog discovery (`/api/catalog/v1`) and SoQL
  resource fetch (`/resource/{id}.json`) across ~12 approved Socrata portals
  including `data.cdc.gov`, `healthdata.gov`, `data.cityofnewyork.us`,
  `data.cityofchicago.org`, `data.lacity.org`, `data.sfgov.org`, NY/WA/TX state
  portals. See `backend/services/discovery.py:SOCRATA_PORTALS`.
- **OpenAI API** — agent loops (Pydantic-AI), one-shot calls for analysis
  plans / hypotheses / chat. Set `OPENAI_API_KEY` in `backend/.env`.
- **PubMed E-utilities** — literature review agent (`/api/literature`).
- **User upload** — any CSV. Bundled demos: `demo_asthma.csv` (CA county ER
  visits 2020–2023), `sample_dirty.csv` (intentionally messy trial data).

## How to run

### 1. Configure

```bash
cp .env.example backend/.env
# edit backend/.env and set OPENAI_API_KEY
```

### 2. Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Backend at <http://localhost:8000>; OpenAPI docs at
<http://localhost:8000/docs>.

### 3. Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

Frontend at <http://localhost:3000>.

## Workspace flow

1. **Source** — Discover (research question), Upload, or demo.
2. **Preview** — first 50 rows.
3. **Quality report** — auto-detected types, missing %, IQR outliers.
4. **Analysis plan** — the model proposes a tailored 5–7-step plan; click *Run*.
5. **Agentic clean** *(optional)* — live trace of each cleaning decision.
6. **Hypotheses** — 3–5 testable hypotheses; *Run this test* fires a
   deterministic stats test.
7. **Free-form stats** — ask any analytical question; agent picks the test,
   checks assumptions, explains.
8. **Memo + charts** — exportable Markdown.

The right panel is a session-scoped chat agent (SSE).

## Architecture

```
backend/
  main.py                FastAPI app
  models/
    schemas.py           Pydantic request / response shapes
    session.py           in-memory store + Workspace + agent traces
  routers/
    upload.py            POST /api/upload
    profile.py           POST /api/profile
    analyze.py           POST /api/analyze
    chat.py              POST /api/chat (SSE)
    export.py            GET  /api/export/{id}
    discover.py          POST /api/discover (SSE) + /recommend + /select
    agent_clean.py       POST /api/agent_clean (SSE)
    hypotheses.py        POST /api/hypotheses
    stats.py             POST /api/stats/run + /ask (SSE)
    literature.py        POST /api/literature (SSE)
    streaming.py         sync-loop → SSE bridge
  services/
    ai_service.py        one-shot LLM calls
    llm_agents.py        Pydantic-AI agents (clean, discover, analyze, code)
    agent.py             sync entry points wrapping the async loops
    profiler.py          column role inference + IQR outliers
    cleaner.py           deterministic clean (dedup → fill → cap)
    analyzer.py          summary stats + chart specs
    tools.py             CLEANING_OPS + STATS_TESTS registries
    discovery.py         Socrata catalog + Workspace + JOIN_OPS

frontend/
  src/app/page.tsx                  AppShell (3 columns)
  src/app/api/                      Next.js → FastAPI proxies (incl. SSE)
  src/components/layout/            LeftSidebar (sources), RightPanel (chat)
  src/components/workspace/         step cards + ThoughtStream + panels
  src/hooks/
    useSession.tsx                  context + reducer
    useChat.ts                      chat SSE consumer
    useAgentStream.ts               generic agent-event SSE consumer
  src/lib/api.ts                    fetch wrappers
```

The agent loops are async (Pydantic-AI on top of the OpenAI SDK). The SSE
endpoints (`backend/routers/streaming.py`) run them in a worker thread and
bridge events through an `asyncio.Queue`, always emitting a terminal `result`
event so the UI exits its loading state on both success and failure paths.

## Extending

- **Cleaning op** — decorate a function in `backend/services/tools.py` with
  `@_op("name")` and append a line to `CLEANING_OPS_DOC`.
- **Stat test** — add a function returning `{test, p_value, interpretation}`
  to `STATS_TESTS` + `STATS_TESTS_DOC`. The `analyze` tool's enum regenerates
  on import.
- **Discovery / join op** — add `(workspace, **args) -> dict` to
  `DISCOVERY_OPS` / `JOIN_OPS` in `backend/services/discovery.py` and update
  the matching `_DOC`.
- **Agent personality** — edit the system prompts at the top of each agent in
  `backend/services/llm_agents.py`.

## Notes / limits

- Sessions are in-memory; restart loses state. Uploaded CSVs persist to
  `UPLOAD_DIR` (default `/tmp/healthlab_sessions`); the Workspace rehydrates
  from disk on demand.
- Socrata `$limit` default is 1000. The discover loop is prompted to fetch
  25,000 rows; cap 100,000. For larger pulls, filter server-side with
  SoQL `where=`.
- Hypothesis generation is single-shot. On JSON parse failure the UI shows the
  raw text.
