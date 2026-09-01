"""Hobday et al. (2016) marine heatwaves (self-contained).

Definition used here:
- Seasonal threshold: 90th percentile of SST by day-of-year, using an 11-day
  window centred on the DOY (climatology years = full series unless masked).
- Event: >= 5 consecutive days with SST > threshold.
- Gaps of <= 2 days below threshold are merged into one event.
- Intensity on a day is SST minus the seasonal *mean* climatology (Hobday 2016).
- Duration = event length in days; cumulative intensity = sum of daily intensities
  while in an event (0 if not in MHW).

Richer continuous intensity (added for Dinophysis ablations):
- mhw_intensity: daily intensity while in event (else 0)
- mhw_max_intensity: running max intensity within the current event
- mhw_i_ratio: (SST - clim) / (thresh - clim); Hobday category scale
- mhw_category: 0 outside event; I–IV while in event (Hobday 2018)
- days_since_mhw: 0 in event; days since last MHW day otherwise
- ssta_pctile: empirical percentile of today's SST among DOY-window climatology samples
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _doy_climatology(sst: np.ndarray, doy: np.ndarray, window: int, q: float | None) -> np.ndarray:
    """Return per-day climatology aligned to `doy` (1–366). q=None -> mean else percentile."""
    n = len(sst)
    out = np.full(n, np.nan)
    half = window // 2
    for d in range(1, 367):
        # circular day-of-year window
        days = np.arange(d - half, d + half + 1)
        days = ((days - 1) % 366) + 1
        mask = np.isin(doy, days) & np.isfinite(sst)
        if not np.any(mask):
            continue
        vals = sst[mask]
        clim = float(np.nanmean(vals) if q is None else np.nanpercentile(vals, q))
        out[doy == d] = clim
    return out


def _doy_sst_percentile(sst: np.ndarray, doy: np.ndarray, window: int) -> np.ndarray:
    """Empirical percentile (0–100) of each day's SST vs DOY-window climatology pool."""
    n = len(sst)
    out = np.full(n, np.nan)
    half = window // 2
    pools: dict[int, np.ndarray] = {}
    for d in range(1, 367):
        days = np.arange(d - half, d + half + 1)
        days = ((days - 1) % 366) + 1
        mask = np.isin(doy, days) & np.isfinite(sst)
        pools[d] = sst[mask] if np.any(mask) else np.array([], dtype=float)
    for i in range(n):
        if not np.isfinite(sst[i]):
            continue
        pool = pools[int(doy[i])]
        if pool.size == 0:
            continue
        out[i] = 100.0 * float(np.mean(pool <= sst[i]))
    return out


def detect_mhw(
    dates: pd.Series,
    sst: pd.Series,
    min_duration: int = 5,
    max_gap: int = 2,
    percentile: float = 90.0,
    doy_window: int = 11,
) -> pd.DataFrame:
    """Return daily frame with sst, clim, thresh, ssta, in_mhw, duration, cum_intensity + rich intensity."""
    d = pd.to_datetime(pd.Series(list(dates)), utc=True)
    d = d.dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    df = pd.DataFrame({"date": d, "sst": pd.to_numeric(pd.Series(list(sst)), errors="coerce")})
    df = df.sort_values("date").drop_duplicates("date")
    full = pd.DataFrame({"date": pd.date_range(df["date"].min(), df["date"].max(), freq="D")})
    df = full.merge(df, on="date", how="left")
    doy = df["date"].dt.dayofyear.to_numpy()
    sst_a = df["sst"].to_numpy(dtype=float)
    clim = _doy_climatology(sst_a, doy, doy_window, q=None)
    thresh = _doy_climatology(sst_a, doy, doy_window, q=percentile)
    ssta = sst_a - clim
    above = (sst_a > thresh) & np.isfinite(sst_a) & np.isfinite(thresh)

    # merge gaps <= max_gap
    n = len(df)
    in_event = above.copy()
    i = 0
    while i < n:
        if not in_event[i]:
            i += 1
            continue
        j = i
        while j < n and in_event[j]:
            j += 1
        # look ahead for gap then resume
        k = j
        while k < n and (not in_event[k]) and (k - j) <= max_gap:
            k += 1
        if k < n and in_event[k] and (k - j) <= max_gap and (k - j) > 0:
            in_event[j:k] = True
            i = k
        else:
            i = j

    # drop events shorter than min_duration
    duration = np.zeros(n, dtype=float)
    cum_int = np.zeros(n, dtype=float)
    in_mhw = np.zeros(n, dtype=int)
    intensity = np.zeros(n, dtype=float)
    max_int = np.zeros(n, dtype=float)
    category = np.zeros(n, dtype=float)
    i = 0
    while i < n:
        if not in_event[i]:
            i += 1
            continue
        j = i
        while j < n and in_event[j]:
            j += 1
        length = j - i
        if length >= min_duration:
            intens_slice = np.where(np.isfinite(ssta[i:j]), ssta[i:j], 0.0)
            in_mhw[i:j] = 1
            duration[i:j] = np.arange(1, length + 1)
            running = np.nancumsum(intens_slice)
            cum_int[i:j] = running
            intensity[i:j] = intens_slice
            # running max within event
            run_max = np.maximum.accumulate(intens_slice)
            max_int[i:j] = run_max
            # Hobday 2018 categories from i_ratio vs (thresh - clim)
            delta = thresh[i:j] - clim[i:j]
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = np.where((np.isfinite(delta) & (delta > 1e-6)), intens_slice / delta, np.nan)
            cat = np.zeros(length, dtype=float)
            cat[(ratio >= 1) & (ratio < 2)] = 1
            cat[(ratio >= 2) & (ratio < 3)] = 2
            cat[(ratio >= 3) & (ratio < 4)] = 3
            cat[ratio >= 4] = 4
            # if somehow in event but ratio < 1 (gap fill), treat as cat I
            cat[(in_mhw[i:j] == 1) & (cat == 0)] = 1
            category[i:j] = cat
        i = j

    # days since last MHW day (0 while in event)
    days_since = np.full(n, np.nan)
    last = -10_000
    for t in range(n):
        if in_mhw[t] == 1:
            days_since[t] = 0.0
            last = t
        elif last >= 0:
            days_since[t] = float(t - last)

    delta_full = thresh - clim
    with np.errstate(divide="ignore", invalid="ignore"):
        i_ratio = np.where(
            np.isfinite(ssta) & np.isfinite(delta_full) & (delta_full > 1e-6),
            ssta / delta_full,
            np.nan,
        )

    ssta_pctile = _doy_sst_percentile(sst_a, doy, doy_window)

    df["clim"] = clim
    df["thresh"] = thresh
    df["ssta"] = ssta
    df["in_mhw"] = in_mhw
    df["mhw_duration"] = duration
    df["mhw_cum_intensity"] = cum_int
    df["mhw_intensity"] = intensity
    df["mhw_max_intensity"] = max_int
    df["mhw_i_ratio"] = i_ratio
    df["mhw_category"] = category
    df["days_since_mhw"] = days_since
    df["ssta_pctile"] = ssta_pctile
    return df


def mhw_for_stations(sst_daily: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """sst_daily columns: location_id, date, sst (and optional anom)."""
    spec = cfg["mhw"]
    parts = []
    for loc, g in sst_daily.groupby("location_id"):
        m = detect_mhw(
            g["date"],
            g["sst"],
            min_duration=spec["min_duration_days"],
            max_gap=spec["max_gap_days"],
            percentile=spec["percentile"],
            doy_window=spec["climatology_doy_window"],
        )
        m["location_id"] = loc
        parts.append(m)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
