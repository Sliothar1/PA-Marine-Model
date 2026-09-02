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
    (
        0.15,
        "Higher",
        "Higher watch — elevated chance Dinophysis is at or above 100 cells/L in this or next week. Check MI bulletins before harvest plans.",
    ),
    (
        0.07,
        "Moderate",
        "Moderate watch — some seasonal / SST-linked risk. Keep an eye on MI bulletins and recent cell counts.",
    ),
    (
        0.0,
        "Lower",
        "Lower watch — below typical risk for this week-of-year, or quiet conditions. Still follow official notices.",
    ),
)

# Sites shown first on the grower dashboard (Killary trio + local sentinels).
PRIORITY_SITE_KEYS = (
    "killary_inner",
    "killary_middle",
    "killary_outer",
    "lehannagh_pool_nmp",
    "mace_head_buoy",
    "lehanagh_buoy",
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
    """Grower-facing dashboard: latest week cards, priority sites, honest gaps."""

    def _fmt_pct(v) -> str:
        return f"{float(v):.1%}" if pd.notna(v) else "—"

    def _fmt_cells(v) -> str:
        if pd.isna(v):
            return "no sample"
        try:
            return f"{int(v)}"
        except (TypeError, ValueError):
            return str(v)

    def _band_class(band: str) -> str:
        b = (band or "").strip()
        return b if b in ("Higher", "Moderate", "Lower") else "Lower"

    def _site_rank(site_key: str, grower_label: str) -> tuple:
        try:
            pri = PRIORITY_SITE_KEYS.index(site_key)
        except ValueError:
            pri = 100
        # Keep Killary trio together, then other scored sites A–Z.
        return (pri, str(grower_label or ""))

    # --- Latest ISO week snapshot (most recent week_start across grower table) ---
    latest_week_label = ""
    latest_week_start = None
    snapshot = latest.iloc[0:0].copy()
    prior = latest.copy()
    if len(latest) and "week_start" in latest.columns:
        ws = pd.to_datetime(latest["week_start"], errors="coerce")
        if ws.notna().any():
            latest_week_start = ws.max()
            mask = ws == latest_week_start
            snapshot = latest.loc[mask].copy()
            prior = latest.loc[~mask].copy()
            if "week_label" in snapshot.columns and len(snapshot):
                latest_week_label = str(snapshot["week_label"].iloc[0])
            else:
                latest_week_label = (
                    f"{latest_week_start.isocalendar().year}-W"
                    f"{latest_week_start.isocalendar().week:02d}"
                )

    # Priority scored sites for the latest week (Killary trio first, then others).
    card_html = []
    snap_by_key = {}
    if len(snapshot):
        for _, r in snapshot.iterrows():
            snap_by_key[str(r.get("site_key", ""))] = r

    def _card_from_row(r) -> str:
        sk = str(r.get("site_key", ""))
        band = _band_class(str(r.get("risk_band", "")))
        vs = r.get("risk_vs_clim")
        vs_txt = f"{vs:+.1%} vs seasonal usual" if pd.notna(vs) else "vs seasonal usual —"
        gap_note = ""
        if str(r.get("status", "")) == "active_oisst_gap":
            gap_note = (
                '<div class="card-gap">⚠ SST gap at this site — score uses '
                "season + location only (no OISST).</div>"
            )
        is_priority = sk in PRIORITY_SITE_KEYS[:3]
        pri_badge = (
            '<span class="badge-pri">Priority site</span>' if is_priority else ""
        )
        return (
            f'<article class="card band-{html.escape(band)}">'
            f'<div class="card-top">'
            f'<h3>{html.escape(str(r.get("grower_label", "")))}{pri_badge}</h3>'
            f'<span class="band-pill {html.escape(band)}">{html.escape(band)} watch</span>'
            f"</div>"
            f'<p class="prob">Model chance: <strong>{_fmt_pct(r.get("risk_score"))}</strong></p>'
            f'<p class="vs">{html.escape(vs_txt)}</p>'
            f'<p class="cells">Recent Dinophysis: <strong>{_fmt_cells(r.get("count_dinophysis"))}</strong> cells/L</p>'
            f'<p class="plain">{html.escape(str(r.get("risk_plain", ""))[:220])}</p>'
            f"{gap_note}"
            f"</article>"
        )

    def _placeholder_card(sk: str) -> str:
        lab_row = stations[stations["site_key"] == sk]
        lab = (
            str(lab_row["grower_label"].iloc[0])
            if len(lab_row)
            else sk.replace("_", " ").title()
        )
        return (
            f'<article class="card band-none">'
            f'<div class="card-top">'
            f'<h3>{html.escape(lab)}<span class="badge-pri">Priority site</span></h3>'
            f'<span class="band-pill none">No sample this week</span>'
            f"</div>"
            f'<p class="plain">No MI phytoplankton sample in the latest scored week '
            f"({html.escape(latest_week_label)}). Check recent weeks below and official bulletins.</p>"
            f"</article>"
        )

    # Always emit Killary Inner → Middle → Outer first.
    for sk in ("killary_inner", "killary_middle", "killary_outer"):
        if sk in snap_by_key:
            card_html.append(_card_from_row(snap_by_key[sk]))
        else:
            card_html.append(_placeholder_card(sk))

    # Then other sites present in the latest week (A–Z by grower label).
    other = [
        snap_by_key[k]
        for k in snap_by_key
        if k not in ("killary_inner", "killary_middle", "killary_outer")
    ]
    other.sort(key=lambda r: str(r.get("grower_label", "")))
    for r in other:
        card_html.append(_card_from_row(r))

    # Full latest-week table (all sites that have that week)
    snap_rows = []
    if len(snapshot):
        snap = snapshot.copy()
        snap["_rank"] = [
            _site_rank(str(r.get("site_key", "")), str(r.get("grower_label", "")))
            for _, r in snap.iterrows()
        ]
        snap = snap.sort_values("_rank")
        for _, r in snap.iterrows():
            band = _band_class(str(r.get("risk_band", "")))
            vs = r.get("risk_vs_clim")
            vs_txt = f"{vs:+.1%}" if pd.notna(vs) else "—"
            dsp = r.get("dsp_closure_risk")
            dsp_txt = _fmt_pct(dsp) if pd.notna(dsp) else "—"
            gap = "SST gap" if str(r.get("status", "")) == "active_oisst_gap" else ""
            snap_rows.append(
                "<tr>"
                f"<td>{html.escape(str(r.get('grower_label', '')))}"
                f"{' <span class=\"tag-gap\">' + gap + '</span>' if gap else ''}</td>"
                f"<td>{html.escape(str(r.get('week_label', '')))}</td>"
                f'<td class="{html.escape(band)}"><strong>{html.escape(band)}</strong> '
                f"({_fmt_pct(r.get('risk_score'))})</td>"
                f"<td>{vs_txt}</td>"
                f"<td>{_fmt_cells(r.get('count_dinophysis'))}</td>"
                f"<td>{dsp_txt}</td>"
                f"<td>{html.escape(str(r.get('risk_plain', ''))[:160])}</td>"
                "</tr>"
            )

    # Prior weeks (history)
    hist_rows = []
    if len(prior):
        hist = prior.copy()
        hist["_rank"] = [
            (
                -pd.Timestamp(r["week_start"]).toordinal()
                if pd.notna(r.get("week_start"))
                else 0,
            )
            + _site_rank(str(r.get("site_key", "")), str(r.get("grower_label", "")))
            for _, r in hist.iterrows()
        ]
        hist = hist.sort_values(["week_start", "_rank"], ascending=[False, True])
        for _, r in hist.iterrows():
            band = _band_class(str(r.get("risk_band", "")))
            vs = r.get("risk_vs_clim")
            vs_txt = f"{vs:+.1%}" if pd.notna(vs) else "—"
            dsp = r.get("dsp_closure_risk")
            dsp_txt = _fmt_pct(dsp) if pd.notna(dsp) else "—"
            hist_rows.append(
                "<tr>"
                f"<td>{html.escape(str(r.get('grower_label', '')))}</td>"
                f"<td>{html.escape(str(r.get('week_label', '')))}</td>"
                f'<td class="{html.escape(band)}"><strong>{html.escape(band)}</strong> '
                f"({_fmt_pct(r.get('risk_score'))})</td>"
                f"<td>{vs_txt}</td>"
                f"<td>{_fmt_cells(r.get('count_dinophysis'))}</td>"
                f"<td>{dsp_txt}</td>"
                "</tr>"
            )

    # Sentinel / prominence panel (Mace Head, Lehanagh buoy + sparse NMP)
    sentinel_keys = ("mace_head_buoy", "lehanagh_buoy", "lehannagh_pool_nmp")
    sentinel_html = []
    for sk in sentinel_keys:
        row = stations[stations["site_key"] == sk]
        if row.empty:
            continue
        r = row.iloc[0]
        status = str(r.get("status", ""))
        if status == "buoy_only":
            status_txt = "Buoy only — hydrography context, not HAB-scored"
        elif status == "sparse_historical":
            status_txt = "Sparse / historical NMP only — not in latest grower table"
        else:
            status_txt = status
        sentinel_html.append(
            f"<li><strong>{html.escape(str(r.grower_label))}</strong> — "
            f"{html.escape(status_txt)}. "
            f"{html.escape(str(r.notes)[:260])}</li>"
        )

    gap_rows = stations[
        stations["status"].isin(["active_oisst_gap", "sparse_historical", "buoy_only"])
    ]
    gaps = "".join(
        f"<li><strong>{html.escape(str(r.grower_label))}</strong> "
        f"({html.escape(str(r.status))}): {html.escape(str(r.notes)[:260])}</li>"
        for _, r in gap_rows.iterrows()
    )

    nat = metrics.get("national_test_calibrated") or {}
    sub = metrics.get("connemara_test_calibrated") or {}
    week_disp = latest_week_label or meta.get("latest_week_span", "n/a")
    week_date = (
        str(pd.Timestamp(latest_week_start).date()) if latest_week_start is not None else ""
    )

    band_legend = """
  <div class="bands" aria-label="Risk band legend">
    <div class="band-item Higher"><strong>Higher</strong> ≥ 15%<br/>
      <span>Elevated chance of Dinophysis ≥ 100 cells/L in this or next week. Check MI bulletins before harvest plans.</span></div>
    <div class="band-item Moderate"><strong>Moderate</strong> 7–15%<br/>
      <span>Some seasonal / SST-linked risk. Watch bulletins and recent cell counts.</span></div>
    <div class="band-item Lower"><strong>Lower</strong> &lt; 7%<br/>
      <span>Below typical risk for this week-of-year, or quiet conditions. Still follow official notices.</span></div>
  </div>
"""

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Connemara Farms — weekly HAB risk</title>
<style>
  :root {{
    --ink: #1a1a1a; --muted: #555; --line: #d0d7de;
    --bg: #f7f9fc; --card: #fff; --pri: #2b6cb0;
    --higher: #9b2c2c; --moderate: #c05621; --lower: #276749;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: system-ui, Segoe UI, sans-serif; margin: 0; color: var(--ink);
    background: var(--bg); line-height: 1.45;
  }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 1.25rem 1.25rem 2.5rem; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 0.35rem; }}
  h2 {{ font-size: 1.15rem; margin: 1.6rem 0 0.6rem; }}
  h3 {{ font-size: 1.05rem; margin: 0; }}
  .sub {{ color: var(--muted); margin: 0 0 1rem; }}
  .note, .warn, .sentinel {{
    background: #fff; border-left: 4px solid var(--pri);
    padding: 0.75rem 1rem; margin: 1rem 0; border-radius: 0 6px 6px 0;
  }}
  .warn {{ border-left-color: var(--moderate); background: #fff8e6; }}
  .sentinel {{ border-left-color: #553c9a; background: #f6f3fb; }}
  .bands {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 0.6rem; margin: 1rem 0;
  }}
  .band-item {{
    background: #fff; border: 1px solid var(--line); border-radius: 8px;
    padding: 0.65rem 0.75rem; font-size: 0.9rem;
  }}
  .band-item.Higher {{ border-top: 4px solid var(--higher); }}
  .band-item.Moderate {{ border-top: 4px solid var(--moderate); }}
  .band-item.Lower {{ border-top: 4px solid var(--lower); }}
  .band-item span {{ color: var(--muted); font-size: 0.82rem; }}
  .latest-banner {{
    background: linear-gradient(135deg, #1a365d, #2b6cb0);
    color: #fff; border-radius: 10px; padding: 1rem 1.15rem; margin: 1rem 0 1.1rem;
  }}
  .latest-banner strong {{ font-size: 1.2rem; }}
  .latest-banner p {{ margin: 0.35rem 0 0; opacity: 0.95; font-size: 0.95rem; }}
  .cards {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 0.75rem; margin: 0.75rem 0 1.25rem;
  }}
  .card {{
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 0.85rem 0.95rem; border-top: 5px solid #a0aec0;
  }}
  .card.band-Higher {{ border-top-color: var(--higher); }}
  .card.band-Moderate {{ border-top-color: var(--moderate); }}
  .card.band-Lower {{ border-top-color: var(--lower); }}
  .card.band-none {{ border-top-color: #a0aec0; opacity: 0.92; }}
  .card-top {{ display: flex; justify-content: space-between; gap: 0.5rem; align-items: flex-start; }}
  .band-pill {{
    font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.02em; padding: 0.2rem 0.45rem; border-radius: 999px;
    white-space: nowrap; background: #edf2f7; color: #2d3748;
  }}
  .band-pill.Higher {{ background: #fff5f5; color: var(--higher); }}
  .band-pill.Moderate {{ background: #fffaf0; color: var(--moderate); }}
  .band-pill.Lower {{ background: #f0fff4; color: var(--lower); }}
  .band-pill.none {{ background: #edf2f7; color: #4a5568; }}
  .badge-pri {{
    display: inline-block; margin-left: 0.4rem; font-size: 0.68rem;
    background: #ebf8ff; color: #2b6cb0; padding: 0.1rem 0.35rem;
    border-radius: 4px; vertical-align: middle; font-weight: 600;
  }}
  .card .prob, .card .vs, .card .cells, .card .plain {{ margin: 0.35rem 0 0; font-size: 0.9rem; }}
  .card-gap {{
    margin-top: 0.5rem; font-size: 0.82rem; color: var(--moderate);
    background: #fffaf0; padding: 0.35rem 0.45rem; border-radius: 4px;
  }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.92rem; background: #fff; }}
  th, td {{ border: 1px solid var(--line); padding: 0.45rem 0.55rem; text-align: left; vertical-align: top; }}
  th {{ background: #eef2f7; position: sticky; top: 0; }}
  .Higher {{ color: var(--higher); }}
  .Moderate {{ color: var(--moderate); }}
  .Lower {{ color: var(--lower); }}
  .tag-gap {{
    font-size: 0.72rem; background: #fffaf0; color: var(--moderate);
    padding: 0.05rem 0.3rem; border-radius: 3px; margin-left: 0.25rem;
  }}
  .scroll {{ overflow-x: auto; margin: 0.5rem 0 1rem; border-radius: 6px; }}
  footer {{ margin-top: 1.75rem; font-size: 0.85rem; color: var(--muted); }}
  code {{ font-size: 0.88em; }}
  ul.compact {{ margin: 0.4rem 0; padding-left: 1.2rem; }}
  ul.compact li {{ margin: 0.25rem 0; }}
  @media (max-width: 640px) {{
    .wrap {{ padding: 0.85rem; }}
    h1 {{ font-size: 1.25rem; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Connemara Farms — weekly Dinophysis risk</h1>
  <p class="sub">Grower / co-op dashboard. Research nowcasts from sea-surface temperature
  (NOAA OISST) plus season and location — <em>not</em> an official Marine Institute warning.
  Always follow official HAB / biotoxin notices before harvesting.</p>

  <div class="note">
    <strong>How to read a score:</strong> calibrated probability that Dinophysis will be
    at or above <strong>100 cells per litre</strong> in the current or next monitoring week
    (0–2 week nowcast). Compare to the “seasonal usual” for that week of year.
    Bands are communication aids for growers — not regulatory cut-offs.
  </div>

  <h2>Risk bands (plain English)</h2>
  {band_legend}

  <div class="latest-banner">
    <div>Latest scored week</div>
    <strong>{html.escape(str(week_disp))}</strong>
    {" · week starting " + html.escape(week_date) if week_date else ""}
    <p>Generated {html.escape(meta.get("generated", ""))}. National Irish
    <code>strong</code> OISST model applied to Connemara NMP sites.
    Showing last sampled weeks per active site
    ({html.escape(str(meta.get("latest_week_span", "")))}).</p>
  </div>

  <h2>This week at a glance</h2>
  <p class="sub">Latest sampled week only. <strong>Killary Inner / Middle / Outer</strong> are listed
  first (priority for fjord co-ops). Missing Killary samples show a “no sample” card.
  Mace Head &amp; Lehanagh are called out in the sentinel panel below (not HAB-scored).</p>
  <div class="cards">
    {''.join(card_html) if card_html else '<p>No scored weeks in the grower window.</p>'}
  </div>

  <h2>This week — all sampled sites</h2>
  <div class="scroll">
  <table>
    <thead>
      <tr>
        <th>Site</th>
        <th>Week</th>
        <th>Risk band</th>
        <th>vs seasonal usual</th>
        <th>Dinophysis cells/L</th>
        <th>Closure-risk proxy</th>
        <th>What it means</th>
      </tr>
    </thead>
    <tbody>
      {''.join(snap_rows) if snap_rows else '<tr><td colspan="7">No sites sampled in the latest week.</td></tr>'}
    </tbody>
  </table>
  </div>

  <div class="sentinel">
    <strong>Mace Head &amp; Lehanagh (prominence / context)</strong>
    <p style="margin:0.4rem 0 0.2rem">These local sentinels matter for Connemara growers but are
    <em>not</em> Dinophysis exceedance scores. Use them as hydrography / site-continuity context
    alongside MI bulletins — see <code>data/processed/local_sites_report.md</code>.</p>
    <ul class="compact">{''.join(sentinel_html)}</ul>
  </div>

  <h2>Recent weeks (same sites)</h2>
  <p class="sub">Earlier sampled weeks in the grower table (not the latest week above).</p>
  <div class="scroll">
  <table>
    <thead>
      <tr>
        <th>Site</th>
        <th>Week</th>
        <th>Risk band</th>
        <th>vs seasonal usual</th>
        <th>Dinophysis cells/L</th>
        <th>Closure-risk proxy</th>
      </tr>
    </thead>
    <tbody>
      {''.join(hist_rows) if hist_rows else '<tr><td colspan="6">No earlier weeks in the current grower window.</td></tr>'}
    </tbody>
  </table>
  </div>

  <h2>Skill (honest)</h2>
  <ul class="compact">
    <li>National test (2022+) calibrated PR-AUC:
      <strong>{nat.get('pr_auc', '—')}</strong>
      vs seasonal clim <strong>{nat.get('pr_auc_clim', '—')}</strong>
      (PR skill {nat.get('pr_auc_skill', '—')}).</li>
    <li>Connemara-site test subset:
      <strong>{sub.get('pr_auc', sub.get('note', '—'))}</strong>
      (n={sub.get('n', '—')}, prevalence={sub.get('prevalence', '—')}).
      Local positives are rare — treat scores as seasonal + SST context, not a crystal ball.</li>
  </ul>

  <div class="warn">
    <strong>Data gaps &amp; caveats (read these)</strong>
    <ul class="compact">{gaps}</ul>
    <ul class="compact">
      <li><strong>Rosmuc OISST nulls:</strong> HAB labels exist, but satellite SST is missing at the
        station pixel — scores there lean on week-of-year and location only.</li>
      <li><strong>Lehanagh NMP:</strong> sparse / historical-only (ends ~2020); excluded from the
        latest grower table. The nearby Lehanagh buoy is separate and buoy-only.</li>
      <li><strong>Mace Head / Lehanagh buoys:</strong> buoy-only hydrography — no Dinophysis labels,
        not scored for HAB exceedance.</li>
      <li><strong>Closure-risk proxy:</strong> national area-closed model (all toxins + admin rules),
        only where toxin/status join exists; often “—” when toxin ingest lags phyto.</li>
      <li><strong>Irregular sampling:</strong> a missing week is “not sampled”, not a true negative.</li>
    </ul>
  </div>

  <footer>
    PA-Marine-Model · Connemara Farms product idea 2 ·
    Grower guide: <code>CONNEMARA_GROWER_README.md</code> ·
    Regenerate with <code>python3 scripts/score_connemara_farms.py</code>
  </footer>
</div>
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
