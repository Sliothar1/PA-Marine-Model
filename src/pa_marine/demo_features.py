"""Demo-lane station×week empirical risk + SST coverage flags.

This is a **PA demo workstream** helper. It is not part of the Cork spine.

Cork judge-card lock (do not weaken):
  STRONG_OISST ~0.295 calibrated test PR-AUC vs week-of-year climatology.
  Chl / ODYSSEA remain narrative-only.

Motivation (cited, not re-claimed here): Claude CONTEXT on
``review/claude-patch-2`` reported a station×week lookup ≈ **0.284** PR-AUC
on the real panel, close to the published STRONG_OISST model. This module
exports those rates as **features / baseline probabilities** so Cork
storytelling can show “which farms bloom which week” without merging that
science-review branch.

Status: **demo-useful + candidate for a later ablation**. Do not quote a
national skill lift until an honest gate file exists.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from pa_marine.erddap import lon_to_oisst_360
from pa_marine.sst import snap_oisst

EPS = 1e-9
DEMO_RATE_COLS = (
    "demo_sw_station_rate",
    "demo_sw_week_rate",
    "demo_sw_station_week_rate",
)
DEMO_COVERAGE_COLS = (
    "cov_sst_missing",
    "cov_sst_always_missing",
    "cov_snap_dist_deg",
    "cov_snap_dist_km",
)


def _logit(p: np.ndarray | float) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1.0 - 1e-6)
    return np.log(p / (1.0 - p))


def _expit(x: np.ndarray | float) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


def _shrunk_group_rate(
    keys: np.ndarray, y: np.ndarray, prior: float, k: float = 20.0
) -> dict[Any, float]:
    """Empirical-Bayes group mean shrunk toward ``prior`` with pseudo-count ``k``."""
    out: dict[Any, float] = {}
    df = pd.DataFrame({"k": keys, "y": y})
    g = df.groupby("k", sort=False)["y"].agg(["sum", "size"])
    for key, (s, n) in zip(g.index, g.to_numpy()):
        out[key] = float((s + k * prior) / (n + k))
    return out


def station_week_baseline_probs(
    train: pd.DataFrame,
    evalset: pd.DataFrame,
    target: str = "y_dinophysis_nowcast",
    *,
    station_col: str = "location_id",
    week_col: str = "iso_week",
    k_station: float = 20.0,
    k_week: float = 20.0,
) -> np.ndarray:
    """Logit-additive station + week-of-year climatology (train labels only).

    logit(p) = logit(p_global) + station effect + week effect.

    Additive in logit rather than a raw station×week cell mean because those
    cells are sparse (hundreds of stations × 52 weeks). Unseen stations/weeks
    fall back to the global train rate.
    """
    if target not in train.columns or train.empty or evalset.empty:
        return np.full(len(evalset), np.nan)
    ytr = pd.to_numeric(train[target], errors="coerce").to_numpy(dtype=float)
    m = np.isfinite(ytr)
    ytr = ytr[m]
    if ytr.size == 0:
        return np.full(len(evalset), np.nan)
    p_global = float(np.mean(ytr))
    if p_global <= 0.0 or p_global >= 1.0:
        return np.full(len(evalset), float(np.clip(p_global, EPS, 1.0 - EPS)))

    st_keys = train.loc[m, station_col].to_numpy()
    wk_keys = train.loc[m, week_col].to_numpy()
    st_rate = _shrunk_group_rate(st_keys, ytr, p_global, k_station)
    wk_rate = _shrunk_group_rate(wk_keys, ytr, p_global, k_week)
    base = float(_logit(p_global))
    st_eff = {s: float(_logit(r)) - base for s, r in st_rate.items()}
    wk_eff = {w: float(_logit(r)) - base for w, r in wk_rate.items()}
    ev_st = evalset[station_col].to_numpy()
    ev_wk = evalset[week_col].to_numpy()
    out = base + np.array([st_eff.get(s, 0.0) for s in ev_st]) + np.array(
        [wk_eff.get(w, 0.0) for w in ev_wk]
    )
    return _expit(out)


def attach_station_week_features(
    df: pd.DataFrame,
    *,
    target: str = "y_dinophysis_nowcast",
    split_col: str = "split",
    station_col: str = "location_id",
    week_col: str = "iso_week",
    train_value: str = "train",
) -> pd.DataFrame:
    """Attach train-only station / week / station×week empirical-risk columns.

    Rates are fit on ``split == train`` only (no val/test label leakage).
    If ``split`` or ``target`` is missing, the three columns are left as NaN.
    """
    out = df.copy()
    for c in DEMO_RATE_COLS:
        out[c] = np.nan
    if target not in out.columns or split_col not in out.columns:
        return out
    train = out[out[split_col] == train_value]
    if train.empty:
        return out
    ytr = pd.to_numeric(train[target], errors="coerce").to_numpy(dtype=float)
    m = np.isfinite(ytr)
    if not m.any():
        return out
    ytr = ytr[m]
    p_global = float(np.mean(ytr))
    st_rate = _shrunk_group_rate(train.loc[m, station_col].to_numpy(), ytr, p_global)
    wk_rate = _shrunk_group_rate(train.loc[m, week_col].to_numpy(), ytr, p_global)
    out["demo_sw_station_rate"] = out[station_col].map(st_rate).astype(float)
    out["demo_sw_station_rate"] = out["demo_sw_station_rate"].fillna(p_global)
    out["demo_sw_week_rate"] = out[week_col].map(wk_rate).astype(float)
    out["demo_sw_week_rate"] = out["demo_sw_week_rate"].fillna(p_global)
    out["demo_sw_station_week_rate"] = station_week_baseline_probs(
        train, out, target, station_col=station_col, week_col=week_col
    )
    return out


def naive_oisst_snap(lat: float, lon: float) -> tuple[float, float]:
    """Naive 0.25° OISST cell centre for a station (not nearest-ocean)."""
    lat_s = float(snap_oisst(float(lat)))
    lon360_s = float(snap_oisst(lon_to_oisst_360(float(lon))))
    lon_s = lon360_s - 360.0 if lon360_s > 180.0 else lon360_s
    return lat_s, lon_s


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2.0) ** 2
    return float(2.0 * r * np.arcsin(np.sqrt(min(1.0, a))))


def attach_sst_coverage_flags(
    df: pd.DataFrame,
    *,
    sst_col: str = "sst",
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    station_col: str = "location_id",
) -> pd.DataFrame:
    """SST-missing / landmask-suspect / naive OISST snap-distance flags.

    ``cov_sst_always_missing`` is the Rosmuc-style landmask story: the station
    never has finite SST in this frame. ``cov_snap_dist_*`` is the distance to
    the **naive** 0.25° snap (already computable from ``sst.snap_oisst``), not
    a true nearest-ocean search (that needs an ocean-mask cube).
    If ``dist_deg`` is already present (nearest-ocean extract), it is copied
    to ``cov_nearest_ocean_dist_deg`` without being renamed.
    """
    out = df.copy()
    if sst_col in out.columns:
        missing = pd.to_numeric(out[sst_col], errors="coerce").isna()
        out["cov_sst_missing"] = missing.astype(int)
        always = out.groupby(station_col)[sst_col].transform(
            lambda s: pd.to_numeric(s, errors="coerce").isna().all()
        )
        out["cov_sst_always_missing"] = always.astype(int)
    else:
        out["cov_sst_missing"] = np.nan
        out["cov_sst_always_missing"] = np.nan

    if lat_col in out.columns and lon_col in out.columns:
        dist_deg = []
        dist_km = []
        for lat, lon in zip(out[lat_col].to_numpy(), out[lon_col].to_numpy()):
            if not (np.isfinite(lat) and np.isfinite(lon)):
                dist_deg.append(np.nan)
                dist_km.append(np.nan)
                continue
            la_s, lo_s = naive_oisst_snap(float(lat), float(lon))
            dlat = float(lat) - la_s
            # approximate degree distance on the snap grid
            dlon = float(lon) - lo_s
            dist_deg.append(float(np.hypot(dlat, dlon)))
            dist_km.append(_haversine_km(float(lat), float(lon), la_s, lo_s))
        out["cov_snap_dist_deg"] = dist_deg
        out["cov_snap_dist_km"] = dist_km
    else:
        out["cov_snap_dist_deg"] = np.nan
        out["cov_snap_dist_km"] = np.nan

    if "dist_deg" in out.columns and "cov_nearest_ocean_dist_deg" not in out.columns:
        out["cov_nearest_ocean_dist_deg"] = pd.to_numeric(out["dist_deg"], errors="coerce")
    return out


def attach_demo_features(
    df: pd.DataFrame,
    *,
    target: str = "y_dinophysis_nowcast",
    split_col: str = "split",
) -> pd.DataFrame:
    """Coverage flags + train-only station×week rates in one pass."""
    out = attach_sst_coverage_flags(df)
    return attach_station_week_features(out, target=target, split_col=split_col)
