"""POST /api/agent_clean — runs the agentic auto_clean loop and streams events as SSE.

Optional alternative to /analyze's deterministic clean step. Lets the user watch the
agent decide which cleaning op to apply at each step, and persists the cleaned df
back into the session's workspace for downstream analysis.
"""

from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError
from fastapi import APIRouter, HTTPException

from models import session as session_store
from models.schemas import AnalyzeRequest
from services.agent import auto_clean
from utils.file_utils import get_cleaned_path
from .streaming import stream_agent_events, sse_response


router = APIRouter()


@router.post("/agent_clean")
async def agent_clean(req: AnalyzeRequest):
    try:
        sess = session_store.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Make sure the workspace has a frame (e.g. recovered after restart from disk).
    if not sess.workspace.frames or sess.primary_alias is None:
        path = Path(sess.original_path) if sess.original_path else None
        if not path or not path.exists() or path.stat().st_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Session has no dataset to clean (empty or missing CSV).",
            )
        try:
            df = pd.read_csv(path)
        except EmptyDataError:
            raise HTTPException(
                status_code=400,
                detail="Session's CSV file is empty. Re-run discovery / upload.",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not read dataset: {e}")
        if len(df) == 0 or len(df.columns) == 0:
            raise HTTPException(status_code=400, detail="Dataset has no data to clean.")
        sess.workspace.add("main", df, {"source": f"upload:{sess.filename}"})
        sess.primary_alias = "main"

    alias = sess.primary_alias

    def run(emit):
        events = auto_clean(sess.workspace, alias, on_event=emit)
        sess.clean_events = list(events)
        cleaned_df = sess.workspace.frames[alias]
        cleaned_path = get_cleaned_path(req.session_id)
        cleaned_df.to_csv(cleaned_path, index=False)
        sess.cleaned_path = str(cleaned_path)
        return {
            "ok": True,
            "session_id": req.session_id,
            "alias": alias,
            "row_count": int(len(cleaned_df)),
            "col_count": int(len(cleaned_df.columns)),
            "n_events": len(events),
        }

    return sse_response(stream_agent_events(run))
