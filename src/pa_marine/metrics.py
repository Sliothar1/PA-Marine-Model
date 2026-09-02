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


def _cluster_index(groups: np.ndarray) -> list[np.ndarray]:
    """Row indices per cluster, computed once (sort-based, not one scan per cluster)."""
    order = np.argsort(groups, kind="stable")
    sorted_g = np.asarray(groups)[order]
    starts = np.flatnonzero(np.r_[True, sorted_g[1:] != sorted_g[:-1]])
    return np.split(order, starts[1:])


def _resample_clusters(members: list[np.ndarray], rng: np.random.Generator) -> np.ndarray:
    """Draw clusters with replacement and return the concatenated row indices."""
    pick = rng.integers(0, len(members), size=len(members))
    return np.concatenate([members[k] for k in pick])


def bootstrap_summary(
    y_true,
    y_prob,
    y_clim,
    groups=None,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> dict:
    """`summarise` plus percentile bootstrap CIs and P(skill > 0).

    Station-weeks are not independent: rows from one station share a location, a local
    SST series and a sampling regime, and neighbouring stations co-bloom. An i.i.d.
    row bootstrap therefore reports intervals that are far too tight. Pass
    `groups=location_id` to resample whole stations (cluster bootstrap), which is the
    right unit of independence here.

    `pr_auc_skill_gt0` is the bootstrap fraction of replicates in which the model beat
    the week-of-year climatology. Treat a headline PR skill whose CI spans 0 as "not
    distinguishable from seasonality", regardless of the point estimate.
    """
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob, dtype=float)
    y_clim = np.asarray(y_clim, dtype=float)
    point = summarise(y_true, y_prob, y_clim)

    n = len(y_true)
    clustered = groups is not None
    groups = np.arange(n) if groups is None else np.asarray(groups)
    rng = np.random.default_rng(seed)
    keys = ("pr_auc", "pr_auc_clim", "pr_auc_skill", "brier", "brier_clim", "brier_skill")
    draws: dict[str, list[float]] = {k: [] for k in keys}
    members = _cluster_index(groups)

    for _ in range(n_boot):
        idx = _resample_clusters(members, rng)
        yt = y_true[idx]
        if yt.min() == yt.max():
            continue  # degenerate replicate: PR-AUC undefined
        rep = summarise(yt, y_prob[idx], y_clim[idx])
        for k in keys:
            draws[k].append(rep[k])

    lo_q, hi_q = 100 * alpha / 2, 100 * (1 - alpha / 2)
    out = dict(point)
    out["n_boot"] = n_boot
    out["n_boot_used"] = len(draws["pr_auc"])
    out["bootstrap_unit"] = "cluster" if clustered else "row"
    out["n_clusters"] = len(members)
    for k in keys:
        v = np.asarray([x for x in draws[k] if np.isfinite(x)], dtype=float)
        if v.size < 20:
            out[f"{k}_ci_low"] = float("nan")
            out[f"{k}_ci_high"] = float("nan")
            continue
        out[f"{k}_ci_low"] = float(np.percentile(v, lo_q))
        out[f"{k}_ci_high"] = float(np.percentile(v, hi_q))
    for k in ("pr_auc_skill", "brier_skill"):
        v = np.asarray([x for x in draws[k] if np.isfinite(x)], dtype=float)
        out[f"{k}_gt0"] = float(np.mean(v > 0)) if v.size else float("nan")
    return out
