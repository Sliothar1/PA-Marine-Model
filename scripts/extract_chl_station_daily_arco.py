#!/usr/bin/env python3
"""Extract station-pixel daily CHL from CloudFerro ARCO zarr (zarr_format=2).

Bypasses copernicusmarine auth (TLS broken). Pattern matches the 2023 MJJA pilot.
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
OUT_DAILY = ROOT / "data/raw/ocean_colour/chl_station_daily.parquet"
OUT_META = ROOT / "data/raw/ocean_colour/chl_station_daily_sources_meta.json"

CHL_PRODUCT = "OCEANCOLOUR_ATL_BGC_L4_MY_009_118"
CHL_DATASET = "cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D"
CHL_ZARR = (
    "https://s3.waw3-1.cloudferro.com/mdl-arco-time-042/arco/"
    "OCEANCOLOUR_ATL_BGC_L4_MY_009_118/"
    "cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D_202603/timeChunked.zarr"
)


def open_arco(uri: str) -> xr.Dataset:
    return xr.open_zarr(uri, consolidated=True, zarr_format=2)


def lat_slice(ds: xr.Dataset, lo: float, hi: float):
    increasing = bool(ds.latitude.values[0] < ds.latitude.values[-1])
    return slice(lo, hi) if increasing else slice(hi, lo)


def nearest_ocean(stations: pd.DataFrame, mask_da: xr.DataArray) -> pd.DataFrame:
    lats = np.asarray(mask_da.latitude.values, dtype=float)
    lons = np.asarray(mask_da.longitude.values, dtype=float)
    vals = np.asarray(mask_da.values, dtype=float)
    while vals.ndim > 2:
        vals = vals[0]
    ocean = np.isfinite(vals)
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


def extract_chunk(
    ds: xr.Dataset, smap: pd.DataFrame, t0: str, t1: str
) -> pd.DataFrame:
    pix = (
        smap[["grid_lat", "grid_lon"]]
        .drop_duplicates()
        .reset_index(drop=True)
        .reset_index(names="pixel_id")
    )
    station_pix = smap.merge(pix, on=["grid_lat", "grid_lon"], how="inner")
    lat_da = xr.DataArray(pix["grid_lat"].to_numpy(dtype=float), dims="pixel")
    lon_da = xr.DataArray(pix["grid_lon"].to_numpy(dtype=float), dims="pixel")
    da = (
        ds["CHL"]
        .sel(time=slice(t0, t1))
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
                    "CHL": vals[:, pi],
                }
            )
        )
    daily_pix = pd.concat(frames, ignore_index=True)
    out = station_pix.merge(daily_pix, on=["pixel_id", "grid_lat", "grid_lon"], how="inner")
    keep = [
        "date",
        "location_id",
        "location_name",
        "request_lat",
        "request_lon",
        "grid_lat",
        "grid_lon",
        "CHL",
        "dist_deg",
    ]
    return out[keep]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--t0", default="2018-01-01")
    p.add_argument("--t1", default="2026-08-31")
    p.add_argument("--chunk-months", type=int, default=6)
    p.add_argument("--max-stations", type=int, default=None)
    p.add_argument("--out", default=str(OUT_DAILY))
    p.add_argument("--meta", default=str(OUT_META))
    p.add_argument("--timing-only", action="store_true", help="time one chunk then exit")
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
    ds = open_arco(CHL_ZARR)
    print("dims", dict(ds.sizes), "time", str(ds.time.values[0])[:10], "->", str(ds.time.values[-1])[:10], flush=True)

    # Irish domain pad for mask
    lat_lo, lat_hi = 51.0 - 0.2, 56.0 + 0.2
    lon_lo, lon_hi = -11.5 - 0.2, -5.0 + 0.2
    print("building ocean mask (2020-06-15)…", flush=True)
    mask = (
        ds["CHL"]
        .sel(time="2020-06-15")
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

    # time chunks
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
    for s, e in zip(starts, ends):
        if s > e:
            continue
        a_s, b_s = s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")
        t0c = time.time()
        print(f"chunk {a_s}..{b_s}", flush=True)
        part = extract_chunk(ds, smap, a_s, b_s)
        print(
            f"  rows={len(part)} finite={int(np.isfinite(part['CHL']).sum())} "
            f"elapsed={time.time()-t0c:.1f}s",
            flush=True,
        )
        frames.append(part)
        if args.timing_only:
            print("timing-only done", flush=True)
            return 0

    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()
    out = out.sort_values(["location_id", "date"]).drop_duplicates(
        ["location_id", "date"], keep="last"
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    finite = out["CHL"].to_numpy(dtype=float)
    finite = finite[np.isfinite(finite)]
    meta = {
        "product_id": CHL_PRODUCT,
        "dataset_id": CHL_DATASET,
        "variable": "CHL",
        "units": "mg m-3",
        "access": "public ARCO zarr HTTPS (CloudFerro), zarr_format=2",
        "arco_zarr": CHL_ZARR,
        "time_range": [args.t0, args.t1],
        "n_stations_requested": int(len(stations)),
        "n_stations_mapped": int(smap["location_id"].nunique()),
        "n_unique_pixels": int(smap[["grid_lat", "grid_lon"]].drop_duplicates().shape[0]),
        "n_rows": int(len(out)),
        "n_finite_chl": int(len(finite)),
        "chl_min": float(finite.min()) if len(finite) else None,
        "chl_median": float(np.median(finite)) if len(finite) else None,
        "chl_max": float(finite.max()) if len(finite) else None,
        "median_dist_deg": float(smap["dist_deg"].median()),
        "stations": smap.to_dict(orient="records"),
        "elapsed_s": round(time.time() - t_wall0, 1),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "created_at_dublin": datetime.now(ZoneInfo("Europe/Dublin")).strftime("%Y-%m-%d %H:%M %Z"),
    }
    Path(args.meta).write_text(json.dumps(meta, indent=2) + "\n")
    print(
        f"wrote {out_path} n={len(out)} stations={out['location_id'].nunique()} "
        f"dates={out['date'].min().date()}..{out['date'].max().date()} "
        f"elapsed={meta['elapsed_s']}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
