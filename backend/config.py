import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    upload_dir: str = "/tmp/healthlab_sessions"
    max_file_size_mb: int = 50
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Pydantic AI provider:model strings. Switch providers by changing the prefix.
    # Anthropic: "anthropic:claude-sonnet-4-6", "anthropic:claude-haiku-4-5"
    # OpenAI:    "openai-responses:gpt-5.5"  (Responses API; recommended by OpenAI for tool loops)
    agent_model: str = "anthropic:claude-sonnet-4-6"
    scout_model: str = "anthropic:claude-haiku-4-5"
    # Reasoning effort applied to the scout sub-agent. No-op on Anthropic; keeps
    # OpenAI reasoning models near the ~3s Haiku baseline.
    scout_reasoning_effort: str = "low"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore", "protected_namespaces": ()}


settings = Settings()

# Pydantic AI providers read keys from the environment, so propagate from .env.
if settings.anthropic_api_key:
    os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
if settings.openai_api_key:
    os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)

# Ensure upload dir exists
os.makedirs(settings.upload_dir, exist_ok=True)
