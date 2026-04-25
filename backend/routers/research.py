from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from providers.registry import complete_text
from research import service
from routers.streaming import stream_agent_events, sse_response

router = APIRouter()


class RunCreate(BaseModel):
    question: str
    provider: str
    model: str


class PinRequest(BaseModel):
    dataset_id: str
    title: str | None = None


class ChatRequest(BaseModel):
    thread_id: str
    message: str


class PythonRequest(BaseModel):
    code: str


@router.get("/research/providers")
def providers():
    return {"providers": service.list_providers()}


@router.post("/research/runs")
def create_run(req: RunCreate):
    try:
        return service.create_run(req.question, req.provider, req.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/research/runs/stream")
async def create_run_stream(req: RunCreate):
    def run(emit):
        emit({"type": "thought", "agent": "orchestrator", "text": "Creating research run and launching previous Socrata discovery agent."})
        emit({"type": "thought", "agent": "provider", "text": f"Selected provider/model for downstream chat and reporting: {req.provider} / {req.model}."})
        bundle = service.create_run_agentic(req.question, req.provider, req.model, on_event=emit)
        emit({"type": "final", "agent": "orchestrator", "summary": f"Discovery persisted {len(bundle.get('pinned_datasets', []))} agent-selected dataset(s)."})
        return bundle

    return sse_response(stream_agent_events(run))


@router.get("/research/runs/{run_id}")
def get_run(run_id: str):
    try:
        return service.get_run_bundle(run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/research/runs/{run_id}/datasets")
def pin_dataset(run_id: str, req: PinRequest):
    try:
        return service.pin_dataset(run_id, req.dataset_id, req.title)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/research/runs/{run_id}/joins/propose")
def propose_joins(run_id: str):
    try:
        return service.propose_joins(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/research/runs/{run_id}/joins/propose/stream")
async def propose_joins_stream(run_id: str):
    def run(emit):
        emit({"type": "thought", "agent": "join_agent", "text": "Inspecting pinned datasets and proposing approved-only join plans."})
        bundle = service.propose_joins(run_id)
        emit({"type": "final", "agent": "join_agent", "summary": f"Prepared {len(bundle.get('join_plans', []))} join plan(s)."})
        return bundle

    return sse_response(stream_agent_events(run))


@router.post("/research/runs/{run_id}/joins/{join_plan_id}/apply")
def apply_join(run_id: str, join_plan_id: int):
    try:
        return service.apply_join(run_id, join_plan_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/research/runs/{run_id}/joins/{join_plan_id}/apply/stream")
async def apply_join_stream(run_id: str, join_plan_id: int):
    def run(emit):
        emit({"type": "tool_call", "agent": "join_agent", "name": "apply_join", "args": {"join_plan_id": join_plan_id}, "rationale": "User approved the join plan."})
        bundle = service.apply_join(run_id, join_plan_id)
        latest = bundle.get("join_results", [])[-1:] or [{}]
        emit({"type": "tool_result", "agent": "join_agent", "name": "apply_join", "summary": latest[0].get("explanation", "Join applied."), "result": latest[0]})
        emit({"type": "final", "agent": "join_agent", "summary": "Join execution completed and methodology log was updated."})
        return bundle

    return sse_response(stream_agent_events(run))


@router.post("/research/runs/{run_id}/methodology")
def methodology(run_id: str):
    try:
        return service.run_methodology(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/research/runs/{run_id}/methodology/stream")
async def methodology_stream(run_id: str):
    def run(emit):
        emit({"type": "thought", "agent": "methodology_agent", "text": "Launching cleaning, hypothesis, analysis, and statistical methodology agents."})
        bundle = service.run_methodology(run_id, on_event=emit)
        emit({"type": "final", "agent": "methodology_agent", "summary": f"Methodology complete with {len(bundle.get('statistical_results', []))} stored statistical result(s)."})
        return bundle

    return sse_response(stream_agent_events(run))


@router.post("/research/runs/{run_id}/execute-python")
def execute_python(run_id: str, req: PythonRequest):
    try:
        return service.run_unsafe_python(run_id, req.code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/research/runs/{run_id}/execute-python/stream")
async def execute_python_stream(run_id: str, req: PythonRequest):
    def run(emit):
        emit({"type": "tool_call", "agent": "unsafe_python_agent", "name": "execute_python", "args": {"chars": len(req.code)}, "rationale": "User requested unsafe Python execution."})
        bundle = service.run_unsafe_python(run_id, req.code)
        result = bundle.get("unsafe_python_result", {})
        emit({"type": "tool_result", "agent": "unsafe_python_agent", "name": "execute_python", "summary": "Unsafe Python finished." if result.get("ok") else str(result.get("error")), "result": result})
        emit({"type": "final", "agent": "unsafe_python_agent", "summary": "Unsafe Python execution was logged."})
        return bundle

    return sse_response(stream_agent_events(run))


@router.post("/research/runs/{run_id}/report")
def report(run_id: str):
    try:
        return service.generate_report(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/research/runs/{run_id}/report/stream")
async def report_stream(run_id: str):
    def run(emit):
        emit({"type": "thought", "agent": "report_agent", "text": "Reading SQLite actions, datasets, joins, literature, and statistical results."})
        bundle = service.generate_report(run_id)
        emit({"type": "final", "agent": "report_agent", "summary": f"Generated report with {len(bundle.get('report_markdown', ''))} markdown characters."})
        return bundle

    return sse_response(stream_agent_events(run))


@router.get("/research/runs/{run_id}/report.md")
def download_report(run_id: str):
    try:
        bundle = service.get_run_bundle(run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    markdown = bundle.get("report_markdown") or service.generate_report(run_id)["report_markdown"]
    return Response(
        markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="healthlab-report.md"'},
    )


@router.post("/research/runs/{run_id}/chat/new")
def new_chat(run_id: str):
    return service.create_thread(run_id, "Research chat")


@router.post("/research/chat")
async def chat(req: ChatRequest):
    thread_rows = service.rows("SELECT * FROM chat_threads WHERE id=?", (req.thread_id,)) if hasattr(service, "rows") else []
    # Avoid coupling the public service namespace to DB helpers; look up through bundle fallback below.
    service.save_chat_message(req.thread_id, "user", req.message)

    async def gen():
        try:
            # Find run/provider for the thread.
            from db.database import row, rows

            thread = row("SELECT * FROM chat_threads WHERE id=?", (req.thread_id,))
            if not thread:
                yield f"data: {json.dumps({'error': 'Thread not found'})}\n\n"
                return
            run = row("SELECT * FROM research_runs WHERE id=?", (thread["run_id"],))
            messages = rows("SELECT role, content FROM chat_messages WHERE thread_id=? ORDER BY id DESC LIMIT 12", (req.thread_id,))
            context = service.get_run_bundle(thread["run_id"])
            prompt = (
                f"Research question: {run['question']}\n"
                f"Recent messages: {list(reversed(messages))}\n"
                f"Statistical results: {context['statistical_results']}\n"
                f"Join results: {context['join_results']}\n\n"
                f"Answer only the newest user message: {req.message}"
            )
            text = complete_text(
                run["provider"],
                run["model"],
                "You are HealthLab's research assistant. Be concise, cite logged results, and do not output the whole chat history.",
                prompt,
            )
            service.save_chat_message(req.thread_id, "assistant", text)
            yield f"data: {json.dumps({'delta': text})}\n\n"
        except Exception as e:
            fallback = f"I could not call the selected AI provider: {e}"
            service.save_chat_message(req.thread_id, "assistant", fallback)
            yield f"data: {json.dumps({'delta': fallback})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
