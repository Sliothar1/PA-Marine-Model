#!/usr/bin/env python3
"""Ablation: STRONG_OISST vs +OC Chl / +ODYSSEA (osi_sst_week aliases) (Apr–Sep / Connemara optional).

Honest national Dinophysis PR-AUC — do not invent metrics. Run only after
join_oc_osi_week.py has produced joined_features_oc_osi.parquet.
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

# Prefer these ODYSSEA / OSI week add-ons (n_clear optional)
OSI_ODYSSEA_CORE = {"osi_sst_week", "osi_minus_oisst"}


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
        cal = ProbCalibrator(method="isotonic").fit(yv.loc[mv].to_numpy(), pr_val)
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


def _cov(df: pd.DataFrame, col: str) -> dict:
    out = {}
    if col not in df.columns:
        return out
    for split, g in df.groupby("split"):
        n = int(len(g))
        n_ok = int(g[col].notna().sum())
        out[str(split)] = {"n": n, "n_nonnull": n_ok, "coverage": float(n_ok / n) if n else 0.0}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--joined", default=str(PROC / "joined_features_oc_osi.parquet"))
    p.add_argument("--apr-sep", action="store_true", help="filter iso_week months via week_start")
    p.add_argument(
        "--connemara",
        action="store_true",
        help="filter to Connemara AOI lat 53.2–53.7 & lon -10.2–-9.4",
    )
    p.add_argument("--out-json", default=str(PROC / "oc_osi_ablation_metrics.json"))
    p.add_argument("--out-md", default=str(PROC / "oc_osi_ablation_report.md"))
    args = p.parse_args()

    path = Path(args.joined)
    if not path.exists():
        raise SystemExit(
            f"Missing {path}. Run scripts/join_oc_osi_week.py first."
        )

    df = pd.read_parquet(path)
    slice_tag = "national"
    if args.connemara:
        df = df[
            df["latitude"].between(53.2, 53.7) & df["longitude"].between(-10.2, -9.4)
        ].copy()
        print(
            f"Connemara filter: n={len(df)} stations={df['location_id'].nunique()}",
            flush=True,
        )
        if df.empty:
            raise SystemExit("Connemara filter emptied the joined frame")
        slice_tag = "connemara"
    if args.apr_sep:
        ws = pd.to_datetime(df["week_start"])
        df = df[ws.dt.month.between(4, 9)].copy()
        slice_tag = f"{slice_tag}_apr_sep" if slice_tag != "national" else "apr_sep"

    present = set(df.columns)
    strong = sorted(STRONG_OISST & present)
    chl = sorted(OC_CHL_CORE & present)
    # Prefer core ODYSSEA aliases; fall back to full OSI_SAF_WEEK if present
    osi = sorted((OSI_ODYSSEA_CORE | (OSI_SAF_WEEK & present)) & present)
    # Keep only cols that actually have any non-null (avoid empty chl pollution claiming skill)
    osi = [c for c in osi if c in df.columns]
    chl_usable = [c for c in chl if df[c].notna().any()]

    configs = [
        ("STRONG_OISST", strong),
        ("STRONG+ODYSSEA", sorted(set(strong) | set(osi))),
    ]
    if chl_usable:
        configs.append(("STRONG+CHL", sorted(set(strong) | set(chl_usable))))
        configs.append(("STRONG+CHL+ODYSSEA", sorted(set(strong) | set(chl_usable) | set(osi))))
    configs = [(lab, feats) for lab, feats in configs if feats]

    cov_col = "odyssea_sst_week" if "odyssea_sst_week" in df.columns else "osi_sst_week"
    coverage = _cov(df, cov_col)
    train_cov = float((coverage.get("train") or {}).get("coverage") or 0.0)
    hard_block = train_cov < 0.05

    results = []
    for lab, feats in configs:
        print(f"eval {lab} n_feats={len(feats)}", flush=True)
        results.append(eval_feature_set(df, feats, lab))

    payload = {
        "slice": slice_tag,
        "joined": str(path),
        "apr_sep": bool(args.apr_sep),
        "connemara": bool(args.connemara),
        "odyssea_coverage_by_split": coverage,
        "provider_swap_hard_block": hard_block,
        "provider_swap_note": (
            "HARD BLOCK: ODYSSEA train coverage ≈0 — cannot claim fair OISST→ODYSSEA "
            "provider-swap; STRONG+ODYSSEA is an add-on with train/val mostly missing→0."
            if hard_block
            else "Train ODYSSEA coverage non-trivial."
        ),
        "chl_cols_present": chl_usable,
        "chl_note": (
            (
                f"Chl cols present ({len(chl_usable)}); "
                f"test non-null rows={(df.loc[df['split']=='test', chl_usable[0]].notna().mean() if chl_usable else 0):.3f}; "
                "train truncated before 2018 ARCO start — fillna(0) on early train."
            )
            if chl_usable
            else "no Chl cols"
        ),
        "osi_cols_present": osi,
        "results": results,
    }

    out_json = Path(args.out_json)
    out_json.write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        f"# ODYSSEA / OC ablation vs STRONG_OISST ({slice_tag})",
        "",
        f"Joined: `{path}`",
        f"Apr–Sep filter: **{bool(args.apr_sep)}**",
        f"Connemara filter: **{bool(args.connemara)}**",
        f"ODYSSEA/OSI cols: {osi or 'none'}",
        f"Chl cols: {chl_usable or 'none'} ({payload['chl_note']})",
        f"Provider-swap hard block: **{hard_block}** (train `{cov_col}` cov={train_cov:.4f})",
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
        payload["provider_swap_note"],
        "",
        "Do not invent metrics — numbers above are from this run only.",
        f"JSON: `{out_json}`",
        "",
    ]
    Path(args.out_md).write_text("\n".join(lines))
    print(f"wrote {out_json} and {args.out_md}", flush=True)
    print(json.dumps({"slice": slice_tag, "hard_block": hard_block, "train_cov": train_cov}, indent=2))


if __name__ == "__main__":
    main()
