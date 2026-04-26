"""POST /api/literature/search — runs the PubMed literature agent and streams events as SSE.

Mirrors routers/discover.py: a sync `run_sync(emit)` closure that drives the agent
and returns a final dict, bridged to SSE through stream_agent_events.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models import session as session_store
from services.agent import review_literature
from .streaming import stream_agent_events, sse_response


router = APIRouter()


class LiteratureRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class LiteratureResponse(BaseModel):
    session_id: Optional[str]
    question: Optional[str]
    summary: Optional[str]
    articles: list[dict]


@router.post("/literature/search")
async def search_literature(req: LiteratureRequest):
    """Stream a literature review for `question`. If session_id is given, persist the result on the session."""
    sess = None
    if req.session_id:
        try:
            sess = session_store.get_session(req.session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Session not found.")

    def run(emit):
        report, events = review_literature(req.question, on_event=emit)
        if sess is not None:
            sess.literature_question = req.question
            if not sess.research_question:
                sess.research_question = req.question
            sess.literature_events = list(events)
            if report is not None:
                sess.literature_summary = report.summary
                sess.literature_articles = [a.model_dump() for a in report.articles]

        if report is None:
            return {"ok": False, "error": "Literature agent did not return a report."}

        return {
            "ok": True,
            "session_id": req.session_id,
            "question": req.question,
            "summary": report.summary,
            "articles": [a.model_dump() for a in report.articles],
        }

    return sse_response(stream_agent_events(run))


@router.get("/literature/{session_id}", response_model=LiteratureResponse)
def get_literature(session_id: str):
    """Return the most recent literature report saved on the session, if any."""
    try:
        sess = session_store.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    return LiteratureResponse(
        session_id=session_id,
        question=sess.literature_question,
        summary=sess.literature_summary,
        articles=list(sess.literature_articles),
    )
