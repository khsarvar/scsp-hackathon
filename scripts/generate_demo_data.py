#!/usr/bin/env python3
"""Generate demo asthma ER visits dataset for HealthLab Agent."""
import os
import sys
import random

import numpy as np
import pandas as pd

SEED = 42
np.random.seed(SEED)
random.seed(SEED)

COUNTIES = ["Riverside", "Los Angeles", "Fresno", "San Diego", "Kern"]
AGE_GROUPS = ["0-17", "18-44", "45-64", "65+"]

# Per-county characteristics
COUNTY_POVERTY = {
    "Riverside": 0.16,
    "Los Angeles": 0.18,
    "Fresno": 0.26,
    "San Diego": 0.13,
    "Kern": 0.24,
}
COUNTY_UNINSURED = {
    "Riverside": 0.10,
    "Los Angeles": 0.12,
    "Fresno": 0.17,
    "San Diego": 0.09,
    "Kern": 0.16,
}
COUNTY_POPULATION_BASE = {
    "Riverside": 2_500_000,
    "Los Angeles": 10_000_000,
    "Fresno": 1_000_000,
    "San Diego": 3_300_000,
    "Kern": 900_000,
}
AGE_POP_FRACTION = {"0-17": 0.22, "18-44": 0.35, "45-64": 0.25, "65+": 0.18}
AGE_ASTHMA_MULTIPLIER = {"0-17": 1.4, "18-44": 0.8, "45-64": 1.0, "65+": 1.3}

# Quarterly date range 2020-Q1 to 2023-Q4
QUARTERS = pd.period_range("2020Q1", "2023Q4", freq="Q")


def generate_aqi(county: str, quarter: pd.Period) -> float:
    """Air quality index — Kern and Fresno are worse; summer is worse."""
    base = {"Riverside": 65, "Los Angeles": 72, "Fresno": 78, "San Diego": 52, "Kern": 85}[county]
    # Summer spike (Q3)
    seasonal = 12 if quarter.quarter == 3 else (-5 if quarter.quarter in [1, 4] else 0)
    # Year trend: slight improvement
    year_adj = (2020 - quarter.year) * 2
    aqi = base + seasonal + year_adj + np.random.normal(0, 8)
    return float(np.clip(aqi, 10, 180))


def generate_asthma_visits(aqi: float, poverty: float, age_group: str, population: int) -> float:
    """Asthma ER visits per 10k population — correlated with AQI and poverty."""
    base_rate = 8.0
    aqi_effect = (aqi - 60) * 0.12
    poverty_effect = poverty * 40
    age_mult = AGE_ASTHMA_MULTIPLIER[age_group]
    noise = np.random.normal(0, 2.5)
    rate = (base_rate + aqi_effect + poverty_effect) * age_mult + noise
    rate = max(0.5, rate)
    visits = rate * population / 10_000
    return round(visits, 1)


rows = []
for quarter in QUARTERS:
    for county in COUNTIES:
        for age_group in AGE_GROUPS:
            pop_base = COUNTY_POPULATION_BASE[county]
            pop_fraction = AGE_POP_FRACTION[age_group]
            population = int(pop_base * pop_fraction * np.random.uniform(0.97, 1.03))

            aqi = generate_aqi(county, quarter)

            # Wildfire outlier: Kern county 2022-Q3
            if county == "Kern" and quarter == pd.Period("2022Q3", freq="Q"):
                aqi = 310.0

            poverty = COUNTY_POVERTY[county] + np.random.normal(0, 0.015)
            poverty = float(np.clip(poverty, 0.05, 0.45))

            uninsured = COUNTY_UNINSURED[county] + np.random.normal(0, 0.01)
            uninsured = float(np.clip(uninsured, 0.02, 0.35))

            visits = generate_asthma_visits(aqi, poverty, age_group, population)

            rows.append({
                "date": str(quarter),
                "county": county,
                "age_group": age_group,
                "population": population,
                "asthma_er_visits": visits,
                "air_quality_index": round(aqi, 1),
                "poverty_rate": round(poverty, 4),
                "uninsured_rate": round(uninsured, 4),
            })

df = pd.DataFrame(rows)

# Add 2 duplicate rows
df = pd.concat([df, df.iloc[[10, 50]]], ignore_index=True)

# Introduce missing values
n = len(df)
rng = np.random.default_rng(SEED)

# ~3.5% missing in air_quality_index
aqi_missing_idx = rng.choice(n, size=int(n * 0.035), replace=False)
df.loc[aqi_missing_idx, "air_quality_index"] = np.nan

# ~2% missing in asthma_er_visits
visits_missing_idx = rng.choice(n, size=int(n * 0.02), replace=False)
df.loc[visits_missing_idx, "asthma_er_visits"] = np.nan

# ~1.5% missing in uninsured_rate
uninsured_missing_idx = rng.choice(n, size=int(n * 0.015), replace=False)
df.loc[uninsured_missing_idx, "uninsured_rate"] = np.nan

# Shuffle
df = df.sample(frac=1, random_state=SEED).reset_index(drop=True)

out_dir = os.path.join(os.path.dirname(__file__), "..", "backend", "data")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "demo_asthma.csv")
df.to_csv(out_path, index=False)
print(f"Generated {len(df)} rows → {out_path}")
print(f"Columns: {list(df.columns)}")
print(f"Missing: {df.isnull().sum().to_dict()}")

# Also copy to frontend/public
frontend_public = os.path.join(os.path.dirname(__file__), "..", "frontend", "public")
os.makedirs(frontend_public, exist_ok=True)
import shutil
shutil.copy(out_path, os.path.join(frontend_public, "demo_asthma.csv"))
print(f"Copied to frontend/public/demo_asthma.csv")
