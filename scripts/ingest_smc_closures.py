#!/usr/bin/env python3
"""Ingest Scotland SMC toxin/E.coli area closures -> processed table.

Raw (gitignored): data/raw/smc_area_closures.csv
Processed: data/processed/smc_closures.csv
Note: data/processed/smc_closures_note.md

These are harvest area closures (OA/DTX/PTX etc.), NOT Copernicus SST.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pa_marine.smc import load_smc_area_closures, process_smc_area_closures

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = ROOT / "data" / "raw" / "smc_area_closures.csv"
DEFAULT_AREAS = ROOT / "data" / "processed" / "smc_areas.csv"
DEFAULT_OUT = ROOT / "data" / "processed" / "smc_closures.csv"
DEFAULT_NOTE = ROOT / "data" / "processed" / "smc_closures_note.md"


def write_note(out: pd.DataFrame, note_path: Path, raw_path: Path) -> None:
    n = len(out)
    n_open = int(out["is_open"].sum()) if "is_open" in out.columns else None
    n_linked = int(out["in_smc_areas"].sum()) if "in_smc_areas" in out.columns else None
    n_trig = int(out["sin_trigger_in_smc_areas"].sum()) if "sin_trigger_in_smc_areas" in out.columns else None
    dmin = out["AreaClosureStart"].min()
    dmax = out["AreaClosureStart"].max()
    tags = (
        out["toxin_tags"].value_counts().to_dict()
        if "toxin_tags" in out.columns
        else {}
    )
    pods = sorted({int(p) for p in out["Pod"].dropna().unique()}) if "Pod" in out.columns else []
    lines = [
        "# Scotland SMC area closures",
        "",
        "Generated: 2026-09-01 (Europe/Dublin).",
        "",
        "## What this is",
        "",
        "Food Standards Scotland / SMC **production-area harvest closures** driven by",
        "official-control biotoxin (mostly OA/DTX/PTX) or E. coli results — **not**",
        "Copernicus SST/ocean products and **not** annual sanitary A/B/C classification.",
        "",
        f"**Raw (gitignored):** `{raw_path.as_posix().replace(str(ROOT) + '/', '')}` — {n} closure rows.",
        "",
        f"**Processed (committed):** `data/processed/smc_closures.csv` — {n} rows,",
        "one per closure `Id`, linked to `smc_areas` on `AreaName` where possible.",
        "",
        "## Linkage",
        "",
        f"- AreaName found in `smc_areas.csv`: **{n_linked}/{n}**",
        f"- Sin parsed from Reason present in `smc_areas`: **{n_trig}/{n}**",
        "  (Reason site codes can differ from sanitary SINs — species suffix or site id.)",
        "- `Sin` column prefers Reason Sin when it exists in areas; else first AreaName Sin.",
        "- `Pod` retained from the closure export (monitoring pod).",
        "",
        "## Coverage",
        "",
        f"- Closure starts: **{dmin.date() if pd.notna(dmin) else 'n/a'} → {dmax.date() if pd.notna(dmax) else 'n/a'}**",
        f"- Still open (null AreaClosureEnd): **{n_open}**",
        f"- Pods: {pods}",
        f"- toxin_tags counts: {tags}",
        "",
        "## Rebuild",
        "",
        "```bash",
        "python scripts/ingest_smc_closures.py",
        "```",
        "",
    ]
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text("\n".join(lines))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    p.add_argument("--areas", type=Path, default=DEFAULT_AREAS)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--note", type=Path, default=DEFAULT_NOTE)
    args = p.parse_args()
    if not args.raw.is_file():
        raise SystemExit(f"Missing {args.raw}")
    areas = pd.read_csv(args.areas) if args.areas.is_file() else None
    raw = load_smc_area_closures(args.raw)
    out = process_smc_area_closures(raw, areas=areas)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Write ISO dates for CSV stability
    to_write = out.copy()
    for c in ("AreaClosureStart", "AreaClosureEnd"):
        to_write[c] = pd.to_datetime(to_write[c]).dt.strftime("%Y-%m-%d %H:%M:%S")
        to_write[c] = to_write[c].where(to_write[c].notna() & (to_write[c] != "NaT"), "")
    to_write.to_csv(args.out, index=False)
    write_note(out, args.note, args.raw)
    print(
        f"Wrote {len(out)} closures -> {args.out}; "
        f"in_smc_areas={int(out['in_smc_areas'].sum())}/{len(out)}; "
        f"note -> {args.note}"
    )


if __name__ == "__main__":
    main()
