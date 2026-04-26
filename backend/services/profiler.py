import math
import re
from typing import Any

import numpy as np
import pandas as pd


def _safe_float(val: float, ndigits: int = 4) -> float | None:
    """Round float, returning None for NaN/inf (not JSON-serializable)."""
    try:
        result = round(float(val), ndigits)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


DATETIME_PATTERNS = [
    r"^\d{4}-\d{2}-\d{2}$",
    r"^\d{4}-\d{2}$",
    r"^\d{2}/\d{2}/\d{4}$",
    r"^\d{4}$",
    r"^\d{4}-Q[1-4]$",
]

DATETIME_KEYWORDS = {"date", "year", "month", "time", "period", "quarter", "week"}
ID_KEYWORDS = {"id", "_id", "uuid", "code", "fips", "zip"}
CATEGORICAL_KEYWORDS = {
    "county", "state", "region", "category", "group", "type", "sex",
    "gender", "race", "ethnicity", "age_group", "class", "status",
}


def infer_column_role(col_name: str, series: pd.Series) -> str:
    name_lower = col_name.lower()

    # Check ID-like
    for kw in ID_KEYWORDS:
        if kw in name_lower:
            return "id"

    # Check datetime by name
    for kw in DATETIME_KEYWORDS:
        if kw in name_lower:
            return "datetime"

    # Check datetime by value patterns
    non_null = series.dropna().astype(str)
    if len(non_null) > 0:
        sample = non_null.head(20)
        pattern_matches = sum(
            any(re.match(p, v) for p in DATETIME_PATTERNS) for v in sample
        )
        if pattern_matches / len(sample) > 0.7:
            return "datetime"

    # Check categorical by name
    for kw in CATEGORICAL_KEYWORDS:
        if kw in name_lower:
            return "categorical"

    # Check numeric
    if pd.api.types.is_numeric_dtype(series):
        # Low cardinality numeric → could be categorical but keep as numeric
        return "numeric"

    # String with low cardinality
    if series.nunique() <= 20:
        return "categorical"

    return "categorical"


def detect_outliers_iqr(series: pd.Series) -> list[dict[str, Any]]:
    numeric = series.dropna()
    if len(numeric) < 4:
        return []
    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return []
    lower = q1 - 3 * iqr
    upper = q3 + 3 * iqr
    outlier_mask = (numeric < lower) | (numeric > upper)
    outliers = numeric[outlier_mask]
    return [
        {"row_index": int(idx), "value": float(val), "method": "IQR"}
        for idx, val in outliers.items()
    ][:10]  # cap at 10


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    try:
        duplicate_rows = int(df.duplicated().sum())
    except TypeError:
        # columns with unhashable types (e.g. dicts) can't be hashed for dedup
        duplicate_rows = 0
    columns = []

    for col in df.columns:
        series = df[col]
        role = infer_column_role(col, series)

        missing_count = int(series.isna().sum())
        missing_pct = round(missing_count / len(series) * 100, 2) if len(series) > 0 else 0.0
        unique_count = int(series.nunique())
        sample_values = series.dropna().unique().tolist()[:5]

        col_profile: dict[str, Any] = {
            "name": col,
            "dtype_inferred": role,
            "missing_count": missing_count,
            "missing_pct": missing_pct,
            "unique_count": unique_count,
            "sample_values": [str(v) for v in sample_values],
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
            "is_datetime_like": role == "datetime",
            "is_categorical": role == "categorical",
            "outliers": [],
        }

        if role == "numeric":
            numeric_series = pd.to_numeric(series, errors="coerce").dropna()
            if len(numeric_series) > 0:
                col_profile["min"] = _safe_float(numeric_series.min())
                col_profile["max"] = _safe_float(numeric_series.max())
                col_profile["mean"] = _safe_float(numeric_series.mean())
                col_profile["std"] = _safe_float(numeric_series.std())
                col_profile["outliers"] = detect_outliers_iqr(numeric_series)

        columns.append(col_profile)

    return {
        "row_count": len(df),
        "col_count": len(df.columns),
        "duplicate_rows": duplicate_rows,
        "columns": columns,
    }
