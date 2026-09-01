#!/usr/bin/env python3
"""Recompute rich MHW from OISST daily and optionally merge IBI physics columns."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pa_marine.config import load_config
from pa_marine.mhw import mhw_for_stations


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--sst-in", default=None, help="OISST daily parquet (default paths.raw_sst)")
    p.add_argument("--ibi-in", default=None, help="Optional IBI daily parquet to merge")
    p.add_argument("--out", default=None)
    args = p.parse_args()
    cfg = load_config(args.config)
    sst_path = args.sst_in or cfg["paths"]["raw_sst"]
    sst = pd.read_parquet(sst_path)
    print(f"SST rows={len(sst)} stations={sst['location_id'].nunique()}")
    mhw = mhw_for_stations(sst, cfg)
    ibi_path = args.ibi_in or cfg["paths"].get("raw_ibi")
    if ibi_path and Path(ibi_path).exists():
        ibi = pd.read_parquet(ibi_path)
        ibi["date"] = pd.to_datetime(ibi["date"]).dt.normalize()
        mhw["date"] = pd.to_datetime(mhw["date"]).dt.normalize()
        value_cols = [
            c
            for c in ibi.columns
            if c
            not in {
                "date",
                "location_id",
                "request_lat",
                "request_lon",
                "grid_lat",
                "grid_lon",
                "pixel_id",
            }
        ]
        mhw = mhw.merge(ibi[["location_id", "date"] + value_cols], on=["location_id", "date"], how="left")
        print(f"merged IBI cols={value_cols}")
    else:
        print("no IBI file; writing rich MHW only")
    out = args.out or cfg["paths"].get("mhw_enriched", "data/processed/mhw_daily_enriched.parquet")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    mhw.to_parquet(out, index=False)
    print(f"wrote {out} n={len(mhw)} cols={len(mhw.columns)}")


if __name__ == "__main__":
    main()
