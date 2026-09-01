"""Scotland SMC annual sanitary shellfish classifications.

This is NOT phytoplankton / HAB / biotoxin monitoring. Food Standards Scotland
(Scotland official control) publishes annual A/B/C sanitary classifications
by production area (SIN). HAB labels for Scotland still need a separate SMC
phytoplankton / toxin export.

Expected raw CSV columns (as provided 2026-09-01):
AreaName, SpeciesCommonName, LocalAuthorityName, OverallCategory,
OverallStartDate, OverallEndDate, Decision, ConfidenceLevel, Type, Status, Sin
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED_COLS = [
    "AreaName",
    "SpeciesCommonName",
    "LocalAuthorityName",
    "OverallCategory",
    "OverallStartDate",
    "OverallEndDate",
    "Decision",
    "ConfidenceLevel",
    "Type",
    "Status",
    "Sin",
]

DATE_COLS = ["OverallStartDate", "OverallEndDate"]


def load_smc_classifications(path: str | Path) -> pd.DataFrame:
    """Load annual sanitary classification CSV; parse date columns day-first."""
    path = Path(path)
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"SMC classifications missing columns: {missing}")
    out = df[REQUIRED_COLS].copy()
    for c in DATE_COLS:
        out[c] = pd.to_datetime(out[c], dayfirst=True, errors="coerce")
    return out


def unique_areas(df: pd.DataFrame) -> pd.DataFrame:
    """Unique (AreaName, Sin, LocalAuthorityName) lookup, sorted."""
    cols = ["AreaName", "Sin", "LocalAuthorityName"]
    return (
        df[cols]
        .drop_duplicates()
        .sort_values(["LocalAuthorityName", "AreaName", "Sin"])
        .reset_index(drop=True)
    )


def write_area_lookup(
    classifications_path: str | Path,
    out_path: str | Path,
) -> pd.DataFrame:
    """Load classifications and write data/processed/smc_areas.csv."""
    areas = unique_areas(load_smc_classifications(classifications_path))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    areas.to_csv(out_path, index=False)
    return areas
