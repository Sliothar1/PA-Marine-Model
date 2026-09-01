#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pa_marine.config import load_config
from pa_marine.features import join_week_panel


def _read(path):
    return pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--panel", default=None)
    p.add_argument("--mhw", default=None)
    p.add_argument("--out", default=None)
    args = p.parse_args()
    cfg = load_config(args.config)
    panel = _read(args.panel or cfg["paths"]["panel"])
    mhw = _read(args.mhw or cfg["paths"]["mhw"])
    joined = join_week_panel(panel, mhw)
    out = args.out or cfg["paths"]["joined"]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    joined.to_parquet(out, index=False) if out.endswith(".parquet") else joined.to_csv(out, index=False)
    print(f"wrote {out} n={len(joined)}")


if __name__ == "__main__":
    main()
