"""Helpers to expose sync agent loops as SSE streams.

The agent loops in services/agent.py are sync (Anthropic SDK + `requests`).
We run each loop in a threadpool and bridge events through an asyncio.Queue
into a Server-Sent Events response.
"""

import asyncio
import json
from typing import AsyncIterator, Callable

from fastapi.responses import StreamingResponse


SENTINEL_DONE = {"type": "_done"}


async def stream_agent_events(run_sync: Callable[[Callable[[dict], None]], dict | None]) -> AsyncIterator[str]:
    """Bridge a sync agent loop into an SSE byte stream.

    `run_sync(emit)` should run the agent loop (in this thread) and call `emit(event)`
    for every event the agent produces. The bridge always emits a final 'result' event
    before the stream ends — synthesizing an `{ok: false, error}` payload if run_sync
    raises or returns a non-dict — so the frontend always exits its loading state.
    """
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def emit(event: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    async def _run():
        try:
            result = await asyncio.to_thread(run_sync, emit)
            if isinstance(result, dict):
                queue.put_nowait({"type": "result", "data": result})
            else:
                queue.put_nowait({"type": "result", "data": {"ok": False, "error": "Agent did not return a result."}})
        except Exception as e:
            queue.put_nowait({"type": "result", "data": {"ok": False, "error": f"{type(e).__name__}: {e}"}})
        finally:
            queue.put_nowait(SENTINEL_DONE)

    task = asyncio.create_task(_run())

    try:
        while True:
            event = await queue.get()
            if event is SENTINEL_DONE:
                yield "data: [DONE]\n\n"
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"
    finally:
        if not task.done():
            await task


def sse_response(generator: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
