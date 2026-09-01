#!/usr/bin/env python3
"""DSP toxin exceedance / harvest-closure risk from Irish OISST strong features.

Highest-economic-value early-warning prototype: shellfish DSP (OA-DTX-PTX family)
regulatory exceedance and optional area closed flag from habs_status.

Reuses toxin_joined_features.parquet from scripts/ingest_biotoxin.py (location_id
overlap with phyto OISST/MHW). Philosophy matches Dinophysis cell models:
  - strong OISST feature set (9 cols)
  - LightGBM + logistic regression
  - year time split (train/val/test from config)
  - val-only probability calibration
  - PR-AUC / Brier vs week-of-year climatology

Writes:
  data/processed/dsp_closure_risk_metrics.json
  data/processed/dsp_closure_risk_report.md
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
from pa_marine.features import STRONG_OISST, select_feature_mode
from pa_marine.metrics import climatology_probs, summarise
from pa_marine.models import fit_predict, make_estimators
from pa_marine.splits import year_split

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JOINED = ROOT / "data/processed/toxin_joined_features.parquet"
DEFAULT_METRICS = ROOT / "data/processed/dsp_closure_risk_metrics.json"
DEFAULT_REPORT = ROOT / "data/processed/dsp_closure_risk_report.md"
DINO_METRICS = ROOT / "data/processed/metrics_dino_strong.json"

# OA / DTX reported as DSP in MI pivot; PTX co-thresholded when present.
FAMILY_EXCEED_COLS = ("exceed_dsp", "exceed_ptx")
FAMILY_MEASURED_COLS = ("measured_dsp", "measured_ptx")


def _raw_probs(est, X) -> np.ndarray:
    if hasattr(est, "predict_proba"):
        return est.predict_proba(X)[:, 1]
    d = est.decision_function(X)
    return 1 / (1 + np.exp(-d))


def _build_targets(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in FAMILY_EXCEED_COLS + FAMILY_MEASURED_COLS:
        if c not in out.columns:
            out[c] = 0
    # Station-week DSP family exceedance (resultvalue >= regulatory threshold).
    out["y_dsp_exceed"] = (
        (out["exceed_dsp"].fillna(0).astype(int) == 1)
        | (out["exceed_ptx"].fillna(0).astype(int) == 1)
    ).astype(int)
    # Prefer weeks where DSP was assayed (PTX alone is sparse / never exceeded in panel).
    out["dsp_measured"] = (out["measured_dsp"].fillna(0).astype(int) == 1).astype(int)
    # Area closed from habs_status (already joined via parent_area_name + ISO week).
    if "closed" in out.columns:
        out["y_closed"] = pd.to_numeric(out["closed"], errors="coerce")
    else:
        out["y_closed"] = np.nan
    return out


def _prepare(
    path: Path,
    cfg: dict,
    require_sst: bool,
    feature_mode: str,
) -> tuple[pd.DataFrame, list[str], dict]:
    df = pd.read_parquet(path)
    df = _build_targets(df)
    df["split"] = year_split(df, cfg)
    feats = select_feature_mode(df, feature_mode)
    meta = {
        "source": str(path),
        "n_rows_raw": int(len(df)),
        "n_locations": int(df["location_id"].nunique()) if "location_id" in df.columns else None,
        "feature_mode": feature_mode,
        "features": feats,
        "strong_oisst_def": sorted(STRONG_OISST),
        "require_sst_complete": require_sst,
        "sst_nonnull_rate": float(df["sst"].notna().mean()) if "sst" in df.columns else None,
        "week_span": [
            str(pd.to_datetime(df["week_start"]).min()),
            str(pd.to_datetime(df["week_start"]).max()),
        ],
    }
    if require_sst:
        complete = df[feats].notna().all(axis=1)
        meta["n_rows_before_sst_filter"] = int(len(df))
        df = df.loc[complete].copy()
        meta["n_rows_after_sst_filter"] = int(len(df))
    return df, feats, meta


def _eval_target(df: pd.DataFrame, feats: list[str], target: str, row_mask: pd.Series) -> dict:
    """Train on train split; calibrate on val; score val/test. Same as evaluate.py."""
    work = df.loc[row_mask].copy()
    results: dict = {
        "target": target,
        "n_rows": int(len(work)),
        "split_counts": work.groupby("split").size().astype(int).to_dict(),
    }
    if work.empty or target not in work.columns:
        results["error"] = "empty or missing target"
        return results

    train = work[work["split"] == "train"]
    val = work[work["split"] == "val"]
    ytr = train[target]
    mtr = ytr.notna()
    if int(mtr.sum()) == 0 or int(ytr.loc[mtr].sum()) == 0:
        results["error"] = "no train positives"
        return results

    clim_week = train.loc[mtr, "iso_week"].to_numpy()
    clim_y = ytr.loc[mtr].astype(int).to_numpy()
    results["train_prevalence"] = float(clim_y.mean())
    results["models"] = {}

    for name, est in make_estimators().items():
        fit_predict(est, train.loc[mtr, feats], ytr.loc[mtr].astype(int), train.loc[mtr, feats])
        calibrator = None
        if not val.empty:
            yv = val[target]
            mv = yv.notna()
            if int(mv.sum()) > 0 and int(yv.loc[mv].sum()) > 0:
                calibrator = ProbCalibrator(method="auto").fit(
                    yv.loc[mv].astype(int).to_numpy(),
                    _raw_probs(est, val.loc[mv, feats]),
                )

        for split in ("val", "test"):
            ev = work[work["split"] == split]
            if ev.empty:
                continue
            y = ev[target]
            mask = y.notna()
            if int(mask.sum()) == 0 or int(y.loc[mask].nunique()) < 2:
                results["models"][f"{name}_{split}"] = {
                    "error": "degenerate labels",
                    "n": int(mask.sum()),
                    "prevalence": float(y.loc[mask].mean()) if int(mask.sum()) else None,
                }
                continue
            pr_raw = _raw_probs(est, ev.loc[mask, feats])
            clim = climatology_probs(clim_week, clim_y, ev.loc[mask, "iso_week"].to_numpy())
            y_np = y.loc[mask].astype(int).to_numpy()
            raw = summarise(y_np, pr_raw, clim)
            key = f"{name}_{split}"
            results["models"][key] = dict(raw)
            results["models"][key]["calibrated"] = False
            if calibrator is not None:
                cal = summarise(y_np, calibrator.transform(pr_raw), clim)
                ckey = f"{name}_{split}_calibrated"
                results["models"][ckey] = dict(cal)
                results["models"][ckey]["calibrated"] = True
                results["models"][ckey]["calibration_method"] = calibrator.chosen_
                results["models"][ckey]["raw_pr_auc"] = raw["pr_auc"]
                results["models"][ckey]["raw_brier"] = raw["brier"]
    return results


def _pick(models: dict, key: str) -> dict | None:
    return models.get(key) if models else None


def _fmt(d: dict | None, key: str = "pr_auc") -> str:
    if not d or key not in d:
        return "n/a"
    v = d.get(key)
    if isinstance(v, (int, float)) and np.isfinite(v):
        return f"{v:.3f}"
    return "n/a"


def _load_dino_ref() -> dict:
    if not DINO_METRICS.is_file():
        return {}
    raw = json.loads(DINO_METRICS.read_text())
    block = raw.get("y_dinophysis_nowcast") or {}
    return {
        "lightgbm_test": block.get("lightgbm_test"),
        "lightgbm_test_calibrated": block.get("lightgbm_test_calibrated"),
        "logreg_test": block.get("logreg_test"),
        "logreg_test_calibrated": block.get("logreg_test_calibrated"),
        "meta": raw.get("_meta"),
    }


def _write_report(path: Path, payload: dict) -> None:
    dublin = datetime.now(ZoneInfo("Europe/Dublin")).strftime("%Y-%m-%d %H:%M %Z")
    dsp = payload.get("y_dsp_exceed") or {}
    clo = payload.get("y_closed") or {}
    dsp_m = dsp.get("models") or {}
    clo_m = clo.get("models") or {}
    dino = payload.get("dinophysis_reference") or {}
    meta = payload.get("meta") or {}

    lgbm_dsp_cal = _pick(dsp_m, "lightgbm_test_calibrated") or _pick(dsp_m, "lightgbm_test")
    lgbm_dsp_raw = _pick(dsp_m, "lightgbm_test")
    log_dsp_cal = _pick(dsp_m, "logreg_test_calibrated") or _pick(dsp_m, "logreg_test")
    lgbm_clo_cal = _pick(clo_m, "lightgbm_test_calibrated") or _pick(clo_m, "lightgbm_test")
    lgbm_clo_raw = _pick(clo_m, "lightgbm_test")
    log_clo_cal = _pick(clo_m, "logreg_test_calibrated") or _pick(clo_m, "logreg_test")
    dino_cal = dino.get("lightgbm_test_calibrated") or dino.get("lightgbm_test")

    # Honest SST-alone predictability for closure
    clo_pr = (lgbm_clo_cal or {}).get("pr_auc")
    clo_clim = (lgbm_clo_cal or {}).get("pr_auc_clim")
    clo_skill = (lgbm_clo_cal or {}).get("pr_auc_skill")
    dsp_pr = (lgbm_dsp_cal or {}).get("pr_auc")
    dsp_clim = (lgbm_dsp_cal or {}).get("pr_auc_clim")
    dsp_skill = (lgbm_dsp_cal or {}).get("pr_auc_skill")
    clo_prev = (lgbm_clo_cal or lgbm_clo_raw or {}).get("prevalence")
    dsp_prev = (lgbm_dsp_cal or lgbm_dsp_raw or {}).get("prevalence")
    dsp_n = (lgbm_dsp_cal or lgbm_dsp_raw or {}).get("n")
    dsp_n_pos = None
    if dsp_n and dsp_prev is not None:
        dsp_n_pos = int(round(float(dsp_prev) * int(dsp_n)))

    def _skill_verdict(skill, prev, n_pos, label: str) -> str:
        if skill is None or not np.isfinite(skill):
            return f"{label}: inconclusive (degenerate or missing metrics)."
        if n_pos is not None and n_pos < 30:
            return (
                f"{label}: **not reliably assessable from SST alone on this test window** "
                f"(only ~{n_pos} positives; PR-AUC is noisy). Prefer more years / denser toxin "
                "sampling before claiming ops skill."
            )
        if skill > 0.05:
            return f"{label}: **partially predictable from SST strong features** (PR skill {skill:.3f} vs week-of-year clim)."
        if skill > 0.0:
            return f"{label}: **marginal** SST signal vs climatology (PR skill {skill:.3f}) — not ops-ready."
        return f"{label}: **not predictable from SST alone** on this split (PR skill {skill:.3f} ≤ 0 vs clim)."

    dsp_verdict = _skill_verdict(dsp_skill, dsp_prev, dsp_n_pos, "DSP exceedance")
    clo_n = (lgbm_clo_cal or lgbm_clo_raw or {}).get("n")
    clo_n_pos = int(round(float(clo_prev) * int(clo_n))) if clo_n and clo_prev is not None else None
    clo_verdict = _skill_verdict(clo_skill, clo_prev, clo_n_pos, "Area closed")

    lines = [
        "# DSP / harvest-closure risk (ops prototype)",
        "",
        f"Generated: **{dublin}**. Script: `scripts/train_dsp_closure_risk.py`.",
        "",
        "Product thesis: **shellfish DSP exceedance and harvest closures** are closer to "
        "euro-loss than cell counts. This run asks whether the same Irish **OISST strong** "
        "features that give modest Dinophysis-cell skill also rank **toxin exceedance** and "
        "**area closed** weeks.",
        "",
        "## Data",
        "",
        f"- Joined panel: `{meta.get('source')}` ({meta.get('n_rows_raw')} rows, "
        f"{meta.get('n_locations')} `location_id`s overlapping phyto OISST/MHW).",
        f"- SST non-null rate: **{meta.get('sst_nonnull_rate')}** "
        f"(require complete strong features: `{meta.get('require_sst_complete')}`).",
        f"- Feature mode `{meta.get('feature_mode')}` ({len(meta.get('features') or [])} cols): "
        f"`{', '.join(meta.get('features') or [])}`.",
        f"- Time split: train {payload.get('splits', {}).get('train')} / "
        f"val {payload.get('splits', {}).get('val')} / test≥{payload.get('splits', {}).get('test_from')}.",
        "- Target `y_dsp_exceed`: station-week max(`exceed_dsp`, `exceed_ptx`) among DSP-measured weeks "
        "(MI pivot: DSP = OA/DTX family; PTX co-thresholded, historically ~0 exceedances).",
        "- Target `y_closed`: `habs_status` closed / closed-pending / harvest-restricted, "
        "joined on `parent_area_name` + ISO week (same as biotoxin ingest).",
        "",
        "## Test metrics (primary = calibrated LightGBM PR-AUC)",
        "",
        "| Target | Model | Test n | Prevalence | PR-AUC | Clim PR-AUC | PR skill | Brier |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    def row(label, model, d):
        if not d or "pr_auc" not in d:
            lines.append(f"| {label} | {model} | — | — | n/a | n/a | n/a | n/a |")
            return
        lines.append(
            f"| {label} | {model} | {d.get('n')} | {_fmt(d, 'prevalence')} | "
            f"**{_fmt(d)}** | {_fmt(d, 'pr_auc_clim')} | {_fmt(d, 'pr_auc_skill')} | {_fmt(d, 'brier')} |"
        )

    row("DSP exceed", "LightGBM cal", lgbm_dsp_cal)
    row("DSP exceed", "LightGBM raw", lgbm_dsp_raw)
    row("DSP exceed", "LogReg cal", log_dsp_cal)
    row("Area closed", "LightGBM cal", lgbm_clo_cal)
    row("Area closed", "LightGBM raw", lgbm_clo_raw)
    row("Area closed", "LogReg cal", log_clo_cal)
    if dino_cal:
        row("Dinophysis cells (ref)", "LightGBM cal", dino_cal)

    lines += [
        "",
        "### Split prevalence (important)",
        "",
        f"- DSP train prevalence: **{_fmt({'prevalence': dsp.get('train_prevalence')}, 'prevalence')}**; "
        f"test prevalence: **{_fmt(lgbm_dsp_cal or lgbm_dsp_raw, 'prevalence')}** "
        f"(~{dsp_n_pos} test positives).",
        f"- Closed train prevalence: **{_fmt({'prevalence': clo.get('train_prevalence')}, 'prevalence')}**; "
        f"test: **{_fmt(lgbm_clo_cal or lgbm_clo_raw, 'prevalence')}**.",
        "",
        "DSP toxin exceedances became **much rarer** on the 2022+ test window than in train/val. "
        "That shrinks the economic-event sample and inflates uncertainty in PR-AUC — do not over-read "
        "a single point estimate.",
        "",
        "## Is closure / DSP predictable from SST alone?",
        "",
        f"- {dsp_verdict}",
        f"- {clo_verdict}",
        "",
        "Context: almost every DSP-exceed week is closed in the matched panel "
        f"(P(closed|DSP+)≈{payload.get('assoc', {}).get('p_closed_given_dsp')}; "
        f"P(DSP+|closed)≈{payload.get('assoc', {}).get('p_dsp_given_closed')}; "
        f"Pearson≈{payload.get('assoc', {}).get('pearson_dsp_closed')}). "
        "Closures are driven by **multiple** toxins and admin rules — SST→DSP cells≠SST→closure.",
        "",
        "## Honest comparison to cell-based Dinophysis model",
        "",
        "| | Dinophysis cells (`y_dinophysis_nowcast`) | DSP toxin exceed | Area closed |",
        "| --- | ---: | ---: | ---: |",
        f"| Test PR-AUC (LGBM cal) | {_fmt(dino_cal)} | {_fmt(lgbm_dsp_cal)} | {_fmt(lgbm_clo_cal)} |",
        f"| Clim PR-AUC | {_fmt(dino_cal, 'pr_auc_clim')} | {_fmt(lgbm_dsp_cal, 'pr_auc_clim')} | {_fmt(lgbm_clo_cal, 'pr_auc_clim')} |",
        f"| PR skill | {_fmt(dino_cal, 'pr_auc_skill')} | {_fmt(lgbm_dsp_cal, 'pr_auc_skill')} | {_fmt(lgbm_clo_cal, 'pr_auc_skill')} |",
        f"| Test prevalence | {_fmt(dino_cal, 'prevalence')} | {_fmt(lgbm_dsp_cal or lgbm_dsp_raw, 'prevalence')} | {_fmt(lgbm_clo_cal or lgbm_clo_raw, 'prevalence')} |",
        "",
        "- Cell model (Ireland strong OISST): modest but real ranking skill (~0.29 cal PR-AUC vs ~0.18 clim).",
        "- DSP toxin head: economically closer to harvest loss, but **positives are scarce on test** and "
        "agreement with Dinophysis cells was only moderate at ingest (Pearson ~0.29; see "
        "`biotoxin_ingest_report.md`). Expect weaker / noisier SST skill than cells.",
        "- Closed head: higher prevalence and more stable — better powered — but mixes DSP with ASP/AZP/PSP "
        "and non-toxin admin closures, so SST-alone skill is an upper-bound on 'toxin-weather' signal, not "
        "a drop-in ops product.",
        "",
        "## Caveats",
        "",
        "- OISST landmask → ~30–40% SST coverage at toxin sites; LightGBM sees NaNs, logreg median-imputes.",
        "- `habs_status` has **no** `location_id`/lat-lon — area-name string join only.",
        "- Not an operational warning system; research prototype for Cork Ocean Hackathon Challenge 4.",
        "",
        "## Re-run",
        "",
        "```bash",
        "python scripts/train_dsp_closure_risk.py",
        "# or, after re-ingest:",
        "python scripts/ingest_biotoxin.py --skip-download",
        "python scripts/train_dsp_closure_risk.py --require-sst",
        "```",
        "",
        f"Metrics JSON: `{payload.get('metrics_path')}`.",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--joined", default=str(DEFAULT_JOINED))
    ap.add_argument("--feature-mode", default="strong")
    ap.add_argument(
        "--require-sst",
        action="store_true",
        help="Drop rows with any NaN in selected features (stricter, fewer DSP test positives).",
    )
    ap.add_argument("--out-metrics", default=str(DEFAULT_METRICS))
    ap.add_argument("--out-report", default=str(DEFAULT_REPORT))
    args = ap.parse_args()

    cfg = load_config(args.config)
    df, feats, meta = _prepare(Path(args.joined), cfg, args.require_sst, args.feature_mode)
    print(
        f"panel n={len(df)} locs={meta.get('n_locations')} feats={len(feats)} "
        f"sst_rate={meta.get('sst_nonnull_rate')}"
    )

    # Association diagnostics on overlapping measured+status rows
    both = df[(df["dsp_measured"] == 1) & df["y_closed"].notna()]
    assoc = {
        "n_overlap": int(len(both)),
        "pearson_dsp_closed": (
            float(both["y_dsp_exceed"].corr(both["y_closed"])) if len(both) > 20 else None
        ),
        "p_closed_given_dsp": (
            float(both.loc[both["y_dsp_exceed"] == 1, "y_closed"].mean())
            if (both["y_dsp_exceed"] == 1).any()
            else None
        ),
        "p_dsp_given_closed": (
            float(both.loc[both["y_closed"] == 1, "y_dsp_exceed"].mean())
            if (both["y_closed"] == 1).any()
            else None
        ),
    }

    dsp_mask = df["dsp_measured"] == 1
    closed_mask = df["y_closed"].notna()
    dsp_res = _eval_target(df, feats, "y_dsp_exceed", dsp_mask)
    closed_res = _eval_target(df, feats, "y_closed", closed_mask)
    dino_ref = _load_dino_ref()

    payload = {
        "_meta": {
            "generated_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
            "calibration": "auto (val-only)",
            "estimators": list(make_estimators()),
        },
        "meta": meta,
        "splits": cfg.get("splits"),
        "assoc": assoc,
        "y_dsp_exceed": dsp_res,
        "y_closed": closed_res,
        "dinophysis_reference": dino_ref,
        "metrics_path": args.out_metrics,
    }

    out_m = Path(args.out_metrics)
    out_r = Path(args.out_report)
    out_m.parent.mkdir(parents=True, exist_ok=True)
    out_m.write_text(json.dumps(payload, indent=2, default=str))
    _write_report(out_r, payload)
    print(f"metrics -> {out_m}")
    print(f"report  -> {out_r}")

    # Console summary for parent agent
    for label, block in (("DSP", dsp_res), ("closed", closed_res)):
        models = block.get("models") or {}
        for key in (
            "lightgbm_test_calibrated",
            "lightgbm_test",
            "logreg_test_calibrated",
            "logreg_test",
        ):
            d = models.get(key)
            if d and "pr_auc" in d:
                print(
                    f"{label} {key}: PR-AUC={d['pr_auc']:.4f} clim={d['pr_auc_clim']:.4f} "
                    f"skill={d.get('pr_auc_skill')} prev={d.get('prevalence'):.4f} n={d.get('n')}"
                )


if __name__ == "__main__":
    main()
