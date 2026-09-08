#!/usr/bin/env python3
"""Build Climate-Drivers CPR AOI × ISO-week aggregates (complements PA ingest).

Does **not** replace `scripts/ingest_cpr_mba.py` (sample parquet + canonical
`cpr_aoi_week.csv`) or `scripts/join_cpr_hab_week.py`. Writes climate-owned
outputs with climate-facing AOI names required for shelf / heatwave docs.

Usage:
  .venv/bin/python scripts/build_cpr_aoi_week.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ingest_cpr_mba import DATA_CSV, load_samples  # noqa: E402

PROC = ROOT / "data" / "processed"
SAMPLES_PQ = PROC / "cpr_samples.parquet"
OUT_CSV = PROC / "cpr_aoi_week_climate_drivers.csv"
OUT_SUMMARY = PROC / "cpr_aoi_summary_climate_drivers.json"
# Also emit task-named summary alias path used in early docs
OUT_SUMMARY_ALT = PROC / "cpr_aoi_week_summary_climate_drivers.json"

# Climate-facing AOIs (lat_min, lat_max, lon_min, lon_max).
# western_irish_shelf / connemara_nested / scotland_west / irish_sea / celtic_sea
# match PA ingest boxes so counts stay honest (western_shelf≈35, connemara=0).
# full_extract is the MBA extract bbox (all CSV samples).
CLIMATE_AOIS: dict[str, tuple[float, float, float, float]] = {
    "full_extract": (49.0, 61.0, -16.0, 0.0),
    "irish_sea": (52.5, 54.5, -6.2, -3.2),
    "celtic_sea": (49.5, 52.0, -10.5, -5.5),
    "western_irish_shelf": (52.5, 55.0, -11.5, -9.0),
    "connemara_nested": (53.1, 53.6, -10.2, -9.3),
    "scotland_west": (54.75, 60.76, -7.5, -0.83),
}

PA_AOI_MAP = {
    "irish_sea": "irish_sea",
    "celtic_sea": "celtic",
    "western_irish_shelf": "western_shelf",
    "connemara_nested": "connemara",  # PA box slightly wider; both are 0 tows
    "scotland_west": "scotland",
    "full_extract": None,
}

METRIC_SRC = {
    "Mean_Dinoflagellates": "cpr_mean_dinoflagellates",
    "Mean_Diatoms": "cpr_mean_diatoms",
    "Mean_LargeCopepods": "cpr_mean_large_copepods",
    "Mean_SmallCopepods": "cpr_mean_small_copepods",
    "PCI": "cpr_pci",
}


def _load_samples(csv_path: Path) -> pd.DataFrame:
    if SAMPLES_PQ.exists() and csv_path == DATA_CSV:
        s = pd.read_parquet(SAMPLES_PQ)
        if {"sample_id", "latitude", "longitude", "iso_year", "iso_week"}.issubset(s.columns):
            return s
    return load_samples(csv_path)


def _in_box(df: pd.DataFrame, box: tuple[float, float, float, float]) -> pd.Series:
    lat0, lat1, lon0, lon1 = box
    return (
        (df["latitude"] >= lat0)
        & (df["latitude"] <= lat1)
        & (df["longitude"] >= lon0)
        & (df["longitude"] <= lon1)
    )


def aggregate(samples: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for aoi, box in CLIMATE_AOIS.items():
        sub = samples.loc[_in_box(samples, box)].copy()
        if sub.empty:
            # still record zero-count AOIs only in summary; no week rows
            continue
        sub = sub.copy()
        sub["Mean_Copepods"] = (
            sub["cpr_mean_large_copepods"] + sub["cpr_mean_small_copepods"]
        )
        g = (
            sub.groupby(["iso_year", "iso_week"], dropna=False)
            .agg(
                week_start=("week_start", "min"),
                n_samples=("sample_id", "count"),
                Mean_Dinoflagellates=("cpr_mean_dinoflagellates", "mean"),
                Mean_Diatoms=("cpr_mean_diatoms", "mean"),
                Mean_Copepods=("Mean_Copepods", "mean"),
                Mean_LargeCopepods=("cpr_mean_large_copepods", "mean"),
                Mean_SmallCopepods=("cpr_mean_small_copepods", "mean"),
                PCI=("cpr_pci", "mean"),
            )
            .reset_index()
        )
        g.insert(0, "aoi", aoi)
        g["lat_min"], g["lat_max"], g["lon_min"], g["lon_max"] = box
        rows.append(g)
    if not rows:
        return pd.DataFrame(
            columns=[
                "aoi",
                "iso_year",
                "iso_week",
                "week_start",
                "n_samples",
                "Mean_Dinoflagellates",
                "Mean_Diatoms",
                "Mean_Copepods",
                "Mean_LargeCopepods",
                "Mean_SmallCopepods",
                "PCI",
                "lat_min",
                "lat_max",
                "lon_min",
                "lon_max",
            ]
        )
    out = pd.concat(rows, ignore_index=True)
    return out.sort_values(["aoi", "iso_year", "iso_week"]).reset_index(drop=True)


def build_summary(samples: pd.DataFrame, week: pd.DataFrame) -> dict:
    counts = {}
    for aoi, box in CLIMATE_AOIS.items():
        n = int(_in_box(samples, box).sum())
        counts[aoi] = {
            "n_samples": n,
            "n_weeks": int((week["aoi"] == aoi).sum()) if not week.empty else 0,
            "bbox": {
                "lat_min": box[0],
                "lat_max": box[1],
                "lon_min": box[2],
                "lon_max": box[3],
            },
            "maps_to_pa_aoi": PA_AOI_MAP.get(aoi),
        }
    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "role": "climate_drivers_aoi_week_support",
        "pa_ingest": "scripts/ingest_cpr_mba.py",
        "pa_canonical_week_table": "data/processed/cpr_aoi_week.csv (do not overwrite)",
        "doi": "10.17031/6a9e6f4a00142",
        "web": "https://doi.mba.ac.uk/data/3793",
        "extractor": "Pierre Hélaouët",
        "n_samples_csv": int(len(samples)),
        "year_min": int(samples["year"].min()),
        "year_max": int(samples["year"].max()),
        "join_keys": ["aoi", "iso_year", "iso_week"],
        "hab_panel_join": (
            "Filter climate AOI-week CSV to one aoi, left-join HAB panel on "
            "iso_year + iso_week. For station→AOI mapping / ablation use PA "
            "scripts/join_cpr_hab_week.py against cpr_aoi_week.csv."
        ),
        "limitations": [
            "Aggregates only — cannot validate Dinophysis spp. abundance",
            "Dinoflagellate taxon list has 0 Dinophysis entries (Ceratium-heavy)",
            "connemara_nested: 0 CPR tows",
            "western_irish_shelf: sparse (~35 tows; same box as PA western_shelf)",
            "Writes climate-owned CSV only — does not overwrite PA cpr_aoi_week.csv",
        ],
        "aoi_sample_counts": counts,
        "n_week_rows": int(len(week)),
        "outputs": {
            "climate_week_csv": str(OUT_CSV.relative_to(ROOT)),
            "climate_summary_json": str(OUT_SUMMARY.relative_to(ROOT)),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=DATA_CSV)
    ap.add_argument("--out", type=Path, default=OUT_CSV)
    ap.add_argument("--summary", type=Path, default=OUT_SUMMARY)
    args = ap.parse_args()

    if not args.csv.exists() and not SAMPLES_PQ.exists():
        raise SystemExit(f"Missing CPR inputs: {args.csv} and {SAMPLES_PQ}")

    samples = _load_samples(args.csv)
    week = aggregate(samples)
    if not week.empty and "week_start" in week.columns:
        week = week.copy()
        week["week_start"] = pd.to_datetime(week["week_start"]).dt.strftime("%Y-%m-%d")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    week.to_csv(args.out, index=False)
    summary = build_summary(samples, week if not week.empty else pd.DataFrame(columns=["aoi"]))
    payload = json.dumps(summary, indent=2) + "\n"
    args.summary.write_text(payload, encoding="utf-8")
    OUT_SUMMARY_ALT.write_text(payload, encoding="utf-8")

    print(f"Wrote {args.out} rows={len(week)}")
    print(f"Wrote {args.summary}")
    print(f"Wrote {OUT_SUMMARY_ALT}")
    print("AOI sample counts (climate names):")
    for aoi, info in summary["aoi_sample_counts"].items():
        print(
            f"  {aoi:22s} n_samples={info['n_samples']:6d}  "
            f"n_weeks={info['n_weeks']:5d}  pa={info['maps_to_pa_aoi']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
