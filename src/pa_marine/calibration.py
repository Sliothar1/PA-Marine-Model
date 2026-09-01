"""Probability calibration fitted on the validation split only (no test leakage)."""
from __future__ import annotations

from typing import Any, Literal

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


CalibMethod = Literal["isotonic", "sigmoid", "auto"]


class ProbCalibrator:
    """Map raw scores/probabilities to calibrated probabilities.

    Fit exclusively on the validation split after the base model is trained
    on train. Prefer isotonic when enough positives/negatives; fall back to
    sigmoid (Platt) otherwise.
    """

    def __init__(self, method: CalibMethod = "auto", min_pos: int = 30, min_neg: int = 30):
        self.method = method
        self.min_pos = min_pos
        self.min_neg = min_neg
        self.chosen_: str | None = None
        self._iso: IsotonicRegression | None = None
        self._platt: LogisticRegression | None = None

    def fit(self, y_true: np.ndarray, y_prob: np.ndarray) -> "ProbCalibrator":
        y = np.asarray(y_true).astype(int)
        p = np.clip(np.asarray(y_prob, dtype=float), 1e-6, 1 - 1e-6)
        n_pos = int(y.sum())
        n_neg = int(len(y) - n_pos)
        method = self.method
        if method == "auto":
            method = "isotonic" if (n_pos >= self.min_pos and n_neg >= self.min_neg) else "sigmoid"
        self.chosen_ = method
        if method == "isotonic":
            self._iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            self._iso.fit(p, y)
        else:
            # Platt scaling on logit of raw probability
            logit = np.log(p / (1.0 - p)).reshape(-1, 1)
            self._platt = LogisticRegression(max_iter=1000)
            self._platt.fit(logit, y)
        return self

    def transform(self, y_prob: np.ndarray) -> np.ndarray:
        p = np.clip(np.asarray(y_prob, dtype=float), 1e-6, 1 - 1e-6)
        if self.chosen_ is None:
            raise RuntimeError("ProbCalibrator.fit must be called before transform")
        if self.chosen_ == "isotonic":
            assert self._iso is not None
            return np.asarray(self._iso.predict(p), dtype=float)
        assert self._platt is not None
        logit = np.log(p / (1.0 - p)).reshape(-1, 1)
        return self._platt.predict_proba(logit)[:, 1]

    def to_meta(self) -> dict[str, Any]:
        return {"method": self.chosen_, "min_pos": self.min_pos, "min_neg": self.min_neg}
