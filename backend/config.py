import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    upload_dir: str = "/tmp/healthlab_sessions"
    healthlab_db_path: str = "var/healthlab.sqlite3"
    healthlab_upload_dir: str = "var/uploads"
    healthlab_cache_dir: str = "var/cache"
    max_file_size_mb: int = 50
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    model_name: str = "claude-sonnet-4-6"
    discovery_model_name: str = "claude-haiku-4-5"
    # Cheaper/faster model used by sub-agents (catalog scout, schema inspection).
    # Haiku 4.5 finishes a search → schema → recommend round-trip in ~2-3s.
    scout_model_name: str = "claude-haiku-4-5"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore", "protected_namespaces": ()}


settings = Settings()

# Ensure upload dir exists
os.makedirs(settings.upload_dir, exist_ok=True)
