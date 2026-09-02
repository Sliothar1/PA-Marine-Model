"""Daily SST at HAB stations: NOAA OISST v2.1 (default) or Copernicus OSTIA L4."""
from __future__ import annotations

import time
from typing import Any

import pandas as pd

from pa_marine.erddap import ErddapError, griddap_csv, lon_to_oisst_360


def snap_oisst(x: float, origin: float = 0.125, step: float = 0.25) -> float:
    return origin + round((x - origin) / step) * step


def haversine_km(
    lat1: "Any", lon1: "Any", lat2: "Any", lon2: "Any", earth_radius_km: float = 6371.0
) -> "Any":
    """Great-circle distance in km. Accepts scalars or numpy arrays.

    Nearest-pixel selection previously used Euclidean distance in *degrees*, which
    treats 1 deg of longitude as costing the same as 1 deg of latitude. At Irish and
    Scottish latitudes 1 deg of longitude is only ~0.60 of 1 deg of latitude on the
    ground (66 km vs 111 km at 53.5N), so that metric over-penalises east-west
    displacement by ~1.7x. On the real Connemara station coordinates it mis-ranks
    ~14% of candidate pixel pairs, and can select an ocean pixel up to ~42 km
    farther away than one it rejected. That matters precisely where the ocean mask
    is anisotropic - i.e. in fjords and bays like Killary, where the only ocean
    pixels lie in one direction.
    """
    import numpy as np

    p1 = np.radians(np.asarray(lat1, dtype=float))
    p2 = np.radians(np.asarray(lat2, dtype=float))
    dphi = p2 - p1
    dlam = np.radians(np.asarray(lon2, dtype=float) - np.asarray(lon1, dtype=float))
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlam / 2) ** 2
    return 2.0 * earth_radius_km * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


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


def download_oisst_bbox_years(
    cfg: dict[str, Any],
    t0: str,
    t1: str,
    *,
    lat_min: float,
    lat_max: float,
    lon360_min: float,
    lon360_max: float,
    label: str = "bbox",
) -> pd.DataFrame:
    """OISST cube over a lat × lon360 window, year chunks (ERDDAP griddap)."""
    sst = cfg["sst"]
    z = sst.get("zlev", 0.0)
    # snap bounds onto the 0.25° OISST grid
    la0, la1 = snap_oisst(lat_min), snap_oisst(lat_max)
    lo0, lo1 = snap_oisst(lon360_min), snap_oisst(lon360_max)
    if la0 > la1:
        la0, la1 = la1, la0
    if lo0 > lo1:
        lo0, lo1 = lo1, lo0
    y0 = pd.Timestamp(t0).year
    y1 = pd.Timestamp(t1).year
    frames = []
    for y in range(y0, y1 + 1):
        a = max(pd.Timestamp(t0), pd.Timestamp(f"{y}-01-01")).strftime("%Y-%m-%d")
        b = min(pd.Timestamp(t1), pd.Timestamp(f"{y}-12-31")).strftime("%Y-%m-%d")
        q = (
            f"{sst['variable']}[({a}):1:({b})][({z}):1:({z})]"
            f"[({la0}):1:({la1})][({lo0}):1:({lo1})]"
            f",{sst['anomaly_variable']}[({a}):1:({b})][({z}):1:({z})]"
            f"[({la0}):1:({la1})][({lo0}):1:({lo1})]"
        )
        print(f"OISST {label} year {y} {a}..{b} lat[{la0},{la1}] lon360[{lo0},{lo1}]")
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


def download_oisst_irish_bbox_years(
    cfg: dict[str, Any],
    t0: str,
    t1: str,
) -> pd.DataFrame:
    """Tight Irish OISST cube: 51–56N, 349–355E (lon 0–360), year chunks."""
    return download_oisst_bbox_years(
        cfg,
        t0,
        t1,
        lat_min=51.125,
        lat_max=55.875,
        lon360_min=349.125,
        lon360_max=354.875,
        label="irish",
    )


def map_stations_to_nearest_oisst_ocean(
    stations: pd.DataFrame,
    cube: pd.DataFrame,
    *,
    max_dist_deg: float | None = None,
    max_dist_km: float | None = None,
) -> pd.DataFrame:
    """Map each location_id to the nearest OISST ocean pixel present in `cube`.

    Coastal snaps often land on land (NaN SST); use any finite-SST pixel in the cube
    as the ocean mask (typically one day is enough once the cube is loaded).

    Distance is great-circle km (see `haversine_km`). `max_dist_km` defaults to 60 km.
    `max_dist_deg` is accepted for backward compatibility and converted at 111 km/deg,
    but note the old degree gate was anisotropic: a threshold of 1.0 admitted pixels
    111 km away north-south yet only 66 km east-west at Irish latitudes.
    """
    import numpy as np

    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]].copy()
    # ocean = pixels with at least one finite SST in the cube
    pix = (
        cube.loc[np.isfinite(cube["sst"].to_numpy(dtype=float)), ["grid_lat", "grid_lon"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    if pix.empty:
        return pd.DataFrame(
            columns=[
                "location_id",
                "latitude",
                "longitude",
                "grid_lat",
                "grid_lon",
                "dist_km",
            ]
        )
    lat_g = pix["grid_lat"].to_numpy(dtype=float)
    lon_g = pix["grid_lon"].to_numpy(dtype=float)
    if max_dist_km is None:
        max_dist_km = 111.195 * max_dist_deg if max_dist_deg is not None else 60.0
    rows = []
    for row in uniq.itertuples(index=False):
        lon360 = lon_to_oisst_360(float(row.longitude))
        dist_km = haversine_km(float(row.latitude), lon360, lat_g, lon_g)
        j = int(np.argmin(dist_km))
        dist = float(dist_km[j])
        if dist > max_dist_km:
            print(
                f"OISST skip {row.location_id}: nearest ocean pixel {dist:.1f} km "
                f"> max_dist_km={max_dist_km:.1f}"
            )
            continue
        rows.append(
            {
                "location_id": row.location_id,
                "latitude": float(row.latitude),
                "longitude": float(row.longitude),
                "grid_lat": float(lat_g[j]),
                "grid_lon": float(lon_g[j]),
                "dist_km": dist,
            }
        )
    return pd.DataFrame(rows)


def download_oisst_for_stations_nearest_ocean(
    stations: pd.DataFrame,
    cfg: dict[str, Any],
    t0: str,
    t1: str,
    *,
    pad_deg: float = 0.5,
    max_dist_deg: float | None = None,
    max_dist_km: float | None = None,
    label: str = "stations",
) -> pd.DataFrame:
    """Download an OISST bbox covering stations, then extract nearest-ocean pixels.

    Preferred for Scotland / coastal sites where naive 0.25° snaps often hit land.
    """
    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]]
    if uniq.empty:
        return pd.DataFrame()
    lat_min = float(uniq["latitude"].min()) - pad_deg
    lat_max = float(uniq["latitude"].max()) + pad_deg
    lon360 = uniq["longitude"].map(lambda x: lon_to_oisst_360(float(x)))
    lon360_min = float(lon360.min()) - pad_deg
    lon360_max = float(lon360.max()) + pad_deg
    cube = download_oisst_bbox_years(
        cfg,
        t0,
        t1,
        lat_min=lat_min,
        lat_max=lat_max,
        lon360_min=lon360_min,
        lon360_max=lon360_max,
        label=label,
    )
    if cube.empty:
        return pd.DataFrame()
    # Ocean mask = pixels with finite SST on the best-covered day in the cube
    import numpy as np

    tmp = cube.assign(_ok=np.isfinite(cube["sst"].to_numpy(dtype=float)))
    cov = tmp.groupby("date")["_ok"].mean()
    if cov.empty or float(cov.max()) <= 0:
        return pd.DataFrame()
    best_day = cov.idxmax()
    day = cube.loc[cube["date"] == best_day]
    pixel_map = map_stations_to_nearest_oisst_ocean(
        uniq, day, max_dist_deg=max_dist_deg, max_dist_km=max_dist_km
    )
    if pixel_map.empty:
        return pd.DataFrame()
    print(
        f"OISST {label}: {len(pixel_map)} stations → "
        f"{pixel_map.groupby(['grid_lat','grid_lon']).ngroups} ocean pixels "
        f"(median dist {pixel_map['dist_km'].median():.1f} km)"
    )
    out = cube.merge(
        pixel_map[["location_id", "latitude", "longitude", "grid_lat", "grid_lon", "dist_km"]],
        on=["grid_lat", "grid_lon"],
        how="inner",
    )
    out = out.rename(columns={"latitude": "request_lat", "longitude": "request_lon"})
    # No ocean mask on this path: report so land-snapped stations are not silent.
    sst_coverage_report(out, label="OISST (naive 0.25deg snap, no ocean mask)")
    return out[
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
        # great-circle km, not Euclidean degrees: see haversine_km
        dist = haversine_km(float(row.latitude), float(row.longitude), lat_grid, lon_grid)
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
                "dist_km": float(dist[i, j]),
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
        f"(median dist {pixel_map['dist_km'].median():.1f} km)"
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


def sst_coverage_report(sst: pd.DataFrame, label: str = "SST") -> pd.DataFrame:
    """Per-station SST availability, with a loud warning for land-snapped stations.

    The default Irish path (`_download_oisst_for_stations`) snaps each station to
    whichever 0.25 deg OISST pixel contains it, with **no ocean mask**. Inshore Irish
    HAB stations - fjords, bays, harbours - frequently snap onto a land pixel, whose
    SST is NaN for the entire record. Nothing in the pipeline previously reported
    this: those stations still carry HAB labels, so they contribute station-weeks
    whose SST/MHW features are entirely missing and get median-imputed (logreg) or
    routed down the NaN branch (LightGBM/HistGB).

    That is a plausible partial explanation for the project's own findings that
    week-of-year and lat/lon dominate feature importance while MHW features look
    like noise: for an unknown share of stations there is simply no SST to learn
    from. `data/processed/connemara_farms_stations.csv` already documents one such
    case (Rosmuc). Use `--ocean-mask` on `compute_mhw.py` to snap to the nearest
    ocean pixel instead.
    """
    import numpy as np

    if sst.empty or "location_id" not in sst.columns:
        print(f"{label}: empty frame, nothing to report")
        return pd.DataFrame()
    g = sst.groupby("location_id")["sst"].agg(
        n_days="size",
        n_finite=lambda x: int(np.isfinite(x.to_numpy(dtype=float)).sum()),
    )
    g["finite_frac"] = g["n_finite"] / g["n_days"]
    g = g.sort_values("finite_frac")
    dead = g.index[g["n_finite"] == 0].tolist()
    thin = g.index[(g["n_finite"] > 0) & (g["finite_frac"] < 0.5)].tolist()
    print(
        f"{label} coverage: {len(g)} stations, "
        f"median finite fraction {g['finite_frac'].median():.3f}"
    )
    if dead:
        print(
            f"  !! {len(dead)} station(s) have NO finite SST at all (land-snapped pixel): "
            f"{dead[:12]}{' ...' if len(dead) > 12 else ''}"
        )
        print(
            "     These still carry HAB labels, so their SST/MHW features are fully "
            "missing/imputed. Re-run with an ocean mask."
        )
    if thin:
        print(f"  !  {len(thin)} station(s) below 50% finite SST: {thin[:12]}")
    if not dead and not thin:
        print("  all stations have usable SST coverage")
    return g.reset_index()
