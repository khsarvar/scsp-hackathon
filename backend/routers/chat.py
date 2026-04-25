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
    dataset_context = build_dataset_context(profile, stats, sample_rows) if profile else ""

    # Update chat history
    new_history = sess.chat_history + [{"role": "user", "content": req.message}]
    session_store.update_session(req.session_id, chat_history=new_history)

    return StreamingResponse(
        _sse_generator(req.message, dataset_context, sess.chat_history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
