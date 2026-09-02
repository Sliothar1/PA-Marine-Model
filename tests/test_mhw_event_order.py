"""Event assembly order and fixed climatology baseline (Hobday et al. 2016).

Hobday's algorithm (and Oliver's reference `marineHeatWaves` implementation) applies
the >= min_duration filter to above-threshold runs FIRST, and only then joins the
surviving events across gaps of <= max_gap days.

v1 of this module did it the other way round, which let two runs that were each too
short to be events bootstrap each other into one. On red-noise SST that over-detected
MHW days by ~55%.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pa_marine.mhw import detect_mhw

# 40-year flat baseline: a single injected spike cannot inflate its own DOY threshold.
N_YEARS = 40
SPIKE_AT = 7000


def _series(pattern: list[int]) -> tuple[pd.DatetimeIndex, np.ndarray]:
    dates = pd.date_range("1985-01-01", periods=365 * N_YEARS, freq="D")
    sst = np.full(len(dates), 10.0)
    for k, v in enumerate(pattern):
        if v:
            sst[SPIKE_AT + k] = 20.0
    return dates, sst


def _mhw_days(pattern: list[int], order: str) -> int:
    dates, sst = _series(pattern)
    df = detect_mhw(dates, sst, min_duration=5, max_gap=2, event_order=order)
    return int(df["in_mhw"].iloc[SPIKE_AT : SPIKE_AT + len(pattern)].sum())


@pytest.mark.parametrize(
    "pattern, expected, why",
    [
        ([1, 1, 1, 0, 0, 1, 1, 1], 0, "neither 3-day run reaches min_duration"),
        ([1] * 6 + [0, 0] + [1] * 6, 14, "both runs qualify, 2-day gap joined"),
        ([1, 1, 1, 1], 0, "4 days is below min_duration"),
        ([1] * 5, 5, "exactly min_duration"),
        ([1] * 6 + [0, 0, 0] + [1] * 6, 12, "3-day gap exceeds max_gap, stays 2 events"),
        ([1, 1, 1, 0, 0] + [1] * 6, 6, "only the second run qualifies; no back-join"),
        ([1] * 4 + [0] + [1] * 4 + [0] + [1] * 4, 0, "chain of sub-duration runs"),
    ],
)
def test_hobday_event_assembly(pattern, expected, why):
    assert _mhw_days(pattern, "hobday") == expected, why


def test_legacy_over_detects_short_runs():
    """The pre-fix ordering invents events from runs that are each too short."""
    short_chain = [1] * 4 + [0] + [1] * 4 + [0] + [1] * 4
    assert _mhw_days(short_chain, "hobday") == 0
    assert _mhw_days(short_chain, "legacy") == 14


def test_event_order_validated():
    dates, sst = _series([1] * 6)
    with pytest.raises(ValueError, match="event_order"):
        detect_mhw(dates, sst, event_order="nonsense")


def test_fixed_baseline_is_not_refitted_on_later_years():
    """A threshold fitted on 2003-2018 must ignore later SST entirely.

    Warm the post-2018 tail hard. With a fixed baseline the early-period threshold is
    unchanged; with the full-series default it is dragged upward, which both leaks
    evaluation-period SST and damps MHW detection in the later years.
    """
    dates = pd.date_range("2003-01-01", "2026-08-16", freq="D")
    rng = np.random.default_rng(11)
    sst = pd.Series(10.0 + rng.normal(0, 0.4, len(dates)))
    sst[dates.year >= 2019] += 3.0

    fixed = detect_mhw(dates, sst, baseline_years=(2003, 2018))
    full = detect_mhw(dates, sst, baseline_years=None)

    early = dates.year <= 2018
    # Fixed baseline: early-period threshold reflects only early-period SST.
    assert fixed.loc[early, "thresh"].mean() < full.loc[early, "thresh"].mean() - 0.5
    # And the warm tail is correctly flagged as almost entirely in MHW.
    late = dates.year >= 2020
    assert fixed.loc[late, "in_mhw"].mean() > 0.9
    # Whereas absorbing the warming into the threshold hides most of it.
    assert full.loc[late, "in_mhw"].mean() < fixed.loc[late, "in_mhw"].mean()


def test_baseline_years_outside_series_raises():
    dates, sst = _series([1] * 6)
    with pytest.raises(ValueError, match="selects no days"):
        detect_mhw(dates, sst, baseline_years=(2100, 2110))


def test_config_defaults_to_fixed_baseline_and_hobday():
    from pa_marine.config import load_config

    cfg = load_config()
    assert cfg["mhw"].get("event_order") == "hobday"
    assert cfg["mhw"].get("climatology_baseline") == [2003, 2018]
