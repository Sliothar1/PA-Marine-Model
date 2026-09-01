#!/usr/bin/env python3
"""Ingest Scotland SMC phytoplankton + biotoxin HAB CSVs → station-week panels.

Raw (gitignored):
  data/raw/smc_phytoplankton.csv
  data/raw/smc_biotoxins.csv

Processed:
  data/processed/smc_station_week_panel.parquet   (phyto; no lat/lon yet)
  data/processed/smc_toxin_station_week_panel.parquet
  data/processed/smc_hab_ingest_summary.json
  data/processed/smc_hab_report.md

Joins sanitary area lookup (smc_areas.csv) on Sin. Geocode Sin→coords before SST.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from pa_marine.smc import (
    load_smc_biotoxins,
    load_smc_phytoplankton,
    smc_phyto_station_week_panel,
    smc_toxin_station_week_panel,
    summarize_phyto_panel,
    unique_areas,
    load_smc_classifications,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PHYTO = ROOT / "data" / "raw" / "smc_phytoplankton.csv"
DEFAULT_TOXIN = ROOT / "data" / "raw" / "smc_biotoxins.csv"
DEFAULT_CLASS = ROOT / "data" / "raw" / "smc_classifications.csv"
DEFAULT_AREAS = ROOT / "data" / "processed" / "smc_areas.csv"
DEFAULT_PHYTO_PANEL = ROOT / "data" / "processed" / "smc_station_week_panel.parquet"
DEFAULT_TOXIN_PANEL = ROOT / "data" / "processed" / "smc_toxin_station_week_panel.parquet"
DEFAULT_SUMMARY = ROOT / "data" / "processed" / "smc_hab_ingest_summary.json"
DEFAULT_REPORT = ROOT / "data" / "processed" / "smc_hab_report.md"


def _load_areas(areas_path: Path, class_path: Path) -> pd.DataFrame:
    if areas_path.is_file():
        return pd.read_csv(areas_path)
    if class_path.is_file():
        return unique_areas(load_smc_classifications(class_path))
    return pd.DataFrame(columns=["AreaName", "Sin", "LocalAuthorityName"])


def _write_report(summary: dict, path: Path) -> None:
    phy = summary.get("phytoplankton", {})
    tox = summary.get("biotoxins", {})
    lines = [
        "# Scotland SMC HAB ingest",
        "",
        f"Generated: {summary.get('generated')} (Europe/Dublin).",
        "",
        "## Phytoplankton station-week panel",
        "",
        f"- Raw rows: **{phy.get('n_raw_rows')}** → `data/raw/smc_phytoplankton.csv`",
        f"- Station-weeks: **{phy.get('n_station_weeks')}**",
        f"- Unique SINs (sites): **{phy.get('n_sites_sin')}**",
        f"- Unique AreaName: **{phy.get('n_area_names')}**",
        f"- Week span: **{phy.get('date_min')} → {phy.get('date_max')}**",
        f"- Dinophysis ≥100 prevalence: **{phy.get('prevalence_dinophysis_ge100'):.4f}**"
        if phy.get("prevalence_dinophysis_ge100") is not None
        else "- Dinophysis prevalence: n/a",
        f"- Pseudo-nitzschia ≥50,000 prevalence: **{phy.get('prevalence_pseudo_nitzschia_ge50000'):.4f}**"
        if phy.get("prevalence_pseudo_nitzschia_ge50000") is not None
        else "- Pseudo-nitzschia prevalence: n/a",
        f"- Alexandrium ≥40 prevalence: **{phy.get('prevalence_alexandrium_ge40'):.4f}**"
        if phy.get("prevalence_alexandrium_ge40") is not None
        else "- Alexandrium prevalence: n/a",
        f"- Fraction of station-weeks with Sin in `smc_areas.csv`: **{phy.get('frac_sin_in_smc_areas'):.3f}**"
        if phy.get("frac_sin_in_smc_areas") is not None
        else "",
        "",
        "## Coordinates / SST",
        "",
        "**No lat/lon in the SMC HAB export.** The first panel leaves `latitude`/`longitude` null.",
        "Geocode `Sin` → WGS84 coords (e.g. from FSS production-area GIS) before joining OISST/OSTIA.",
        "",
        "## Biotoxins station-week panel",
        "",
        f"- Raw rows: **{tox.get('n_raw_rows')}** → `data/raw/smc_biotoxins.csv`",
        f"- Station-weeks: **{tox.get('n_station_weeks')}**",
        f"- Unique SINs: **{tox.get('n_sites_sin')}**",
        f"- Week span: **{tox.get('date_min')} → {tox.get('date_max')}**",
        f"- DSP (OA+DTX+PTX ≥160) prevalence: **{tox.get('prevalence_dsp'):.4f}**"
        if tox.get("prevalence_dsp") is not None
        else "",
        f"- ASP (≥20) prevalence: **{tox.get('prevalence_asp'):.4f}**"
        if tox.get("prevalence_asp") is not None
        else "",
        f"- PSP (≥800) prevalence: **{tox.get('prevalence_psp'):.4f}**"
        if tox.get("prevalence_psp") is not None
        else "",
        "",
        "Raw CSVs stay gitignored under `data/raw/`. Parquet panels are gitignored; this report + JSON summary are committed.",
        "",
        "## Rebuild",
        "",
        "```bash",
        "python scripts/ingest_smc_hab.py",
        "```",
        "",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phyto", type=Path, default=DEFAULT_PHYTO)
    p.add_argument("--toxin", type=Path, default=DEFAULT_TOXIN)
    p.add_argument("--classifications", type=Path, default=DEFAULT_CLASS)
    p.add_argument("--areas", type=Path, default=DEFAULT_AREAS)
    p.add_argument("--phyto-out", type=Path, default=DEFAULT_PHYTO_PANEL)
    p.add_argument("--toxin-out", type=Path, default=DEFAULT_TOXIN_PANEL)
    p.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = p.parse_args()

    if not args.phyto.is_file():
        raise SystemExit(f"Missing {args.phyto}")
    if not args.toxin.is_file():
        raise SystemExit(f"Missing {args.toxin}")

    areas = _load_areas(args.areas, args.classifications)
    phy = load_smc_phytoplankton(args.phyto)
    phyto_panel = smc_phyto_station_week_panel(phy, areas=areas)
    args.phyto_out.parent.mkdir(parents=True, exist_ok=True)
    phyto_panel.to_parquet(args.phyto_out, index=False)

    tox = load_smc_biotoxins(args.toxin)
    toxin_panel = smc_toxin_station_week_panel(tox, areas=areas)
    toxin_panel.to_parquet(args.toxin_out, index=False)

    phy_sum = summarize_phyto_panel(phyto_panel, n_raw=len(phy))
    tox_sum = {
        "n_raw_rows": int(len(tox)),
        "n_station_weeks": int(len(toxin_panel)),
        "n_sites_sin": int(toxin_panel["location_id"].nunique()),
        "date_min": str(toxin_panel["week_start"].min().date()) if len(toxin_panel) else None,
        "date_max": str(toxin_panel["week_start"].max().date()) if len(toxin_panel) else None,
        "prevalence_dsp": float(toxin_panel["y_dsp"].mean()) if len(toxin_panel) else None,
        "prevalence_asp": float(toxin_panel["y_asp"].mean()) if len(toxin_panel) else None,
        "prevalence_psp": float(toxin_panel["y_psp"].mean()) if len(toxin_panel) else None,
        "prevalence_aza": float(toxin_panel["y_aza"].mean()) if len(toxin_panel) else None,
        "prevalence_ytx": float(toxin_panel["y_ytx"].mean()) if len(toxin_panel) else None,
        "frac_sin_in_smc_areas": float(toxin_panel["in_smc_areas"].mean())
        if len(toxin_panel)
        else None,
        "thresholds": {
            "dsp_ug_oa_eq_kg": 160.0,
            "asp_mg_kg": 20.0,
            "psp_ug_stx_eq_kg": 800.0,
            "aza_ug_kg": 160.0,
            "ytx_mg_kg": 3.75,
        },
    }
    summary = {
        "generated": "2026-09-01",
        "phytoplankton": phy_sum,
        "biotoxins": tox_sum,
        "outputs": {
            "phyto_panel": str(args.phyto_out),
            "toxin_panel": str(args.toxin_out),
            "areas_lookup": str(args.areas),
        },
    }
    args.summary.write_text(json.dumps(summary, indent=2))
    _write_report(summary, args.report)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
