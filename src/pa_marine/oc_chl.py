"""Copernicus / WEkEO Atlantic Ocean Colour chlorophyll (L4 gap-free) at HAB stations.

Product: OCEANCOLOUR_ATL_BGC_L4_MY_009_118
Dataset: cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D
Variable: CHL (mg m-3), daily gap-free multi-sensor, ~1 km, 1997→ongoing.

Credentials: ~/.copernicusmarine (never printed). Same pattern as OSTIA / IBI.

When auth.marine.copernicus.eu TLS fails, fall back to public CloudFerro ARCO
zarr (zarr_format=2) — same product/dataset, nearest ocean pixel per station.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

CHL_ARCO_ZARR = (
    "https://s3.waw3-1.cloudferro.com/mdl-arco-time-042/arco/"
    "OCEANCOLOUR_ATL_BGC_L4_MY_009_118/"
    "cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D_202603/timeChunked.zarr"
)


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
    oc.setdefault("arco_zarr", CHL_ARCO_ZARR)
    return oc


def _domain_pad(cfg: dict[str, Any], pad: float = 0.15) -> tuple[float, float, float, float]:
    domain = cfg.get("domain", {})
    return (
        float(domain.get("lon_min", -11.0)) - pad,
        float(domain.get("lon_max", -5.0)) + pad,
        float(domain.get("lat_min", 51.0)) - pad,
        float(domain.get("lat_max", 56.0)) + pad,
    )


def _is_auth_tls_failure(exc: BaseException) -> bool:
    msg = f"{type(exc).__name__}: {exc}".lower()
    needles = (
        "ssl",
        "tls",
        "unexpected_eof",
        "certificate",
        "auth.marine.copernicus",
        "unauthorized",
        "authentication",
        "credential",
        "token",
        "forbidden",
        "login",
        "keycloak",
    )
    return any(n in msg for n in needles)


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


def _lat_slice(ds: Any, lo: float, hi: float):
    increasing = bool(ds.latitude.values[0] < ds.latitude.values[-1])
    return slice(lo, hi) if increasing else slice(hi, lo)


def _finalize_daily(out: pd.DataFrame) -> pd.DataFrame:
    if out.empty:
        return out
    out = out.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()
    out["chl_log1p"] = np.log1p(np.clip(out["chl"].astype(float), a_min=0.0, a_max=None))
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
    keep = [c for c in keep if c in out.columns]
    return out[keep].sort_values(["location_id", "date"]).reset_index(drop=True)


def download_oc_chl_via_arco(
    stations: pd.DataFrame,
    cfg: dict[str, Any],
    t0: str | None = None,
    t1: str | None = None,
    max_stations: int | None = None,
    chunk_months: int = 6,
) -> pd.DataFrame:
    """Nearest-ocean-pixel daily CHL via public CloudFerro ARCO zarr (zarr_format=2)."""
    import xarray as xr

    oc = _oc_cfg(cfg)
    t0 = t0 or oc["t0"]
    t1 = t1 or oc["t1"]
    zarr_uri = oc.get("arco_zarr") or CHL_ARCO_ZARR
    lon_min, lon_max, lat_min, lat_max = _domain_pad(cfg, pad=0.2)

    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]].copy()
    if max_stations is not None:
        uniq = uniq.head(max_stations)

    print(f"OC-Chl ARCO: opening {zarr_uri}", flush=True)
    ds = xr.open_zarr(zarr_uri, consolidated=True, zarr_format=2)
    print(
        f"OC-Chl ARCO dims={dict(ds.sizes)} "
        f"time={str(ds.time.values[0])[:10]}..{str(ds.time.values[-1])[:10]}",
        flush=True,
    )

    print("OC-Chl ARCO: loading ocean mask (2020-06-15)…", flush=True)
    mask = (
        ds["CHL"]
        .sel(time="2020-06-15")
        .sel(
            latitude=_lat_slice(ds, lat_min, lat_max),
            longitude=slice(lon_min, lon_max),
        )
        .load()
    )
    if "time" in mask.dims:
        mask = mask.isel(time=0)
    pixel_map = _nearest_ocean_pixel_map(uniq, mask)
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
        f"OC-Chl ARCO: {len(station_pix)} stations → {len(pix)} unique pixels "
        f"(median dist {pixel_map['dist_deg'].median():.3f}°)",
        flush=True,
    )

    lat_da = xr.DataArray(pix["grid_lat"].to_numpy(dtype=float), dims="pixel")
    lon_da = xr.DataArray(pix["grid_lon"].to_numpy(dtype=float), dims="pixel")

    starts = pd.date_range(t0, t1, freq=f"{chunk_months}MS")
    if len(starts) == 0 or starts[0] > pd.Timestamp(t0):
        starts = pd.DatetimeIndex([pd.Timestamp(t0)]).append(starts)
    starts = starts[starts <= pd.Timestamp(t1)]
    frames: list[pd.DataFrame] = []
    for i, s in enumerate(starts):
        if i + 1 < len(starts):
            e = starts[i + 1] - pd.Timedelta(days=1)
        else:
            e = pd.Timestamp(t1)
        e = min(e, pd.Timestamp(t1))
        if s > e:
            continue
        a_s, b_s = s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")
        print(f"OC-Chl ARCO chunk {a_s}..{b_s}", flush=True)
        try:
            da = (
                ds["CHL"]
                .sel(time=slice(a_s, b_s))
                .sel(latitude=lat_da, longitude=lon_da, method="nearest")
                .load()
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  OC-Chl ARCO skip chunk {a_s}..{b_s}: {exc}", flush=True)
            continue
        times = pd.to_datetime(np.asarray(da.time.values)).tz_localize(None)
        vals = np.asarray(da.values, dtype=float)
        if vals.ndim == 1:
            vals = vals.reshape(len(times), 1)
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

    if not frames:
        return pd.DataFrame()
    daily_pix = pd.concat(frames, ignore_index=True)
    out = station_pix.merge(daily_pix, on=["pixel_id", "grid_lat", "grid_lon"], how="inner")
    return _finalize_daily(out)


def download_oc_chl_via_copernicusmarine(
    stations: pd.DataFrame,
    cfg: dict[str, Any],
    t0: str | None = None,
    t1: str | None = None,
    max_stations: int | None = None,
) -> pd.DataFrame:
    """Nearest-ocean-pixel daily CHL via copernicusmarine open_dataset."""
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

    print("OC-Chl CMEMS: loading ocean mask (1 day)…", flush=True)
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
        f"OC-Chl CMEMS: {len(station_pix)} stations → {len(pix)} unique pixels "
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
        print(f"OC-Chl CMEMS year {y} {a_s}..{b_s}", flush=True)
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
            print(f"  OC-Chl CMEMS skip year {y}: {exc}", flush=True)
            continue

        times = pd.to_datetime(np.asarray(da.time.values)).tz_localize(None)
        vals = np.asarray(da.values, dtype=float)
        for pi, prow in pix.iterrows():
            col = vals[:, pi] if vals.ndim == 2 else vals
            frames.append(
                pd.DataFrame(
                    {
                        "date": times,
                        "pixel_id": int(prow["pixel_id"]),
                        "grid_lat": float(prow["grid_lat"]),
                        "grid_lon": float(prow["grid_lon"]),
                        "chl": col,
                    }
                )
            )

    if not frames:
        return pd.DataFrame()
    daily_pix = pd.concat(frames, ignore_index=True)
    out = station_pix.merge(daily_pix, on=["pixel_id", "grid_lat", "grid_lon"], how="inner")
    return _finalize_daily(out)


def download_oc_chl_for_stations(
    stations: pd.DataFrame,
    cfg: dict[str, Any],
    t0: str | None = None,
    t1: str | None = None,
    max_stations: int | None = None,
    prefer_arco: bool = False,
    chunk_months: int = 6,
) -> pd.DataFrame:
    """Nearest-ocean-pixel daily CHL (mg m-3) per location_id.

    Tries copernicusmarine first unless prefer_arco=True. On auth/TLS failure,
    falls back to public CloudFerro ARCO zarr (zarr_format=2).
    """
    if prefer_arco:
        print("OC-Chl: prefer_arco=True → ARCO path", flush=True)
        return download_oc_chl_via_arco(
            stations, cfg, t0=t0, t1=t1, max_stations=max_stations, chunk_months=chunk_months
        )

    try:
        return download_oc_chl_via_copernicusmarine(
            stations, cfg, t0=t0, t1=t1, max_stations=max_stations
        )
    except Exception as exc:  # noqa: BLE001
        if not _is_auth_tls_failure(exc):
            # still try ARCO for any open_dataset failure that looks networky
            print(f"OC-Chl CMEMS failed ({type(exc).__name__}: {exc}); trying ARCO…", flush=True)
        else:
            print(
                f"OC-Chl CMEMS auth/TLS failure ({type(exc).__name__}); "
                "falling back to ARCO zarr…",
                flush=True,
            )
        return download_oc_chl_via_arco(
            stations, cfg, t0=t0, t1=t1, max_stations=max_stations, chunk_months=chunk_months
        )
