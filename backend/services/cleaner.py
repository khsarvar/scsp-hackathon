from typing import Any

import pandas as pd
import numpy as np


def _parse_datetimes(df: pd.DataFrame, datetime_cols: list[str]) -> tuple[pd.DataFrame, list[str]]:
    steps = []
    for col in datetime_cols:
        try:
            df[col] = pd.to_datetime(df[col], infer_format=True, errors="coerce")
            steps.append(f"Parsed '{col}' as datetime column.")
        except Exception:
            pass
    return df, steps


def _deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    n_dupes = int(df.duplicated().sum())
    if n_dupes > 0:
        df = df.drop_duplicates().reset_index(drop=True)
        return df, [f"Removed {n_dupes} duplicate row(s)."]
    return df, []


def _handle_nulls(df: pd.DataFrame, col: str, role: str) -> tuple[pd.DataFrame, list[str]]:
    missing = int(df[col].isna().sum())
    if missing == 0:
        return df, []

    steps = []
    if role == "numeric":
        median_val = pd.to_numeric(df[col], errors="coerce").median()
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(median_val)
        steps.append(
            f"Filled {missing} missing value(s) in '{col}' with column median ({round(median_val, 2)})."
        )
    else:
        df[col] = df[col].fillna("Unknown")
        steps.append(f"Filled {missing} missing value(s) in '{col}' with 'Unknown'.")

    return df, steps


def _cap_outliers(df: pd.DataFrame, col: str) -> tuple[pd.DataFrame, list[str]]:
    numeric = pd.to_numeric(df[col], errors="coerce")
    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return df, []
    lower = q1 - 3 * iqr
    upper = q3 + 3 * iqr
    capped_high = int((numeric > upper).sum())
    capped_low = int((numeric < lower).sum())
    total_capped = capped_high + capped_low
    if total_capped == 0:
        return df, []
    df[col] = numeric.clip(lower=lower, upper=upper)
    return df, [
        f"Capped {total_capped} outlier(s) in '{col}' to IQR fence "
        f"[{round(lower, 2)}, {round(upper, 2)}]."
    ]


def clean_dataframe(
    df: pd.DataFrame, profile: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    all_steps: list[str] = []

    # Step 1: Deduplicate
    df, steps = _deduplicate(df)
    all_steps.extend(steps)

    # Step 2: Parse datetime columns
    datetime_cols = [
        c["name"] for c in profile["columns"] if c["dtype_inferred"] == "datetime"
    ]
    df, steps = _parse_datetimes(df, datetime_cols)
    all_steps.extend(steps)

    # Step 3 & 4: Handle nulls, cap outliers per column
    for col_info in profile["columns"]:
        col = col_info["name"]
        role = col_info["dtype_inferred"]
        if col not in df.columns:
            continue

        df, steps = _handle_nulls(df, col, role)
        all_steps.extend(steps)

        if role == "numeric" and col_info.get("outliers"):
            df, steps = _cap_outliers(df, col)
            all_steps.extend(steps)

    if not all_steps:
        all_steps.append("No cleaning issues found — dataset looks clean.")

    return df, all_steps
