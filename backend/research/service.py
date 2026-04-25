from __future__ import annotations

import json
import math
import re
import uuid
import concurrent.futures
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from scipy import stats as sp_stats

from config import settings
from db.database import _backend_path, execute, log_action, now_iso, row, rows
from providers.registry import available_providers, validate_provider
from services.agent import analyze_question, auto_clean, discover, generate_hypotheses
from services.discovery import CDC_DOMAIN, CATALOG_URL, RESOURCE_URL, VIEW_URL
from services.discovery import Workspace
from services.discovery import fetch_dataset as socrata_fetch_dataset
from services.discovery import get_dataset_schema as socrata_get_dataset_schema
from services.discovery import search_catalog as socrata_search_catalog


def _j(value: Any) -> str:
    return json.dumps(value, default=str)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _safe_number(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _cache_path(run_id: str, name: str) -> Path:
    path = _backend_path(settings.healthlab_cache_dir) / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path / name


def list_providers() -> list[dict[str, Any]]:
    return available_providers()


def _create_run_record(question: str, provider: str, model: str) -> str:
    validate_provider(provider, model)
    if not settings.anthropic_api_key:
        raise ValueError("The previous agent loops require ANTHROPIC_API_KEY. Add it to backend/.env.")
    run_id = str(uuid.uuid4())
    ts = now_iso()
    execute(
        """
        INSERT INTO research_runs
        (id, question, provider, model, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, question, provider, model, "discovering", ts, ts),
    )
    log_action(run_id, "orchestrator", "create_run", {"question": question, "provider": provider, "model": model}, {"status": "created"})
    create_thread(run_id, "Research chat")
    return run_id


def create_run(question: str, provider: str, model: str) -> dict[str, Any]:
    return create_run_agentic(question, provider, model)


def create_run_agentic(
    question: str,
    provider: str,
    model: str,
    on_event: Any | None = None,
) -> dict[str, Any]:
    run_id = _create_run_record(question, provider, model)
    ws = Workspace()
    literature_future = None

    def emit(event: dict[str, Any]) -> None:
        _log_agent_event(run_id, event)
        if on_event is not None:
            on_event(event)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            literature_future = ex.submit(search_pubmed, run_id, question)
            if _use_fast_socrata_discovery(question):
                primary_alias = _fast_socrata_discover(question, ws, emit)
            else:
                ws, primary_alias, events = discover(
                    question,
                    workspace=ws,
                    on_event=emit,
                    model_name=settings.discovery_model_name,
                    scout_model_name=settings.scout_model_name,
                )
            citations = literature_future.result()
    except Exception as e:
        log_action(run_id, "discover", "agent_error", {"question": question}, {"error": str(e)}, warnings=[str(e)])
        raise

    candidates = _persist_workspace_candidates(run_id, ws, primary_alias)
    mode = _discovery_mode(question, candidates)
    rationale = (
        f"Agentic Socrata discovery completed with primary alias `{primary_alias}`. "
        "Datasets were selected after catalog/schema/tool inspection."
        if candidates
        else "Agentic Socrata discovery did not persist any dataset candidates."
    )
    execute(
        "UPDATE research_runs SET status=?, discovery_mode=?, discovery_rationale=?, updated_at=? WHERE id=?",
        ("agent_discovery_ready", mode, rationale, now_iso(), run_id),
    )
    return get_run_bundle(run_id) | {"new_citations": citations}


def _use_fast_socrata_discovery(question: str) -> bool:
    q = question.lower()
    multi_terms = [" join ", " combine ", " relationship ", " associated ", " association ", " versus ", " vs ", " and "]
    return not any(t in f" {q} " for t in multi_terms)


def _fast_socrata_discover(question: str, ws: Workspace, emit: Any) -> str | None:
    emit({"type": "thought", "agent": "discover", "text": "Using fast Socrata discovery for a likely single-dataset question."})
    queries = _expanded_queries(question)
    all_results: list[dict[str, Any]] = []
    for query in queries:
        emit({"type": "tool_call", "agent": "discover", "name": "search_catalog", "args": {"query": query, "limit": 8}, "rationale": "Fast Socrata search variant"})
        try:
            result = socrata_search_catalog(ws, query, 8)
        except Exception as e:
            emit({"type": "tool_result", "agent": "discover", "name": "search_catalog", "summary": f"error: {e}", "result": {"ok": False, "error": str(e)}})
            continue
        emit({"type": "tool_result", "agent": "discover", "name": "search_catalog", "summary": f"{result.get('n_results', 0)} result(s)", "result": result})
        all_results.extend(result.get("results", []))
        if all_results:
            break
    if not all_results:
        emit({"type": "error", "agent": "discover", "message": "Fast Socrata search found no candidates."})
        return None

    ranked = _rank_catalog_results(question, all_results)[:4]

    def inspect(candidate: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        schema = socrata_get_dataset_schema(ws, candidate["id"])
        return candidate, schema

    inspected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(ranked))) as ex:
        futures = []
        for candidate in ranked:
            emit({"type": "tool_call", "agent": "discover", "name": "get_dataset_schema", "args": {"dataset_id": candidate["id"]}, "rationale": "Inspect candidate schema before fetch"})
            futures.append(ex.submit(inspect, candidate))
        for fut in concurrent.futures.as_completed(futures):
            try:
                candidate, schema = fut.result()
            except Exception as e:
                emit({"type": "tool_result", "agent": "discover", "name": "get_dataset_schema", "summary": f"error: {e}", "result": {"ok": False, "error": str(e)}})
                continue
            inspected.append((candidate, schema))
            emit({"type": "tool_result", "agent": "discover", "name": "get_dataset_schema", "summary": f"{schema.get('name', candidate.get('name'))} - {len(schema.get('columns', []))} columns", "result": schema})

    if not inspected:
        return None
    candidate, schema = sorted(inspected, key=lambda item: _schema_score(question, item[0], item[1]), reverse=True)[0]
    fields = [c.get("field") for c in schema.get("columns", []) if c.get("field")]
    alias = re.sub(r"[^a-z0-9]+", "_", (schema.get("name") or candidate["id"]).lower()).strip("_")[:32] or "primary"
    args = {"dataset_id": candidate["id"], "alias": alias, "select": ",".join(fields[:12]) if fields else None, "limit": 25000}
    emit({"type": "tool_call", "agent": "discover", "name": "fetch_dataset", "args": args, "rationale": "Fetch best schema-inspected Socrata candidate"})
    result = socrata_fetch_dataset(ws, **args)
    emit({"type": "tool_result", "agent": "discover", "name": "fetch_dataset", "summary": f"loaded `{alias}` - {result.get('rows', 0)} rows", "result": result})
    if result.get("ok") and result.get("rows", 0) > 0:
        emit({"type": "final", "agent": "discover", "primary_alias": alias, "summary": f"Fast Socrata discovery selected `{candidate['id']}`."})
        return alias
    return None


def _expanded_queries(question: str) -> list[str]:
    q = question.strip()
    variants = [q]
    if "emergency visits" in q.lower():
        variants.append(re.sub("emergency visits", "emergency department visits", q, flags=re.I))
    variants.extend([f"{q} surveillance", f"{q} chronic disease indicators"])
    out = []
    seen = set()
    for v in variants:
        key = v.lower()
        if key not in seen:
            out.append(v)
            seen.add(key)
    return out


def _rank_catalog_results(question: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dedup = {c.get("id"): c for c in candidates if c.get("id")}
    return sorted(dedup.values(), key=lambda c: _catalog_score(question, c), reverse=True)


def _catalog_score(question: str, candidate: dict[str, Any]) -> int:
    terms = [t for t in re.split(r"[^a-z0-9]+", question.lower()) if len(t) > 2]
    hay = " ".join([
        str(candidate.get("name", "")),
        str(candidate.get("description", "")),
        " ".join(candidate.get("columns_field_names", []) or []),
    ]).lower()
    score = sum(3 for t in terms if t in hay)
    for bonus in ("asthma", "emergency", "department", "visits", "county", "state", "fips", "week", "year"):
        if bonus in hay:
            score += 1
    return score


def _schema_score(question: str, candidate: dict[str, Any], schema: dict[str, Any]) -> int:
    fields = " ".join(str(c.get("field") or c.get("name") or "") for c in schema.get("columns", [])).lower()
    return _catalog_score(question, candidate) + sum(2 for k in ("county", "state", "fips", "geography", "date", "week", "year") if k in fields)


def _log_agent_event(run_id: str, event: dict[str, Any]) -> None:
    etype = event.get("type", "event")
    agent = event.get("agent") or "agent"
    input_data = {
        "name": event.get("name"),
        "args": event.get("args", {}),
        "primary_alias": event.get("primary_alias"),
    }
    output_data = {
        "text": event.get("text"),
        "summary": event.get("summary"),
        "result": event.get("result"),
        "message": event.get("message"),
    }
    warnings = [event["message"]] if etype == "error" and event.get("message") else []
    log_action(
        run_id,
        agent,
        etype,
        input_data,
        output_data,
        rationale=event.get("rationale", ""),
        warnings=warnings,
    )


def _persist_workspace_candidates(run_id: str, ws: Workspace, primary_alias: str | None) -> list[dict[str, Any]]:
    aliases = list(ws.frames)
    if primary_alias in aliases:
        aliases.remove(primary_alias)
        aliases.insert(0, primary_alias)
    candidates: list[dict[str, Any]] = []
    for alias in aliases:
        df = ws.frames[alias]
        meta = ws.meta.get(alias, {})
        dataset_id = meta.get("id") or f"workspace-{alias}"
        schema = _schema(dataset_id) if not dataset_id.startswith("workspace-") else {}
        title = schema.get("name") or alias
        columns = [str(c) for c in df.columns.tolist()]
        geo_fields = [c for c in columns if any(k in c.lower() for k in ("county", "state", "zip", "fips", "geography", "location"))]
        date_fields = [c for c in columns if any(k in c.lower() for k in ("date", "year", "week", "month", "time"))]
        execute(
            """
            INSERT INTO cdc_candidates
            (run_id, dataset_id, title, description, row_count, updated_at, columns_json,
             geo_fields_json, date_fields_json, relevance_reason, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                dataset_id,
                title,
                (schema.get("description") or f"Agent-selected Socrata workspace alias `{alias}`")[:700],
                int(len(df)),
                schema.get("updatedAt"),
                _j(columns),
                _j(geo_fields),
                _j(date_fields),
                "Selected by the previous agentic Socrata discovery loop after tool/schema inspection.",
                _j({"alias": alias, "meta": meta}),
            ),
        )
        local_path = _cache_path(run_id, f"{alias}.csv")
        df.to_csv(local_path, index=False)
        profile = _profile(df)
        execute(
            """
            INSERT INTO pinned_datasets
            (run_id, dataset_id, title, api_url, soql_json, selected_columns_json, selected_by_user,
             local_path, profile_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                run_id,
                dataset_id,
                title,
                meta.get("source", RESOURCE_URL.format(domain=CDC_DOMAIN, id=dataset_id)),
                _j(meta.get("soql", {})),
                _j(columns),
                str(local_path),
                _j(profile),
                now_iso(),
            ),
        )
        candidates.append(
            {
                "dataset_id": dataset_id,
                "title": title,
                "description": (schema.get("description") or "")[:700],
                "row_count": int(len(df)),
                "updated_at": schema.get("updatedAt"),
                "columns": columns,
                "geo_fields": geo_fields,
                "date_fields": date_fields,
                "relevance_reason": "Selected by the previous agentic Socrata discovery loop.",
            }
        )
    log_action(run_id, "discover", "persist_workspace", {"aliases": aliases, "primary_alias": primary_alias}, {"n_candidates": len(candidates)})
    return candidates


def _discovery_mode(question: str, candidates: list[dict[str, Any]]) -> str:
    q = question.lower()
    multi_terms = ["compare", "relationship", "associated", "association", "versus", " vs ", " and ", "join", "combine"]
    if len(candidates) > 1 and any(t in q for t in multi_terms):
        return "multi_dataset_candidates"
    return "single_dataset_ready"


def _discovery_rationale(mode: str, candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "No CDC candidates were found. Try broader keywords or upload a CSV."
    if mode == "single_dataset_ready":
        return f"The top CDC result looks sufficient for a first pass: {candidates[0]['title']}."
    return "The question may benefit from combining more than one dataset, so candidate datasets are shown for pinning."


def search_cdc_candidates(run_id: str, question: str, limit: int = 8) -> list[dict[str, Any]]:
    params = {
        "domains": CDC_DOMAIN,
        "search_context": CDC_DOMAIN,
        "q": question,
        "only": "dataset",
        "limit": limit,
    }
    try:
        data = requests.get(CATALOG_URL, params=params, timeout=30).json()
    except Exception as e:
        log_action(run_id, "discovery", "cdc_search", {"question": question}, {"error": str(e)}, warnings=[str(e)])
        return []

    candidates = []
    for entry in data.get("results", []):
        resource = entry.get("resource", {})
        dataset_id = resource.get("id")
        if not dataset_id:
            continue
        columns = resource.get("columns_field_name", [])[:60]
        geo_fields = [c for c in columns if any(k in c.lower() for k in ("county", "state", "zip", "fips", "geography", "location"))]
        date_fields = [c for c in columns if any(k in c.lower() for k in ("date", "year", "week", "month", "time"))]
        title = resource.get("name") or dataset_id
        candidate = {
            "dataset_id": dataset_id,
            "title": title,
            "description": (resource.get("description") or "")[:700],
            "row_count": resource.get("rows_size"),
            "updated_at": resource.get("updatedAt"),
            "columns": columns,
            "geo_fields": geo_fields,
            "date_fields": date_fields,
            "relevance_reason": f"Matched CDC catalog terms for: {question[:120]}",
            "raw": resource,
        }
        execute(
            """
            INSERT INTO cdc_candidates
            (run_id, dataset_id, title, description, row_count, updated_at, columns_json,
             geo_fields_json, date_fields_json, relevance_reason, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                dataset_id,
                title,
                candidate["description"],
                candidate["row_count"],
                candidate["updated_at"],
                _j(columns),
                _j(geo_fields),
                _j(date_fields),
                candidate["relevance_reason"],
                _j(resource),
            ),
        )
        candidates.append(candidate)

    log_action(run_id, "discovery", "cdc_search", {"question": question, "limit": limit}, {"n_candidates": len(candidates)})
    return candidates


def _schema(dataset_id: str) -> dict[str, Any]:
    try:
        return requests.get(VIEW_URL.format(domain=CDC_DOMAIN, id=dataset_id), timeout=30).json()
    except Exception:
        return {}


def _fetch_dataset(dataset_id: str, limit: int = 25000) -> pd.DataFrame:
    url = RESOURCE_URL.format(domain=CDC_DOMAIN, id=dataset_id)
    rows_data = requests.get(url, params={"$limit": limit}, timeout=60).json()
    if not isinstance(rows_data, list):
        raise ValueError(f"Unexpected CDC response for {dataset_id}: {str(rows_data)[:200]}")
    return pd.DataFrame(rows_data)


def _profile(df: pd.DataFrame) -> dict[str, Any]:
    cols = []
    for name in df.columns:
        s = df[name]
        numeric = pd.to_numeric(s, errors="coerce")
        numeric_ok = int(numeric.notna().sum())
        dtype = "numeric" if numeric_ok >= max(3, int(len(s) * 0.7)) else "categorical"
        if any(k in name.lower() for k in ("date", "year", "week", "month")):
            dtype = "datetime"
        if s.nunique(dropna=True) == len(s) and len(s) > 20:
            dtype = "id"
        cols.append(
            {
                "name": name,
                "dtype": dtype,
                "missing_pct": round(float(s.isna().mean() * 100), 2),
                "unique_count": int(s.nunique(dropna=True)),
                "sample_values": [str(x) for x in s.dropna().unique()[:6].tolist()],
            }
        )
    return {"row_count": int(len(df)), "col_count": int(len(df.columns)), "columns": cols}


def pin_dataset(run_id: str, dataset_id: str, title: str | None = None) -> dict[str, Any]:
    df = _fetch_dataset(dataset_id)
    api_url = RESOURCE_URL.format(domain=CDC_DOMAIN, id=dataset_id)
    if df.empty:
        raise ValueError(f"CDC dataset {dataset_id} returned no rows.")
    schema = _schema(dataset_id)
    title = title or schema.get("name") or dataset_id
    local_path = _cache_path(run_id, f"{dataset_id}.csv")
    df.to_csv(local_path, index=False)
    profile = _profile(df)
    execute(
        """
        INSERT INTO pinned_datasets
        (run_id, dataset_id, title, api_url, soql_json, selected_columns_json, selected_by_user,
         local_path, profile_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            run_id,
            dataset_id,
            title,
            api_url,
            _j({"limit": 25000}),
            _j(list(df.columns)),
            str(local_path),
            _j(profile),
            now_iso(),
        ),
    )
    log_action(run_id, "discovery", "pin_dataset", {"dataset_id": dataset_id}, {"rows": len(df), "columns": list(df.columns)})
    execute("UPDATE research_runs SET status=?, updated_at=? WHERE id=?", ("datasets_pinned", now_iso(), run_id))
    return get_run_bundle(run_id)


def _norm_col_name(name: str) -> str:
    n = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    replacements = {
        "county_name": "county",
        "cnty": "county",
        "state_name": "state",
        "state_abbr": "state",
        "zipcode": "zip",
        "zip_code": "zip",
        "postal_code": "zip",
        "fips_code": "fips",
        "year_number": "year",
    }
    return replacements.get(n, n)


def _join_candidates(left_profile: dict[str, Any], right_profile: dict[str, Any]) -> list[dict[str, str]]:
    left_cols = [c["name"] for c in left_profile.get("columns", [])]
    right_cols = [c["name"] for c in right_profile.get("columns", [])]
    by_norm = {}
    for c in right_cols:
        by_norm.setdefault(_norm_col_name(c), []).append(c)
    keys = []
    preferred = ("fips", "county", "state", "zip", "year", "date", "week", "month")
    for lc in left_cols:
        norm = _norm_col_name(lc)
        if norm in by_norm and (norm in preferred or any(p in norm for p in preferred)):
            keys.append({"left": lc, "right": by_norm[norm][0], "normalized_name": norm})
    if not keys:
        for lc in left_cols:
            norm = _norm_col_name(lc)
            if norm in by_norm:
                keys.append({"left": lc, "right": by_norm[norm][0], "normalized_name": norm})
    return keys[:4]


def propose_joins(run_id: str) -> dict[str, Any]:
    pins = _pinned(run_id)
    if len(pins) < 2:
        return get_run_bundle(run_id) | {"join_message": "At least two pinned datasets are needed to propose joins."}
    existing = rows("SELECT * FROM join_plans WHERE run_id=? ORDER BY id", (run_id,))
    if existing:
        return get_run_bundle(run_id)
    for i in range(len(pins) - 1):
        left, right_pin = pins[i], pins[i + 1]
        keys = _join_candidates(left.get("profile") or {}, right_pin.get("profile") or {})
        if not keys:
            keys = [{"left": (left.get("columns") or [""])[0], "right": (right_pin.get("columns") or [""])[0], "normalized_name": "manual_review"}]
            confidence = 0.25
            risks = "No obvious shared geography/time key was found. Review and edit before applying."
            strategy = "manual_review"
        else:
            confidence = min(0.95, 0.55 + 0.1 * len(keys))
            strategy = "normalized"
            risks = "Validate grain before applying. County/state/year joins can duplicate rows if either side has repeated keys."
        execute(
            """
            INSERT INTO join_plans
            (run_id, left_dataset_id, right_dataset_id, strategy, join_type, keys_json,
             normalizations_json, confidence, risks, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                left["dataset_id"],
                right_pin["dataset_id"],
                strategy,
                "left",
                _j(keys),
                _j(["trim", "lowercase", "county suffix stripping", "zip5 extraction", "fips zero-padding", "year/date bucketing"]),
                confidence,
                risks,
                "proposed",
                now_iso(),
            ),
        )
    log_action(run_id, "join_agent", "propose_joins", {"pinned_dataset_count": len(pins)}, {"plans_created": max(0, len(pins) - 1)})
    return get_run_bundle(run_id)


def _normal_series(s: pd.Series, norm_name: str) -> pd.Series:
    out = s.astype(str).str.strip().str.lower()
    out = out.str.replace(r"\s+county$", "", regex=True)
    if "zip" in norm_name:
        out = out.str.extract(r"(\d{5})", expand=False).fillna(out)
    if "fips" in norm_name:
        out = out.str.extract(r"(\d+)", expand=False).fillna(out).str.zfill(5)
    if "year" in norm_name:
        out = out.str.extract(r"(\d{4})", expand=False).fillna(out)
    return out


def apply_join(run_id: str, join_plan_id: int) -> dict[str, Any]:
    plan = row("SELECT * FROM join_plans WHERE id=? AND run_id=?", (join_plan_id, run_id))
    if not plan:
        raise ValueError("Join plan not found.")
    pins = {p["dataset_id"]: p for p in _pinned(run_id)}
    left_pin, right_pin = pins[plan["left_dataset_id"]], pins[plan["right_dataset_id"]]
    left = pd.read_csv(left_pin["local_path"])
    right = pd.read_csv(right_pin["local_path"])
    keys = _loads(plan["keys_json"], [])
    left_work, right_work = left.copy(), right.copy()
    left_keys, right_keys = [], []
    for idx, key in enumerate(keys):
        lk, rk = f"__join_left_{idx}", f"__join_right_{idx}"
        left_work[lk] = _normal_series(left_work[key["left"]], key.get("normalized_name", ""))
        right_work[rk] = _normal_series(right_work[key["right"]], key.get("normalized_name", ""))
        left_keys.append(lk)
        right_keys.append(rk)
    dup_warnings = []
    if left_work.duplicated(left_keys).any():
        dup_warnings.append("Left dataset has duplicate join keys; output may contain repeated rows.")
    if right_work.duplicated(right_keys).any():
        dup_warnings.append("Right dataset has duplicate join keys; output may contain repeated rows.")
    out = left_work.merge(right_work, how=plan["join_type"], left_on=left_keys, right_on=right_keys, suffixes=("_left", "_right"), indicator=True)
    matched = int((out["_merge"] == "both").sum()) if "_merge" in out else len(out)
    match_rate = round(matched / max(len(left), 1), 4)
    unmatched = out.loc[out["_merge"] != "both", left_keys].head(8).to_dict("records") if "_merge" in out else []
    out = out.drop(columns=[c for c in out.columns if c.startswith("__join_")] + ["_merge"], errors="ignore")
    path = _cache_path(run_id, f"join_{join_plan_id}.csv")
    out.to_csv(path, index=False)
    explanation = (
        f"Joined {left_pin['title']} to {right_pin['title']} with a {plan['join_type']} join "
        f"using {', '.join(f'{k['left']} -> {k['right']}' for k in keys)} after normalization. "
        f"Matched {matched} of {len(left)} left rows ({match_rate:.0%})."
    )
    execute(
        """
        INSERT INTO join_results
        (run_id, join_plan_id, local_path, rows_left, rows_right, rows_output, match_rate,
         unmatched_examples_json, duplicate_warnings_json, explanation, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, join_plan_id, str(path), len(left), len(right), len(out), match_rate, _j(unmatched), _j(dup_warnings), explanation, now_iso()),
    )
    execute("UPDATE join_plans SET status=? WHERE id=?", ("applied", join_plan_id))
    execute("UPDATE research_runs SET status=?, updated_at=? WHERE id=?", ("analysis_ready", now_iso(), run_id))
    log_action(run_id, "join_agent", "apply_join", {"join_plan_id": join_plan_id, "keys": keys}, {"match_rate": match_rate, "rows_output": len(out)}, explanation, dup_warnings)
    return get_run_bundle(run_id)


def _analysis_frame(run_id: str) -> tuple[pd.DataFrame, str]:
    join = row("SELECT * FROM join_results WHERE run_id=? ORDER BY id DESC LIMIT 1", (run_id,))
    if join:
        return pd.read_csv(join["local_path"]), f"joined dataset from plan {join['join_plan_id']}"
    pins = _pinned(run_id)
    if not pins:
        raise ValueError("Pin at least one dataset before running methodology.")
    return pd.read_csv(pins[0]["local_path"]), pins[0]["title"]


def _interpret_p(p: float) -> str:
    if p < 0.001:
        return "p < 0.001; strong evidence against the null hypothesis."
    if p < 0.05:
        return f"p = {p:.3f}; statistically significant at alpha = 0.05."
    return f"p = {p:.3f}; not statistically significant at alpha = 0.05."


def run_methodology(run_id: str, on_event: Any | None = None) -> dict[str, Any]:
    df, source = _analysis_frame(run_id)
    ws = Workspace()
    ws.add("analysis", df.copy(), {"source": source})
    if settings.anthropic_api_key:
        def emit_method_event(event: dict[str, Any]) -> None:
            _log_agent_event(run_id, event)
            if on_event is not None:
                on_event(event)

        clean_events = auto_clean(ws, "analysis", on_event=emit_method_event, model_name=settings.discovery_model_name)
        cleaned = ws.get("analysis")
        cleaned_path = _cache_path(run_id, "agent_cleaned_analysis.csv")
        cleaned.to_csv(cleaned_path, index=False)
        log_action(
            run_id,
            "clean",
            "persist_cleaned_dataset",
            {"source": source},
            {"rows": len(cleaned), "columns": list(cleaned.columns), "path": str(cleaned_path)},
            rationale="Previous cleaning agent completed and the cleaned analysis frame was saved.",
        )
        try:
            hypotheses = generate_hypotheses(ws, "analysis", n=4, model_name=settings.discovery_model_name)
        except Exception as e:
            hypotheses = [{"question": "Hypothesis generation failed", "rationale": str(e)}]
        log_action(
            run_id,
            "hypotheses",
            "generate_hypotheses",
            {"alias": "analysis", "n": 4},
            {"hypotheses": hypotheses},
        )
        if on_event is not None:
            on_event({"type": "tool_result", "agent": "hypotheses", "name": "generate_hypotheses", "summary": f"Generated {len(hypotheses)} hypotheses.", "result": {"hypotheses": hypotheses}})
        first_question = next((h.get("question") for h in hypotheses if h.get("question")), None)
        if first_question:
            answer, analyze_events = analyze_question(
                first_question,
                ws,
                "analysis",
                on_event=emit_method_event,
                model_name=settings.discovery_model_name,
            )
            log_action(
                run_id,
                "analyze",
                "answer_hypothesis",
                {"question": first_question},
                {"answer": answer},
            )
            for event in analyze_events:
                if event.get("type") == "tool_result" and isinstance(event.get("result"), dict):
                    result_payload = event["result"]
                    if "error" not in result_payload:
                        stat_result = {
                            "test_name": str(result_payload.get("test") or event.get("name") or "Agent-selected statistical test"),
                            "variables": list((hypotheses[0].get("variables") or [])) if hypotheses else [],
                            "assumptions": result_payload.get("assumption_check", {}),
                            "result": result_payload,
                            "interpretation": result_payload.get("interpretation", answer),
                        }
                        _save_stat(run_id, stat_result)
        df = ws.get("analysis")

    profile = _profile(df)
    log_action(run_id, "methodology_agent", "profile_analysis_frame", {"source": source}, profile)
    results: list[dict[str, Any]] = []

    missing = sorted(
        [{"column": c["name"], "missing_pct": c["missing_pct"]} for c in profile["columns"]],
        key=lambda x: x["missing_pct"],
        reverse=True,
    )[:8]
    log_action(run_id, "methodology_agent", "missingness_check", {}, {"top_missing": missing})

    categorical = [c["name"] for c in profile["columns"] if c["dtype"] == "categorical" and 1 < c["unique_count"] <= 12]
    numeric = []
    for c in profile["columns"]:
        if c["dtype"] == "numeric":
            numeric.append(c["name"])

    if len(categorical) >= 2:
        col1, col2 = categorical[:2]
        ct = pd.crosstab(df[col1], df[col2])
        if not ct.empty:
            chi2, p, dof, expected = sp_stats.chi2_contingency(ct)
            sparse = ct.shape == (2, 2) and (expected < 5).any()
            if sparse:
                _, p = sp_stats.fisher_exact(ct.values)
                test = "Fisher's exact test"
                interpretation = "Used Fisher's exact test because the 2x2 table has expected counts below 5."
                stat = None
            else:
                test = "Chi-squared test"
                interpretation = _interpret_p(float(p))
                stat = float(chi2)
            result = {
                "test_name": test,
                "variables": [col1, col2],
                "assumptions": {"expected_cell_min": float(np.min(expected)), "fallback": "Fisher's exact for sparse 2x2" if sparse else None},
                "result": {"statistic": stat, "p_value": float(p), "dof": int(dof), "contingency": ct.to_dict()},
                "interpretation": interpretation,
            }
            _save_stat(run_id, result)
            results.append(result)
            log_action(run_id, "methodology_agent", "run_statistical_test", {"test": test, "variables": [col1, col2]}, result)

    if numeric:
        summary = df[numeric].apply(pd.to_numeric, errors="coerce").describe().replace({np.nan: None}).to_dict()
        log_action(run_id, "methodology_agent", "numeric_summary", {"columns": numeric[:12]}, summary)

    if len(numeric) >= 2:
        clean = df[numeric[:2]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(clean) >= 3:
            r, p = sp_stats.spearmanr(clean[numeric[0]], clean[numeric[1]])
            result = {
                "test_name": "Spearman correlation",
                "variables": numeric[:2],
                "assumptions": {"complete_pairs": int(len(clean)), "method": "rank correlation for robustness"},
                "result": {"correlation": float(r), "p_value": float(p)},
                "interpretation": _interpret_p(float(p)),
            }
            _save_stat(run_id, result)
            results.append(result)
            log_action(run_id, "methodology_agent", "run_statistical_test", {"test": "Spearman correlation", "variables": numeric[:2]}, result)

    if categorical and numeric:
        group_col, value_col = categorical[0], numeric[0]
        groups = [g for g in df[group_col].dropna().unique().tolist() if str(g).strip()][:6]
        samples = [pd.to_numeric(df.loc[df[group_col] == g, value_col], errors="coerce").dropna() for g in groups]
        samples = [s for s in samples if len(s) >= 2]
        if len(samples) == 2:
            stat, p = sp_stats.mannwhitneyu(samples[0], samples[1], alternative="two-sided")
            result = {
                "test_name": "Mann-Whitney U test",
                "variables": [group_col, value_col],
                "assumptions": {"groups_compared": [str(g) for g in groups[:2]], "nonparametric": True},
                "result": {"statistic": float(stat), "p_value": float(p)},
                "interpretation": _interpret_p(float(p)),
            }
            _save_stat(run_id, result)
            results.append(result)
            log_action(run_id, "methodology_agent", "run_statistical_test", {"test": "Mann-Whitney U test"}, result)
        elif len(samples) > 2:
            stat, p = sp_stats.kruskal(*samples)
            result = {
                "test_name": "Kruskal-Wallis test",
                "variables": [group_col, value_col],
                "assumptions": {"n_groups": len(samples), "nonparametric": True},
                "result": {"statistic": float(stat), "p_value": float(p)},
                "interpretation": _interpret_p(float(p)),
            }
            _save_stat(run_id, result)
            results.append(result)
            log_action(run_id, "methodology_agent", "run_statistical_test", {"test": "Kruskal-Wallis test"}, result)

    execute("UPDATE research_runs SET status=?, updated_at=? WHERE id=?", ("methodology_complete", now_iso(), run_id))
    return get_run_bundle(run_id) | {"methodology_results": results}


def run_unsafe_python(run_id: str, code: str) -> dict[str, Any]:
    """Execute arbitrary Python against the active analysis frame.

    This is intentionally unsafe for hackathon experimentation. It runs inside
    the backend process with normal Python builtins and filesystem/network
    access inherited from the server. The full code and output are logged.
    """
    df, source = _analysis_frame(run_id)
    stdout = StringIO()
    env: dict[str, Any] = {
        "pd": pd,
        "np": np,
        "sp_stats": sp_stats,
        "df": df.copy(),
        "result": None,
    }
    output: dict[str, Any]
    warnings = [
        "Unsafe Python execution was enabled. Code ran inside the backend process with server permissions."
    ]
    try:
        with redirect_stdout(stdout):
            exec(code, env, env)
        result = env.get("result")
        output_df = env.get("output_df")
        saved_path = None
        if isinstance(output_df, pd.DataFrame):
            saved_path = _cache_path(run_id, f"unsafe_output_{uuid.uuid4().hex[:8]}.csv")
            output_df.to_csv(saved_path, index=False)
        output = {
            "ok": True,
            "source": source,
            "stdout": stdout.getvalue(),
            "result": _json_safe(result),
            "df_shape": list(env["df"].shape) if isinstance(env.get("df"), pd.DataFrame) else None,
            "output_df_path": str(saved_path) if saved_path else None,
        }
    except Exception as e:
        output = {
            "ok": False,
            "source": source,
            "stdout": stdout.getvalue(),
            "error": f"{type(e).__name__}: {e}",
        }
        warnings.append(output["error"])

    log_action(
        run_id,
        "unsafe_python_agent",
        "execute_python",
        {"code": code},
        output,
        rationale="User-requested unsafe Python execution against the active research dataframe.",
        warnings=warnings,
    )
    execute("UPDATE research_runs SET status=?, updated_at=? WHERE id=?", ("unsafe_code_executed", now_iso(), run_id))
    return get_run_bundle(run_id) | {"unsafe_python_result": output}


def _json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return {
            "type": "DataFrame",
            "shape": list(value.shape),
            "preview": value.head(20).replace({np.nan: None}).to_dict("records"),
        }
    if isinstance(value, pd.Series):
        return {
            "type": "Series",
            "name": value.name,
            "preview": value.head(40).replace({np.nan: None}).to_dict(),
        }
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    try:
        json.dumps(value, default=str)
        return value
    except Exception:
        return str(value)


def _save_stat(run_id: str, result: dict[str, Any]) -> None:
    execute(
        """
        INSERT INTO statistical_results
        (run_id, test_name, variables_json, assumptions_json, result_json, interpretation, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            result["test_name"],
            _j(result.get("variables", [])),
            _j(result.get("assumptions", {})),
            _j(result.get("result", {})),
            result.get("interpretation", ""),
            now_iso(),
        ),
    )


def search_pubmed(run_id: str, question: str, limit: int = 5) -> list[dict[str, Any]]:
    query = f"{question} public health epidemiology"
    try:
        search = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmode": "json", "retmax": limit},
            timeout=30,
        ).json()
        pmids = search.get("esearchresult", {}).get("idlist", [])
        if not pmids:
            log_action(run_id, "literature_agent", "pubmed_search", {"query": query}, {"citations": 0}, warnings=["No PubMed results found."])
            return []
        summary = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(pmids), "retmode": "json"},
            timeout=30,
        ).json()
    except Exception as e:
        log_action(run_id, "literature_agent", "pubmed_search", {"query": query}, {"error": str(e)}, warnings=[str(e)])
        return []
    citations = []
    for pmid in pmids:
        item = summary.get("result", {}).get(pmid, {})
        title = item.get("title") or f"PubMed record {pmid}"
        authors = ", ".join(a.get("name", "") for a in item.get("authors", [])[:5])
        year = str(item.get("pubdate", ""))[:4]
        citation = {
            "pmid": pmid,
            "title": title,
            "authors": authors,
            "journal": item.get("fulljournalname", ""),
            "year": year,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "abstract_snippet": "",
            "query_used": query,
            "relevance_note": "PubMed result retrieved for the research question and public health context.",
        }
        execute(
            """
            INSERT INTO literature_citations
            (run_id, pmid, title, authors, journal, year, url, abstract_snippet, query_used, relevance_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, pmid, title, authors, citation["journal"], year, citation["url"], "", query, citation["relevance_note"], now_iso()),
        )
        citations.append(citation)
    log_action(run_id, "literature_agent", "pubmed_search", {"query": query}, {"citations": len(citations)})
    return citations


def generate_report(run_id: str) -> dict[str, Any]:
    bundle = get_run_bundle(run_id)
    run = bundle["run"]
    lines = [
        f"# HealthLab Research Report",
        "",
        f"## Research Question",
        run["question"],
        "",
        "## Datasets",
    ]
    if bundle["pinned_datasets"]:
        for ds in bundle["pinned_datasets"]:
            lines.append(f"- **{ds['title']}** (`{ds['dataset_id']}`), {ds.get('profile', {}).get('row_count', 'unknown')} rows.")
    else:
        lines.append("- No dataset has been pinned yet.")
    if bundle["join_results"]:
        lines.extend(["", "## How The Data Was Joined"])
        for jr in bundle["join_results"]:
            lines.append(f"- {jr['explanation']}")
            if jr["duplicate_warnings"]:
                lines.append(f"  - Warnings: {'; '.join(jr['duplicate_warnings'])}")
    else:
        lines.extend(["", "## How The Data Was Joined", "No join was applied for this run. The analysis used the selected dataset directly."])
    lines.extend(["", "## Literature Review"])
    if bundle["literature"]:
        for c in bundle["literature"]:
            lines.append(f"- {c['title']} ({c.get('year') or 'n.d.'}). {c.get('journal') or 'PubMed'}. PMID: {c['pmid']}. {c['url']}")
    else:
        lines.append("No PubMed citations were retrieved for this run.")
    lines.extend(["", "## Methodology And Results"])
    if bundle["statistical_results"]:
        for s in bundle["statistical_results"]:
            lines.append(f"### {s['test_name']}")
            lines.append(f"- Variables: {', '.join(s['variables'])}")
            lines.append(f"- Assumptions: `{json.dumps(s['assumptions'], default=str)}`")
            lines.append(f"- Result: `{json.dumps(s['result'], default=str)}`")
            lines.append(f"- Interpretation: {s.get('interpretation') or 'No interpretation recorded.'}")
    else:
        lines.append("Methodology has not been run yet.")
    lines.extend(["", "## Reproducibility Log"])
    for action in bundle["actions"]:
        lines.append(f"- {action['created_at']} — **{action['agent_name']}** `{action['action_type']}`: {action.get('rationale') or 'logged action'}")
    lines.extend(["", "## Limitations", "- This is an exploratory analysis. Observational public health data does not establish causation by itself.", "- Dataset grain, missingness, and join quality should be reviewed before policy or clinical use."])
    markdown = "\n".join(lines)
    execute("INSERT INTO reports (run_id, markdown, created_at) VALUES (?, ?, ?)", (run_id, markdown, now_iso()))
    execute("UPDATE research_runs SET status=?, updated_at=? WHERE id=?", ("report_ready", now_iso(), run_id))
    return get_run_bundle(run_id) | {"report_markdown": markdown}


def create_thread(run_id: str, title: str = "Research chat") -> dict[str, Any]:
    thread_id = str(uuid.uuid4())
    execute("INSERT INTO chat_threads (id, run_id, title, created_at) VALUES (?, ?, ?, ?)", (thread_id, run_id, title, now_iso()))
    return {"id": thread_id, "run_id": run_id, "title": title}


def save_chat_message(thread_id: str, role: str, content: str) -> None:
    execute("INSERT INTO chat_messages (thread_id, role, content, created_at) VALUES (?, ?, ?, ?)", (thread_id, role, content, now_iso()))


def _pinned(run_id: str) -> list[dict[str, Any]]:
    data = rows("SELECT * FROM pinned_datasets WHERE run_id=? ORDER BY id", (run_id,))
    for item in data:
        item["soql"] = _loads(item.pop("soql_json", None), {})
        item["columns"] = _loads(item.pop("selected_columns_json", None), [])
        item["profile"] = _loads(item.pop("profile_json", None), {})
    return data


def get_run_bundle(run_id: str) -> dict[str, Any]:
    run = row("SELECT * FROM research_runs WHERE id=?", (run_id,))
    if not run:
        raise ValueError("Run not found.")
    candidates = rows("SELECT * FROM cdc_candidates WHERE run_id=? ORDER BY id", (run_id,))
    for c in candidates:
        c["columns"] = _loads(c.pop("columns_json", None), [])
        c["geo_fields"] = _loads(c.pop("geo_fields_json", None), [])
        c["date_fields"] = _loads(c.pop("date_fields_json", None), [])
        c.pop("raw_json", None)
    join_plans = rows("SELECT * FROM join_plans WHERE run_id=? ORDER BY id", (run_id,))
    for p in join_plans:
        p["keys"] = _loads(p.pop("keys_json", None), [])
        p["normalizations"] = _loads(p.pop("normalizations_json", None), [])
    join_results = rows("SELECT * FROM join_results WHERE run_id=? ORDER BY id", (run_id,))
    for jr in join_results:
        jr["unmatched_examples"] = _loads(jr.pop("unmatched_examples_json", None), [])
        jr["duplicate_warnings"] = _loads(jr.pop("duplicate_warnings_json", None), [])
    actions = rows("SELECT * FROM methodology_actions WHERE run_id=? ORDER BY id", (run_id,))
    for a in actions:
        a["input"] = _loads(a.pop("input_json", None), {})
        a["output"] = _loads(a.pop("output_json", None), {})
        a["warnings"] = _loads(a.pop("warnings_json", None), [])
    stats = rows("SELECT * FROM statistical_results WHERE run_id=? ORDER BY id", (run_id,))
    for s in stats:
        s["variables"] = _loads(s.pop("variables_json", None), [])
        s["assumptions"] = _loads(s.pop("assumptions_json", None), {})
        s["result"] = _loads(s.pop("result_json", None), {})
    latest_report = row("SELECT markdown FROM reports WHERE run_id=? ORDER BY id DESC LIMIT 1", (run_id,))
    return {
        "run": run,
        "candidates": candidates,
        "pinned_datasets": _pinned(run_id),
        "join_plans": join_plans,
        "join_results": join_results,
        "actions": actions,
        "statistical_results": stats,
        "literature": rows("SELECT * FROM literature_citations WHERE run_id=? ORDER BY id", (run_id,)),
        "chat_threads": rows("SELECT * FROM chat_threads WHERE run_id=? ORDER BY created_at", (run_id,)),
        "report_markdown": latest_report["markdown"] if latest_report else "",
    }
