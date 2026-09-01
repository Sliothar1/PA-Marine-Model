"""Daily SST at HAB stations from NOAA OISST v2.1 (ncdcOisst21Agg)."""
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


def download_sst_for_stations(
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
