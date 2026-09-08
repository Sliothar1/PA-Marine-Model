#!/usr/bin/env python3
"""Pilot ingest: ODYSSEA L4 SST (OSI SAF fallback) via anonymous ARCO zarr.

Preferred OSI-202-c (Ifremer FTP/HTTPS + PO.DAAC) is blocked from this box
(TLS EOF / FTP timeout / Earthdata 401). ODYSSEA product
SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025 is the locked CMEMS fallback and is
readable anonymously from CloudFerro ARCO.

Writes:
  data/raw/osi_saf/sources.json
  data/raw/osi_saf/odyssea_irish_YYYYMM_bbox.nc  (optional --bbox)
  data/raw/odyssea_daily.parquet
  data/processed/osi_saf_station_day.parquet
  data/processed/osi_saf_odyssea_pilot_status.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from pa_marine.osi_saf_sst import (
    ODYSSEA_META,
    download_odyssea_for_stations,
    write_odyssea_bbox_netcdf,
)

# ~5 HAB stations reused from OISST/HAB panel (west + SW + Connemara)
DEFAULT_STATIONS = [184, 190, 171, 216, 177]  # Glenbeigh, Tahilla, Killary Inner, Rosmoney, Mannin


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", default="data/processed/station_week_panel.parquet")
    p.add_argument("--t0", default="2023-05-01")
    p.add_argument("--t1", default="2023-08-31")
    p.add_argument(
        "--stations",
        default=",".join(str(s) for s in DEFAULT_STATIONS),
        help="comma-separated location_id list",
    )
    p.add_argument("--bbox-month", default="2023-06", help="YYYY-MM for Irish bbox NetCDF (or empty)")
    p.add_argument("--skip-bbox", action="store_true")
    args = p.parse_args()

    root = Path(".")
    raw_dir = root / "data" / "raw" / "osi_saf"
    raw_dir.mkdir(parents=True, exist_ok=True)
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
    if stations.empty:
        raise SystemExit(f"no stations matched ids={ids}")
    print("stations:\n", stations.to_string(index=False), flush=True)

    daily = download_odyssea_for_stations(stations, args.t0, args.t1)
    if daily.empty:
        raise SystemExit("ODYSSEA extract empty")

    # Attach names for readability
    daily = daily.merge(stations[["location_id", "location_name"]], on="location_id", how="left")

    daily_path = root / "data" / "raw" / "odyssea_daily.parquet"
    daily.to_parquet(daily_path, index=False)
    print(f"wrote {daily_path} n={len(daily)}", flush=True)

    station_day = daily.rename(columns={"location_id": "station_id"})[
        ["date", "station_id", "location_name", "request_lat", "request_lon", "sst", "source"]
    ].copy()
    # also keep lat/lon aliases
    station_day["lat"] = station_day["request_lat"]
    station_day["lon"] = station_day["request_lon"]
    station_day_path = processed / "osi_saf_station_day.parquet"
    station_day.to_parquet(station_day_path, index=False)
    # small CSV companion (git-friendly whitelist candidate)
    station_day.to_csv(processed / "osi_saf_station_day.csv", index=False)
    print(f"wrote {station_day_path}", flush=True)

    bbox_path = None
    if not args.skip_bbox and args.bbox_month:
        y, m = args.bbox_month.split("-")
        t0b = f"{y}-{m}-01"
        t1b = (pd.Timestamp(t0b) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
        bbox_path = raw_dir / f"odyssea_irish_{y}{m}_bbox.nc"
        write_odyssea_bbox_netcdf(bbox_path, t0b, t1b)

    sources = {
        "lane": "osi_saf_sst",
        "preferred_product": {
            "id": "OSI-202-c",
            "ghrsst": "AVHRR_SST_METOP_B_NAR-OSISAF-L3C-v1.0",
            "url": "https://osi-saf.eumetsat.int/products/osi-202-c",
            "ftp": "ftp://ftp.ifremer.fr/ifremer/cersat/projects/osisaf/sst/l3c/north_atlantic/",
            "https": "https://osi-saf.ifremer.fr/sst/l3c/north_atlantic/",
            "licence": "CC BY 4.0",
            "doi": "10.15770/EUM_SAF_OSI_NRT_2012",
            "status_this_box": "blocked",
            "blockers": [
                "osi-saf.ifremer.fr HTTPS TLS unexpected EOF",
                "ftp.ifremer.fr listing timeout",
                "opensearch.ifremer.fr TLS EOF",
                "PO.DAAC protected granules HTTP 401 (no Earthdata ~/.netrc)",
            ],
            "cmr_manifest": "data/raw/osi_saf_sst/nar_metop_b_manifest.csv",
        },
        "working_product": {
            **ODYSSEA_META,
            "url": "https://data.marine.copernicus.eu/product/SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025/description",
            "open_data_note": (
                "Copernicus Marine Service open data under product licence; "
                "ARCO zarr objects (.zmetadata / chunks) readable anonymously over HTTPS "
                "from CloudFerro S3 when toolbox auth host is unreachable."
            ),
            "status_this_box": "ok_anonymous_arco",
        },
        "pilot": {
            "t0": args.t0,
            "t1": args.t1,
            "bbox": [51.0, 56.0, -11.0, -5.0],
            "station_ids": ids,
            "n_rows": int(len(daily)),
            "n_days": int(daily["date"].nunique()),
            "n_stations": int(daily["location_id"].nunique()),
            "paths": {
                "odyssea_daily": str(daily_path),
                "station_day": str(station_day_path),
                "bbox_nc": str(bbox_path) if bbox_path else None,
            },
        },
    }
    sources_path = raw_dir / "sources.json"
    sources_path.write_text(json.dumps(sources, indent=2) + "\n")
    print(f"wrote {sources_path}", flush=True)

    status = {
        "product_worked": "ODYSSEA L4 IFREMER-ATL-SST-L4-NRT-OBS_FULL_TIME_SERIE (anonymous ARCO)",
        "osi_202c_worked": False,
        "n_days": int(daily["date"].nunique()),
        "n_stations": int(daily["location_id"].nunique()),
        "date_min": str(daily["date"].min().date()),
        "date_max": str(daily["date"].max().date()),
        "paths": sources["pilot"]["paths"],
        "sources_json": str(sources_path),
        "blockers": sources["preferred_product"]["blockers"],
    }
    status_path = processed / "osi_saf_odyssea_pilot_status.json"
    status_path.write_text(json.dumps(status, indent=2) + "\n")
    print(f"wrote {status_path}", flush=True)
    print(json.dumps(status, indent=2), flush=True)


if __name__ == "__main__":
    main()
