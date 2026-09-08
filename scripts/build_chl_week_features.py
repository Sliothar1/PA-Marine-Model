#!/usr/bin/env python3
"""Build Sunday week-end CHL features (no future leakage) from station daily CHL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/ocean_colour/chl_station_daily.parquet"
JOINED = ROOT / "data/processed/joined_features.parquet"
OUT_WEEK = ROOT / "data/processed/chl_week_features.parquet"
OUT_JOINED = ROOT / "data/processed/joined_features_chl.parquet"
OUT_COV = ROOT / "data/processed/chl_join_coverage.json"

LAGS = (7, 14)
ROLLS = (7, 14)


def engineer(daily: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for loc, g in daily.groupby("location_id"):
        g = g.sort_values("date").copy()
        s = g["chl"]
        extra = {"chl": s}
        for lag in LAGS:
            extra[f"chl_lag{lag}d"] = s.shift(lag)
        for w in ROLLS:
            extra[f"chl_roll{w}d"] = s.rolling(w, min_periods=max(3, w // 3)).mean()
        frame = pd.DataFrame(extra, index=g.index)
        frame.insert(0, "location_id", loc)
        frame.insert(1, "date", g["date"].values)
        parts.append(frame)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--daily", default=str(RAW))
    p.add_argument("--joined", default=str(JOINED))
    p.add_argument("--out-week", default=str(OUT_WEEK))
    p.add_argument("--out-joined", default=str(OUT_JOINED))
    p.add_argument("--coverage", default=str(OUT_COV))
    args = p.parse_args()

    daily = pd.read_parquet(args.daily)
    daily["date"] = pd.to_datetime(daily["date"]).dt.tz_localize(None).dt.normalize()
    if "CHL" in daily.columns and "chl" not in daily.columns:
        daily = daily.rename(columns={"CHL": "chl"})
    daily["chl"] = pd.to_numeric(daily["chl"], errors="coerce")

    feat = engineer(daily)
    feat_cols = ["chl", "chl_lag7d", "chl_lag14d", "chl_roll7d", "chl_roll14d"]

    joined = pd.read_parquet(args.joined)
    joined["week_start"] = pd.to_datetime(joined["week_start"]).dt.tz_localize(None).dt.normalize()
    joined["feat_date"] = joined["week_start"] + pd.Timedelta(days=6)

    week = feat.rename(columns={"date": "feat_date"})
    week_out = week[["location_id", "feat_date"] + feat_cols].copy()
    iso = week_out["feat_date"].dt.isocalendar()
    week_out["iso_year"] = iso.year.astype(int)
    week_out["iso_week"] = iso.week.astype(int)
    week_out["week_start"] = week_out["feat_date"] - pd.Timedelta(days=6)
    Path(args.out_week).parent.mkdir(parents=True, exist_ok=True)
    week_out.to_parquet(args.out_week, index=False)

    keep = ["location_id", "feat_date"] + feat_cols
    out = joined.merge(week[keep], on=["location_id", "feat_date"], how="left")
    out.to_parquet(args.out_joined, index=False)

    cov = {
        "n_daily_rows": int(len(daily)),
        "n_daily_stations": int(daily["location_id"].nunique()),
        "daily_date_min": str(daily["date"].min().date()),
        "daily_date_max": str(daily["date"].max().date()),
        "n_week_feature_rows": int(len(week_out)),
        "n_joined_in": int(len(joined)),
        "n_joined_out": int(len(out)),
        "feature_cols": feat_cols,
        "coverage_overall": {c: float(out[c].notna().mean()) for c in feat_cols},
    }
    if "split" in out.columns:
        by = {}
        for s, g in out.groupby("split"):
            by[str(s)] = {c: float(g[c].notna().mean()) for c in feat_cols}
            by[str(s)]["n"] = int(len(g))
        cov["coverage_by_split"] = by
    Path(args.coverage).write_text(json.dumps(cov, indent=2) + "\n")
    print(json.dumps(cov, indent=2))
    print(f"wrote {args.out_week}")
    print(f"wrote {args.out_joined}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
