#!/usr/bin/env python3
"""Geocode Scotland SMC sites → data/processed/smc_site_coords.csv and merge into phyto panel.

Sources (priority):
  1. OSGB grid refs in smc_closures.csv Descriptions
  2. SEPA Shellfish Water Protected Areas centroids (public ArcGIS REST)
  3. Nominatim AreaName, Scotland, UK (rate-limited)

FSS classified-areas WFS currently 401 without login — skipped.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import urllib3

from pa_marine.smc_geocode import (
    apply_coords_to_panel,
    build_site_coords,
    coverage_stats,
    load_sepa_swpa_centroids,
)

urllib3.disable_warnings()

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AREAS = ROOT / "data" / "processed" / "smc_areas.csv"
DEFAULT_CLOSURES = ROOT / "data" / "processed" / "smc_closures.csv"
DEFAULT_PHYTO_PANEL = ROOT / "data" / "processed" / "smc_station_week_panel.parquet"
DEFAULT_PHYTO_RAW = ROOT / "data" / "raw" / "smc_phytoplankton.csv"
DEFAULT_SEPA_JSON = ROOT / "data" / "raw" / "sepa_swpa.json"
DEFAULT_SEPA_CSV = ROOT / "data" / "processed" / "sepa_swpa_centroids.csv"
DEFAULT_COORDS = ROOT / "data" / "processed" / "smc_site_coords.csv"
DEFAULT_SUMMARY = ROOT / "data" / "processed" / "smc_geocode_summary.json"
DEFAULT_REPORT = ROOT / "data" / "processed" / "smc_geocode_report.md"
DEFAULT_NOM_CACHE = ROOT / "data" / "raw" / "nominatim_smc_cache.json"
SEPA_REST = (
    "https://map.sepa.org.uk/server/rest/services/Open/Regulation_Zones/"
    "MapServer/12/query"
)


def _download_sepa(out_json: Path) -> Path:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "false",
        "outSR": "4326",
        "f": "json",
        "resultRecordCount": 500,
    }
    r = requests.get(SEPA_REST, params=params, timeout=120, verify=False)
    r.raise_for_status()
    out_json.write_text(r.text)
    return out_json


def _sepa_to_csv(sepa_json: Path, out_csv: Path) -> pd.DataFrame:
    sepa = load_sepa_swpa_centroids(sepa_json)
    thin = sepa[["site", "latitude", "longitude", "pa_id"]].copy()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    thin.to_csv(out_csv, index=False)
    return sepa


def _load_sites(phyto_panel: Path, phyto_raw: Path, areas: Path) -> pd.DataFrame:
    if phyto_panel.is_file():
        p = pd.read_parquet(phyto_panel)
        cols = [c for c in ("Sin", "AreaName", "SiteName", "LocalAuthorityName") if c in p.columns]
        return p[cols].drop_duplicates("Sin").reset_index(drop=True)
    if phyto_raw.is_file():
        p = pd.read_csv(phyto_raw, usecols=lambda c: c in {"Sin", "AreaName", "SiteName", "LocalAuthorityName"})
        return p.drop_duplicates("Sin").reset_index(drop=True)
    a = pd.read_csv(areas)
    a["SiteName"] = pd.NA
    return a


def _write_report(summary: dict, path: Path) -> None:
    cov = summary.get("coverage", {})
    lines = [
        "# Scotland SMC site geocoding",
        "",
        f"Generated: {summary.get('generated')} (Europe/Dublin).",
        "",
        "## Coverage",
        "",
        f"- Panel SINs with coords: **{cov.get('n_panel_sins_with_coords')}/{cov.get('n_panel_sins')}** "
        f"({cov.get('pct_panel_sins_with_coords')}%)",
        f"- Panel rows with coords: **{cov.get('n_panel_rows_with_coords')}/{cov.get('n_panel_rows')}** "
        f"({cov.get('pct_panel_rows_with_coords')}%)",
        f"- Coord rows with lat/lon: **{cov.get('n_coords_with_latlon')}/{cov.get('n_coord_rows')}**",
        f"- By source: `{cov.get('coords_by_source')}`",
        f"- By confidence: `{cov.get('coords_by_confidence')}`",
        f"- Missing panel SINs: **{cov.get('n_panel_sins_missing_coords')}**",
        "",
        "## Sources",
        "",
        "1. **osgb_closure** — OSGB grid refs parsed from `smc_closures.csv` Description → WGS84 mean (high).",
        "2. **sepa_swpa** — SEPA Shellfish Water Protected Areas centroids (public REST; name match).",
        "3. **nominatim** — OpenStreetMap Nominatim `{AreaName}, Scotland, UK` (rate-limited; many lochs ambiguous → low).",
        "",
        f"**FSS GIS:** {cov.get('fss_wfs_note')}",
        "",
        "## Caveats",
        "",
        "- Many Scottish loch / voe names are ambiguous; Nominatim hits marked `confidence=low` when multiple hits or low importance.",
        "- Closure OSGB polygons cover only recent closed areas (small subset of SINs).",
        "- SEPA SWPAs are designated waters, not 1:1 with FSS production-area SINs.",
        "",
        "## Rebuild",
        "",
        "```bash",
        "python scripts/geocode_smc_sites.py",
        "```",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--areas", type=Path, default=DEFAULT_AREAS)
    ap.add_argument("--closures", type=Path, default=DEFAULT_CLOSURES)
    ap.add_argument("--phyto-panel", type=Path, default=DEFAULT_PHYTO_PANEL)
    ap.add_argument("--phyto-raw", type=Path, default=DEFAULT_PHYTO_RAW)
    ap.add_argument("--sepa-json", type=Path, default=DEFAULT_SEPA_JSON)
    ap.add_argument("--sepa-csv", type=Path, default=DEFAULT_SEPA_CSV)
    ap.add_argument("--coords-out", type=Path, default=DEFAULT_COORDS)
    ap.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    ap.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--nominatim-cache", type=Path, default=DEFAULT_NOM_CACHE)
    ap.add_argument("--no-nominatim", action="store_true")
    ap.add_argument("--no-panel-update", action="store_true")
    ap.add_argument("--sleep", type=float, default=1.1)
    args = ap.parse_args()

    sites = _load_sites(args.phyto_panel, args.phyto_raw, args.areas)
    closures = pd.read_csv(args.closures) if args.closures.is_file() else pd.DataFrame()

    if not args.sepa_json.is_file():
        print(f"Downloading SEPA SWPA → {args.sepa_json}")
        _download_sepa(args.sepa_json)
    sepa = _sepa_to_csv(args.sepa_json, args.sepa_csv)
    print(f"SEPA SWPA sites: {len(sepa)}")

    nom_cache: dict = {}
    if args.nominatim_cache.is_file():
        nom_cache = json.loads(args.nominatim_cache.read_text())
        print(f"Loaded Nominatim cache: {len(nom_cache)} entries")

    coords = build_site_coords(
        sites,
        closures=closures,
        sepa=sepa,
        nominatim_cache=nom_cache,
        use_nominatim=not args.no_nominatim,
        nominatim_sleep_s=args.sleep,
    )
    args.coords_out.parent.mkdir(parents=True, exist_ok=True)
    coords.to_csv(args.coords_out, index=False)
    print(f"Wrote {args.coords_out} ({len(coords)} rows)")

    args.nominatim_cache.parent.mkdir(parents=True, exist_ok=True)
    # serialize cache (skip non-jsonables)
    slim = {k: v for k, v in nom_cache.items()}
    args.nominatim_cache.write_text(json.dumps(slim, indent=2))

    panel = None
    if args.phyto_panel.is_file() and not args.no_panel_update:
        panel = pd.read_parquet(args.phyto_panel)
        panel2 = apply_coords_to_panel(panel, coords)
        panel2.to_parquet(args.phyto_panel, index=False)
        print(
            f"Updated panel coords: has_coords={int(panel2['has_coords'].sum())}/{len(panel2)}"
        )
        cov = coverage_stats(panel2, coords)
    else:
        cov = coverage_stats(
            sites.assign(**{c: None for c in []}),
            coords,
        )
        # minimal coverage from sites alone
        cov = coverage_stats(
            pd.DataFrame({"Sin": sites["Sin"]}),
            coords,
        )

    generated = datetime.now(ZoneInfo("Europe/Dublin")).strftime("%Y-%m-%d %H:%M %Z")
    summary = {
        "generated": generated,
        "n_sites_input": int(len(sites)),
        "n_sepa": int(len(sepa)),
        "n_closures": int(len(closures)),
        "coverage": cov,
        "coords_path": str(args.coords_out.relative_to(ROOT)),
    }
    args.summary_out.write_text(json.dumps(summary, indent=2))
    _write_report(summary, args.report_out)
    print(json.dumps(cov, indent=2))


if __name__ == "__main__":
    main()
