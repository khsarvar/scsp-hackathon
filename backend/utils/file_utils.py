import os
import shutil
from pathlib import Path

from config import settings


def get_session_dir(session_id: str) -> Path:
    path = Path(settings.upload_dir) / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(session_id: str, filename: str, contents: bytes) -> Path:
    session_dir = get_session_dir(session_id)
    file_path = session_dir / "original.csv"
    file_path.write_bytes(contents)
    return file_path


def get_original_path(session_id: str) -> Path:
    return get_session_dir(session_id) / "original.csv"


def get_cleaned_path(session_id: str) -> Path:
    return get_session_dir(session_id) / "cleaned.csv"


def cleanup_session(session_id: str) -> None:
    session_dir = get_session_dir(session_id)
    if session_dir.exists():
        shutil.rmtree(session_dir)
