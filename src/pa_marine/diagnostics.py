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


def smoothed_week_rate(
    train_week: np.ndarray, train_y: np.ndarray, eval_week: np.ndarray, window: int = 5
) -> np.ndarray:
    """Week-of-year climatology with a circular moving average over +/- window//2 weeks.

    The plain `week` baseline estimates 52 independent bins. The model, by contrast,
    represents seasonality with a smooth `woy_sin`/`woy_cos` Fourier basis - so it can
    beat the bin-wise baseline simply by being smoother, with no forecasting skill at
    all. Measured on synthetic panels with zero dynamical signal, that alone put ~71%
    of leave-one-station-out folds above the unsmoothed baseline. Smoothing the
    baseline removes that free win and makes the comparison about timing, not about
    estimator variance.
    """
    train_week = np.asarray(train_week).astype(int)
    train_y = np.asarray(train_y, dtype=float)
    global_p = float(np.mean(train_y)) if train_y.size else 0.0
    n_weeks = 53
    sums = np.zeros(n_weeks + 1)
    cnts = np.zeros(n_weeks + 1)
    np.add.at(sums, np.clip(train_week, 1, n_weeks), train_y)
    np.add.at(cnts, np.clip(train_week, 1, n_weeks), 1.0)
    half = max(window // 2, 0)
    rate = np.full(n_weeks + 1, global_p)
    for w in range(1, n_weeks + 1):
        idx = ((np.arange(w - half, w + half + 1) - 1) % n_weeks) + 1
        c = cnts[idx].sum()
        rate[w] = sums[idx].sum() / c if c > 0 else global_p
    ew = np.asarray(eval_week).astype(int)
    # ISO weeks are 1..53; anything outside that is bad data, so fall back to the
    # global rate rather than silently clamping it onto week 1 or 53.
    valid = (ew >= 1) & (ew <= n_weeks)
    out = np.full(len(ew), global_p, dtype=float)
    out[valid] = rate[ew[valid]]
    return out


def station_week_climatology(
    train_station: np.ndarray,
    train_week: np.ndarray,
    train_y: np.ndarray,
    eval_station: np.ndarray,
    eval_week: np.ndarray,
    k_station: float = 20.0,
    k_week: float = 20.0,
    week_window: int = 5,
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
    base = _logit(p_global)
    st_eff = {s: _logit(r) - base for s, r in st_rate.items()}
    # smoothed seasonal term, so the baseline is not penalised for bin-wise noise
    wk_eff = _logit(smoothed_week_rate(train_week, train_y, eval_week, window=week_window)) - base

    out = base + np.array([st_eff.get(s, 0.0) for s in eval_station]) + wk_eff
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
    if kind == "week_smooth":
        return smoothed_week_rate(
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


BASELINES = ("prevalence", "week", "week_smooth", "station", "station_week")


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


def grouped_cv_metrics(
    df: pd.DataFrame,
    feats: list[str],
    target: str,
    fit_predict_fn,
    group_col: str = "location_id",
    baseline: str = "station_week",
    n_folds: int | None = None,
    seed: int = 42,
    min_test_pos: int = 5,
) -> pd.DataFrame:
    """Grouped hold-out CV: train on all groups but one, predict the held-out group.

    The fixed temporal split answers "can we forecast next fortnight at a station we
    already monitor?". It does not answer "can we forecast at a station we have never
    sampled?" - which is the question a new farm site actually poses. Because the
    model is handed `latitude`/`longitude` and the project's own feature study found
    those among the dominant features, in-sample station identity may be carrying much
    of the apparent skill. Holding out whole stations removes it.

    `group_col="location_id"` gives leave-one-station-out (spatial transfer);
    `group_col="iso_year"` gives leave-one-year-out (temporal transfer).

    Note the baseline is refitted per fold on that fold's training groups only, so a
    held-out station gets no station effect - it falls back to the week-of-year
    component, which is the honest situation for an unmonitored site.

    Two cautions, both measured rather than assumed:

    1. A leave-one-station-out skill number is NOT comparable to the pooled
       temporal-split number. The held-out baseline has no station effect, so it is
       weaker, and LOSO skill can read *higher* even though the task is harder.

    2. **The null is not zero.** On synthetic panels with no dynamical signal at all,
       LOSO still put 86-93% of folds above the baseline with a median skill of
       0.03-0.07. The model represents seasonality with a smooth Fourier basis while
       the baseline estimates 52 independent week bins, so it wins on estimator
       variance alone. Using `baseline="week_smooth"` or `"station_week"` halves that
       but does not remove it.

    So do not read a positive LOSO median as evidence of skill on its own. Establish
    the null for *your* panel by running this function on permuted labels
    (`permute_within_groups` with `control_groups(df, "within_station_month")`) and
    compare. `scripts/run_diagnostics.py --mode grouped_cv` reports the observed
    value; the permutation mode gives you the reference level.
    """
    groups = df[group_col].to_numpy()
    uniq = pd.unique(groups)
    rng = np.random.default_rng(seed)
    if n_folds is not None and n_folds < len(uniq):
        uniq = rng.choice(uniq, size=n_folds, replace=False)

    rows = []
    for g in uniq:
        te = df[groups == g]
        tr = df[groups != g]
        y_te = te[target].astype(int).to_numpy()
        y_tr = tr[target].astype(int).to_numpy()
        if y_te.sum() < min_test_pos or y_tr.min() == y_tr.max():
            rows.append({group_col: g, "n": len(te), "n_pos": int(y_te.sum()),
                         "note": "too few held-out positives"})
            continue
        p = fit_predict_fn(tr[feats], y_tr, te[feats])
        bp = baseline_probs(baseline, tr.assign(**{target: y_tr}), te, target)
        s = summarise(y_te, p, bp)
        s[group_col] = g
        s["n_pos"] = int(y_te.sum())
        rows.append(s)
    return pd.DataFrame(rows)


def summarise_grouped_cv(tab: pd.DataFrame, group_col: str = "location_id") -> dict:
    """Pooled summary of a grouped-CV table: median skill and the share of folds > 0."""
    ok = tab[tab.get("note").isna()] if "note" in tab.columns else tab
    if ok.empty or "pr_auc_skill" not in ok.columns:
        return {"n_folds_scored": 0}
    v = ok["pr_auc_skill"].to_numpy(dtype=float)
    v = v[np.isfinite(v)]
    return {
        "n_folds_total": int(len(tab)),
        "n_folds_scored": int(len(v)),
        "pr_auc_skill_median": float(np.median(v)) if v.size else float("nan"),
        "pr_auc_skill_mean": float(v.mean()) if v.size else float("nan"),
        "pr_auc_skill_q25": float(np.percentile(v, 25)) if v.size else float("nan"),
        "pr_auc_skill_q75": float(np.percentile(v, 75)) if v.size else float("nan"),
        "frac_folds_positive": float(np.mean(v > 0)) if v.size else float("nan"),
    }
