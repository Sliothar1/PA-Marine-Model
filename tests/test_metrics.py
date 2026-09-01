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
