#!/usr/bin/env python3
"""Download IBI PHY/BGC station-pixel series for Irish HAB locations."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pa_marine.config import load_config
from pa_marine.ibi import download_ibi_for_stations, download_ibi_group_for_stations


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--panel", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--t0", default=None)
    p.add_argument("--t1", default=None)
    p.add_argument("--max-stations", type=int, default=None)
    p.add_argument(
        "--groups",
        default="mlotst,rsntds,optics",
        help="Comma-separated: mlotst,rsntds,optics,so,currents (priority: MLD+light first)",
    )
    args = p.parse_args()
    cfg = load_config(args.config)
    panel_path = args.panel or cfg["paths"]["panel"]
    panel = pd.read_parquet(panel_path) if panel_path.endswith(".parquet") else pd.read_csv(panel_path)
    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    t0 = args.t0 or cfg.get("ibi", {}).get("t0", "2002-01-01")
    t1 = args.t1 or cfg.get("ibi", {}).get("t1", "2024-12-31")
    out = Path(args.out or cfg["paths"].get("raw_ibi", "data/raw/ibi_daily.parquet"))
    out.parent.mkdir(parents=True, exist_ok=True)

    merged = None
    meta = {"request_lat", "request_lon", "grid_lat", "grid_lon"}
    for g in groups:
        part_path = out.with_name(out.stem + f"_{g}" + out.suffix)
        if part_path.exists():
            print(f"reuse cached {part_path}", flush=True)
            part = pd.read_parquet(part_path)
        else:
            part = download_ibi_group_for_stations(
                panel, cfg, g, t0=t0, t1=t1, max_stations=args.max_stations
            )
            if part.empty:
                print(f"IBI[{g}]: empty", flush=True)
                continue
            part.to_parquet(part_path, index=False)
            print(f"wrote {part_path} n={len(part)}", flush=True)
        value_cols = [c for c in part.columns if c not in {"date", "location_id"} | meta]
        slim = part[["location_id", "date"] + value_cols]
        if merged is None:
            keep_meta = [c for c in sorted(meta) if c in part.columns]
            merged = part[["location_id", "date"] + keep_meta + value_cols].copy()
        else:
            merged = merged.merge(slim, on=["location_id", "date"], how="outer")
    if merged is None:
        merged = pd.DataFrame()
    merged.to_parquet(out, index=False)
    print(f"wrote {out} n={len(merged)} cols={list(merged.columns)}", flush=True)


if __name__ == "__main__":
    main()
