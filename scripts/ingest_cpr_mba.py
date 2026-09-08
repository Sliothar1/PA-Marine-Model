#!/usr/bin/env python3
"""Ingest MBA Continuous Plankton Recorder (CPR) IrishHeatwaves extract.

Source: Pierre Hélaouët extraction (DOI 10.17031/6a9e6f4a00142), ~41884 samples
1982–2022 with aggregate mean abundances (large/small copepods, diatoms,
dinoflagellates) + PCI. Not taxon-resolved Dinophysis — dino list is Ceratium-heavy.

Outputs:
  data/processed/cpr_samples.parquet
  data/processed/cpr_aoi_week.csv
  data/processed/cpr_ingest_summary.json
  data/processed/figures/CPR_IrishHeatwaves_ControlMap_04092026.png
  docs/climate_assets/CPR_IrishHeatwaves_ControlMap_04092026.png
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "external" / "cpr_mba"
RAW = EXT / "raw"
PROC = ROOT / "data" / "processed"
FIG = PROC / "figures"

DATA_CSV = RAW / "CPR_IrishHeatwaves_Data_04092026.csv"
MAP_CANDIDATES = [
    EXT / "CPR_IrishHeatwaves_ControlMap_04092026.png",
    RAW / "CPR_IrishHeatwaves_ControlMap_04092026.png",
]
TAXA_FILES = {
    "large_copepods": RAW / "CPR_IrishHeatwaves_List_LargeCopepods_04092026.csv",
    "small_copepods": RAW / "CPR_IrishHeatwaves_List_SmallCopepods_04092026.csv",
    "diatoms": RAW / "CPR_IrishHeatwaves_List_Diatoms_04092026.csv",
    "dinoflagellates": RAW / "CPR_IrishHeatwaves_List_Dinoflagellates_04092026.csv",
}

DOI = "10.17031/6a9e6f4a00142"
DOI_URL = "https://doi.mba.ac.uk/data/3793"

# (lat_min, lat_max, lon_min, lon_max)
AOIS: dict[str, tuple[float, float, float, float]] = {
    "western_shelf": (52.5, 55.0, -11.5, -9.0),
    "celtic": (49.5, 52.0, -10.5, -5.5),
    "irish_sea": (52.5, 54.5, -6.2, -3.2),
    "shelf_break": (51.0, 55.0, -15.0, -11.5),
    "malin": (54.5, 55.8, -8.0, -4.5),
    "scotland": (54.75, 60.76, -7.5, -0.83),
    "connemara": (53.2, 53.7, -10.2, -9.4),  # nested; expected 0 tows
    "total_box": (49.5, 60.76, -15.0, -0.83),
}


def _in_box(lat: np.ndarray, lon: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    lat0, lat1, lon0, lon1 = box
    return (lat >= lat0) & (lat <= lat1) & (lon >= lon0) & (lon <= lon1)


def load_samples(path: Path = DATA_CSV) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing CPR data CSV: {path}")
    df = pd.read_csv(path)
    need = [
        "SampleId",
        "Latitude",
        "Longitude",
        "Year",
        "Month",
        "Day",
        "Hour",
        "Minute",
        "Mean_LargeCopepods",
        "Mean_SmallCopepods",
        "Mean_Diatoms",
        "Mean_Dinoflagellates",
        "PCI",
    ]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"CPR CSV missing columns: {missing}")

    for c in [
        "Mean_LargeCopepods",
        "Mean_SmallCopepods",
        "Mean_Diatoms",
        "Mean_Dinoflagellates",
        "PCI",
        "Latitude",
        "Longitude",
        "Year",
        "Month",
        "Day",
        "Hour",
        "Minute",
    ]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Time is UTC per MBA README
    df["sample_time_utc"] = pd.to_datetime(
        {
            "year": df["Year"].astype("Int64"),
            "month": df["Month"].astype("Int64"),
            "day": df["Day"].astype("Int64"),
            "hour": df["Hour"].fillna(0).astype(int),
            "minute": df["Minute"].fillna(0).astype(int),
        },
        utc=True,
        errors="coerce",
    )
    iso = df["sample_time_utc"].dt.isocalendar()
    df["iso_year"] = iso.year.astype("Int64")
    df["iso_week"] = iso.week.astype("Int64")
    df["week_start"] = (
        df["sample_time_utc"].dt.tz_localize(None)
        - pd.to_timedelta(df["sample_time_utc"].dt.weekday, unit="D")
    ).dt.normalize()

    lat = df["Latitude"].to_numpy()
    lon = df["Longitude"].to_numpy()
    for name, box in AOIS.items():
        df[f"in_{name}"] = _in_box(lat, lon, box)

    df = df.rename(
        columns={
            "SampleId": "sample_id",
            "Latitude": "latitude",
            "Longitude": "longitude",
            "Year": "year",
            "Month": "month",
            "Day": "day",
            "Hour": "hour",
            "Minute": "minute",
            "Mean_LargeCopepods": "cpr_mean_large_copepods",
            "Mean_SmallCopepods": "cpr_mean_small_copepods",
            "Mean_Diatoms": "cpr_mean_diatoms",
            "Mean_Dinoflagellates": "cpr_mean_dinoflagellates",
            "PCI": "cpr_pci",
        }
    )
    diatom = df["cpr_mean_diatoms"].to_numpy(dtype=float)
    dino = df["cpr_mean_dinoflagellates"].to_numpy(dtype=float)
    ratio = np.full(len(df), np.nan, dtype=float)
    ok = diatom > 0
    ratio[ok] = dino[ok] / diatom[ok]
    df["cpr_dino_diatom_ratio"] = ratio
    return df


def aggregate_aoi_week(samples: pd.DataFrame) -> pd.DataFrame:
    metric_cols = [
        "cpr_mean_large_copepods",
        "cpr_mean_small_copepods",
        "cpr_mean_diatoms",
        "cpr_mean_dinoflagellates",
        "cpr_pci",
        "cpr_dino_diatom_ratio",
    ]
    rows: list[pd.DataFrame] = []
    for aoi, box in AOIS.items():
        flag = f"in_{aoi}"
        sub = samples.loc[samples[flag]].copy()
        if sub.empty:
            continue
        g = (
            sub.groupby(["iso_year", "iso_week"], dropna=False)
            .agg(
                week_start=("week_start", "min"),
                n_samples=("sample_id", "count"),
                latitude_mean=("latitude", "mean"),
                longitude_mean=("longitude", "mean"),
                **{c: (c, "mean") for c in metric_cols},
            )
            .reset_index()
        )
        g.insert(0, "aoi", aoi)
        g["lat_min"], g["lat_max"], g["lon_min"], g["lon_max"] = box
        rows.append(g)
    if not rows:
        cols = [
            "aoi",
            "iso_year",
            "iso_week",
            "week_start",
            "n_samples",
            "latitude_mean",
            "longitude_mean",
            *metric_cols,
            "lat_min",
            "lat_max",
            "lon_min",
            "lon_max",
        ]
        return pd.DataFrame(columns=cols)
    out = pd.concat(rows, ignore_index=True)
    out = out.sort_values(["aoi", "iso_year", "iso_week"]).reset_index(drop=True)
    return out


def taxa_summary() -> dict:
    out: dict = {}
    for key, path in TAXA_FILES.items():
        if not path.exists():
            out[key] = {"path": str(path.relative_to(ROOT)), "exists": False}
            continue
        t = pd.read_csv(path)
        names = t["Taxon_Name"].astype(str) if "Taxon_Name" in t.columns else pd.Series(dtype=str)
        out[key] = {
            "path": str(path.relative_to(ROOT)),
            "exists": True,
            "n_taxa": int(len(t)),
            "n_ceratium": int(names.str.contains("Ceratium", case=False, na=False).sum()),
            "n_dinophysis": int(names.str.contains("Dinophysis", case=False, na=False).sum()),
            "columns": list(t.columns),
        }
    return out


def copy_control_map() -> str | None:
    FIG.mkdir(parents=True, exist_ok=True)
    assets = ROOT / "docs" / "climate_assets"
    assets.mkdir(parents=True, exist_ok=True)
    for src in MAP_CANDIDATES:
        if src.exists():
            dest = FIG / src.name
            shutil.copy2(src, dest)
            shutil.copy2(src, assets / src.name)
            # Stable short name for docs embeds
            shutil.copy2(src, assets / "cpr_irish_heatwaves_control_map.png")
            shutil.copy2(src, FIG / "cpr_irish_heatwaves_control_map.png")
            return str(dest.relative_to(ROOT))
    return None


def main() -> int:
    PROC.mkdir(parents=True, exist_ok=True)
    samples = load_samples()
    aoi_week = aggregate_aoi_week(samples)

    samples_out = PROC / "cpr_samples.parquet"
    aoi_out = PROC / "cpr_aoi_week.csv"
    summary_out = PROC / "cpr_ingest_summary.json"

    keep_cols = [
        "sample_id",
        "latitude",
        "longitude",
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "sample_time_utc",
        "iso_year",
        "iso_week",
        "week_start",
        "cpr_mean_large_copepods",
        "cpr_mean_small_copepods",
        "cpr_mean_diatoms",
        "cpr_mean_dinoflagellates",
        "cpr_pci",
        "cpr_dino_diatom_ratio",
        *[f"in_{a}" for a in AOIS],
    ]
    samples[keep_cols].to_parquet(samples_out, index=False)
    # Convenience aliases requested by pipeline consumers
    aoi_week = aoi_week.copy()
    aoi_week.insert(1, "year", aoi_week["iso_year"])
    aoi_week.insert(2, "week", aoi_week["iso_week"])
    aoi_week.insert(3, "n", aoi_week["n_samples"])
    aoi_week.to_csv(aoi_out, index=False)
    # Also keep a parquet for faster joins (gitignored)
    aoi_week.to_parquet(PROC / "cpr_aoi_week.parquet", index=False)
    map_rel = copy_control_map()

    aoi_counts = {a: int(samples[f"in_{a}"].sum()) for a in AOIS}
    taxa = taxa_summary()
    dino = taxa.get("dinoflagellates", {})

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "doi": DOI,
        "doi_url": DOI_URL,
        "extractor": "Pierre Hélaouët",
        "source_csv": str(DATA_CSV.relative_to(ROOT)),
        "n_samples": int(len(samples)),
        "year_min": int(samples["year"].min()),
        "year_max": int(samples["year"].max()),
        "iso_year_min": int(samples["iso_year"].min()),
        "iso_year_max": int(samples["iso_year"].max()),
        "columns_value": [
            "cpr_mean_large_copepods",
            "cpr_mean_small_copepods",
            "cpr_mean_diatoms",
            "cpr_mean_dinoflagellates",
            "cpr_pci",
        ],
        "note_volume": "Each CPR sample filters ~3 m3 seawater",
        "note_aggregates_only": True,
        "note_not_dinophysis": (
            "Mean_Dinoflagellates is an aggregate over routine taxa; list is Ceratium-heavy "
            "and contains 0 Dinophysis spp. Do not treat as HAB Dinophysis labels."
        ),
        "dinoflagellate_taxa_n": dino.get("n_taxa"),
        "dinoflagellate_ceratium_n": dino.get("n_ceratium"),
        "dinoflagellate_dinophysis_n": dino.get("n_dinophysis", 0),
        "aoi_sample_counts": aoi_counts,
        "connemara_nested_zero_tows": aoi_counts.get("connemara", 0) == 0,
        "n_aoi_week_rows": int(len(aoi_week)),
        "aoi_week_rows_by_aoi": {a: int((aoi_week["aoi"] == a).sum()) for a in AOIS},
        "outputs": {
            "cpr_samples_parquet": str(samples_out.relative_to(ROOT)),
            "cpr_aoi_week_csv": str(aoi_out.relative_to(ROOT)),
            "control_map_figure": map_rel,
            "summary_json": str(summary_out.relative_to(ROOT)),
        },
        "taxa_lists": taxa,
        "aoi_boxes": {
            k: {"lat_min": v[0], "lat_max": v[1], "lon_min": v[2], "lon_max": v[3]}
            for k, v in AOIS.items()
        },
    }
    summary_out.write_text(json.dumps(summary, indent=2) + "\n")

    print(f"Wrote {samples_out} rows={len(samples)}")
    print(f"Wrote {aoi_out} rows={len(aoi_week)}")
    print(f"Wrote {summary_out}")
    if map_rel:
        print(f"Copied control map -> {map_rel}")
    else:
        print("WARNING: control map PNG not found")
    print("AOI sample counts:", aoi_counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
