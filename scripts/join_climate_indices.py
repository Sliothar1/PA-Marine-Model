#!/usr/bin/env python3
"""Join NAO/EA/AMO week helper onto a HAB week panel (iso_year, iso_week).

Usage:
  .venv/bin/python scripts/join_climate_indices.py \
      --panel data/processed/joined_features.parquet \
      --out data/processed/joined_features_with_climate_indices.parquet

Does not overwrite the baseline joined_features.parquet by default.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEEK = ROOT / "data" / "processed" / "climate_indices_week.csv"
ALT_WEEK = ROOT / "data" / "external" / "climate_indices" / "processed" / "climate_indices_week.csv"


def load_week_helper(path: Path | None = None) -> pd.DataFrame:
    p = path or (DEFAULT_WEEK if DEFAULT_WEEK.exists() else ALT_WEEK)
    if not p.exists():
        raise FileNotFoundError(
            f"Missing climate week helper at {p}. Run scripts/ingest_climate_indices.py first."
        )
    w = pd.read_csv(p) if p.suffix == ".csv" else pd.read_parquet(p)
    return w


def attach_climate_indices(panel: pd.DataFrame, week: pd.DataFrame | None = None) -> pd.DataFrame:
    if week is None:
        week = load_week_helper()
    need = {"iso_year", "iso_week"}
    if not need.issubset(panel.columns):
        raise ValueError(f"panel needs {need}")
    if not need.issubset(week.columns):
        raise ValueError(f"week helper needs {need}")
    w = week.copy()
    if "week_start" in panel.columns and "week_start" in w.columns:
        w = w.drop(columns=["week_start"])
    for c in ("year", "month"):
        if c in panel.columns and c in w.columns:
            w = w.drop(columns=[c])
    # panel wins on name collisions
    w = w.drop(columns=[c for c in w.columns if c in panel.columns and c not in need])
    return panel.merge(w, on=["iso_year", "iso_week"], how="left")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", type=Path, default=ROOT / "data" / "processed" / "joined_features.parquet")
    ap.add_argument("--week", type=Path, default=None)
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "processed" / "joined_features_with_climate_indices.parquet",
    )
    args = ap.parse_args()
    panel = pd.read_parquet(args.panel) if args.panel.suffix == ".parquet" else pd.read_csv(args.panel)
    week = load_week_helper(args.week)
    out = attach_climate_indices(panel, week)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.suffix == ".parquet":
        out.to_parquet(args.out, index=False)
    else:
        out.to_csv(args.out, index=False)
    idx_cols = [c for c in out.columns if c.startswith(("nao", "ea", "amo"))]
    cov = {c: float(out[c].notna().mean()) for c in idx_cols}
    print(f"Wrote {args.out} rows={len(out)} index_cols={len(idx_cols)}")
    print("coverage_sample:", {k: round(v, 3) for k, v in list(cov.items())[:8]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
