#!/usr/bin/env python3
"""Light ablation: STRONG_OISST ± ocean colour Chl ± OSI SAF SST week features.

Honest national Dinophysis PR-AUC report (pattern: climate_drivers_ablation.py).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from pa_marine.calibration import ProbCalibrator
from pa_marine.features import STRONG_OISST
from pa_marine.metrics import climatology_probs, summarise
from pa_marine.models import make_estimators

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
JOINED = PROC / "joined_features.parquet"
CHL_WEEK = PROC / "ocean_colour_chl_week.parquet"
OSI_WEEK = PROC / "osi_saf_sst_week.parquet"
OUT_JSON = PROC / "oc_osi_ablation_metrics.json"
OUT_MD = PROC / "oc_osi_ablation_report.md"
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


def _raw_probs(est, X) -> np.ndarray:
    return est.predict_proba(X)[:, 1]


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
        pr_val = _raw_probs(model, val.loc[mv, feats].fillna(0.0))
        cal = ProbCalibrator(method="auto").fit(yv.loc[mv].to_numpy(), pr_val)
        for split_name, ev in (("val", val), ("test", test)):
            y = ev[TARGET].astype(int)
            mask = y.notna()
            pr_raw = _raw_probs(model, ev.loc[mask, feats].fillna(0.0))
            clim = climatology_probs(clim_week, clim_y, ev.loc[mask, "iso_week"].to_numpy())
            y_np = y.loc[mask].to_numpy()
            raw = summarise(y_np, pr_raw, clim)
            pr_cal = cal.transform(pr_raw)
            cal_s = summarise(y_np, pr_cal, clim)
            out[f"{name}_{split_name}_raw"] = raw
            out[f"{name}_{split_name}_cal"] = {**cal_s, "calibration_method": cal.chosen_}
    return out


def main() -> int:
    t0 = time.time()
    if not JOINED.exists():
        print("missing joined_features", file=sys.stderr)
        return 1
    df = pd.read_parquet(JOINED)
    strong = [f for f in sorted(STRONG_OISST) if f in df.columns]
    cov: dict = {}

    if CHL_WEEK.exists():
        chl = pd.read_parquet(CHL_WEEK)
        chl_cols = [
            c
            for c in [
                "chl_mean",
                "chl_log1p",
                "chl_mean_lag1w",
                "chl_log1p_lag1w",
                "chl_mean_roll4w",
                "chl_max",
            ]
            if c in chl.columns
        ]
        df = df.merge(
            chl[["location_id", "iso_year", "iso_week"] + chl_cols],
            on=["location_id", "iso_year", "iso_week"],
            how="left",
        )
        for c in chl_cols:
            cov[c] = float(df[c].notna().mean())
    else:
        chl_cols = []
        cov["chl_week"] = "missing"

    if OSI_WEEK.exists():
        osi = pd.read_parquet(OSI_WEEK)
        osi_cols = [c for c in ["osi_sst_mean", "osi_sst_lag1w", "osi_sst_max"] if c in osi.columns]
        df = df.merge(
            osi[["location_id", "iso_year", "iso_week"] + osi_cols],
            on=["location_id", "iso_year", "iso_week"],
            how="left",
        )
        for c in osi_cols:
            cov[c] = float(df[c].notna().mean())
    else:
        osi_cols = []
        cov["osi_week"] = "missing"

    configs = {
        "strong": strong,
        "strong_chl": strong + chl_cols,
        "strong_osi_sst": strong + osi_cols,
        "strong_chl_osi": strong + chl_cols + osi_cols,
    }
    configs = {k: list(dict.fromkeys(v)) for k, v in configs.items() if len(v) >= len(strong)}

    results = {"_meta": {"target": TARGET, "coverage": cov}, "runs": {}}
    for label, feats in configs.items():
        print(f"eval {label} n={len(feats)}", flush=True)
        results["runs"][label] = eval_feature_set(df, feats, label)

    rows = []
    for label, r in results["runs"].items():
        cal = r.get("lightgbm_test_cal", {})
        vcal = r.get("lightgbm_val_cal", {})
        rows.append(
            {
                "label": label,
                "n_features": r["n_features"],
                "lgbm_val_cal_pr_auc": vcal.get("pr_auc"),
                "lgbm_test_cal_pr_auc": cal.get("pr_auc"),
            }
        )
    tab = pd.DataFrame(rows)
    base = float(tab.loc[tab["label"] == "strong", "lgbm_test_cal_pr_auc"].iloc[0])
    tab["delta_test_cal_vs_strong"] = tab["lgbm_test_cal_pr_auc"] - base
    results["headline_table"] = tab.to_dict(orient="records")
    best = tab.sort_values("lgbm_test_cal_pr_auc", ascending=False).iloc[0]
    delta = float(best["delta_test_cal_vs_strong"])
    if delta > 0.01:
        verdict = f"Chl/OSI extras **lift** test cal PR-AUC by {delta:+.4f} (best={best['label']})."
        lift = True
    elif delta > 0.002:
        verdict = f"Marginal lift only ({delta:+.4f} at {best['label']}); inconclusive nationally."
        lift = False
    else:
        verdict = (
            f"Chl / OSI SAF SST extras **do not beat** STRONG_OISST nationally "
            f"(best delta={delta:+.4f} at {best['label']})."
        )
        lift = False
    results["verdict"] = {"text": verdict, "lift": lift, "best_label": best["label"], "delta": delta}
    results["_meta"]["elapsed_s"] = round(time.time() - t0, 1)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=float))

    lines = [
        "# Ocean colour + OSI SAF SST ablation — Irish Dinophysis",
        "",
        f"**Generated:** 2026-09-08 (Europe/Dublin).  ",
        f"**Target:** `{TARGET}`. Baseline: `STRONG_OISST` (9 features).",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "## Coverage (non-null after left join)",
        "",
        "| feature | fraction |",
        "| --- | ---: |",
    ]
    for k, v in sorted(cov.items()):
        if isinstance(v, float):
            lines.append(f"| `{k}` | {v:.3f} |")
        else:
            lines.append(f"| `{k}` | {v} |")
    lines += [
        "",
        "## Results",
        "",
        "| config | n_feat | val cal PR-AUC | test cal PR-AUC | Δ vs strong |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for _, r in tab.iterrows():
        lines.append(
            f"| `{r['label']}` | {int(r['n_features'])} | "
            f"{r['lgbm_val_cal_pr_auc']:.4f} | {r['lgbm_test_cal_pr_auc']:.4f} | "
            f"{r['delta_test_cal_vs_strong']:+.4f} |"
        )
    lines += ["", f"JSON: `{OUT_JSON.relative_to(ROOT)}`.", ""]
    OUT_MD.write_text("\n".join(lines))
    print(verdict)
    print("Wrote", OUT_JSON, OUT_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
