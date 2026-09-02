import numpy as np
from pa_marine.metrics import skill_vs_clim, summarise


def test_perfect_classifier_metrics():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.0, 0.0, 1.0, 1.0])
    clim = np.array([0.5, 0.5, 0.5, 0.5])
    s = summarise(y, p, clim)
    assert s["pr_auc"] == 1.0
    assert s["brier"] == 0.0
    assert s["brier_skill"] == 1.0


def test_brier_skill():
    assert abs(skill_vs_clim(0.1, 0.2, False) - 0.5) < 1e-9


def test_bootstrap_cluster_ci_is_wider_than_row_ci():
    """Station-weeks are clustered; an i.i.d. row bootstrap understates uncertainty."""
    import numpy as np

    from pa_marine.metrics import bootstrap_summary, climatology_probs

    rng = np.random.default_rng(3)
    n_st, n_wk = 40, 120
    st = np.repeat(np.arange(n_st), n_wk)
    woy = np.tile(np.arange(1, n_wk + 1) % 52 + 1, n_st)
    seasonal = -1.6 + 1.9 * np.sin(2 * np.pi * (woy - 14) / 52)
    station_re = rng.normal(0, 0.9, n_st)[st]
    logit = seasonal + station_re + rng.normal(0, 0.7, n_st * n_wk)
    y = (rng.random(n_st * n_wk) < 1 / (1 + np.exp(-logit))).astype(int)
    score = 1 / (1 + np.exp(-(seasonal + station_re)))
    clim = climatology_probs(woy, y, woy)

    row = bootstrap_summary(y, score, clim, n_boot=120, seed=1)
    clus = bootstrap_summary(y, score, clim, groups=st, n_boot=120, seed=1)

    assert row["bootstrap_unit"] == "row" and clus["bootstrap_unit"] == "cluster"
    assert clus["n_clusters"] == n_st
    # point estimates identical; only the intervals differ
    assert row["pr_auc"] == clus["pr_auc"]
    w_row = row["pr_auc_skill_ci_high"] - row["pr_auc_skill_ci_low"]
    w_clus = clus["pr_auc_skill_ci_high"] - clus["pr_auc_skill_ci_low"]
    assert w_clus > 1.5 * w_row
    # CI must bracket the point estimate
    assert clus["pr_auc_skill_ci_low"] <= clus["pr_auc_skill"] <= clus["pr_auc_skill_ci_high"]
    assert 0.0 <= clus["pr_auc_skill_gt0"] <= 1.0


def test_bootstrap_degenerate_labels_do_not_crash():
    import numpy as np

    from pa_marine.metrics import bootstrap_summary

    y = np.zeros(200, dtype=int)          # no positives anywhere
    p = np.random.default_rng(0).random(200)
    r = bootstrap_summary(y, p, np.full(200, 0.1), n_boot=30)
    assert r["n_boot_used"] == 0
    assert r["pr_auc_skill_ci_low"] != r["pr_auc_skill_ci_low"]  # NaN
