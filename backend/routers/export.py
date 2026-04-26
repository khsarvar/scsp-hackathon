from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from models import session as session_store
from services.script_export import build_script
from utils.memo_builder import build_markdown_memo

router = APIRouter()


@router.get("/export/{session_id}")
def export_memo(session_id: str):
    try:
        sess = session_store.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    if not sess.analysis_result:
        raise HTTPException(status_code=400, detail="Run analysis before exporting.")

    result = sess.analysis_result
    profile = sess.profile or {}

    memo = build_markdown_memo(
        filename=sess.filename,
        profile=profile,
        cleaning_steps=result.get("cleaning_steps", []),
        stats=result.get("stats", []),
        chart_specs=result.get("charts", []),
        findings=result.get("findings", ""),
        limitations=result.get("limitations", ""),
        follow_up=result.get("follow_up", ""),
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )

    safe_name = sess.filename.replace(".csv", "").replace(" ", "_")
    return Response(
        content=memo,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="healthlab_memo_{safe_name}.md"'
        },
    )


@router.get("/export/{session_id}/script")
def export_script(session_id: str):
    try:
        sess = session_store.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    if not sess.analysis_result:
        raise HTTPException(status_code=400, detail="Run analysis before exporting a script.")

    script = build_script(sess)
    safe_name = sess.filename.replace(".csv", "").replace(" ", "_")
    return Response(
        content=script,
        media_type="text/x-python",
        headers={
            "Content-Disposition": f'attachment; filename="healthlab_{safe_name}.py"'
        },
    )
