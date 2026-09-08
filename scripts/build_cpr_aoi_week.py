#!/usr/bin/env python3
"""Build MBA CPR AOI × ISO-week aggregates for Climate Drivers support.

Complements PA ingest (`scripts/ingest_cpr_mba.py`) — does **not** replace sample
parquet ingest, taxon QC, HAB joins, or ablation.

Writes:
  data/processed/cpr_aoi_week.csv
  data/processed/cpr_aoi_summary.json

Usage:
  .venv/bin/python scripts/build_cpr_aoi_week.py
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = (
    ROOT / "data" / "external" / "cpr_mba" / "raw" / "CPR_IrishHeatwaves_Data_04092026.csv"
)
OUT_CSV = ROOT / "data" / "processed" / "cpr_aoi_week.csv"
OUT_SUMMARY = ROOT / "data" / "processed" / "cpr_aoi_summary.json"

AOIS: dict[str, dict[str, float | str]] = {
    "full_extract": {
        "lat_min": 49.0, "lat_max": 61.0, "lon_min": -16.0, "lon_max": 0.0,
        "note": "MBA extract bbox (49–61N, −16–0E); all samples in the CSV",
    },
    "connemara_nested": {
        "lat_min": 53.1, "lat_max": 53.6, "lon_min": -10.2, "lon_max": -9.3,
        "note": "Connemara nested farm/HAB box — expected 0 CPR tows",
    },
    "western_irish_shelf": {
        "lat_min": 52.5, "lat_max": 55.0, "lon_min": -11.5, "lon_max": -9.0,
        "note": "Western Irish shelf coastal strip; sparse (~35 tows)",
    },
    "irish_sea": {
        "lat_min": 52.5, "lat_max": 54.5, "lon_min": -6.2, "lon_max": -3.2,
        "note": "Irish Sea — good CPR coverage",
    },
    "celtic_sea": {
        "lat_min": 49.5, "lat_max": 52.0, "lon_min": -10.5, "lon_max": -5.5,
        "note": "Celtic Sea — good CPR coverage",
    },
    "scotland_west": {
        "lat_min": 54.75, "lat_max": 60.76, "lon_min": -7.5, "lon_max": -0.83,
        "note": "West / NW Scotland approaches — better coverage than west Ireland coast",
    },
}

GROUP_COLS = [
    "Mean_LargeCopepods", "Mean_SmallCopepods", "Mean_Diatoms",
    "Mean_Dinoflagellates", "PCI",
]


def _in_aoi(df: pd.DataFrame, box: dict) -> pd.Series:
    return (
        (df["Latitude"] >= box["lat_min"]) & (df["Latitude"] <= box["lat_max"])
        & (df["Longitude"] >= box["lon_min"]) & (df["Longitude"] <= box["lon_max"])
    )


def load_cpr(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = {"SampleId", "Latitude", "Longitude", "Year", "Month", "Day", *GROUP_COLS} - set(df.columns)
    if missing:
        raise ValueError(f"CPR CSV missing columns: {sorted(missing)}")
    df = df.copy()
    for c in GROUP_COLS + ["Latitude", "Longitude", "Year", "Month", "Day"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["sample_date"] = pd.to_datetime(
        dict(year=df["Year"], month=df["Month"], day=df["Day"]), errors="coerce"
    )
    iso = df["sample_date"].dt.isocalendar()
    df["iso_year"] = iso.year.astype(int)
    df["iso_week"] = iso.week.astype(int)
    df["week_start"] = df["sample_date"] - pd.to_timedelta(df["sample_date"].dt.weekday, unit="D")
    df["Mean_Copepods"] = df["Mean_LargeCopepods"] + df["Mean_SmallCopepods"]
    return df


def aggregate_aoi(df: pd.DataFrame, aoi: str, box: dict) -> pd.DataFrame:
    cols = [
        "aoi", "iso_year", "iso_week", "week_start", "n_samples",
        "Mean_Dinoflagellates", "Mean_Diatoms", "Mean_Copepods",
        "Mean_LargeCopepods", "Mean_SmallCopepods", "PCI",
        "lat_min", "lat_max", "lon_min", "lon_max",
    ]
    sub = df.loc[_in_aoi(df, box)].copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    agg = (
        sub.groupby(["iso_year", "iso_week"], as_index=False)
        .agg(
            week_start=("week_start", "min"),
            n_samples=("SampleId", "count"),
            Mean_Dinoflagellates=("Mean_Dinoflagellates", "mean"),
            Mean_Diatoms=("Mean_Diatoms", "mean"),
            Mean_Copepods=("Mean_Copepods", "mean"),
            Mean_LargeCopepods=("Mean_LargeCopepods", "mean"),
            Mean_SmallCopepods=("Mean_SmallCopepods", "mean"),
            PCI=("PCI", "mean"),
        )
        .sort_values(["iso_year", "iso_week"])
    )
    agg.insert(0, "aoi", aoi)
    for k in ("lat_min", "lat_max", "lon_min", "lon_max"):
        agg[k] = box[k]
    return agg[cols]


def build_summary(df: pd.DataFrame, week: pd.DataFrame) -> dict:
    aoi_counts = {}
    for aoi, box in AOIS.items():
        n = int(_in_aoi(df, box).sum())
        aoi_counts[aoi] = {
            "n_samples": n,
            "n_weeks": int((week["aoi"] == aoi).sum()) if not week.empty else 0,
            "bbox": {k: box[k] for k in ("lat_min", "lat_max", "lon_min", "lon_max")},
            "note": box.get("note", ""),
        }
    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "role": "climate_drivers_aoi_week_support",
        "complements_pa_ingest": "scripts/ingest_cpr_mba.py",
        "source_csv": str(DEFAULT_CSV.relative_to(ROOT)),
        "doi": "10.17031/6a9e6f4a00142",
        "web": "https://doi.mba.ac.uk/data/3793",
        "extractor": "Pierre Hélaouët",
        "n_samples_csv": int(len(df)),
        "year_min": int(df["Year"].min()),
        "year_max": int(df["Year"].max()),
        "group_columns": GROUP_COLS + ["Mean_Copepods (= Large + Small per sample)"],
        "join_keys": ["aoi", "iso_year", "iso_week"],
        "hab_panel_join": (
            "Filter cpr_aoi_week to one aoi (celtic_sea / irish_sea / scotland_west — "
            "not connemara_nested), then left-join HAB week panel on iso_year + iso_week."
        ),
        "limitations": [
            "Aggregates only — no species-level Dinophysis",
            "Dinophysis spp. absent from accompanying dinoflagellate taxon list",
            "connemara_nested has 0 CPR tows",
            "western_irish_shelf sparse (~35 tows)",
            "AOI-week covariates only — not a Met Éireann or NAO/EA/AMO replacement",
            "Heavy CPR ingest left to PA (scripts/ingest_cpr_mba.py)",
        ],
        "aoi_sample_counts": aoi_counts,
        "n_week_rows": int(len(week)),
        "outputs": {
            "cpr_aoi_week_csv": str(OUT_CSV.relative_to(ROOT)),
            "cpr_aoi_summary_json": str(OUT_SUMMARY.relative_to(ROOT)),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--out", type=Path, default=OUT_CSV)
    ap.add_argument("--summary", type=Path, default=OUT_SUMMARY)
    args = ap.parse_args()
    if not args.csv.exists():
        raise SystemExit(f"Missing CPR CSV: {args.csv}")
    df = load_cpr(args.csv)
    parts = [aggregate_aoi(df, aoi, box) for aoi, box in AOIS.items()]
    week = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not week.empty:
        week["week_start"] = pd.to_datetime(week["week_start"]).dt.strftime("%Y-%m-%d")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    week.to_csv(args.out, index=False)
    summary = build_summary(df, week)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} rows={len(week)}")
    print(f"Wrote {args.summary}")
    print("AOI sample counts:")
    for aoi, info in summary["aoi_sample_counts"].items():
        print(f"  {aoi:22s} n_samples={info['n_samples']:6d}  n_weeks={info['n_weeks']:5d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
