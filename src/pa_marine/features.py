"""Join daily MHW/SST (+ optional IBI physics) onto station-week panel and engineer features."""
from __future__ import annotations

import numpy as np
import pandas as pd


LAGS = (0, 7, 14, 21)
ROLLS = (7, 14, 30)

# Core SST / Hobday MHW (binary + continuous intensity)
BASE_COLS = [
    "sst",
    "ssta",
    "in_mhw",
    "mhw_duration",
    "mhw_cum_intensity",
    "mhw_intensity",
    "mhw_max_intensity",
    "mhw_i_ratio",
    "mhw_category",
    "days_since_mhw",
    "ssta_pctile",
]

# IBI physics / light (joined into the same daily frame when available)
PHYSICS_COLS = [
    "mlotst",
    "rsntds",
    "kd",
    "zeu",
    "so",
    "uo",
    "vo",
    "current_speed",
]

WIND_COLS = [
    "wind_u",
    "wind_v",
    "wind_speed",
    "wind_alongshore",
    "wind_crossshore",
    "msl",
]

FEATURE_PREFIXES = tuple(BASE_COLS + PHYSICS_COLS + WIND_COLS)


def _week_end_features(daily: pd.DataFrame) -> pd.DataFrame:
    """For each location_id × date, attach lags and rolling stats (past-only)."""
    parts = []
    cols = [c for c in FEATURE_PREFIXES if c in daily.columns]
    for loc, g in daily.groupby("location_id"):
        g = g.sort_values("date").copy()
        extra = {}
        for col in cols:
            s = g[col]
            for lag in LAGS:
                extra[f"{col}_lag{lag}d"] = s.shift(lag)
            for w in ROLLS:
                extra[f"{col}_roll{w}d"] = s.rolling(w, min_periods=max(3, w // 3)).mean()
        if extra:
            g = pd.concat([g, pd.DataFrame(extra, index=g.index)], axis=1)
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
    base_present = [c for c in FEATURE_PREFIXES if c in feat.columns]
    extra = [
        c
        for c in feat.columns
        if (c.endswith("d") or c in base_present + ["clim", "thresh", "anom"])
    ]
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
    """Numeric model features: BASE/PHYSICS + lag/roll engineered cols + seasonality/geo.

    Intentionally excludes identifiers such as location_id (which ends with 'd').
    """
    extra = ["woy_sin", "woy_cos", "latitude", "longitude"]
    skip = {"location_id", "iso_year", "iso_week", "n_samples", "feat_date"}
    cols = []
    for c in df.columns:
        if c in skip:
            continue
        if any(c == b or c.startswith(b + "_") for b in FEATURE_PREFIXES):
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


# Strong OISST feature set from 2026-09-01 Dinophysis ablation (drop_weak winner).
STRONG_OISST = {
    "woy_sin",
    "woy_cos",
    "latitude",
    "longitude",
    "sst",
    "sst_lag0d",
    "sst_lag21d",
    "sst_roll7d",
    "sst_roll30d",
}

# Continuous MHW intensity features (richer than in_mhw binary).
RICH_MHW = {
    "mhw_intensity",
    "mhw_intensity_lag0d",
    "mhw_intensity_lag7d",
    "mhw_intensity_roll7d",
    "mhw_intensity_roll14d",
    "mhw_intensity_roll30d",
    "mhw_max_intensity",
    "mhw_max_intensity_lag0d",
    "mhw_max_intensity_roll14d",
    "mhw_max_intensity_roll30d",
    "mhw_cum_intensity",
    "mhw_cum_intensity_roll14d",
    "mhw_cum_intensity_roll30d",
    "mhw_i_ratio",
    "mhw_i_ratio_lag0d",
    "mhw_i_ratio_roll14d",
    "mhw_i_ratio_roll30d",
    "mhw_category",
    "mhw_category_roll14d",
    "mhw_category_roll30d",
    "days_since_mhw",
    "days_since_mhw_lag0d",
    "ssta_pctile",
    "ssta_pctile_lag0d",
    "ssta_pctile_roll14d",
    "ssta_pctile_roll30d",
    "ssta",
    "ssta_roll14d",
    "ssta_roll30d",
}

# Priority IBI physics / light
# Compact continuous intensity (avoid diluting strong set with too many MHW cols)
RICH_MHW_TOP3 = {
    "days_since_mhw",
    "mhw_i_ratio",
    "mhw_intensity_roll30d",
}

RICH_MHW_LEAN = {
    "mhw_intensity_roll30d",
    "mhw_max_intensity_roll30d",
    "mhw_cum_intensity_roll30d",
    "mhw_i_ratio",
    "mhw_i_ratio_roll30d",
    "mhw_category_roll30d",
    "days_since_mhw",
    "ssta_pctile",
    "ssta_pctile_roll30d",
}

IBI_LIGHT_MLD = {
    "mlotst",
    "mlotst_lag0d",
    "mlotst_lag7d",
    "mlotst_roll7d",
    "mlotst_roll14d",
    "mlotst_roll30d",
    "rsntds",
    "rsntds_lag0d",
    "rsntds_lag7d",
    "rsntds_roll7d",
    "rsntds_roll14d",
    "rsntds_roll30d",
    "kd",
    "kd_lag0d",
    "kd_roll7d",
    "kd_roll14d",
    "kd_roll30d",
    "zeu",
    "zeu_lag0d",
    "zeu_roll7d",
    "zeu_roll14d",
    "zeu_roll30d",
}

IBI_SSS_CUR = {
    "so",
    "so_lag0d",
    "so_roll14d",
    "so_roll30d",
    "uo",
    "uo_lag0d",
    "uo_roll14d",
    "vo",
    "vo_lag0d",
    "vo_roll14d",
    "current_speed",
    "current_speed_lag0d",
    "current_speed_roll7d",
    "current_speed_roll14d",
    "current_speed_roll30d",
}


def select_feature_mode(df: pd.DataFrame, mode: str) -> list[str]:
    """Select a named feature subset present in df."""
    all_feats = feature_columns(df)
    mode = mode.lower()
    if mode in {"all", "full"}:
        return all_feats
    if mode == "strong":
        return [f for f in all_feats if f in STRONG_OISST]
    if mode == "sst":
        must = {"woy_sin", "woy_cos", "latitude", "longitude"}
        return [f for f in all_feats if f.startswith("sst") or f.startswith("ssta") or f in must]
    if mode == "strong_rich_mhw":
        keep = STRONG_OISST | RICH_MHW
        return [f for f in all_feats if f in keep]
    if mode == "strong_rich_mhw_lean":
        keep = STRONG_OISST | RICH_MHW_LEAN
        return [f for f in all_feats if f in keep]
    if mode == "strong_rich_mhw_top3":
        keep = STRONG_OISST | RICH_MHW_TOP3
        return [f for f in all_feats if f in keep]
    if mode == "strong_ibi":
        keep = STRONG_OISST | IBI_LIGHT_MLD
        return [f for f in all_feats if f in keep]
    if mode == "strong_rich_mhw_ibi":
        keep = STRONG_OISST | RICH_MHW | IBI_LIGHT_MLD
        return [f for f in all_feats if f in keep]
    if mode == "strong_rich_mhw_lean_ibi":
        keep = STRONG_OISST | RICH_MHW_LEAN | IBI_LIGHT_MLD
        return [f for f in all_feats if f in keep]
    if mode == "strong_rich_mhw_ibi_full":
        keep = STRONG_OISST | RICH_MHW | IBI_LIGHT_MLD | IBI_SSS_CUR
        return [f for f in all_feats if f in keep]
    raise ValueError(f"Unknown feature mode: {mode}")
