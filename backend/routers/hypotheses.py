"""POST /api/hypotheses — generate testable hypotheses for a session's primary frame."""

from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError
from fastapi import APIRouter, HTTPException

from models import session as session_store
from models.schemas import HypothesesRequest, HypothesesResponse, Hypothesis
from services.agent import generate_hypotheses


router = APIRouter()


@router.post("/hypotheses", response_model=HypothesesResponse)
def hypotheses(req: HypothesesRequest):
    try:
        sess = session_store.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    if not sess.workspace.frames or sess.primary_alias is None:
        candidate = sess.cleaned_path or sess.original_path
        if not candidate or not Path(candidate).exists() or Path(candidate).stat().st_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Session has no dataset to generate hypotheses from.",
            )
        try:
            df = pd.read_csv(candidate)
        except EmptyDataError:
            raise HTTPException(
                status_code=400,
                detail="Session's CSV file is empty. Re-run discovery / upload.",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not read dataset: {e}")
        if len(df) == 0 or len(df.columns) == 0:
            raise HTTPException(status_code=400, detail="Dataset is empty.")
        sess.workspace.add("main", df, {"source": f"upload:{sess.filename}"})
        sess.primary_alias = "main"

    analysis_plan = sess.profile.get("analysis_plan", "") if sess.profile else ""
    raw = generate_hypotheses(sess.workspace, sess.primary_alias, n=req.n, analysis_plan=analysis_plan)
    sess.hypotheses = list(raw)

    return HypothesesResponse(
        session_id=req.session_id,
        hypotheses=[Hypothesis(**h) if isinstance(h, dict) else Hypothesis(question=str(h)) for h in raw],
    )
