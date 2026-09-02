"""Idea 3 - Advection graph: does an upstream bloom predict a downstream one?

This repo holds parallel, schema-harmonised phytoplankton panels for Ireland
(`habs_phyto`, 207 stations), Scotland (SMC/FSS, SIN-level, geocoded) and England & Wales
(FSA/Cefas). The hard part - three schemas, three taxonomic conventions, OSGB -> WGS84 -
is already done. They are not joined; the README says "Not merged into Irish training
yet."

Dinophysis does not respect borders. It advects with the Irish and Scottish Coastal
Currents. If a detection at an upstream site predicts one downstream at the lag the
currents imply, that is genuine warning lead time - which is the whole game, because the
current nowcast is essentially concurrent with the sample it would warn you about.

**The falsifiability requirement.** Any two coastal HAB series correlate, because both
follow the same seasonal cycle. Correlation at *some* lag is therefore worthless as
evidence. The test that means something is whether the *physically implied* lag - distance
divided by residual current speed along the connecting path - beats arbitrary lags. If
lag-3 works no better than lag-11 or lag-0, you are looking at shared seasonality, not
transport. `assess_directed_lift` builds that comparison in, and
`lag_profile` returns the whole curve so you can see whether there is a peak at the
implied lag or just a flat smear.

I expect this to return a null result more often than not, and a well-tested null is
worth publishing: "national HAB networks are not advectively predictive of each other at
operational lags" is useful to know.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pa_marine.sst import haversine_km


def transit_time_days(dist_km: float, speed_m_s: float) -> float:
    """Advective transit time. speed in m/s, distance in km."""
    if not np.isfinite(speed_m_s) or speed_m_s <= 0:
        return float("nan")
    return float(dist_km * 1000.0 / (speed_m_s * 86400.0))


def build_advection_graph(
    sites: pd.DataFrame,
    default_speed_m_s: float = 0.10,
    max_transit_days: float = 21.0,
    site_col: str = "site_id",
    currents: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Directed edges between sites with implied transit time and lag in weeks.

    `sites` needs `site_col`, `latitude`, `longitude`. If `currents` is given (columns
    `site_id`, `uo`, `vo` - mean surface velocity from Copernicus IBI), the edge is
    projected onto the actual flow direction so that only downstream pairs survive.
    Without it, edges are symmetric and `default_speed_m_s` applies - a shelf-current
    scale of ~0.1 m/s, which is ~8.6 km/day.

    Returns one row per ordered pair within `max_transit_days`.
    """
    s = sites.drop_duplicates(site_col)[[site_col, "latitude", "longitude"]].dropna()
    lat = s["latitude"].to_numpy(dtype=float)
    lon = s["longitude"].to_numpy(dtype=float)
    ids = s[site_col].to_numpy()

    cur = None
    if currents is not None:
        cur = currents.drop_duplicates(site_col).set_index(site_col)

    rows = []
    for i, src in enumerate(ids):
        d_km = haversine_km(lat[i], lon[i], lat, lon)
        for j, dst in enumerate(ids):
            if i == j:
                continue
            speed = default_speed_m_s
            if cur is not None and src in cur.index:
                u, v = float(cur.loc[src, "uo"]), float(cur.loc[src, "vo"])
                mag = float(np.hypot(u, v))
                if mag <= 0 or not np.isfinite(mag):
                    continue
                # unit vector src -> dst in local metric coords
                dy = lat[j] - lat[i]
                dx = (lon[j] - lon[i]) * np.cos(np.radians(0.5 * (lat[i] + lat[j])))
                norm = float(np.hypot(dx, dy))
                if norm <= 0:
                    continue
                # component of flow along the src->dst direction
                along = (u * dx + v * dy) / norm
                if along <= 0:
                    continue  # dst is upstream of src, not downstream
                speed = along
            t = transit_time_days(float(d_km[j]), speed)
            if not np.isfinite(t) or t > max_transit_days:
                continue
            rows.append({
                "src": src, "dst": dst, "dist_km": float(d_km[j]),
                "speed_m_s": speed, "transit_days": t,
                "implied_lag_weeks": int(np.round(t / 7.0)),
            })
    return pd.DataFrame(rows)


def _lagged_pair(
    panel: pd.DataFrame, src, dst, lag_weeks: int,
    site_col: str, week_col: str, y_col: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Align an upstream series shifted by `lag_weeks` against the downstream series."""
    a = panel[panel[site_col] == src][[week_col, y_col]].rename(columns={y_col: "y_src"})
    b = panel[panel[site_col] == dst][[week_col, y_col]].rename(columns={y_col: "y_dst"})
    a = a.copy()
    a[week_col] = pd.to_datetime(a[week_col]) + pd.Timedelta(weeks=lag_weeks)
    b = b.copy()
    b[week_col] = pd.to_datetime(b[week_col])
    m = a.merge(b, on=week_col, how="inner").dropna()
    return m["y_src"].to_numpy(), m["y_dst"].to_numpy()


def lag_profile(
    panel: pd.DataFrame, src, dst, lags=range(0, 13),
    site_col: str = "site_id", week_col: str = "week_start", y_col: str = "y",
    deseasonalise: bool = True,
) -> pd.DataFrame:
    """Association between upstream and downstream exceedance across a range of lags.

    With `deseasonalise=True` (default and strongly recommended) both series have their
    week-of-year mean removed first. Without that step every coastal pair on the same
    shelf shows a broad positive association at every lag, because both are tracking
    the same annual cycle, and the profile is uninterpretable.

    A real advective signal looks like a *peak* near the implied lag. Shared seasonality
    looks like a flat or broadly humped smear.
    """
    p = panel.copy()
    p[week_col] = pd.to_datetime(p[week_col])
    if deseasonalise:
        woy = p[week_col].dt.isocalendar().week.to_numpy()
        p["_woy"] = woy
        p[y_col] = p[y_col].astype(float) - p.groupby([site_col, "_woy"])[y_col].transform("mean")
    rows = []
    for lag in lags:
        ys, yd = _lagged_pair(p, src, dst, lag, site_col, week_col, y_col)
        if len(ys) < 30 or np.std(ys) == 0 or np.std(yd) == 0:
            rows.append({"lag_weeks": lag, "n": len(ys), "corr": np.nan})
            continue
        rows.append({
            "lag_weeks": lag, "n": len(ys),
            "corr": float(np.corrcoef(ys, yd)[0, 1]),
        })
    return pd.DataFrame(rows)


def assess_directed_lift(
    panel: pd.DataFrame,
    graph: pd.DataFrame,
    site_col: str = "site_id",
    week_col: str = "week_start",
    y_col: str = "y",
    max_lag: int = 12,
    min_pairs: int = 30,
) -> pd.DataFrame:
    """For each edge, does the implied lag beat arbitrary lags?

    Returns per-edge: correlation at the implied lag, the best correlation over all
    lags, the lag at which that best occurred, and the mean over all *other* lags.

    `lift_over_other_lags` = corr(implied) - mean(corr at other lags). This is the
    column that matters. A positive lift concentrated at the implied lag is evidence of
    transport; a lift near zero with a high absolute correlation means the pair is
    simply co-seasonal, which tells you nothing you did not already know.
    """
    rows = []
    for e in graph.itertuples(index=False):
        prof = lag_profile(
            panel, e.src, e.dst, range(0, max_lag + 1),
            site_col=site_col, week_col=week_col, y_col=y_col,
        )
        prof = prof.dropna(subset=["corr"])
        if len(prof) < 3 or prof["n"].max() < min_pairs:
            continue
        implied = int(np.clip(e.implied_lag_weeks, 0, max_lag))
        hit = prof[prof.lag_weeks == implied]
        if hit.empty:
            continue
        c_imp = float(hit["corr"].iloc[0])
        others = prof[prof.lag_weeks != implied]["corr"].to_numpy()
        best = prof.loc[prof["corr"].idxmax()]
        rows.append({
            "src": e.src, "dst": e.dst, "dist_km": e.dist_km,
            "implied_lag_weeks": implied, "corr_at_implied": c_imp,
            "corr_best": float(best["corr"]), "lag_best": int(best["lag_weeks"]),
            "mean_corr_other_lags": float(np.mean(others)) if others.size else np.nan,
            "lift_over_other_lags": c_imp - float(np.mean(others)) if others.size else np.nan,
            "n_pairs": int(hit["n"].iloc[0]),
        })
    return pd.DataFrame(rows)


def summarise_lift(tab: pd.DataFrame) -> dict:
    """Pooled verdict across edges, with the honest interpretation built in."""
    if tab.empty:
        return {"n_edges": 0, "verdict": "no edges with sufficient overlap"}
    lift = tab["lift_over_other_lags"].to_numpy(dtype=float)
    lift = lift[np.isfinite(lift)]
    agree = (tab["lag_best"] == tab["implied_lag_weeks"]).mean()
    out = {
        "n_edges": int(len(tab)),
        "median_lift": float(np.median(lift)) if lift.size else float("nan"),
        "frac_edges_positive_lift": float(np.mean(lift > 0)) if lift.size else float("nan"),
        "frac_best_lag_equals_implied": float(agree),
    }
    # A flat profile puts the best lag at the implied one only by chance: 1/(max_lag+1).
    out["verdict"] = (
        "advective signal plausible"
        if out["frac_edges_positive_lift"] > 0.65 and out["median_lift"] > 0.02
        else "no evidence of transport beyond shared seasonality"
    )
    return out
