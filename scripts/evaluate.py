#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pa_marine.calibration import ProbCalibrator
from pa_marine.config import load_config
from pa_marine.features import feature_columns
from pa_marine.metrics import climatology_probs, summarise
from pa_marine.models import fit_predict, make_estimators


def _raw_probs(est, X) -> np.ndarray:
    if hasattr(est, "predict_proba"):
        return est.predict_proba(X)[:, 1]
    d = est.decision_function(X)
    return 1 / (1 + np.exp(-d))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--joined", default=None)
    p.add_argument("--horizon", default="both", choices=["nowcast", "ahead7", "both"])
    p.add_argument(
        "--calibration",
        default="auto",
        choices=["auto", "isotonic", "sigmoid", "none"],
        help="Fit calibrator on validation only (default: auto = isotonic if enough positives).",
    )
    p.add_argument("--out", default=None)
    p.add_argument(
        "--feature-mode",
        default="all",
        choices=["all", "strong", "sst"],
        help="all=joined features; strong=drop weak MHW/noise (dino ablation winner); "
        "sst=SST/SSTA + woy + geo only.",
    )
    args = p.parse_args()
    cfg = load_config(args.config)
    path = args.joined or cfg["paths"]["joined"]
    df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    feats = feature_columns(df)
    if args.feature_mode == "strong":
        # Keep seasonal/geo + features that had gain_pct>=1% or clear perm signal in
        # the 2026-09-01 Dinophysis study (see data/processed/dino_feature_report.md).
        # Exact drop_weak winner set from dino_feature_report.md (gain>=1% & perm>0 + must).
        strong = {
            "woy_sin", "woy_cos", "latitude", "longitude",
            "sst", "sst_lag0d", "sst_lag21d", "sst_roll7d", "sst_roll30d",
        }
        feats = [f for f in feats if f in strong]
    elif args.feature_mode == "sst":
        must = {"woy_sin", "woy_cos", "latitude", "longitude"}
        feats = [f for f in feats if f.startswith("sst") or f.startswith("ssta") or f in must]
    train = df[df["split"] == "train"]
    val = df[df["split"] == "val"]
    results: dict = {"_meta": {"calibration": args.calibration, "feature_mode": args.feature_mode, "n_features": len(feats)}}
    horizons = ["nowcast", "ahead7"] if args.horizon == "both" else [args.horizon]
    for horizon in horizons:
        targets = [c for c in df.columns if c.startswith("y_") and c.endswith(f"_{horizon}")]
        for tgt in targets:
            results[tgt] = {}
            ytr = train[tgt].astype(int)
            Xtr = train[feats]
            mtr = ytr.notna()
            clim_week = train.loc[mtr, "iso_week"].to_numpy()
            clim_y = ytr.loc[mtr].to_numpy()
            estimators = make_estimators()
            for name, est in estimators.items():
                fit_predict(est, Xtr.loc[mtr], ytr.loc[mtr], Xtr.loc[mtr])

                calibrator = None
                if args.calibration != "none" and not val.empty:
                    yv = val[tgt].astype(int)
                    mv = yv.notna()
                    if int(mv.sum()) > 0 and int(yv.loc[mv].sum()) > 0:
                        pr_val_raw = _raw_probs(est, val.loc[mv, feats])
                        calibrator = ProbCalibrator(method=args.calibration).fit(
                            yv.loc[mv].to_numpy(), pr_val_raw
                        )

                for split in ("val", "test"):
                    ev = df[df["split"] == split]
                    if ev.empty:
                        continue
                    y = ev[tgt].astype(int)
                    mask = y.notna()
                    if int(mask.sum()) == 0:
                        continue
                    pr_raw = _raw_probs(est, ev.loc[mask, feats])
                    clim = climatology_probs(clim_week, clim_y, ev.loc[mask, "iso_week"].to_numpy())
                    y_np = y.loc[mask].to_numpy()
                    raw_summary = summarise(y_np, pr_raw, clim)
                    key = f"{name}_{split}"
                    results[tgt][key] = dict(raw_summary)
                    results[tgt][key]["calibrated"] = False

                    if calibrator is not None:
                        # On val, report both raw and calibrated; calibrator was fit on val
                        # so calibrated val metrics are in-sample for the calibrator.
                        pr_cal = calibrator.transform(pr_raw)
                        cal_summary = summarise(y_np, pr_cal, clim)
                        cal_key = f"{name}_{split}_calibrated"
                        results[tgt][cal_key] = dict(cal_summary)
                        results[tgt][cal_key]["calibrated"] = True
                        results[tgt][cal_key]["calibration_method"] = calibrator.chosen_
                        results[tgt][cal_key]["raw_brier"] = raw_summary["brier"]
                        results[tgt][cal_key]["raw_brier_skill"] = raw_summary["brier_skill"]
                        results[tgt][cal_key]["raw_pr_auc"] = raw_summary["pr_auc"]
    out = args.out or cfg["paths"]["metrics"]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
