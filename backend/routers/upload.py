import io
import math
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File

from config import settings
from models import session as session_store
from utils.file_utils import save_upload


def _sanitize(val: Any) -> Any:
    """Replace NaN/inf with None so the value is JSON-serializable."""
    if isinstance(val, float) and not math.isfinite(val):
        return None
    return val

router = APIRouter()

MAX_BYTES = settings.max_file_size_mb * 1024 * 1024


@router.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    contents = await file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_file_size_mb} MB.",
        )

    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    if df.empty:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty.")

    # Create session
    sess = session_store.create_session(
        filename=file.filename,
        original_path="",  # filled after save
    )

    file_path = save_upload(sess.session_id, file.filename, contents)
    session_store.update_session(sess.session_id, original_path=str(file_path))

    # Build preview (first 50 rows, NaN/inf → None for JSON)
    preview_df = df.head(50)
    preview_rows = [
        {k: _sanitize(v) for k, v in row.items()}
        for row in preview_df.to_dict("records")
    ]
    session_store.update_session(sess.session_id, preview_rows=preview_rows)

    return {
        "session_id": sess.session_id,
        "filename": file.filename,
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns": df.columns.tolist(),
        "preview_rows": preview_rows,
        "file_size_bytes": len(contents),
    }
