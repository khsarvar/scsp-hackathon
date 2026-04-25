import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    upload_dir: str = "/tmp/healthlab_sessions"
    max_file_size_mb: int = 50
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    model_name: str = "claude-sonnet-4-6"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore", "protected_namespaces": ()}


settings = Settings()

# Ensure upload dir exists
os.makedirs(settings.upload_dir, exist_ok=True)
