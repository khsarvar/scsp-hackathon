import io
from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError
from fastapi import APIRouter, HTTPException

from models.schemas import ProfileRequest
from models import session as session_store
from services.profiler import profile_dataframe
from services.ai_service import build_dataset_context, generate_analysis_plan

router = APIRouter()


@router.post("/profile")
def profile_dataset(req: ProfileRequest):
    try:
        sess = session_store.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Prefer the in-memory workspace frame if it's there (e.g. fresh from /discover);
    # fall back to reading the CSV from disk for sessions recovered after a restart.
    df = None
    if sess.workspace.frames and sess.primary_alias in sess.workspace.frames:
        df = sess.workspace.frames[sess.primary_alias]

    if df is None or len(df) == 0:
        path = Path(sess.original_path) if sess.original_path else None
        if not path or not path.exists() or path.stat().st_size == 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "This session has no data to profile. The dataset is empty — most likely "
                    "the discovery agent's SoQL filter excluded every row, or the upload was "
                    "blank. Try rephrasing your research question with a broader scope."
                ),
            )
        try:
            df = pd.read_csv(path)
        except EmptyDataError:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Dataset file has no parseable rows. The most common cause is a SoQL "
                    "`where` filter that excluded every row during CDC discovery."
                ),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not read dataset: {e}")

    if len(df) == 0 or len(df.columns) == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Dataset is empty ({len(df)} rows × {len(df.columns)} cols). Nothing to profile.",
        )

    profile = profile_dataframe(df)
    session_store.update_session(req.session_id, profile=profile)

    # Build lightweight stats for context (no cleaning yet — use raw stats)
    stats = []
    for col in profile["columns"]:
        if col["dtype_inferred"] == "numeric" and col["mean"] is not None:
            stats.append({
                "column": col["name"],
                "count": profile["row_count"] - col["missing_count"],
                "mean": col["mean"],
                "median": col["mean"],  # approx before cleaning
                "std": col["std"],
                "min": col["min"],
                "max": col["max"],
                "p25": None,
                "p75": None,
            })

    sample_rows = sess.preview_rows[:5]
    dataset_context = build_dataset_context(profile, stats, sample_rows)

    # Generate AI analysis plan
    try:
        analysis_plan = generate_analysis_plan(dataset_context, research_question=sess.research_question or "")
    except Exception as e:
        analysis_plan = f"_Analysis plan could not be generated: {e}_"

    session_store.update_session(req.session_id, profile={**profile, "analysis_plan": analysis_plan})

    return {
        "session_id": req.session_id,
        "row_count": profile["row_count"],
        "col_count": profile["col_count"],
        "duplicate_rows": profile["duplicate_rows"],
        "columns": profile["columns"],
        "analysis_plan": analysis_plan,
    }
