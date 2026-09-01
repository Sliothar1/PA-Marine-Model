import numpy as np

from pa_marine.calibration import ProbCalibrator
from pa_marine.metrics import brier


def test_isotonic_improves_overconfident_probs():
    rng = np.random.default_rng(0)
    # True prevalence ~0.1; overconfident raw probs near 0.5–0.9
    n = 800
    y = (rng.random(n) < 0.1).astype(int)
    raw = np.clip(0.55 + 0.35 * y + rng.normal(0, 0.08, n), 0.01, 0.99)
    cal = ProbCalibrator(method="isotonic").fit(y, raw)
    assert cal.chosen_ == "isotonic"
    adj = cal.transform(raw)
    assert brier(y, adj) < brier(y, raw)


def test_sigmoid_fallback_on_tiny_positives():
    y = np.array([0, 0, 0, 0, 0, 1, 0, 0, 0, 0])
    raw = np.array([0.1, 0.2, 0.15, 0.3, 0.25, 0.9, 0.05, 0.12, 0.18, 0.22])
    cal = ProbCalibrator(method="auto", min_pos=30).fit(y, raw)
    assert cal.chosen_ == "sigmoid"
    out = cal.transform(raw)
    assert out.shape == raw.shape
    assert np.all((out >= 0) & (out <= 1))
