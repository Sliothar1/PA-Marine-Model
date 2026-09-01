#!/usr/bin/env python3
"""Extract ERA5 station wind and join 7/14-day means into Irish feature table."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pa_marine.config import load_config
from pa_marine.era5 import (
    extract_station_daily,
    join_era5_to_week_panel,
    save_station_parquet,
)


def _read(path: str) -> pd.DataFrame:
    return pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--panel", default=None, help="Station-week panel (for locations)")
    p.add_argument("--joined-in", default=None, help="Existing Irish feature table to enrich")
    p.add_argument("--station-out", default=None)
    p.add_argument("--joined-out", default=None)
    p.add_argument("--years", default=None, help="Optional year list/range to load")
    args = p.parse_args()
    cfg = load_config(args.config)
    paths = cfg["paths"]

    panel_path = args.panel or paths["panel"]
    panel = _read(panel_path)
    years = None
    if args.years:
        years = []
        for part in args.years.split(","):
            part = part.strip()
            if "-" in part and part.count("-") == 1:
                a, b = part.split("-")
                years.extend(range(int(a), int(b) + 1))
            else:
                years.append(int(part))

    wind = extract_station_daily(panel, cfg, years=years)
    if wind.empty:
        raise SystemExit("no ERA5 wind extracted — download yearly zips first")
    station_out = args.station_out or paths.get("raw_era5_stations", "data/raw/era5_wind_stations.parquet")
    save_station_parquet(wind, cfg, station_out)
    print(f"wrote {station_out} n={len(wind)} locs={wind['location_id'].nunique()}")

    joined_in = args.joined_in or paths.get("joined_ostia") or paths["joined"]
    # Prefer richest available Irish joined table
    candidates = [
        joined_in,
        paths.get("joined_ibi"),
        "data/processed/joined_features_rich_mhw.parquet",
        paths.get("joined_ostia"),
        paths["joined"],
    ]
    src = None
    for c in candidates:
        if c and Path(c).exists():
            src = c
            break
    if src is None:
        raise SystemExit("no joined feature table found")
    joined = _read(src)
    enriched = join_era5_to_week_panel(joined, wind)
    out = args.joined_out or paths.get("joined_era5", "data/processed/joined_features_era5.parquet")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    enriched.to_parquet(out, index=False)
    wind_cols = [c for c in enriched.columns if c.startswith("wind_") or c.startswith("msl")]
    print(f"wrote {out} n={len(enriched)} from {src}")
    print(f"wind feature cols ({len(wind_cols)}): {wind_cols}")


if __name__ == "__main__":
    main()
