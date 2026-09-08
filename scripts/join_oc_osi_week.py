#!/usr/bin/env python3
"""Join OC Chl (+ ODYSSEA / optional OSI SAF week SST) onto the strong Dinophysis joined panel.

Week-join schema (aligned with join_week_panel):
  - Chl daily → lag0/7/14/21 + roll7/14/30 at week_end (= week_start + 6d)
  - ODYSSEA week: ISO-week mean SST aliased as osi_sst_week (+ osi_minus_oisst)
  - OSI SAF daily (optional): ISO-week mean of quality-filtered clear-sky SST

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


def _coverage_by_split(df: pd.DataFrame, col: str) -> dict:
    out = {}
    if col not in df.columns or "split" not in df.columns:
        return out
    for split, g in df.groupby("split"):
        n = int(len(g))
        n_ok = int(g[col].notna().sum())
        out[str(split)] = {
            "n": n,
            "n_nonnull": n_ok,
            "coverage": float(n_ok / n) if n else 0.0,
        }
    # overall
    n = int(len(df))
    n_ok = int(df[col].notna().sum())
    out["all"] = {"n": n, "n_nonnull": n_ok, "coverage": float(n_ok / n) if n else 0.0}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--joined", default=str(PROC / "joined_features.parquet"))
    p.add_argument("--chl-daily", default=str(RAW / "oc_chl_daily.parquet"))
    p.add_argument("--osi-daily", default=None, help="optional clear-sky daily OSI SST parquet")
    p.add_argument(
        "--odyssea-week",
        default=str(PROC / "odyssea_station_week.parquet"),
        help="ODYSSEA ISO-week SST (Climate Drivers extract); set empty to skip",
    )
    p.add_argument("--out", default=str(PROC / "joined_features_oc_osi.parquet"))
    p.add_argument("--summary", default=str(PROC / "oc_osi_join_summary.json"))
    p.add_argument("--skip-chl", action="store_true", help="do not attach pilot Chl")
    args = p.parse_args()

    joined = pd.read_parquet(args.joined)
    joined["week_start"] = pd.to_datetime(joined["week_start"]).dt.tz_localize(None).dt.normalize()
    joined["feat_date"] = joined["week_start"] + pd.Timedelta(days=6)

    summary: dict = {
        "n_joined_in": int(len(joined)),
        "chl_path": args.chl_daily,
        "osi_daily_path": args.osi_daily,
        "odyssea_week_path": args.odyssea_week or None,
        "chl_attached": False,
        "osi_attached": False,
        "odyssea_attached": False,
    }

    out = joined.copy()

    chl_path = Path(args.chl_daily)
    if (not args.skip_chl) and chl_path.exists():
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
        summary["chl_coverage_by_split"] = _coverage_by_split(out, "chl")
        summary["chl_daily_n"] = int(len(chl))
        summary["chl_daily_stations"] = int(chl["location_id"].nunique())
        cov_by = summary.get("chl_coverage_by_split") or {}
        cov_test = (cov_by.get("test") or {}).get("coverage")
        cov_train = (cov_by.get("train") or {}).get("coverage")
        cov_all = summary["chl_week_coverage"]
        if (
            cov_test is not None
            and cov_test >= 0.05
            and summary["chl_daily_stations"] >= 50
        ):
            summary["chl_note"] = (
                f"National ARCO Chl attached: stations={summary['chl_daily_stations']} "
                f"train_cov={float(cov_train or 0):.3f} test_cov={cov_test:.3f} "
                f"all_cov={cov_all:.3f}."
            )
        else:
            summary["chl_note"] = (
                "PILOT/LOW coverage — do NOT claim national Chl skill from fillna(0)"
            )
    else:
        summary["chl_missing"] = f"skipped or not found: {chl_path}"

    # ODYSSEA week SST (preferred Climate Drivers path) → OSI_SAF_WEEK aliases
    if args.odyssea_week:
        ody_path = Path(args.odyssea_week)
        if ody_path.exists():
            ody = pd.read_parquet(ody_path)
            keep_cols = ["location_id", "iso_year", "iso_week", "odyssea_sst_week"]
            if "odyssea_sst_n" in ody.columns:
                keep_cols.append("odyssea_sst_n")
            ody = ody[keep_cols].drop_duplicates(["location_id", "iso_year", "iso_week"])
            out = out.merge(ody, on=["location_id", "iso_year", "iso_week"], how="left")
            out["osi_sst_week"] = out["odyssea_sst_week"]
            if "odyssea_sst_n" in out.columns:
                out["osi_sst_n_clear"] = out["odyssea_sst_n"]
            if "sst" in out.columns:
                out["osi_minus_oisst"] = out["odyssea_sst_week"] - out["sst"]
            summary["odyssea_attached"] = True
            summary["odyssea_week_n"] = int(len(ody))
            summary["odyssea_week_stations"] = int(ody["location_id"].nunique())
            summary["odyssea_sst_week_coverage_by_split"] = _coverage_by_split(
                out, "odyssea_sst_week"
            )
            summary["osi_sst_week_coverage_by_split"] = _coverage_by_split(out, "osi_sst_week")
            summary["osi_feature_cols"] = [
                c
                for c in ["osi_sst_week", "osi_sst_n_clear", "osi_minus_oisst", "odyssea_sst_week"]
                if c in out.columns
            ]
            # Hard block for true provider-swap when train coverage ~0
            cov = summary["odyssea_sst_week_coverage_by_split"]
            train_cov = float((cov.get("train") or {}).get("coverage") or 0.0)
            summary["provider_swap_hard_block"] = train_cov < 0.05
            summary["provider_swap_note"] = (
                "HARD BLOCK: cannot rebuild STRONG features from ODYSSEA across train "
                "2003–2018 with current extract (ODYSSEA station-week is ~2022–2024 only; "
                f"train odyssea_sst_week coverage={train_cov:.4f}). "
                "Ablation STRONG+odyssea is an add-on with missing-filled zeros on train/val, "
                "NOT a fair OISST→ODYSSEA provider swap."
                if summary["provider_swap_hard_block"]
                else "Train coverage sufficient for cautious provider-swap discussion."
            )
        else:
            summary["odyssea_missing"] = f"not found: {ody_path}"

    if args.osi_daily:
        osi_path = Path(args.osi_daily)
        if osi_path.exists():
            osi_d = pd.read_parquet(osi_path)
            osi_w = week_mean_from_daily_clearsky(osi_d)
            # only fill where ODYSSEA did not already supply osi_sst_week
            if "osi_sst_week" in out.columns:
                tmp = out[["location_id", "iso_year", "iso_week"]].merge(
                    osi_w, on=["location_id", "iso_year", "iso_week"], how="left", suffixes=("", "_osi")
                )
                # merge osi cols that don't collide
                for c in osi_w.columns:
                    if c in ("location_id", "iso_year", "iso_week"):
                        continue
                    if c not in out.columns:
                        out = out.merge(
                            osi_w[["location_id", "iso_year", "iso_week", c]],
                            on=["location_id", "iso_year", "iso_week"],
                            how="left",
                        )
            else:
                out = out.merge(osi_w, on=["location_id", "iso_year", "iso_week"], how="left")
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
    # also write alias path for Gatekeeper naming
    alias = PROC / "joined_features_odyssea.parquet"
    if out_path.resolve() != alias.resolve():
        out.to_parquet(alias, index=False)
        summary["out_alias"] = str(alias)
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
