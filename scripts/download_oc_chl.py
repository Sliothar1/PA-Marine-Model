#!/usr/bin/env python3
"""Download Copernicus Atlantic L4 gap-free CHL at Irish HAB station pixels.

Product OCEANCOLOUR_ATL_BGC_L4_MY_009_118 /
dataset cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D.

Requires working ~/.copernicusmarine login (auth.marine.copernicus.eu reachable).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pa_marine.config import load_config
from pa_marine.oc_chl import download_oc_chl_for_stations


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default=None)
    p.add_argument("--panel", default=None, help="station-week panel (for station list)")
    p.add_argument("--out", default=None)
    p.add_argument("--t0", default=None)
    p.add_argument("--t1", default=None)
    p.add_argument("--max-stations", type=int, default=None)
    args = p.parse_args()

    cfg = load_config(args.config)
    panel_path = args.panel or cfg["paths"]["panel"]
    panel = pd.read_parquet(panel_path) if str(panel_path).endswith(".parquet") else pd.read_csv(panel_path)
    out = Path(args.out or cfg["paths"].get("raw_oc_chl", "data/raw/oc_chl_daily.parquet"))
    out.parent.mkdir(parents=True, exist_ok=True)

    df = download_oc_chl_for_stations(
        panel,
        cfg,
        t0=args.t0,
        t1=args.t1,
        max_stations=args.max_stations,
    )
    if df.empty:
        print("OC-Chl: empty result (auth / network / mask?)", flush=True)
        return
    df.to_parquet(out, index=False)
    print(f"wrote {out} n={len(df)} stations={df['location_id'].nunique()}", flush=True)


if __name__ == "__main__":
    main()
