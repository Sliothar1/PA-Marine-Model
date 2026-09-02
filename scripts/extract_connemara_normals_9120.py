#!/usr/bin/env python3
"""Extract Met Éireann 1991–2020 1 km normals for Mace Head + Connemara.

Climatological NORMALS (long-term averages on Irish Grid TM65) — for anomaly
maps / paper climate context vs Mace monthly actuals. NOT a time series for
HAB week ML joins (use clidata daily/hourly week panel instead).

Source grids (local; large *.txt/*.zip gitignored):
  data/external/met_eireann/normals_9120/IE_{RR,TMEAN,TMAX,TMIN}_9120_V2.txt
Refs: Climatological Notes 22 (rainfall) / 23 (temperature).
Catalogue: https://www.met.ie/climate/available-data

Output:
  data/processed/connemara_normals_9120_extract.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
NORMALS = ROOT / "data" / "external" / "met_eireann" / "normals_9120"
OUT = ROOT / "data" / "processed" / "connemara_normals_9120_extract.csv"

# Point sites (WGS84) — nearest 1 km TM65 cell
SITES = {
    "mace_head": (53.326, -9.901),
    "lehanagh_pool": (53.40, -9.82),
    "killary": (53.62, -9.87),
    "belmullet": (54.228, -10.007),
}

# Small Connemara coastal bbox (WGS84) for mean/median over land cells
BBOX_LAT = (53.20, 53.55)
BBOX_LON = (-10.20, -9.40)

# TM65 Irish Grid (EPSG:29902) — matches Readme_9120.txt
_TO_TM65 = Transformer.from_crs("EPSG:4326", "EPSG:29902", always_xy=True)

GRIDS = {
    "RR": ("IE_RR_9120_V2.txt", {"m6": "aar9120m6", "JJA": "JJA", "ANN": "ANN"}, "mm"),
    "TMEAN": ("IE_TMEAN_9120_V2.txt", {"m6": "m6Tmean", "JJA": "JJA", "ANN": "ANN"}, "degC"),
    "TMAX": ("IE_TMAX_9120_V2.txt", {"m6": "m6Tmax", "JJA": "JJA", "ANN": "ANN"}, "degC"),
    "TMIN": ("IE_TMIN_9120_V2.txt", {"m6": "m6Tmin", "JJA": "JJA", "ANN": "ANN"}, "degC"),
}


def wgs84_to_tm65(lat: float, lon: float) -> tuple[float, float]:
    e, n = _TO_TM65.transform(lon, lat)
    return float(e), float(n)


def load_grid(name: str) -> pd.DataFrame:
    path = NORMALS / name
    if not path.is_file():
        raise FileNotFoundError(f"Missing normals grid: {path}")
    df = pd.read_csv(path, sep=r"\s+", engine="python")
    df.columns = [str(c).strip().strip('"') for c in df.columns]
    df["east"] = pd.to_numeric(df["east"], errors="coerce")
    df["north"] = pd.to_numeric(df["north"], errors="coerce")
    return df.dropna(subset=["east", "north"])


def nearest_row(df: pd.DataFrame, east: float, north: float) -> tuple[pd.Series, float]:
    d2 = (df["east"].to_numpy(float) - east) ** 2 + (df["north"].to_numpy(float) - north) ** 2
    i = int(np.argmin(d2))
    return df.iloc[i], float(np.sqrt(d2[i]))


def bbox_tm65() -> tuple[float, float, float, float]:
    corners = [
        (BBOX_LON[0], BBOX_LAT[0]),
        (BBOX_LON[0], BBOX_LAT[1]),
        (BBOX_LON[1], BBOX_LAT[0]),
        (BBOX_LON[1], BBOX_LAT[1]),
    ]
    es, ns = zip(*(wgs84_to_tm65(lat, lon) for lon, lat in corners))
    return min(es), max(es), min(ns), max(ns)


def main() -> int:
    e_min, e_max, n_min, n_max = bbox_tm65()
    records: list[dict] = []

    for var, (fname, cols, unit) in GRIDS.items():
        print(f"Reading {fname} …", flush=True)
        df = load_grid(fname)
        missing = [c for c in cols.values() if c not in df.columns]
        if missing:
            raise ValueError(f"{fname}: missing {missing}")

        for site, (lat, lon) in SITES.items():
            e, n = wgs84_to_tm65(lat, lon)
            row, dist = nearest_row(df, e, n)
            for period, col in cols.items():
                records.append(
                    {
                        "site": site,
                        "variable": var,
                        "period": period,
                        "value": float(row[col]),
                        "unit": unit,
                        "agg": "nearest_cell",
                        "east": int(row["east"]),
                        "north": int(row["north"]),
                        "dist_m": round(dist, 1),
                        "lat_ref": lat,
                        "lon_ref": lon,
                        "n_cells": 1,
                        "source_file": fname,
                    }
                )

        mask = (
            (df["east"] >= e_min)
            & (df["east"] <= e_max)
            & (df["north"] >= n_min)
            & (df["north"] <= n_max)
        )
        sub = df.loc[mask]
        n_cells = int(len(sub))
        if n_cells == 0:
            raise RuntimeError(f"No cells in Connemara bbox for {var}")
        for period, col in cols.items():
            vals = sub[col].astype(float)
            for agg, fn in (("bbox_mean", vals.mean), ("bbox_median", vals.median)):
                records.append(
                    {
                        "site": "connemara_bbox",
                        "variable": var,
                        "period": period,
                        "value": round(float(fn()), 3),
                        "unit": unit,
                        "agg": agg,
                        "east": None,
                        "north": None,
                        "dist_m": None,
                        "lat_ref": None,
                        "lon_ref": None,
                        "n_cells": n_cells,
                        "source_file": fname,
                    }
                )
        print(f"  {var}: bbox cells={n_cells}", flush=True)

    out = pd.DataFrame.from_records(records)
    out = out.sort_values(["site", "variable", "period", "agg"]).reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"Wrote {OUT} ({len(out)} rows)", flush=True)

    mace_june = out[
        (out["site"] == "mace_head")
        & (out["variable"] == "TMEAN")
        & (out["period"] == "m6")
        & (out["agg"] == "nearest_cell")
    ]
    if not mace_june.empty:
        normal = float(mace_june.iloc[0]["value"])
        print(
            f"Compare: Mace June TMEAN normal={normal:.1f}°C "
            f"vs Garry Mace June 2023 meant=17.0°C "
            f"(anomaly ≈ {17.0 - normal:+.1f}°C)",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
