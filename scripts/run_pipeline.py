#!/usr/bin/env python3
"""End-to-end: download → panel → mhw → join → train → evaluate.

For a dry-run on the fixture, pass --fixture.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.check_call(cmd)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", action="store_true")
    p.add_argument("--config", default="configs/default.yaml")
    args = p.parse_args()
    py = sys.executable
    if args.fixture:
        run([py, "scripts/build_panel.py", "--hab", "tests/fixtures/tiny_hab.csv", "--out", "data/processed/panel.csv"])
        run([py, "scripts/compute_mhw.py", "--panel", "data/processed/panel.csv", "--sst-in", "tests/fixtures/tiny_sst.csv", "--out", "data/processed/mhw.csv"])
        run([py, "scripts/join_features.py", "--panel", "data/processed/panel.csv", "--mhw", "data/processed/mhw.csv", "--out", "data/processed/joined.csv"])
        run([py, "scripts/evaluate.py", "--joined", "data/processed/joined.csv", "--out", "data/processed/metrics.json"])
    else:
        run([py, "scripts/download.py", "--config", args.config])
        run([py, "scripts/build_panel.py", "--config", args.config])
        run([py, "scripts/compute_mhw.py", "--config", args.config])
        run([py, "scripts/join_features.py", "--config", args.config])
        run([py, "scripts/evaluate.py", "--config", args.config])


if __name__ == "__main__":
    main()
