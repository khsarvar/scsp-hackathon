"""Deterministic functions the agent calls: profile, cleaning ops, statistical tests."""

import numpy as np
import pandas as pd
from scipy import stats as sp_stats


# ---------- PROFILE ----------

def profile_df(df: pd.DataFrame) -> dict:
    cols = []
    for col in df.columns:
        s = df[col]
        cols.append({
            "column": col,
            "dtype": str(s.dtype),
            "n_missing": int(s.isna().sum()),
            "pct_missing": round(100 * float(s.isna().mean()), 2),
            "n_unique": int(s.nunique(dropna=True)),
            "sample": [str(x) for x in s.dropna().unique()[:5].tolist()],
        })
    return {"n_rows": int(len(df)), "n_cols": int(len(df.columns)), "columns": cols}


# ---------- CLEANING OPS ----------

CLEANING_OPS = {}

def _op(name):
    def deco(fn):
        CLEANING_OPS[name] = fn
        return fn
    return deco


@_op("strip_whitespace")
def strip_whitespace(df, col):
    df = df.copy()
    df[col] = df[col].astype(str).str.strip()
    return df, f"Stripped whitespace from '{col}'"

@_op("lowercase")
def lowercase(df, col):
    df = df.copy()
    df[col] = df[col].astype(str).str.lower()
    return df, f"Lowercased '{col}'"

@_op("replace_value")
def replace_value(df, col, old, new):
    df = df.copy()
    if new in (None, "", "null", "NaN", "nan"):
        df[col] = df[col].replace(old, np.nan)
    else:
        df[col] = df[col].replace(old, new)
    return df, f"Replaced {old!r} with {new!r} in '{col}'"

@_op("coerce_numeric")
def coerce_numeric(df, col):
    df = df.copy()
    before = df[col].notna().sum()
    df[col] = pd.to_numeric(df[col], errors="coerce")
    after = df[col].notna().sum()
    return df, f"Coerced '{col}' to numeric (lost {int(before - after)} values to NaN)"

@_op("parse_datetime")
def parse_datetime(df, col):
    df = df.copy()
    df[col] = pd.to_datetime(df[col], errors="coerce")
    return df, f"Parsed '{col}' as datetime"

@_op("drop_duplicates")
def drop_duplicates(df, subset=None):
    before = len(df)
    df = df.drop_duplicates(subset=subset).reset_index(drop=True)
    return df, f"Dropped {before - len(df)} duplicate rows"

@_op("drop_rows_missing")
def drop_rows_missing(df, cols):
    if isinstance(cols, str):
        cols = [cols]
    before = len(df)
    df = df.dropna(subset=cols).reset_index(drop=True)
    return df, f"Dropped {before - len(df)} rows missing values in {cols}"

@_op("impute_median")
def impute_median(df, col):
    df = df.copy()
    val = df[col].median()
    n = int(df[col].isna().sum())
    df[col] = df[col].fillna(val)
    return df, f"Imputed {n} missing values in '{col}' with median ({val})"

@_op("impute_mode")
def impute_mode(df, col):
    df = df.copy()
    mode = df[col].mode(dropna=True)
    if len(mode) == 0:
        return df, f"No mode for '{col}' — skipped"
    val = mode.iloc[0]
    n = int(df[col].isna().sum())
    df[col] = df[col].fillna(val)
    return df, f"Imputed {n} missing values in '{col}' with mode ({val!r})"

@_op("clip_outliers_iqr")
def clip_outliers_iqr(df, col):
    df = df.copy()
    q1, q3 = df[col].quantile([0.25, 0.75])
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    n = int(((df[col] < lo) | (df[col] > hi)).sum())
    df[col] = df[col].clip(lo, hi)
    return df, f"Clipped {n} outliers in '{col}' to [{lo:.2f}, {hi:.2f}]"

@_op("rename_column")
def rename_column(df, old, new):
    df = df.rename(columns={old: new})
    return df, f"Renamed '{old}' to '{new}'"


CLEANING_OPS_DOC = """Available cleaning ops (op_name(args)):
- strip_whitespace(col)
- lowercase(col)
- replace_value(col, old, new)   # use new="" to convert to NaN
- coerce_numeric(col)
- parse_datetime(col)
- drop_duplicates(subset=None)
- drop_rows_missing(cols)         # cols is a string or list
- impute_median(col)
- impute_mode(col)
- clip_outliers_iqr(col)
- rename_column(old, new)
"""


def apply_op(df, op_spec):
    """op_spec = {'op': name, 'args': {...}, 'rationale': '...'}"""
    fn = CLEANING_OPS[op_spec["op"]]
    return fn(df, **op_spec.get("args", {}))


# ---------- STATS ----------

def _interpret_p(p, alpha=0.05):
    if p < 0.001:
        return "p < 0.001 — strong evidence against the null"
    if p < alpha:
        return f"p = {p:.3f} — significant at α=0.05"
    return f"p = {p:.3f} — not significant at α=0.05"


def _shapiro_p(s):
    s = s.dropna()
    if len(s) < 3:
        return 0.0
    if len(s) > 5000:
        s = s.sample(5000, random_state=0)
    try:
        return float(sp_stats.shapiro(s)[1])
    except Exception:
        return 0.0


def two_group_numeric(df, group_col, value_col):
    """Compare a numeric outcome between exactly 2 groups. Welch's t-test → Mann-Whitney fallback."""
    groups = df[group_col].dropna().unique()
    if len(groups) != 2:
        return {"error": f"Expected 2 groups in '{group_col}', got {len(groups)}: {list(groups)[:5]}"}
    a = pd.to_numeric(df.loc[df[group_col] == groups[0], value_col], errors="coerce").dropna()
    b = pd.to_numeric(df.loc[df[group_col] == groups[1], value_col], errors="coerce").dropna()
    if len(a) < 2 or len(b) < 2:
        return {"error": f"Not enough data: n={len(a)}, {len(b)}"}

    norm_a, norm_b = _shapiro_p(a), _shapiro_p(b)
    normal = norm_a > 0.05 and norm_b > 0.05

    if normal:
        stat, p = sp_stats.ttest_ind(a, b, equal_var=False)
        test = "Welch's t-test"
    else:
        stat, p = sp_stats.mannwhitneyu(a, b, alternative="two-sided")
        test = "Mann-Whitney U (normality violated)"

    pooled_var = ((len(a) - 1) * a.var() + (len(b) - 1) * b.var()) / max(len(a) + len(b) - 2, 1)
    cohen_d = float((a.mean() - b.mean()) / np.sqrt(pooled_var)) if pooled_var > 0 else 0.0

    return {
        "test": test,
        "groups": [str(groups[0]), str(groups[1])],
        "n": [int(len(a)), int(len(b))],
        "means": [float(a.mean()), float(b.mean())],
        "statistic": float(stat),
        "p_value": float(p),
        "cohens_d": cohen_d,
        "interpretation": _interpret_p(p),
        "assumption_check": {
            "normality_p": [norm_a, norm_b],
            "normality_satisfied": normal,
        },
    }


def multi_group_numeric(df, group_col, value_col):
    """Compare a numeric outcome across 3+ groups. ANOVA → Kruskal-Wallis fallback."""
    groups = df[group_col].dropna().unique()
    if len(groups) < 2:
        return {"error": "Need ≥2 groups"}
    samples = [pd.to_numeric(df.loc[df[group_col] == g, value_col], errors="coerce").dropna() for g in groups]
    if any(len(s) < 2 for s in samples):
        return {"error": f"Some groups have <2 observations: {[len(s) for s in samples]}"}

    norms = [_shapiro_p(s) for s in samples]
    normal = all(p > 0.05 for p in norms)

    if normal:
        stat, p = sp_stats.f_oneway(*samples)
        test = "One-way ANOVA"
    else:
        stat, p = sp_stats.kruskal(*samples)
        test = "Kruskal-Wallis (normality violated)"

    return {
        "test": test,
        "groups": [str(g) for g in groups],
        "n": [int(len(s)) for s in samples],
        "means": [float(s.mean()) for s in samples],
        "statistic": float(stat),
        "p_value": float(p),
        "interpretation": _interpret_p(p),
        "assumption_check": {"normality_p": norms, "normality_satisfied": normal},
    }


def two_categorical(df, col1, col2):
    """Test association between two categorical columns. Chi-square → Fisher's exact for sparse 2x2."""
    ct = pd.crosstab(df[col1], df[col2])
    if ct.size == 0:
        return {"error": "Empty contingency table"}
    chi2, p, dof, expected = sp_stats.chi2_contingency(ct)
    if ct.shape == (2, 2) and (expected < 5).any():
        _, p = sp_stats.fisher_exact(ct.values)
        test = "Fisher's exact (sparse 2x2)"
        statistic = None
    else:
        test = "Chi-square"
        statistic = float(chi2)

    return {
        "test": test,
        "contingency": ct.to_dict(),
        "statistic": statistic,
        "dof": int(dof),
        "p_value": float(p),
        "interpretation": _interpret_p(p),
    }


def correlation(df, col1, col2):
    """Correlation between two numeric columns. Pearson → Spearman if non-normal."""
    a = df[[col1, col2]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(a) < 3:
        return {"error": f"Not enough complete pairs: n={len(a)}"}
    norm1, norm2 = _shapiro_p(a[col1]), _shapiro_p(a[col2])
    normal = norm1 > 0.05 and norm2 > 0.05
    if normal:
        r, p = sp_stats.pearsonr(a[col1], a[col2])
        test = "Pearson"
    else:
        r, p = sp_stats.spearmanr(a[col1], a[col2])
        test = "Spearman (non-normal)"
    return {
        "test": test,
        "n": int(len(a)),
        "correlation": float(r),
        "p_value": float(p),
        "interpretation": _interpret_p(p),
        "assumption_check": {"normality_p": [norm1, norm2], "normality_satisfied": normal},
    }


STATS_TESTS = {
    "two_group_numeric": two_group_numeric,
    "multi_group_numeric": multi_group_numeric,
    "two_categorical": two_categorical,
    "correlation": correlation,
}

STATS_TESTS_DOC = """Available statistical tests (test_name(args)):
- two_group_numeric(group_col, value_col)        # exactly 2 groups, numeric outcome
- multi_group_numeric(group_col, value_col)      # 3+ groups, numeric outcome
- two_categorical(col1, col2)                    # association between 2 categorical cols
- correlation(col1, col2)                        # 2 numeric cols
Each test auto-checks assumptions (normality where relevant) and falls back to non-parametric.
"""
