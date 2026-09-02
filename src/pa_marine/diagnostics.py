"""Diagnostics for the HAB nowcast: fairer baselines, permutation controls, coverage strata.

Three questions this module exists to answer, none of which the headline
`metrics.json` currently addresses:

1. **Is the climatology baseline too weak?** `metrics.climatology_probs` is a
   week-of-year mean pooled over all stations. But the model is given `latitude`
   and `longitude`, and stations differ enormously in base exceedance rate. So the
   model can beat that baseline simply by learning which farms are risky - which
   an operator already knows - without any forecasting skill at all. A
   station x week-of-year climatology closes that gap, and the difference between
   the two skill numbers tells you how much of the reported skill was station
   identity rather than timing.

2. **Would the pipeline find "skill" in noise?** Permuting labels destroys the
   feature-label relationship. If skill survives permutation, the metric or the
   baseline is broken. The graded controls below localise *which* signal the model
   is actually using.

3. **Does skill survive on fully-sampled label windows?** `y_<tax>_nowcast` ORs
   over however many station-weeks happen to be sampled in the window, and
   sampling effort is seasonal (see `hab.add_horizon_labels`). Stratifying by
   `n_obs_*` separates real signal from sampling-calendar artefact.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pa_marine.metrics import bootstrap_summary, climatology_probs, summarise

EPS = 1e-9


def _logit(p: np.ndarray | float) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1.0 - p))


def _expit(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


def _shrunk_group_rate(
    keys: np.ndarray, y: np.ndarray, prior: float, k: float
) -> dict:
    """Empirical-Bayes group rates shrunk toward `prior`.

    k is the pseudo-count: a group with k observations is weighted half-and-half
    against the prior. Guards against a station with three samples and one
    exceedance being credited with a 33% base rate.
    """
    out = {}
    df = pd.DataFrame({"k": keys, "y": y})
    g = df.groupby("k")["y"].agg(["sum", "size"])
    for key, (s, n) in zip(g.index, g.to_numpy()):
        out[key] = float((s + k * prior) / (n + k))
    return out


def station_week_climatology(
    train_station: np.ndarray,
    train_week: np.ndarray,
    train_y: np.ndarray,
    eval_station: np.ndarray,
    eval_week: np.ndarray,
    k_station: float = 20.0,
    k_week: float = 20.0,
) -> np.ndarray:
    """Station x week-of-year climatology, logit-additive with shrinkage.

    logit(p) = logit(p_global) + station effect + week-of-year effect

    Additive-in-logit rather than a raw station x week cell mean, because those
    cells are far too sparse to estimate directly (207 stations x 52 weeks against
    a training split with a few thousand positives). Unseen stations or weeks fall
    back to the global rate, so this is always defined on the evaluation split.
    """
    train_y = np.asarray(train_y, dtype=float)
    p_global = float(np.mean(train_y)) if train_y.size else 0.0
    if p_global <= 0.0 or p_global >= 1.0:
        return np.full(len(eval_station), max(p_global, EPS))

    st_rate = _shrunk_group_rate(np.asarray(train_station), train_y, p_global, k_station)
    wk_rate = _shrunk_group_rate(np.asarray(train_week), train_y, p_global, k_week)

    base = _logit(p_global)
    st_eff = {s: _logit(r) - base for s, r in st_rate.items()}
    wk_eff = {w: _logit(r) - base for w, r in wk_rate.items()}

    out = base + np.array([st_eff.get(s, 0.0) for s in eval_station]) + np.array(
        [wk_eff.get(w, 0.0) for w in eval_week]
    )
    return _expit(out)


def baseline_probs(
    kind: str,
    train: pd.DataFrame,
    evalset: pd.DataFrame,
    target: str,
    station_col: str = "location_id",
    week_col: str = "iso_week",
) -> np.ndarray:
    """Dispatch a named baseline. 'week' reproduces the current metrics.json baseline."""
    ytr = train[target].to_numpy()
    if kind == "prevalence":
        return np.full(len(evalset), float(np.mean(ytr)))
    if kind == "week":
        return climatology_probs(
            train[week_col].to_numpy(), ytr, evalset[week_col].to_numpy()
        )
    if kind == "station":
        p = float(np.mean(ytr))
        rate = _shrunk_group_rate(train[station_col].to_numpy(), ytr, p, 20.0)
        return np.array([rate.get(s, p) for s in evalset[station_col].to_numpy()])
    if kind == "station_week":
        return station_week_climatology(
            train[station_col].to_numpy(),
            train[week_col].to_numpy(),
            ytr,
            evalset[station_col].to_numpy(),
            evalset[week_col].to_numpy(),
        )
    raise ValueError(f"unknown baseline {kind!r}")


BASELINES = ("prevalence", "week", "station", "station_week")


def permute_within_groups(
    y: np.ndarray, groups: np.ndarray | None, rng: np.random.Generator
) -> np.ndarray:
    """Shuffle y within each group, preserving each group's positive count exactly."""
    y = np.asarray(y)
    if groups is None:
        return rng.permutation(y)
    out = y.copy()
    order = np.argsort(groups, kind="stable")
    sorted_g = np.asarray(groups)[order]
    starts = np.flatnonzero(np.r_[True, sorted_g[1:] != sorted_g[:-1]])
    for idx in np.split(order, starts[1:]):
        out[idx] = rng.permutation(y[idx])
    return out


def control_groups(df: pd.DataFrame, control: str, station_col="location_id", week_col="iso_week"):
    """Grouping key for each named negative control.

    global
        Destroys everything. Skill must collapse to ~0 against every baseline, or
        the metric plumbing itself is wrong.
    within_station
        Destroys timing, preserves each station's base rate. Skill surviving here
        against the *week* baseline means the model is being rewarded for knowing
        which station is risky - not for forecasting.
    within_week
        Destroys station and SST signal, preserves seasonality. Skill should
        collapse against the week baseline.
    within_station_month
        The sharpest control. Preserves both station base rate and seasonality,
        destroys only the residual within-station, within-season variation - which
        is exactly the SST/MHW signal the project claims to be using. Any skill
        left here is real dynamical signal; anything lost was structure the
        baselines should have been crediting all along.
    """
    if control == "global":
        return None
    if control == "within_station":
        return df[station_col].to_numpy()
    if control == "within_week":
        return df[week_col].to_numpy()
    if control == "within_station_month":
        month = ((df[week_col].astype(int) - 1) // 4).to_numpy()
        return pd.Series(
            [f"{s}|{m}" for s, m in zip(df[station_col].to_numpy(), month)]
        ).to_numpy()
    raise ValueError(f"unknown control {control!r}")


CONTROLS = ("global", "within_station", "within_week", "within_station_month")


def coverage_strata_metrics(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    baseline: np.ndarray,
    n_obs: np.ndarray,
    groups: np.ndarray | None = None,
    n_boot: int = 0,
    min_rows: int = 200,
) -> pd.DataFrame:
    """Metrics split by how many station-weeks were sampled inside the label window."""
    rows = []
    n_obs = np.asarray(n_obs)
    for cov in sorted(pd.unique(n_obs)):
        m = n_obs == cov
        yt = y_true[m]
        if m.sum() < min_rows or yt.min() == yt.max():
            rows.append({"n_obs": int(cov), "n": int(m.sum()), "note": "too few rows or single class"})
            continue
        g = None if groups is None else np.asarray(groups)[m]
        s = (
            bootstrap_summary(yt, y_prob[m], baseline[m], groups=g, n_boot=n_boot)
            if n_boot > 0
            else summarise(yt, y_prob[m], baseline[m])
        )
        s["n_obs"] = int(cov)
        rows.append(s)
    return pd.DataFrame(rows)
