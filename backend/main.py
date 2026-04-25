from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import (
    upload, profile, analyze, chat, export,
    discover, agent_clean, hypotheses, stats,
)

app = FastAPI(
    title="HealthLab Agent API",
    description="Autonomous public health data analysis assistant",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Original labloop endpoints
app.include_router(upload.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(analyze.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(export.router, prefix="/api")

# Agentic endpoints (CDC discover, agentic clean, hypotheses, stats tests)
app.include_router(discover.router, prefix="/api")
app.include_router(agent_clean.router, prefix="/api")
app.include_router(hypotheses.router, prefix="/api")
app.include_router(stats.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "HealthLab Agent"}
