import json
from typing import Any, AsyncIterator

import anthropic

from config import settings

SYSTEM_PROMPT = """You are HealthLab Agent, an autonomous public health research assistant. Your role is to inspect public health datasets, clean them, run exploratory analysis, generate charts and tables, explain findings in plain English, and suggest follow-up research questions or experiments.

Always be careful with public health claims. Do not provide medical advice. Do not claim causation from observational data unless the study design supports it. Always mention missing data, limitations, uncertainty, and possible confounders. Prefer simple, interpretable analysis first. Make your work reproducible by explaining cleaning steps and analysis methods.

When responding:
- Be concise and precise
- Use plain English accessible to non-statisticians
- Clearly distinguish between correlation and causation
- Always mention data quality limitations
- Suggest specific, actionable follow-up research questions
- Format responses in clean markdown when appropriate"""


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _get_async_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


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

    # Column inventory table
    lines.append("COLUMNS:")
    lines.append("| Name | Type | Missing% | Unique |")
    lines.append("|------|------|----------|--------|")
    for col in profile["columns"]:
        lines.append(
            f"| {col['name']} | {col['dtype_inferred']} | {col['missing_pct']}% | {col['unique_count']} |"
        )

    # Summary stats
    if stats:
        lines.append("")
        lines.append("SUMMARY STATISTICS (numeric columns):")
        lines.append("| Column | Count | Mean | Median | Std | Min | Max |")
        lines.append("|--------|-------|------|--------|-----|-----|-----|")
        for s in stats[:10]:
            lines.append(
                f"| {s['column']} | {s['count']} | {s['mean']} | {s['median']} | {s['std']} | {s['min']} | {s['max']} |"
            )

    # Outlier summary
    outlier_cols = [
        c for c in profile["columns"] if c.get("outliers")
    ]
    if outlier_cols:
        lines.append("")
        lines.append("OUTLIERS DETECTED (IQR method, 3×IQR fence):")
        for col in outlier_cols:
            for o in col["outliers"][:3]:
                lines.append(f"- {col['name']}: row {o['row_index']}, value={o['value']}")

    # Sample rows
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


def generate_analysis_plan(dataset_context: str) -> str:
    """Ask Claude to propose a numbered analysis plan."""
    client = _get_client()

    response = client.messages.create(
        model=settings.model_name,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"""{dataset_context}

Based on this public health dataset, please propose a concise analysis plan with 5-7 numbered steps. For each step, briefly explain what will be done and why it matters for public health research. Focus on exploratory analysis appropriate for this dataset's structure. Keep the plan actionable and specific to the columns present.""",
            }
        ],
    )
    return response.content[0].text


def generate_findings(
    dataset_context: str,
    chart_specs: list[dict[str, Any]],
    stats: list[dict[str, Any]],
    cleaning_steps: list[str],
) -> dict[str, str]:
    """Generate findings, limitations, and follow-up questions."""
    client = _get_client()

    chart_summary = "\n".join(
        f"- {c['chart_type'].title()} chart: {c['title']}" for c in chart_specs
    )
    cleaning_summary = "\n".join(f"- {s}" for s in cleaning_steps)

    prompt = f"""{dataset_context}

CLEANING STEPS APPLIED:
{cleaning_summary}

CHARTS GENERATED:
{chart_summary}

Please write a research analysis report with exactly three sections in this JSON format:
{{
  "findings": "3-5 paragraph plain-English narrative of the key findings. Describe what the data shows, notable patterns, group comparisons, and any correlations observed. Be specific about column names and values.",
  "limitations": "A bullet-pointed list (using • ) of 4-6 limitations of this analysis. Include data quality issues, observational study limitations, confounders, and generalizability concerns.",
  "follow_up": "A numbered list of 5 specific follow-up research questions or experiments that would strengthen the analysis. Be concrete and reference the specific columns and findings."
}}

Return only valid JSON. No extra text."""

    response = client.messages.create(
        model=settings.model_name,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        data = json.loads(raw)
        return {
            "findings": data.get("findings", ""),
            "limitations": data.get("limitations", ""),
            "follow_up": data.get("follow_up", ""),
        }
    except json.JSONDecodeError:
        # Graceful fallback
        return {
            "findings": raw,
            "limitations": "• Analysis limitations could not be parsed automatically.",
            "follow_up": "1. Review the raw data for additional patterns.",
        }


async def stream_chat_response(
    message: str,
    dataset_context: str,
    chat_history: list[dict[str, str]],
) -> AsyncIterator[str]:
    """Stream chat response tokens from Claude."""
    system_with_context = SYSTEM_PROMPT + f"\n\nCurrent dataset context:\n{dataset_context}"

    # Build message history (cap at 20 turns)
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in chat_history[-20:]
    ]
    messages.append({"role": "user", "content": message})

    client = _get_async_client()
    async with client.messages.stream(
        model=settings.model_name,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": system_with_context,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
