"""Join daily MHW/SST onto station-week panel and engineer features."""
from __future__ import annotations

import numpy as np
import pandas as pd


LAGS = (0, 7, 14, 21)
ROLLS = (7, 14, 30)
BASE_COLS = ["sst", "ssta", "in_mhw", "mhw_duration", "mhw_cum_intensity"]


def _week_end_features(daily: pd.DataFrame) -> pd.DataFrame:
    """For each location_id × date, attach lags and rolling stats (past-only)."""
    parts = []
    for loc, g in daily.groupby("location_id"):
        g = g.sort_values("date").copy()
        for col in BASE_COLS:
            if col not in g.columns:
                continue
            for lag in LAGS:
                g[f"{col}_lag{lag}d"] = g[col].shift(lag)
            for w in ROLLS:
                g[f"{col}_roll{w}d"] = g[col].rolling(w, min_periods=max(3, w // 3)).mean()
        parts.append(g)
    return pd.concat(parts, ignore_index=True) if parts else daily


def join_week_panel(panel: pd.DataFrame, mhw_daily: pd.DataFrame) -> pd.DataFrame:
    daily = mhw_daily.copy()
    daily["date"] = pd.to_datetime(daily["date"], utc=True).dt.tz_localize(None).dt.normalize()
    feat = _week_end_features(daily)
    # attach features as of Sunday (end of ISO week) = week_start + 6 days
    p = panel.copy()
    p["week_start"] = pd.to_datetime(p["week_start"], utc=True).dt.tz_localize(None).dt.normalize()
    p["feat_date"] = p["week_start"] + pd.Timedelta(days=6)
    extra = [c for c in feat.columns if (c.endswith("d") or c in BASE_COLS + ["clim", "thresh", "anom"])]
    keep = []
    for c in ["location_id", "date"] + extra:
        if c in feat.columns and c not in keep:
            keep.append(c)
    merged = p.merge(
        feat[keep].rename(columns={"date": "feat_date"}),
        on=["location_id", "feat_date"],
        how="left",
    )
    # week-of-year Fourier + lon/lat
    woy = merged["iso_week"].astype(float)
    merged["woy_sin"] = np.sin(2 * np.pi * woy / 53.0)
    merged["woy_cos"] = np.cos(2 * np.pi * woy / 53.0)
    return merged


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Numeric model features: BASE_COLS + lag/roll engineered cols + seasonality/geo.

    Intentionally excludes identifiers such as location_id (which ends with 'd').
    """
    extra = ["woy_sin", "woy_cos", "latitude", "longitude"]
    skip = {"location_id", "iso_year", "iso_week", "n_samples", "feat_date"}
    cols = []
    for c in df.columns:
        if c in skip:
            continue
        if any(c.startswith(b) for b in BASE_COLS):
            cols.append(c)
        elif c.endswith(("lag0d", "lag3d", "lag7d", "lag14d", "lag21d")) or c.endswith(
            ("roll7d", "roll14d", "roll30d")
        ):
            cols.append(c)
    cols += [c for c in extra if c in df.columns]
    seen = set()
    out = []
    for c in cols:
        if c not in seen and c not in skip and pd.api.types.is_numeric_dtype(df[c]):
            seen.add(c)
            out.append(c)
    return out
