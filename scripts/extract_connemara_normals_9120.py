#!/usr/bin/env python3
"""Extract 1991–2020 1km Met Éireann climatological normals for Connemara.

Grids are Irish Grid TM65 (Climatological Notes 22/23). NOT for HAB week ML —
context / anomaly maps vs Mace monthly actuals only.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyproj

ROOT = Path(__file__).resolve().parents[1]
NORM = ROOT / "data" / "external" / "met_eireann" / "normals_9120"
PROC = ROOT / "data" / "processed"

SITES = {
    "mace_head": (53.326, -9.901),
    "lehanagh_pool": (53.40, -9.82),
    "killary": (53.62, -9.87),
    "belmullet": (54.228, -10.007),
}


def wgs84_to_tm65(lat: float, lon: float) -> tuple[float, float]:
    t = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:29903", always_xy=True)
    e, n = t.transform(lon, lat)
    return float(e), float(n)


def load_grid(name: str) -> pd.DataFrame:
    path = NORM / name
    df = pd.read_csv(path, sep=r"\s+", engine="python")
    df.columns = [str(c).strip('"') for c in df.columns]
    df["east"] = pd.to_numeric(df["east"], errors="coerce")
    df["north"] = pd.to_numeric(df["north"], errors="coerce")
    return df.dropna(subset=["east", "north"])


def nearest_row(df: pd.DataFrame, east: float, north: float) -> pd.Series:
    d2 = (df["east"] - east) ** 2 + (df["north"] - north) ** 2
    return df.loc[d2.idxmin()]


def main() -> None:
    tmean = load_grid("IE_TMEAN_9120_V2.txt")
    tmax = load_grid("IE_TMAX_9120_V2.txt")
    tmin = load_grid("IE_TMIN_9120_V2.txt")
    rr = load_grid("IE_RR_9120_V2.txt")

    rows = []
    for site, (lat, lon) in SITES.items():
        e, n = wgs84_to_tm65(lat, lon)
        r_tmean = nearest_row(tmean, e, n)
        r_tmax = nearest_row(tmax, e, n)
        r_tmin = nearest_row(tmin, e, n)
        r_rr = nearest_row(rr, e, n)
        rows.append(
            {
                "site": site,
                "lat": lat,
                "lon": lon,
                "tm65_east": int(r_tmean["east"]),
                "tm65_north": int(r_tmean["north"]),
                "tmean_june_c": float(r_tmean["m6Tmean"]),
                "tmax_june_c": float(r_tmax["m6Tmax"]),
                "tmin_june_c": float(r_tmin["m6Tmin"]),
                "tmean_jja_c": float(r_tmean["JJA"]),
                "tmean_ann_c": float(r_tmean["ANN"]),
                "rr_june_mm": float(r_rr["aar9120m6"]),
                "rr_jja_mm": float(r_rr["JJA"]),
                "rr_ann_mm": float(r_rr["ANN"]),
                "note": "1991-2020 1km normals (Notes 22/23); not HAB week ML",
            }
        )

    out = pd.DataFrame(rows)
    PROC.mkdir(parents=True, exist_ok=True)
    csv_path = PROC / "connemara_normals_9120_extract.csv"
    out.to_csv(csv_path, index=False)
    print(out.to_string(index=False))
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()
