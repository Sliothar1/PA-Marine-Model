"""Idea 1 - Virtual Inshore Thermometer: downscale offshore SST to the water a farm sits in.

Motivation, from the code review (REVIEW.md items 8-9): the Irish pipeline snaps each
station to whichever 0.25 deg OISST pixel contains it, with no land mask. Inshore sites
land on land pixels and return NaN SST for the whole record - the repo already documents
Rosmuc that way. Killary Harbour is a 16 km fjord roughly 300 m wide; no 0.25 deg product
resolves it.

Evidence the gap is real, measured on `data/processed/june2023_case_study_daily.csv`
(123 days of Mace Head in-situ water temperature, May-Aug 2023):

    offshore CRW MHW fraction  vs inshore water temp:  r = +0.03
    Met Eireann min air temp   vs inshore water temp:  r = +0.71
    in-situ salinity           vs inshore water temp:  r = +0.63

The offshore heatwave product carries almost no information about the water the shellfish
are actually in. Land-station night-minimum air temperature and local salinity carry a lot.

Approach: predict inshore water temperature from variables measured everywhere (offshore
SST, coastal met, river discharge, solar geometry, tide), trained against the handful of
sites where in-situ truth exists (`sbe37_macehead`, `compass_mace_head`,
`sentinel_lehanagh`, `smartbay_obs_ctd_sbe16`, `spiddal_obs_ctd`).

The honest validation is leave-one-SITE-out, not leave-one-day-out: adjacent days are
strongly autocorrelated, so a random day split would report near-perfect skill while
telling you nothing about a new farm. See `loso_validate`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Predictor groups. Absent columns are skipped, so this degrades gracefully when a
# site lacks river gauges or an offshore pixel.
OFFSHORE = ["offshore_sst", "offshore_ssta"]
MET = ["air_temp_min", "air_temp_max", "wind_speed", "solar_rad", "rain"]
FRESHWATER = ["river_q_local", "river_q_regional"]
DERIVED_SOLAR = ["day_length_h", "solar_decl_deg", "clear_sky_index"]
LAGS_DAYS = (1, 3, 7)
ROLLS_DAYS = (3, 7, 30)


def solar_geometry(dates: pd.Series, latitude: float) -> pd.DataFrame:
    """Day length and solar declination - free predictors, no data needed.

    Thermal inertia in a shallow embayment tracks accumulated insolation, and day
    length is a cleaner index of that than a single day's measured radiation (which is
    dominated by cloud). Computed from the standard solar-position approximation.
    """
    d = pd.to_datetime(pd.Series(list(dates)))
    doy = d.dt.dayofyear.to_numpy(dtype=float)
    decl = 23.45 * np.sin(np.radians(360.0 * (284.0 + doy) / 365.0))
    phi = np.radians(latitude)
    cos_omega = -np.tan(phi) * np.tan(np.radians(decl))
    cos_omega = np.clip(cos_omega, -1.0, 1.0)
    day_length = 2.0 * np.degrees(np.arccos(cos_omega)) / 15.0
    return pd.DataFrame(
        {"day_length_h": day_length, "solar_decl_deg": decl}, index=d.index
    )


def add_lags_and_rolls(
    df: pd.DataFrame, cols: list[str], lags=LAGS_DAYS, rolls=ROLLS_DAYS
) -> pd.DataFrame:
    """Past-only lags and rolling means, built in one concat to avoid refragmenting."""
    present = [c for c in cols if c in df.columns]
    if not present:
        return df
    out = df.sort_values("date").copy()
    extra = {}
    for c in present:
        s = out[c]
        for lag in lags:
            extra[f"{c}_lag{lag}d"] = s.shift(lag)
        for w in rolls:
            extra[f"{c}_roll{w}d"] = s.rolling(w, min_periods=max(2, w // 3)).mean()
    return pd.concat([out, pd.DataFrame(extra, index=out.index)], axis=1)


def build_inshore_features(
    daily: pd.DataFrame, latitude: float | None = None, add_solar: bool = True
) -> tuple[pd.DataFrame, list[str]]:
    """Assemble the predictor matrix from a daily frame.

    `daily` needs a `date` column plus any subset of OFFSHORE/MET/FRESHWATER columns.
    Returns (frame, feature_names). Nothing is imputed here - the estimators handle
    missingness, and silently filling gaps in a temperature series is how you end up
    with a model that looks good and means nothing.
    """
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    if add_solar and latitude is not None:
        df = pd.concat([df, solar_geometry(df["date"], latitude)], axis=1)
        if "solar_rad" in df.columns:
            # crude clear-sky index: measured radiation relative to the seasonal envelope
            env = df.groupby(df["date"].dt.dayofyear)["solar_rad"].transform("max")
            df["clear_sky_index"] = df["solar_rad"] / env.replace(0, np.nan)

    base = [c for c in OFFSHORE + MET + FRESHWATER if c in df.columns]
    df = add_lags_and_rolls(df, base)

    feats = []
    for group in (OFFSHORE, MET, FRESHWATER, DERIVED_SOLAR):
        feats += [c for c in group if c in df.columns]
    feats += [
        c
        for c in df.columns
        if any(c.startswith(b + "_lag") or c.startswith(b + "_roll") for b in base)
    ]
    # seasonality, so the model is not forced to learn the annual cycle from scratch
    doy = df["date"].dt.dayofyear.to_numpy(dtype=float)
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    feats += ["doy_sin", "doy_cos"]

    seen, ordered = set(), []
    for c in feats:
        if c not in seen and c in df.columns and pd.api.types.is_numeric_dtype(df[c]):
            seen.add(c)
            ordered.append(c)
    return df, ordered


def make_inshore_estimator(quantile: float | None = None):
    """Gradient-boosted trees; `quantile` returns a quantile regressor for intervals.

    Trees rather than a linear model because the offshore-to-inshore relationship is
    genuinely non-linear: wind mixing only matters above a threshold, and freshwater
    stratification flips the sign of the solar heating term.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor

    if quantile is not None:
        return HistGradientBoostingRegressor(
            loss="quantile", quantile=quantile, max_depth=5,
            learning_rate=0.06, max_iter=250, random_state=42,
        )
    return HistGradientBoostingRegressor(
        max_depth=5, learning_rate=0.06, max_iter=250, random_state=42
    )


def fit_predict_inshore(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feats: list[str],
    target: str = "inshore_temp_c",
    with_interval: bool = False,
) -> pd.DataFrame:
    """Fit on train, predict test. Optionally add a 10-90% predictive interval."""
    tr = train.dropna(subset=[target])
    if tr.empty:
        raise ValueError(f"no finite {target!r} in the training frame")
    est = make_inshore_estimator()
    est.fit(tr[feats], tr[target])
    out = pd.DataFrame({"pred": est.predict(test[feats])}, index=test.index)
    if with_interval:
        # Known limitation: on the 92-day real Mace Head demo the nominal 10-90%
        # interval achieved only ~48% coverage. Quantile GBMs need far more data than
        # that to be calibrated. Treat the interval as indicative until it has been
        # checked against a multi-year record, and prefer a conformal wrapper (split
        # the training set, take empirical residual quantiles) if coverage matters.
        for q, name in ((0.1, "pred_p10"), (0.9, "pred_p90")):
            qe = make_inshore_estimator(quantile=q)
            qe.fit(tr[feats], tr[target])
            out[name] = qe.predict(test[feats])
    return out


def skill_vs_offshore(
    truth: np.ndarray, pred: np.ndarray, offshore: np.ndarray | None = None
) -> dict:
    """RMSE/MAE/bias, plus the reduction in RMSE against using offshore SST directly.

    `rmse_skill_vs_offshore` is the number that matters: it says whether downscaling
    beats the status quo of handing the model an offshore pixel. Below zero means the
    downscaler is worse than doing nothing, which is worth knowing plainly.
    """
    truth = np.asarray(truth, dtype=float)
    pred = np.asarray(pred, dtype=float)
    m = np.isfinite(truth) & np.isfinite(pred)
    if m.sum() < 3:
        return {"n": int(m.sum())}
    err = pred[m] - truth[m]
    out = {
        "n": int(m.sum()),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mae": float(np.mean(np.abs(err))),
        "bias": float(np.mean(err)),
        "corr": float(np.corrcoef(truth[m], pred[m])[0, 1]) if m.sum() > 2 else float("nan"),
    }
    if offshore is not None:
        off = np.asarray(offshore, dtype=float)
        mo = m & np.isfinite(off)
        if mo.sum() >= 3:
            base_rmse = float(np.sqrt(np.mean((off[mo] - truth[mo]) ** 2)))
            out["rmse_offshore"] = base_rmse
            out["rmse_skill_vs_offshore"] = (
                float(1.0 - out["rmse"] / base_rmse) if base_rmse > 0 else float("nan")
            )
    return out


def loso_validate(
    daily: pd.DataFrame,
    feats: list[str],
    site_col: str = "site",
    target: str = "inshore_temp_c",
    offshore_col: str = "offshore_sst",
) -> pd.DataFrame:
    """Leave-one-SITE-out validation - the only honest test for a new farm.

    A random day-level split leaks badly: inshore temperature is autocorrelated over
    weeks, so neighbouring days land on both sides of the split and the model reports
    skill it does not have. Holding out whole sites asks the operational question,
    which is whether this works at a location with no sensor.
    """
    rows = []
    for site in pd.unique(daily[site_col]):
        te = daily[daily[site_col] == site]
        tr = daily[daily[site_col] != site]
        if tr.dropna(subset=[target]).empty or te.dropna(subset=[target]).empty:
            rows.append({site_col: site, "n": len(te), "note": "no overlapping truth"})
            continue
        pred = fit_predict_inshore(tr, te, feats, target=target)["pred"].to_numpy()
        off = te[offshore_col].to_numpy() if offshore_col in te.columns else None
        s = skill_vs_offshore(te[target].to_numpy(), pred, off)
        s[site_col] = site
        rows.append(s)
    return pd.DataFrame(rows)
