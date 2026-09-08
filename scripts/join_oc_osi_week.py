#!/usr/bin/env python3
"""Join OC Chl (+ optional OSI SAF week SST) onto the strong Dinophysis joined panel.

Week-join schema (aligned with join_week_panel):
  - Chl daily → lag0/7/14/21 + roll7/14/30 at week_end (= week_start + 6d)
  - OSI SAF: ISO-week mean of quality-filtered clear-sky SST (independent check)

Outputs:
  data/processed/joined_features_oc_osi.parquet
  data/processed/oc_osi_join_summary.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pa_marine.features import LAGS, ROLLS
from pa_marine.osi_saf_sst import week_mean_from_daily_clearsky

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"


def _engineer_daily_lags(daily: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    parts = []
    for loc, g in daily.groupby("location_id"):
        g = g.sort_values("date").copy()
        extra = {}
        for col in cols:
            if col not in g.columns:
                continue
            s = g[col]
            for lag in LAGS:
                extra[f"{col}_lag{lag}d"] = s.shift(lag)
            for w in ROLLS:
                extra[f"{col}_roll{w}d"] = s.rolling(w, min_periods=max(3, w // 3)).mean()
        if extra:
            g = pd.concat([g, pd.DataFrame(extra, index=g.index)], axis=1)
        parts.append(g)
    return pd.concat(parts, ignore_index=True) if parts else daily


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--joined", default=str(PROC / "joined_features.parquet"))
    p.add_argument("--chl-daily", default=str(RAW / "oc_chl_daily.parquet"))
    p.add_argument("--osi-daily", default=None, help="optional clear-sky daily OSI SST parquet")
    p.add_argument("--out", default=str(PROC / "joined_features_oc_osi.parquet"))
    p.add_argument("--summary", default=str(PROC / "oc_osi_join_summary.json"))
    args = p.parse_args()

    joined = pd.read_parquet(args.joined)
    joined["week_start"] = pd.to_datetime(joined["week_start"]).dt.tz_localize(None).dt.normalize()
    joined["feat_date"] = joined["week_start"] + pd.Timedelta(days=6)

    summary: dict = {
        "n_joined_in": int(len(joined)),
        "chl_path": args.chl_daily,
        "osi_daily_path": args.osi_daily,
        "chl_attached": False,
        "osi_attached": False,
    }

    out = joined.copy()

    chl_path = Path(args.chl_daily)
    if chl_path.exists():
        chl = pd.read_parquet(chl_path)
        chl["date"] = pd.to_datetime(chl["date"]).dt.tz_localize(None).dt.normalize()
        chl = _engineer_daily_lags(chl, ["chl", "chl_log1p"])
        feat_cols = [
            c
            for c in chl.columns
            if c.startswith("chl") and (c == "chl" or c == "chl_log1p" or "_lag" in c or "_roll" in c)
        ]
        keep = ["location_id", "date"] + feat_cols
        feat = chl[keep].rename(columns={"date": "feat_date"})
        out = out.merge(feat, on=["location_id", "feat_date"], how="left")
        summary["chl_attached"] = True
        summary["chl_feature_cols"] = feat_cols
        summary["chl_week_coverage"] = float(out["chl"].notna().mean()) if "chl" in out.columns else 0.0
        summary["chl_daily_n"] = int(len(chl))
        summary["chl_daily_stations"] = int(chl["location_id"].nunique())
    else:
        summary["chl_missing"] = f"not found: {chl_path}"

    if args.osi_daily:
        osi_path = Path(args.osi_daily)
        if osi_path.exists():
            osi_d = pd.read_parquet(osi_path)
            osi_w = week_mean_from_daily_clearsky(osi_d)
            out = out.merge(osi_w, on=["location_id", "iso_year", "iso_week"], how="left")
            # optional delta vs OISST week-end sst
            if "sst" in out.columns and "osi_sst_week" in out.columns:
                out["osi_minus_oisst"] = out["osi_sst_week"] - out["sst"]
            summary["osi_attached"] = True
            summary["osi_week_coverage"] = float(out["osi_sst_week"].notna().mean())
            summary["osi_feature_cols"] = [
                c for c in ["osi_sst_week", "osi_sst_n_clear", "osi_minus_oisst"] if c in out.columns
            ]
        else:
            summary["osi_missing"] = f"not found: {osi_path}"

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    summary["n_joined_out"] = int(len(out))
    summary["out"] = str(out_path)
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
