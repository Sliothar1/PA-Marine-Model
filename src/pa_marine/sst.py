"""Daily SST at HAB stations: NOAA OISST v2.1 (default) or Copernicus OSTIA L4."""
from __future__ import annotations

import time
from typing import Any

import pandas as pd

from pa_marine.erddap import ErddapError, griddap_csv, lon_to_oisst_360


def snap_oisst(x: float, origin: float = 0.125, step: float = 0.25) -> float:
    return origin + round((x - origin) / step) * step


def download_oisst_point(
    cfg: dict[str, Any],
    lat: float,
    lon: float,
    t0: str,
    t1: str,
) -> pd.DataFrame:
    sst = cfg["sst"]
    lon360 = lon_to_oisst_360(lon)
    la = snap_oisst(lat)
    lo = snap_oisst(lon360)
    z = sst.get("zlev", 0.0)
    q = (
        f"{sst['variable']}[({t0}):1:({t1})][({z}):1:({z})]"
        f"[({la}):1:({la})][({lo}):1:({lo})]"
        f",{sst['anomaly_variable']}[({t0}):1:({t1})][({z}):1:({z})]"
        f"[({la}):1:({la})][({lo}):1:({lo})]"
    )
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            df = griddap_csv(sst["erddap_base"], sst["dataset_id"], q, timeout=300)
            break
        except (ErddapError, OSError, TimeoutError) as exc:
            last_err = exc
            time.sleep(2 ** attempt)
    else:
        raise last_err  # type: ignore[misc]
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df["date"] = df["time"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    df = df.rename(columns={sst["variable"]: "sst", sst["anomaly_variable"]: "anom"})
    df["request_lat"] = lat
    df["request_lon"] = lon
    df["grid_lat"] = la
    df["grid_lon"] = lo
    return df[["date", "sst", "anom", "request_lat", "request_lon", "grid_lat", "grid_lon"]]


def download_oisst_irish_bbox_years(
    cfg: dict[str, Any],
    t0: str,
    t1: str,
) -> pd.DataFrame:
    """Tight Irish OISST cube: 51–56N, 349–355E (lon 0–360), year chunks."""
    sst = cfg["sst"]
    z = sst.get("zlev", 0.0)
    y0 = pd.Timestamp(t0).year
    y1 = pd.Timestamp(t1).year
    frames = []
    for y in range(y0, y1 + 1):
        a = max(pd.Timestamp(t0), pd.Timestamp(f"{y}-01-01")).strftime("%Y-%m-%d")
        b = min(pd.Timestamp(t1), pd.Timestamp(f"{y}-12-31")).strftime("%Y-%m-%d")
        q = (
            f"{sst['variable']}[({a}):1:({b})][({z}):1:({z})]"
            f"[(51.125):1:(55.875)][(349.125):1:(354.875)]"
            f",{sst['anomaly_variable']}[({a}):1:({b})][({z}):1:({z})]"
            f"[(51.125):1:(55.875)][(349.125):1:(354.875)]"
        )
        print(f"OISST bbox year {y} {a}..{b}")
        last_err: Exception | None = None
        df = None
        for attempt in range(5):
            try:
                df = griddap_csv(sst["erddap_base"], sst["dataset_id"], q, timeout=300)
                break
            except (ErddapError, OSError, TimeoutError) as exc:
                last_err = exc
                print(f"  retry {attempt+1}: {exc}")
                time.sleep(2 ** attempt)
        if df is None:
            print(f"OISST skip year {y}: {last_err}")
            continue
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    cube = pd.concat(frames, ignore_index=True)
    cube["time"] = pd.to_datetime(cube["time"], utc=True, errors="coerce")
    cube["date"] = cube["time"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    cube = cube.rename(
        columns={
            sst["variable"]: "sst",
            sst["anomaly_variable"]: "anom",
            "latitude": "grid_lat",
            "longitude": "grid_lon",
        }
    )
    return cube[["date", "sst", "anom", "grid_lat", "grid_lon"]]


def _download_oisst_for_stations(
    stations: pd.DataFrame,
    cfg: dict[str, Any],
    t0: str,
    t1: str,
    max_stations: int | None = None,
) -> pd.DataFrame:
    """Nearest-neighbour OISST time series per unique location_id."""
    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]]
    if max_stations is not None:
        uniq = uniq.head(max_stations)
        frames = []
        for row in uniq.itertuples(index=False):
            try:
                d = download_oisst_point(cfg, float(row.latitude), float(row.longitude), t0, t1)
            except Exception as exc:  # noqa: BLE001
                print(f"OISST skip {row.location_id}: {exc}")
                continue
            d["location_id"] = row.location_id
            frames.append(d)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    cube = download_oisst_irish_bbox_years(cfg, t0, t1)
    if cube.empty:
        return pd.DataFrame()
    uniq = uniq.copy()
    uniq["grid_lat"] = uniq["latitude"].map(lambda x: snap_oisst(float(x)))
    uniq["grid_lon"] = uniq["longitude"].map(lambda x: snap_oisst(lon_to_oisst_360(float(x))))
    # keep only pixels present in cube
    pix = cube[["grid_lat", "grid_lon"]].drop_duplicates()
    merged_map = uniq.merge(pix, on=["grid_lat", "grid_lon"], how="inner")
    missing = set(uniq["location_id"]) - set(merged_map["location_id"])
    for loc in missing:
        print(f"OISST skip {loc}: pixel outside bbox")
    out = cube.merge(
        merged_map[["location_id", "latitude", "longitude", "grid_lat", "grid_lon"]],
        on=["grid_lat", "grid_lon"],
        how="inner",
    )
    out = out.rename(columns={"latitude": "request_lat", "longitude": "request_lon"})
    return out


# ---------------------------------------------------------------------------
# Copernicus OSTIA L4 reprocessed (~0.05°)
# ---------------------------------------------------------------------------

def snap_ostia(x: float, origin: float = -179.975, step: float = 0.05) -> float:
    return origin + round((x - origin) / step) * step


def _require_copernicusmarine():
    try:
        import copernicusmarine  # noqa: F401
        import xarray  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "copernicusmarine and xarray are required for OSTIA downloads "
            "(pip install 'pa-marine[ostia]' or copernicusmarine xarray)"
        ) from exc
    import copernicusmarine as cm

    return cm


def _ostia_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    ostia = dict(cfg.get("sst", {}).get("copernicus_ostia") or {})
    ostia.setdefault("product", "SST_GLO_SST_L4_REP_OBSERVATIONS_010_011")
    ostia.setdefault("dataset_id", "METOFFICE-GLO-SST-L4-REP-OBS-SST")
    ostia.setdefault("variable", "analysed_sst")
    ostia.setdefault("service", "timeseries")
    ostia.setdefault("kelvin_to_celsius", True)
    return ostia


def _nearest_ocean_pixel_map(
    stations: pd.DataFrame,
    mask_sst: "Any",  # xarray.DataArray lat×lon
) -> pd.DataFrame:
    """Map each station to the nearest finite (ocean) OSTIA pixel."""
    import numpy as np

    lats = np.asarray(mask_sst.latitude.values, dtype=float)
    lons = np.asarray(mask_sst.longitude.values, dtype=float)
    ocean = np.isfinite(np.asarray(mask_sst.values, dtype=float))
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
    rows = []
    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]]
    for row in uniq.itertuples(index=False):
        dist = (lat_grid - float(row.latitude)) ** 2 + (lon_grid - float(row.longitude)) ** 2
        dist = np.where(ocean, dist, np.inf)
        if not np.isfinite(dist).any():
            print(f"OSTIA skip {row.location_id}: no ocean pixel in mask bbox")
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


def download_ostia_for_stations(
    stations: pd.DataFrame,
    cfg: dict[str, Any],
    t0: str,
    t1: str,
    max_stations: int | None = None,
) -> pd.DataFrame:
    """Nearest-ocean-pixel OSTIA foundation SST (°C) per location_id.

    Uses the Copernicus Marine Python API (`open_dataset`, timeseries/ARCO)
    and extracts only unique station pixels (much smaller than a full Irish cube).
    Credentials: existing `~/.copernicusmarine` login (never printed).
    """
    import numpy as np
    import xarray as xr

    cm = _require_copernicusmarine()
    ostia = _ostia_cfg(cfg)
    # Callers reach this via --provider ostia / download_sst_for_stations dispatch.
    # Config flag documents default enablement; do not block explicit pulls.
    if not ostia.get("enabled", False):
        print("NOTE: sst.copernicus_ostia.enabled is false; proceeding with explicit OSTIA pull")

    domain = cfg.get("domain", {})
    lat_min = float(domain.get("lat_min", 51.0)) - 0.1
    lat_max = float(domain.get("lat_max", 56.0)) + 0.1
    lon_min = float(domain.get("lon_min", -11.0)) - 0.1
    lon_max = float(domain.get("lon_max", -5.0)) + 0.1

    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]].copy()
    if max_stations is not None:
        uniq = uniq.head(max_stations)

    print("OSTIA: loading ocean mask (1 day)…")
    mask_ds = cm.open_dataset(
        dataset_id=ostia["dataset_id"],
        variables=[ostia["variable"]],
        minimum_longitude=lon_min,
        maximum_longitude=lon_max,
        minimum_latitude=lat_min,
        maximum_latitude=lat_max,
        start_datetime="2020-06-15",
        end_datetime="2020-06-15",
        service=ostia.get("service", "timeseries"),
    )
    mask_da = mask_ds[ostia["variable"]].isel(time=0).load()
    pixel_map = _nearest_ocean_pixel_map(uniq, mask_da)
    if pixel_map.empty:
        return pd.DataFrame()

    # Stable unique pixel list + station→pixel_id map
    pix = (
        pixel_map[["grid_lat", "grid_lon"]]
        .drop_duplicates()
        .reset_index(drop=True)
        .reset_index(names="pixel_id")
    )
    station_pix = pixel_map.merge(pix, on=["grid_lat", "grid_lon"], how="inner")
    print(
        f"OSTIA: {len(station_pix)} stations → {len(pix)} unique ocean pixels "
        f"(median dist {pixel_map['dist_deg'].median():.3f}°)"
    )

    y0 = pd.Timestamp(t0).year
    y1 = pd.Timestamp(t1).year
    hard_end = pd.Timestamp(ostia.get("t1_cap", "2026-03-31"))
    frames: list[pd.DataFrame] = []
    lat_da = xr.DataArray(pix["grid_lat"].to_numpy(dtype=float), dims="pixel")
    lon_da = xr.DataArray(pix["grid_lon"].to_numpy(dtype=float), dims="pixel")

    for y in range(y0, y1 + 1):
        a = max(pd.Timestamp(t0), pd.Timestamp(f"{y}-01-01"))
        b = min(pd.Timestamp(t1), pd.Timestamp(f"{y}-12-31"), hard_end)
        if a > b:
            continue
        a_s, b_s = a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")
        print(f"OSTIA pixels year {y} {a_s}..{b_s}")
        try:
            ds = cm.open_dataset(
                dataset_id=ostia["dataset_id"],
                variables=[ostia["variable"]],
                minimum_longitude=float(pix["grid_lon"].min() - 0.05),
                maximum_longitude=float(pix["grid_lon"].max() + 0.05),
                minimum_latitude=float(pix["grid_lat"].min() - 0.05),
                maximum_latitude=float(pix["grid_lat"].max() + 0.05),
                start_datetime=a_s,
                end_datetime=b_s,
                service=ostia.get("service", "timeseries"),
            )
            da = (
                ds[ostia["variable"]]
                .sel(latitude=lat_da, longitude=lon_da, method="nearest")
                .load()
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  OSTIA skip year {y}: {exc}")
            continue

        times = pd.to_datetime(np.asarray(da.time.values)).tz_localize(None)
        # Keep *requested* grid coords (nearest may equal them); index by pixel dim order
        vals = np.asarray(da.values, dtype=float)  # (time, pixel)
        if ostia.get("kelvin_to_celsius", True):
            vals = vals - 273.15
        n_t, n_p = vals.shape
        assert n_p == len(pix), (n_p, len(pix))
        pixel_daily = pd.DataFrame(
            {
                "date": np.repeat(times, n_p),
                "sst": vals.reshape(-1),
                "pixel_id": np.tile(pix["pixel_id"].to_numpy(), n_t),
                "grid_lat": np.tile(pix["grid_lat"].to_numpy(), n_t),
                "grid_lon": np.tile(pix["grid_lon"].to_numpy(), n_t),
            }
        )
        part = pixel_daily.merge(
            station_pix[
                ["location_id", "request_lat", "request_lon", "pixel_id", "grid_lat", "grid_lon"]
            ],
            on=["pixel_id", "grid_lat", "grid_lon"],
            how="inner",
        )
        part["anom"] = np.nan
        frames.append(
            part[
                [
                    "date",
                    "sst",
                    "anom",
                    "grid_lat",
                    "grid_lon",
                    "location_id",
                    "request_lat",
                    "request_lon",
                ]
            ]
        )
        print(f"  rows={len(part)} nan_sst={float(np.isnan(part['sst']).mean()):.3f}")

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out = out.drop_duplicates(["location_id", "date"])
    return out

def download_sst_for_stations(
    stations: pd.DataFrame,
    cfg: dict[str, Any],
    t0: str,
    t1: str,
    max_stations: int | None = None,
    provider: str | None = None,
) -> pd.DataFrame:
    """Dispatch SST download by provider (OISST default, or OSTIA)."""
    prov = (provider or cfg.get("sst", {}).get("provider") or "ncdcOisst21Agg").lower()
    if prov in {"ostia", "copernicus_ostia", "cmems_ostia"}:
        return download_ostia_for_stations(stations, cfg, t0, t1, max_stations)
    # default: NOAA OISST (existing implementation below was renamed — see wrapper)
    return _download_oisst_for_stations(stations, cfg, t0, t1, max_stations)
