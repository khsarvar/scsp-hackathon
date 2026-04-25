import math
from typing import Any, Optional

import numpy as np
import pandas as pd


def _sf(val: float, ndigits: int = 4) -> float | None:
    """Safe float: round and return None for NaN/inf."""
    try:
        r = round(float(val), ndigits)
        return r if math.isfinite(r) else None
    except (TypeError, ValueError):
        return None


def compute_summary_stats(df: pd.DataFrame) -> list[dict[str, Any]]:
    stats = []
    for col in df.select_dtypes(include=[np.number]).columns:
        series = df[col].dropna()
        if len(series) == 0:
            continue
        stats.append({
            "column": col,
            "count": int(series.count()),
            "mean": _sf(series.mean()),
            "median": _sf(series.median()),
            "std": _sf(series.std()),
            "min": _sf(series.min()),
            "max": _sf(series.max()),
            "p25": _sf(series.quantile(0.25)),
            "p75": _sf(series.quantile(0.75)),
        })
    return stats


def compute_correlations(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    numeric = df.select_dtypes(include=[np.number])
    if numeric.shape[1] < 2:
        return {}
    corr = numeric.corr()
    return {
        col: {
            other: _sf(corr.loc[col, other])
            for other in corr.columns
        }
        for col in corr.index
    }


def _build_time_series(
    df: pd.DataFrame, date_col: str, numeric_cols: list[str], cat_col: Optional[str]
) -> list[dict[str, Any]]:
    """Build line chart data: aggregate numeric cols over time, optionally grouped."""
    df = df.copy()

    # Convert date column to string for JSON serialization
    if pd.api.types.is_datetime64_any_dtype(df[date_col]):
        # Group by year-month
        df["_date_str"] = df[date_col].dt.to_period("M").astype(str)
    else:
        df["_date_str"] = df[date_col].astype(str)

    if cat_col and cat_col in df.columns:
        # Pivot: one series per category value
        cats = df[cat_col].dropna().unique()[:6]  # max 6 series
        target_col = numeric_cols[0] if numeric_cols else None
        if target_col is None:
            return []
        grouped = (
            df.groupby(["_date_str", cat_col])[target_col]
            .mean()
            .reset_index()
        )
        pivoted = grouped.pivot(index="_date_str", columns=cat_col, values=target_col)
        pivoted = pivoted.fillna(0).reset_index()
        pivoted.columns = [str(c) for c in pivoted.columns]
        # Round numeric values
        for c in pivoted.columns:
            if c != "_date_str":
                pivoted[c] = pivoted[c].round(2)
        return pivoted.rename(columns={"_date_str": date_col}).to_dict("records")
    else:
        agg = {col: "mean" for col in numeric_cols if col in df.columns}
        grouped = df.groupby("_date_str").agg(agg).reset_index()
        for col in numeric_cols:
            if col in grouped.columns:
                grouped[col] = grouped[col].round(2)
        return grouped.rename(columns={"_date_str": date_col}).to_dict("records")


def _build_scatter(
    df: pd.DataFrame, x_col: str, y_col: str, label_col: Optional[str]
) -> list[dict[str, Any]]:
    subset = df[[x_col, y_col]].dropna()
    if label_col and label_col in df.columns:
        subset = df[[x_col, y_col, label_col]].dropna()
        return [
            {"x": round(float(r[x_col]), 4), "y": round(float(r[y_col]), 4), "label": str(r[label_col])}
            for _, r in subset.iterrows()
        ]
    return [
        {"x": round(float(r[x_col]), 4), "y": round(float(r[y_col]), 4)}
        for _, r in subset.iterrows()
    ]


def _build_bar_aggregation(
    df: pd.DataFrame, cat_col: str, numeric_col: str
) -> list[dict[str, Any]]:
    grouped = (
        df.groupby(cat_col)[numeric_col]
        .mean()
        .reset_index()
        .sort_values(numeric_col, ascending=False)
    )
    grouped[numeric_col] = grouped[numeric_col].round(2)
    return grouped.to_dict("records")


def build_chart_specs(
    df: pd.DataFrame, profile: dict[str, Any]
) -> list[dict[str, Any]]:
    charts = []

    cols_by_role: dict[str, list[str]] = {
        "datetime": [],
        "numeric": [],
        "categorical": [],
        "id": [],
    }
    for c in profile["columns"]:
        role = c["dtype_inferred"]
        cols_by_role.setdefault(role, []).append(c["name"])

    datetime_cols = cols_by_role["datetime"]
    numeric_cols = [c for c in cols_by_role["numeric"] if c in df.columns]
    categorical_cols = cols_by_role["categorical"]

    # Prefer health-outcome-sounding cols for primary numeric
    health_keywords = {"visit", "rate", "case", "death", "count", "index", "er_"}
    primary_numeric = sorted(
        numeric_cols,
        key=lambda c: sum(kw in c.lower() for kw in health_keywords),
        reverse=True,
    )

    # ── Chart 1: Line chart (time series) ───────────────────────────────────
    if datetime_cols and primary_numeric:
        date_col = datetime_cols[0]
        y_cols = primary_numeric[:3]
        cat_col = categorical_cols[0] if categorical_cols else None

        # Try pivoted (one series per county/group) for most meaningful view
        line_data = _build_time_series(df, date_col, y_cols, cat_col)
        if line_data:
            series_keys = [k for k in (line_data[0].keys() if line_data else []) if k != date_col]
            charts.append({
                "chart_type": "line",
                "title": f"{y_cols[0].replace('_', ' ').title()} Over Time"
                         + (f" by {cat_col.replace('_', ' ').title()}" if cat_col else ""),
                "x_key": date_col,
                "y_keys": series_keys,
                "y_key": None,
                "data": line_data,
            })

    # ── Chart 2: Bar chart (categorical breakdown) ────────────────────────
    if categorical_cols and primary_numeric:
        cat_col = categorical_cols[0]
        y_col = primary_numeric[0]
        bar_data = _build_bar_aggregation(df, cat_col, y_col)
        if bar_data:
            charts.append({
                "chart_type": "bar",
                "title": f"Mean {y_col.replace('_', ' ').title()} by {cat_col.replace('_', ' ').title()}",
                "x_key": cat_col,
                "y_keys": [y_col],
                "y_key": y_col,
                "data": bar_data,
            })

    # ── Chart 3: Scatter plot (two numeric columns) ───────────────────────
    if len(numeric_cols) >= 2:
        y_col = primary_numeric[0]
        # Pick x_col as the first numeric col that differs from y_col
        x_col = next((c for c in primary_numeric[1:] if c != y_col), None)
        if x_col is None:
            x_col = next((c for c in numeric_cols if c != y_col), None)
        if x_col and x_col != y_col:
            scatter_data = _build_scatter(df, x_col, y_col, categorical_cols[0] if categorical_cols else None)
            if scatter_data:
                charts.append({
                    "chart_type": "scatter",
                    "title": f"{x_col.replace('_', ' ').title()} vs {y_col.replace('_', ' ').title()}",
                    "x_key": x_col,
                    "y_keys": [y_col],
                    "y_key": y_col,
                    "data": scatter_data[:200],  # cap for performance
                })

    # ── Chart 4: Second bar chart (second categorical) ────────────────────
    if len(categorical_cols) >= 2 and primary_numeric:
        cat_col2 = categorical_cols[1]
        y_col = primary_numeric[0]
        bar_data2 = _build_bar_aggregation(df, cat_col2, y_col)
        if bar_data2:
            charts.append({
                "chart_type": "bar",
                "title": f"Mean {y_col.replace('_', ' ').title()} by {cat_col2.replace('_', ' ').title()}",
                "x_key": cat_col2,
                "y_keys": [y_col],
                "y_key": y_col,
                "data": bar_data2,
            })

    return charts
