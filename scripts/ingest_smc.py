#!/usr/bin/env python3
"""Ingest Scotland SMC annual sanitary classifications -> area lookup.

Raw file (gitignored): data/raw/smc_classifications.csv
Processed lookup: data/processed/smc_areas.csv

This is sanitary A/B/C classification, not HAB phytoplankton/toxin labels.
See data/processed/smc_note.md.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from pa_marine.smc import load_smc_classifications, write_area_lookup

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = ROOT / "data" / "raw" / "smc_classifications.csv"
DEFAULT_AREAS = ROOT / "data" / "processed" / "smc_areas.csv"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    p.add_argument("--out", type=Path, default=DEFAULT_AREAS)
    args = p.parse_args()
    if not args.raw.is_file():
        raise SystemExit(
            f"Missing {args.raw}. Place the SMC annual classification CSV there "
            "(sanitary A/B/C — not phytoplankton). HAB labels need a separate "
            "SMC phytoplankton/toxin export."
        )
    df = load_smc_classifications(args.raw)
    areas = write_area_lookup(args.raw, args.out)
    print(
        f"Loaded {len(df)} classification rows "
        f"({df['OverallStartDate'].min().date()} .. {df['OverallStartDate'].max().date()}); "
        f"wrote {len(areas)} unique areas -> {args.out}"
    )
    print(
        "NOTE: This file is annual sanitary classification only. "
        "HAB / phytoplankton / toxin labels still need a separate SMC export."
    )


if __name__ == "__main__":
    main()
