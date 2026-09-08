#!/usr/bin/env python3
"""Ablation: STRONG_OISST vs +OC Chl / +OSI SAF week SST (Apr–Sep optional).

Honest national Dinophysis PR-AUC — do not invent metrics. Run only after
join_oc_osi_week.py has produced joined_features_oc_osi.parquet with real Chl.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from pa_marine.calibration import ProbCalibrator
from pa_marine.features import OC_CHL_CORE, OSI_SAF_WEEK, STRONG_OISST
from pa_marine.metrics import climatology_probs, summarise
from pa_marine.models import make_estimators

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
TARGET = "y_dinophysis_nowcast"


def _lgbm():
    return LGBMClassifier(
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        class_weight="balanced",
        verbosity=-1,
    )


def eval_feature_set(df: pd.DataFrame, feats: list[str], label: str) -> dict:
    train = df[df["split"] == "train"]
    val = df[df["split"] == "val"]
    test = df[df["split"] == "test"]
    ytr = train[TARGET].astype(int)
    mtr = ytr.notna()
    Xtr = train.loc[mtr, feats].fillna(0.0)
    ytr = ytr.loc[mtr]
    clim_week = train.loc[mtr, "iso_week"].to_numpy()
    clim_y = ytr.to_numpy()

    estimators = {"lightgbm": _lgbm(), "logreg": make_estimators()["logreg"]}
    for est in estimators.values():
        est.fit(Xtr, ytr)

    out: dict = {
        "label": label,
        "n_features": len(feats),
        "features": feats,
        "n_train": int(mtr.sum()),
        "n_val": int(val[TARGET].notna().sum()),
        "n_test": int(test[TARGET].notna().sum()),
    }
    for name, model in estimators.items():
        yv = val[TARGET].astype(int)
        mv = yv.notna()
        pr_val = model.predict_proba(val.loc[mv, feats].fillna(0.0))[:, 1]
        cal = ProbCalibrator(method="auto").fit(yv.loc[mv].to_numpy(), pr_val)
        for split_name, ev in (("val", val), ("test", test)):
            y = ev[TARGET].astype(int)
            mask = y.notna()
            pr_raw = model.predict_proba(ev.loc[mask, feats].fillna(0.0))[:, 1]
            clim = climatology_probs(clim_week, clim_y, ev.loc[mask, "iso_week"].to_numpy())
            y_np = y.loc[mask].to_numpy()
            raw = summarise(y_np, pr_raw, clim)
            pr_cal = cal.transform(pr_raw)
            cal_s = summarise(y_np, pr_cal, clim)
            out[f"{name}_{split_name}_raw"] = raw
            out[f"{name}_{split_name}_cal"] = {**cal_s, "calibration_method": cal.chosen_}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--joined", default=str(PROC / "joined_features_oc_osi.parquet"))
    p.add_argument("--apr-sep", action="store_true", help="filter iso_week months via week_start")
    p.add_argument("--out-json", default=str(PROC / "oc_osi_ablation_metrics.json"))
    p.add_argument("--out-md", default=str(PROC / "oc_osi_ablation_report.md"))
    args = p.parse_args()

    path = Path(args.joined)
    if not path.exists():
        raise SystemExit(
            f"Missing {path}. Run scripts/download_oc_chl.py then scripts/join_oc_osi_week.py first."
        )

    df = pd.read_parquet(path)
    if args.apr_sep:
        ws = pd.to_datetime(df["week_start"])
        df = df[ws.dt.month.between(4, 9)].copy()

    present = set(df.columns)
    strong = sorted(STRONG_OISST & present)
    chl = sorted(OC_CHL_CORE & present)
    osi = sorted(OSI_SAF_WEEK & present)

    configs = [
        ("STRONG_OISST", strong),
        ("STRONG+CHL", sorted(set(strong) | set(chl))),
        ("STRONG+OSI", sorted(set(strong) | set(osi))),
        ("STRONG+CHL+OSI", sorted(set(strong) | set(chl) | set(osi))),
    ]
    # drop empty extras
    configs = [(lab, feats) for lab, feats in configs if feats]

    results = []
    for lab, feats in configs:
        print(f"eval {lab} n_feats={len(feats)}", flush=True)
        results.append(eval_feature_set(df, feats, lab))

    out_json = Path(args.out_json)
    out_json.write_text(json.dumps(results, indent=2) + "\n")

    lines = [
        "# OC Chl / OSI SAF ablation vs STRONG_OISST",
        "",
        f"Joined: `{path}`",
        f"Apr–Sep filter: **{bool(args.apr_sep)}**",
        f"Chl cols present: {chl or 'none'}",
        f"OSI cols present: {osi or 'none'}",
        "",
        "| Config | n_feat | LGBM test cal PR-AUC | vs clim |",
        "| --- | ---: | ---: | ---: |",
    ]
    for r in results:
        cal = r.get("lightgbm_test_cal") or {}
        pr = cal.get("pr_auc")
        clim = cal.get("clim_pr_auc")
        lines.append(
            f"| {r['label']} | {r['n_features']} | "
            f"{pr if pr is not None else 'n/a'} | {clim if clim is not None else 'n/a'} |"
        )
    lines += [
        "",
        "Do not invent metrics — numbers above are from this run only.",
        f"JSON: `{out_json}`",
        "",
    ]
    Path(args.out_md).write_text("\n".join(lines))
    print(f"wrote {out_json} and {args.out_md}", flush=True)


if __name__ == "__main__":
    main()
