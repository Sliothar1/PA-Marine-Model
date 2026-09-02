"""Idea 2 - Sampling Scheduler: turn the label confound into an allocation tool.

Motivation, from the code review (REVIEW.md item 3): `y_<tax>_nowcast` is an OR over
whichever station-weeks happen to be sampled inside a 14-day window. Measured label
prevalence ran 0.070 / 0.326 / 0.608 for windows containing 1 / 2 / 3 samples, while the
underlying weekly bloom rate rose only from 0.070 to 0.271. Most of that gradient is the
OR, not the ocean. And sampling effort is seasonal, so it is entangled with the
week-of-year features the model leans on hardest.

That is a problem for inference. It is also an opportunity: the monitoring programme
already makes a weekly allocation decision under a fixed boat-and-lab budget, and nothing
in the pipeline helps with it.

This module inverts the model. Instead of "what is the risk at station X", it answers
"where is the next sample worth most".

**Two objectives, and they disagree.** My first version scored only "decision
uncertainty" - weight peaking where risk sits near the action threshold, on the reasoning
that a sample there can change the decision while a station at p=0.98 tells you nothing
new. Backtesting killed it: detection rate *fell* from 28.6% to 25.4% against a
risk-blind status quo. The diagnosis is that exceedances concentrate at p -> 1 (a
calibrated p=0.95 bin has a 95% exceedance rate), so weighting the middle deliberately
skips the stations most likely to be in exceedance.

The error was assuming the action can be taken on the model alone. In a regulatory
setting it cannot: a closure requires a confirmatory *measurement*. So sampling a p=0.98
station has high action value precisely because it produces the legal evidence needed to
close. Hence `objective`:

  "detection" (default) - weight on p itself. Maximises exceedances caught and evidence
                          generated. This is the regulator's objective.
  "decision"            - weight on nearness to threshold. Maximises information gain
                          about ambiguous cases. Appropriate for a research campaign
                          deciding where the model is weakest, not for routine control.
  "balanced"            - both, for a programme doing surveillance and model improvement
                          at once.

Terms shared across objectives:

  consequence           - production tonnage, or the size of the parent closure area from
                          `habs_status`. Being wrong about a big area costs more.
  staleness             - days since last sample, so persistent blind spots surface.

Crucially this is backtestable on data already held: the 23-year `habs_phyto` record
contains the full sampling history, so `backtest_time_to_detection` can ask whether an
alternative schedule would have caught known exceedance events earlier than the schedule
actually used.

**Framing that matters operationally:** this must never be read as "sample less".
Statutory minimum sampling exists for good reason. `allocate` takes a `mandatory` set that
is always scheduled first, and the optimiser only ever distributes the *marginal* samples
above that floor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def decision_uncertainty(prob: np.ndarray, threshold: float = 0.5, sharpness: float = 8.0) -> np.ndarray:
    """Weight peaking at the action threshold, falling away from it.

    Not the same as variance. A station at p=0.02 and one at p=0.98 are both *certain*,
    but so is a station at p=0.5 under a variance measure that ignores the decision.
    What matters for allocation is whether new information could flip the action, which
    is a function of distance from the threshold.
    """
    p = np.clip(np.asarray(prob, dtype=float), 0.0, 1.0)
    return np.exp(-sharpness * np.abs(p - threshold))


OBJECTIVES = ("detection", "decision", "balanced")


def sample_value(
    prob: np.ndarray,
    consequence: np.ndarray | None = None,
    days_since_sample: np.ndarray | None = None,
    threshold: float = 0.5,
    staleness_halflife_days: float = 14.0,
    w_staleness: float = 0.5,
    objective: str = "detection",
) -> np.ndarray:
    """Expected value of taking one more sample at each candidate station-week.

    value = consequence * (risk_term + w_staleness * staleness)

    where risk_term is p ("detection"), decision_uncertainty ("decision"), or their
    mean ("balanced"). See the module docstring for why the default is "detection" -
    the "decision" objective measurably *reduced* detection rate in backtest.

    Staleness saturates rather than growing without bound, so a site unsampled for two
    years does not permanently monopolise the schedule.
    """
    if objective not in OBJECTIVES:
        raise ValueError(f"objective must be one of {OBJECTIVES}, got {objective!r}")
    p = np.clip(np.asarray(prob, dtype=float), 0.0, 1.0)
    u = decision_uncertainty(p, threshold=threshold)
    if objective == "detection":
        risk = p
    elif objective == "decision":
        risk = u
    else:
        risk = 0.5 * (p + u)
    n = len(risk)
    cons = np.ones(n) if consequence is None else np.asarray(consequence, dtype=float)
    cons = np.where(np.isfinite(cons) & (cons > 0), cons, 1.0)
    if days_since_sample is None:
        stale = np.zeros(n)
    else:
        d = np.asarray(days_since_sample, dtype=float)
        d = np.where(np.isfinite(d), d, 0.0)
        stale = 1.0 - np.exp(-np.log(2.0) * d / max(staleness_halflife_days, 1e-6))
    return cons * (risk + w_staleness * stale)


def allocate(
    candidates: pd.DataFrame,
    budget: int,
    value_col: str = "value",
    station_col: str = "location_id",
    mandatory: set | None = None,
) -> pd.DataFrame:
    """Pick this week's sampling stations: statutory floor first, then greedy by value.

    Returns the candidate frame with `scheduled` and `schedule_reason` columns. Greedy
    is optimal here because the objective is additive across stations and the budget is
    a simple count - there is no submodular interaction to exploit within one week.
    """
    df = candidates.copy()
    df["scheduled"] = False
    df["schedule_reason"] = ""
    mandatory = mandatory or set()

    is_mand = df[station_col].isin(mandatory)
    df.loc[is_mand, ["scheduled", "schedule_reason"]] = [True, "statutory"]
    remaining = int(budget) - int(is_mand.sum())
    if remaining > 0:
        pool = df.loc[~is_mand].sort_values(value_col, ascending=False)
        pick = pool.head(remaining).index
        df.loc[pick, ["scheduled", "schedule_reason"]] = [True, "value"]
    elif remaining < 0:
        # Statutory sampling already exceeds the stated budget. Report it rather than
        # silently dropping mandatory sites.
        df.attrs["budget_exceeded_by"] = -remaining
    return df


def days_since_last_sample(
    panel: pd.DataFrame, station_col: str = "location_id", date_col: str = "week_start"
) -> pd.Series:
    """Days since the previous sampled week at each station (NaN for the first)."""
    df = panel[[station_col, date_col]].copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values([station_col, date_col])
    gap = df.groupby(station_col)[date_col].diff().dt.days
    return gap.reindex(panel.index)


def backtest_time_to_detection(
    panel: pd.DataFrame,
    prob_col: str,
    truth_col: str,
    budget_per_week: int,
    station_col: str = "location_id",
    week_col: str = "week_start",
    consequence_col: str | None = None,
    threshold: float = 0.5,
    mandatory: set | None = None,
    objective: str = "detection",
) -> pd.DataFrame:
    """Replay history under a value-based schedule and measure detection lag.

    For each week, score every station, schedule `budget_per_week` of them, and record
    whether a station that was genuinely in exceedance (`truth_col`) was among them.

    The comparison metric is **detection lag**: for each contiguous run of exceedance at
    a station, how many weeks passed before a scheduled sample landed on it. Lower is
    better. This is the number a regulator cares about, and it is far more meaningful
    than PR-AUC because it is measured in the units of the actual harm - days of
    contaminated product on the market.

    Returns one row per exceedance episode.
    """
    df = panel.copy()
    df[week_col] = pd.to_datetime(df[week_col])
    df = df.sort_values([week_col, station_col])

    df["_days_since"] = days_since_last_sample(df, station_col, week_col)
    cons = df[consequence_col].to_numpy() if consequence_col else None
    df["_value"] = sample_value(
        df[prob_col].to_numpy(), consequence=cons,
        days_since_sample=df["_days_since"].to_numpy(), threshold=threshold,
        objective=objective,
    )

    scheduled = []
    for _, wk in df.groupby(week_col, sort=True):
        scheduled.append(allocate(wk, budget_per_week, "_value", station_col, mandatory))
    sched = pd.concat(scheduled)

    # episodes = contiguous runs of truth==1 per station
    rows = []
    for st, g in sched.sort_values(week_col).groupby(station_col):
        y = g[truth_col].to_numpy().astype(int)
        picked = g["scheduled"].to_numpy()
        weeks = g[week_col].to_numpy()
        i = 0
        while i < len(y):
            if y[i] != 1:
                i += 1
                continue
            j = i
            while j < len(y) and y[j] == 1:
                j += 1
            hit = np.flatnonzero(picked[i:j])
            rows.append({
                station_col: st,
                "episode_start": weeks[i],
                "episode_weeks": int(j - i),
                "detected": bool(hit.size > 0),
                "detection_lag_weeks": int(hit[0]) if hit.size else np.nan,
            })
            i = j
    return pd.DataFrame(rows)


def summarise_backtest(episodes: pd.DataFrame) -> dict:
    """Detection rate and lag distribution across exceedance episodes."""
    if episodes.empty:
        return {"n_episodes": 0}
    lag = episodes["detection_lag_weeks"].to_numpy(dtype=float)
    seen = np.isfinite(lag)
    return {
        "n_episodes": int(len(episodes)),
        "detection_rate": float(episodes["detected"].mean()),
        "median_lag_weeks": float(np.median(lag[seen])) if seen.any() else float("nan"),
        "mean_lag_weeks": float(np.mean(lag[seen])) if seen.any() else float("nan"),
        "detected_same_week": float(np.mean(lag[seen] == 0)) if seen.any() else float("nan"),
    }
