#!/usr/bin/env python3
"""Extract full Irish HAB station-day ODYSSEA L4 SST via CloudFerro ARCO zarr.

Bypasses copernicusmarine auth (TLS EOF on auth.marine.copernicus.eu).
Reuses pilot schema from data/raw/osi_saf/odyssea_pilot_2023_jun.parquet.

Writes:
  data/processed/odyssea_station_day.parquet
  data/raw/osi_saf/sources.json
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from pa_marine.osi_saf_sst import (
    ODYSSEA_ARCO_TIMECHUNKED,
    ODYSSEA_META,
    download_odyssea_for_stations,
    open_odyssea_arco,
)

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data/processed/station_week_panel.parquet"
OUT_PARQUET = ROOT / "data/processed/odyssea_station_day.parquet"
OUT_SOURCES = ROOT / "data/raw/osi_saf/sources.json"
PILOT = ROOT / "data/raw/osi_saf/odyssea_pilot_2023_jun.parquet"


def quarter_chunks(t0: str, t1: str) -> list[tuple[str, str]]:
    start = pd.Timestamp(t0)
    end = pd.Timestamp(t1)
    chunks: list[tuple[str, str]] = []
    y, q = start.year, (start.month - 1) // 3
    cur = pd.Timestamp(year=y, month=q * 3 + 1, day=1)
    if cur < start:
        cur = start
    while cur <= end:
        q = (cur.month - 1) // 3
        q_end_month = q * 3 + 3
        q_end = pd.Timestamp(year=cur.year, month=q_end_month, day=1) + pd.offsets.MonthEnd(0)
        a = max(cur, start)
        b = min(q_end, end)
        chunks.append((a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")))
        cur = b + pd.Timedelta(days=1)
    return chunks


def month_chunks(t0: str, t1: str) -> list[tuple[str, str]]:
    start = pd.Timestamp(t0)
    end = pd.Timestamp(t1)
    chunks = []
    cur = start.replace(day=1)
    if cur < start:
        cur = start
    while cur <= end:
        m_end = cur + pd.offsets.MonthEnd(0)
        a = max(cur if cur.day == 1 else cur, start)
        # if cur was mid-month start
        a = max(pd.Timestamp(t0) if cur <= pd.Timestamp(t0) else cur.replace(day=1), start)
        a = max(cur.replace(day=1), start) if cur.day == 1 else max(cur, start)
        b = min(m_end, end)
        if a <= b:
            chunks.append((a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")))
        cur = m_end + pd.Timedelta(days=1)
    return chunks


def day_list(t0: str, t1: str) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(t0, t1, freq="D")]


def try_extract(stations: pd.DataFrame, t0: str, t1: str) -> pd.DataFrame:
    return download_odyssea_for_stations(stations, t0, t1)


def extract_range(
    stations: pd.DataFrame, t0: str, t1: str, *, skipped: list[str]
) -> pd.DataFrame:
    """Quarter → month → day fallback; skip individual ARCO-403 days."""
    try:
        return try_extract(stations, t0, t1)
    except Exception as exc:
        print(f"  range fail {t0}..{t1}: {type(exc).__name__} → split", flush=True)

    # If single day, skip
    if t0 == t1:
        print(f"  SKIP bad day {t0}", flush=True)
        skipped.append(t0)
        return pd.DataFrame()

    # Prefer monthly split if span > 31 days else daily
    span = (pd.Timestamp(t1) - pd.Timestamp(t0)).days + 1
    if span > 31:
        sub_chunks = month_chunks(t0, t1)
    else:
        sub_chunks = [(d, d) for d in day_list(t0, t1)]

    frames = []
    for a, b in sub_chunks:
        try:
            part = try_extract(stations, a, b)
            frames.append(part)
            print(f"  ok {a}..{b} rows={len(part)}", flush=True)
        except Exception:
            if a == b:
                print(f"  SKIP bad day {a}", flush=True)
                skipped.append(a)
            else:
                # recurse to days
                for d in day_list(a, b):
                    try:
                        part = try_extract(stations, d, d)
                        frames.append(part)
                        print(f"  ok day {d}", flush=True)
                    except Exception:
                        print(f"  SKIP bad day {d}", flush=True)
                        skipped.append(d)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--t0", default="2018-01-01")
    p.add_argument("--t1", default="2026-09-06")
    p.add_argument("--max-stations", type=int, default=None)
    p.add_argument("--out", default=str(OUT_PARQUET))
    p.add_argument("--sources", default=str(OUT_SOURCES))
    p.add_argument("--timing-only", action="store_true")
    args = p.parse_args()

    t_wall0 = time.time()
    panel = pd.read_parquet(PANEL)
    stations = panel.drop_duplicates("location_id")[
        ["location_id", "location_name", "latitude", "longitude"]
    ].copy()
    if args.max_stations:
        stations = stations.head(args.max_stations)
    print(f"stations={len(stations)} t0={args.t0} t1={args.t1}", flush=True)

    print("opening ODYSSEA ARCO zarr (catalogue bounds)…", flush=True)
    ds = open_odyssea_arco()
    t_min = str(ds.time.values[0])[:10]
    t_max = str(ds.time.values[-1])[:10]
    ds.close()
    print("catalogue time", t_min, "->", t_max, flush=True)

    t0 = max(args.t0, t_min)
    t1 = min(args.t1, t_max)
    chunks = quarter_chunks(t0, t1)
    print(f"n_chunks={len(chunks)} (quarterly + fallback)", flush=True)

    skipped: list[str] = []
    frames: list[pd.DataFrame] = []
    for a_s, b_s in chunks:
        t0c = time.time()
        print(f"chunk {a_s}..{b_s}", flush=True)
        part = extract_range(stations, a_s, b_s, skipped=skipped)
        n = len(part)
        finite = int(np.isfinite(part["sst"]).sum()) if n else 0
        print(f"  rows={n} finite={finite} elapsed={time.time()-t0c:.1f}s", flush=True)
        if n:
            frames.append(part)
        if args.timing_only:
            print("timing-only done", flush=True)
            return 0

    if not frames:
        raise SystemExit("no data extracted")

    daily = pd.concat(frames, ignore_index=True)
    daily["date"] = pd.to_datetime(daily["date"]).dt.tz_localize(None).dt.normalize()
    daily = daily.sort_values(["location_id", "date"]).drop_duplicates(
        ["location_id", "date"], keep="last"
    )

    names = stations[["location_id", "location_name"]]
    out = daily.merge(names, on="location_id", how="left")
    out["dist_deg"] = np.sqrt(
        (out["grid_lat"] - out["request_lat"]) ** 2
        + (out["grid_lon"] - out["request_lon"]) ** 2
    )
    out["sst_c"] = out["sst"]
    out["analysed_sst"] = out["sst_c"] + 273.15
    out["source"] = "odyssea_l4_arco"
    keep = [
        "date",
        "location_id",
        "location_name",
        "request_lat",
        "request_lon",
        "grid_lat",
        "grid_lon",
        "dist_deg",
        "analysed_sst",
        "sst_c",
        "source",
    ]
    out = out[keep]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    size_mb = out_path.stat().st_size / 1e6

    csv_path = None
    if size_mb < 8:
        csv_path = out_path.with_suffix(".csv")
        out.to_csv(csv_path, index=False)
        print(f"wrote companion CSV {csv_path}", flush=True)
    else:
        print(f"skip CSV (parquet {size_mb:.1f} MB > 8 MB threshold)", flush=True)

    smap = (
        out.drop_duplicates("location_id")[
            [
                "location_id",
                "location_name",
                "request_lat",
                "request_lon",
                "grid_lat",
                "grid_lon",
                "dist_deg",
            ]
        ]
        .sort_values("location_id")
        .reset_index(drop=True)
    )
    map_path = ROOT / "data/processed/odyssea_station_pixel_map.csv"
    smap.to_csv(map_path, index=False)

    finite = out["sst_c"].to_numpy(dtype=float)
    finite = finite[np.isfinite(finite)]
    dublin = datetime.now(ZoneInfo("Europe/Dublin")).strftime("%Y-%m-%d %H:%M %Z")
    sources = {
        "lane": "osi_saf / odyssea_sst",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "created_at_dublin": dublin,
        "auth_note": {
            "copernicusmarine_cli": "fails TLS EOF on auth.marine.copernicus.eu from this box",
            "credentials_present": True,
            "working_path": "public CloudFerro ARCO zarr HTTPS with zarr_format=2",
        },
        "preferred_osi_saf_l3c": {
            "id": "OSI-202-c",
            "status_this_box": "not used for full extract (TLS/FTP blockers); ODYSSEA L4 fallback",
            "note": "ODYSSEA L4 uses OSI SAF among IR/MW inputs",
        },
        "working_product": {
            **ODYSSEA_META,
            "arco_zarr": ODYSSEA_ARCO_TIMECHUNKED,
            "catalogue_time": [t_min, t_max],
            "spatial_resolution": "~0.02 deg (~2 km)",
        },
        "pilot_reuse": {
            "path": str(PILOT.relative_to(ROOT)),
            "n_rows": 150,
            "stations": 5,
            "period": "2023-06",
            "note": "Connemara Jun 2023 pilot kept on disk; full extract supersedes for week join",
        },
        "extract": {
            "script": "scripts/extract_odyssea_station_day_arco.py",
            "chunking": "quarterly with month/day fallback; skip ARCO 403 days",
            "t0": t0,
            "t1": t1,
            "skipped_days": skipped,
            "n_stations_requested": int(len(stations)),
            "n_stations_mapped": int(out["location_id"].nunique()),
            "n_unique_pixels": int(smap[["grid_lat", "grid_lon"]].drop_duplicates().shape[0]),
            "n_rows": int(len(out)),
            "n_days": int(out["date"].nunique()),
            "n_finite_sst_c": int(len(finite)),
            "sst_c_min": float(finite.min()) if len(finite) else None,
            "sst_c_median": float(np.median(finite)) if len(finite) else None,
            "sst_c_max": float(finite.max()) if len(finite) else None,
            "median_dist_deg": float(smap["dist_deg"].median()),
            "paths": {
                "odyssea_station_day_parquet": str(out_path.relative_to(ROOT)),
                "odyssea_station_day_csv": (
                    str(csv_path.relative_to(ROOT)) if csv_path else None
                ),
                "odyssea_station_pixel_map_csv": str(map_path.relative_to(ROOT)),
                "pilot_parquet": str(PILOT.relative_to(ROOT)),
                "sources_json": str(Path(args.sources).relative_to(ROOT)),
            },
            "elapsed_s": round(time.time() - t_wall0, 1),
            "parquet_mb": round(size_mb, 2),
        },
        "station_pixel_map_n": int(len(smap)),
    }
    sources_path = Path(args.sources)
    sources_path.parent.mkdir(parents=True, exist_ok=True)
    sources_path.write_text(json.dumps(sources, indent=2) + "\n")

    print(
        f"wrote {out_path} n={len(out)} stations={out['location_id'].nunique()} "
        f"dates={out['date'].min().date()}..{out['date'].max().date()} "
        f"skipped={skipped} mb={size_mb:.2f} elapsed={sources['extract']['elapsed_s']}s",
        flush=True,
    )
    print(f"wrote {sources_path}", flush=True)
    print(f"wrote {map_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
