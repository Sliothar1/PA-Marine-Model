#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pa_marine.config import load_config
from pa_marine.features import feature_columns
from pa_marine.metrics import climatology_probs, summarise
from pa_marine.models import fit_predict, make_estimators


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--joined", default=None)
    p.add_argument("--horizon", default="nowcast", choices=["nowcast", "ahead7"])
    p.add_argument("--out", default=None)
    args = p.parse_args()
    cfg = load_config(args.config)
    path = args.joined or cfg["paths"]["joined"]
    df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    feats = feature_columns(df)
    train = df[df["split"] == "train"]
    results = {}
    targets = [c for c in df.columns if c.startswith("y_") and c.endswith(f"_{args.horizon}")]
    estimators = make_estimators()
    for tgt in targets:
        results[tgt] = {}
        ytr = train[tgt].astype(int)
        Xtr = train[feats]
        mtr = ytr.notna()
        clim_week = train.loc[mtr, "iso_week"].to_numpy()
        clim_y = ytr.loc[mtr].to_numpy()
        for name, est in estimators.items():
            fit_predict(est, Xtr.loc[mtr], ytr.loc[mtr], Xtr.loc[mtr])
            for split in ("val", "test"):
                ev = df[df["split"] == split]
                if ev.empty:
                    continue
                y = ev[tgt].astype(int)
                mask = y.notna()
                if hasattr(est, "predict_proba"):
                    pr = est.predict_proba(ev.loc[mask, feats])[:, 1]
                else:
                    d = est.decision_function(ev.loc[mask, feats])
                    pr = 1 / (1 + np.exp(-d))
                clim = climatology_probs(clim_week, clim_y, ev.loc[mask, "iso_week"].to_numpy())
                results[tgt][f"{name}_{split}"] = summarise(y.loc[mask].to_numpy(), pr, clim)
    out = args.out or cfg["paths"]["metrics"]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
