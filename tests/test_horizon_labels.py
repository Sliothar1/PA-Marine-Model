"""Horizon labels: vectorised equivalence, and the sampling-density confound.

`y_<tax>_nowcast` is an OR over whichever station-weeks happen to be sampled inside the
label window. Sampling effort is seasonal, so the label's base rate rises with sampling
density independently of bloom dynamics. `n_obs_*` makes that visible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pa_marine.hab import add_horizon_labels


def _reference_loop(panel, tax_ids, nowcast=(0, 14), ahead=(7, 14)):
    """The original O(k^2) pairwise implementation, kept as an oracle."""
    out = panel.sort_values(["location_id", "week_start"]).copy()
    pieces = []
    for _, g in out.groupby("location_id", sort=False):
        g = g.copy()
        ws = pd.to_datetime(g["week_start"], utc=True).dt.tz_localize(None)
        ws_d = ws.dt.normalize().to_numpy()
        for tax in tax_ids:
            y = g[f"y_{tax}"].to_numpy()
            n = len(g)
            now = np.zeros(n, dtype=int)
            a7 = np.zeros(n, dtype=int)
            for i in range(n):
                d = ((ws_d - ws_d[i]) / np.timedelta64(1, "D")).astype(int)
                now[i] = int(np.any(y[(d >= nowcast[0]) & (d <= nowcast[1])]))
                a7[i] = int(np.any(y[(d >= ahead[0]) & (d <= ahead[1])]))
            g[f"y_{tax}_nowcast"] = now
            g[f"y_{tax}_ahead7"] = a7
        pieces.append(g)
    return pd.concat(pieces, ignore_index=True)


def _irregular_panel(seed=5, n_stations=12, years=range(2010, 2020)):
    """Seasonally irregular sampling, like the real Marine Institute programme."""
    rng = np.random.default_rng(seed)
    rows = []
    for st in range(n_stations):
        for yr in years:
            for wk in range(1, 53):
                p = 0.9 if 18 <= wk <= 40 else 0.25
                if rng.random() < p:
                    rows.append((st, yr, wk, pd.Timestamp(f"{yr}-01-01") + pd.Timedelta(weeks=wk - 1)))
    panel = pd.DataFrame(rows, columns=["location_id", "iso_year", "iso_week", "week_start"])
    rate = np.where((panel.iso_week >= 18) & (panel.iso_week <= 40), 0.28, 0.03)
    panel["y_dinophysis"] = (rng.random(len(panel)) < rate).astype(int)
    panel["y_pseudo_nitzschia"] = (rng.random(len(panel)) < 0.05).astype(int)
    return panel


def test_vectorised_matches_reference_loop():
    panel = _irregular_panel()
    taxa = ["dinophysis", "pseudo_nitzschia"]
    got = add_horizon_labels(panel, taxa).sort_values(["location_id", "week_start"]).reset_index(drop=True)
    want = _reference_loop(panel, taxa).sort_values(["location_id", "week_start"]).reset_index(drop=True)
    for tax in taxa:
        for h in ("nowcast", "ahead7"):
            col = f"y_{tax}_{h}"
            assert got[col].equals(want[col]), col


def test_coverage_columns_present_and_sane():
    panel = _irregular_panel()
    out = add_horizon_labels(panel, ["dinophysis"])
    assert "n_obs_dinophysis_nowcast" in out.columns
    assert "n_obs_dinophysis_ahead7" in out.columns
    # the nowcast window [0,14] always contains the row itself
    assert (out["n_obs_dinophysis_nowcast"] >= 1).all()
    # a [0,14]-day window spans at most 3 weekly samples
    assert out["n_obs_dinophysis_nowcast"].max() <= 3
    # ahead7 [7,14] excludes the current week, so it can be empty
    assert out["n_obs_dinophysis_ahead7"].min() == 0
    assert out["n_obs_dinophysis_ahead7"].max() <= 2


def test_coverage_can_be_disabled():
    panel = _irregular_panel(n_stations=3, years=range(2010, 2013))
    out = add_horizon_labels(panel, ["dinophysis"], add_coverage=False)
    assert not [c for c in out.columns if c.startswith("n_obs_")]
    assert "y_dinophysis_nowcast" in out.columns


def test_label_rate_rises_with_sampling_density():
    """The confound itself: more samples in the window -> more positive labels.

    This is a property of the OR-over-window label definition, not of the ocean, and it
    is why metrics should be stratified by (or conditioned on) window coverage.
    """
    panel = _irregular_panel()
    out = add_horizon_labels(panel, ["dinophysis"])
    by_cov = out.groupby("n_obs_dinophysis_nowcast")["y_dinophysis_nowcast"].mean()
    assert by_cov.loc[3] > 3 * by_cov.loc[1]
    # and coverage is itself seasonal, so it is entangled with the woy features
    in_season = out.iso_week.between(18, 40)
    assert (
        out.loc[in_season, "n_obs_dinophysis_nowcast"].mean()
        > out.loc[~in_season, "n_obs_dinophysis_nowcast"].mean() + 0.5
    )


def test_single_station_single_week_is_degenerate_but_safe():
    panel = pd.DataFrame(
        {
            "location_id": [1],
            "iso_year": [2015],
            "iso_week": [20],
            "week_start": [pd.Timestamp("2015-05-11")],
            "y_dinophysis": [1],
        }
    )
    out = add_horizon_labels(panel, ["dinophysis"])
    assert out["y_dinophysis_nowcast"].iloc[0] == 1
    assert out["y_dinophysis_ahead7"].iloc[0] == 0
    assert out["n_obs_dinophysis_nowcast"].iloc[0] == 1
