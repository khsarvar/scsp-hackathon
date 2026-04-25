from __future__ import annotations

from typing import Any

from config import settings

PROVIDER_MODELS = {
    "openai": ["gpt-5.2", "gpt-5.2-mini"],
    "anthropic": ["claude-sonnet-4-6", "claude-haiku-4-5"],
    "gemini": ["gemini-2.5-pro", "gemini-2.5-flash"],
}


def available_providers() -> list[dict[str, Any]]:
    keys = {
        "openai": bool(settings.openai_api_key),
        "anthropic": bool(settings.anthropic_api_key),
        "gemini": bool(settings.gemini_api_key),
    }
    return [
        {
            "id": provider,
            "label": {"openai": "OpenAI", "anthropic": "Claude", "gemini": "Gemini"}[provider],
            "configured": keys[provider],
            "models": models,
        }
        for provider, models in PROVIDER_MODELS.items()
    ]


def validate_provider(provider: str, model: str) -> None:
    if provider not in PROVIDER_MODELS:
        raise ValueError(f"Unknown provider: {provider}")
    if model not in PROVIDER_MODELS[provider]:
        raise ValueError(f"Unknown model for {provider}: {model}")
    configured = {p["id"]: p["configured"] for p in available_providers()}
    if not configured.get(provider):
        raise ValueError(f"{provider} is not configured. Add the API key to backend/.env.")


def complete_text(provider: str, model: str, system: str, prompt: str) -> str:
    """Small provider abstraction for chat/report polishing.

    The workbench remains useful without an API key because methodology,
    CDC search, joins, PubMed, and reports are deterministic/log-based.
    """
    validate_provider(provider, model)
    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=900,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text
    if provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.responses.create(
            model=model,
            instructions=system,
            input=prompt,
            max_output_tokens=900,
        )
        return resp.output_text
    if provider == "gemini":
        from google import genai

        client = genai.Client(api_key=settings.gemini_api_key)
        resp = client.models.generate_content(
            model=model,
            contents=f"{system}\n\n{prompt}",
        )
        return resp.text or ""
    raise ValueError(f"Unknown provider: {provider}")
