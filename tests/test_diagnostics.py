"""Tests for baselines, permutation controls and coverage stratification."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pa_marine.diagnostics import (
    BASELINES,
    CONTROLS,
    baseline_probs,
    control_groups,
    coverage_strata_metrics,
    permute_within_groups,
    station_week_climatology,
)
from pa_marine.metrics import summarise


def _panel(sst_beta=0.0, seed=11, n_st=60, n_wk=200):
    """Station + seasonal structure; sst_beta controls the genuine dynamical signal."""
    rng = np.random.default_rng(seed)
    st = np.repeat(np.arange(n_st), n_wk)
    wk = np.tile((np.arange(n_wk) % 52) + 1, n_st)
    st_eff = rng.normal(0, 1.0, n_st)[st]
    seasonal = -2.0 + 2.0 * np.sin(2 * np.pi * (wk - 14) / 52)
    sst = rng.normal(0, 1, len(st))
    y = (rng.random(len(st)) < 1 / (1 + np.exp(-(seasonal + st_eff + sst_beta * sst)))).astype(int)
    df = pd.DataFrame({"location_id": st, "iso_week": wk, "sst": sst, "y": y})
    df["split"] = np.where(np.tile(np.arange(n_wk), n_st) < 140, "train", "test")
    df["_truth"] = 1 / (1 + np.exp(-(seasonal + st_eff + sst_beta * sst)))
    return df


# --------------------------------------------------------------------------- baselines


def test_all_baselines_return_valid_probabilities():
    df = _panel()
    tr, te = df[df.split == "train"], df[df.split == "test"]
    for kind in BASELINES:
        p = baseline_probs(kind, tr, te, "y")
        assert len(p) == len(te)
        assert np.isfinite(p).all()
        assert ((p >= 0) & (p <= 1)).all()


def test_station_week_baseline_is_strictly_harder_to_beat():
    """The headline metric uses a week-of-year baseline; the model gets lat/lon.

    A model that knows only station identity and season - i.e. no dynamical
    information whatsoever - should look skilful against `week` and score ~0
    against `station_week`. That gap is the whole point of this baseline.
    """
    df = _panel(sst_beta=0.0)
    tr, te = df[df.split == "train"], df[df.split == "test"]
    oracle = te["_truth"].to_numpy()  # station + season only, by construction

    s_week = summarise(te.y.to_numpy(), oracle, baseline_probs("week", tr, te, "y"))
    s_sw = summarise(te.y.to_numpy(), oracle, baseline_probs("station_week", tr, te, "y"))

    assert s_week["pr_auc_skill"] > 0.15, "week baseline should be beatable for free"
    assert s_sw["pr_auc_skill"] < s_week["pr_auc_skill"] - 0.1
    assert s_sw["pr_auc_skill"] < 0.1, "station_week should not be beatable for free"


def test_station_week_falls_back_for_unseen_station_and_week():
    df = _panel()
    tr = df[df.split == "train"]
    ev = pd.DataFrame({"location_id": [9999], "iso_week": [99]})
    p = station_week_climatology(
        tr.location_id.to_numpy(), tr.iso_week.to_numpy(), tr.y.to_numpy(),
        ev.location_id.to_numpy(), ev.iso_week.to_numpy(),
    )
    assert np.isfinite(p).all()
    assert 0 < p[0] < 1
    assert p[0] == pytest.approx(tr.y.mean(), abs=0.05)


def test_shrinkage_protects_sparse_stations():
    """A station with 3 samples and 1 exceedance must not be credited with 33%."""
    train = pd.DataFrame(
        {"location_id": [0] * 3 + [1] * 500, "iso_week": [20] * 503,
         "y": [1, 0, 0] + [0] * 500}
    )
    ev = pd.DataFrame({"location_id": [0], "iso_week": [20]})
    p = baseline_probs("station", train, ev, "y")[0]
    assert p < 0.1, "sparse station rate should shrink toward the global rate"


def test_unknown_baseline_raises():
    df = _panel()
    with pytest.raises(ValueError, match="unknown baseline"):
        baseline_probs("nope", df, df, "y")


# --------------------------------------------------------------- permutation controls


def test_permutation_preserves_positive_count():
    df = _panel()
    rng = np.random.default_rng(0)
    for control in CONTROLS:
        yp = permute_within_groups(df.y.to_numpy(), control_groups(df, control), rng)
        assert yp.sum() == df.y.sum()
        assert len(yp) == len(df)


def test_each_control_destroys_what_it_claims():
    df = _panel(sst_beta=1.2)
    rng = np.random.default_rng(0)
    y, sst, st, wk = df.y.to_numpy(), df.sst.to_numpy(), df.location_id.to_numpy(), df.iso_week.to_numpy()

    def structure(yp):
        return {
            "sst": abs(np.corrcoef(yp, sst)[0, 1]),
            "station": np.corrcoef(
                pd.Series(y).groupby(st).mean(), pd.Series(yp).groupby(st).mean()
            )[0, 1],
            "season": np.corrcoef(
                pd.Series(y).groupby(wk).mean(), pd.Series(yp).groupby(wk).mean()
            )[0, 1],
        }

    assert structure(y)["sst"] > 0.15  # there is a real link to destroy

    g = structure(permute_within_groups(y, control_groups(df, "global"), rng))
    assert g["sst"] < 0.05 and abs(g["station"]) < 0.3

    s = structure(permute_within_groups(y, control_groups(df, "within_station"), rng))
    assert s["sst"] < 0.05 and s["station"] > 0.99  # station rate exactly preserved

    w = structure(permute_within_groups(y, control_groups(df, "within_week"), rng))
    assert w["sst"] < 0.05 and w["season"] > 0.99  # seasonality exactly preserved

    m = structure(permute_within_groups(y, control_groups(df, "within_station_month"), rng))
    assert m["sst"] < 0.06, "the SST link must die"
    assert m["station"] > 0.99 and m["season"] > 0.9, "station and season must survive"


def test_unknown_control_raises():
    df = _panel()
    with pytest.raises(ValueError, match="unknown control"):
        control_groups(df, "nope")


# ------------------------------------------------------------------ coverage strata


def test_coverage_strata_splits_and_flags_thin_strata():
    df = _panel()
    rng = np.random.default_rng(1)
    n_obs = rng.choice([1, 2, 3], size=len(df), p=[0.02, 0.2, 0.78])
    tab = coverage_strata_metrics(
        df.y.to_numpy(), df["_truth"].to_numpy(), np.full(len(df), df.y.mean()),
        n_obs, min_rows=500,
    )
    assert set(tab["n_obs"]) == {1, 2, 3}
    assert "note" in tab.columns and tab.loc[tab.n_obs == 1, "note"].notna().all()
    big = tab[tab.n_obs == 3].iloc[0]
    assert np.isfinite(big["pr_auc"]) and big["n"] > 500


def test_coverage_strata_carries_bootstrap_ci_when_requested():
    df = _panel()
    n_obs = np.full(len(df), 3)
    tab = coverage_strata_metrics(
        df.y.to_numpy(), df["_truth"].to_numpy(), np.full(len(df), df.y.mean()),
        n_obs, groups=df.location_id.to_numpy(), n_boot=40, min_rows=100,
    )
    row = tab.iloc[0]
    assert row["bootstrap_unit"] == "cluster"
    assert np.isfinite(row["pr_auc_skill_ci_low"])
    assert row["pr_auc_skill_ci_low"] <= row["pr_auc_skill"] <= row["pr_auc_skill_ci_high"]
