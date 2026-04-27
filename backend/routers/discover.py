"""POST /api/discover — runs the CDC discovery agent and streams events as SSE.

On success, emits a final 'result' event with {session_id, primary_alias, filename,
row_count, col_count, columns, preview_rows} so the frontend can transition into
the same flow as a CSV upload.

When ≥2 frames are in the workspace, the result includes pending_join=True and a
candidates list so the user can choose which frame to profile (HITL checkpoint).
The actual CSV save then happens via POST /api/discover/select.
"""

import math
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models import session as session_store
from models.schemas import DiscoverRequest, RecommendRequest
from services.agent import discover
from services.discovery import Workspace, search_catalog, get_dataset_schema
from utils.file_utils import save_upload
from .streaming import stream_agent_events, sse_response


router = APIRouter()


def _sanitize(v: Any) -> Any:
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _build_provenance(ws, primary: str, research_question: str, filename: str) -> dict:
    sources = []
    for alias, meta in ws.meta.items():
        cdc_id = meta.get("id")
        domain = meta.get("domain") or "data.cdc.gov"
        soql = meta.get("soql") or {}
        sources.append({
            "alias": alias,
            "source_str": meta.get("source", alias),
            "cdc_id": cdc_id,
            "cdc_url": f"https://{domain}/resource/{cdc_id}" if cdc_id else None,
            "soql_filter": soql.get("where"),
            "soql_select": soql.get("select"),
            "parents": meta.get("parents", []),
        })
    return {
        "type": "cdc_discover",
        "filename": filename,
        "research_question": research_question,
        "primary_alias": primary,
        "sources": sources,
    }


def _save_frame(sess, alias: str) -> dict:
    """Save the named workspace frame to disk and return the upload-ready payload."""
    ws = sess.workspace
    df = ws.frames[alias]
    contents = df.to_csv(index=False).encode("utf-8")
    nice_filename = f"cdc_{alias}.csv"
    sess.filename = nice_filename
    path = save_upload(sess.session_id, nice_filename, contents)
    sess.original_path = str(path)
    sess.primary_alias = alias
    sess.pending_join = False

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
        "primary_alias": alias,
        "row_count": int(len(df)),
        "col_count": int(len(df.columns)),
        "columns": [str(c) for c in df.columns.tolist()],
        "preview_rows": preview_rows,
        "file_size_bytes": len(contents),
        "provenance": _build_provenance(ws, alias, sess.research_question or "", nice_filename),
    }


@router.post("/discover/recommend")
async def recommend_datasets(req: RecommendRequest):
    """Search the CDC Socrata catalog and return dataset metadata for user selection.
    No LLM involved — fast direct catalog search + schema calls."""
    ws = Workspace()
    catalog = search_catalog(ws, req.question, limit=6)
    results = catalog.get("results", [])

    # Enrich each result with full column info from the schema endpoint
    enriched = []
    for entry in results:
        dataset_id = entry.get("id")
        if not dataset_id:
            continue
        schema = {}
        try:
            schema = get_dataset_schema(ws, dataset_id)
        except Exception:
            pass
        enriched.append({
            "id": dataset_id,
            "name": entry.get("name") or schema.get("name") or dataset_id,
            "description": schema.get("description") or entry.get("description") or "",
            "row_count": entry.get("row_count"),
            "categories": entry.get("categories", []),
            "tags": entry.get("tags", []),
            "columns": [
                {"field": c.get("field"), "name": c.get("name"), "type": c.get("type")}
                for c in schema.get("columns", [])
                if not (c.get("field") or "").startswith(":")  # skip Socrata internal cols
            ][:20],
        })

    return {"ok": True, "question": req.question, "results": enriched}


@router.post("/discover")
async def discover_datasets(req: DiscoverRequest):
    """Spawn a session, run the discovery agent on `question`, stream events as SSE."""
    sess = session_store.create_session(
        filename="cdc-discover.csv",
        original_path="",
    )
    sess.research_question = req.question

    def run(emit):
        ws, primary, _events = discover(
            req.question,
            workspace=sess.workspace,
            on_event=emit,
            selected_dataset_ids=req.selected_dataset_ids or [],
        )
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

        all_aliases = list(ws.frames.keys())

        # HITL checkpoint: if the agent fetched/created ≥2 frames, let the user pick.
        if len(all_aliases) >= 2:
            candidates = []
            for alias in all_aliases:
                frame_df = ws.frames[alias]
                meta = ws.meta.get(alias, {})
                candidates.append({
                    "alias": alias,
                    "rows": int(len(frame_df)),
                    "cols": int(len(frame_df.columns)),
                    "columns": [str(c) for c in frame_df.columns.tolist()],
                    "is_derived": bool(meta.get("parents")),
                    "source_title": meta.get("id", alias),
                    "parents": meta.get("parents", []),
                })

            emit({
                "type": "hitl_join",
                "candidates": candidates,
                "suggested_alias": primary,
            })
            sess.pending_join = True

            provenance = _build_provenance(ws, primary, req.question, f"cdc_{primary}.csv")
            return {
                "ok": True,
                "session_id": sess.session_id,
                "pending_join": True,
                "candidates": candidates,
                "suggested_alias": primary,
                "provenance": provenance,
            }

        # Single frame — save immediately and return upload-ready payload.
        return _save_frame(sess, primary)

    return sse_response(stream_agent_events(run))


class SelectFrameRequest(BaseModel):
    session_id: str
    alias: str


@router.post("/discover/select")
async def select_frame(req: SelectFrameRequest):
    """HITL resolution: user chose which workspace frame to use. Save it and return the upload payload."""
    try:
        sess = session_store.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{req.session_id}' not found")

    if req.alias not in sess.workspace.frames:
        raise HTTPException(
            status_code=400,
            detail=f"Alias '{req.alias}' not found in workspace. Available: {list(sess.workspace.frames.keys())}",
        )

    return _save_frame(sess, req.alias)
