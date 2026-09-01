from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss


def pr_auc(y_true, y_prob) -> float:
    y_true = np.asarray(y_true)
    if y_true.min() == y_true.max():
        return float("nan")
    return float(average_precision_score(y_true, y_prob))


def brier(y_true, y_prob) -> float:
    return float(brier_score_loss(y_true, y_prob))


def climatology_probs(week: np.ndarray, y: np.ndarray, week_eval: np.ndarray) -> np.ndarray:
    """Week-of-year climatology from training labels."""
    means = {}
    for w in np.unique(week):
        m = week == w
        means[int(w)] = float(np.mean(y[m])) if m.any() else float(np.mean(y))
    global_p = float(np.mean(y))
    return np.array([means.get(int(w), global_p) for w in week_eval])


def skill_vs_clim(model_metric: float, clim_metric: float, higher_is_better: bool) -> float:
    if not np.isfinite(model_metric) or not np.isfinite(clim_metric):
        return float("nan")
    if higher_is_better:
        denom = 1.0 - clim_metric if clim_metric != 1 else np.nan
        return float((model_metric - clim_metric) / denom) if denom else float("nan")
    # Brier: skill = 1 - model/clim
    if clim_metric == 0:
        return float("nan")
    return float(1.0 - model_metric / clim_metric)


def summarise(y_true, y_prob, y_clim) -> dict:
    m_pr = pr_auc(y_true, y_prob)
    c_pr = pr_auc(y_true, y_clim)
    m_br = brier(y_true, y_prob)
    c_br = brier(y_true, y_clim)
    return {
        "n": int(len(y_true)),
        "prevalence": float(np.mean(y_true)),
        "pr_auc": m_pr,
        "pr_auc_clim": c_pr,
        "pr_auc_skill": skill_vs_clim(m_pr, c_pr, True),
        "brier": m_br,
        "brier_clim": c_br,
        "brier_skill": skill_vs_clim(m_br, c_br, False),
    }
