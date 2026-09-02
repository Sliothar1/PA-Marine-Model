"""Idea 5 - Decision layer: turn a calibrated probability into an action, and an index.

Two things a grower and an insurer both need, and neither gets from a PR-AUC.

**Layer A - harvest timing.** A probability is not a decision. The grower's actual choice
is harvest now or wait, and both directions have costs: harvesting into an undetected
closure risks destroyed product and reputational damage; waiting risks lost condition, a
missed market window, or the season. Given a *calibrated* probability and a cost
structure, the optimal action is an expected-value comparison.

This is where the project's existing calibration work pays off, and it is worth being
precise about why. The README reports raw Brier skill of -1.10 improving to -0.01 after
isotonic calibration - i.e. the uncalibrated probabilities from `class_weight="balanced"`
are wildly over-confident. An over-confident probability fed into a cost matrix produces
systematically wrong actions, and it fails *silently*: the ranking (PR-AUC) barely moves,
so nothing in the metrics table warns you. `expected_cost` is only meaningful on
calibrated output, and `require_calibrated` exists to make that explicit rather than
assumed.

**Layer B - closure-day index.** An area-level count of closure days per season, built
from `habs_status`. This makes a good parametric insurance trigger because it is
objective, independently verifiable from a public regulator feed, and effectively
impossible for either party to manipulate. Aquaculture is under-insured largely because no
such trigger exists, and small family operations are the ones that need cover most - a
large firm can absorb a lost harvest.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class CostStructure:
    """Costs of each outcome, in whatever currency the grower thinks in.

    Only *relative* magnitudes matter for the decision, so a grower who knows "a lost
    harvest is about four times worse than a fortnight's delay" can use 4 and 1 without
    estimating anything in euros.

    harvest_into_closure
        Product destroyed or recalled, plus reputational cost. The expensive mistake.
    wait_unnecessarily
        Condition loss, missed market window, extra holding cost, per week of delay.
    harvest_clean
        Baseline, normally 0 - this is the intended outcome.
    wait_correctly
        Avoided a real closure, but still paid the delay. Normally the same as
        wait_unnecessarily: the delay costs the same whether or not it turned out to be
        needed. Kept separate because some operations can partially recover value.
    """

    def __init__(
        self,
        harvest_into_closure: float = 10.0,
        wait_unnecessarily: float = 1.0,
        harvest_clean: float = 0.0,
        wait_correctly: float | None = None,
    ):
        if harvest_into_closure <= 0 or wait_unnecessarily < 0:
            raise ValueError("harvest_into_closure must be > 0 and wait cost >= 0")
        self.harvest_into_closure = float(harvest_into_closure)
        self.wait_unnecessarily = float(wait_unnecessarily)
        self.harvest_clean = float(harvest_clean)
        self.wait_correctly = (
            float(wait_unnecessarily) if wait_correctly is None else float(wait_correctly)
        )

    @property
    def breakeven_probability(self) -> float:
        """The probability above which waiting beats harvesting.

        E[harvest] = p*C_hic + (1-p)*C_hc ; E[wait] = p*C_wc + (1-p)*C_wu
        Solving for equality gives the threshold below. Note this is a property of the
        *costs alone* - the model does not enter. A grower can therefore sanity-check
        their own cost numbers against the threshold they imply before trusting any
        forecast: if your costs imply acting at p=0.02, no model will serve you well.
        """
        num = self.wait_unnecessarily - self.harvest_clean
        den = (
            (self.harvest_into_closure - self.harvest_clean)
            - (self.wait_correctly - self.wait_unnecessarily)
        )
        if den <= 0:
            return float("nan")
        return float(np.clip(num / den, 0.0, 1.0))


def expected_cost(prob: np.ndarray, costs: CostStructure) -> pd.DataFrame:
    """Expected cost of each action, and the cheaper one, per row."""
    p = np.clip(np.asarray(prob, dtype=float), 0.0, 1.0)
    e_harvest = p * costs.harvest_into_closure + (1 - p) * costs.harvest_clean
    e_wait = p * costs.wait_correctly + (1 - p) * costs.wait_unnecessarily
    return pd.DataFrame({
        "prob_closure": p,
        "expected_cost_harvest": e_harvest,
        "expected_cost_wait": e_wait,
        "action": np.where(e_wait < e_harvest, "wait", "harvest"),
        "cost_of_regret": np.abs(e_wait - e_harvest),
    })


def harvest_recommendation(
    prob: np.ndarray,
    costs: CostStructure,
    require_calibrated: bool = True,
    calibrated: bool = False,
) -> pd.DataFrame:
    """Actionable recommendation, refusing to run on uncalibrated probabilities.

    The guard is deliberate. Uncalibrated output from a `class_weight="balanced"` model
    is over-confident by roughly the factor the class weighting introduced, and feeding
    that into a cost matrix shifts every decision toward "wait" - producing a system
    that looks cautious and is in fact just miscalibrated. Pass `calibrated=True` only
    for probabilities that went through `ProbCalibrator` fitted on the validation split.
    """
    if require_calibrated and not calibrated:
        raise ValueError(
            "harvest_recommendation needs calibrated probabilities. Fit "
            "pa_marine.calibration.ProbCalibrator on the validation split, apply it, "
            "then pass calibrated=True. Raw class_weight='balanced' output is "
            "over-confident (README: raw Brier skill -1.10 vs -0.01 calibrated) and "
            "will systematically distort the action."
        )
    out = expected_cost(prob, costs)
    out["breakeven_prob"] = costs.breakeven_probability
    # margin: how far past the breakeven point, i.e. how firm the call is
    out["margin"] = out["prob_closure"] - costs.breakeven_probability
    out["confidence"] = pd.cut(
        out["margin"].abs(), bins=[-0.01, 0.05, 0.15, 1.0],
        labels=["marginal", "moderate", "clear"],
    )
    return out


def realised_cost(
    prob: np.ndarray, truth: np.ndarray, costs: CostStructure
) -> dict:
    """Cost actually incurred by following the rule, against three reference policies.

    `cost_skill_vs_best_fixed` is the honest headline: it compares the model-driven
    policy against the better of always-harvest and always-wait. A model that cannot
    beat "always harvest" adds nothing, however good its PR-AUC. This is a decision-
    curve analysis in the sense of Vickers & Elkin, and it is a much harder test to
    pass than a ranking metric.
    """
    p = np.clip(np.asarray(prob, dtype=float), 0.0, 1.0)
    y = np.asarray(truth).astype(int)
    m = np.isfinite(p)
    p, y = p[m], y[m]
    if len(y) == 0:
        return {"n": 0}

    def cost_of(actions):
        c = np.where(
            actions == "harvest",
            np.where(y == 1, costs.harvest_into_closure, costs.harvest_clean),
            np.where(y == 1, costs.wait_correctly, costs.wait_unnecessarily),
        )
        return float(np.mean(c))

    model = expected_cost(p, costs)["action"].to_numpy()
    always_h = np.full(len(y), "harvest")
    always_w = np.full(len(y), "wait")
    oracle = np.where(y == 1, "wait", "harvest")

    c_model, c_h, c_w, c_o = (cost_of(a) for a in (model, always_h, always_w, oracle))
    best_fixed = min(c_h, c_w)
    return {
        "n": int(len(y)),
        "prevalence": float(np.mean(y)),
        "cost_model": c_model,
        "cost_always_harvest": c_h,
        "cost_always_wait": c_w,
        "cost_oracle": c_o,
        "cost_skill_vs_best_fixed": (
            float(1.0 - c_model / best_fixed) if best_fixed > 0 else float("nan")
        ),
        "frac_of_oracle_gap_closed": (
            float((best_fixed - c_model) / (best_fixed - c_o))
            if best_fixed > c_o else float("nan")
        ),
        "frac_waiting": float(np.mean(model == "wait")),
    }


def closure_day_index(
    status: pd.DataFrame,
    area_col: str = "parent_area_name",
    date_col: str = "week_start",
    closed_col: str = "closed",
    season_months: tuple[int, int] = (5, 10),
) -> pd.DataFrame:
    """Closure days per area per season, from `habs_status` - a parametric trigger.

    `habs_status` has no lat/lon or location_id (verified in the README), so it joins
    only on `parent_area_name` plus ISO week. That is coarse, but for an insurance
    trigger coarse is a feature: the payout unit should be the administrative area the
    regulator actually closes, not a model grid cell.

    Weeks are converted to days at 7 per closed week. If the source carries daily
    status, aggregate before calling this.
    """
    df = status.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    m0, m1 = season_months
    df = df[df[date_col].dt.month.between(m0, m1)]
    df["season"] = df[date_col].dt.year
    g = (
        df.groupby([area_col, "season"])
        .agg(weeks_observed=(closed_col, "size"), weeks_closed=(closed_col, "sum"))
        .reset_index()
    )
    g["closure_days"] = g["weeks_closed"] * 7
    g["closure_fraction"] = g["weeks_closed"] / g["weeks_observed"].replace(0, np.nan)
    return g


def index_return_period(index: pd.DataFrame, area: str, threshold_days: float,
                        area_col: str = "parent_area_name") -> dict:
    """Empirical return period for exceeding a closure-day threshold in one area.

    Used to price a trigger. Deliberately empirical rather than fitted: with ~20
    seasons of record a parametric extreme-value fit would carry more uncertainty than
    it removes, and would hide it behind a smooth curve.
    """
    a = index[index[area_col] == area]
    if a.empty:
        return {"area": area, "n_seasons": 0}
    d = a["closure_days"].to_numpy(dtype=float)
    exceed = float(np.mean(d >= threshold_days))
    return {
        "area": area,
        "n_seasons": int(len(d)),
        "threshold_days": float(threshold_days),
        "exceedance_prob": exceed,
        "return_period_seasons": float(1.0 / exceed) if exceed > 0 else float("inf"),
        "median_closure_days": float(np.median(d)),
        "max_closure_days": float(np.max(d)),
        "caveat": "empirical over a short record; wide uncertainty at high thresholds",
    }
