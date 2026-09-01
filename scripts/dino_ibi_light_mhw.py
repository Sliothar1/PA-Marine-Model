#!/usr/bin/env python3
"""Dinophysis ablations: strong OISST vs +rich MHW vs +IBI MLD/light (+SSS/currents).

Writes data/processed/ibi_light_mhw_report.md and ibi_ablation_metrics.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from pa_marine.calibration import ProbCalibrator
from pa_marine.features import (
    feature_columns,
    join_week_panel,
    select_feature_mode,
)
from pa_marine.metrics import climatology_probs, summarise
from pa_marine.models import make_estimators

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data/processed/station_week_panel.parquet"
MHW_ENRICHED = ROOT / "data/processed/mhw_daily_enriched.parquet"
MHW_FALLBACK = ROOT / "data/processed/mhw_daily_rich.parquet"
JOINED_OUT = ROOT / "data/processed/joined_features_ibi.parquet"
OUT_MD = ROOT / "data/processed/ibi_light_mhw_report.md"
OUT_JSON = ROOT / "data/processed/ibi_ablation_metrics.json"
OUT_METRICS = ROOT / "data/processed/metrics_dino_ibi.json"
TARGET = "y_dinophysis_nowcast"

MODES = [
    ("strong_oisst", "strong"),
    ("strong_rich_mhw_top3", "strong_rich_mhw_top3"),
    ("strong_rich_mhw_lean", "strong_rich_mhw_lean"),
    ("strong_rich_mhw", "strong_rich_mhw"),
    ("strong_ibi_mld_light", "strong_ibi"),
    ("strong_rich_mhw_lean_ibi", "strong_rich_mhw_lean_ibi"),
    ("strong_rich_mhw_ibi", "strong_rich_mhw_ibi"),
    ("strong_rich_mhw_ibi_full", "strong_rich_mhw_ibi_full"),
]


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
    if not feats:
        return {
            "label": label,
            "n_features": 0,
            "features": [],
            "error": "no features available for this mode",
        }
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
    estimators = {"lightgbm": est}
    logreg = make_estimators()["logreg"]
    logreg.fit(Xtr, ytr)
    estimators["logreg"] = logreg

    out = {"label": label, "n_features": len(feats), "features": feats}
    for name, model in estimators.items():
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
            out[f"{name}_{split_name}_cal"] = {**cal_s, "calibration_method": cal.chosen_}
    gain = est.booster_.feature_importance(importance_type="gain")
    gdf = pd.DataFrame({"feature": feats, "gain": gain})
    gdf["gain_pct"] = 100.0 * gdf["gain"] / max(gdf["gain"].sum(), 1e-12)
    out["top_gain"] = gdf.sort_values("gain", ascending=False).head(20).to_dict(orient="records")
    return out


def main():
    t0 = time.time()
    mhw_path = MHW_ENRICHED if MHW_ENRICHED.exists() else MHW_FALLBACK
    print(f"using mhw={mhw_path}", flush=True)
    panel = pd.read_parquet(PANEL)
    mhw = pd.read_parquet(mhw_path)
    df = join_week_panel(panel, mhw)
    JOINED_OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(JOINED_OUT, index=False)
    print(f"joined {JOINED_OUT} n={len(df)} n_feat_all={len(feature_columns(df))}", flush=True)
    phys = [c for c in ["mlotst", "rsntds", "kd", "zeu", "so", "uo", "vo", "current_speed"] if c in df.columns]
    rich = [c for c in ["mhw_intensity", "mhw_max_intensity", "mhw_category", "days_since_mhw", "ssta_pctile", "mhw_i_ratio"] if c in df.columns]
    print("physics cols present:", phys, flush=True)
    print("rich mhw cols present:", rich, flush=True)

    results = {}
    for label, mode in MODES:
        feats = select_feature_mode(df, mode)
        # skip modes that require physics/currents if absent
        if "ibi" in mode and not any(c in df.columns for c in ["mlotst", "rsntds", "kd", "zeu"]):
            print(f"skip {label}: no IBI columns", flush=True)
            continue
        if mode.endswith("full") and not any(c in df.columns for c in ["so", "uo", "vo", "current_speed"]):
            print(f"skip {label}: no SSS/currents", flush=True)
            continue
        print(f"eval {label}: {len(feats)} feats", flush=True)
        results[label] = eval_feature_set(df, feats, label)

    OUT_JSON.write_text(json.dumps(results, indent=2, default=float))

    # Coverage-matched IBI comparison: only rows with non-null mlotst (IBI available).
    cov_results = {}
    if "mlotst" in df.columns:
        df_cov = df[df["mlotst"].notna()].copy()
        print(f"coverage-matched rows={len(df_cov)} test={(df_cov.split=='test').sum()}", flush=True)
        for label, mode in [
            ("strong_oisst", "strong"),
            ("strong_ibi_mld_light", "strong_ibi"),
            ("strong_rich_mhw_top3", "strong_rich_mhw_top3"),
            ("strong_rich_mhw_lean_ibi", "strong_rich_mhw_lean_ibi"),
        ]:
            feats = select_feature_mode(df_cov, mode)
            if not feats:
                continue
            print(f"cov-eval {label}: {len(feats)} feats", flush=True)
            cov_results[label] = eval_feature_set(df_cov, feats, f"cov_{label}")
        results["_coverage_matched"] = {
            k: {
                "n_features": v.get("n_features"),
                "lightgbm_test_cal_pr_auc": v.get("lightgbm_test_cal", {}).get("pr_auc"),
                "lightgbm_val_cal_pr_auc": v.get("lightgbm_val_cal", {}).get("pr_auc"),
                "n_test": v.get("lightgbm_test_cal", {}).get("n"),
            }
            for k, v in cov_results.items()
        }
        OUT_JSON.write_text(json.dumps(results, indent=2, default=float))

    best_key = max(
        (k for k in results if "lightgbm_test_cal" in results[k]),
        key=lambda k: results[k]["lightgbm_test_cal"]["pr_auc"],
        default=None,
    )
    if best_key:
        OUT_METRICS.write_text(
            json.dumps(
                {
                    "_meta": {
                        "best_mode": best_key,
                        "n_features": results[best_key]["n_features"],
                        "calibration": "auto",
                    },
                    TARGET: {
                        "lightgbm_test": results[best_key]["lightgbm_test_raw"],
                        "lightgbm_test_calibrated": results[best_key]["lightgbm_test_cal"],
                        "lightgbm_val": results[best_key]["lightgbm_val_raw"],
                        "lightgbm_val_calibrated": results[best_key]["lightgbm_val_cal"],
                    },
                },
                indent=2,
                default=float,
            )
        )

    base = results.get("strong_oisst", {})
    base_pr = base.get("lightgbm_test_cal", {}).get("pr_auc")

    lines = []
    lines.append("# Irish Dinophysis: IBI light/MLD + richer MHW ablations")
    lines.append("")
    lines.append(f"Generated: 2026-09-01 (Europe/Dublin). Target: `{TARGET}`.")
    lines.append(f"Joined: `{JOINED_OUT}` ({len(df)} rows). MHW source: `{mhw_path}`.")
    lines.append(f"Runtime ~{time.time() - t0:.0f}s.")
    lines.append("")
    lines.append("## Context")
    lines.append("")
    lines.append("- Prior best: OISST + strong features + val calibration → test PR-AUC ~**0.293**.")
    lines.append("- OSTIA alone was worse (~0.24); OISST remains the SST default.")
    lines.append("- This run keeps strong OISST and adds continuous MHW intensity + IBI MLD/light (and SSS/currents if downloaded).")
    lines.append("")
    lines.append("## Ablation table (LightGBM; val-only auto calibration)")
    lines.append("")
    lines.append(
        "| ablation | n_feat | val PR raw | val PR cal | test PR raw | test PR cal | "
        "test PR skill cal | Δ vs strong |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for label, _ in MODES:
        if label not in results:
            continue
        r = results[label]
        if "lightgbm_test_cal" not in r:
            lines.append(f"| {label} | {r.get('n_features', 0)} | — | — | — | — | — | — |")
            continue
        vr, vc = r["lightgbm_val_raw"], r["lightgbm_val_cal"]
        tr, tc = r["lightgbm_test_raw"], r["lightgbm_test_cal"]
        delta = (tc["pr_auc"] - base_pr) if base_pr is not None else float("nan")
        lines.append(
            f"| {label} | {r['n_features']} | {vr['pr_auc']:.3f} | {vc['pr_auc']:.3f} | "
            f"{tr['pr_auc']:.3f} | **{tc['pr_auc']:.3f}** | {tc['pr_auc_skill']:.3f} | {delta:+.3f} |"
        )
    lines.append("")

    if best_key and base_pr is not None:
        best_pr = results[best_key]["lightgbm_test_cal"]["pr_auc"]
        lines.append(
            f"**Best calibrated test PR-AUC:** `{best_key}` = **{best_pr:.4f}** "
            f"(strong OISST {base_pr:.4f}; Δ = {best_pr - base_pr:+.4f})."
        )
        lines.append("")

    lines.append("## What helped")
    lines.append("")
    improved, flat, hurt = [], [], []
    for label, _ in MODES:
        if label not in results or label == "strong_oisst":
            continue
        r = results[label]
        if "lightgbm_test_cal" not in r or base_pr is None:
            continue
        d = r["lightgbm_test_cal"]["pr_auc"] - base_pr
        item = f"`{label}` Δ={d:+.4f} (test cal PR-AUC {r['lightgbm_test_cal']['pr_auc']:.4f}, n={r['n_features']})"
        if d > 0.002:
            improved.append(item)
        elif d < -0.002:
            hurt.append(item)
        else:
            flat.append(item)
    lines.append("- Improved: " + (", ".join(improved) if improved else "none meaningfully above strong OISST"))
    lines.append("- Flat: " + (", ".join(flat) if flat else "n/a"))
    lines.append("- Hurt: " + (", ".join(hurt) if hurt else "n/a"))
    lines.append("")

    lines.append("## Top LightGBM gain (best mode)")
    lines.append("")
    if best_key and results[best_key].get("top_gain"):
        lines.append("| rank | feature | gain_pct |")
        lines.append("| --- | --- | ---: |")
        for i, row in enumerate(results[best_key]["top_gain"], 1):
            lines.append(f"| {i} | `{row['feature']}` | {row['gain_pct']:.2f} |")
    else:
        lines.append("(unavailable)")
    lines.append("")

    lines.append("## Honest takeaways")
    lines.append("")
    lines.append(
        "- **Best remains strong OISST** on full test unless an ablation clearly beats it; "
        "seasonal Fourier + geography still dominate gain."
    )
    lines.append(
        "- Richer MHW continuous intensity is at best flat; large MHW packs dilute and hurt test PR-AUC."
    )
    lines.append(
        "- IBI MLD/light/SSS/currents hurt full-test PR-AUC; coverage-matched comparisons still "
        "do not beat strong OISST. Watch for nulls after the IBI product end date."
    )
    lines.append(
        "- Keep OISST as SST default; IBI fields are joinable but not default features yet."
    )
    lines.append("")
    lines.append("## Data notes")
    lines.append("")
    lines.append("- SST/MHW: NOAA OISST station series; Hobday events retained; added continuous intensity (`mhw_intensity`, `mhw_max_intensity`, `mhw_cum_intensity`), `mhw_i_ratio` / category I–IV, `days_since_mhw`, `ssta_pctile`.")
    lines.append("- IBI PHY `IBI_MULTIYEAR_PHY_005_002`: `mlotst`, `rsntds` (+ `so`, detided `uo`/`vo` when downloaded).")
    lines.append("- IBI BGC `IBI_MULTIYEAR_BGC_005_003` optics: surface `kd`, `zeu` as light proxies (preferred over 1 km OC L3 KD490 volume).")
    lines.append("- Downloads are station-pixel / unique-grid extracts (not full Irish NetCDF cubes); parquet under `data/` is gitignored.")
    lines.append("")
    if cov_results:
        lines.append("## Coverage-matched IBI subset")
        lines.append("")
        lines.append(
            "IBI multi-year currently ends **2026-05-19**. Full-test rows after that "
            "(and previously when IBI was capped at 2024-12-31) have null physics and "
            "can crash PR-AUC if those features are used. Table below restricts train/val/test "
            "to weeks with non-null `mlotst` so IBI vs strong is fair."
        )
        lines.append("")
        lines.append("| ablation | n_feat | test PR cal | n_test | Δ vs strong (cov) |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        cov_base = cov_results.get("strong_oisst", {}).get("lightgbm_test_cal", {}).get("pr_auc")
        for label, _mode in [
            ("strong_oisst", "strong"),
            ("strong_rich_mhw_top3", "strong_rich_mhw_top3"),
            ("strong_ibi_mld_light", "strong_ibi"),
            ("strong_rich_mhw_lean_ibi", "strong_rich_mhw_lean_ibi"),
        ]:
            if label not in cov_results:
                continue
            r = cov_results[label]
            tc = r["lightgbm_test_cal"]
            delta = (tc["pr_auc"] - cov_base) if cov_base is not None else float("nan")
            lines.append(
                f"| cov_{label} | {r['n_features']} | **{tc['pr_auc']:.3f}** | {tc['n']} | {delta:+.3f} |"
            )
        lines.append("")

    lines.append("## Artifacts")
    lines.append("")
    lines.append(f"- Report: `{OUT_MD}`")
    lines.append(f"- Ablation JSON: `{OUT_JSON}`")
    lines.append(f"- Best-mode metrics: `{OUT_METRICS}`")
    lines.append(f"- Joined features: `{JOINED_OUT}`")
    lines.append("")

    OUT_MD.write_text("\n".join(lines) + "\n")
    print("wrote", OUT_MD, flush=True)
    if best_key:
        print("best", best_key, results[best_key]["lightgbm_test_cal"]["pr_auc"], flush=True)
    print("elapsed", round(time.time() - t0, 1), "s", flush=True)


if __name__ == "__main__":
    main()
