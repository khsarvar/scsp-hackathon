from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from config import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _backend_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BACKEND_DIR / path


DB_PATH = _backend_path(settings.healthlab_db_path)


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    _backend_path(settings.healthlab_upload_dir).mkdir(parents=True, exist_ok=True)
    _backend_path(settings.healthlab_cache_dir).mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_runs (
              id TEXT PRIMARY KEY,
              question TEXT NOT NULL,
              provider TEXT NOT NULL,
              model TEXT NOT NULL,
              status TEXT NOT NULL,
              discovery_mode TEXT,
              discovery_rationale TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cdc_candidates (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id TEXT NOT NULL,
              dataset_id TEXT NOT NULL,
              title TEXT NOT NULL,
              description TEXT,
              row_count INTEGER,
              updated_at TEXT,
              columns_json TEXT NOT NULL,
              geo_fields_json TEXT NOT NULL,
              date_fields_json TEXT NOT NULL,
              relevance_reason TEXT,
              raw_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pinned_datasets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id TEXT NOT NULL,
              dataset_id TEXT NOT NULL,
              title TEXT NOT NULL,
              api_url TEXT NOT NULL,
              soql_json TEXT NOT NULL,
              selected_columns_json TEXT NOT NULL,
              selected_by_user INTEGER NOT NULL DEFAULT 1,
              local_path TEXT,
              profile_json TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS join_plans (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id TEXT NOT NULL,
              left_dataset_id TEXT NOT NULL,
              right_dataset_id TEXT NOT NULL,
              strategy TEXT NOT NULL,
              join_type TEXT NOT NULL,
              keys_json TEXT NOT NULL,
              normalizations_json TEXT NOT NULL,
              confidence REAL NOT NULL,
              risks TEXT,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS join_results (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id TEXT NOT NULL,
              join_plan_id INTEGER NOT NULL,
              local_path TEXT NOT NULL,
              rows_left INTEGER NOT NULL,
              rows_right INTEGER NOT NULL,
              rows_output INTEGER NOT NULL,
              match_rate REAL NOT NULL,
              unmatched_examples_json TEXT NOT NULL,
              duplicate_warnings_json TEXT NOT NULL,
              explanation TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS methodology_actions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id TEXT NOT NULL,
              agent_name TEXT NOT NULL,
              action_type TEXT NOT NULL,
              rationale TEXT,
              input_json TEXT NOT NULL,
              output_json TEXT NOT NULL,
              warnings_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS statistical_results (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id TEXT NOT NULL,
              test_name TEXT NOT NULL,
              variables_json TEXT NOT NULL,
              assumptions_json TEXT NOT NULL,
              result_json TEXT NOT NULL,
              interpretation TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS literature_citations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id TEXT NOT NULL,
              pmid TEXT NOT NULL,
              title TEXT NOT NULL,
              authors TEXT,
              journal TEXT,
              year TEXT,
              url TEXT NOT NULL,
              abstract_snippet TEXT,
              query_used TEXT NOT NULL,
              relevance_note TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_threads (
              id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              title TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              thread_id TEXT NOT NULL,
              role TEXT NOT NULL,
              content TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id TEXT NOT NULL,
              markdown TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )


def rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def row(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with connect() as conn:
        value = conn.execute(sql, params).fetchone()
        return dict(value) if value else None


def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    with connect() as conn:
        cur = conn.execute(sql, params)
        return int(cur.lastrowid or 0)


def log_action(
    run_id: str,
    agent_name: str,
    action_type: str,
    input_data: Any,
    output_data: Any,
    rationale: str = "",
    warnings: Any | None = None,
) -> None:
    execute(
        """
        INSERT INTO methodology_actions
        (run_id, agent_name, action_type, rationale, input_json, output_json, warnings_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            agent_name,
            action_type,
            rationale,
            _json(input_data),
            _json(output_data),
            _json(warnings or []),
            now_iso(),
        ),
    )
