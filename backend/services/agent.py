"""Sync wrappers around the Pydantic AI agents in services.llm_agents.

Routers call these from within `run_in_threadpool`, so each invocation gets its
own event loop via `asyncio.run`. The agent loops, tool registration, and
provider selection all live in services.llm_agents — this file just preserves
the public sync surface (function signatures and return shapes) the routers
have always depended on.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Optional

from services.discovery import Workspace
from services.tools import STATS_TESTS
from services.llm_agents import (
    Hypothesis,
    analyze_run,
    clean_run,
    discover_run,
    hypotheses_run,
)


EventCallback = Optional[Callable[[dict], None]]


def _emit(events: list, on_event: EventCallback, event: dict) -> None:
    events.append(event)
    if on_event is not None:
        try:
            on_event(event)
        except Exception:
            pass


def _make_emitter(events: list, on_event: EventCallback) -> Callable[[dict], None]:
    def emit(event: dict) -> None:
        _emit(events, on_event, event)
    return emit


def discover(
    question: str,
    workspace: Optional[Workspace] = None,
    max_steps: int = 15,
    on_event: EventCallback = None,
) -> tuple[Workspace, Optional[str], list]:
    """Run the discovery agent. Returns (workspace, primary_alias, events)."""
    workspace = workspace or Workspace()
    events: list = []
    emit = _make_emitter(events, on_event)
    result = asyncio.run(discover_run(question, workspace, emit, max_steps=max_steps))
    primary_alias: Optional[str]
    if result is not None and result.primary_alias:
        primary_alias = result.primary_alias
    elif workspace.frames:
        primary_alias = next(iter(workspace.frames))
    else:
        primary_alias = None
    return workspace, primary_alias, events


def auto_clean(
    workspace: Workspace,
    alias: str,
    max_steps: int = 12,
    on_event: EventCallback = None,
) -> list:
    """Run the cleaning agent on workspace[alias]. Mutates workspace in place. Returns events."""
    events: list = []
    emit = _make_emitter(events, on_event)
    asyncio.run(clean_run(workspace, alias, emit, max_steps=max_steps))
    return events


def generate_hypotheses(workspace: Workspace, alias: str, n: int = 4) -> list[dict]:
    try:
        result: list[Hypothesis] = asyncio.run(hypotheses_run(workspace, alias, n=n))
    except Exception as e:
        return [{"question": "Failed to generate hypotheses", "rationale": str(e)}]
    return [h.model_dump() for h in result]


def analyze_question(
    question: str,
    workspace: Workspace,
    alias: str,
    max_steps: int = 5,
    on_event: EventCallback = None,
) -> tuple[str, list]:
    """Run the analysis agent on workspace[alias]. Returns (answer_text, events)."""
    events: list = []
    emit = _make_emitter(events, on_event)
    answer = asyncio.run(analyze_run(question, workspace, alias, emit, max_steps=max_steps))
    return answer, events


def run_stats_test(workspace: Workspace, alias: str, test: str, args: dict) -> dict:
    """Run a named STATS_TESTS function directly on workspace[alias]. No LLM."""
    df = workspace.get(alias)
    fn = STATS_TESTS.get(test)
    if fn is None:
        return {"error": f"unknown test '{test}'"}
    try:
        return fn(df, **args)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
