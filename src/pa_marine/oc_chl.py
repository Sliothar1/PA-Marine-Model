"""Copernicus / WEkEO Atlantic Ocean Colour chlorophyll (L4 gap-free) at HAB stations.

Product: OCEANCOLOUR_ATL_BGC_L4_MY_009_118
Dataset: cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D
Variable: CHL (mg m-3), daily gap-free multi-sensor, ~1 km, 1997→ongoing.

Credentials: ~/.copernicusmarine (never printed). Same pattern as OSTIA / IBI.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _require_cm():
    try:
        import copernicusmarine as cm
        import xarray  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "copernicusmarine and xarray required for OC Chl downloads "
            "(pip install copernicusmarine xarray)"
        ) from exc
    return cm


def _oc_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    oc = dict(cfg.get("ocean_colour") or {})
    oc.setdefault("product", "OCEANCOLOUR_ATL_BGC_L4_MY_009_118")
    oc.setdefault(
        "dataset_id",
        "cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D",
    )
    oc.setdefault("variable", "CHL")
    oc.setdefault("service", "timeseries")
    oc.setdefault("t0", "2002-01-01")
    oc.setdefault("t1", "2026-08-31")
    return oc


def _domain_pad(cfg: dict[str, Any], pad: float = 0.15) -> tuple[float, float, float, float]:
    domain = cfg.get("domain", {})
    return (
        float(domain.get("lon_min", -11.0)) - pad,
        float(domain.get("lon_max", -5.0)) + pad,
        float(domain.get("lat_min", 51.0)) - pad,
        float(domain.get("lat_max", 56.0)) + pad,
    )


def _nearest_ocean_pixel_map(stations: pd.DataFrame, mask_da: Any) -> pd.DataFrame:
    lats = np.asarray(mask_da.latitude.values, dtype=float)
    lons = np.asarray(mask_da.longitude.values, dtype=float)
    vals = np.asarray(mask_da.values, dtype=float)
    while vals.ndim > 2:
        vals = vals[0]
    ocean = np.isfinite(vals)
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
    rows = []
    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]]
    for row in uniq.itertuples(index=False):
        dist = (lat_grid - float(row.latitude)) ** 2 + (lon_grid - float(row.longitude)) ** 2
        dist = np.where(ocean, dist, np.inf)
        if not np.isfinite(dist).any():
            print(f"OC-Chl skip {row.location_id}: no ocean pixel in mask bbox", flush=True)
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
            }
        )
    return pd.DataFrame(rows)


def download_oc_chl_for_stations(
    stations: pd.DataFrame,
    cfg: dict[str, Any],
    t0: str | None = None,
    t1: str | None = None,
    max_stations: int | None = None,
) -> pd.DataFrame:
    """Nearest-ocean-pixel daily CHL (mg m-3) per location_id (year chunks)."""
    import xarray as xr

    cm = _require_cm()
    oc = _oc_cfg(cfg)
    dataset_id = oc["dataset_id"]
    variable = oc["variable"]
    service = oc.get("service", "timeseries")
    t0 = t0 or oc["t0"]
    t1 = t1 or oc["t1"]

    lon_min, lon_max, lat_min, lat_max = _domain_pad(cfg)
    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]].copy()
    if max_stations is not None:
        uniq = uniq.head(max_stations)

    print("OC-Chl: loading ocean mask (1 day)…", flush=True)
    mask_ds = cm.open_dataset(
        dataset_id=dataset_id,
        variables=[variable],
        minimum_longitude=lon_min,
        maximum_longitude=lon_max,
        minimum_latitude=lat_min,
        maximum_latitude=lat_max,
        start_datetime="2020-06-15",
        end_datetime="2020-06-15",
        service=service,
    )
    mask_da = mask_ds[variable].isel(time=0).load()
    pixel_map = _nearest_ocean_pixel_map(uniq, mask_da)
    if pixel_map.empty:
        return pd.DataFrame()

    pix = (
        pixel_map[["grid_lat", "grid_lon"]]
        .drop_duplicates()
        .reset_index(drop=True)
        .reset_index(names="pixel_id")
    )
    station_pix = pixel_map.merge(pix, on=["grid_lat", "grid_lon"], how="inner")
    print(
        f"OC-Chl: {len(station_pix)} stations → {len(pix)} unique pixels "
        f"(median dist {pixel_map['dist_deg'].median():.3f}°)",
        flush=True,
    )

    lat_da = xr.DataArray(pix["grid_lat"].to_numpy(dtype=float), dims="pixel")
    lon_da = xr.DataArray(pix["grid_lon"].to_numpy(dtype=float), dims="pixel")
    y0, y1 = pd.Timestamp(t0).year, pd.Timestamp(t1).year
    frames: list[pd.DataFrame] = []

    for y in range(y0, y1 + 1):
        a = max(pd.Timestamp(t0), pd.Timestamp(f"{y}-01-01"))
        b = min(pd.Timestamp(t1), pd.Timestamp(f"{y}-12-31"))
        if a > b:
            continue
        a_s, b_s = a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")
        print(f"OC-Chl year {y} {a_s}..{b_s}", flush=True)
        try:
            ds = cm.open_dataset(
                dataset_id=dataset_id,
                variables=[variable],
                minimum_longitude=float(pix["grid_lon"].min() - 0.05),
                maximum_longitude=float(pix["grid_lon"].max() + 0.05),
                minimum_latitude=float(pix["grid_lat"].min() - 0.05),
                maximum_latitude=float(pix["grid_lat"].max() + 0.05),
                start_datetime=a_s,
                end_datetime=b_s,
                service=service,
            )
            da = (
                ds[variable]
                .sel(latitude=lat_da, longitude=lon_da, method="nearest")
                .load()
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  OC-Chl skip year {y}: {exc}", flush=True)
            continue

        times = pd.to_datetime(np.asarray(da.time.values)).tz_localize(None)
        vals = np.asarray(da.values, dtype=float)
        # da dims: time × pixel
        for pi, prow in pix.iterrows():
            col = vals[:, pi] if vals.ndim == 2 else vals
            part = pd.DataFrame(
                {
                    "date": times,
                    "pixel_id": int(prow["pixel_id"]),
                    "grid_lat": float(prow["grid_lat"]),
                    "grid_lon": float(prow["grid_lon"]),
                    "chl": col,
                }
            )
            frames.append(part)

    if not frames:
        return pd.DataFrame()

    daily_pix = pd.concat(frames, ignore_index=True)
    out = station_pix.merge(daily_pix, on=["pixel_id", "grid_lat", "grid_lon"], how="inner")
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["chl_log1p"] = np.log1p(np.clip(out["chl"], a_min=0.0, a_max=None))
    keep = [
        "location_id",
        "date",
        "request_lat",
        "request_lon",
        "grid_lat",
        "grid_lon",
        "dist_deg",
        "chl",
        "chl_log1p",
    ]
    return out[keep].sort_values(["location_id", "date"]).reset_index(drop=True)
