#!/usr/bin/env python3
"""Ablation: strong OISST Dinophysis baseline vs +Met radiation / river Q / warming.

Honest report — expected that single-point Met + regional Q may not lift national
PR-AUC (ERA5 wind already failed). Still quantify coverage and deltas.
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
MET_WEEK = PROC / "met_west_climate_week.parquet"
RIVERS = PROC / "rivers_week_primary_Q.csv"
WARM = PROC / "sst_warming_year_features.csv"
OUT_JSON = PROC / "climate_drivers_ablation_metrics.json"
OUT_MD = PROC / "climate_drivers_ablation_report.md"
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
            out[f"{name}_{split_name}_cal"] = {
                **cal_s,
                "calibration_method": cal.chosen_,
            }
    return out


def attach_climate(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    cov: dict = {}
    out = df.copy()

    # Met week (national broadcast — same west-coast series on all stations)
    if MET_WEEK.exists():
        met = pd.read_parquet(MET_WEEK)
        met_cols = [
            c
            for c in [
                "met_glorad",
                "met_sun",
                "met_wdsp",
                "met_west_glorad",
                "met_belmullet_glorad",
                "met_belmullet_sun",
                "met_mace_glorad",
            ]
            if c in met.columns
        ]
        keep = ["iso_year", "iso_week"] + met_cols
        met = met[keep].drop_duplicates(["iso_year", "iso_week"])
        # week lags of radiation
        met = met.sort_values(["iso_year", "iso_week"])
        if "met_glorad" in met.columns:
            met["met_glorad_lag1w"] = met["met_glorad"].shift(1)
            met["met_glorad_roll4w"] = met["met_glorad"].rolling(4, min_periods=1).mean()
            met_cols += ["met_glorad_lag1w", "met_glorad_roll4w"]
        if "met_sun" in met.columns:
            met["met_sun_lag1w"] = met["met_sun"].shift(1)
            met_cols += ["met_sun_lag1w"]
        n_before = len(out)
        out = out.merge(met, on=["iso_year", "iso_week"], how="left")
        for c in met_cols:
            if c in out.columns:
                cov[c] = float(out[c].notna().mean())
        cov["met_merge_rows"] = n_before
    else:
        cov["met_week"] = "missing"

    # Rivers — broadcast regional Q
    if RIVERS.exists():
        riv = pd.read_csv(RIVERS)
        riv = riv[riv["parameter"] == "Q"] if "parameter" in riv.columns else riv
        piv = riv.pivot_table(
            index=["iso_year", "iso_week"],
            columns="station_no",
            values="mean_value",
            aggfunc="mean",
        )
        piv = piv.rename(columns={c: f"Q_{c}" for c in piv.columns})
        piv = piv.reset_index()
        # primary Connemara gauges
        want = [c for c in ["Q_31075", "Q_30061", "Q_30031"] if c in piv.columns]
        if want:
            # log1p + lag
            for c in list(want):
                piv[f"{c}_log1p"] = np.log1p(piv[c].clip(lower=0))
                piv[f"{c}_lag1w"] = piv[c].shift(1)
            riv_feats = want + [f"{c}_log1p" for c in want] + [f"{c}_lag1w" for c in want]
            out = out.merge(piv[["iso_year", "iso_week"] + riv_feats], on=["iso_year", "iso_week"], how="left")
            for c in riv_feats:
                cov[c] = float(out[c].notna().mean())
    else:
        cov["rivers"] = "missing"

    # Warming year features
    if WARM.exists():
        w = pd.read_csv(WARM)
        # join on iso_year == year (June context for that year)
        w = w.rename(columns={"year": "iso_year"})
        wfeats = [
            c
            for c in [
                "june_sst_clim_anom",
                "june_sst_trend_residual",
                "warming_year_decade",
            ]
            if c in w.columns
        ]
        out = out.merge(w[["iso_year"] + wfeats], on="iso_year", how="left")
        for c in wfeats:
            cov[c] = float(out[c].notna().mean())
    else:
        cov["warming"] = "missing"

    return out, cov


def main() -> int:
    t0 = time.time()
    if not JOINED.exists():
        print("missing joined features", file=sys.stderr)
        return 1

    df0 = pd.read_parquet(JOINED)
    strong = [f for f in sorted(STRONG_OISST) if f in df0.columns]
    if len(strong) < 9:
        print("strong features incomplete:", strong, file=sys.stderr)
        return 1

    df, cov = attach_climate(df0)
    print("coverage:", json.dumps(cov, indent=2))

    met_feats = [c for c in ["met_glorad", "met_glorad_lag1w", "met_glorad_roll4w", "met_sun", "met_sun_lag1w", "met_wdsp"] if c in df.columns]
    riv_feats = [c for c in df.columns if c.startswith("Q_") and (c.endswith("_log1p") or c in {"Q_31075", "Q_30061"} or c.endswith("_lag1w"))]
    # keep a lean river set
    riv_lean = [c for c in ["Q_31075_log1p", "Q_31075_lag1w", "Q_30061_log1p"] if c in df.columns]
    warm_feats = [c for c in ["june_sst_clim_anom", "warming_year_decade", "june_sst_trend_residual"] if c in df.columns]

    configs = {
        "strong": strong,
        "strong_met_rad": strong + met_feats,
        "strong_river_Q": strong + riv_lean,
        "strong_warming": strong + warm_feats,
        "strong_met_river": strong + met_feats + riv_lean,
        "strong_climate_all": strong + met_feats + riv_lean + warm_feats,
    }
    # drop empty extras
    configs = {k: list(dict.fromkeys(v)) for k, v in configs.items()}

    results = {"_meta": {"target": TARGET, "coverage": cov, "elapsed_s": None}, "runs": {}}
    for label, feats in configs.items():
        print(f"eval {label} n_feats={len(feats)} …", flush=True)
        results["runs"][label] = eval_feature_set(df, feats, label)

    results["_meta"]["elapsed_s"] = round(time.time() - t0, 1)

    # Headline table
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

    # Honest verdict
    best = tab.sort_values("lgbm_test_cal_pr_auc", ascending=False).iloc[0]
    delta_best = float(best["delta_test_cal_vs_strong"])
    if delta_best > 0.01:
        verdict = (
            f"Climate extras **lift** LightGBM test cal PR-AUC vs strong by "
            f"{delta_best:+.4f} (best={best['label']})."
        )
        lift = True
    elif delta_best > 0.002:
        verdict = (
            f"Climate extras show a **marginal** test lift ({delta_best:+.4f} at {best['label']}); "
            "treat as inconclusive / not worth complexity nationally."
        )
        lift = False
    else:
        verdict = (
            f"Climate extras **do not beat** strong nationally (best delta={delta_best:+.4f} "
            f"at {best['label']}). Consistent with ERA5 wind failure: single-point Met / "
            "regional Q / year warming proxy add little beyond SST seasonality for Irish Dinophysis."
        )
        lift = False
    results["verdict"] = {"text": verdict, "lift": lift, "best_label": best["label"], "delta": delta_best}
    results["baseline_reference"] = {
        "metrics_dino_strong_lightgbm_test_calibrated_pr_auc": 0.29326665676644725,
        "this_run_strong_lightgbm_test_cal_pr_auc": base,
        "note": "Small run-to-run differences possible from fillna(0) on extras join; strong-only should match closely.",
    }

    OUT_JSON.write_text(json.dumps(results, indent=2, default=float))

    # Markdown
    lines = [
        "# Climate drivers ablation — Irish Dinophysis nowcast",
        "",
        f"**Generated:** 2026-09-02 (Europe/Dublin).  ",
        f"**Target:** `{TARGET}`. **Model headline:** LightGBM test calibrated PR-AUC.",
        f"**Baseline:** strong 9-feature OISST (`STRONG_OISST`).",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "## Coverage caveats",
        "",
        "- Met radiation/sunshine is **point/regional west-coast** (Mace Head / Belmullet / composite), "
        "broadcast to all Irish HAB stations — sparse spatially for a national panel.",
        "- River Q is **Galway Bay / Connemara** (Owenboliskey 31075, Corrib 30061), not national.",
        "- Warming features are **year-level** June SST anomaly / decade proxy — collinear with SST seasonality.",
        "",
        "### Feature non-null fractions (after left join)",
        "",
        "| feature | fraction non-null |",
        "| --- | ---: |",
    ]
    for k, v in sorted(cov.items()):
        if isinstance(v, float):
            lines.append(f"| `{k}` | {v:.3f} |")
    lines += [
        "",
        "## Results table",
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
        f"Full JSON: `{OUT_JSON.relative_to(ROOT)}`.",
        f"Elapsed: {results['_meta']['elapsed_s']} s.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines))
    print(verdict)
    print("Wrote", OUT_JSON, OUT_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
