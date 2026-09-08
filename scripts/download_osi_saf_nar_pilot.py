#!/usr/bin/env python3
"""Download OSI-202-c NAR Metop-B L3C (anonymous Ifremer FTP via curl) + station-day extract.

Pilot default: June 2023, 5 Irish HAB stations. Large .nc stay under data/raw/osi_saf/
(gitignored). Prefer ODYSSEA ARCO for gap-free week joins; this is the direct OSI SAF spine.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from pa_marine.osi_saf_sst import (
    cmr_list_granules,
    download_nar_metop_b_granules,
    extract_nar_station_day,
)

DEFAULT_STATIONS = [184, 190, 171, 216, 177]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", default="data/processed/station_week_panel.parquet")
    p.add_argument("--t0", default="2023-06-01")
    p.add_argument("--t1", default="2023-06-30")
    p.add_argument("--stations", default=",".join(map(str, DEFAULT_STATIONS)))
    p.add_argument("--out-dir", default="data/raw/osi_saf")
    p.add_argument("--max-granules", type=int, default=None)
    p.add_argument("--skip-download", action="store_true")
    p.add_argument("--max-dist-deg", type=float, default=0.5)
    args = p.parse_args()

    root = Path(".")
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    processed = root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)

    panel = pd.read_parquet(args.panel)
    ids = [int(x) for x in args.stations.split(",") if x.strip()]
    stations = (
        panel[panel["location_id"].isin(ids)]
        .drop_duplicates("location_id")[["location_id", "location_name", "latitude", "longitude"]]
        .sort_values("location_id")
        .reset_index(drop=True)
    )
    print("stations:\n", stations.to_string(index=False), flush=True)

    entries = cmr_list_granules(
        "AVHRR_SST_METOP_B_NAR-OSISAF-L3C-v1.0",
        args.t0,
        args.t1,
        bbox=(-11.0, 51.0, -5.0, 56.0),
        page_size=100,
    )
    titles = sorted({e.get("title") or "" for e in entries if e.get("title")})
    if args.max_granules:
        titles = titles[: args.max_granules]
    print(f"CMR titles={len(titles)} range={args.t0}..{args.t1}", flush=True)

    if args.skip_download:
        nc_paths = sorted(out_dir.glob("*OSISAF-L3C*AVHRR_SST_METOP_B_NAR*.nc"))
    else:
        nc_paths = download_nar_metop_b_granules(titles, out_dir)

    daily = extract_nar_station_day(
        nc_paths, stations, quality_min=3, max_dist_deg=args.max_dist_deg
    )
    if daily.empty:
        raise SystemExit("NAR extract empty — check cloud cover / max_dist_deg")

    daily = daily.merge(stations[["location_id", "location_name"]], on="location_id", how="left")
    nar_path = processed / "osi_saf_nar_station_day.parquet"
    daily.to_parquet(nar_path, index=False)
    daily.to_csv(processed / "osi_saf_nar_station_day.csv", index=False)
    print(f"wrote {nar_path} n={len(daily)} days={daily['date'].nunique()} stations={daily['location_id'].nunique()}", flush=True)

    # coverage summary
    cov = (
        daily.groupby("location_id")
        .agg(n_days=("date", "nunique"), sst_mean=("sst", "mean"), median_dist=("dist_deg", "median"))
        .reset_index()
    )
    print(cov.to_string(index=False), flush=True)

    # update sources.json beside raw (merge with existing ODYSSEA notes if present)
    sources_path = out_dir / "sources.json"
    sources = {}
    if sources_path.exists():
        sources = json.loads(sources_path.read_text())
    sources["preferred_product"] = {
        "id": "OSI-202-c",
        "ghrsst": "AVHRR_SST_METOP_B_NAR-OSISAF-L3C-v1.0",
        "url": "https://osi-saf.eumetsat.int/products/osi-202-c",
        "ftp": "ftp://ftp.ifremer.fr/ifremer/cersat/projects/osisaf/sst/l3c/north_atlantic/nar_avhrr_metop_b/",
        "https": "https://osi-saf.ifremer.fr/sst/l3c/north_atlantic/",
        "licence": "CC BY 4.0",
        "doi": "10.15770/EUM_SAF_OSI_NRT_2012",
        "status_this_box": "ok_anonymous_ftp_curl",
        "access_note": (
            "Anonymous FTP download works with curl --ftp-pasv; "
            "ftplib NLST/PASV data connections often time out; HTTPS TLS fails from this box; "
            "PO.DAAC still needs Earthdata ~/.netrc."
        ),
        "path_pattern": "nar_avhrr_metop_b/{year}/{doy:03d}/{granule}.nc",
        "cmr_manifest": "data/raw/osi_saf_sst/nar_metop_b_manifest.csv",
    }
    sources.setdefault("lane", "osi_saf_sst")
    sources["nar_pilot"] = {
        "t0": args.t0,
        "t1": args.t1,
        "station_ids": ids,
        "n_granules_downloaded": len(nc_paths),
        "n_rows": int(len(daily)),
        "n_days": int(daily["date"].nunique()),
        "n_stations": int(daily["location_id"].nunique()),
        "paths": {
            "nar_station_day": str(nar_path),
            "raw_dir": str(out_dir),
        },
    }
    sources_path.write_text(json.dumps(sources, indent=2) + "\n")
    print(f"wrote {sources_path}", flush=True)


if __name__ == "__main__":
    main()
