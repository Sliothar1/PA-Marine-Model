#!/usr/bin/env python3
"""Light ablation: STRONG_OISST ± lagged NAO/EA/AMO for Irish Dinophysis nowcast.

Honest national PR-AUC check — macro teleconnections are for explanatory power /
Cork narrative, not expected to beat the strong 9-feature baseline.
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
WEEK = PROC / "climate_indices_week.csv"
OUT_JSON = PROC / "macro_climate_ablation_metrics.json"
OUT_MD = PROC / "macro_climate_ablation_report.md"
TARGET = "y_dinophysis_nowcast"

NAO_EA_FEATS = [
    "nao",
    "nao_lag1m",
    "nao_lag2m",
    "nao_daily_mean",
    "nao_daily_mean_lag1w",
    "ea",
    "ea_lag1m",
    "ea_lag2m",
]
AMO_FEATS = ["amo", "amo_lag1m", "amo_lag3m", "amo_roll3m"]


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
    if not JOINED.exists() or not WEEK.exists():
        print("missing joined or climate week helper", file=sys.stderr)
        return 1

    df0 = pd.read_parquet(JOINED)
    strong = [f for f in sorted(STRONG_OISST) if f in df0.columns]
    if len(strong) < 9:
        print("strong incomplete", strong, file=sys.stderr)
        return 1

    week = pd.read_csv(WEEK)
    drop = [c for c in ("year", "month", "week_start") if c in week.columns]
    week = week.drop(columns=drop)
    df = df0.merge(week, on=["iso_year", "iso_week"], how="left")

    nao_ea = [c for c in NAO_EA_FEATS if c in df.columns]
    amo = [c for c in AMO_FEATS if c in df.columns]
    cov = {c: float(df[c].notna().mean()) for c in nao_ea + amo}

    configs = {
        "strong": strong,
        "strong_nao_ea": strong + nao_ea,
        "strong_amo": strong + amo,
        "strong_nao_ea_amo": strong + nao_ea + amo,
        "nao_ea_only": nao_ea,
    }
    configs = {k: list(dict.fromkeys(v)) for k, v in configs.items() if v}

    results = {"_meta": {"target": TARGET, "coverage": cov, "elapsed_s": None}, "runs": {}}
    for label, feats in configs.items():
        print(f"eval {label} n={len(feats)} …", flush=True)
        results["runs"][label] = eval_feature_set(df, feats, label)

    results["_meta"]["elapsed_s"] = round(time.time() - t0, 1)

    rows = []
    for label, r in results["runs"].items():
        cal = r.get("lightgbm_test_cal", {})
        raw = r.get("lightgbm_test_raw", {})
        vcal = r.get("lightgbm_val_cal", {})
        rows.append(
            {
                "label": label,
                "n_features": r["n_features"],
                "lgbm_val_cal_pr_auc": vcal.get("pr_auc"),
                "lgbm_test_cal_pr_auc": cal.get("pr_auc"),
                "lgbm_test_raw_pr_auc": raw.get("pr_auc"),
                "lgbm_test_cal_brier": cal.get("brier"),
            }
        )
    tab = pd.DataFrame(rows)
    base = float(tab.loc[tab["label"] == "strong", "lgbm_test_cal_pr_auc"].iloc[0])
    tab["delta_test_cal_vs_strong"] = tab["lgbm_test_cal_pr_auc"] - base
    results["headline_table"] = tab.to_dict(orient="records")

    tab_s = tab[tab["label"].str.startswith("strong")].copy()
    best = tab_s.sort_values("lgbm_test_cal_pr_auc", ascending=False).iloc[0]
    delta_best = float(best["delta_test_cal_vs_strong"])
    if delta_best > 0.01:
        verdict = (
            f"NAO/EA/AMO lags **lift** LightGBM test cal PR-AUC vs strong by "
            f"{delta_best:+.4f} (best={best['label']})."
        )
        lift = True
    elif delta_best > 0.002:
        verdict = (
            f"Macro indices show a **marginal** test lift ({delta_best:+.4f} at {best['label']}); "
            "treat as inconclusive for national nowcast — still useful for Cork / regime narrative."
        )
        lift = False
    else:
        verdict = (
            f"NAO/EA/AMO lags **do not beat** strong nationally (best delta={delta_best:+.4f} "
            f"at {best['label']}). Use for explanatory / Cork narrative, not as a national feature upgrade."
        )
        lift = False
    results["verdict"] = {
        "text": verdict,
        "lift": lift,
        "best_label": best["label"],
        "delta": delta_best,
    }
    results["baseline_reference"] = {
        "metrics_dino_strong_lightgbm_test_calibrated_pr_auc": 0.29326665676644725,
        "this_run_strong_lightgbm_test_cal_pr_auc": base,
    }

    OUT_JSON.write_text(json.dumps(results, indent=2, default=float))
    lines = [
        "# Macro climate (NAO / EA / AMO) ablation — Irish Dinophysis nowcast",
        "",
        "**Generated:** 2026-09-02 (Europe/Dublin).  ",
        f"**Target:** `{TARGET}`. **Headline:** LightGBM test calibrated PR-AUC.",
        "**Baseline:** strong 9-feature OISST (`STRONG_OISST`).",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "## Coverage (left-join on iso_year, iso_week)",
        "",
        "| feature | fraction non-null |",
        "| --- | ---: |",
    ]
    for k, v in sorted(cov.items()):
        lines.append(f"| `{k}` | {v:.3f} |")
    lines += [
        "",
        "## Results",
        "",
        "| config | n_feat | LGBM val cal PR-AUC | LGBM test cal PR-AUC | Δ test vs strong |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for _, r in tab.iterrows():
        lines.append(
            f"| `{r['label']}` | {int(r['n_features'])} | "
            f"{r['lgbm_val_cal_pr_auc']:.4f} | {r['lgbm_test_cal_pr_auc']:.4f} | "
            f"{r['delta_test_cal_vs_strong']:+.4f} |"
        )
    lines += [
        "",
        "Indices from `scripts/ingest_climate_indices.py` → `data/processed/climate_indices_week.csv`.",
        f"Full JSON: `{OUT_JSON.relative_to(ROOT)}`. Elapsed: {results['_meta']['elapsed_s']} s.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines))
    print(verdict)
    print("Wrote", OUT_JSON, OUT_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
