import pandas as pd
from fastapi import APIRouter, HTTPException

from models.schemas import AnalyzeRequest
from models import session as session_store
from services.cleaner import clean_dataframe
from services.analyzer import compute_summary_stats, build_chart_specs
from services.ai_service import build_dataset_context, generate_findings
from utils.file_utils import get_cleaned_path

router = APIRouter()


@router.post("/analyze")
def run_analysis(req: AnalyzeRequest):
    try:
        sess = session_store.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    if not sess.profile:
        raise HTTPException(status_code=400, detail="Run /profile before /analyze.")

    try:
        df = pd.read_csv(sess.original_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read dataset: {e}")

    # Clean
    cleaned_df, cleaning_steps = clean_dataframe(df, sess.profile)

    # Save cleaned CSV
    cleaned_path = get_cleaned_path(req.session_id)
    cleaned_df.to_csv(cleaned_path, index=False)
    session_store.update_session(req.session_id, cleaned_path=str(cleaned_path))

    # Compute stats
    stats = compute_summary_stats(cleaned_df)

    # Build chart specs
    charts = build_chart_specs(cleaned_df, sess.profile)

    # Generate AI findings
    sample_rows = sess.preview_rows[:5]
    dataset_context = build_dataset_context(sess.profile, stats, sample_rows)
    try:
        ai_result = generate_findings(dataset_context, charts, stats, cleaning_steps)
    except Exception as e:
        ai_result = {
            "findings": f"_AI findings could not be generated: {e}_",
            "limitations": "• Could not generate limitations automatically.",
            "follow_up": "1. Review the data manually for insights.",
        }

    result = {
        "session_id": req.session_id,
        "cleaning_steps": cleaning_steps,
        "stats": stats,
        "charts": charts,
        "findings": ai_result["findings"],
        "limitations": ai_result["limitations"],
        "follow_up": ai_result["follow_up"],
    }
    session_store.update_session(req.session_id, analysis_result=result)

    return result
