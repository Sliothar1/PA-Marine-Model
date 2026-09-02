#!/usr/bin/env python3
"""Diagnostics for the HAB nowcast. Reads existing joined features; retrains nothing upstream.

    python scripts/run_diagnostics.py --joined data/processed/joined_features.parquet \
        --target y_dinophysis_nowcast --feature-mode strong --bootstrap 500

Three modes, all run by default:

  baselines    Skill against progressively fairer baselines. The current
               metrics.json uses week-of-year only, which does not credit
               station identity - yet the model is handed latitude/longitude.
  permutation  Refit on shuffled labels. Skill that survives is an artefact of
               the metric or the baseline, not the ocean.
  coverage     Skill split by how many station-weeks were sampled inside the
               label window (requires n_obs_* columns from add_horizon_labels).

Writes JSON + a markdown report. Nothing here touches data/raw or the network.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pa_marine.calibration import ProbCalibrator
from pa_marine.config import load_config
from pa_marine.diagnostics import (
    BASELINES,
    CONTROLS,
    baseline_probs,
    control_groups,
    coverage_strata_metrics,
    grouped_cv_metrics,
    permute_within_groups,
    summarise_grouped_cv,
)
from pa_marine.features import select_feature_mode
from pa_marine.metrics import bootstrap_summary, summarise
from pa_marine.models import make_estimators


def _probs(est, X) -> np.ndarray:
    if hasattr(est, "predict_proba"):
        return est.predict_proba(X)[:, 1]
    return 1 / (1 + np.exp(-est.decision_function(X)))


def _fit_and_score(df, feats, target, est_name, calibration="auto", y_override=None):
    """Fit on train, calibrate on val, return (test frame, calibrated test probs)."""
    y = df[target].astype(int).to_numpy() if y_override is None else np.asarray(y_override)
    # build the working frame in one shot; assign() on a wide joined panel refragments it
    # carry the columns downstream consumers need: cluster/baseline keys and the
    # n_obs_* sampling-coverage columns used by the coverage report.
    keep = list(dict.fromkeys(
        feats + ["split", target, "location_id", "iso_week"]
        + [c for c in df.columns if c.startswith("n_obs_")]
    ))
    keep = [c for c in keep if c in df.columns]
    d = pd.concat([df[keep].reset_index(drop=True), pd.Series(y, name="_y")], axis=1)
    tr, va, te = (d[d["split"] == s] for s in ("train", "val", "test"))
    for name, part in (("train", tr), ("test", te)):
        if part.empty:
            raise SystemExit(
                f"split {name!r} is empty - check iso_year against splits in config "
                f"(found splits: {sorted(d['split'].unique())})"
            )
    est = make_estimators()[est_name]
    est.fit(tr[feats], tr["_y"])
    p_te = _probs(est, te[feats])
    if calibration != "none" and not va.empty and va["_y"].sum() > 0:
        cal = ProbCalibrator(method=calibration).fit(va["_y"].to_numpy(), _probs(est, va[feats]))
        p_te = cal.transform(p_te)
    return tr, te, p_te


def run_baselines(df, feats, target, est_name, n_boot, cluster):
    tr, te, p_te = _fit_and_score(df, feats, target, est_name)
    yt = te["_y"].to_numpy()
    groups = te[cluster].to_numpy() if (n_boot and cluster != "row") else None
    out = {}
    for b in BASELINES:
        bp = baseline_probs(b, tr.assign(**{target: tr["_y"]}), te, target)
        out[b] = (
            bootstrap_summary(yt, p_te, bp, groups=groups, n_boot=n_boot)
            if n_boot
            else summarise(yt, p_te, bp)
        )
    return out


def run_permutation(df, feats, target, est_name, baseline, n_repeats, seed):
    """Refit on permuted labels; report the skill distribution under each control."""
    rng = np.random.default_rng(seed)
    out = {}
    for control in CONTROLS:
        skills = []
        for _ in range(n_repeats):
            yp = df[target].astype(int).to_numpy().copy()
            for split in ("train", "val", "test"):
                m = (df["split"] == split).to_numpy()
                if not m.any():
                    continue
                g = control_groups(df[m], control)
                yp[m] = permute_within_groups(yp[m], g, rng)
            tr, te, p_te = _fit_and_score(df, feats, target, est_name, y_override=yp)
            bp = baseline_probs(baseline, tr.assign(**{target: tr["_y"]}), te, target)
            s = summarise(te["_y"].to_numpy(), p_te, bp)
            if np.isfinite(s["pr_auc_skill"]):
                skills.append(s["pr_auc_skill"])
        arr = np.asarray(skills, dtype=float)
        out[control] = {
            "n_repeats": len(arr),
            "pr_auc_skill_mean": float(arr.mean()) if arr.size else float("nan"),
            "pr_auc_skill_p95": float(np.percentile(arr, 95)) if arr.size else float("nan"),
            "pr_auc_skill_max": float(arr.max()) if arr.size else float("nan"),
        }
    return out


def run_coverage(df, feats, target, est_name, baseline, n_boot, cluster):
    tax = target.replace("y_", "").rsplit("_", 1)[0]
    horizon = target.rsplit("_", 1)[1]
    col = f"n_obs_{tax}_{horizon}"
    if col not in df.columns:
        return {
            "skipped": f"{col} not in joined features - rebuild the panel with the "
            "patched hab.add_horizon_labels to emit sampling-coverage columns"
        }
    tr, te, p_te = _fit_and_score(df, feats, target, est_name)
    bp = baseline_probs(baseline, tr.assign(**{target: tr["_y"]}), te, target)
    groups = te[cluster].to_numpy() if (n_boot and cluster != "row") else None
    tab = coverage_strata_metrics(
        te["_y"].to_numpy(), p_te, bp, te[col].to_numpy(), groups=groups, n_boot=n_boot
    )
    return {"column": col, "strata": tab.to_dict(orient="records")}


def run_grouped_cv(df, feats, target, est_name, baseline, group_col, n_folds, seed):
    def fp(Xtr, ytr, Xte):
        est = make_estimators()[est_name]
        est.fit(Xtr, ytr)
        return _probs(est, Xte)

    tab = grouped_cv_metrics(
        df, feats, target, fp, group_col=group_col,
        baseline=baseline, n_folds=n_folds, seed=seed,
    )
    return {
        "group_col": group_col,
        "summary": summarise_grouped_cv(tab, group_col),
        "folds": tab.to_dict(orient="records"),
    }


def _fmt(v, nd=3):
    return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{nd}f}"


def report(res, args) -> str:
    L = [
        f"# Diagnostics - `{args.target}`",
        "",
        f"feature mode `{args.feature_mode}` ({res['_meta']['n_features']} features), "
        f"estimator `{res['_meta']['estimator']}`, bootstrap {args.bootstrap} "
        f"clustered on `{args.bootstrap_cluster}`.",
        "",
        "## 1. Skill against progressively fairer baselines",
        "",
        "The model receives `latitude`/`longitude`, so a week-of-year-only baseline "
        "rewards it for knowing which stations bloom. `station_week` removes that.",
        "",
        "| baseline | baseline PR-AUC | model PR-AUC | PR skill | 95% CI | P(>0) |",
        "| --- | ---: | ---: | ---: | --- | ---: |",
    ]
    for b, s in res.get("baselines", {}).items():
        ci = (
            f"[{_fmt(s.get('pr_auc_skill_ci_low'))}, {_fmt(s.get('pr_auc_skill_ci_high'))}]"
            if "pr_auc_skill_ci_low" in s
            else "-"
        )
        L.append(
            f"| `{b}` | {_fmt(s['pr_auc_clim'])} | {_fmt(s['pr_auc'])} | "
            f"**{_fmt(s['pr_auc_skill'])}** | {ci} | {_fmt(s.get('pr_auc_skill_gt0'), 2)} |"
        )

    if "permutation" in res:
        L += [
            "",
            "## 2. Negative controls (labels permuted, model refit)",
            "",
            f"Skill measured against the `{args.baseline}` baseline. `global` must be ~0 "
            "or the plumbing is broken. `within_station_month` preserves station base "
            "rate and seasonality while destroying the residual SST/MHW link, so "
            "surviving skill there is real dynamical signal.",
            "",
            "| control | repeats | mean PR skill | p95 | max |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for c, s in res["permutation"].items():
            L.append(
                f"| `{c}` | {s['n_repeats']} | {_fmt(s['pr_auc_skill_mean'])} | "
                f"{_fmt(s['pr_auc_skill_p95'])} | {_fmt(s['pr_auc_skill_max'])} |"
            )
        real = res.get("baselines", {}).get(args.baseline, {}).get("pr_auc_skill")
        p95 = res["permutation"]["within_station_month"]["pr_auc_skill_p95"]
        if real is not None and np.isfinite(real) and np.isfinite(p95):
            verdict = (
                "clears the permutation ceiling"
                if real > p95
                else "**does NOT clear the permutation ceiling** - not distinguishable "
                "from station+season structure"
            )
            L += ["", f"Real PR skill {_fmt(real)} vs permuted p95 {_fmt(p95)}: {verdict}."]

    if "grouped_cv" in res:
        g = res["grouped_cv"]
        s = g["summary"]
        L += [
            "",
            f"## Generalisation to unseen `{g['group_col']}`",
            "",
            "The fixed temporal split asks whether we can forecast at a station we "
            "already monitor. Holding out whole stations asks whether we can forecast "
            "at one we have never sampled - the question a new farm site poses. The "
            "model receives lat/lon, so in-sample station identity may be carrying the "
            "skill.",
            "",
            f"- folds scored: **{s.get('n_folds_scored')}** of {s.get('n_folds_total')}",
            f"- median PR skill: **{_fmt(s.get('pr_auc_skill_median'))}** "
            f"(IQR {_fmt(s.get('pr_auc_skill_q25'))} to {_fmt(s.get('pr_auc_skill_q75'))})",
            f"- folds with positive skill: **{_fmt(s.get('frac_folds_positive'), 2)}**",
            "",
            "**The null here is not zero.** A held-out group has no station effect, "
            "so the baseline degenerates to week-of-year, and the model's smooth "
            "Fourier seasonality beats 52 independent week bins on estimator "
            "variance alone. On synthetic panels with no dynamical signal this "
            "still produced 86-93% of folds positive at a median skill of 0.03-0.07. "
            "Treat these numbers as comparable only against a permuted-label run of "
            "the same configuration, not against zero.",
        ]

    if "coverage" in res:
        L += ["", "## 3. Skill by label-window sampling coverage", ""]
        if "skipped" in res["coverage"]:
            L.append(f"_Skipped: {res['coverage']['skipped']}_")
        else:
            L += [
                "`y_*_nowcast` ORs over whichever weeks were sampled in the window, and "
                "sampling effort is seasonal. If skill only appears in the well-sampled "
                "strata, it may be tracking the sampling calendar.",
                "",
                "| weeks sampled | n | prevalence | model PR-AUC | baseline | PR skill |",
                "| ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
            for r in res["coverage"]["strata"]:
                if "note" in r:
                    L.append(f"| {r['n_obs']} | {r['n']} | - | - | - | _{r['note']}_ |")
                else:
                    L.append(
                        f"| {r['n_obs']} | {r['n']} | {_fmt(r['prevalence'])} | "
                        f"{_fmt(r['pr_auc'])} | {_fmt(r['pr_auc_clim'])} | "
                        f"**{_fmt(r['pr_auc_skill'])}** |"
                    )
    return "\n".join(L) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--joined", default=None)
    p.add_argument("--target", default="y_dinophysis_nowcast")
    p.add_argument("--feature-mode", default="strong")
    p.add_argument("--estimator", default=None, help="default: last in make_estimators()")
    p.add_argument("--baseline", default="station_week", choices=list(BASELINES))
    p.add_argument("--bootstrap", type=int, default=0)
    p.add_argument("--bootstrap-cluster", default="location_id")
    p.add_argument("--permutation-repeats", type=int, default=20)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--mode", default="all",
        choices=["all", "baselines", "permutation", "coverage", "grouped_cv"],
    )
    p.add_argument(
        "--cv-group", default="location_id",
        help="Group to hold out: location_id (leave-one-station-out, spatial "
        "transfer) or iso_year (leave-one-year-out, temporal transfer).",
    )
    p.add_argument("--cv-folds", type=int, default=None, help="Cap folds (default: all groups).")
    p.add_argument("--out-json", default="data/processed/diagnostics.json")
    p.add_argument("--out-md", default="data/processed/diagnostics_report.md")
    args = p.parse_args()

    cfg = load_config(args.config)
    path = args.joined or cfg["paths"]["joined"]
    df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    if args.target not in df.columns:
        raise SystemExit(f"target {args.target!r} not in {path}")
    feats = select_feature_mode(df, args.feature_mode)
    ests = make_estimators()
    est_name = args.estimator or list(ests)[-1]
    if est_name not in ests:
        raise SystemExit(f"estimator {est_name!r} not available; have {list(ests)}")

    res = {
        "_meta": {
            "joined": path,
            "target": args.target,
            "feature_mode": args.feature_mode,
            "n_features": len(feats),
            "estimator": est_name,
            "baseline": args.baseline,
            "bootstrap": args.bootstrap,
            "bootstrap_cluster": args.bootstrap_cluster,
        }
    }
    want = CONTROLS if args.mode == "all" else None
    if args.mode in ("all", "baselines"):
        res["baselines"] = run_baselines(
            df, feats, args.target, est_name, args.bootstrap, args.bootstrap_cluster
        )
    if args.mode in ("all", "permutation"):
        res["permutation"] = run_permutation(
            df, feats, args.target, est_name, args.baseline,
            args.permutation_repeats, args.seed,
        )
    if args.mode in ("all", "grouped_cv"):
        res["grouped_cv"] = run_grouped_cv(
            df, feats, args.target, est_name, args.baseline,
            args.cv_group, args.cv_folds, args.seed,
        )
    if args.mode in ("all", "coverage"):
        res["coverage"] = run_coverage(
            df, feats, args.target, est_name, args.baseline,
            args.bootstrap, args.bootstrap_cluster,
        )

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(res, indent=2, default=float))
    md = report(res, args)
    Path(args.out_md).write_text(md)
    print(md)
    print(f"wrote {args.out_json} and {args.out_md}")


if __name__ == "__main__":
    main()
