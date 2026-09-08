#!/usr/bin/env python3
"""Extend GlobColour Chl MY station-day extract backward via CloudFerro ARCO.

Reuses nearest-ocean pixels from an existing ``data/raw/oc_chl_daily.parquet``
(2018+ extract), writes year chunks under ``data/raw/oc_chl/chunks/``, merges
with the 2018+ slice, and refreshes meta JSON.

Monthly pulls with day-level retry on ARCO 403 gaps (common pre-~2003).
Does not invent credentials or ARCO URLs.

Example:
  PYTHONPATH=src .venv/bin/python scripts/extend_oc_chl_arco_history.py \\
    --hist-t0 1997-10-01 --hist-t1 2017-12-31
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
import xarray as xr

from pa_marine.oc_chl import CHL_ARCO_ZARR

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXISTING = ROOT / "data/raw/oc_chl_daily.parquet"
DEFAULT_CHUNK_DIR = ROOT / "data/raw/oc_chl/chunks"
DEFAULT_OUT = ROOT / "data/raw/oc_chl_daily.parquet"
DEFAULT_SIDE = ROOT / "data/raw/oc_chl_daily_1997_2017.parquet"
DEFAULT_META = ROOT / "data/raw/ocean_colour/oc_chl_daily_sources_meta.json"
DEFAULT_META2 = ROOT / "data/raw/oc_chl_daily_meta.json"


def finalize(out: pd.DataFrame) -> pd.DataFrame:
    out = out.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()
    out["chl_log1p"] = np.log1p(np.clip(out["chl"].astype(float), a_min=0.0, a_max=None))
    keep = [
        "location_id",
        "date",
        "chl",
        "chl_log1p",
        "grid_lat",
        "grid_lon",
        "request_lat",
        "request_lon",
        "dist_deg",
    ]
    return out[keep].sort_values(["location_id", "date"]).reset_index(drop=True)


def extract_range(ds, station_pix, pix, a_s: str, b_s: str) -> pd.DataFrame:
    lat_da = xr.DataArray(pix["grid_lat"].to_numpy(dtype=float), dims="pixel")
    lon_da = xr.DataArray(pix["grid_lon"].to_numpy(dtype=float), dims="pixel")
    da = (
        ds["CHL"]
        .sel(time=slice(a_s, b_s))
        .sel(latitude=lat_da, longitude=lon_da, method="nearest")
        .load()
    )
    times = pd.to_datetime(np.asarray(da.time.values)).tz_localize(None)
    vals = np.asarray(da.values, dtype=float)
    if vals.ndim == 1:
        vals = vals.reshape(len(times), 1)
    frames = []
    for pi, prow in pix.iterrows():
        frames.append(
            pd.DataFrame(
                {
                    "date": times,
                    "pixel_id": int(prow["pixel_id"]),
                    "grid_lat": float(prow["grid_lat"]),
                    "grid_lon": float(prow["grid_lon"]),
                    "chl": vals[:, pi],
                }
            )
        )
    daily_pix = pd.concat(frames, ignore_index=True)
    part = station_pix.merge(daily_pix, on=["pixel_id", "grid_lat", "grid_lon"], how="inner")
    return finalize(part)


def extract_year_monthly(
    ds, station_pix, pix, year: int, hist_t0: str, hist_t1: str, chunk_dir: Path, skips: list
) -> pd.DataFrame:
    chunk_path = chunk_dir / f"chl_{year}.parquet"
    if chunk_path.exists():
        part = pd.read_parquet(chunk_path)
        print(
            f"reuse {chunk_path.name} rows={len(part)} "
            f"{part['date'].min().date()}..{part['date'].max().date()}",
            flush=True,
        )
        return part

    y0 = max(pd.Timestamp(f"{year}-01-01"), pd.Timestamp(hist_t0))
    y1 = min(pd.Timestamp(f"{year}-12-31"), pd.Timestamp(hist_t1))
    if y0 > y1:
        return pd.DataFrame()

    # Prefer half-year for post-2002 (fewer 403s); monthly+day retry for earlier.
    use_half = year >= 2003
    frames: list[pd.DataFrame] = []
    if use_half:
        halves = [
            (max(y0, pd.Timestamp(f"{year}-01-01")), min(y1, pd.Timestamp(f"{year}-06-30"))),
            (max(y0, pd.Timestamp(f"{year}-07-01")), min(y1, pd.Timestamp(f"{year}-12-31"))),
        ]
        windows = [(a, b) for a, b in halves if a <= b]
    else:
        months = pd.date_range(y0.replace(day=1), y1, freq="MS")
        windows = []
        for m0 in months:
            m1 = (m0 + pd.offsets.MonthEnd(1)).normalize()
            a = max(m0, y0)
            b = min(m1, y1)
            if a <= b:
                windows.append((a, b))

    for a, b in windows:
        a_s, b_s = a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")
        t0c = time.time()
        try:
            part = extract_range(ds, station_pix, pix, a_s, b_s)
            print(
                f"OK {a_s}..{b_s} rows={len(part)} "
                f"finite={int(np.isfinite(part['chl']).sum())} "
                f"elapsed={time.time()-t0c:.1f}s",
                flush=True,
            )
            frames.append(part)
        except Exception as exc:  # noqa: BLE001
            msg = f"{type(exc).__name__}: {exc}"
            print(f"SKIP window {a_s}..{b_s}: {msg[:160]}", flush=True)
            skips.append({"t0": a_s, "t1": b_s, "error": msg[:300]})
            for d in pd.date_range(a, b, freq="D"):
                ds_ = d.strftime("%Y-%m-%d")
                try:
                    frames.append(extract_range(ds, station_pix, pix, ds_, ds_))
                    print(f"  day OK {ds_}", flush=True)
                except Exception as exc2:  # noqa: BLE001
                    print(f"  day SKIP {ds_}: {type(exc2).__name__}", flush=True)
                    skips.append(
                        {
                            "t0": ds_,
                            "t1": ds_,
                            "error": f"{type(exc2).__name__}: {exc2}"[:300],
                        }
                    )

    if not frames:
        return pd.DataFrame()
    part = finalize(pd.concat(frames, ignore_index=True)).drop_duplicates(
        ["location_id", "date"], keep="last"
    )
    part.to_parquet(chunk_path, index=False)
    print(
        f"wrote {chunk_path.name} rows={len(part)} "
        f"{part['date'].min().date()}..{part['date'].max().date()}",
        flush=True,
    )
    return part


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--existing", default=str(DEFAULT_EXISTING))
    p.add_argument("--chunk-dir", default=str(DEFAULT_CHUNK_DIR))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--side", default=str(DEFAULT_SIDE))
    p.add_argument("--meta", default=str(DEFAULT_META))
    p.add_argument("--meta2", default=str(DEFAULT_META2))
    p.add_argument("--hist-t0", default="1997-10-01")
    p.add_argument("--hist-t1", default="2017-12-31")
    p.add_argument("--keep-from", default="2018-01-01", help="keep existing rows on/after this date")
    p.add_argument("--arco-zarr", default=CHL_ARCO_ZARR)
    args = p.parse_args()

    chunk_dir = Path(args.chunk_dir)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    t_wall0 = time.time()
    skips: list[dict] = []

    existing = pd.read_parquet(args.existing)
    smap = (
        existing.drop_duplicates("location_id")[
            ["location_id", "request_lat", "request_lon", "grid_lat", "grid_lon", "dist_deg"]
        ]
        .reset_index(drop=True)
    )
    pix = (
        smap[["grid_lat", "grid_lon"]]
        .drop_duplicates()
        .reset_index(drop=True)
        .reset_index(names="pixel_id")
    )
    station_pix = smap.merge(pix, on=["grid_lat", "grid_lon"], how="inner")
    print(
        f"pixel map: {len(smap)} stations, {len(pix)} pixels; "
        f"hist {args.hist_t0}..{args.hist_t1}",
        flush=True,
    )

    print("opening ARCO…", flush=True)
    ds = xr.open_zarr(args.arco_zarr, consolidated=True, zarr_format=2)
    print(
        f"time {str(ds.time.values[0])[:10]}..{str(ds.time.values[-1])[:10]}",
        flush=True,
    )

    y0 = pd.Timestamp(args.hist_t0).year
    y1 = pd.Timestamp(args.hist_t1).year
    hist_frames = []
    for y in range(y0, y1 + 1):
        part = extract_year_monthly(
            ds, station_pix, pix, y, args.hist_t0, args.hist_t1, chunk_dir, skips
        )
        if not part.empty:
            hist_frames.append(part)

    if not hist_frames:
        raise SystemExit("no history extracted")

    hist = finalize(pd.concat(hist_frames, ignore_index=True))
    hist = hist[(hist["date"] >= args.hist_t0) & (hist["date"] <= args.hist_t1)]
    hist = hist.drop_duplicates(["location_id", "date"], keep="last")
    side = Path(args.side)
    hist.to_parquet(side, index=False)
    print(
        f"side {side.name}: n={len(hist)} "
        f"{hist['date'].min().date()}..{hist['date'].max().date()}",
        flush=True,
    )

    exist = finalize(existing)
    exist = exist[exist["date"] >= args.keep_from]
    merged = pd.concat([hist, exist], ignore_index=True)
    merged = (
        merged.sort_values(["location_id", "date"])
        .drop_duplicates(["location_id", "date"], keep="last")
        .reset_index(drop=True)
    )
    cols = [
        "location_id",
        "date",
        "chl",
        "chl_log1p",
        "grid_lat",
        "grid_lon",
        "request_lat",
        "request_lon",
        "dist_deg",
    ]
    merged = merged[cols]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(out, index=False)

    meta = {
        "product_id": "OCEANCOLOUR_ATL_BGC_L4_MY_009_118",
        "dataset_id": "cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D",
        "variable": "CHL",
        "units": "mg m-3",
        "access": "public ARCO zarr HTTPS (CloudFerro), zarr_format=2",
        "arco_url": args.arco_zarr,
        "arco_zarr": args.arco_zarr,
        "date_range": [str(merged["date"].min().date()), str(merged["date"].max().date())],
        "date_min": str(merged["date"].min().date()),
        "date_max": str(merged["date"].max().date()),
        "n_rows": int(len(merged)),
        "n_stations": int(merged["location_id"].nunique()),
        "n_unique_pixels": int(merged[["grid_lat", "grid_lon"]].drop_duplicates().shape[0]),
        "hist_append": {
            "t0": args.hist_t0,
            "t1": args.hist_t1,
            "n_rows": int(len(hist)),
            "side": str(side.relative_to(ROOT)) if side.is_relative_to(ROOT) else str(side),
        },
        "existing_kept": {
            "t0": args.keep_from,
            "t1": str(exist["date"].max().date()) if len(exist) else None,
            "n_rows": int(len(exist)),
        },
        "n_arco_skips": len(skips),
        "arco_skips_sample": skips[:20],
        "pixel_map_source": "reused from existing oc_chl_daily.parquet (same nearest-pixel)",
        "elapsed_s": round(time.time() - t_wall0, 1),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "created_at_dublin": datetime.now(ZoneInfo("Europe/Dublin")).strftime("%Y-%m-%d %H:%M %Z"),
    }
    Path(args.meta).parent.mkdir(parents=True, exist_ok=True)
    Path(args.meta).write_text(json.dumps(meta, indent=2) + "\n")
    Path(args.meta2).write_text(
        json.dumps(
            {
                "out": str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out),
                "n_rows": meta["n_rows"],
                "n_stations": meta["n_stations"],
                "date_min": meta["date_min"],
                "date_max": meta["date_max"],
                "prefer_arco": True,
                "arco_zarr": args.arco_zarr,
                "t0": meta["date_min"],
                "t1": meta["date_max"],
                "lon_max": None,
                "side_hist": meta["hist_append"]["side"],
                "hist_t0": args.hist_t0,
                "hist_t1": args.hist_t1,
                "n_arco_skips": len(skips),
            },
            indent=2,
        )
        + "\n"
    )
    print(
        f"wrote {out} n={len(merged)} stations={merged['location_id'].nunique()} "
        f"{merged['date'].min().date()}..{merged['date'].max().date()} "
        f"skips={len(skips)} elapsed={meta['elapsed_s']}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
