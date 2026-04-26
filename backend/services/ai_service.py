"""Single-shot LLM helpers + streaming chat — all backed by Pydantic AI agents.

Provider selection happens in services.llm_agents via the configured
`provider:model` strings; this module just wires the prompts and message
history into those agents.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from services.llm_agents import (
    chat_agent_with_context,
    findings_run,
    plan_run,
    plan_refine_run,
)


def build_dataset_context(
    profile: dict[str, Any],
    stats: list[dict[str, Any]],
    sample_rows: list[dict[str, Any]],
) -> str:
    """Build a compact dataset context string (~2000 tokens max)."""
    lines = []
    lines.append("<dataset_context>")
    lines.append(f"Shape: {profile['row_count']} rows × {profile['col_count']} columns")
    lines.append(f"Duplicate rows: {profile['duplicate_rows']}")
    lines.append("")

    lines.append("COLUMNS:")
    lines.append("| Name | Type | Missing% | Unique |")
    lines.append("|------|------|----------|--------|")
    for col in profile["columns"]:
        lines.append(
            f"| {col['name']} | {col['dtype_inferred']} | {col['missing_pct']}% | {col['unique_count']} |"
        )

    if stats:
        lines.append("")
        lines.append("SUMMARY STATISTICS (numeric columns):")
        lines.append("| Column | Count | Mean | Median | Std | Min | Max |")
        lines.append("|--------|-------|------|--------|-----|-----|-----|")
        for s in stats[:10]:
            lines.append(
                f"| {s['column']} | {s['count']} | {s['mean']} | {s['median']} | {s['std']} | {s['min']} | {s['max']} |"
            )

    outlier_cols = [c for c in profile["columns"] if c.get("outliers")]
    if outlier_cols:
        lines.append("")
        lines.append("OUTLIERS DETECTED (IQR method, 3×IQR fence):")
        for col in outlier_cols:
            for o in col["outliers"][:3]:
                lines.append(f"- {col['name']}: row {o['row_index']}, value={o['value']}")

    if sample_rows:
        lines.append("")
        lines.append("SAMPLE DATA (first 5 rows):")
        if sample_rows:
            headers = list(sample_rows[0].keys())
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in sample_rows[:5]:
                lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")

    lines.append("</dataset_context>")
    return "\n".join(lines)


def generate_analysis_plan(dataset_context: str, research_question: str = "") -> str:
    """Ask the model to propose a numbered analysis plan."""
    import asyncio
    return asyncio.run(plan_run(dataset_context, research_question=research_question))


def refine_analysis_plan(current_plan: str, instruction: str) -> str:
    """Ask the model to revise an existing plan based on a user instruction."""
    import asyncio
    return asyncio.run(plan_refine_run(current_plan, instruction))


def generate_findings(
    dataset_context: str,
    chart_specs: list[dict[str, Any]],
    stats: list[dict[str, Any]],
    cleaning_steps: list[str],
    analysis_plan: str = "",
) -> dict[str, str]:
    """Generate findings, limitations, and follow-up questions."""
    import asyncio
    try:
        report = asyncio.run(findings_run(dataset_context, chart_specs, stats,
                                          cleaning_steps, analysis_plan=analysis_plan))
        return {
            "findings": report.findings,
            "limitations": report.limitations,
            "follow_up": report.follow_up,
        }
    except Exception as e:
        return {
            "findings": f"Could not produce findings: {e}",
            "limitations": "• Analysis limitations could not be generated.",
            "follow_up": "1. Review the raw data for additional patterns.",
        }


def _history_to_model_messages(history: list[dict[str, str]]) -> list:
    """Convert simple [{role, content}] dicts into Pydantic AI message objects."""
    msgs = []
    for m in history:
        role = m.get("role")
        content = m.get("content", "")
        if role == "user":
            msgs.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == "assistant":
            msgs.append(ModelResponse(parts=[TextPart(content=content)]))
    return msgs


async def stream_chat_response(
    message: str,
    dataset_context: str,
    chat_history: list[dict[str, str]],
) -> AsyncIterator[str]:
    """Stream chat response tokens from the configured provider."""
    agent = chat_agent_with_context(dataset_context)
    history = _history_to_model_messages(chat_history[-20:])
    async with agent.run_stream(message, message_history=history) as response:
        async for chunk in response.stream_text(delta=True):
            yield chunk
