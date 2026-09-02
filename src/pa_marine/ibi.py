"""IBI multi-year physics + BGC optics at Irish HAB station pixels (Copernicus Marine).

Downloads compact station-pixel daily series (not full cubes) for:
- mlotst (MLD), rsntds (net shortwave), so (surface SSS)
- kd / zeu (light attenuation / euphotic depth) from IBI BGC optics
- optional detided surface currents uo_detided / vo_detided

Credentials: existing ~/.copernicusmarine login (never printed).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from pa_marine.sst import haversine_km


def _require_cm():
    try:
        import copernicusmarine as cm
        import xarray  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "copernicusmarine and xarray required for IBI downloads "
            "(pip install copernicusmarine xarray)"
        ) from exc
    return cm


def _ibi_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    ibi = dict(cfg.get("ibi") or {})
    ibi.setdefault("service", "timeseries")
    ibi.setdefault("t0", "2002-01-01")
    ibi.setdefault("t1", "2024-12-31")
    ibi.setdefault(
        "datasets",
        {
            "mlotst": {
                "dataset_id": "cmems_mod_ibi_phy-mld_my_0.027deg_P1D-m",
                "variables": ["mlotst"],
            },
            "rsntds": {
                "dataset_id": "cmems_mod_ibi_phy-hflux_my_0.027deg_P1D-m",
                "variables": ["rsntds"],
            },
            "so": {
                "dataset_id": "cmems_mod_ibi_phy-sal_my_0.027deg_P1D-m",
                "variables": ["so"],
                "surface": True,
            },
            "optics": {
                "dataset_id": "cmems_mod_ibi_bgc-optics_my_0.027deg_P1D-m",
                "variables": ["kd", "zeu"],
                "surface": True,
            },
            "currents": {
                "dataset_id": "cmems_mod_ibi_phy-cur_my_detided-0.027deg_P1D-m",
                "variables": ["uo_detided", "vo_detided"],
            },
        },
    )
    return ibi


def _nearest_ocean_pixel_map(stations: pd.DataFrame, mask_da: Any) -> pd.DataFrame:
    """Map each station to nearest finite ocean pixel on an IBI lat×lon field."""
    lats = np.asarray(mask_da.latitude.values, dtype=float)
    lons = np.asarray(mask_da.longitude.values, dtype=float)
    vals = np.asarray(mask_da.values, dtype=float)
    # mask may be (lat, lon) or (depth, lat, lon)
    while vals.ndim > 2:
        vals = vals[0]
    ocean = np.isfinite(vals)
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
    rows = []
    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]]
    for row in uniq.itertuples(index=False):
        dist = haversine_km(float(row.latitude), float(row.longitude), lat_grid, lon_grid)
        dist = np.where(ocean, dist, np.inf)
        if not np.isfinite(dist).any():
            print(f"IBI skip {row.location_id}: no ocean pixel in mask bbox")
            continue
        i, j = np.unravel_index(int(np.argmin(dist)), dist.shape)
        rows.append(
            {
                "location_id": row.location_id,
                "request_lat": float(row.latitude),
                "request_lon": float(row.longitude),
                "grid_lat": float(lats[i]),
                "grid_lon": float(lons[j]),
                "dist_km": float(dist[i, j]),
            }
        )
    return pd.DataFrame(rows)


def _domain_pad(cfg: dict[str, Any], pad: float = 0.15) -> tuple[float, float, float, float]:
    domain = cfg.get("domain", {})
    return (
        float(domain.get("lon_min", -11.0)) - pad,
        float(domain.get("lon_max", -5.0)) + pad,
        float(domain.get("lat_min", 51.0)) - pad,
        float(domain.get("lat_max", 56.0)) + pad,
    )


def _surface_isel(da: Any) -> Any:
    """Select surface / first depth if present."""
    if "depth" in getattr(da, "dims", ()):
        return da.isel(depth=0)
    return da


def download_ibi_group_for_stations(
    stations: pd.DataFrame,
    cfg: dict[str, Any],
    group: str,
    t0: str | None = None,
    t1: str | None = None,
    max_stations: int | None = None,
) -> pd.DataFrame:
    """Download one IBI variable group at unique station pixels (year chunks)."""
    import xarray as xr

    cm = _require_cm()
    ibi = _ibi_cfg(cfg)
    spec = ibi["datasets"][group]
    dataset_id = spec["dataset_id"]
    variables = list(spec["variables"])
    surface = bool(spec.get("surface", False))
    service = ibi.get("service", "timeseries")
    t0 = t0 or ibi["t0"]
    t1 = t1 or ibi["t1"]

    lon_min, lon_max, lat_min, lat_max = _domain_pad(cfg)
    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]].copy()
    if max_stations is not None:
        uniq = uniq.head(max_stations)

    print(f"IBI[{group}]: loading ocean mask…", flush=True)
    depth_kw = {}
    if surface or any(v in {"kd", "zeu", "so"} for v in variables):
        depth_kw = {"minimum_depth": 0.0, "maximum_depth": 1.0}
    mask_ds = cm.open_dataset(
        dataset_id=dataset_id,
        variables=[variables[0]],
        minimum_longitude=lon_min,
        maximum_longitude=lon_max,
        minimum_latitude=lat_min,
        maximum_latitude=lat_max,
        start_datetime="2020-06-15",
        end_datetime="2020-06-15",
        service=service,
        **depth_kw,
    )
    mask_da = _surface_isel(mask_ds[variables[0]].isel(time=0)).load()
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
        f"IBI[{group}]: {len(station_pix)} stations → {len(pix)} pixels "
        f"(median dist {pixel_map['dist_km'].median():.1f} km)",
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
        print(f"IBI[{group}] year {y} {a_s}..{b_s}", flush=True)
        try:
            depth_kw = {}
            if surface or any(v in {"kd", "zeu", "so"} for v in variables):
                # surface-only: avoid pulling 50-level 3D cubes
                depth_kw = {"minimum_depth": 0.0, "maximum_depth": 1.0}
            ds = cm.open_dataset(
                dataset_id=dataset_id,
                variables=variables,
                minimum_longitude=float(pix["grid_lon"].min() - 0.05),
                maximum_longitude=float(pix["grid_lon"].max() + 0.05),
                minimum_latitude=float(pix["grid_lat"].min() - 0.05),
                maximum_latitude=float(pix["grid_lat"].max() + 0.05),
                start_datetime=a_s,
                end_datetime=b_s,
                service=service,
                **depth_kw,
            )
            data = {}
            times = None
            for v in variables:
                da = ds[v]
                if surface or "depth" in da.dims:
                    da = _surface_isel(da)
                da = da.sel(latitude=lat_da, longitude=lon_da, method="nearest").load()
                if times is None:
                    times = pd.to_datetime(np.asarray(da.time.values)).tz_localize(None)
                data[v] = np.asarray(da.values, dtype=float)
        except Exception as exc:  # noqa: BLE001
            print(f"  IBI[{group}] skip year {y}: {exc}")
            continue

        assert times is not None
        n_t = len(times)
        n_p = len(pix)
        # rename detided currents to shorter names used as features
        rename = {"uo_detided": "uo", "vo_detided": "vo"}
        colmap = {v: rename.get(v, v) for v in variables}
        base = {
            "date": np.repeat(times, n_p),
            "pixel_id": np.tile(pix["pixel_id"].to_numpy(), n_t),
            "grid_lat": np.tile(pix["grid_lat"].to_numpy(), n_t),
            "grid_lon": np.tile(pix["grid_lon"].to_numpy(), n_t),
        }
        for v in variables:
            vals = data[v]
            if vals.ndim == 1:
                vals = vals.reshape(n_t, 1)
            base[colmap[v]] = vals.reshape(-1)
        pixel_daily = pd.DataFrame(base)
        part = pixel_daily.merge(
            station_pix[
                ["location_id", "request_lat", "request_lon", "pixel_id", "grid_lat", "grid_lon"]
            ],
            on=["pixel_id", "grid_lat", "grid_lon"],
            how="inner",
        )
        keep = ["date", "location_id", "request_lat", "request_lon", "grid_lat", "grid_lon"] + [
            colmap[v] for v in variables
        ]
        frames.append(part[keep])
        nan_frac = float(np.isnan(part[colmap[variables[0]]]).mean())
        print(f"  rows={len(part)} nan_{colmap[variables[0]]}={nan_frac:.3f}", flush=True)

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out = out.drop_duplicates(["location_id", "date"])
    if "uo" in out.columns and "vo" in out.columns:
        out["current_speed"] = np.sqrt(out["uo"] ** 2 + out["vo"] ** 2)
    return out


def download_ibi_for_stations(
    stations: pd.DataFrame,
    cfg: dict[str, Any],
    groups: list[str] | None = None,
    t0: str | None = None,
    t1: str | None = None,
    max_stations: int | None = None,
) -> pd.DataFrame:
    """Download and outer-merge IBI groups onto location_id × date."""
    ibi = _ibi_cfg(cfg)
    groups = groups or ["mlotst", "rsntds", "optics", "so"]
    merged: pd.DataFrame | None = None
    meta_cols = {"request_lat", "request_lon", "grid_lat", "grid_lon"}
    for g in groups:
        if g not in ibi["datasets"]:
            raise KeyError(f"Unknown IBI group {g}; known={list(ibi['datasets'])}")
        part = download_ibi_group_for_stations(
            stations, cfg, g, t0=t0, t1=t1, max_stations=max_stations
        )
        if part.empty:
            print(f"IBI[{g}]: empty")
            continue
        value_cols = [
            c
            for c in part.columns
            if c not in {"date", "location_id"} | meta_cols
        ]
        slim = part[["location_id", "date"] + value_cols].copy()
        if merged is None:
            # keep one copy of request/grid from first non-empty group
            merged = part[["location_id", "date"] + sorted(meta_cols & set(part.columns)) + value_cols].copy()
        else:
            merged = merged.merge(slim, on=["location_id", "date"], how="outer")
    return merged if merged is not None else pd.DataFrame()
