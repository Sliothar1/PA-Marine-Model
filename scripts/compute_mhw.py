#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pa_marine.config import load_config
from pa_marine.mhw import mhw_for_stations
from pa_marine.sst import download_sst_for_stations


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--panel", default=None)
    p.add_argument("--sst-in", default=None, help="Existing daily SST parquet; skip download if set")
    p.add_argument("--out", default=None)
    p.add_argument("--t0", default="2002-01-01")
    p.add_argument("--t1", default="2026-08-31")
    p.add_argument("--max-stations", type=int, default=None)
    args = p.parse_args()
    cfg = load_config(args.config)
    panel_path = args.panel or cfg["paths"]["panel"]
    panel = pd.read_parquet(panel_path) if panel_path.endswith(".parquet") else pd.read_csv(panel_path)
    if args.sst_in:
        sst = pd.read_parquet(args.sst_in) if args.sst_in.endswith(".parquet") else pd.read_csv(args.sst_in)
    else:
        sst = download_sst_for_stations(panel, cfg, args.t0, args.t1, args.max_stations)
        raw = cfg["paths"]["raw_sst"]
        Path(raw).parent.mkdir(parents=True, exist_ok=True)
        sst.to_parquet(raw, index=False)
    mhw = mhw_for_stations(sst, cfg)
    out = args.out or cfg["paths"]["mhw"]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    mhw.to_parquet(out, index=False) if out.endswith(".parquet") else mhw.to_csv(out, index=False)
    print(f"wrote {out} n={len(mhw)}")


if __name__ == "__main__":
    main()
