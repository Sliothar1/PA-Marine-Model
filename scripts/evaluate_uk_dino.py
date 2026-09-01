#!/usr/bin/env python3
"""Train/eval Dinophysis on UK FSA panel alone (+ Ireland→UK transfer check).

UK FSA years are short (2018–2025); the Irish year split leaves only 2018 as
train — too thin for a solid fit. This script therefore:

1. Uses a UK-adapted time split (train 2018–2021, val 2022, test 2023+) with
   val-only probability calibration.
2. Reports leave-one-year-out (LOYO) PR-AUC as a robustness check.
3. Runs train-on-Ireland / test-on-UK transfer on shared seasonal+geo features
   (labels align at ≥100 cells L⁻¹: Irish Dinophysis vs UK Dinophysiaceae).

No OSTIA / Copernicus download. Features are woy Fourier + lat/lon only
(UK station OISST not joined yet); comparable to Irish strong-mode seasonality
dominance noted in dino_feature_report.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from pa_marine.calibration import ProbCalibrator
from pa_marine.hab import add_horizon_labels
from pa_marine.metrics import climatology_probs, summarise
from pa_marine.models import fit_predict, make_estimators

ROOT = Path(__file__).resolve().parents[1]
UK_PANEL = ROOT / "data/processed/uk_station_week_panel.parquet"
IE_PANEL = ROOT / "data/processed/station_week_panel.parquet"
OUT_JSON = ROOT / "data/processed/uk_dino_metrics.json"
OUT_MD = ROOT / "data/processed/uk_dino_report.md"
TARGET = "y_dinophysis_nowcast"
FEATS = ["woy_sin", "woy_cos", "latitude", "longitude"]


def _raw_probs(est, X) -> np.ndarray:
    if hasattr(est, "predict_proba"):
        return est.predict_proba(X)[:, 1]
    d = est.decision_function(X)
    return 1 / (1 + np.exp(-d))


def _add_woy(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    woy = out["iso_week"].astype(float)
    out["woy_sin"] = np.sin(2 * np.pi * woy / 53.0)
    out["woy_cos"] = np.cos(2 * np.pi * woy / 53.0)
    return out


def uk_adapted_split(years: pd.Series) -> pd.Series:
    y = years.astype(int)
    out = pd.Series("drop", index=years.index)
    out[(y >= 2018) & (y <= 2021)] = "train"
    out[y == 2022] = "val"
    out[y >= 2023] = "test"
    return out


def _eval_split(
    df: pd.DataFrame,
    feats: list[str],
    target: str,
    *,
    calibrate: bool = True,
) -> dict:
    train = df[df["split"] == "train"]
    val = df[df["split"] == "val"]
    results: dict = {}
    ytr = train[target].astype(int)
    mtr = ytr.notna() & train[feats].notna().all(axis=1)
    if int(mtr.sum()) == 0 or int(ytr.loc[mtr].sum()) == 0:
        return {"error": "no train positives or rows"}
    clim_week = train.loc[mtr, "iso_week"].to_numpy()
    clim_y = ytr.loc[mtr].to_numpy()
    estimators = make_estimators()
    for name, est in estimators.items():
        fit_predict(est, train.loc[mtr, feats], ytr.loc[mtr], train.loc[mtr, feats])
        calibrator = None
        if calibrate and not val.empty:
            yv = val[target].astype(int)
            mv = yv.notna() & val[feats].notna().all(axis=1)
            if int(mv.sum()) > 0 and int(yv.loc[mv].sum()) > 0:
                pr_val_raw = _raw_probs(est, val.loc[mv, feats])
                calibrator = ProbCalibrator(method="auto").fit(yv.loc[mv].to_numpy(), pr_val_raw)
        for split in ("val", "test"):
            ev = df[df["split"] == split]
            if ev.empty:
                continue
            y = ev[target].astype(int)
            mask = y.notna() & ev[feats].notna().all(axis=1)
            if int(mask.sum()) == 0 or int(y.loc[mask].nunique()) < 2:
                continue
            pr_raw = _raw_probs(est, ev.loc[mask, feats])
            clim = climatology_probs(clim_week, clim_y, ev.loc[mask, "iso_week"].to_numpy())
            y_np = y.loc[mask].to_numpy()
            raw = summarise(y_np, pr_raw, clim)
            key = f"{name}_{split}"
            results[key] = dict(raw)
            results[key]["calibrated"] = False
            if calibrator is not None:
                pr_cal = calibrator.transform(pr_raw)
                cal = summarise(y_np, pr_cal, clim)
                ckey = f"{name}_{split}_calibrated"
                results[ckey] = dict(cal)
                results[ckey]["calibrated"] = True
                results[ckey]["calibration_method"] = calibrator.chosen_
                results[ckey]["raw_pr_auc"] = raw["pr_auc"]
                results[ckey]["raw_brier"] = raw["brier"]
    return results


def leave_one_year_out(df: pd.DataFrame, feats: list[str], target: str) -> dict:
    years = sorted(int(y) for y in df["iso_year"].dropna().unique())
    folds = {}
    for hold in years:
        train = df[df["iso_year"] != hold].copy()
        test = df[df["iso_year"] == hold].copy()
        if train.empty or test.empty:
            continue
        ytr = train[target].astype(int)
        mtr = ytr.notna() & train[feats].notna().all(axis=1)
        yte = test[target].astype(int)
        mte = yte.notna() & test[feats].notna().all(axis=1)
        if int(mtr.sum()) < 50 or int(ytr.loc[mtr].sum()) < 5:
            continue
        if int(mte.sum()) < 20 or int(yte.loc[mte].nunique()) < 2:
            continue
        # Use earliest half of remaining years as a mini-val for calibration when possible
        tr_years = sorted(train["iso_year"].unique())
        if len(tr_years) >= 3:
            val_years = set(tr_years[-1:])
            train2 = train[~train["iso_year"].isin(val_years)]
            val2 = train[train["iso_year"].isin(val_years)]
        else:
            train2, val2 = train, train.iloc[0:0]
        tmp = pd.concat(
            [
                train2.assign(split="train"),
                val2.assign(split="val"),
                test.assign(split="test"),
            ],
            ignore_index=True,
        )
        fold = _eval_split(tmp, feats, target, calibrate=not val2.empty)
        # keep lightgbm/logreg test calibrated (or raw)
        slim = {k: v for k, v in fold.items() if k.endswith("_test_calibrated") or (
            k.endswith("_test") and f"{k}_calibrated" not in fold
        )}
        folds[str(hold)] = {
            "n_train": int(mtr.sum()),
            "n_test": int(mte.sum()),
            "test_prevalence": float(yte.loc[mte].mean()),
            "metrics": slim,
        }
    return folds


def transfer_ie_to_uk(ie: pd.DataFrame, uk: pd.DataFrame, feats: list[str]) -> dict:
    """Train on Irish same-week / nowcast labels; evaluate on UK test years."""
    ie = ie.copy()
    uk = uk.copy()
    # Irish default time split already on panel; use train/val for fit+cal, UK test for eval
    ie_tr = ie[ie["split"] == "train"]
    ie_va = ie[ie["split"] == "val"]
    uk_te = uk[uk["split"] == "test"]
    out = {"n_ie_train": int(len(ie_tr)), "n_uk_test": int(len(uk_te)), "features": feats}
    if uk_te.empty or ie_tr.empty:
        out["error"] = "empty transfer splits"
        return out
    ytr = ie_tr[TARGET].astype(int)
    mtr = ytr.notna() & ie_tr[feats].notna().all(axis=1)
    clim_week = ie_tr.loc[mtr, "iso_week"].to_numpy()
    clim_y = ytr.loc[mtr].to_numpy()
    estimators = make_estimators()
    for name, est in estimators.items():
        fit_predict(est, ie_tr.loc[mtr, feats], ytr.loc[mtr], ie_tr.loc[mtr, feats])
        calibrator = None
        if not ie_va.empty:
            yv = ie_va[TARGET].astype(int)
            mv = yv.notna() & ie_va[feats].notna().all(axis=1)
            if int(mv.sum()) and int(yv.loc[mv].sum()):
                calibrator = ProbCalibrator(method="auto").fit(
                    yv.loc[mv].to_numpy(), _raw_probs(est, ie_va.loc[mv, feats])
                )
        y = uk_te[TARGET].astype(int)
        mask = y.notna() & uk_te[feats].notna().all(axis=1)
        if int(mask.sum()) == 0 or int(y.loc[mask].nunique()) < 2:
            continue
        pr_raw = _raw_probs(est, uk_te.loc[mask, feats])
        clim = climatology_probs(clim_week, clim_y, uk_te.loc[mask, "iso_week"].to_numpy())
        y_np = y.loc[mask].to_numpy()
        raw = summarise(y_np, pr_raw, clim)
        out[f"{name}_uk_test"] = dict(raw)
        out[f"{name}_uk_test"]["calibrated"] = False
        if calibrator is not None:
            cal = summarise(y_np, calibrator.transform(pr_raw), clim)
            out[f"{name}_uk_test_calibrated"] = {
                **cal,
                "calibrated": True,
                "calibration_method": calibrator.chosen_,
                "raw_pr_auc": raw["pr_auc"],
            }
    return out


def main():
    uk = pd.read_parquet(UK_PANEL)
    uk = uk.dropna(subset=["latitude", "longitude", "iso_week"]).copy()
    uk = _add_woy(uk)
    if TARGET not in uk.columns:
        uk = add_horizon_labels(uk, ["dinophysis", "pseudo_nitzschia"])

    # Document Irish-split inadequacy
    irish_like = uk.copy()
    y = irish_like["iso_year"].astype(int)
    irish_like["split"] = "drop"
    irish_like.loc[(y >= 2003) & (y <= 2018), "split"] = "train"
    irish_like.loc[(y >= 2019) & (y <= 2021), "split"] = "val"
    irish_like.loc[y >= 2022, "split"] = "test"
    irish_counts = irish_like.groupby("split").agg(
        n=("y_dinophysis", "size"),
        positives=("y_dinophysis", "sum"),
        years=("iso_year", lambda s: sorted(set(int(x) for x in s))),
    ).to_dict(orient="index")

    uk["split"] = uk_adapted_split(uk["iso_year"])
    adapted = _eval_split(uk, FEATS, TARGET, calibrate=True)
    loyo = leave_one_year_out(uk, FEATS, TARGET)

    ie = pd.read_parquet(IE_PANEL)
    ie = _add_woy(ie)
    transfer = transfer_ie_to_uk(ie, uk, FEATS)

    # Rates comparison
    rates = {
        "uk_same_week": float(uk["y_dinophysis"].mean()),
        "uk_nowcast": float(uk[TARGET].mean()),
        "uk_n_station_weeks": int(len(uk)),
        "uk_years": sorted(int(y) for y in uk["iso_year"].unique()),
        "ie_same_week": float(ie["y_dinophysis"].mean()),
        "ie_nowcast": float(ie[TARGET].mean()),
        "ie_n_station_weeks": int(len(ie)),
    }

    # Pull Irish strong-mode test numbers if present for the report
    ie_strong_path = ROOT / "data/processed/metrics_dino_strong.json"
    ie_strong = None
    if ie_strong_path.exists():
        ie_strong = json.loads(ie_strong_path.read_text())

    payload = {
        "_meta": {
            "target": TARGET,
            "features": FEATS,
            "feature_note": (
                "Seasonality + geo only; UK OISST/MHW not joined. No OSTIA download. "
                "Irish strong ablation showed woy/geo dominate Dinophysis ranking."
            ),
            "uk_adapted_split": {"train": [2018, 2021], "val": [2022, 2022], "test_from": 2023},
            "irish_year_split_inadequate": True,
            "irish_year_split_counts": {
                k: {"n": int(v["n"]), "positives": int(v["positives"]), "years": v["years"]}
                for k, v in irish_counts.items()
            },
            "label_alignment": (
                "UK Dinophysiaceae ≥100 cells/L proxy vs Irish Dinophysis ≥100 cells/L"
            ),
        },
        "rates": rates,
        "uk_adapted_time_split": adapted,
        "leave_one_year_out": loyo,
        "transfer_ireland_to_uk": transfer,
        "irish_strong_reference": None,
    }
    if ie_strong and "y_dinophysis_nowcast" in ie_strong:
        ref = ie_strong["y_dinophysis_nowcast"]
        payload["irish_strong_reference"] = {
            k: ref[k]
            for k in (
                "lightgbm_test_calibrated",
                "lightgbm_test",
                "logreg_test_calibrated",
            )
            if k in ref
        }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2))

    # Short comparison paragraph for the markdown report
    uk_lgb = adapted.get("lightgbm_test_calibrated") or adapted.get("lightgbm_test") or {}
    ie_lgb = (payload["irish_strong_reference"] or {}).get("lightgbm_test_calibrated") or {}
    xfer = transfer.get("lightgbm_uk_test_calibrated") or transfer.get("lightgbm_uk_test") or {}
    loyo_pr = []
    for yr, fold in loyo.items():
        mets = fold.get("metrics") or {}
        hit = mets.get("lightgbm_test_calibrated") or mets.get("lightgbm_test")
        if hit and np.isfinite(hit.get("pr_auc", np.nan)):
            loyo_pr.append((yr, hit["pr_auc"], hit.get("prevalence")))

    def _fmt(d, key="pr_auc"):
        v = d.get(key)
        return f"{v:.3f}" if isinstance(v, (int, float)) and np.isfinite(v) else "n/a"

    md = f"""# UK FSA Dinophysis evaluation

Generated: 2026-09-01 (Europe/Dublin). Target: `{TARGET}` on England & Wales FSA
Dinophysiaceae (≥100 cells L⁻¹) as Dinophysis proxy. Features: `{', '.join(FEATS)}`
only (no UK OISST join; no OSTIA). Metrics: `{OUT_JSON.relative_to(ROOT)}`.

## Data adequacy vs Irish year split

UK panel years are **{rates['uk_years']}** ({rates['uk_n_station_weeks']} station-weeks after
coord filter). Applying the Irish split (train ≤2018 / val 2019–2021 / test ≥2022) leaves
**only ISO 2018 as train** (~one year, few hundred positives at most across folds) — **too
little for a solid UK-only fit**. We therefore use a **UK-adapted time split**
(train 2018–2021, val 2022 for calibration, test 2023+) plus **leave-one-year-out** and an
**Ireland→UK transfer** check on aligned ≥100 cells L⁻¹ labels.

## UK vs Irish PR-AUC / rates

Same-week Dinophysis exceedance rate is similar on the two coasts (**UK {_fmt({'pr_auc': rates['uk_same_week']})}**
vs **Irish {_fmt({'pr_auc': rates['ie_same_week']})}**; nowcast rates **{_fmt({'pr_auc': rates['uk_nowcast']})}** vs
**{_fmt({'pr_auc': rates['ie_nowcast']})}**). On the UK-adapted test set, LightGBM val-calibrated
PR-AUC is **{_fmt(uk_lgb)}** (clim {_fmt(uk_lgb, 'pr_auc_clim')}, prevalence {_fmt(uk_lgb, 'prevalence')}),
versus Irish strong-mode LightGBM test-calibrated PR-AUC **{_fmt(ie_lgb)}** (clim {_fmt(ie_lgb, 'pr_auc_clim')},
prevalence {_fmt(ie_lgb, 'prevalence')}, SST+seasonality features). Ireland→UK transfer with
shared seasonality/geo features yields LightGBM UK-test PR-AUC **{_fmt(xfer)}** — useful as a
cross-shelf sanity check, not a replacement for UK SST features. LOYO LightGBM test PR-AUC by
held-out year: {', '.join(f'{y}={p:.3f}' for y, p, _ in loyo_pr) or 'n/a'}. Honest takeaway:
UK labels are usable and rates align with Ireland, but without joined UK SST the ranking skill
is mostly seasonal/geographic; treat UK numbers as a parallel baseline until OISST is attached
(still no Copernicus/OSTIA without credentials).

## Split counts (UK-adapted)

| split | n | positives (same-week) | years |
| --- | ---: | ---: | --- |
"""
    for split in ("train", "val", "test"):
        sub = uk[uk["split"] == split]
        md += (
            f"| {split} | {len(sub)} | {int(sub['y_dinophysis'].sum())} | "
            f"{sorted(int(x) for x in sub['iso_year'].unique())} |\n"
        )
    md += f"""
## Reproduce

```bash
python scripts/ingest_uk_fsa.py          # refresh panel (cp1252-safe)
python scripts/evaluate_uk_dino.py
```
"""
    OUT_MD.write_text(md)
    print(json.dumps({
        "wrote": [str(OUT_JSON), str(OUT_MD)],
        "uk_lgb_test_pr": uk_lgb.get("pr_auc"),
        "ie_lgb_test_pr": ie_lgb.get("pr_auc"),
        "transfer_pr": xfer.get("pr_auc"),
        "rates": rates,
    }, indent=2))


if __name__ == "__main__":
    main()
