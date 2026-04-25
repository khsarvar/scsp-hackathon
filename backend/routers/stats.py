"""POST /api/stats/run — run a single statistical test (no LLM).
POST /api/stats/ask — ask a free-form question; the agent picks a test and explains. (SSE)
"""

from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError
from fastapi import APIRouter, HTTPException

from models import session as session_store
from models.schemas import RunTestRequest, RunTestResponse, AskRequest
from services.agent import analyze_question, run_stats_test
from .streaming import stream_agent_events, sse_response


router = APIRouter()


def _ensure_workspace(sess) -> None:
    if sess.workspace.frames and sess.primary_alias in sess.workspace.frames:
        return
    candidate = sess.cleaned_path or sess.original_path
    if not candidate or not Path(candidate).exists() or Path(candidate).stat().st_size == 0:
        raise HTTPException(
            status_code=400,
            detail="Session has no dataset to operate on (empty or missing CSV on disk).",
        )
    try:
        df = pd.read_csv(candidate)
    except EmptyDataError:
        raise HTTPException(
            status_code=400,
            detail="Session's CSV file is empty (no header or rows). Re-run discovery / upload.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read dataset: {e}")
    if len(df) == 0 or len(df.columns) == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Session dataset is empty ({len(df)} rows × {len(df.columns)} cols).",
        )
    sess.workspace.add("main", df, {"source": f"upload:{sess.filename}"})
    sess.primary_alias = "main"


@router.post("/stats/run", response_model=RunTestResponse)
def stats_run(req: RunTestRequest):
    try:
        sess = session_store.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    _ensure_workspace(sess)
    result = run_stats_test(sess.workspace, sess.primary_alias, req.test, req.args)
    sess.test_history.append({"test": req.test, "args": req.args, "result": result})
    return RunTestResponse(
        session_id=req.session_id,
        test=req.test,
        args=req.args,
        result=result,
    )


@router.post("/stats/ask")
async def stats_ask(req: AskRequest):
    try:
        sess = session_store.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    _ensure_workspace(sess)
    alias = sess.primary_alias

    def run(emit):
        answer, events = analyze_question(req.question, sess.workspace, alias, on_event=emit)
        sess.analyze_events = list(events)
        return {
            "ok": True,
            "session_id": req.session_id,
            "alias": alias,
            "question": req.question,
            "answer": answer,
        }

    return sse_response(stream_agent_events(run))
