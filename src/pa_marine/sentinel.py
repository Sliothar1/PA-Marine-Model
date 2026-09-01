"""Connemara sentinel buoy ingest (Mace Head + Lehanagh Pool).

Schemas verified 2026-09-01 via ERDDAP info.json + small CSV pulls on
erddap.marine.ie. NRT feeds are raw (not fully QC'd). Delayed-mode QC for
Mace Head SBE37 is dataset sbe37_macehead (2018-06 .. 2022-03).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from pa_marine.erddap import tabledap_csv

ERDDAP_BASE = "https://erddap.marine.ie/erddap"

# Nominal buoy positions (match NC_GLOBAL geospatial_*).
BUOY_SITES = {
    "mace_head": {
        "label": "Mace Head",
        "dataset_id": "compass_mace_head",
        "qc_dataset_id": "sbe37_macehead",
        "lat": 53.3306,
        "lon": -9.9326,
        "t0": "2018-05-01",
        "variables": [
            "time",
            "latitude",
            "longitude",
            "depth",
            "sbe_temp_avg",
            "sbe_salinity_avg",
            "sbe_do_avg",
            "suna_nitrate_conc_avg",
            "sami_ph_avg",
            "seafet_ph_ext_avg",
            "contros_pco2_avg",
            "wind_speed",
            "wind_direction",
            "wind_gust",
            "air_temperature",
            "air_pressure",
        ],
        "qc_variables": [
            "time",
            "latitude",
            "longitude",
            "depth",
            "temperature",
            "salinity",
            "oxygen",
            "temperature_qc",
            "salinity_qc",
            "oxygen_qc",
        ],
        # Canonical daily columns after rename.
        "rename": {
            "sbe_temp_avg": "temp_c",
            "sbe_salinity_avg": "salinity",
            "sbe_do_avg": "do_mg_l",
            "suna_nitrate_conc_avg": "nitrate_umol_l",
            "sami_ph_avg": "ph_sami",
            "seafet_ph_ext_avg": "ph_seafet",
            "contros_pco2_avg": "pco2_uatm",
            "wind_speed": "wind_speed_ms",
            "wind_direction": "wind_dir_deg",
            "wind_gust": "wind_gust_ms",
            "air_temperature": "air_temp_c",
            "air_pressure": "air_pressure_mbar",
        },
    },
    "lehanagh": {
        "label": "Lehanagh Pool",
        "dataset_id": "sentinel_lehanagh",
        "qc_dataset_id": None,
        "lat": 53.4001,
        "lon": -9.8207,
        "t0": "2024-05-27",
        "variables": [
            "time",
            "latitude",
            "longitude",
            "depth",
            "SBE_Temp_Avg",
            "SBE_Salinity_Avg",
            "SBE_DO_Avg",
            "EXO2_Temperature",
            "EXO2_Salinity",
            "EXO2_RDO_Concentration",
            "EXO2_RDO_Saturation",
            "EXO2_Chlorophyll_ug",
            "EXO2_Chlorophyll_RFU",
            "EXO2_Phycoerythrin",
            "EXO2_Turbidity",
            "Wind_Speed",
            "Wind_Direction",
            "Wind_Gust",
            "Air_Temperature",
            "Air_Pressure",
        ],
        "rename": {
            "SBE_Temp_Avg": "temp_c",
            "SBE_Salinity_Avg": "salinity",
            "SBE_DO_Avg": "do_mg_l",
            "EXO2_Temperature": "exo_temp_c",
            "EXO2_Salinity": "exo_salinity",
            "EXO2_RDO_Concentration": "exo_do_mg_l",
            "EXO2_RDO_Saturation": "exo_do_sat_pct",
            "EXO2_Chlorophyll_ug": "chl_ug_l",
            "EXO2_Chlorophyll_RFU": "chl_rfu",
            "EXO2_Phycoerythrin": "phycoerythrin",
            "EXO2_Turbidity": "turbidity_ntu",
            "Wind_Speed": "wind_speed_ms",
            "Wind_Direction": "wind_dir_deg",
            "Wind_Gust": "wind_gust_ms",
            "Air_Temperature": "air_temp_c",
            "Air_Pressure": "air_pressure_mbar",
        },
    },
}


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(
        np.radians,
        [np.asarray(lat1, float), np.asarray(lon1, float), np.asarray(lat2, float), np.asarray(lon2, float)],
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def _year_chunks(t0: str, t1: str | None = None) -> list[tuple[str, str]]:
    start = pd.Timestamp(t0, tz="UTC")
    end = pd.Timestamp(t1 or "2026-08-31", tz="UTC")
    chunks = []
    y = start.year
    while y <= end.year:
        a = max(start, pd.Timestamp(f"{y}-01-01", tz="UTC"))
        b = min(end, pd.Timestamp(f"{y}-12-31 23:59:59", tz="UTC"))
        chunks.append((a.strftime("%Y-%m-%dT%H:%M:%SZ"), b.strftime("%Y-%m-%dT%H:%M:%SZ")))
        y += 1
    return chunks


def download_dataset(
    dataset_id: str,
    variables: Iterable[str],
    t0: str,
    t1: str | None = None,
    out_csv: str | Path | None = None,
    base: str = ERDDAP_BASE,
    timeout: int = 600,
) -> pd.DataFrame:
    """Download tabledap in yearly chunks; optionally write concatenated CSV."""
    frames = []
    for a, b in _year_chunks(t0, t1):
        cons = [f"time>={a}", f"time<={b}"]
        print(f"  {dataset_id} {a[:10]}..{b[:10]} ...", flush=True)
        try:
            part = tabledap_csv(base, dataset_id, variables, cons, timeout=timeout)
        except Exception as e:
            msg = str(e)
            if "404" in msg or "nRows = 0" in msg:
                print(f"    empty/skip: {msg[:120]}")
                continue
            raise
        if part is None or part.empty:
            continue
        frames.append(part)
        print(f"    rows={len(part)}")
    if not frames:
        df = pd.DataFrame(columns=list(variables))
    else:
        df = pd.concat(frames, ignore_index=True)
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df = df.dropna(subset=["time"]).sort_values("time").drop_duplicates(subset=["time"], keep="last")
    if out_csv:
        Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_csv, index=False)
    return df


def daily_aggregate(raw: pd.DataFrame, rename: dict[str, str]) -> pd.DataFrame:
    """Mean of numeric sensor columns by UTC calendar day."""
    if raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.dropna(subset=["time"])
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df["date"] = df["time"].dt.floor("D")
    value_cols = [c for c in rename.values() if c in df.columns]
    meta = {}
    if "latitude" in df.columns:
        meta["latitude"] = ("latitude", "median")
    if "longitude" in df.columns:
        meta["longitude"] = ("longitude", "median")
    agg = {c: "mean" for c in value_cols}
    agg["n_obs"] = ("time", "size")
    for k, v in meta.items():
        agg[k] = v
    # pandas named agg needs column present
    out = df.groupby("date", as_index=False).agg(**{k: v if isinstance(v, tuple) else (k, v) for k, v in {
        **{c: (c, "mean") for c in value_cols},
        "n_obs": ("time", "size"),
        **{k: v for k, v in meta.items()},
    }.items()})
    return out.sort_values("date").reset_index(drop=True)


def nearest_hab_stations(
    panel: pd.DataFrame,
    lat: float,
    lon: float,
    max_km: float = 30.0,
    min_year: int | None = None,
) -> pd.DataFrame:
    """Unique HAB locations from station_week_panel within max_km of buoy."""
    stations = (
        panel.groupby(["location_id", "location_name"], as_index=False)
        .agg(
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
            n_weeks=("week_start", "count"),
            year_min=("iso_year", "min"),
            year_max=("iso_year", "max"),
        )
    )
    stations["dist_km"] = haversine_km(stations["latitude"], stations["longitude"], lat, lon)
    near = stations[stations["dist_km"] <= max_km].sort_values("dist_km").reset_index(drop=True)
    if min_year is not None:
        near["overlap_years"] = near["year_max"] >= min_year
    return near


def week_aggregate_from_daily(daily: pd.DataFrame) -> pd.DataFrame:
    """ISO-week means from daily buoy series (Monday week_start)."""
    if daily.empty:
        return pd.DataFrame()
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"], utc=True)
    iso = d["date"].dt.isocalendar()
    d["iso_year"] = iso.year.astype(int)
    d["iso_week"] = iso.week.astype(int)
    d["week_start"] = d["date"] - pd.to_timedelta(d["date"].dt.dayofweek, unit="D")
    d["week_start"] = d["week_start"].dt.normalize()
    skip = {"date", "latitude", "longitude", "n_obs", "iso_year", "iso_week", "week_start"}
    value_cols = [c for c in d.columns if c not in skip and pd.api.types.is_numeric_dtype(d[c])]
    keys = ["iso_year", "iso_week", "week_start"]
    named = {c: (c, "mean") for c in value_cols}
    named["n_days"] = ("date", "size")
    out = d.groupby(keys, as_index=False).agg(**named)
    return out.sort_values(keys).reset_index(drop=True)


def join_buoy_to_hab_weeks(
    buoy_week: pd.DataFrame,
    panel: pd.DataFrame,
    location_ids: Iterable[int],
    buoy_cols: list[str],
    min_year: int,
) -> pd.DataFrame:
    hab = panel[panel["location_id"].isin(list(location_ids)) & (panel["iso_year"] >= min_year)].copy()
    if hab.empty or buoy_week.empty:
        return pd.DataFrame()
    keys = ["iso_year", "iso_week"]
    cols = [c for c in buoy_cols if c in buoy_week.columns]
    merged = hab.merge(buoy_week[keys + cols + [c for c in ("week_start", "n_days") if c in buoy_week.columns]], on=keys, how="inner", suffixes=("", "_buoy"))
    return merged


def correlate_signal(joined: pd.DataFrame, x_cols: list[str], y_cols: list[str]) -> pd.DataFrame:
    rows = []
    for x in x_cols:
        if x not in joined.columns:
            continue
        for y in y_cols:
            if y not in joined.columns:
                continue
            sub = joined[[x, y]].dropna()
            n = len(sub)
            if n < 5:
                rows.append({"x": x, "y": y, "n": n, "pearson_r": np.nan, "note": "too few pairs"})
                continue
            r = float(sub[x].corr(sub[y]))
            rows.append({"x": x, "y": y, "n": n, "pearson_r": r, "note": ""})
    return pd.DataFrame(rows)


def ingest_site(
    site_key: str,
    raw_dir: Path,
    t1: str | None = None,
    skip_download: bool = False,
) -> dict[str, Any]:
    site = BUOY_SITES[site_key]
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{site['dataset_id']}.csv"
    daily_path = raw_dir / f"{site['dataset_id']}_daily.parquet"
    week_path = raw_dir / f"{site['dataset_id']}_week.parquet"

    if skip_download and raw_path.exists():
        raw = pd.read_csv(raw_path, low_memory=False)
        raw["time"] = pd.to_datetime(raw["time"], utc=True, errors="coerce")
    else:
        print(f"Downloading {site['dataset_id']} ...")
        raw = download_dataset(site["dataset_id"], site["variables"], site["t0"], t1, out_csv=raw_path)

    daily = daily_aggregate(raw, site["rename"])
    daily.to_parquet(daily_path, index=False)
    week = week_aggregate_from_daily(daily)
    week.to_parquet(week_path, index=False)

    qc_info = None
    if site.get("qc_dataset_id"):
        qc_path = raw_dir / f"{site['qc_dataset_id']}.csv"
        qc_daily_path = raw_dir / f"{site['qc_dataset_id']}_daily.parquet"
        if skip_download and qc_path.exists():
            qc = pd.read_csv(qc_path, low_memory=False)
            qc["time"] = pd.to_datetime(qc["time"], utc=True, errors="coerce")
        else:
            print(f"Downloading QC {site['qc_dataset_id']} ...")
            # QC coverage ends ~2022-03; still start from site t0
            qc = download_dataset(
                site["qc_dataset_id"],
                site["qc_variables"],
                site["t0"],
                t1 or "2022-12-31",
                out_csv=qc_path,
            )
        qc_rename = {"temperature": "temp_c", "salinity": "salinity", "oxygen": "oxygen_umol_kg"}
        qc_daily = daily_aggregate(qc, qc_rename)
        qc_daily.to_parquet(qc_daily_path, index=False)
        qc_info = {
            "dataset_id": site["qc_dataset_id"],
            "raw_csv": str(qc_path),
            "daily_parquet": str(qc_daily_path),
            "n_rows": int(len(qc)),
            "t_min": str(qc["time"].min()) if len(qc) else None,
            "t_max": str(qc["time"].max()) if len(qc) else None,
        }

    return {
        "site_key": site_key,
        "label": site["label"],
        "dataset_id": site["dataset_id"],
        "lat": site["lat"],
        "lon": site["lon"],
        "raw_csv": str(raw_path),
        "daily_parquet": str(daily_path),
        "week_parquet": str(week_path),
        "n_rows": int(len(raw)),
        "n_days": int(len(daily)),
        "n_weeks": int(len(week)),
        "t_min": str(raw["time"].min()) if len(raw) else None,
        "t_max": str(raw["time"].max()) if len(raw) else None,
        "variables": list(site["variables"]),
        "daily_columns": list(daily.columns),
        "qc": qc_info,
        "daily": daily,
        "week": week,
    }
