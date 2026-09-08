#!/usr/bin/env python3
"""Join MBA CPR features onto Irish HAB station-weeks + best-effort ablation.

Join / eval protocol (International HAB Dev — follow exactly):
  1. Primary: AOI × ISO-week aggregates left-joined to station-weeks
  2. Optional: nearest CPR same ISO week within ≤100 km haversine
  3. Ablate strong vs strong+CPR_AOI vs strong+CPR_nearest100;
     report coverage %; never use HAB labels as CPR features.

Usage:
  .venv/bin/python scripts/join_cpr_hab_week.py
  .venv/bin/python scripts/join_cpr_hab_week.py --skip-ablation
  .venv/bin/python scripts/join_cpr_hab_week.py --skip-nearest

If HAB feature table is missing, writes a blocker doc and exits 0.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
JOINED = PROC / "joined_features.parquet"
CPR_SAMPLES = PROC / "cpr_samples.parquet"
CPR_AOI_WEEK = PROC / "cpr_aoi_week.csv"
OUT_JOINED = PROC / "joined_features_with_cpr.parquet"
OUT_COV = PROC / "cpr_join_coverage.json"
OUT_METRICS = PROC / "cpr_ablation_metrics.json"
OUT_MD = PROC / "cpr_ablation_report.md"
BLOCKER = PROC / "cpr_join_blocker.md"
TARGET = "y_dinophysis_nowcast"
MAX_KM = 100.0

# Prefer more specific boxes; skip optional connemara (0 tows) for primary join key
PRIMARY_AOI_PREF = [
    "irish_sea",
    "western_shelf",
    "malin",
    "celtic",
    "shelf_break",
    "scotland",
    "total_box",
]

AOIS = {
    "western_shelf": (52.5, 55.0, -11.5, -9.0),
    "celtic": (49.5, 52.0, -10.5, -5.5),
    "irish_sea": (52.5, 54.5, -6.2, -3.2),
    "shelf_break": (51.0, 55.0, -15.0, -11.5),
    "malin": (54.5, 55.8, -8.0, -4.5),
    "scotland": (54.75, 60.76, -7.5, -0.83),
    "connemara": (53.2, 53.7, -10.2, -9.4),
    "total_box": (49.5, 60.76, -15.0, -0.83),
}

CPR_AOI_FEATS = [
    "cpr_aoi_n_samples",
    "cpr_aoi_mean_large_copepods",
    "cpr_aoi_mean_small_copepods",
    "cpr_aoi_mean_diatoms",
    "cpr_aoi_mean_dinoflagellates",
    "cpr_aoi_pci",
    "cpr_aoi_dino_diatom_ratio",
]
CPR_NEAR_FEATS = [
    "cpr_near_dist_km",
    "cpr_near_mean_large_copepods",
    "cpr_near_mean_small_copepods",
    "cpr_near_mean_diatoms",
    "cpr_near_mean_dinoflagellates",
    "cpr_near_pci",
]


def _in_box(lat: float, lon: float, box: tuple[float, float, float, float]) -> bool:
    lat0, lat1, lon0, lon1 = box
    return lat0 <= lat <= lat1 and lon0 <= lon <= lon1


def assign_primary_aoi(lat: float, lon: float) -> str | None:
    for name in PRIMARY_AOI_PREF:
        if _in_box(lat, lon, AOIS[name]):
            return name
    return None


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2.0) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def write_blocker(reason: str, missing: list[str]) -> None:
    text = f"""# CPR HAB join blocker

**Generated:** {datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")}
**Status:** blocked — cannot run AOI / nearest join or CPR ablation.

## Reason

{reason}

## Missing paths

{chr(10).join(f"- `{p}`" for p in missing)}

## How to unblock

1. Ensure Irish HAB week feature table exists at `data/processed/joined_features.parquet`
   (pipeline: ingest HAB → MHW → `scripts/join_features.py`).
2. Run `scripts/ingest_cpr_mba.py` to build `cpr_samples.parquet` + `cpr_aoi_week.csv`.
3. Re-run `scripts/join_cpr_hab_week.py`.

CPR aggregates are **not** Dinophysis labels (Ceratium-heavy dino list). Never train on HAB counts as CPR features.
"""
    BLOCKER.write_text(text)
    print(f"Wrote blocker: {BLOCKER}")


def attach_aoi(panel: pd.DataFrame, aoi_week: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    st = (
        out.groupby("location_id", as_index=False)
        .agg(latitude=("latitude", "first"), longitude=("longitude", "first"))
    )
    st["cpr_aoi"] = [
        assign_primary_aoi(float(a), float(b)) for a, b in zip(st["latitude"], st["longitude"])
    ]
    out = out.merge(st[["location_id", "cpr_aoi"]], on="location_id", how="left")

    aw = aoi_week.copy()
    rename = {
        "n_samples": "cpr_aoi_n_samples",
        "cpr_mean_large_copepods": "cpr_aoi_mean_large_copepods",
        "cpr_mean_small_copepods": "cpr_aoi_mean_small_copepods",
        "cpr_mean_diatoms": "cpr_aoi_mean_diatoms",
        "cpr_mean_dinoflagellates": "cpr_aoi_mean_dinoflagellates",
        "cpr_pci": "cpr_aoi_pci",
        "cpr_dino_diatom_ratio": "cpr_aoi_dino_diatom_ratio",
    }
    keep = ["aoi", "iso_year", "iso_week"] + [c for c in rename if c in aw.columns]
    aw = aw[keep].rename(columns=rename)
    aw = aw.rename(columns={"aoi": "cpr_aoi"})
    out = out.merge(aw, on=["cpr_aoi", "iso_year", "iso_week"], how="left")
    return out


def attach_nearest(panel: pd.DataFrame, samples: pd.DataFrame, max_km: float = MAX_KM) -> pd.DataFrame:
    """Nearest CPR sample in the same ISO week within max_km."""
    out = panel.copy()
    for c in CPR_NEAR_FEATS:
        out[c] = np.nan

    cpr = samples.dropna(subset=["iso_year", "iso_week", "latitude", "longitude"]).copy()
    cpr["iso_year"] = cpr["iso_year"].astype(int)
    cpr["iso_week"] = cpr["iso_week"].astype(int)

    week_groups = {key: grp for key, grp in cpr.groupby(["iso_year", "iso_week"], sort=False)}

    near_cols = [
        "cpr_mean_large_copepods",
        "cpr_mean_small_copepods",
        "cpr_mean_diatoms",
        "cpr_mean_dinoflagellates",
        "cpr_pci",
    ]

    dist_all = np.full(len(out), np.nan)
    vals = {c: np.full(len(out), np.nan) for c in near_cols}

    iy = out["iso_year"].to_numpy()
    iw = out["iso_week"].to_numpy()
    plat = out["latitude"].to_numpy(dtype=float)
    plon = out["longitude"].to_numpy(dtype=float)

    week_to_rows: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, (y, w) in enumerate(zip(iy, iw)):
        if pd.isna(y) or pd.isna(w):
            continue
        week_to_rows[(int(y), int(w))].append(i)

    for key, rows in week_to_rows.items():
        grp = week_groups.get(key)
        if grp is None or grp.empty:
            continue
        clat = grp["latitude"].to_numpy(dtype=float)
        clon = grp["longitude"].to_numpy(dtype=float)
        crow = grp
        for i in rows:
            d = haversine_km(plat[i], plon[i], clat, clon)
            j = int(np.nanargmin(d))
            best = float(d[j])
            if best <= max_km:
                dist_all[i] = best
                row = crow.iloc[j]
                for c in near_cols:
                    vals[c][i] = row[c]

    out["cpr_near_dist_km"] = dist_all
    out["cpr_near_mean_large_copepods"] = vals["cpr_mean_large_copepods"]
    out["cpr_near_mean_small_copepods"] = vals["cpr_mean_small_copepods"]
    out["cpr_near_mean_diatoms"] = vals["cpr_mean_diatoms"]
    out["cpr_near_mean_dinoflagellates"] = vals["cpr_mean_dinoflagellates"]
    out["cpr_near_pci"] = vals["cpr_pci"]
    return out


def coverage_report(df: pd.DataFrame) -> dict:
    cov = {
        "n_rows": int(len(df)),
        "n_locations": int(df["location_id"].nunique()) if "location_id" in df.columns else None,
        "aoi_assignment": {},
        "coverage_pct": {},
    }
    if "cpr_aoi" in df.columns:
        cov["aoi_assignment"] = {str(k): int(v) for k, v in df["cpr_aoi"].value_counts(dropna=False).items()}
    for c in CPR_AOI_FEATS + CPR_NEAR_FEATS:
        if c in df.columns:
            cov["coverage_pct"][c] = round(float(df[c].notna().mean()) * 100.0, 3)
    if "cpr_aoi_pci" in df.columns:
        cov["coverage_pct"]["any_cpr_aoi"] = round(float(df["cpr_aoi_pci"].notna().mean()) * 100.0, 3)
    if "cpr_near_pci" in df.columns:
        cov["coverage_pct"]["any_cpr_nearest100"] = round(float(df["cpr_near_pci"].notna().mean()) * 100.0, 3)
    return cov


def _lgbm():
    from lightgbm import LGBMClassifier

    return LGBMClassifier(
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        class_weight="balanced",
        verbosity=-1,
    )


def _raw_probs(est, X) -> np.ndarray:
    return est.predict_proba(X)[:, 1]


def eval_feature_set(df: pd.DataFrame, feats: list[str], label: str) -> dict:
    from pa_marine.calibration import ProbCalibrator
    from pa_marine.metrics import climatology_probs, summarise
    from pa_marine.models import make_estimators

    train = df[df["split"] == "train"]
    val = df[df["split"] == "val"]
    test = df[df["split"] == "test"]
    ytr = train[TARGET].astype(int)
    mtr = ytr.notna()
    Xtr = train.loc[mtr, feats].fillna(0.0)
    ytr = ytr.loc[mtr]
    clim_week = train.loc[mtr, "iso_week"].to_numpy()
    clim_y = ytr.to_numpy()

    estimators = {"lightgbm": _lgbm(), "logreg": make_estimators()["logreg"]}
    for est in estimators.values():
        est.fit(Xtr, ytr)

    out: dict = {
        "label": label,
        "n_features": len(feats),
        "features": feats,
        "n_train": int(mtr.sum()),
        "n_val": int(val[TARGET].notna().sum()),
        "n_test": int(test[TARGET].notna().sum()),
        "feature_coverage_train_pct": {
            f: round(float(train.loc[mtr, f].notna().mean()) * 100.0, 3)
            for f in feats
            if f in train.columns
        },
    }
    for name, model in estimators.items():
        yv = val[TARGET].astype(int)
        mv = yv.notna()
        pr_val = _raw_probs(model, val.loc[mv, feats].fillna(0.0))
        cal = ProbCalibrator(method="auto").fit(yv.loc[mv].to_numpy(), pr_val)
        for split_name, ev in (("val", val), ("test", test)):
            y = ev[TARGET].astype(int)
            mask = y.notna()
            pr_raw = _raw_probs(model, ev.loc[mask, feats].fillna(0.0))
            clim = climatology_probs(clim_week, clim_y, ev.loc[mask, "iso_week"].to_numpy())
            y_np = y.loc[mask].to_numpy()
            raw = summarise(y_np, pr_raw, clim)
            pr_cal = cal.transform(pr_raw)
            cal_s = summarise(y_np, pr_cal, clim)
            out[f"{name}_{split_name}_raw"] = raw
            out[f"{name}_{split_name}_cal"] = {**cal_s, "calibration_method": cal.chosen_}
    return out


def run_ablation(df: pd.DataFrame) -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from pa_marine.features import STRONG_OISST

    strong = [f for f in STRONG_OISST if f in df.columns]
    aoi_feats = [f for f in CPR_AOI_FEATS if f in df.columns]
    near_feats = [f for f in CPR_NEAR_FEATS if f in df.columns]
    sets = [
        (strong, "strong"),
        (strong + aoi_feats, "strong+CPR_AOI"),
        (strong + near_feats, "strong+CPR_nearest100"),
        (strong + aoi_feats + near_feats, "strong+CPR_AOI+nearest100"),
    ]
    results = []
    t0 = time.time()
    for feats, label in sets:
        print(f"Ablating {label} ({len(feats)} feats)...")
        results.append(eval_feature_set(df, feats, label))
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": TARGET,
        "protocol": [
            "AOI x ISO-week left-join to station-weeks",
            "nearest CPR same ISO week <=100 km haversine",
            "ablate strong vs +CPR_AOI vs +CPR_nearest100; coverage %; never HAB labels",
        ],
        "elapsed_s": round(time.time() - t0, 1),
        "results": results,
    }


def write_ablation_md(metrics: dict, cov: dict) -> None:
    lines = [
        "# CPR MBA ablation vs strong Dinophysis baseline",
        "",
        f"**Generated:** {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M %Z')}  ",
        f"**Target:** `{TARGET}`  ",
        "**Protocol:** AOI x ISO-week left-join; optional nearest <=100 km same ISO week; "
        "never HAB labels as CPR features.",
        "",
        "## Coverage",
        "",
        "| Feature / set | Coverage % |",
        "| --- | ---: |",
    ]
    for k, v in cov.get("coverage_pct", {}).items():
        lines.append(f"| `{k}` | {v} |")
    lines += [
        "",
        "## Results (LightGBM calibrated test PR-AUC)",
        "",
        "| Setting | n_feat | test PR-AUC | clim | PR skill | Brier skill |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in metrics.get("results", []):
        cal = r.get("lightgbm_test_cal", {})
        lines.append(
            f"| {r['label']} | {r['n_features']} | {cal.get('pr_auc', float('nan')):.4f} | "
            f"{cal.get('clim_pr_auc', float('nan')):.4f} | {cal.get('pr_skill', float('nan')):.4f} | "
            f"{cal.get('brier_skill', float('nan')):.4f} |"
        )
    lines += [
        "",
        "## Caveats",
        "",
        "- CPR `Mean_Dinoflagellates` is **not** Dinophysis (Ceratium-heavy aggregate).",
        "- Connemara AOI has **0** CPR tows; stations there join via `western_shelf` / other primary AOI.",
        "- Sparse western_shelf CPR (few tows) -> low AOI coverage for west-coast stations.",
        "- Nearest-100 km join is best-effort and week-sparse offshore.",
        "",
        f"Metrics JSON: `{OUT_METRICS.relative_to(ROOT)}`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", type=Path, default=JOINED)
    ap.add_argument("--samples", type=Path, default=CPR_SAMPLES)
    ap.add_argument("--aoi-week", type=Path, default=CPR_AOI_WEEK)
    ap.add_argument("--out", type=Path, default=OUT_JOINED)
    ap.add_argument("--skip-nearest", action="store_true")
    ap.add_argument("--skip-ablation", action="store_true")
    ap.add_argument("--max-km", type=float, default=MAX_KM)
    args = ap.parse_args()

    missing = [str(p) for p in (args.panel, args.samples, args.aoi_week) if not p.exists()]
    if missing:
        reason = "Required HAB panel and/or CPR ingest outputs are missing."
        if not args.panel.exists():
            reason = (
                "HAB feature table missing (`joined_features.parquet`). "
                "CPR ingest may still be OK; join/ablation cannot proceed without station-weeks."
            )
        write_blocker(reason, missing)
        return 0

    if BLOCKER.exists():
        BLOCKER.unlink()

    panel = pd.read_parquet(args.panel) if args.panel.suffix == ".parquet" else pd.read_csv(args.panel)
    aoi_week = pd.read_csv(args.aoi_week)
    samples = (
        pd.read_parquet(args.samples) if args.samples.suffix == ".parquet" else pd.read_csv(args.samples)
    )

    print(f"Panel rows={len(panel)}; CPR samples={len(samples)}; AOI-week rows={len(aoi_week)}")
    out = attach_aoi(panel, aoi_week)
    if not args.skip_nearest:
        print(f"Attaching nearest CPR <={args.max_km} km (same ISO week)...")
        t0 = time.time()
        out = attach_nearest(out, samples, max_km=args.max_km)
        print(f"Nearest join done in {time.time() - t0:.1f}s")
    else:
        for c in CPR_NEAR_FEATS:
            out[c] = np.nan

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    cov = coverage_report(out)
    cov["outputs"] = {"joined": str(args.out.relative_to(ROOT))}
    OUT_COV.write_text(json.dumps(cov, indent=2) + "\n")
    print("Coverage %:", cov["coverage_pct"])
    print(f"Wrote {args.out}")

    if not args.skip_ablation:
        try:
            metrics = run_ablation(out)
            metrics["coverage"] = cov
            OUT_METRICS.write_text(json.dumps(metrics, indent=2) + "\n")
            write_ablation_md(metrics, cov)
            print(f"Wrote {OUT_METRICS} and {OUT_MD}")
        except Exception as e:  # noqa: BLE001
            err = PROC / "cpr_ablation_blocker.md"
            err.write_text(
                f"# CPR ablation blocker\n\nJoin succeeded but ablation failed:\n\n```\n{e}\n```\n"
            )
            print(f"Ablation failed: {e} -> {err}")
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
