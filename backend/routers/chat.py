import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from models.schemas import ChatRequest
from models import session as session_store
from services.ai_service import build_dataset_context, stream_chat_response

router = APIRouter()


async def _sse_generator(message: str, dataset_context: str, history: list[dict]):
    try:
        async for token in stream_chat_response(message, dataset_context, history):
            data = json.dumps({"delta": token})
            yield f"data: {data}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat(req: ChatRequest):
    try:
        sess = session_store.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Build dataset context from stored profile/analysis
    profile = sess.profile or {}
    stats = []
    if sess.analysis_result:
        stats = sess.analysis_result.get("stats", [])
    sample_rows = sess.preview_rows[:5]
    workspace_summary = sess.workspace.summary() if sess.workspace else None
    dataset_context = build_dataset_context(
        profile,
        stats,
        sample_rows,
        research_question=sess.research_question,
        analysis_result=sess.analysis_result,
        hypotheses=sess.hypotheses or None,
        test_history=sess.test_history or None,
        workspace_summary=workspace_summary,
        literature_question=sess.literature_question,
        literature_summary=sess.literature_summary,
    ) if profile else ""

    # Use history sent by the frontend (correctly includes prior assistant responses).
    # Fall back to server-side history if the client sent nothing.
    if req.history:
        history_for_llm = [{"role": m.role, "content": m.content} for m in req.history]
    else:
        history_for_llm = sess.chat_history

    # Persist user turn server-side (used as fallback and for export/recovery).
    new_history = sess.chat_history + [{"role": "user", "content": req.message}]
    session_store.update_session(req.session_id, chat_history=new_history)

    return StreamingResponse(
        _sse_generator(req.message, dataset_context, history_for_llm),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
