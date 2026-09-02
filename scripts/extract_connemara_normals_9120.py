#!/usr/bin/env python3
"""Extract Met Éireann 1991–2020 1 km normals for Mace Head + Connemara.

Climatological NORMALS (static long-term averages on Irish Grid TM65) — for
anomaly maps / paper climate context vs Mace monthly *actuals*.

NOT a time series and NOT for HAB week ML joins. Use clidata daily/hourly
(Mace Head 275, Belmullet 2375) for week-scale features.

Source grids (local; large IE_*.txt / *.zip gitignored):
  data/external/met_eireann/normals_9120/IE_{RR,TMEAN,TMAX,TMIN}_9120_V2.txt
Refs: Climatological Notes 22 (rainfall) / 23 (temperature).
Catalogue: https://www.met.ie/climate/available-data

Output:
  data/processed/connemara_normals_9120_extract.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
NORM = ROOT / "data" / "external" / "met_eireann" / "normals_9120"
OUT = ROOT / "data" / "processed" / "connemara_normals_9120_extract.csv"

# Point sites (lat, lon WGS84)
SITES = {
    "mace_head": (53.326, -9.901),
    "lehanagh_pool": (53.40, -9.82),
    "killary": (53.62, -9.87),
    "belmullet": (54.228, -10.007),
}

# Small Connemara coastal bbox (WGS84)
BBOX_LAT = (53.20, 53.55)
BBOX_LON = (-10.20, -9.40)

# TM65 Irish Grid (Met readmes); not TM75 (29903)
TM65 = "EPSG:29902"


def wgs84_to_tm65(lon: float, lat: float) -> tuple[float, float]:
    tr = Transformer.from_crs("EPSG:4326", TM65, always_xy=True)
    e, n = tr.transform(lon, lat)
    return float(e), float(n)


def load_grid(name: str) -> pd.DataFrame:
    path = NORM / name
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing {path} — unzip IE_*_9120_V2.zip locally under normals_9120/"
        )
    df = pd.read_csv(path, sep=r"\s+", engine="python")
    df.columns = [str(c).strip().strip('"') for c in df.columns]
    df["east"] = pd.to_numeric(df["east"], errors="coerce")
    df["north"] = pd.to_numeric(df["north"], errors="coerce")
    return df.dropna(subset=["east", "north"])


def nearest_row(df: pd.DataFrame, east: float, north: float) -> pd.Series:
    d2 = (df["east"].to_numpy(float) - east) ** 2 + (df["north"].to_numpy(float) - north) ** 2
    i = int(np.argmin(d2))
    row = df.iloc[i].copy()
    row["_dist_m"] = float(np.sqrt(d2[i]))
    return row


def bbox_tm65() -> tuple[float, float, float, float]:
    corners = [
        (BBOX_LON[0], BBOX_LAT[0]),
        (BBOX_LON[0], BBOX_LAT[1]),
        (BBOX_LON[1], BBOX_LAT[0]),
        (BBOX_LON[1], BBOX_LAT[1]),
    ]
    es, ns = zip(*(wgs84_to_tm65(lon, lat) for lon, lat in corners))
    return min(es), max(es), min(ns), max(ns)


def extract_vars(row_tmean, row_tmax, row_tmin, row_rr) -> dict:
    return {
        "tmean_june_c": float(row_tmean["m6Tmean"]),
        "tmax_june_c": float(row_tmax["m6Tmax"]),
        "tmin_june_c": float(row_tmin["m6Tmin"]),
        "tmean_jja_c": float(row_tmean["JJA"]),
        "tmean_ann_c": float(row_tmean["ANN"]),
        "tmax_jja_c": float(row_tmax["JJA"]),
        "tmax_ann_c": float(row_tmax["ANN"]),
        "tmin_jja_c": float(row_tmin["JJA"]),
        "tmin_ann_c": float(row_tmin["ANN"]),
        "rr_june_mm": float(row_rr["aar9120m6"]),
        "rr_jja_mm": float(row_rr["JJA"]),
        "rr_ann_mm": float(row_rr["ANN"]),
    }


def main() -> int:
    tmean = load_grid("IE_TMEAN_9120_V2.txt")
    tmax = load_grid("IE_TMAX_9120_V2.txt")
    tmin = load_grid("IE_TMIN_9120_V2.txt")
    rr = load_grid("IE_RR_9120_V2.txt")

    rows: list[dict] = []
    for site, (lat, lon) in SITES.items():
        e, n = wgs84_to_tm65(lon, lat)
        r_tm = nearest_row(tmean, e, n)
        r_tx = nearest_row(tmax, e, n)
        r_tn = nearest_row(tmin, e, n)
        r_rr = nearest_row(rr, e, n)
        rec = {
            "site": site,
            "agg": "nearest_cell",
            "lat": lat,
            "lon": lon,
            "tm65_east": int(r_tm["east"]),
            "tm65_north": int(r_tm["north"]),
            "dist_m": round(float(r_tm["_dist_m"]), 1),
            "n_cells": 1,
            **extract_vars(r_tm, r_tx, r_tn, r_rr),
            "note": "1991-2020 1km normals (Notes 22/23); not HAB week ML",
        }
        rows.append(rec)

    e_min, e_max, n_min, n_max = bbox_tm65()
    mask = (
        (tmean["east"] >= e_min)
        & (tmean["east"] <= e_max)
        & (tmean["north"] >= n_min)
        & (tmean["north"] <= n_max)
    )
    # Align grids on east/north for bbox stats
    keys = ["east", "north"]
    merged = (
        tmean.loc[mask, keys + ["m6Tmean", "JJA", "ANN"]]
        .rename(columns={"m6Tmean": "tmean_m6", "JJA": "tmean_jja", "ANN": "tmean_ann"})
        .merge(
            tmax.loc[mask, keys + ["m6Tmax", "JJA", "ANN"]].rename(
                columns={"m6Tmax": "tmax_m6", "JJA": "tmax_jja", "ANN": "tmax_ann"}
            ),
            on=keys,
        )
        .merge(
            tmin.loc[mask, keys + ["m6Tmin", "JJA", "ANN"]].rename(
                columns={"m6Tmin": "tmin_m6", "JJA": "tmin_jja", "ANN": "tmin_ann"}
            ),
            on=keys,
        )
        .merge(
            rr.loc[mask, keys + ["aar9120m6", "JJA", "ANN"]].rename(
                columns={"aar9120m6": "rr_m6", "JJA": "rr_jja", "ANN": "rr_ann"}
            ),
            on=keys,
        )
    )
    n_cells = int(len(merged))
    if n_cells == 0:
        raise RuntimeError(f"No cells in Connemara TM65 bbox E[{e_min:.0f},{e_max:.0f}] N[{n_min:.0f},{n_max:.0f}]")

    for agg, fn in (("bbox_mean", "mean"), ("bbox_median", "median")):
        s = getattr(merged, fn)(numeric_only=True)
        rows.append(
            {
                "site": "connemara_bbox",
                "agg": agg,
                "lat": None,
                "lon": None,
                "tm65_east": None,
                "tm65_north": None,
                "dist_m": None,
                "n_cells": n_cells,
                "tmean_june_c": round(float(s["tmean_m6"]), 3),
                "tmax_june_c": round(float(s["tmax_m6"]), 3),
                "tmin_june_c": round(float(s["tmin_m6"]), 3),
                "tmean_jja_c": round(float(s["tmean_jja"]), 3),
                "tmean_ann_c": round(float(s["tmean_ann"]), 3),
                "tmax_jja_c": round(float(s["tmax_jja"]), 3),
                "tmax_ann_c": round(float(s["tmax_ann"]), 3),
                "tmin_jja_c": round(float(s["tmin_jja"]), 3),
                "tmin_ann_c": round(float(s["tmin_ann"]), 3),
                "rr_june_mm": round(float(s["rr_m6"]), 3),
                "rr_jja_mm": round(float(s["rr_jja"]), 3),
                "rr_ann_mm": round(float(s["rr_ann"]), 3),
                "note": (
                    f"1991-2020 1km normals; WGS84 bbox lat {BBOX_LAT}, lon {BBOX_LON}; "
                    f"TM65 E[{e_min:.0f},{e_max:.0f}] N[{n_min:.0f},{n_max:.0f}]; not HAB week ML"
                ),
            }
        )

    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(out[["site", "agg", "tmean_june_c", "rr_june_mm", "tmean_jja_c", "tmean_ann_c"]].to_string(index=False))
    print(f"wrote {OUT} ({len(out)} rows, bbox_cells={n_cells})")

    mace = out[(out["site"] == "mace_head")].iloc[0]
    print(
        f"Compare: Mace June TMEAN normal={mace['tmean_june_c']:.1f}°C "
        f"vs Garry/Agmet June 2023 meant=17.0°C "
        f"(anomaly ≈ {17.0 - mace['tmean_june_c']:+.1f}°C); "
        f"June RR normal={mace['rr_june_mm']:.1f} mm vs 2023 rain=56.1 mm"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
