#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pa_marine.config import load_config
from pa_marine.hab import add_binary_labels, add_horizon_labels, resolve_thresholds, station_week_panel
from pa_marine.splits import year_split


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--hab", default=None)
    p.add_argument("--out", default=None)
    args = p.parse_args()
    cfg = load_config(args.config)
    hab_path = args.hab or cfg["paths"]["raw_hab"]
    out = args.out or cfg["paths"]["panel"]
    hab = pd.read_csv(hab_path)
    hab["time"] = pd.to_datetime(hab["time"], utc=True, errors="coerce")
    panel = station_week_panel(hab, cfg)
    split = year_split(panel, cfg)
    thr = resolve_thresholds(panel, cfg, split == "train")
    print("thresholds", thr)
    panel = add_binary_labels(panel, thr)
    panel = add_horizon_labels(panel, list(thr))
    panel["split"] = year_split(panel, cfg)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out, index=False) if out.endswith(".parquet") else panel.to_csv(out, index=False)
    print(f"wrote {out} n={len(panel)} stations={panel['location_id'].nunique()}")


if __name__ == "__main__":
    main()
