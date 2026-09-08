#!/usr/bin/env python3
"""Ingest Irish-shelf ocean colour (Chl-a) for HAB station-week joins.

Preferred: Copernicus Marine Atlantic L4 gap-free GlobColour
  product OCEANCOLOUR_ATL_BGC_L4_MY_009_118
  dataset cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D
  (requires working ~/.copernicusmarine auth).

Fallback (used when CM auth unreachable): NOAA CoastWatch DINEOF gap-filled
  VIIRS+OLCI L4 daily 2 km via public ERDDAP
  dataset noaacwNPPN20S3ASCIDINEOF2kmDaily (2018-present).

Outputs under data/external/ocean_colour/ and data/processed/ week joins.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "external" / "ocean_colour"
PROC = ROOT / "data" / "processed"
JOINED = PROC / "joined_features.parquet"

ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap"
ERDDAP_ID = "noaacwNPPN20S3ASCIDINEOF2kmDaily"
CM_PRODUCT = "OCEANCOLOUR_ATL_BGC_L4_MY_009_118"
CM_DATASET = "cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D"


def try_copernicus_auth() -> tuple[bool, str]:
    try:
        import copernicusmarine as cm
    except ImportError:
        return False, "copernicusmarine not installed"
    try:
        ok = cm.login(check_credentials_valid=True)
        return bool(ok), "ok" if ok else "invalid credentials"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def download_erddap_year_nc(
    year: int,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    out: Path,
) -> Path:
    """Download one year Irish bbox as NetCDF (lat axis descending on this dataset)."""
    if out.exists() and out.stat().st_size > 1000:
        print(f"reuse {out}", flush=True)
        return out
    t0 = f"{year}-01-01T12:00:00Z"
    t1 = f"{year}-12-31T12:00:00Z"
    # latitude constraint: high:low because axis is descending
    q = (
        f"chlor_a[({t0}):1:({t1})][(0.0):1:(0.0)]"
        f"[({lat_max}):1:({lat_min})][({lon_min}):1:({lon_max})]"
    )
    url = f"{ERDDAP_BASE}/griddap/{ERDDAP_ID}.nc?{q}"
    print(f"ERDDAP Chl year {year} …", flush=True)
    last = None
    for attempt in range(5):
        try:
            r = requests.get(url, timeout=600)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(r.content)
            print(f"  wrote {out} bytes={out.stat().st_size}", flush=True)
            return out
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"  retry {attempt+1}: {exc}", flush=True)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"failed year {year}: {last}")


def stations_from_joined() -> pd.DataFrame:
    df = pd.read_parquet(JOINED, columns=["location_id", "latitude", "longitude"])
    return df.drop_duplicates("location_id").reset_index(drop=True)


def extract_station_series(nc_path: Path, stations: pd.DataFrame) -> pd.DataFrame:
    import xarray as xr

    ds = xr.open_dataset(nc_path)
    da = ds["chlor_a"]
    if "altitude" in da.dims:
        da = da.isel(altitude=0)
    # Build ocean mask from any finite Chl day
    vals = da.values
    ocean = np.isfinite(vals).any(axis=0)
    lats = da["latitude"].values.astype(float)
    lons = da["longitude"].values.astype(float)
    lat_g, lon_g = np.meshgrid(lats, lons, indexing="ij")
    rows = []
    for row in stations.itertuples(index=False):
        dist = (lat_g - float(row.latitude)) ** 2 + (lon_g - float(row.longitude)) ** 2
        dist = np.where(ocean, dist, np.inf)
        if not np.isfinite(dist).any():
            continue
        i, j = np.unravel_index(int(np.argmin(dist)), dist.shape)
        rows.append(
            {
                "location_id": row.location_id,
                "request_lat": float(row.latitude),
                "request_lon": float(row.longitude),
                "grid_lat": float(lats[i]),
                "grid_lon": float(lons[j]),
                "dist_deg": float(np.sqrt(dist[i, j])),
                "i": int(i),
                "j": int(j),
            }
        )
    pix = pd.DataFrame(rows)
    if pix.empty:
        return pd.DataFrame()
    times = pd.to_datetime(da["time"].values).tz_localize(None)
    frames = []
    arr = np.asarray(da.values, dtype=float)
    for rec in pix.itertuples(index=False):
        series = arr[:, rec.i, rec.j]
        frames.append(
            pd.DataFrame(
                {
                    "date": times,
                    "location_id": rec.location_id,
                    "chl": series,
                    "grid_lat": rec.grid_lat,
                    "grid_lon": rec.grid_lon,
                    "request_lat": rec.request_lat,
                    "request_lon": rec.request_lon,
                    "dist_deg": rec.dist_deg,
                }
            )
        )
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out


def to_week(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.dropna(subset=["chl"]).copy()
    iso = d["date"].dt.isocalendar()
    d["iso_year"] = iso.year.astype(int)
    d["iso_week"] = iso.week.astype(int)
    g = (
        d.groupby(["location_id", "iso_year", "iso_week"], as_index=False)
        .agg(
            chl_mean=("chl", "mean"),
            chl_median=("chl", "median"),
            chl_max=("chl", "max"),
            chl_n=("chl", "count"),
            grid_lat=("grid_lat", "first"),
            grid_lon=("grid_lon", "first"),
        )
    )
    g["chl_log1p"] = np.log1p(g["chl_mean"].clip(lower=0))
    g = g.sort_values(["location_id", "iso_year", "iso_week"])
    g["chl_mean_lag1w"] = g.groupby("location_id")["chl_mean"].shift(1)
    g["chl_log1p_lag1w"] = g.groupby("location_id")["chl_log1p"].shift(1)
    g["chl_mean_roll4w"] = (
        g.groupby("location_id")["chl_mean"].transform(lambda s: s.rolling(4, min_periods=1).mean())
    )
    return g


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--y0", type=int, default=2018)
    p.add_argument("--y1", type=int, default=2025)
    p.add_argument("--lat-min", type=float, default=51.0)
    p.add_argument("--lat-max", type=float, default=56.0)
    p.add_argument("--lon-min", type=float, default=-11.0)
    p.add_argument("--lon-max", type=float, default=-5.0)
    p.add_argument("--skip-cm", action="store_true")
    args = p.parse_args()

    EXT.mkdir(parents=True, exist_ok=True)
    source = {
        "preferred_product": CM_PRODUCT,
        "preferred_dataset": CM_DATASET,
        "fallback_erddap_base": ERDDAP_BASE,
        "fallback_dataset_id": ERDDAP_ID,
        "bbox": [args.lat_min, args.lat_max, args.lon_min, args.lon_max],
        "years": [args.y0, args.y1],
    }

    cm_ok, cm_msg = (False, "skipped") if args.skip_cm else try_copernicus_auth()
    source["copernicus_auth"] = {"ok": cm_ok, "detail": cm_msg}
    print("Copernicus auth:", cm_ok, cm_msg, flush=True)

    if cm_ok:
        source["active_source"] = "copernicus_marine"
        # Station-pixel timeseries via open_dataset (mirror OSTIA pattern) — optional path
        print("NOTE: CM auth OK but ERDDAP fallback still used for reproducibility this run "
              "(CM L4 path can be enabled once subset timing is stable).", flush=True)
        source["active_source"] = "coastwatch_erddap_dineof_despite_cm_ok"
    else:
        source["active_source"] = "coastwatch_erddap_dineof_fallback"

    stations = stations_from_joined()
    print(f"stations={len(stations)}", flush=True)

    daily_parts = []
    raw_dir = EXT / "raw_erddap_nc"
    for y in range(args.y0, args.y1 + 1):
        nc = raw_dir / f"chl_dineof2km_irish_{y}.nc"
        try:
            download_erddap_year_nc(y, args.lat_min, args.lat_max, args.lon_min, args.lon_max, nc)
            part = extract_station_series(nc, stations)
            print(f"  year {y} rows={len(part)} nan={float(part['chl'].isna().mean()) if len(part) else 1:.3f}", flush=True)
            if not part.empty:
                daily_parts.append(part)
        except Exception as exc:  # noqa: BLE001
            print(f"  YEAR FAIL {y}: {exc}", flush=True)

    if not daily_parts:
        print("no daily Chl extracted", flush=True)
        (EXT / "sources.json").write_text(json.dumps(source, indent=2))
        return 1

    daily = pd.concat(daily_parts, ignore_index=True).drop_duplicates(["location_id", "date"])
    daily_path = EXT / "chl_station_daily.parquet"
    daily.to_parquet(daily_path, index=False)
    daily.to_csv(EXT / "chl_station_daily.csv", index=False)
    print(f"daily {daily_path} n={len(daily)} "
          f"{daily['date'].min().date()}..{daily['date'].max().date()}", flush=True)

    week = to_week(daily)
    week_path = PROC / "ocean_colour_chl_week.parquet"
    week.to_parquet(week_path, index=False)
    week.to_csv(PROC / "ocean_colour_chl_week.csv", index=False)
    print(f"week {week_path} n={len(week)}", flush=True)

    source.update(
        {
            "daily_path": str(daily_path.relative_to(ROOT)),
            "week_path": str(week_path.relative_to(ROOT)),
            "n_daily": int(len(daily)),
            "n_week": int(len(week)),
            "date_min": str(daily["date"].min().date()),
            "date_max": str(daily["date"].max().date()),
            "n_stations": int(daily["location_id"].nunique()),
            "join_keys": ["location_id", "iso_year", "iso_week"],
            "units": "mg m^-3",
        }
    )
    (EXT / "sources.json").write_text(json.dumps(source, indent=2))
    (PROC / "ocean_colour_ingest_summary.json").write_text(json.dumps(source, indent=2))
    print("wrote sources + summary", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
