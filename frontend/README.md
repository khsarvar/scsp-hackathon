# frontend

Next.js workspace UI for HealthLab Agent. See the [root README](../README.md)
for project overview, datasets/APIs, and how to run the full stack.

## Dev

```bash
npm install
npm run dev
```

App at <http://localhost:3000>. Expects the FastAPI backend on
<http://localhost:8000>; override with `BACKEND_URL` in `.env.local` if
running it elsewhere.

## Layout

- `src/app/page.tsx` — AppShell (3-column workspace).
- `src/app/api/*` — Next.js route handlers proxying to the FastAPI backend
  (including SSE endpoints).
- `src/components/layout/` — left sidebar (sources) and right panel (chat).
- `src/components/workspace/` — step cards, agent thought stream, tabs.
- `src/hooks/` — session reducer, SSE consumers.
- `src/lib/api.ts` — typed fetch wrappers.
