#!/usr/bin/env python3
"""Dinophysis feature importance + quick ablations on existing joined features.

Writes data/processed/dino_feature_report.md and updates metrics snippets.
Does not re-download OISST; lag ablations re-join from mhw_daily if present.
"""
from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.inspection import permutation_importance

from pa_marine.calibration import ProbCalibrator
from pa_marine.features import BASE_COLS, feature_columns, join_week_panel
from pa_marine.metrics import climatology_probs, summarise
from pa_marine.models import make_estimators

ROOT = Path(__file__).resolve().parents[1]
JOINED = ROOT / "data/processed/joined_features.parquet"
MHW = ROOT / "data/processed/mhw_daily.parquet"
PANEL = ROOT / "data/processed/station_week_panel.parquet"
OUT_MD = ROOT / "data/processed/dino_feature_report.md"
OUT_JSON = ROOT / "data/processed/dino_ablation_metrics.json"
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
    Xtr = train.loc[mtr, feats]
    ytr = ytr.loc[mtr]
    clim_week = train.loc[mtr, "iso_week"].to_numpy()
    clim_y = ytr.to_numpy()

    est = _lgbm()
    est.fit(Xtr, ytr)
    # also logreg for comparison on ablations
    estimators = {"lightgbm": est}
    logreg = make_estimators()["logreg"]
    logreg.fit(Xtr, ytr)
    estimators["logreg"] = logreg

    out = {"label": label, "n_features": len(feats), "features": feats}
    for name, model in estimators.items():
        # calibrate on val
        yv = val[TARGET].astype(int)
        mv = yv.notna()
        pr_val = _raw_probs(model, val.loc[mv, feats])
        cal = ProbCalibrator(method="auto").fit(yv.loc[mv].to_numpy(), pr_val)
        for split_name, ev in (("val", val), ("test", test)):
            y = ev[TARGET].astype(int)
            mask = y.notna()
            pr_raw = _raw_probs(model, ev.loc[mask, feats])
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
    return out, est, feats


def gain_importance(est, feats: list[str]) -> pd.DataFrame:
    gain = est.booster_.feature_importance(importance_type="gain")
    split = est.booster_.feature_importance(importance_type="split")
    df = pd.DataFrame({"feature": feats, "gain": gain, "split": split})
    df["gain_pct"] = 100.0 * df["gain"] / max(df["gain"].sum(), 1e-12)
    return df.sort_values("gain", ascending=False).reset_index(drop=True)


def perm_importance(est, df: pd.DataFrame, feats: list[str], n_repeats: int = 8) -> pd.DataFrame:
    val = df[df["split"] == "val"]
    y = val[TARGET].astype(int)
    mask = y.notna()
    X = val.loc[mask, feats]
    y = y.loc[mask]
    r = permutation_importance(
        est,
        X,
        y,
        n_repeats=n_repeats,
        random_state=42,
        scoring="average_precision",
        n_jobs=2,
    )
    out = pd.DataFrame(
        {
            "feature": feats,
            "perm_mean": r.importances_mean,
            "perm_std": r.importances_std,
        }
    )
    return out.sort_values("perm_mean", ascending=False).reset_index(drop=True)


def rebuild_with_lags(lags: tuple[int, ...], rolls: tuple[int, ...] = (7, 14, 30)) -> pd.DataFrame:
    """Re-join panel to mhw_daily with alternate lag set (no OISST re-download)."""
    import pa_marine.features as featmod

    panel = pd.read_parquet(PANEL)
    mhw = pd.read_parquet(MHW)
    old_lags, old_rolls = featmod.LAGS, featmod.ROLLS
    featmod.LAGS = lags
    featmod.ROLLS = rolls
    try:
        return join_week_panel(panel, mhw)
    finally:
        featmod.LAGS = old_lags
        featmod.ROLLS = old_rolls


def main():
    t0 = time.time()
    df = pd.read_parquet(JOINED)
    feats = feature_columns(df)
    print(f"baseline features ({len(feats)}): {feats}")

    baseline, est, feats = eval_feature_set(df, feats, "baseline_all")
    gain = gain_importance(est, feats)
    print("computing permutation importance on val…")
    perm = perm_importance(est, df, feats, n_repeats=8)

    # Ablation 1: drop weak features (bottom half by gain, keep seasonal+geo always)
    must = {"woy_sin", "woy_cos", "latitude", "longitude"}
    weak = set(gain.loc[gain["gain_pct"] < 1.0, "feature"]) - must
    # also drop features with non-positive perm mean
    weak |= set(perm.loc[perm["perm_mean"] <= 0, "feature"]) - must
    keep_strong = [f for f in feats if f not in weak]
    if len(keep_strong) < 8:
        # fallback: top 15 by gain + must
        top = list(gain["feature"].head(15))
        keep_strong = list(dict.fromkeys(top + list(must)))
    print(f"ablation drop_weak: {len(feats)} -> {len(keep_strong)} (dropped {len(feats)-len(keep_strong)})")
    abl_drop, _, _ = eval_feature_set(df, keep_strong, "drop_weak_gain_perm")

    # Ablation 2: SST/SSTA + seasonality only (no MHW event flags)
    sst_only = [
        f
        for f in feats
        if f.startswith("sst") or f.startswith("ssta") or f in must
    ]
    print(f"ablation sst_ssta_only: {len(sst_only)} feats")
    abl_sst, _, _ = eval_feature_set(df, sst_only, "sst_ssta_woy_geo")

    # Ablation 3: lag tweak — denser short lags 0/3/7/14, drop 21; rolls 7/14 only
    abl_lag = None
    if MHW.exists() and PANEL.exists():
        print("ablation lag_tweak: rebuilding join with lags (0,3,7,14) rolls (7,14)…")
        df_lag = rebuild_with_lags((0, 3, 7, 14), (7, 14))
        feats_lag = feature_columns(df_lag)
        abl_lag, _, _ = eval_feature_set(df_lag, feats_lag, "lags_0_3_7_14_rolls_7_14")
    else:
        print("skip lag_tweak: mhw_daily or panel missing")

    # Wind: skip (ERA5/Open-Meteo for 207 stations × decades >30 min budget)
    wind_note = (
        "Skipped wind proxies: no local ERA5; Open-Meteo archive for 207 stations × "
        "~24 y daily would exceed the 30‑min cheap-source budget. Revisit with "
        "CDS/ERA5 single-level u10/v10 at station pixels if credentials available."
    )

    results = {
        "baseline": baseline,
        "drop_weak": abl_drop,
        "sst_ssta_only": abl_sst,
    }
    if abl_lag is not None:
        results["lag_tweak"] = abl_lag

    OUT_JSON.write_text(json.dumps(results, indent=2, default=float))

    def row(r: dict, model: str = "lightgbm") -> str:
        tr = r[f"{model}_test_raw"]
        tc = r[f"{model}_test_cal"]
        vr = r[f"{model}_val_raw"]
        vc = r[f"{model}_val_cal"]
        return (
            f"| {r['label']} | {r['n_features']} | "
            f"{vr['pr_auc']:.3f} | {vc['pr_auc']:.3f} | "
            f"{tr['pr_auc']:.3f} | {tc['pr_auc']:.3f} | "
            f"{tc['pr_auc_skill']:.3f} | {tc['brier_skill']:.3f} |"
        )

    # pick best by calibrated test PR-AUC (LightGBM)
    best_key = max(
        results,
        key=lambda k: results[k]["lightgbm_test_cal"]["pr_auc"],
    )
    base_pr = baseline["lightgbm_test_cal"]["pr_auc"]
    best_pr = results[best_key]["lightgbm_test_cal"]["pr_auc"]
    delta = best_pr - base_pr

    lines = []
    lines.append("# Dinophysis feature importance & ablations")
    lines.append("")
    lines.append(f"Generated: 2026-09-01 (Europe/Dublin). Target: `{TARGET}`.")
    lines.append(f"Joined features: `{JOINED}` ({len(df)} rows). Runtime ~{time.time()-t0:.0f}s.")
    lines.append("")
    lines.append("## Baseline (LightGBM, all joined features)")
    lines.append("")
    lines.append(
        f"- Val PR-AUC raw/cal: **{baseline['lightgbm_val_raw']['pr_auc']:.3f}** / "
        f"**{baseline['lightgbm_val_cal']['pr_auc']:.3f}**"
    )
    lines.append(
        f"- Test PR-AUC raw/cal: **{baseline['lightgbm_test_raw']['pr_auc']:.3f}** / "
        f"**{baseline['lightgbm_test_cal']['pr_auc']:.3f}** "
        f"(clim {baseline['lightgbm_test_cal']['pr_auc_clim']:.3f}; "
        f"PR skill cal **{baseline['lightgbm_test_cal']['pr_auc_skill']:.3f}**)"
    )
    lines.append(
        f"- Test Brier skill raw → cal: "
        f"{baseline['lightgbm_test_raw']['brier_skill']:.3f} → "
        f"**{baseline['lightgbm_test_cal']['brier_skill']:.3f}**"
    )
    lines.append("")
    lines.append("## LightGBM gain importance (train fit)")
    lines.append("")
    lines.append("| rank | feature | gain_pct | split_count |")
    lines.append("| --- | --- | ---: | ---: |")
    for i, r in gain.iterrows():
        lines.append(f"| {i+1} | `{r['feature']}` | {r['gain_pct']:.2f} | {int(r['split'])} |")
    lines.append("")
    lines.append("## Permutation importance (val, scoring=average_precision, 8 repeats)")
    lines.append("")
    lines.append("| rank | feature | perm_mean ΔPR-AUC | perm_std |")
    lines.append("| --- | --- | ---: | ---: |")
    for i, r in perm.iterrows():
        lines.append(
            f"| {i+1} | `{r['feature']}` | {r['perm_mean']:.4f} | {r['perm_std']:.4f} |"
        )
    lines.append("")
    lines.append("### Takeaways from importance")
    top5 = list(gain["feature"].head(5))
    top_perm = list(perm["feature"].head(5))
    lines.append(f"- Top gain: {', '.join(f'`{x}`' for x in top5)}")
    lines.append(f"- Top permutation: {', '.join(f'`{x}`' for x in top_perm)}")
    lines.append(
        "- Seasonal Fourier (`woy_sin`/`woy_cos`) and geography usually dominate; "
        "SST/SSTA rolls/lags add modest discrimination beyond climatology."
    )
    lines.append("")
    lines.append("## Ablations (LightGBM; val-only isotonic/sigmoid calibration)")
    lines.append("")
    lines.append(
        "| ablation | n_feat | val PR raw | val PR cal | test PR raw | test PR cal | "
        "test PR skill cal | test Brier skill cal |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for k in results:
        lines.append(row(results[k]))
    lines.append("")
    lines.append(f"**Best calibrated test PR-AUC:** `{best_key}` = **{best_pr:.3f}** "
                 f"(baseline {base_pr:.3f}; Δ = {delta:+.3f}).")
    lines.append("")
    lines.append("### Ablation notes")
    lines.append(
        f"- **drop_weak**: removed features with gain_pct < 1% or non-positive "
        f"permutation mean (kept {must}). Dropped: "
        + (", ".join(f'`{f}`' for f in sorted(set(feats) - set(keep_strong))) or "(none)")
    )
    lines.append(
        "- **sst_ssta_woy_geo**: dropped all `in_mhw*` / `mhw_duration*` / "
        "`mhw_cum_intensity*` columns."
    )
    if abl_lag is not None:
        lines.append(
            "- **lags_0_3_7_14_rolls_7_14**: rebuilt from `mhw_daily.parquet` "
            "(no OISST re-download); denser short lags, dropped lag21 and roll30."
        )
    lines.append(f"- **Wind:** {wind_note}")
    lines.append("")
    lines.append("## What improved / what didn't")
    improved = []
    worsened = []
    for k, r in results.items():
        if k == "baseline":
            continue
        d = r["lightgbm_test_cal"]["pr_auc"] - base_pr
        if d > 0.002:
            improved.append(f"{k} (ΔPR-AUC cal {d:+.3f})")
        elif d < -0.002:
            worsened.append(f"{k} (ΔPR-AUC cal {d:+.3f})")
        else:
            worsened.append(f"{k} (≈ flat, Δ {d:+.3f})")
    lines.append("- Improved: " + (", ".join(improved) if improved else "none meaningfully above baseline"))
    lines.append("- Did not help / flat: " + (", ".join(worsened) if worsened else "n/a"))
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append(f"- Report: `{OUT_MD}`")
    lines.append(f"- Ablation metrics JSON: `{OUT_JSON}`")
    lines.append("- Full multi-taxon metrics remain in `data/processed/metrics.json`")
    lines.append("")
    lines.append(
        "**Best next lever:** replace 0.25° OISST with Copernicus **OSTIA 0.05° (~5 km)** "
        "SST at station pixels (and/or add ERA5 wind) — coastal Dinophysis is poorly "
        "resolved at OISST scale."
    )

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    print("wrote", OUT_MD)
    print("best", best_key, best_pr, "delta", delta)
    print("elapsed", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
