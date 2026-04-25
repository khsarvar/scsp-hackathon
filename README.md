# HealthLab Agent

> **Turn public health data into reproducible insights.**

An autonomous AI-powered public health research assistant. Upload a CSV dataset and the agent automatically profiles, cleans, analyzes, and explains the data — producing charts, tables, a research memo, and suggested follow-up experiments.

---

## Quick Start

### 1. Clone & configure

```bash
cp .env.example backend/.env
# Edit backend/.env and add your ANTHROPIC_API_KEY
```

### 2. Backend (Python FastAPI)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Backend runs at http://localhost:8000. API docs at http://localhost:8000/docs

### 3. Generate demo dataset

```bash
python3 scripts/generate_demo_data.py
```

### 4. Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at http://localhost:3000

---

## Features

- **CSV Upload** — drag-drop or click to upload any CSV
- **Auto Profiling** — detects column types, missing values, duplicates, outliers
- **AI Analysis Plan** — Claude proposes a tailored research plan for your data
- **Data Cleaning** — auto-fills nulls, removes duplicates, caps outliers
- **Charts** — auto-generates line charts, bar charts, scatter plots
- **AI Findings** — plain-English narrative of key patterns and correlations
- **Limitations Section** — honest assessment of what can/can't be concluded
- **Follow-up Research** — AI suggests next experiments and hypotheses
- **Export Memo** — download full research memo as Markdown
- **AI Chat** — ask follow-up questions about your dataset

## Demo Dataset

The demo dataset (`backend/data/demo_asthma.csv`) covers:
- 322 rows of asthma ER visit data
- 5 California counties (Riverside, Los Angeles, Fresno, San Diego, Kern)
- Quarterly data from 2020–2023, 4 age groups
- Correlated features: AQI, poverty rate, uninsured rate
- Realistic missing values and a wildfire outlier (Kern 2022-Q3, AQI=310)

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Charts | Recharts |
| Backend | Python FastAPI |
| Data processing | pandas, numpy, scipy |
| AI | Anthropic Claude (`claude-sonnet-4-6`) |

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/upload` | POST | Upload CSV file |
| `/api/profile` | POST | Profile dataset + generate AI plan |
| `/api/analyze` | POST | Clean data + run analysis + AI findings |
| `/api/chat` | POST | Streaming AI chat (SSE) |
| `/api/export/{id}` | GET | Download research memo as Markdown |

---

*Built for the "Autonomous Laboratories" hackathon challenge.*
