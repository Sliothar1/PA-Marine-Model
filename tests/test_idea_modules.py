"""Tests for the four new capability modules (ideas 1, 2, 3, 5 in OCEAN_IDEAS.md).

Each is validated against data with known ground truth, so the tests check that the tool
returns the *right verdict*, not merely that it runs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# =========================================================== idea 1: downscaling


from pa_marine.downscale import (  # noqa: E402
    build_inshore_features,
    fit_predict_inshore,
    loso_validate,
    skill_vs_offshore,
    solar_geometry,
)


def test_solar_geometry_is_physically_sensible():
    dates = pd.Series(pd.to_datetime(["2023-06-21", "2023-12-21", "2023-03-21"]))
    g = solar_geometry(dates, latitude=53.3)  # Connemara
    # summer solstice long, winter short, equinox ~12h
    assert g.day_length_h.iloc[0] > 16.0
    assert g.day_length_h.iloc[1] < 8.0
    assert g.day_length_h.iloc[2] == pytest.approx(12.0, abs=0.4)
    # declination sign flips between solstices
    assert g.solar_decl_deg.iloc[0] > 20 and g.solar_decl_deg.iloc[1] < -20


def test_day_length_is_flat_at_equator_and_extreme_at_pole():
    dates = pd.Series(pd.to_datetime(["2023-06-21", "2023-12-21"]))
    eq = solar_geometry(dates, latitude=0.0)
    assert eq.day_length_h.max() - eq.day_length_h.min() < 0.5
    arctic = solar_geometry(dates, latitude=78.0)
    assert arctic.day_length_h.iloc[0] == pytest.approx(24.0, abs=0.1)


def _synth_inshore(n_sites=4, days=900, seed=3):
    """Inshore temp = offshore + solar heating - wind mixing + freshwater term."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2019-01-01", periods=days, freq="D")
    doy = dates.dayofyear.to_numpy()
    parts = []
    for s in range(n_sites):
        offshore = 11.5 + 3.5 * np.sin(2 * np.pi * (doy - 120) / 365.25) + rng.normal(0, 0.3, days)
        wind = np.abs(rng.normal(6, 2.5, days))
        solar = np.clip(2000 * np.sin(np.pi * doy / 365.25), 0, None) + rng.normal(0, 200, days)
        q = np.abs(rng.lognormal(1.5, 0.6, days))
        amp = 0.6 + 0.4 * s  # site-specific sensitivity
        inshore = (
            offshore
            + amp * (solar / 2000.0) * 2.2
            - amp * (wind / 10.0) * 1.4
            - 0.02 * q
            + rng.normal(0, 0.25, days)
        )
        parts.append(pd.DataFrame({
            "site": f"site{s}", "date": dates, "inshore_temp_c": inshore,
            "offshore_sst": offshore, "wind_speed": wind, "solar_rad": solar,
            "air_temp_min": offshore - 1.5 + rng.normal(0, 0.8, days),
            "air_temp_max": offshore + 3.0 + rng.normal(0, 1.2, days),
            "river_q_local": q,
        }))
    return pd.concat(parts, ignore_index=True)


def test_downscaler_beats_offshore_sst_directly():
    """The whole point: does downscaling improve on handing over an offshore pixel?"""
    df = _synth_inshore()
    feat, feats = build_inshore_features(df, latitude=53.3)
    tr = feat[feat.date < "2021-01-01"]
    te = feat[feat.date >= "2021-01-01"]
    pred = fit_predict_inshore(tr, te, feats)["pred"].to_numpy()
    s = skill_vs_offshore(
        te.inshore_temp_c.to_numpy(), pred, te.offshore_sst.to_numpy()
    )
    assert s["rmse"] < s["rmse_offshore"], "should beat raw offshore SST"
    assert s["rmse_skill_vs_offshore"] > 0.25
    assert abs(s["bias"]) < 0.4


def test_loso_validation_holds_out_whole_sites():
    df = _synth_inshore(n_sites=4, days=500)
    feat, feats = build_inshore_features(df, latitude=53.3)
    tab = loso_validate(feat, feats)
    assert len(tab) == 4
    assert set(tab["site"]) == {f"site{i}" for i in range(4)}
    assert tab["rmse"].notna().all()


def test_features_degrade_gracefully_when_predictors_absent():
    """A station with no river gauge or offshore pixel must still build features."""
    df = _synth_inshore(n_sites=1, days=300).drop(
        columns=["river_q_local", "offshore_sst"]
    )
    feat, feats = build_inshore_features(df, latitude=53.3)
    assert len(feats) > 5
    assert not any("river_q_local" in f for f in feats)
    assert not any(f.startswith("offshore_sst") for f in feats)


def test_fit_raises_when_no_training_truth():
    df = _synth_inshore(n_sites=1, days=200)
    feat, feats = build_inshore_features(df, latitude=53.3)
    empty = feat.assign(inshore_temp_c=np.nan)
    with pytest.raises(ValueError, match="no finite"):
        fit_predict_inshore(empty, feat, feats)


def test_skill_reports_nothing_useful_on_too_few_points():
    assert skill_vs_offshore(np.array([1.0]), np.array([1.0]))["n"] == 1


# ============================================================ idea 2: scheduler


from pa_marine.scheduler import (  # noqa: E402
    OBJECTIVES,
    allocate,
    decision_uncertainty,
    sample_value,
    summarise_backtest,
)


def test_decision_uncertainty_peaks_at_threshold():
    p = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    u = decision_uncertainty(p, threshold=0.5)
    assert u.argmax() == 2
    assert u[0] < u[1] < u[2] and u[2] > u[3] > u[4]


def test_detection_objective_weights_high_risk_not_the_middle():
    """The bug the backtest caught: 'decision' scoring skips likely exceedances."""
    p = np.array([0.05, 0.5, 0.95])
    v_det = sample_value(p, objective="detection", w_staleness=0.0)
    v_dec = sample_value(p, objective="decision", w_staleness=0.0)
    assert v_det.argmax() == 2, "detection should prefer the p=0.95 station"
    assert v_dec.argmax() == 1, "decision should prefer the ambiguous station"


def test_objective_is_validated():
    with pytest.raises(ValueError, match="objective must be"):
        sample_value(np.array([0.5]), objective="nonsense")
    assert set(OBJECTIVES) == {"detection", "decision", "balanced"}


def test_consequence_scales_value_and_bad_values_are_ignored():
    p = np.array([0.5, 0.5])
    v = sample_value(p, consequence=np.array([1.0, 10.0]), w_staleness=0.0)
    assert v[1] == pytest.approx(10 * v[0])
    # NaN / non-positive consequence falls back to 1.0 rather than poisoning the score
    v2 = sample_value(p, consequence=np.array([np.nan, -5.0]), w_staleness=0.0)
    assert np.isfinite(v2).all() and (v2 > 0).all()


def test_staleness_saturates():
    p = np.array([0.5, 0.5])
    v = sample_value(p, days_since_sample=np.array([14.0, 3650.0]), w_staleness=1.0)
    assert v[1] > v[0]
    assert v[1] / v[0] < 3.0, "an unsampled site must not monopolise the schedule"


def test_allocate_respects_budget_and_statutory_floor():
    df = pd.DataFrame({"location_id": list(range(10)), "value": np.arange(10.0)})
    got = allocate(df, budget=4, mandatory={0})
    assert got["scheduled"].sum() == 4
    assert got.loc[got.location_id == 0, "schedule_reason"].iloc[0] == "statutory"
    # the remaining 3 go to the highest-value non-mandatory stations
    chosen = set(got.loc[got.scheduled & (got.schedule_reason == "value"), "location_id"])
    assert chosen == {9, 8, 7}


def test_allocate_flags_statutory_over_budget():
    df = pd.DataFrame({"location_id": [0, 1, 2], "value": [1.0, 2.0, 3.0]})
    got = allocate(df, budget=1, mandatory={0, 1, 2})
    assert got["scheduled"].sum() == 3
    assert got.attrs.get("budget_exceeded_by") == 2


def test_summarise_backtest_on_empty():
    assert summarise_backtest(pd.DataFrame())["n_episodes"] == 0


# ============================================================ idea 3: advection


from pa_marine.advection import (  # noqa: E402
    build_advection_graph,
    lag_profile,
    summarise_lift,
    assess_directed_lift,
    transit_time_days,
)


def test_transit_time_arithmetic():
    # 86.4 km at 1 m/s is exactly one day
    assert transit_time_days(86.4, 1.0) == pytest.approx(1.0, abs=1e-6)
    assert not np.isfinite(transit_time_days(100.0, 0.0))
    assert not np.isfinite(transit_time_days(100.0, -1.0))


def _chain_sites(n=5, spacing_deg=0.36):
    return pd.DataFrame({
        "site_id": [f"s{i}" for i in range(n)],
        "latitude": [53.0 + i * spacing_deg for i in range(n)],
        "longitude": [-10.0] * n,
    })


def test_currents_make_the_graph_directed():
    sites = _chain_sites()
    north = pd.DataFrame({"site_id": sites.site_id, "uo": 0.0, "vo": 0.10})
    g = build_advection_graph(sites, currents=north)
    # with northward flow, every edge must run south -> north
    assert len(g) > 0
    for e in g.itertuples():
        assert int(e.src[1:]) < int(e.dst[1:]), "edge points upstream"


def test_graph_is_symmetric_without_currents():
    g = build_advection_graph(_chain_sites(n=3), max_transit_days=60.0)
    pairs = set(zip(g.src, g.dst))
    assert ("s0", "s1") in pairs and ("s1", "s0") in pairs


def test_transit_cap_prunes_distant_pairs():
    sites = _chain_sites(n=6)
    near = build_advection_graph(sites, max_transit_days=6.0)
    far = build_advection_graph(sites, max_transit_days=40.0)
    assert len(near) < len(far)
    assert near["transit_days"].max() <= 6.0


def _propagating_panel(advect: bool, seed=7):
    wks = pd.date_range("2010-01-04", "2024-12-30", freq="W-MON")
    rng = np.random.default_rng(seed)
    woy = wks.isocalendar().week.to_numpy()
    seasonal = -2.2 + 2.2 * np.sin(2 * np.pi * (woy - 26) / 52)
    seed_series = rng.normal(0, 1.2, len(wks))
    parts = []
    for i in range(5):
        lag = int(round(i * 40 * 1000 / (0.10 * 86400) / 7)) if advect else 0
        f = np.roll(seed_series, lag) if advect else np.zeros(len(wks))
        p = 1 / (1 + np.exp(-(seasonal + f + rng.normal(0, 0.7, len(wks)))))
        parts.append(pd.DataFrame({
            "site_id": f"s{i}", "week_start": wks,
            "y": (rng.random(len(wks)) < p).astype(int),
        }))
    return pd.concat(parts, ignore_index=True)


def test_lift_test_distinguishes_transport_from_shared_seasonality():
    """The verdict must flip between a propagating signal and a co-seasonal one."""
    sites = _chain_sites()
    g = build_advection_graph(
        sites, currents=pd.DataFrame({"site_id": sites.site_id, "uo": 0.0, "vo": 0.10})
    )
    adv = summarise_lift(assess_directed_lift(_propagating_panel(True), g))
    nul = summarise_lift(assess_directed_lift(_propagating_panel(False), g))

    assert adv["verdict"] == "advective signal plausible"
    assert nul["verdict"] == "no evidence of transport beyond shared seasonality"
    assert adv["median_lift"] > nul["median_lift"] + 0.05
    # implied lag should be the best lag far more often than chance under real transport
    assert adv["frac_best_lag_equals_implied"] > 0.4
    assert nul["frac_best_lag_equals_implied"] < adv["frac_best_lag_equals_implied"]


def test_lag_profile_deseasonalises_by_default():
    panel = _propagating_panel(False)
    raw = lag_profile(panel, "s0", "s1", range(0, 5), deseasonalise=False)
    des = lag_profile(panel, "s0", "s1", range(0, 5), deseasonalise=True)
    # removing the shared annual cycle must reduce the spurious association
    assert des["corr"].mean() < raw["corr"].mean()


def test_summarise_lift_on_empty():
    assert summarise_lift(pd.DataFrame())["n_edges"] == 0


# ============================================================ idea 5: decisions


from pa_marine.decisions import (  # noqa: E402
    CostStructure,
    closure_day_index,
    expected_cost,
    harvest_recommendation,
    index_return_period,
    realised_cost,
)


@pytest.mark.parametrize("ratio, expected", [(2, 0.5), (4, 0.25), (10, 0.1), (25, 0.04)])
def test_breakeven_follows_cost_ratio(ratio, expected):
    c = CostStructure(harvest_into_closure=ratio, wait_unnecessarily=1.0)
    assert c.breakeven_probability == pytest.approx(expected, abs=1e-6)


def test_cost_structure_validates_inputs():
    with pytest.raises(ValueError):
        CostStructure(harvest_into_closure=0.0)
    with pytest.raises(ValueError):
        CostStructure(wait_unnecessarily=-1.0)


def test_action_flips_at_the_breakeven_probability():
    c = CostStructure(harvest_into_closure=10.0, wait_unnecessarily=1.0)
    out = expected_cost(np.array([0.05, 0.15]), c)
    assert out.action.tolist() == ["harvest", "wait"]


def test_uncalibrated_probabilities_are_refused():
    c = CostStructure()
    with pytest.raises(ValueError, match="calibrated"):
        harvest_recommendation(np.array([0.3]), c)
    ok = harvest_recommendation(np.array([0.3]), c, calibrated=True)
    assert ok.action.iloc[0] in {"wait", "harvest"}
    assert "confidence" in ok.columns


def test_decision_rule_beats_both_fixed_policies():
    """A model that cannot beat 'always harvest' adds nothing, whatever its PR-AUC."""
    rng = np.random.default_rng(4)
    n = 6000
    p_true = rng.beta(1.4, 6.0, n)
    y = (rng.random(n) < p_true).astype(int)
    r = realised_cost(p_true, y, CostStructure(harvest_into_closure=10.0))
    assert r["cost_model"] < r["cost_always_harvest"]
    assert r["cost_model"] < r["cost_always_wait"]
    assert r["cost_skill_vs_best_fixed"] > 0
    assert r["cost_oracle"] < r["cost_model"], "oracle must be the floor"


def test_overconfident_probabilities_collapse_the_policy():
    """Why the calibration guard exists: over-confidence silently degrades decisions."""
    rng = np.random.default_rng(4)
    n = 6000
    p_true = rng.beta(1.4, 6.0, n)
    y = (rng.random(n) < p_true).astype(int)
    over = np.clip(p_true**0.45, 1e-6, 1 - 1e-6)
    c = CostStructure(harvest_into_closure=10.0)
    good = realised_cost(p_true, y, c)
    bad = realised_cost(over, y, c)
    assert bad["frac_waiting"] > 0.95, "over-confidence pushes everything to 'wait'"
    assert bad["cost_skill_vs_best_fixed"] < good["cost_skill_vs_best_fixed"]


def test_realised_cost_on_empty_input():
    assert realised_cost(np.array([]), np.array([]), CostStructure())["n"] == 0


def test_closure_day_index_and_return_period():
    wks = pd.date_range("2015-01-05", "2024-12-30", freq="W-MON")
    rng = np.random.default_rng(2)
    df = pd.concat([
        pd.DataFrame({
            "parent_area_name": area, "week_start": wks,
            "closed": (rng.random(len(wks)) < rate).astype(int),
        })
        for area, rate in (("Killary", 0.25), ("Bantry", 0.05))
    ])
    idx = closure_day_index(df)
    assert set(idx.parent_area_name) == {"Killary", "Bantry"}
    k = idx[idx.parent_area_name == "Killary"].closure_days.mean()
    b = idx[idx.parent_area_name == "Bantry"].closure_days.mean()
    assert k > b, "the higher-risk area must show more closure days"
    assert (idx.closure_fraction.between(0, 1)).all()

    rp = index_return_period(idx, "Killary", threshold_days=1e6)
    assert rp["return_period_seasons"] == float("inf")
    rp0 = index_return_period(idx, "Killary", threshold_days=0.0)
    assert rp0["exceedance_prob"] == 1.0
    assert "caveat" in rp0


def test_index_return_period_on_unknown_area():
    idx = pd.DataFrame({"parent_area_name": ["A"], "season": [2020], "closure_days": [7]})
    assert index_return_period(idx, "Nowhere", 5)["n_seasons"] == 0
