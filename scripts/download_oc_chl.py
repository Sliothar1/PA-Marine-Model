#!/usr/bin/env python3
"""Download Copernicus Atlantic L4 gap-free CHL at Irish HAB station pixels.

Product OCEANCOLOUR_ATL_BGC_L4_MY_009_118 /
dataset cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D.

Tries ~/.copernicusmarine first; on auth.marine.copernicus.eu TLS failure falls
back to public CloudFerro ARCO zarr (zarr_format=2). Use --prefer-arco to skip
CMEMS when the TLS blocker is known.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from pa_marine.config import load_config
from pa_marine.oc_chl import CHL_ARCO_ZARR, download_oc_chl_for_stations


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default=None)
    p.add_argument("--panel", default=None, help="station-week panel (for station list)")
    p.add_argument("--out", default=None)
    p.add_argument("--t0", default=None)
    p.add_argument("--t1", default=None)
    p.add_argument("--max-stations", type=int, default=None)
    p.add_argument(
        "--prefer-arco",
        action="store_true",
        help="skip copernicusmarine; use CloudFerro ARCO zarr directly",
    )
    p.add_argument("--chunk-months", type=int, default=6)
    p.add_argument("--lon-max", type=float, default=None, help="filter stations longitude ≤ this")
    p.add_argument("--meta", default=None, help="optional meta JSON path")
    args = p.parse_args()

    cfg = load_config(args.config)
    panel_path = args.panel or cfg["paths"]["panel"]
    panel = pd.read_parquet(panel_path) if str(panel_path).endswith(".parquet") else pd.read_csv(panel_path)
    if args.lon_max is not None:
        panel = panel[panel["longitude"] <= args.lon_max].copy()
        print(f"filtered lon≤{args.lon_max}: stations={panel['location_id'].nunique()}", flush=True)

    out = Path(args.out or cfg["paths"].get("raw_oc_chl", "data/raw/oc_chl_daily.parquet"))
    out.parent.mkdir(parents=True, exist_ok=True)

    df = download_oc_chl_for_stations(
        panel,
        cfg,
        t0=args.t0,
        t1=args.t1,
        max_stations=args.max_stations,
        prefer_arco=args.prefer_arco,
        chunk_months=args.chunk_months,
    )
    if df.empty:
        print("OC-Chl: empty result (auth / network / mask?)", flush=True)
        return
    df.to_parquet(out, index=False)
    meta = {
        "out": str(out),
        "n_rows": int(len(df)),
        "n_stations": int(df["location_id"].nunique()),
        "date_min": str(pd.to_datetime(df["date"]).min().date()),
        "date_max": str(pd.to_datetime(df["date"]).max().date()),
        "prefer_arco": bool(args.prefer_arco),
        "arco_zarr": CHL_ARCO_ZARR,
        "t0": args.t0,
        "t1": args.t1,
        "lon_max": args.lon_max,
    }
    meta_path = Path(args.meta) if args.meta else out.with_name(out.stem + "_meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(
        f"wrote {out} n={len(df)} stations={df['location_id'].nunique()} meta={meta_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
