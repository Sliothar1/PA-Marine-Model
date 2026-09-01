#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from pa_marine.config import load_config
from pa_marine.features import feature_columns
from pa_marine.models import fit_predict, make_estimators


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--joined", default=None)
    p.add_argument("--horizon", default="nowcast", choices=["nowcast", "ahead7"])
    p.add_argument("--out-dir", default=None)
    args = p.parse_args()
    cfg = load_config(args.config)
    path = args.joined or cfg["paths"]["joined"]
    df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    feats = feature_columns(df)
    out_dir = Path(args.out_dir or cfg["paths"]["models_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    train = df[df["split"] == "train"]
    estimators = make_estimators()
    tax_ids = [c[2:] for c in df.columns if c.startswith("y_") and c.endswith(f"_{args.horizon}")]
    # columns like y_dinophysis_nowcast
    targets = [c for c in df.columns if c.startswith("y_") and c.endswith(f"_{args.horizon}")]
    meta = {"features": feats, "horizon": args.horizon, "models": list(estimators), "targets": targets}
    for tgt in targets:
        y = train[tgt].astype(int)
        X = train[feats]
        mask = y.notna()
        for name, est in estimators.items():
            fit_predict(est, X.loc[mask], y.loc[mask], X.loc[mask])
            joblib.dump(est, out_dir / f"{name}_{tgt}.joblib")
            print("fitted", name, tgt)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
