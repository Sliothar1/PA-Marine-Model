"""Daily SST at HAB stations from NOAA OISST v2.1 (ncdcOisst21Agg)."""
from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from pa_marine.erddap import griddap_csv, lon_to_oisst_360


def download_oisst_point(
    cfg: dict[str, Any],
    lat: float,
    lon: float,
    t0: str,
    t1: str,
) -> pd.DataFrame:
    sst = cfg["sst"]
    lon360 = lon_to_oisst_360(lon)
    # nearest 0.25° grid (OISST centres at *.125 / *.375 / *.625 / *.875)
    def snap(x, origin=0.125, step=0.25):
        return origin + round((x - origin) / step) * step

    la = snap(lat)
    lo = snap(lon360)
    z = sst.get("zlev", 0.0)
    q = (
        f"{sst['variable']}[({t0}):1:({t1})][({z}):1:({z})]"
        f"[({la}):1:({la})][({lo}):1:({lo})]"
        f",{sst['anomaly_variable']}[({t0}):1:({t1})][({z}):1:({z})]"
        f"[({la}):1:({la})][({lo}):1:({lo})]"
    )
    df = griddap_csv(sst["erddap_base"], sst["dataset_id"], q)
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df["date"] = df["time"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    df = df.rename(columns={sst["variable"]: "sst", sst["anomaly_variable"]: "anom"})
    df["request_lat"] = lat
    df["request_lon"] = lon
    df["grid_lat"] = la
    df["grid_lon"] = lo
    return df[["date", "sst", "anom", "request_lat", "request_lon", "grid_lat", "grid_lon"]]


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
        except Exception as exc:  # noqa: BLE001 — keep remaining stations
            print(f"OISST skip {row.location_id}: {exc}")
            continue
        d["location_id"] = row.location_id
        frames.append(d)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
