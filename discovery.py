"""CDC dataset discovery + multi-dataset workspace.

Two concerns, kept together because they're useless apart:
1. Find datasets on data.cdc.gov via the Socrata catalog API.
2. Hold multiple named DataFrames in a workspace so the agent can join/merge.

Public surface (what agent.py wires into tool schemas):
- DISCOVERY_OPS: name -> fn(workspace, **args) -> dict (tool result)
- JOIN_OPS:      name -> fn(workspace, **args) -> dict
- DISCOVERY_OPS_DOC, JOIN_OPS_DOC: prompt-injectable docs
- Workspace:     in-memory dict of named DataFrames + light metadata
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import requests

CDC_DOMAIN = "data.cdc.gov"
CATALOG_URL = "https://api.us.socrata.com/api/catalog/v1"
RESOURCE_URL = "https://{domain}/resource/{id}.json"
VIEW_URL = "https://{domain}/api/views/{id}.json"

DEFAULT_TIMEOUT = 60
DEFAULT_FETCH_LIMIT = 25000   # row cap per fetch; agent can override up to MAX
MIN_FETCH_LIMIT = 5000        # floor: never fetch fewer than this unless agent overrides explicitly with smaller for sampling
MAX_FETCH_LIMIT = 100000


# ---------- WORKSPACE ----------

@dataclass
class Workspace:
    """Holds multiple named DataFrames for the agent to operate on.

    The agent addresses datasets by short alias ('vax', 'flu_2024'), not by
    Socrata id. Aliases are assigned at fetch time and persist for the session.
    """
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    meta: dict[str, dict] = field(default_factory=dict)  # alias -> {id, name, source, fetched_at}

    def add(self, alias: str, df: pd.DataFrame, meta: dict) -> None:
        self.frames[alias] = df
        self.meta[alias] = meta

    def get(self, alias: str) -> pd.DataFrame:
        if alias not in self.frames:
            raise KeyError(f"No dataset aliased '{alias}'. Available: {list(self.frames)}")
        return self.frames[alias]

    def summary(self) -> list[dict]:
        return [
            {"alias": a, "rows": len(df), "cols": list(df.columns), **self.meta.get(a, {})}
            for a, df in self.frames.items()
        ]


# ---------- DISCOVERY (Socrata catalog) ----------

def _catalog_get(params: dict) -> dict:
    r = requests.get(CATALOG_URL, params=params, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return r.json()


def search_catalog(workspace: Workspace, query: str, limit: int = 10) -> dict:
    """Full-text search the CDC Socrata catalog. Returns ranked dataset metadata."""
    data = _catalog_get({
        "domains": CDC_DOMAIN,
        "search_context": CDC_DOMAIN,
        "q": query,
        "only": "dataset",
        "limit": min(limit, 25),
    })
    results = []
    for entry in data.get("results", []):
        r = entry.get("resource", {})
        results.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "description": (r.get("description") or "")[:500],
            "updated_at": r.get("updatedAt"),
            "row_count": r.get("rows_size"),
            "columns_field_names": r.get("columns_field_name", [])[:30],
            "categories": entry.get("classification", {}).get("categories", []),
            "tags": entry.get("classification", {}).get("tags", [])[:10],
        })
    return {"ok": True, "query": query, "n_results": len(results), "results": results}


def get_dataset_schema(workspace: Workspace, dataset_id: str) -> dict:
    """Full column schema (name, type, description) for a single dataset."""
    url = VIEW_URL.format(domain=CDC_DOMAIN, id=dataset_id)
    r = requests.get(url, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    view = r.json()
    cols = [
        {
            "field": c.get("fieldName"),
            "name": c.get("name"),
            "type": c.get("dataTypeName"),
            "description": (c.get("description") or "")[:300],
        }
        for c in view.get("columns", [])
    ]
    return {
        "ok": True,
        "id": dataset_id,
        "name": view.get("name"),
        "description": (view.get("description") or "")[:1000],
        "row_count": view.get("rowsUpdatedAt") and view.get("viewCount"),
        "columns": cols,
    }


def fetch_dataset(
    workspace: Workspace,
    dataset_id: str,
    alias: str,
    select: str | None = None,
    where: str | None = None,
    order: str | None = None,
    limit: int = DEFAULT_FETCH_LIMIT,
) -> dict:
    """Run a SoQL query against a Socrata dataset and load into the workspace as `alias`.

    select/where/order use SoQL syntax. Examples:
      select="state, year, deaths"
      where="year >= 2020 AND state = 'CA'"
      order="year DESC"
    """
    limit = min(int(limit), MAX_FETCH_LIMIT)
    params: dict[str, Any] = {"$limit": limit}
    if select: params["$select"] = select
    if where:  params["$where"] = where
    if order:  params["$order"] = order

    url = RESOURCE_URL.format(domain=CDC_DOMAIN, id=dataset_id)
    r = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list):
        return {"ok": False, "error": f"Unexpected response: {str(rows)[:200]}"}

    df = pd.DataFrame(rows)
    workspace.add(alias, df, {
        "id": dataset_id,
        "source": f"data.cdc.gov/{dataset_id}",
        "soql": {"select": select, "where": where, "order": order, "limit": limit},
    })
    return {
        "ok": True,
        "alias": alias,
        "rows": len(df),
        "columns": list(df.columns),
        "preview": df.head(3).to_dict(orient="records"),
    }


def list_workspace(workspace: Workspace) -> dict:
    return {"ok": True, "datasets": workspace.summary()}


def drop_dataset(workspace: Workspace, alias: str) -> dict:
    if alias in workspace.frames:
        del workspace.frames[alias]
        workspace.meta.pop(alias, None)
        return {"ok": True, "dropped": alias}
    return {"ok": False, "error": f"No alias '{alias}'"}


DISCOVERY_OPS = {
    "search_catalog": search_catalog,
    "get_dataset_schema": get_dataset_schema,
    "fetch_dataset": fetch_dataset,
    "list_workspace": list_workspace,
    "drop_dataset": drop_dataset,
}

DISCOVERY_OPS_DOC = """Dataset discovery ops (operate on a shared Workspace):
- search_catalog(query, limit=10)              # full-text search CDC catalog
- get_dataset_schema(dataset_id)               # column names/types/descriptions
- fetch_dataset(dataset_id, alias, select=None, where=None, order=None, limit=25000)
    # SoQL query → DataFrame stored under `alias` in the workspace
    # IMPORTANT: Socrata's server-side default is only 1000 rows. ALWAYS pass
    # an explicit `limit` of at least 25000 unless the dataset is known to be
    # small. Cap is 100000 per fetch. Use SoQL `where` to filter (year, state)
    # rather than truncating with a small limit.
- list_workspace()                             # what's currently loaded
- drop_dataset(alias)                          # free memory
"""


# ---------- MULTI-DATASET OPS (joins, concat, aggregate) ----------

def _resolve_keys(keys: str | list[str]) -> list[str]:
    return [keys] if isinstance(keys, str) else list(keys)


def merge_datasets(
    workspace: Workspace,
    left: str,
    right: str,
    on: str | list[str] | None = None,
    left_on: str | list[str] | None = None,
    right_on: str | list[str] | None = None,
    how: str = "inner",
    alias: str = "merged",
) -> dict:
    """SQL-style join. Use `on` if key columns share names, else left_on/right_on."""
    if how not in ("inner", "left", "right", "outer"):
        return {"ok": False, "error": f"Bad how={how!r}"}
    l, r = workspace.get(left), workspace.get(right)
    kwargs: dict[str, Any] = {"how": how}
    if on is not None:
        kwargs["on"] = _resolve_keys(on)
    else:
        if not (left_on and right_on):
            return {"ok": False, "error": "Provide `on` or both left_on/right_on"}
        kwargs["left_on"] = _resolve_keys(left_on)
        kwargs["right_on"] = _resolve_keys(right_on)
    try:
        out = l.merge(r, suffixes=(f"_{left}", f"_{right}"), **kwargs)
    except Exception as e:
        return {"ok": False, "error": f"Merge failed: {e}"}

    workspace.add(alias, out, {
        "source": f"merge({left}, {right}, how={how})",
        "parents": [left, right],
    })
    return {
        "ok": True, "alias": alias, "rows": len(out), "columns": list(out.columns),
        "left_only_keys_lost": int(len(l) - len(out)) if how == "inner" else None,
    }


def concat_datasets(
    workspace: Workspace,
    aliases: list[str],
    alias: str = "concat",
    add_source_col: bool = True,
) -> dict:
    """Stack datasets vertically (same shape across years/states/etc.)."""
    frames = []
    for a in aliases:
        df = workspace.get(a).copy()
        if add_source_col:
            df["_source_alias"] = a
        frames.append(df)
    out = pd.concat(frames, ignore_index=True, sort=False)
    workspace.add(alias, out, {"source": f"concat({aliases})", "parents": aliases})
    return {"ok": True, "alias": alias, "rows": len(out), "columns": list(out.columns)}


def aggregate_dataset(
    workspace: Workspace,
    source: str,
    group_by: str | list[str],
    agg: dict[str, str],   # {"deaths": "sum", "rate": "mean"}
    alias: str = "agg",
) -> dict:
    """Group + aggregate. Useful before joining datasets at different grain
    (e.g. roll county-level up to state-level before joining a state-level table)."""
    df = workspace.get(source)
    try:
        out = df.groupby(_resolve_keys(group_by), dropna=False).agg(agg).reset_index()
    except Exception as e:
        return {"ok": False, "error": f"Aggregate failed: {e}"}
    workspace.add(alias, out, {
        "source": f"agg({source} by {group_by})", "parents": [source],
    })
    return {"ok": True, "alias": alias, "rows": len(out), "columns": list(out.columns)}


def select_columns(workspace: Workspace, source: str, columns: list[str], alias: str | None = None) -> dict:
    """Project a subset of columns into a new (or same) alias."""
    df = workspace.get(source)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        return {"ok": False, "error": f"Missing columns: {missing}"}
    out = df[columns].copy()
    target = alias or source
    workspace.add(target, out, {"source": f"select({source}, {columns})", "parents": [source]})
    return {"ok": True, "alias": target, "rows": len(out), "columns": list(out.columns)}


JOIN_OPS = {
    "merge_datasets": merge_datasets,
    "concat_datasets": concat_datasets,
    "aggregate_dataset": aggregate_dataset,
    "select_columns": select_columns,
}

JOIN_OPS_DOC = """Multi-dataset ops (combine workspace datasets):
- merge_datasets(left, right, on|left_on+right_on, how='inner', alias='merged')
- concat_datasets(aliases, alias='concat', add_source_col=True)   # stack rows
- aggregate_dataset(source, group_by, agg={col: 'sum'|'mean'|...}, alias='agg')
    # use BEFORE merge_datasets when grains differ (county → state, daily → monthly)
- select_columns(source, columns, alias=None)                     # project subset

Typical multi-dataset flow:
  1. search_catalog → pick 2 datasets
  2. fetch_dataset each (alias='a', alias='b')
  3. (optional) aggregate_dataset to align grain
  4. merge_datasets on shared keys (state, year, fips, etc.)
  5. clean / hypothesize / analyze on the merged frame
"""


def apply_discovery_op(workspace: Workspace, op_spec: dict) -> dict:
    """op_spec = {'op': name, 'args': {...}}"""
    name = op_spec["op"]
    fn = DISCOVERY_OPS.get(name) or JOIN_OPS.get(name)
    if not fn:
        return {"ok": False, "error": f"Unknown op '{name}'"}
    try:
        return fn(workspace, **op_spec.get("args", {}))
    except requests.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
