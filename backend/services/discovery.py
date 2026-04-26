"""Socrata dataset discovery + multi-dataset workspace.

Two concerns, kept together because they're useless apart:
1. Find datasets on any approved Socrata-hosted open-data portal via the catalog API.
2. Hold multiple named DataFrames in a workspace so the agent can join/merge.

Public surface (what agent.py wires into tool schemas):
- DISCOVERY_OPS: name -> fn(workspace, **args) -> dict (tool result)
- JOIN_OPS:      name -> fn(workspace, **args) -> dict
- DISCOVERY_OPS_DOC, JOIN_OPS_DOC: prompt-injectable docs
- Workspace:     in-memory dict of named DataFrames + light metadata
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import requests

# Curated Socrata-hosted portals. The agent can search any of these and the
# scout/discover prompts list them so the LLM picks the right host for the
# question. Add a new portal by appending one tuple here — no other code change.
# Each entry: (domain, label, category, hint).
SOCRATA_PORTALS: list[tuple[str, str, str, str]] = [
    # Federal — public health
    ("data.cdc.gov",     "CDC Open Data",        "federal-health",  "disease surveillance, vaccination, mortality, BRFSS, NHANES"),
    ("data.cms.gov",     "CMS / Medicare",       "federal-health",  "Hospital Compare, Nursing Home Compare, provider quality + utilization"),
    ("healthdata.gov",   "HHS HealthData.gov",   "federal-health",  "HHS-wide datasets: hospital capacity, Medicaid, COVID operational data"),
    # Federal — non-health
    ("data.medicare.gov","Medicare.gov",         "federal-health",  "consumer-facing Medicare quality + cost data"),
    # Cities
    ("data.cityofnewyork.us", "NYC Open Data",   "city",            "311 complaints, NYPD, taxi/Uber, MV collisions, restaurant inspections, building permits, schools"),
    ("data.cityofchicago.org","Chicago Data Portal","city",         "crime, taxi/TNP rideshare, food inspections, building violations, 311"),
    ("data.lacity.org",       "Los Angeles",     "city",            "crime, building permits, transit, code enforcement"),
    ("data.sfgov.org",        "San Francisco",   "city",            "311, crime, permits, MUNI transit, restaurant inspections"),
    ("data.seattle.gov",      "Seattle",         "city",            "police reports, building permits, transit, parks"),
    ("data.austintexas.gov",  "Austin",          "city",            "crime, building permits, traffic, animal services"),
    ("data.boston.gov",       "Boston",          "city",            "311, crime, permits, BPD field interrogations"),
    ("opendata.dc.gov",       "Washington DC",   "city",            "permits, transit, crime, public services"),
    # States
    ("data.ny.gov",      "New York State",       "state",           "education, vehicle registrations, lottery, SNAP, environmental, labor"),
    ("data.wa.gov",      "Washington State",     "state",           "education, transportation, environment, labor stats"),
    ("data.texas.gov",   "Texas",                "state",           "education, transportation, public safety, environment"),
    ("data.ca.gov",      "California",           "state",           "education, environment, labor, transportation"),
    # Energy / housing / other federal
    ("data.energy.gov",  "Department of Energy", "federal-other",   "energy production, consumption, fuel economy, emissions"),
]

SOCRATA_DOMAINS: list[str] = [p[0] for p in SOCRATA_PORTALS]
DEFAULT_DOMAIN = "data.cdc.gov"

CATALOG_URL = "https://api.us.socrata.com/api/catalog/v1"
RESOURCE_URL = "https://{domain}/resource/{id}.json"
VIEW_URL = "https://{domain}/api/views/{id}.json"

DEFAULT_TIMEOUT = 60
DEFAULT_FETCH_LIMIT = 25000   # row cap per fetch; agent can override up to MAX
MIN_FETCH_LIMIT = 5000
MAX_FETCH_LIMIT = 100000


def _portals_doc() -> str:
    """Compact prompt-injectable list grouped by category."""
    by_cat: dict[str, list[tuple[str, str, str]]] = {}
    for dom, label, cat, hint in SOCRATA_PORTALS:
        by_cat.setdefault(cat, []).append((dom, label, hint))
    lines = ["Available Socrata portals (pass any of these as `domain`):"]
    for cat in ("federal-health", "federal-other", "state", "city"):
        if cat not in by_cat:
            continue
        lines.append(f"  [{cat}]")
        for dom, label, hint in by_cat[cat]:
            lines.append(f"    - {dom}  ({label}) — {hint}")
    return "\n".join(lines)


SOCRATA_PORTALS_DOC = _portals_doc()


# ---------- WORKSPACE ----------

@dataclass
class Workspace:
    """Holds multiple named DataFrames for the agent to operate on."""
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    meta: dict[str, dict] = field(default_factory=dict)

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


def _resolve_domains(domain: str | list[str] | None) -> list[str]:
    """Accept a single domain, a list, comma string, 'all', or None → all approved."""
    if domain is None or (isinstance(domain, str) and domain.lower() in ("", "all", "*")):
        return list(SOCRATA_DOMAINS)
    if isinstance(domain, str):
        items = [d.strip() for d in domain.split(",") if d.strip()]
    else:
        items = list(domain)
    bad = [d for d in items if d not in SOCRATA_DOMAINS]
    if bad:
        raise ValueError(f"Unknown Socrata domain(s) {bad}. Allowed: {SOCRATA_DOMAINS}")
    return items


@functools.lru_cache(maxsize=256)
def _cached_catalog_search(domains_key: str, query: str, limit: int) -> dict:
    """Cached wrapper — Socrata catalog rarely changes within a session, and the
    discover loop often re-issues the same query while exploring. Process-wide cache.
    `domains_key` is a comma-joined sorted tuple of domains (cache key)."""
    params = {
        "domains": domains_key,
        "q": query,
        "only": "dataset",
        "limit": limit,
    }
    # Only set search_context when scoped to a single domain; cross-domain ranks better
    # without it.
    if "," not in domains_key:
        params["search_context"] = domains_key
    return _catalog_get(params)


@functools.lru_cache(maxsize=128)
def _cached_view_get(domain: str, dataset_id: str) -> dict:
    """Cached schema fetch keyed on (domain, dataset_id)."""
    url = VIEW_URL.format(domain=domain, id=dataset_id)
    r = requests.get(url, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return r.json()


def search_catalog(
    workspace: Workspace,
    query: str,
    limit: int = 5,
    domain: str | list[str] | None = None,
) -> dict:
    """Full-text search the Socrata catalog across one or many approved portals.

    `domain` accepts: None / 'all' (search all approved portals), a single domain
    like 'data.cdc.gov', or a comma-separated list / list of domains.
    """
    capped = min(int(limit), 25)
    domains = _resolve_domains(domain)
    domains_key = ",".join(sorted(domains))
    data = _cached_catalog_search(domains_key, query, capped)
    results = []
    for entry in data.get("results", []):
        r = entry.get("resource", {})
        meta = entry.get("metadata", {})
        results.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "domain": meta.get("domain"),
            "description": (r.get("description") or "")[:500],
            "updated_at": r.get("updatedAt"),
            "row_count": r.get("rows_size"),
            "columns_field_names": r.get("columns_field_name", [])[:30],
            "categories": entry.get("classification", {}).get("categories", []),
            "tags": entry.get("classification", {}).get("tags", [])[:10],
        })
    return {
        "ok": True,
        "query": query,
        "domains_searched": domains,
        "n_results": len(results),
        "results": results,
    }


def get_dataset_schema(
    workspace: Workspace,
    dataset_id: str,
    domain: str = DEFAULT_DOMAIN,
) -> dict:
    """Full column schema (name, type, description) for a single dataset on `domain`."""
    if domain not in SOCRATA_DOMAINS:
        return {"ok": False, "error": f"Unknown domain '{domain}'. Allowed: {SOCRATA_DOMAINS}"}
    view = _cached_view_get(domain, dataset_id)
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
        "domain": domain,
        "name": view.get("name"),
        "description": (view.get("description") or "")[:1000],
        "row_count": view.get("rowsUpdatedAt") and view.get("viewCount"),
        "columns": cols,
    }


def fetch_dataset(
    workspace: Workspace,
    dataset_id: str,
    alias: str,
    domain: str = DEFAULT_DOMAIN,
    select: str | None = None,
    where: str | None = None,
    group: str | None = None,
    having: str | None = None,
    order: str | None = None,
    limit: int = DEFAULT_FETCH_LIMIT,
) -> dict:
    """Run a SoQL query against a Socrata dataset on `domain` and load it as `alias`.

    For server-side aggregation pass `group` (a comma-separated column list) along
    with aggregate functions in `select` (e.g. select='borough, count(*) as n',
    group='borough'). Use `having` to filter on aggregates.
    """
    if domain not in SOCRATA_DOMAINS:
        return {"ok": False, "error": f"Unknown domain '{domain}'. Allowed: {SOCRATA_DOMAINS}"}
    limit = min(int(limit), MAX_FETCH_LIMIT)
    params: dict[str, Any] = {"$limit": limit}
    if select: params["$select"] = select
    if where:  params["$where"] = where
    if group:  params["$group"] = group
    if having: params["$having"] = having
    if order:  params["$order"] = order

    url = RESOURCE_URL.format(domain=domain, id=dataset_id)
    r = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list):
        return {"ok": False, "error": f"Unexpected response: {str(rows)[:200]}"}

    df = pd.DataFrame(rows)
    if len(df) == 0:
        # 0 rows usually means the `where` filter excluded everything (wrong state name,
        # year out of range, typo in a categorical value). Don't load it into the workspace
        # — return a self-correctable error so the agent can revise the filter.
        return {
            "ok": False,
            "error": (
                f"fetch_dataset returned 0 rows for {domain}/{dataset_id}. "
                "Your `where` clause likely excludes everything. Try get_dataset_schema "
                "to see real column values, then relax the filter (e.g. drop the state "
                "predicate, widen the year range, or use LIKE with % wildcards for fuzzy "
                "match, e.g. `dimension LIKE '%6 Month%'`). "
                "Note: Socrata SoQL does NOT support ILIKE — use LIKE instead."
            ),
            "alias": alias,
            "rows": 0,
            "soql": {"select": select, "where": where, "order": order, "limit": limit},
        }

    workspace.add(alias, df, {
        "id": dataset_id,
        "domain": domain,
        "source": f"{domain}/{dataset_id}",
        "soql": {
            "select": select, "where": where, "group": group, "having": having,
            "order": order, "limit": limit,
        },
    })
    return {
        "ok": True,
        "alias": alias,
        "domain": domain,
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

DISCOVERY_OPS_DOC = f"""Dataset discovery ops (operate on a shared Workspace).

{SOCRATA_PORTALS_DOC}

- search_catalog(query, limit=10, domain=None)
    # Full-text search across one or many Socrata portals.
    # `domain` accepts: None or 'all' (search ALL portals), a single domain
    # like 'data.cityofnewyork.us', or a comma-separated list. When you don't
    # know which portal owns the data, omit `domain` and let ranking pick.
    # Each result includes the `domain` field — pass it back to fetch/schema.
- get_dataset_schema(dataset_id, domain='data.cdc.gov')
    # Column names/types/descriptions. `domain` MUST match the portal that
    # owns the dataset (use the `domain` from search_catalog results).
- fetch_dataset(dataset_id, alias, domain='data.cdc.gov', select=None, where=None, group=None, having=None, order=None, limit=25000)
    # SoQL query → DataFrame stored under `alias` in the workspace.
    # IMPORTANT: Socrata's server-side default is only 1000 rows. ALWAYS pass
    # an explicit `limit` of at least 25000 unless the dataset is known to be
    # small. Cap is 100000 per fetch. Use SoQL `where` to filter (year, state)
    # rather than truncating with a small limit.
    # SERVER-SIDE AGGREGATION (use this for large datasets like FHV trips, taxi,
    # 311, crime — millions of rows):
    #   select='pulocationid, date_extract_hh(pickup_datetime) as hr, count(*) as n'
    #   group='pulocationid, date_extract_hh(pickup_datetime)'
    # Notes:
    #   * Do NOT put 'group by ...' inside the select string. Pass it as `group`.
    #   * Every non-aggregate column in `select` must also appear in `group`.
    #   * Aliases created with `as` (e.g. `as hr`) can be repeated literally in
    #     `group` ('date_extract_hh(pickup_datetime)') — group on the EXPRESSION,
    #     not the alias.
    #   * Use `having` to filter aggregates (e.g. having='count(*) > 100').
- list_workspace()                             # what's currently loaded
- drop_dataset(alias)                          # free memory
"""


# ---------- MULTI-DATASET OPS (joins, concat, aggregate) ----------

def _resolve_keys(keys):
    return [keys] if isinstance(keys, str) else list(keys)


def merge_datasets(
    workspace: Workspace,
    left: str,
    right: str,
    on=None,
    left_on=None,
    right_on=None,
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

    if len(out) == 0:
        return {
            "ok": False,
            "error": (
                f"Inner merge of `{left}` ({len(l)} rows) and `{right}` ({len(r)} rows) "
                f"on {kwargs.get('on') or (kwargs.get('left_on'), kwargs.get('right_on'))} "
                "produced 0 rows — the join keys don't overlap. Inspect a few values from "
                "each side (e.g. select_columns) to verify casing / formatting / aggregation grain."
            ),
        }

    # Cartesian-product guard: if output is far larger than both inputs, the join
    # key is likely non-unique on one or both sides (e.g. missing a season/year key).
    max_input = max(len(l), len(r))
    if len(out) > max_input * 10:
        return {
            "ok": False,
            "error": (
                f"Merge of `{left}` ({len(l)} rows) × `{right}` ({len(r)} rows) "
                f"produced {len(out)} rows — looks like a cartesian product. "
                "The join key is probably not unique on one or both sides. "
                "You are likely missing a second key column (e.g. a season or year). "
                "Add it to left_on/right_on (after normalizing the format if needed), "
                "or aggregate_dataset first to make the key unique."
            ),
        }

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
    group_by,
    agg: dict[str, str],
    alias: str = "agg",
) -> dict:
    """Group + aggregate. Useful before joining datasets at different grain."""
    df = workspace.get(source)
    try:
        out = df.groupby(_resolve_keys(group_by), dropna=False).agg(agg).reset_index()
    except Exception as e:
        # Diagnose the most common cause: numeric agg (mean/sum) on a text column.
        text_cols = {col for col, fn in agg.items() if fn in ("mean", "sum", "std", "var") and col in df.columns and df[col].dtype == object}
        hint = ""
        if text_cols:
            hint = (
                f" Columns {sorted(text_cols)} are text (dtype=object) — they cannot be "
                "aggregated with mean/sum. Either use 'count' or 'first', or convert the "
                "column to numeric first (e.g. coerce non-numeric values to NaN with a "
                "cast cleaning op)."
            )
        return {"ok": False, "error": f"Aggregate failed: {e}.{hint}"}
    workspace.add(alias, out, {
        "source": f"agg({source} by {group_by})", "parents": [source],
    })
    return {"ok": True, "alias": alias, "rows": len(out), "columns": list(out.columns)}


def select_columns(workspace: Workspace, source: str, columns: list[str], alias=None) -> dict:
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
