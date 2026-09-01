#!/usr/bin/env python3
"""Scotland SMC Dinophysis nowcast: OISST → Hobday MHW → strong features → train/eval.

Uses only SINs with geocode confidence high or medium (~73% of station-weeks).
Does not wait for ERA5. Writes:
  data/raw/oisst_scotland_daily.parquet          (gitignored)
  data/processed/mhw_daily_scotland.parquet      (gitignored)
  data/processed/joined_features_scotland.parquet (gitignored)
  data/processed/scotland_dino_metrics.json
  data/processed/scotland_dino_report.md
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from pa_marine.calibration import ProbCalibrator
from pa_marine.config import load_config
from pa_marine.features import join_week_panel, select_feature_mode
from pa_marine.hab import add_horizon_labels
from pa_marine.metrics import climatology_probs, summarise
from pa_marine.mhw import mhw_for_stations
from pa_marine.models import fit_predict, make_estimators
from pa_marine.splits import year_split
from pa_marine.sst import download_oisst_for_stations_nearest_ocean

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data/processed/smc_station_week_panel.parquet"
COORDS = ROOT / "data/processed/smc_site_coords.csv"
SST_OUT = ROOT / "data/raw/oisst_scotland_daily.parquet"
MHW_OUT = ROOT / "data/processed/mhw_daily_scotland.parquet"
JOINED_OUT = ROOT / "data/processed/joined_features_scotland.parquet"
OUT_JSON = ROOT / "data/processed/scotland_dino_metrics.json"
OUT_MD = ROOT / "data/processed/scotland_dino_report.md"
TARGET = "y_dinophysis_nowcast"
CONF_KEEP = ("high", "medium")


def _raw_probs(est, X) -> np.ndarray:
    if hasattr(est, "predict_proba"):
        return est.predict_proba(X)[:, 1]
    d = est.decision_function(X)
    return 1 / (1 + np.exp(-d))


def _load_scotland_panel(min_conf: tuple[str, ...] = CONF_KEEP) -> tuple[pd.DataFrame, dict]:
    panel = pd.read_parquet(PANEL)
    coords = pd.read_csv(COORDS)
    conf_map = coords.set_index("Sin")["confidence"].to_dict()
    # Prefer panel coord_confidence; fall back to coords file
    if "coord_confidence" not in panel.columns or panel["coord_confidence"].isna().all():
        panel["coord_confidence"] = panel["Sin"].map(conf_map)
    n_all = len(panel)
    n_sin_all = int(panel["Sin"].nunique())
    keep = panel["coord_confidence"].isin(min_conf) & panel["latitude"].notna() & panel["longitude"].notna()
    out = panel.loc[keep].copy()
    # location_id is Sin in SMC panel
    if "location_id" not in out.columns or out["location_id"].isna().any():
        out["location_id"] = out["Sin"]
    meta = {
        "n_panel_all": n_all,
        "n_sin_all": n_sin_all,
        "n_panel_keep": int(len(out)),
        "n_sin_keep": int(out["Sin"].nunique()),
        "frac_rows_keep": float(len(out) / max(n_all, 1)),
        "confidence_keep": list(min_conf),
        "confidence_counts_all": panel["coord_confidence"].value_counts(dropna=False).to_dict(),
        "lat_range": [float(out["latitude"].min()), float(out["latitude"].max())],
        "lon_range": [float(out["longitude"].min()), float(out["longitude"].max())],
        "week_span": [
            str(pd.to_datetime(out["week_start"]).min().date()),
            str(pd.to_datetime(out["week_start"]).max().date()),
        ],
        "years": sorted(int(y) for y in out["iso_year"].unique()),
    }
    return out, meta


def _ensure_labels(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    if TARGET not in out.columns:
        tax = [c[2:] for c in out.columns if c.startswith("y_") and not c.endswith(("_nowcast", "_ahead7"))]
        # y_dinophysis etc.
        tax = [t for t in tax if f"y_{t}" in out.columns]
        out = add_horizon_labels(out, tax or ["dinophysis"])
    return out


def _eval(df: pd.DataFrame, feats: list[str], target: str) -> dict:
    train = df[df["split"] == "train"]
    val = df[df["split"] == "val"]
    results: dict = {}
    ytr = train[target].astype(int)
    mtr = ytr.notna() & train[feats].notna().all(axis=1)
    if int(mtr.sum()) == 0 or int(ytr.loc[mtr].sum()) == 0:
        return {"error": "no train positives or complete feature rows"}
    clim_week = train.loc[mtr, "iso_week"].to_numpy()
    clim_y = ytr.loc[mtr].to_numpy()
    for name, est in make_estimators().items():
        fit_predict(est, train.loc[mtr, feats], ytr.loc[mtr], train.loc[mtr, feats])
        calibrator = None
        if not val.empty:
            yv = val[target].astype(int)
            mv = yv.notna() & val[feats].notna().all(axis=1)
            if int(mv.sum()) > 0 and int(yv.loc[mv].sum()) > 0:
                calibrator = ProbCalibrator(method="auto").fit(
                    yv.loc[mv].to_numpy(), _raw_probs(est, val.loc[mv, feats])
                )
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
                cal = summarise(y_np, calibrator.transform(pr_raw), clim)
                ckey = f"{name}_{split}_calibrated"
                results[ckey] = dict(cal)
                results[ckey]["calibrated"] = True
                results[ckey]["calibration_method"] = calibrator.chosen_
                results[ckey]["raw_pr_auc"] = raw["pr_auc"]
                results[ckey]["raw_brier"] = raw["brier"]
    return results


def _fmt(d: dict | None, key: str = "pr_auc") -> str:
    if not d:
        return "n/a"
    v = d.get(key)
    return f"{v:.3f}" if isinstance(v, (int, float)) and np.isfinite(v) else "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--t0", default="2002-01-01", help="OISST start (climatology buffer before 2009)")
    ap.add_argument("--t1", default="2026-08-16")
    ap.add_argument("--sst-in", default=None, help="Reuse existing Scotland OISST parquet")
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--feature-mode", default="strong")
    args = ap.parse_args()
    cfg = load_config(args.config)

    panel, panel_meta = _load_scotland_panel()
    panel = _ensure_labels(panel)
    panel["split"] = year_split(panel, cfg)
    print(
        f"Scotland panel keep={panel_meta['n_panel_keep']} "
        f"({panel_meta['frac_rows_keep']:.1%}) sins={panel_meta['n_sin_keep']} "
        f"years={panel_meta['years'][0]}..{panel_meta['years'][-1]}"
    )

    sst_path = Path(args.sst_in) if args.sst_in else SST_OUT
    if args.skip_download and sst_path.is_file():
        sst = pd.read_parquet(sst_path)
        print(f"reused {sst_path} n={len(sst)}")
    elif sst_path.is_file() and not args.sst_in:
        # default: reuse if present unless explicitly forcing via missing file
        sst = pd.read_parquet(sst_path)
        print(f"reused existing {sst_path} n={len(sst)} (delete to re-download)")
    else:
        stations = panel.drop_duplicates("location_id")[
            ["location_id", "latitude", "longitude"]
        ]
        sst = download_oisst_for_stations_nearest_ocean(
            stations, cfg, args.t0, args.t1, label="scotland"
        )
        sst_path.parent.mkdir(parents=True, exist_ok=True)
        sst.to_parquet(sst_path, index=False)
        print(f"wrote {sst_path} n={len(sst)} locs={sst['location_id'].nunique()}")

    mhw = mhw_for_stations(sst, cfg)
    MHW_OUT.parent.mkdir(parents=True, exist_ok=True)
    mhw.to_parquet(MHW_OUT, index=False)
    print(f"wrote {MHW_OUT} n={len(mhw)}")

    joined = join_week_panel(panel, mhw)
    # re-attach split (join keeps it)
    if "split" not in joined.columns:
        joined["split"] = year_split(joined, cfg)
    JOINED_OUT.parent.mkdir(parents=True, exist_ok=True)
    joined.to_parquet(JOINED_OUT, index=False)
    print(f"wrote {JOINED_OUT} n={len(joined)}")

    feats = select_feature_mode(joined, args.feature_mode)
    # Require SST present for fair SST-feature eval
    sst_ok = joined["sst"].notna() if "sst" in joined.columns else pd.Series(True, index=joined.index)
    df = joined.loc[sst_ok].copy()
    print(f"rows with sst={int(sst_ok.sum())}/{len(joined)}; features({len(feats)})={feats}")

    metrics = _eval(df, feats, TARGET)

    split_counts = {}
    for split in ("train", "val", "test"):
        sub = df[df["split"] == split]
        split_counts[split] = {
            "n": int(len(sub)),
            "n_complete": int((sub[TARGET].notna() & sub[feats].notna().all(axis=1)).sum()),
            "positives_same_week": int(sub["y_dinophysis"].sum()) if "y_dinophysis" in sub else None,
            "positives_nowcast": int(sub[TARGET].sum()) if TARGET in sub else None,
            "years": sorted(int(x) for x in sub["iso_year"].unique()),
            "prevalence_nowcast": float(sub[TARGET].mean()) if len(sub) else None,
        }

    ie_ref = None
    ie_path = ROOT / "data/processed/metrics_dino_strong.json"
    if ie_path.is_file():
        ie = json.loads(ie_path.read_text())
        block = ie.get(TARGET) or {}
        ie_ref = {
            k: block[k]
            for k in ("lightgbm_test_calibrated", "logreg_test_calibrated", "lightgbm_test")
            if k in block
        }

    generated = datetime.now(ZoneInfo("Europe/Dublin")).strftime("%Y-%m-%d %H:%M %Z")
    payload = {
        "_meta": {
            "generated": generated,
            "target": TARGET,
            "feature_mode": args.feature_mode,
            "features": feats,
            "n_features": len(feats),
            "oisst_t0": args.t0,
            "oisst_t1": args.t1,
            "sst_path": str(sst_path.relative_to(ROOT)),
            "panel_filter": panel_meta,
            "split": cfg["splits"],
            "n_joined": int(len(joined)),
            "n_with_sst": int(len(df)),
            "sst_finite_frac": float(sst_ok.mean()),
            "same_week_prevalence": float(df["y_dinophysis"].mean()),
            "nowcast_prevalence": float(df[TARGET].mean()),
            "note": (
                "High/medium geocode confidence only; nearest-ocean OISST 0.25° pixels; "
                "Hobday MHW + Irish strong OISST feature set; no ERA5."
            ),
        },
        "split_counts": split_counts,
        "metrics": metrics,
        "irish_strong_reference": ie_ref,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2))

    lgb = metrics.get("lightgbm_test_calibrated") or metrics.get("lightgbm_test") or {}
    lr = metrics.get("logreg_test_calibrated") or metrics.get("logreg_test") or {}
    ie_lgb = (ie_ref or {}).get("lightgbm_test_calibrated") or {}

    md = f"""# Scotland SMC Dinophysis nowcast (OISST strong)

Generated: {generated} (Europe/Dublin). Target: `{TARGET}`.
Feature mode: **{args.feature_mode}** ({len(feats)} feats). Metrics: `{OUT_JSON.relative_to(ROOT)}`.

## Data filter

- Panel SINs: **{panel_meta['n_sin_all']}** → keep confidence ∈ {{{", ".join(CONF_KEEP)}}} → **{panel_meta['n_sin_keep']}** SINs
- Station-weeks: **{panel_meta['n_panel_all']}** → **{panel_meta['n_panel_keep']}** ({panel_meta['frac_rows_keep']:.1%})
- Week span: **{panel_meta['week_span'][0]} → {panel_meta['week_span'][1]}**
- Coords: lat [{panel_meta['lat_range'][0]:.2f}, {panel_meta['lat_range'][1]:.2f}],
  lon [{panel_meta['lon_range'][0]:.2f}, {panel_meta['lon_range'][1]:.2f}]
- OISST: nearest-ocean 0.25° pixels, `{args.t0}` → `{args.t1}` (climatology buffer before first SMC week)
- Rows with finite SST after join: **{int(len(df))}** / {len(joined)} ({float(sst_ok.mean()):.1%})
- Same-week / nowcast prevalence: **{_fmt({"pr_auc": payload["_meta"]["same_week_prevalence"]})}** /
  **{_fmt({"pr_auc": payload["_meta"]["nowcast_prevalence"]})}**

## Time split (Irish years)

| split | n (with SST) | nowcast + | years |
| --- | ---: | ---: | --- |
| train | {split_counts['train']['n']} | {split_counts['train']['positives_nowcast']} | {split_counts['train']['years']} |
| val | {split_counts['val']['n']} | {split_counts['val']['positives_nowcast']} | {split_counts['val']['years']} |
| test | {split_counts['test']['n']} | {split_counts['test']['positives_nowcast']} | {split_counts['test']['years']} |

## Test metrics vs week-of-year climatology

| model | PR-AUC | clim PR-AUC | PR skill | Brier | Brier skill | n | prevalence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LightGBM calibrated | {_fmt(lgb)} | {_fmt(lgb, "pr_auc_clim")} | {_fmt(lgb, "pr_auc_skill")} | {_fmt(lgb, "brier")} | {_fmt(lgb, "brier_skill")} | {lgb.get("n", "n/a")} | {_fmt(lgb, "prevalence")} |
| LogReg calibrated | {_fmt(lr)} | {_fmt(lr, "pr_auc_clim")} | {_fmt(lr, "pr_auc_skill")} | {_fmt(lr, "brier")} | {_fmt(lr, "brier_skill")} | {lr.get("n", "n/a")} | {_fmt(lr, "prevalence")} |
| Irish strong LGBM (ref) | {_fmt(ie_lgb)} | {_fmt(ie_lgb, "pr_auc_clim")} | {_fmt(ie_lgb, "pr_auc_skill")} | {_fmt(ie_lgb, "brier")} | {_fmt(ie_lgb, "brier_skill")} | {ie_lgb.get("n", "n/a")} | {_fmt(ie_lgb, "prevalence")} |

Features: `{", ".join(feats)}`.

## Notes

- Low-confidence geocodes excluded from SST join (ambiguous Nominatim / island fallbacks).
- Coastal OISST snaps use **nearest ocean pixel** (many Scottish loch/voe snaps are land on the 0.25° grid).
- No ERA5 / IBI / OSTIA in this path.
- Calibration fitted on **val only** (isotonic/sigmoid auto).

## Reproduce

```bash
python scripts/train_scotland_dino.py
# reuse SST:
python scripts/train_scotland_dino.py --skip-download
```
"""
    OUT_MD.write_text(md)
    print(json.dumps({
        "wrote": [str(OUT_JSON), str(OUT_MD)],
        "lightgbm_test_pr_auc": lgb.get("pr_auc"),
        "logreg_test_pr_auc": lr.get("pr_auc"),
        "n_test": lgb.get("n"),
        "prevalence": lgb.get("prevalence"),
        "frac_keep": panel_meta["frac_rows_keep"],
    }, indent=2))


if __name__ == "__main__":
    main()
