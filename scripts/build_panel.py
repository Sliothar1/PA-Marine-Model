#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pa_marine.config import load_config
from pa_marine.hab import add_binary_labels, add_horizon_labels, resolve_thresholds, station_week_panel
from pa_marine.splits import purge_boundary_rows, year_split


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--hab", default=None)
    p.add_argument("--out", default=None)
    p.add_argument(
        "--no-purge",
        action="store_true",
        help="Keep rows whose label window reaches into the next split. The "
        "[0,14]d nowcast window spans 3 ISO weeks, so the last ~2 weeks of each "
        "split otherwise leak labels forward across the boundary. Purging is on "
        "by default; this flag restores the pre-fix behaviour.",
    )
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
    split = year_split(panel, cfg)
    if not args.no_purge:
        horizon = int(cfg["labels"]["horizons"]["nowcast_days"][1])
        purged = purge_boundary_rows(panel, split, label_horizon_days=horizon)
        n_dropped = int((purged == "drop").sum() - (split == "drop").sum())
        print(f"purged {n_dropped} boundary row(s) whose {horizon}d label window "
              f"crossed a split edge")
        split = purged
    panel["split"] = split
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out, index=False) if out.endswith(".parquet") else panel.to_csv(out, index=False)
    print(f"wrote {out} n={len(panel)} stations={panel['location_id'].nunique()}")


if __name__ == "__main__":
    main()
