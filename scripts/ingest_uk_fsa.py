#!/usr/bin/env python3
"""Download / ingest England & Wales FSA phytoplankton into a parallel UK panel."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pa_marine.uk_fsa import download_fsa_csvs, load_fsa_dir, uk_station_week_panel

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default=str(ROOT / "data/raw/uk_phyto"))
    p.add_argument("--out", default=str(ROOT / "data/processed/uk_station_week_panel.parquet"))
    p.add_argument("--download", action="store_true", help="Also fetch public CSV URLs")
    p.add_argument("--summary", default=str(ROOT / "data/processed/uk_ingest_summary.json"))
    args = p.parse_args()
    raw = Path(args.raw_dir)
    if args.download or not any(raw.glob("*.csv")):
        saved = download_fsa_csvs(raw)
        print(f"downloaded {len(saved)} files -> {raw}")
    samples = load_fsa_dir(raw)
    panel = uk_station_week_panel(samples)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(args.out, index=False)
    summary = {
        "n_sample_rows": int(len(samples)),
        "n_station_weeks": int(len(panel)),
        "n_locations": int(panel["location_id"].nunique()),
        "date_min": str(samples["date"].min()),
        "date_max": str(samples["date"].max()),
        "dino_rate": float(panel["y_dinophysis"].mean()),
        "pn_rate": float(panel["y_pseudo_nitzschia"].mean()),
        "frac_with_coords": float(panel["latitude"].notna().mean()),
        "out": args.out,
        "note": (
            "Dinophysiaceae (DSP family) used as Dinophysis proxy at 100 cells/L; "
            "Pseudo-nitzschia at 50,000 cells/L. Parallel UK panel only — not merged "
            "into Irish training yet."
        ),
    }
    Path(args.summary).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
