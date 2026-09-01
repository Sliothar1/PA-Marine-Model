#!/usr/bin/env python3
"""Connemara Farms weekly Dinophysis / DSP-closure risk scores (product idea 2).

Applies the **national** Irish Dinophysis strong-OISST model (and optionally the
DSP / area-closed heads from toxin_joined_features) to the Connemara station
set in configs/connemara_farms_stations.yaml.

Why national apply (not local retrain): core Connemara NMP sites have too few
Dinophysis positives for a stable local fit (single-digit to low-dozens per
site). National train 2003–2018 + val calibration 2019–2021 is the documented
strong-feature protocol (test PR-AUC ≈ 0.293 vs clim ≈ 0.183).

Writes (under data/processed/ unless --out-dir):
  connemara_farms_stations.csv
  connemara_farms_scores.csv          # all scored station-weeks
  connemara_farms_latest.csv          # grower table (recent weeks)
  connemara_farms_scores.html         # plain-language HTML
  connemara_farms_metrics.json        # national + Connemara-subset metrics
"""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yaml

from pa_marine.calibration import ProbCalibrator
from pa_marine.config import load_config
from pa_marine.features import STRONG_OISST, select_feature_mode
from pa_marine.metrics import climatology_probs, summarise
from pa_marine.models import fit_predict, make_estimators

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATIONS = ROOT / "configs/connemara_farms_stations.yaml"
DEFAULT_JOINED = ROOT / "data/processed/joined_features.parquet"
DEFAULT_TOXIN = ROOT / "data/processed/toxin_joined_features.parquet"
DEFAULT_OUT = ROOT / "data/processed"
IST = ZoneInfo("Europe/Dublin")

# Plain-language risk bands for growers (calibrated probability).
BANDS = (
    (0.15, "Higher", "Elevated chance of Dinophysis above the monitoring threshold in the next ~2 weeks relative to a quiet week."),
    (0.07, "Moderate", "Some seasonal / SST-linked risk — watch Marine Institute bulletins."),
    (0.0, "Lower", "Below typical seasonal risk for this week-of-year, or quiet conditions."),
)


def _now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")


def _raw_probs(est, X) -> np.ndarray:
    if hasattr(est, "predict_proba"):
        return est.predict_proba(X)[:, 1]
    d = est.decision_function(X)
    return 1.0 / (1.0 + np.exp(-d))


def _risk_band(p: float) -> tuple[str, str]:
    for thr, label, blurb in BANDS:
        if p >= thr:
            return label, blurb
    return "Lower", BANDS[-1][2]


def load_station_config(path: Path) -> tuple[pd.DataFrame, dict]:
    raw = yaml.safe_load(path.read_text())
    rows = []
    for s in raw.get("stations") or []:
        rows.append(
            {
                "site_key": s["site_key"],
                "grower_label": s.get("grower_label") or s.get("location_name"),
                "location_id": s.get("location_id"),
                "location_name": s.get("location_name"),
                "latitude": s.get("latitude"),
                "longitude": s.get("longitude"),
                "role": s.get("role"),
                "status": s.get("status"),
                "erddap_dataset": s.get("erddap_dataset"),
                "notes": (s.get("notes") or "").strip().replace("\n", " "),
            }
        )
    return pd.DataFrame(rows), raw


def _fit_national_dino(
    df: pd.DataFrame,
    feats: list[str],
    target: str = "y_dinophysis_nowcast",
) -> tuple[object, ProbCalibrator | None, dict, np.ndarray, np.ndarray]:
    """Train LightGBM (fallback logreg) on national train; calibrate on val."""
    train = df[df["split"] == "train"]
    val = df[df["split"] == "val"]
    ytr = train[target].astype(int)
    mtr = ytr.notna()
    Xtr = train.loc[mtr, feats]
    ytr = ytr.loc[mtr]
    clim_week = train.loc[mtr, "iso_week"].to_numpy()
    clim_y = ytr.to_numpy()

    estimators = make_estimators()
    # Prefer lightgbm / hist_gbdt / xgboost over logreg for primary scores.
    name = next((k for k in ("lightgbm", "hist_gbdt", "xgboost", "logreg") if k in estimators), "logreg")
    est = estimators[name]
    fit_predict(est, Xtr, ytr, Xtr)

    calibrator = None
    if not val.empty:
        yv = val[target].astype(int)
        mv = yv.notna()
        if int(mv.sum()) > 0 and int(yv.loc[mv].sum()) > 0:
            pr_val = _raw_probs(est, val.loc[mv, feats])
            calibrator = ProbCalibrator(method="auto").fit(yv.loc[mv].to_numpy(), pr_val)

    meta = {
        "model": name,
        "target": target,
        "feature_mode": "strong",
        "features": feats,
        "n_train": int(mtr.sum()),
        "n_train_pos": int(ytr.sum()),
        "calibration": calibrator.chosen_ if calibrator else None,
        "train_years": "2003-2018 (config year_split)",
        "val_years": "2019-2021",
        "test_years": "2022+",
    }
    return est, calibrator, meta, clim_week, clim_y


def _score_frame(
    work: pd.DataFrame,
    feats: list[str],
    est,
    calibrator: ProbCalibrator | None,
    clim_week: np.ndarray,
    clim_y: np.ndarray,
    score_col: str = "risk_score",
) -> pd.DataFrame:
    out = work.copy()
    if out.empty:
        out[score_col] = []
        out["clim_score"] = []
        out["risk_vs_clim"] = []
        return out
    X = out[feats]
    raw = _raw_probs(est, X)
    cal = calibrator.transform(raw) if calibrator is not None else raw
    clim = climatology_probs(clim_week, clim_y, out["iso_week"].to_numpy())
    out[score_col] = cal
    out["risk_score_raw"] = raw
    out["clim_score"] = clim
    out["risk_vs_clim"] = cal - clim
    bands = [_risk_band(float(p)) for p in cal]
    out["risk_band"] = [b[0] for b in bands]
    out["risk_plain"] = [b[1] for b in bands]
    return out


def _eval_subset(
    df: pd.DataFrame,
    feats: list[str],
    est,
    calibrator: ProbCalibrator | None,
    clim_week: np.ndarray,
    clim_y: np.ndarray,
    target: str,
    split: str,
) -> dict:
    ev = df[df["split"] == split]
    if ev.empty or target not in ev.columns:
        return {"error": "empty"}
    y = ev[target].astype(int)
    mask = y.notna()
    if int(mask.sum()) == 0 or int(y.loc[mask].sum()) == 0:
        return {
            "n": int(mask.sum()),
            "prevalence": float(y.loc[mask].mean()) if int(mask.sum()) else None,
            "note": "no positives or empty — PR-AUC undefined",
        }
    pr = _raw_probs(est, ev.loc[mask, feats])
    if calibrator is not None:
        pr = calibrator.transform(pr)
    clim = climatology_probs(clim_week, clim_y, ev.loc[mask, "iso_week"].to_numpy())
    return summarise(y.loc[mask].to_numpy(), pr, clim)


def _fit_dsp_optional(
    toxin_path: Path,
    cfg: dict,
    feats_template: list[str],
) -> tuple[object | None, ProbCalibrator | None, dict | None, list[str] | None]:
    """Optional national area-closed / DSP head on toxin_joined_features."""
    if not toxin_path.exists():
        return None, None, {"skipped": "toxin_joined_features missing"}, None
    tox = pd.read_parquet(toxin_path)
    from pa_marine.splits import year_split

    tox = tox.copy()
    tox["split"] = year_split(tox, cfg)
    if "closed" in tox.columns:
        tox["y_closed"] = pd.to_numeric(tox["closed"], errors="coerce")
    else:
        return None, None, {"skipped": "no closed column"}, None
    feats = [f for f in feats_template if f in tox.columns]
    if len(feats) < 5:
        return None, None, {"skipped": "strong features missing on toxin panel"}, None

    work = tox[tox["y_closed"].notna()].copy()
    train = work[work["split"] == "train"]
    val = work[work["split"] == "val"]
    if train.empty or int(train["y_closed"].sum()) == 0:
        return None, None, {"skipped": "no train closed positives"}, None

    estimators = make_estimators()
    name = next((k for k in ("lightgbm", "hist_gbdt", "xgboost", "logreg") if k in estimators), "logreg")
    est = estimators[name]
    ytr = train["y_closed"].astype(int)
    fit_predict(est, train[feats], ytr, train[feats])
    calibrator = None
    if not val.empty and int(val["y_closed"].sum()) > 0:
        pr_val = _raw_probs(est, val[feats])
        calibrator = ProbCalibrator(method="auto").fit(val["y_closed"].astype(int).to_numpy(), pr_val)
    meta = {
        "model": name,
        "target": "y_closed",
        "features": feats,
        "n_train": int(len(train)),
        "calibration": calibrator.chosen_ if calibrator else None,
        "note": "National area-closed head (multi-toxin + admin); not DSP-only.",
    }
    return est, calibrator, meta, feats


def build_html(
    latest: pd.DataFrame,
    stations: pd.DataFrame,
    meta: dict,
    metrics: dict,
    out_path: Path,
) -> None:
    rows_html = []
    for _, r in latest.iterrows():
        vs = r.get("risk_vs_clim")
        vs_txt = f"{vs:+.1%}" if pd.notna(vs) else "—"
        cells = r.get("count_dinophysis")
        cells_txt = f"{int(cells)}" if pd.notna(cells) else "no sample"
        dsp = r.get("dsp_closure_risk")
        dsp_txt = f"{dsp:.1%}" if pd.notna(dsp) else "—"
        rows_html.append(
            "<tr>"
            f"<td>{html.escape(str(r['grower_label']))}</td>"
            f"<td>{html.escape(str(r.get('week_label', '')))}</td>"
            f"<td><strong>{html.escape(str(r.get('risk_band', '')))}</strong> "
            f"({r['risk_score']:.1%})</td>"
            f"<td>{vs_txt} vs seasonal usual</td>"
            f"<td>{cells_txt}</td>"
            f"<td>{dsp_txt}</td>"
            f"<td>{html.escape(str(r.get('risk_plain', ''))[:160])}</td>"
            "</tr>"
        )

    gap_rows = stations[stations["status"].isin(["active_oisst_gap", "sparse_historical", "buoy_only"])]
    gaps = "".join(
        f"<li><strong>{html.escape(str(r.grower_label))}</strong> "
        f"({html.escape(str(r.status))}): {html.escape(str(r.notes)[:220])}</li>"
        for _, r in gap_rows.iterrows()
    )

    nat = metrics.get("national_test_calibrated") or {}
    sub = metrics.get("connemara_test_calibrated") or {}

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Connemara Farms — weekly HAB risk</title>
<style>
  body {{ font-family: system-ui, Segoe UI, sans-serif; margin: 1.5rem; max-width: 1100px; color: #1a1a1a; }}
  h1 {{ font-size: 1.45rem; }}
  .note {{ background: #f4f7fb; border-left: 4px solid #2b6cb0; padding: 0.75rem 1rem; margin: 1rem 0; }}
  .warn {{ background: #fff8e6; border-left: 4px solid #c05621; padding: 0.75rem 1rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.95rem; }}
  th, td {{ border: 1px solid #d0d7de; padding: 0.45rem 0.55rem; text-align: left; vertical-align: top; }}
  th {{ background: #eef2f7; }}
  .Higher {{ color: #9b2c2c; }}
  .Moderate {{ color: #c05621; }}
  .Lower {{ color: #276749; }}
  footer {{ margin-top: 1.5rem; font-size: 0.85rem; color: #555; }}
</style>
</head>
<body>
  <h1>Connemara Farms — weekly Dinophysis risk</h1>
  <p>Simple view for shellfish growers. Scores are <strong>research nowcasts</strong>
  from sea-surface temperature patterns (NOAA OISST) plus season and location —
  <em>not</em> an official Marine Institute warning.</p>
  <div class="note">
    <strong>How to read the score:</strong> probability that Dinophysis will be at or
    above 100 cells per litre in the current or next monitoring week (0–2 week
    nowcast). Compare to the “seasonal usual” for that week of year.
    Always follow official HAB / biotoxin notices before harvesting.
  </div>
  <p>Generated: <strong>{html.escape(meta.get('generated', ''))}</strong>.
  Model: national Irish <code>strong</code> OISST LightGBM (calibrated), applied to Connemara sites.
  Latest weeks shown: <strong>{html.escape(str(meta.get('latest_week_span', '')))}</strong>.</p>

  <h2>Latest site scores</h2>
  <table>
    <thead>
      <tr>
        <th>Site</th>
        <th>Week</th>
        <th>Risk</th>
        <th>vs seasonal usual</th>
        <th>Recent Dinophysis cells L⁻¹</th>
        <th>Closure-risk proxy</th>
        <th>Plain language</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html) if rows_html else '<tr><td colspan="7">No scored weeks in window.</td></tr>'}
    </tbody>
  </table>

  <h2>Skill (honest)</h2>
  <ul>
    <li>National test (2022+) calibrated PR-AUC:
      <strong>{nat.get('pr_auc', '—')}</strong>
      vs seasonal clim <strong>{nat.get('pr_auc_clim', '—')}</strong>
      (PR skill {nat.get('pr_auc_skill', '—')}).</li>
    <li>Connemara-site test subset:
      <strong>{sub.get('pr_auc', sub.get('note', '—'))}</strong>
      (n={sub.get('n', '—')}, prevalence={sub.get('prevalence', '—')}).</li>
  </ul>

  <div class="warn">
    <strong>Gaps / caveats</strong>
    <ul>{gaps}</ul>
    <p>Closure-risk proxy uses the national area-closed model (all toxins + admin rules),
    only where toxin/status join exists. Rosmuc lacks OISST SST at the station pixel.</p>
  </div>

  <footer>
    PA-Marine-Model · Connemara Farms product idea 2 · regenerate with
    <code>python scripts/score_connemara_farms.py</code>
  </footer>
</body>
</html>
"""
    out_path.write_text(body)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stations", default=str(DEFAULT_STATIONS))
    ap.add_argument("--joined", default=str(DEFAULT_JOINED))
    ap.add_argument("--toxin", default=str(DEFAULT_TOXIN))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument(
        "--latest-weeks",
        type=int,
        default=4,
        help="Number of most recent ISO weeks (by max week_start) for grower table.",
    )
    ap.add_argument("--skip-dsp", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_config()

    stations, raw_cfg = load_station_config(Path(args.stations))
    stations_path = out_dir / "connemara_farms_stations.csv"
    stations.to_csv(stations_path, index=False)

    nmp_ids = sorted({int(x) for x in stations["location_id"].dropna().astype(int)})
    df = pd.read_parquet(args.joined)
    feats = select_feature_mode(df, "strong")
    if set(feats) != STRONG_OISST and not STRONG_OISST.issubset(set(df.columns)):
        # Prefer canonical strong set order when all present.
        feats = [f for f in sorted(STRONG_OISST) if f in df.columns] or feats

    est, calibrator, model_meta, clim_week, clim_y = _fit_national_dino(df, feats)

    # National test metrics (full Ireland) for reference.
    metrics: dict = {
        "generated": _now_ist(),
        "model_choice": "national_apply_strong_oisst",
        "model_choice_rationale": (
            "Apply the national Irish Dinophysis strong-OISST model rather than "
            "retraining on Connemara alone: local positives are too sparse for a "
            "stable site-level fit, and the national protocol already has documented "
            "test skill (PR-AUC ≈ 0.293 vs clim ≈ 0.183)."
        ),
        "model": model_meta,
        "nmp_location_ids": nmp_ids,
        "national_test_calibrated": _eval_subset(
            df, feats, est, calibrator, clim_week, clim_y, "y_dinophysis_nowcast", "test"
        ),
        "national_val_calibrated": _eval_subset(
            df, feats, est, calibrator, clim_week, clim_y, "y_dinophysis_nowcast", "val"
        ),
    }

    local = df[df["location_id"].isin(nmp_ids)].copy()
    metrics["connemara_coverage"] = {
        "n_station_weeks": int(len(local)),
        "n_stations_scored": int(local["location_id"].nunique()),
        "week_span": [
            str(pd.to_datetime(local["week_start"]).min()) if len(local) else None,
            str(pd.to_datetime(local["week_start"]).max()) if len(local) else None,
        ],
        "sst_nonnull_rate": float(local["sst"].notna().mean()) if "sst" in local.columns and len(local) else None,
        "dino_positives": int(local["y_dinophysis"].fillna(0).sum()) if "y_dinophysis" in local.columns else None,
        "per_station": local.groupby("location_id")
        .agg(
            name=("location_name", "first"),
            n_weeks=("week_start", "size"),
            year_min=("iso_year", "min"),
            year_max=("iso_year", "max"),
            sst_nn=("sst", lambda s: int(s.notna().sum())),
            dino_pos=("y_dinophysis", lambda s: int(pd.to_numeric(s, errors="coerce").fillna(0).sum())),
        )
        .reset_index()
        .to_dict(orient="records"),
    }
    metrics["connemara_test_calibrated"] = _eval_subset(
        local, feats, est, calibrator, clim_week, clim_y, "y_dinophysis_nowcast", "test"
    )

    scored = _score_frame(local, feats, est, calibrator, clim_week, clim_y, "risk_score")
    # Attach grower labels
    lab = stations.dropna(subset=["location_id"]).copy()
    lab["location_id"] = lab["location_id"].astype(int)
    scored = scored.merge(
        lab[["location_id", "site_key", "grower_label", "status", "role"]],
        on="location_id",
        how="left",
    )

    # Optional DSP / closure proxy on overlapping toxin rows
    dsp_est, dsp_cal, dsp_meta, dsp_feats = (None, None, None, None)
    if not args.skip_dsp:
        dsp_est, dsp_cal, dsp_meta, dsp_feats = _fit_dsp_optional(Path(args.toxin), cfg, feats)
    metrics["dsp_closure_model"] = dsp_meta
    scored["dsp_closure_risk"] = np.nan
    if dsp_est is not None and dsp_feats is not None and Path(args.toxin).exists():
        tox = pd.read_parquet(args.toxin)
        tox_loc = tox[tox["location_id"].isin(nmp_ids)].copy()
        if not tox_loc.empty and all(f in tox_loc.columns for f in dsp_feats):
            # Score toxin rows then merge max closure risk per station-week onto phyto scores
            raw = _raw_probs(dsp_est, tox_loc[dsp_feats])
            cal = dsp_cal.transform(raw) if dsp_cal is not None else raw
            tox_loc = tox_loc.assign(dsp_closure_risk=cal)
            keys = ["location_id", "iso_year", "iso_week"]
            merge_cols = keys + ["dsp_closure_risk"]
            scored = scored.drop(columns=["dsp_closure_risk"], errors="ignore")
            scored = scored.merge(
                tox_loc[merge_cols].drop_duplicates(keys),
                on=keys,
                how="left",
            )

    # Grower latest table: last N sampled weeks *per site* (so quieter sites still appear)
    scored["week_start"] = pd.to_datetime(scored["week_start"])
    grower_roles = {"nmp_core", "nmp_nearby"}
    recent_pool = scored[
        scored["role"].isin(grower_roles) & (scored["status"] != "sparse_historical")
    ].copy()
    parts = []
    for _, g in recent_pool.groupby("location_id", sort=False):
        parts.append(g.sort_values("week_start", ascending=False).head(args.latest_weeks))
    latest = pd.concat(parts, ignore_index=True) if parts else recent_pool.iloc[0:0].copy()
    max_weeks = sorted(latest["week_start"].dropna().unique()) if len(latest) else []
    latest["week_label"] = latest.apply(
        lambda r: f"{int(r['iso_year'])}-W{int(r['iso_week']):02d}", axis=1
    )
    latest = latest.sort_values(["week_start", "grower_label"], ascending=[False, True])

    keep_cols = [
        "grower_label",
        "site_key",
        "location_id",
        "location_name",
        "iso_year",
        "iso_week",
        "week_start",
        "week_label",
        "risk_score",
        "clim_score",
        "risk_vs_clim",
        "risk_band",
        "risk_plain",
        "count_dinophysis",
        "y_dinophysis",
        "y_dinophysis_nowcast",
        "dsp_closure_risk",
        "sst",
        "status",
        "role",
        "split",
    ]
    keep_cols = [c for c in keep_cols if c in latest.columns]
    latest_out = latest[keep_cols]

    # Full scores export (compact)
    full_cols = [
        c
        for c in [
            "grower_label",
            "site_key",
            "location_id",
            "location_name",
            "iso_year",
            "iso_week",
            "week_start",
            "risk_score",
            "risk_score_raw",
            "clim_score",
            "risk_vs_clim",
            "risk_band",
            "count_dinophysis",
            "y_dinophysis",
            "y_dinophysis_nowcast",
            "dsp_closure_risk",
            "sst",
            "ssta",
            "status",
            "role",
            "split",
            "latitude",
            "longitude",
        ]
        if c in scored.columns
    ]
    scores_path = out_dir / "connemara_farms_scores.csv"
    latest_path = out_dir / "connemara_farms_latest.csv"
    html_path = out_dir / "connemara_farms_scores.html"
    metrics_path = out_dir / "connemara_farms_metrics.json"

    scored[full_cols].sort_values(["week_start", "location_id"]).to_csv(scores_path, index=False)
    latest_out.to_csv(latest_path, index=False)

    html_meta = {
        "generated": metrics["generated"],
        "latest_week_span": (
            f"{pd.to_datetime(max_weeks).min().date()} → {pd.to_datetime(max_weeks).max().date()}"
            if len(max_weeks)
            else "n/a"
        ),
    }
    # Round metrics floats for JSON readability
    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_clean(v) for v in o]
        if isinstance(o, (np.floating, float)):
            x = float(o)
            return None if not np.isfinite(x) else round(x, 6)
        if isinstance(o, (np.integer,)):
            return int(o)
        return o

    metrics["outputs"] = {
        "stations_csv": str(stations_path.relative_to(ROOT)),
        "scores_csv": str(scores_path.relative_to(ROOT)),
        "latest_csv": str(latest_path.relative_to(ROOT)),
        "html": str(html_path.relative_to(ROOT)),
    }
    metrics_path.write_text(json.dumps(_clean(metrics), indent=2))
    build_html(latest_out, stations, html_meta, _clean(metrics), html_path)

    print(
        json.dumps(
            {
                "generated": metrics["generated"],
                "n_scored_rows": int(len(scored)),
                "n_latest_rows": int(len(latest_out)),
                "national_test_pr_auc": metrics["national_test_calibrated"].get("pr_auc"),
                "connemara_test": metrics["connemara_test_calibrated"],
                "outputs": metrics["outputs"],
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
