"""POST /api/discover — runs the CDC discovery agent and streams events as SSE.

On success, emits a final 'result' event with {session_id, primary_alias, filename,
row_count, col_count, columns, preview_rows} so the frontend can transition into
the same flow as a CSV upload.
"""

import math
from typing import Any

from fastapi import APIRouter

from models import session as session_store
from models.schemas import DiscoverRequest
from services.agent import discover
from utils.file_utils import save_upload
from .streaming import stream_agent_events, sse_response


router = APIRouter()


def _sanitize(v: Any) -> Any:
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


@router.post("/discover")
async def discover_datasets(req: DiscoverRequest):
    """Spawn a session, run the discovery agent on `question`, stream events as SSE."""
    sess = session_store.create_session(
        filename=f"cdc-discover.csv",
        original_path="",
    )
    sess.research_question = req.question

    def run(emit):
        ws, primary, _events = discover(req.question, workspace=sess.workspace, on_event=emit)
        sess.discover_events = list(_events)

        if primary is None or primary not in ws.frames:
            return {"ok": False, "error": "Discovery agent did not produce a primary dataset."}

        df = ws.frames[primary]
        if len(df) == 0 or len(df.columns) == 0:
            return {
                "ok": False,
                "error": (
                    f"Discovery agent finished with empty primary alias `{primary}` "
                    f"({len(df)} rows × {len(df.columns)} cols). The most common cause is "
                    "a SoQL `where` filter that excludes every row (e.g. a state name that "
                    "doesn't exist in the dataset). Try rephrasing the question with a "
                    "broader scope, or omitting the geographic filter."
                ),
            }

        sess.primary_alias = primary

        # Save to disk so /profile and /analyze can read it like an upload
        contents = df.to_csv(index=False).encode("utf-8")
        nice_filename = f"cdc_{primary}.csv"
        sess.filename = nice_filename
        path = save_upload(sess.session_id, nice_filename, contents)
        sess.original_path = str(path)

        # Build a 50-row preview
        preview_df = df.head(50)
        preview_rows = [
            {k: _sanitize(v) for k, v in row.items()}
            for row in preview_df.to_dict("records")
        ]
        sess.preview_rows = preview_rows

        return {
            "ok": True,
            "session_id": sess.session_id,
            "filename": nice_filename,
            "primary_alias": primary,
            "row_count": int(len(df)),
            "col_count": int(len(df.columns)),
            "columns": [str(c) for c in df.columns.tolist()],
            "preview_rows": preview_rows,
            "file_size_bytes": len(contents),
        }

    return sse_response(stream_agent_events(run))
