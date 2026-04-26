from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import uuid

from services.discovery import Workspace


@dataclass
class SessionData:
    session_id: str
    filename: str
    original_path: str
    cleaned_path: Optional[str] = None
    preview_rows: list[dict[str, Any]] = field(default_factory=list)
    profile: Optional[dict[str, Any]] = None
    analysis_result: Optional[dict[str, Any]] = None
    chat_history: list[dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    # akbar/init upgrades: multi-frame workspace, agent thought streams, hypotheses
    workspace: Workspace = field(default_factory=Workspace)
    primary_alias: Optional[str] = None
    research_question: Optional[str] = None  # what the user originally asked (CDC discover / literature input)
    discover_events: list[dict[str, Any]] = field(default_factory=list)
    clean_events: list[dict[str, Any]] = field(default_factory=list)
    analyze_events: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    test_history: list[dict[str, Any]] = field(default_factory=list)

    # HITL: set to True after discover when ≥2 frames exist; cleared after /discover/select
    pending_join: bool = False

    # Literature review (PubMed) — last completed report for this session
    literature_question: Optional[str] = None
    literature_summary: Optional[str] = None
    literature_articles: list[dict[str, Any]] = field(default_factory=list)
    literature_events: list[dict[str, Any]] = field(default_factory=list)


# In-memory store — fine for hackathon MVP
_sessions: dict[str, SessionData] = {}


def create_session(filename: str, original_path: str) -> SessionData:
    session_id = str(uuid.uuid4())
    session = SessionData(
        session_id=session_id,
        filename=filename,
        original_path=original_path,
    )
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> SessionData:
    session = _sessions.get(session_id)
    if session is None:
        raise KeyError(f"Session '{session_id}' not found")
    return session


def update_session(session_id: str, **kwargs) -> None:
    session = get_session(session_id)
    for key, value in kwargs.items():
        setattr(session, key, value)


def list_sessions() -> list[SessionData]:
    return sorted(_sessions.values(), key=lambda s: s.created_at, reverse=True)
