#!/usr/bin/env python3
"""Extract station-day ODYSSEA L4 SST from CloudFerro ARCO zarr (zarr_format=2).

Bypasses broken copernicusmarine TLS to auth.marine.copernicus.eu.
Schema matches data/raw/osi_saf/odyssea_pilot_2023_jun.parquet.
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

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data/processed/station_week_panel.parquet"
OUT_DAILY = ROOT / "data/processed/odyssea_station_day.parquet"
OUT_WEEK = ROOT / "data/processed/odyssea_station_week.parquet"
OUT_META = ROOT / "data/raw/osi_saf/odyssea_station_day_sources.json"

PRODUCT = "SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025"
DATASET = "IFREMER-ATL-SST-L4-NRT-OBS_FULL_TIME_SERIE"
ARCO_ZARR = (
    "https://s3.waw3-1.cloudferro.com/mdl-arco-time-045/arco/"
    "SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025/"
    "IFREMER-ATL-SST-L4-NRT-OBS_FULL_TIME_SERIE_201904/timeChunked.zarr"
)
# GHRSST mask: bit 1=sea, 2=land, 4=lake, 8=ice
SEA_MASK = 1


def open_arco(uri: str) -> xr.Dataset:
    return xr.open_zarr(uri, consolidated=True, zarr_format=2)


def lat_slice(ds: xr.Dataset, lo: float, hi: float):
    increasing = bool(ds.latitude.values[0] < ds.latitude.values[-1])
    return slice(lo, hi) if increasing else slice(hi, lo)


def nearest_ocean(stations: pd.DataFrame, mask_da: xr.DataArray) -> pd.DataFrame:
    """Snap each station to nearest sea pixel (mask == SEA_MASK)."""
    lats = np.asarray(mask_da.latitude.values, dtype=float)
    lons = np.asarray(mask_da.longitude.values, dtype=float)
    vals = np.asarray(mask_da.values)
    while vals.ndim > 2:
        vals = vals[0]
    ocean = vals == SEA_MASK
    latg, long = np.meshgrid(lats, lons, indexing="ij")
    rows = []
    cols = ["location_id", "location_name", "latitude", "longitude"]
    for row in stations.drop_duplicates("location_id")[cols].itertuples(index=False):
        dist = (latg - float(row.latitude)) ** 2 + (long - float(row.longitude)) ** 2
        dist = np.where(ocean, dist, np.inf)
        if not np.isfinite(dist).any():
            print(f"skip {row.location_id}: no ocean pixel", flush=True)
            continue
        i, j = np.unravel_index(int(np.argmin(dist)), dist.shape)
        rows.append(
            {
                "location_id": int(row.location_id),
                "location_name": row.location_name,
                "request_lat": float(row.latitude),
                "request_lon": float(row.longitude),
                "grid_lat": float(lats[i]),
                "grid_lon": float(lons[j]),
                "dist_deg": float(np.sqrt(dist[i, j])),
            }
        )
    return pd.DataFrame(rows)


def extract_chunk(ds: xr.Dataset, smap: pd.DataFrame, t0: str, t1: str) -> pd.DataFrame:
    pix = (
        smap[["grid_lat", "grid_lon"]]
        .drop_duplicates()
        .reset_index(drop=True)
        .reset_index(names="pixel_id")
    )
    station_pix = smap.merge(pix, on=["grid_lat", "grid_lon"], how="inner")
    lat_da = xr.DataArray(pix["grid_lat"].to_numpy(dtype=float), dims="pixel")
    lon_da = xr.DataArray(pix["grid_lon"].to_numpy(dtype=float), dims="pixel")
    last_err = None
    da = None
    for attempt in range(1, 6):
        try:
            da = (
                ds["analysed_sst"]
                .sel(time=slice(t0, t1))
                .sel(latitude=lat_da, longitude=lon_da, method="nearest")
                .load()
            )
            break
        except Exception as exc:  # noqa: BLE001 — network/403 from ARCO
            last_err = exc
            wait = min(30, 2 ** attempt)
            print(f"  retry {attempt}/5 after {type(exc).__name__}: {exc} sleep={wait}s", flush=True)
            time.sleep(wait)
    if da is None:
        raise RuntimeError(f"extract failed {t0}..{t1}: {last_err}")
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
                    "analysed_sst": vals[:, pi],
                }
            )
        )
    daily_pix = pd.concat(frames, ignore_index=True)
    out = station_pix.merge(daily_pix, on=["pixel_id", "grid_lat", "grid_lon"], how="inner")
    out["sst_c"] = out["analysed_sst"] - 273.15
    keep = [
        "date",
        "grid_lat",
        "grid_lon",
        "analysed_sst",
        "location_id",
        "location_name",
        "request_lat",
        "request_lon",
        "dist_deg",
        "sst_c",
    ]
    return out[keep]


def to_week(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"]).dt.tz_localize(None).dt.normalize()
    iso = d["date"].dt.isocalendar()
    d["iso_year"] = iso.year.astype(int)
    d["iso_week"] = iso.week.astype(int)
    g = (
        d.groupby(["location_id", "location_name", "iso_year", "iso_week"], as_index=False)
        .agg(
            odyssea_sst_week=("sst_c", "mean"),
            odyssea_sst_n=("sst_c", lambda s: int(np.isfinite(s.to_numpy(dtype=float)).sum())),
            odyssea_sst_kelvin_week=("analysed_sst", "mean"),
            grid_lat=("grid_lat", "first"),
            grid_lon=("grid_lon", "first"),
            request_lat=("request_lat", "first"),
            request_lon=("request_lon", "first"),
            dist_deg=("dist_deg", "first"),
            date_min=("date", "min"),
            date_max=("date", "max"),
        )
    )
    return g.sort_values(["location_id", "iso_year", "iso_week"]).reset_index(drop=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--t0", default="2022-01-01")
    p.add_argument("--t1", default="2024-12-31")
    p.add_argument("--chunk-months", type=int, default=3)
    p.add_argument("--max-stations", type=int, default=None)
    p.add_argument("--out", default=str(OUT_DAILY))
    p.add_argument("--week-out", default=str(OUT_WEEK))
    p.add_argument("--meta", default=str(OUT_META))
    p.add_argument("--no-week", action="store_true")
    p.add_argument("--timing-only", action="store_true")
    p.add_argument("--append", action="store_true", help="merge with existing out parquet")
    args = p.parse_args()

    t_wall0 = time.time()
    panel = pd.read_parquet(PANEL)
    stations = panel.drop_duplicates("location_id")[
        ["location_id", "location_name", "latitude", "longitude"]
    ].copy()
    if args.max_stations:
        stations = stations.head(args.max_stations)
    print(f"stations={len(stations)} t0={args.t0} t1={args.t1}", flush=True)

    print("opening ARCO zarr…", flush=True)
    ds = open_arco(ARCO_ZARR)
    tmin = str(ds.time.values[0])[:10]
    tmax = str(ds.time.values[-1])[:10]
    print("dims", dict(ds.sizes), "time", tmin, "->", tmax, flush=True)

    lat_lo, lat_hi = 51.0 - 0.3, 56.0 + 0.3
    lon_lo, lon_hi = -11.5 - 0.3, -5.0 + 0.3
    print("building sea mask (2023-06-15)…", flush=True)
    mask = (
        ds["mask"]
        .sel(time="2023-06-15")
        .sel(latitude=lat_slice(ds, lat_lo, lat_hi), longitude=slice(lon_lo, lon_hi))
        .load()
    )
    if "time" in mask.dims:
        mask = mask.isel(time=0)
    smap = nearest_ocean(stations, mask)
    print(
        f"mapped {len(smap)}/{len(stations)} stations → "
        f"{smap[['grid_lat','grid_lon']].drop_duplicates().shape[0]} unique pixels; "
        f"median dist_deg={smap['dist_deg'].median():.4f}",
        flush=True,
    )
    if smap.empty:
        raise SystemExit("no stations mapped")

    starts = pd.date_range(args.t0, args.t1, freq=f"{args.chunk_months}MS")
    if len(starts) == 0 or starts[0] > pd.Timestamp(args.t0):
        starts = pd.DatetimeIndex([pd.Timestamp(args.t0)]).append(starts)
    starts = starts[starts <= pd.Timestamp(args.t1)]
    ends = []
    for i, s in enumerate(starts):
        if i + 1 < len(starts):
            e = starts[i + 1] - pd.Timedelta(days=1)
        else:
            e = pd.Timestamp(args.t1)
        ends.append(min(e, pd.Timestamp(args.t1)))

    frames = []
    failed_chunks: list[str] = []
    for s, e in zip(starts, ends):
        if s > e:
            continue
        a_s, b_s = s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")
        t0c = time.time()
        print(f"chunk {a_s}..{b_s}", flush=True)
        try:
            part = extract_chunk(ds, smap, a_s, b_s)
        except Exception as exc:  # noqa: BLE001
            failed_chunks.append(f"{a_s}..{b_s}: {type(exc).__name__}: {exc}")
            print(f"  SKIP failed chunk: {exc}", flush=True)
            continue
        n_fin = int(np.isfinite(part["analysed_sst"]).sum())
        print(
            f"  rows={len(part)} finite={n_fin} elapsed={time.time()-t0c:.1f}s",
            flush=True,
        )
        frames.append(part)
        if args.timing_only:
            print("timing-only done", flush=True)
            return 0

    if not frames:
        raise SystemExit(f"no chunks succeeded; failed={failed_chunks}")
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()
    out = out.sort_values(["location_id", "date"]).drop_duplicates(
        ["location_id", "date"], keep="last"
    )

    out_path = Path(args.out)
    if args.append and out_path.exists():
        prev = pd.read_parquet(out_path)
        prev["date"] = pd.to_datetime(prev["date"]).dt.tz_localize(None).dt.normalize()
        out = (
            pd.concat([prev, out], ignore_index=True)
            .sort_values(["location_id", "date"])
            .drop_duplicates(["location_id", "date"], keep="last")
        )
        print(f"appended → total rows={len(out)}", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    week_path = None
    week = None
    if not args.no_week:
        week = to_week(out)
        week_path = Path(args.week_out)
        week_path.parent.mkdir(parents=True, exist_ok=True)
        week.to_parquet(week_path, index=False)

    finite = out["sst_c"].to_numpy(dtype=float)
    finite = finite[np.isfinite(finite)]
    meta = {
        "product_id": PRODUCT,
        "dataset_id": DATASET,
        "variable": "analysed_sst",
        "units": "kelvin (+ sst_c = K - 273.15)",
        "access": "public ARCO zarr HTTPS (CloudFerro), zarr_format=2",
        "arco_zarr": ARCO_ZARR,
        "auth_note": "bypasses copernicusmarine / auth.marine.copernicus.eu TLS",
        "time_range_requested": [args.t0, args.t1],
        "arco_time_available": [tmin, tmax],
        "date_min": str(out["date"].min().date()),
        "date_max": str(out["date"].max().date()),
        "n_stations_requested": int(len(stations)),
        "n_stations": int(out["location_id"].nunique()),
        "n_unique_pixels": int(smap[["grid_lat", "grid_lon"]].drop_duplicates().shape[0]),
        "n_rows": int(len(out)),
        "n_finite_sst": int(len(finite)),
        "sst_c_min": float(finite.min()) if len(finite) else None,
        "sst_c_median": float(np.median(finite)) if len(finite) else None,
        "sst_c_max": float(finite.max()) if len(finite) else None,
        "median_dist_deg": float(smap["dist_deg"].median()),
        "pilot_schema": "data/raw/osi_saf/odyssea_pilot_2023_jun.parquet",
        "out_daily": str(out_path),
        "out_week": str(week_path) if week_path else None,
        "n_week_rows": int(len(week)) if week is not None else None,
        "stations": smap.to_dict(orient="records"),
        "failed_chunks": failed_chunks,
        "elapsed_s": round(time.time() - t_wall0, 1),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "created_at_dublin": datetime.now(ZoneInfo("Europe/Dublin")).strftime(
            "%Y-%m-%d %H:%M %Z"
        ),
    }
    meta_path = Path(args.meta)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    # keep meta lean in git: drop full station list to sibling if huge — keep stations here
    # (207 rows is fine for JSON)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    print(
        f"wrote {out_path} n={len(out)} stations={out['location_id'].nunique()} "
        f"dates={out['date'].min().date()}..{out['date'].max().date()} "
        f"elapsed={meta['elapsed_s']}s",
        flush=True,
    )
    if week_path is not None:
        print(f"wrote {week_path} n={len(week)}", flush=True)
    print(f"wrote {meta_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
