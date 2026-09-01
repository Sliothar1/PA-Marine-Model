#!/usr/bin/env python3
"""Download HAB tabledap extract (and optional tiny OISST probe)."""
from __future__ import annotations

import argparse
from pathlib import Path

from pa_marine.config import load_config
from pa_marine.hab import download_hab


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--out", default=None)
    args = p.parse_args()
    cfg = load_config(args.config)
    out = args.out or cfg["paths"]["raw_hab"]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    df = download_hab(cfg, out)
    print(f"wrote {out} n={len(df)}")


if __name__ == "__main__":
    main()
