"""Split-boundary purging and grouped (leave-one-group-out) cross-validation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pa_marine.diagnostics import grouped_cv_metrics, summarise_grouped_cv
from pa_marine.hab import add_horizon_labels
from pa_marine.splits import purge_boundary_rows


def _weekly(start, end, n_stations=1):
    wks = pd.date_range(start, end, freq="W-MON")
    iso = wks.isocalendar()
    parts = []
    for st in range(n_stations):
        parts.append(
            pd.DataFrame(
                {
                    "location_id": st,
                    "week_start": wks,
                    "iso_year": iso.year.to_numpy(),
                    "iso_week": iso.week.to_numpy(),
                    "y_dino": 0,
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def _raw_split(df):
    return pd.Series(
        np.where(df.iso_year <= 2018, "train", np.where(df.iso_year <= 2021, "val", "test")),
        index=df.index,
    )


# --------------------------------------------------------------- purging


def test_label_window_leaks_across_boundary_without_purge():
    """The bug being fixed: a train-split label sourced from val-period data."""
    df = _weekly("2018-11-05", "2019-02-25")
    df.loc[df.week_start == pd.Timestamp("2019-01-07"), "y_dino"] = 1  # in val
    out = add_horizon_labels(df, ["dino"])
    split = _raw_split(out)

    leaked = out.loc[(split == "train") & (out.y_dino_nowcast == 1)]
    assert len(leaked) >= 1, "expected forward label leakage across the split edge"
    assert (leaked.iso_year <= 2018).all()
    assert out.loc[split == "train", "y_dino"].sum() == 0, "no train-period positives exist"


def test_purge_removes_the_leak():
    df = _weekly("2018-11-05", "2019-02-25")
    df.loc[df.week_start == pd.Timestamp("2019-01-07"), "y_dino"] = 1
    out = add_horizon_labels(df, ["dino"])
    split = _raw_split(out)
    purged = purge_boundary_rows(out, split)

    assert int(out.loc[purged == "train", "y_dino_nowcast"].sum()) == 0
    assert (purged == "drop").sum() > 0
    # only boundary rows are dropped, never whole splits
    for s in ("train", "val"):
        assert (purged == s).sum() > 0


def test_purge_drops_only_the_last_horizon_of_each_split():
    df = _weekly("2016-01-04", "2023-12-25")
    out = add_horizon_labels(df, ["dino"])
    split = _raw_split(out)
    purged = purge_boundary_rows(out, split, label_horizon_days=14)

    dropped = out.loc[purged == "drop", "week_start"]
    assert len(dropped) > 0
    # every dropped row is within 14 days of a downstream split start
    val_start = out.loc[split == "val", "week_start"].min()
    test_start = out.loc[split == "test", "week_start"].min()
    for d in dropped:
        assert (d + pd.Timedelta(days=14) >= val_start) or (
            d + pd.Timedelta(days=14) >= test_start
        )
    # test is last, so nothing in it should be purged
    assert not (out.loc[purged == "drop", "iso_year"] >= 2022).any()


def test_purge_is_a_noop_with_zero_horizon():
    df = _weekly("2016-01-04", "2023-12-25")
    out = add_horizon_labels(df, ["dino"])
    split = _raw_split(out)
    purged = purge_boundary_rows(out, split, label_horizon_days=0)
    assert (purged == "drop").sum() <= (split == "drop").sum() + 2


def test_purge_handles_single_split():
    df = _weekly("2010-01-04", "2012-12-31")
    out = add_horizon_labels(df, ["dino"])
    split = pd.Series("train", index=out.index)
    purged = purge_boundary_rows(out, split)
    assert (purged == "train").all(), "nothing downstream to leak into"


# ------------------------------------------------------------- grouped CV


def _cv_panel(sst_beta, seed=5, n_st=14, n_wk=200):
    rng = np.random.default_rng(seed)
    st = np.repeat(np.arange(n_st), n_wk)
    wk = np.tile((np.arange(n_wk) % 52) + 1, n_st)
    st_eff = rng.normal(0, 1.2, n_st)[st]
    seasonal = -1.8 + 2.0 * np.sin(2 * np.pi * (wk - 14) / 52)
    sst = rng.normal(0, 1, len(st))
    y = (rng.random(len(st)) < 1 / (1 + np.exp(-(seasonal + st_eff + sst_beta * sst)))).astype(int)
    return pd.DataFrame(
        {
            "location_id": st, "iso_week": wk,
            "latitude": 51 + (st % 7) * 0.3, "longitude": -11 + (st // 7) * 1.2,
            "sst": sst,
            "woy_sin": np.sin(2 * np.pi * wk / 53), "woy_cos": np.cos(2 * np.pi * wk / 53),
            "y": y,
        }
    )


FEATS = ["sst", "woy_sin", "woy_cos", "latitude", "longitude"]


def _logreg_fp(Xtr, ytr, Xte):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    pipe = Pipeline(
        [("i", SimpleImputer(strategy="median")), ("s", StandardScaler()),
         ("c", LogisticRegression(max_iter=400, class_weight="balanced"))]
    )
    pipe.fit(Xtr, ytr)
    return pipe.predict_proba(Xte)[:, 1]


def test_grouped_cv_holds_out_whole_stations():
    df = _cv_panel(1.0)
    tab = grouped_cv_metrics(df, FEATS, "y", _logreg_fp, group_col="location_id")
    assert len(tab) == df.location_id.nunique()
    assert set(tab["location_id"]) == set(df.location_id.unique())


def test_grouped_cv_separates_real_signal_from_none():
    """Real signal must sit far above the no-signal level.

    Note the no-signal level is NOT zero: the model fits seasonality with a smooth
    Fourier basis while the baseline uses 52 independent week bins, so it wins on
    estimator variance alone. This test asserts separation, not an absolute floor -
    the null has to be established empirically per panel.
    """
    none = summarise_grouped_cv(
        grouped_cv_metrics(_cv_panel(0.0), FEATS, "y", _logreg_fp)
    )
    real = summarise_grouped_cv(
        grouped_cv_metrics(_cv_panel(1.5), FEATS, "y", _logreg_fp)
    )
    assert 0.0 < none["pr_auc_skill_median"] < 0.15, "documented non-zero null"
    assert real["pr_auc_skill_median"] > 5 * none["pr_auc_skill_median"]
    assert real["frac_folds_positive"] > 0.9


def test_smoothed_baseline_reduces_the_free_win():
    """week_smooth should shrink the no-signal skill relative to bin-wise week."""
    df = _cv_panel(0.0)
    raw = summarise_grouped_cv(
        grouped_cv_metrics(df, FEATS, "y", _logreg_fp, baseline="week")
    )
    sm = summarise_grouped_cv(
        grouped_cv_metrics(df, FEATS, "y", _logreg_fp, baseline="week_smooth")
    )
    assert sm["pr_auc_skill_median"] < raw["pr_auc_skill_median"]


def test_grouped_cv_supports_leave_one_year_out():
    df = _cv_panel(1.0)
    df["iso_year"] = 2003 + (np.arange(len(df)) % 10)
    tab = grouped_cv_metrics(df, FEATS, "y", _logreg_fp, group_col="iso_year")
    assert len(tab) == 10


def test_grouped_cv_flags_folds_with_too_few_positives():
    df = _cv_panel(1.0)
    df.loc[df.location_id == 0, "y"] = 0  # held-out station has no positives
    tab = grouped_cv_metrics(df, FEATS, "y", _logreg_fp, min_test_pos=5)
    row = tab[tab.location_id == 0].iloc[0]
    assert row["note"] == "too few held-out positives"
    s = summarise_grouped_cv(tab)
    assert s["n_folds_scored"] < s["n_folds_total"]


def test_grouped_cv_fold_cap_is_respected():
    df = _cv_panel(1.0)
    tab = grouped_cv_metrics(df, FEATS, "y", _logreg_fp, n_folds=4, seed=1)
    assert len(tab) == 4


def test_summarise_grouped_cv_on_empty_table():
    assert summarise_grouped_cv(pd.DataFrame())["n_folds_scored"] == 0
