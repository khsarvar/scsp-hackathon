"""PUT /api/plan — save a user-edited analysis plan.
POST /api/plan/refine — ask the AI to revise the plan based on a user instruction.
"""

from fastapi import APIRouter, HTTPException

from models.schemas import UpdatePlanRequest, RefinePlanRequest
from models import session as session_store
from services.ai_service import refine_analysis_plan

router = APIRouter()


@router.put("/plan")
def update_plan(req: UpdatePlanRequest):
    """Overwrite the stored analysis plan with user-edited text."""
    try:
        sess = session_store.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    if not sess.profile:
        raise HTTPException(status_code=400, detail="Run /profile before editing the plan.")

    updated_profile = {**sess.profile, "analysis_plan": req.plan}
    session_store.update_session(req.session_id, profile=updated_profile)
    return {"session_id": req.session_id, "analysis_plan": req.plan}


@router.post("/plan/refine")
def refine_plan(req: RefinePlanRequest):
    """Use the AI to revise the current analysis plan per the user's instruction."""
    try:
        sess = session_store.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    if not sess.profile:
        raise HTTPException(status_code=400, detail="Run /profile before refining the plan.")

    current_plan = sess.profile.get("analysis_plan", "")
    if not current_plan:
        raise HTTPException(status_code=400, detail="No analysis plan found to refine.")

    try:
        revised_plan = refine_analysis_plan(current_plan, req.instruction)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI refinement failed: {e}")

    updated_profile = {**sess.profile, "analysis_plan": revised_plan}
    session_store.update_session(req.session_id, profile=updated_profile)
    return {"session_id": req.session_id, "analysis_plan": revised_plan}
