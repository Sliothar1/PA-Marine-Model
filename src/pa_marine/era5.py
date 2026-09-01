"""ERA5 10 m wind for Irish HAB stations via CDS API.

Preferred product: ``reanalysis-era5-single-levels`` with 4× daily samples
(00/06/12/18 UTC), averaged to daily means locally. Full calendar years for the
Irish bbox fit CDS cost limits (unlike on-the-fly
``derived-era5-single-levels-daily-statistics`` year requests).

Credentials: ``~/.cdsapirc`` (never print/commit).

Alongshore convention for western Ireland (coast roughly N–S):
  wind_alongshore ≈ v10 (meridional), wind_crossshore ≈ u10 (zonal / onshore).
"""
from __future__ import annotations

import time
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CDS_TERMS_URL = (
    "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download"
)
DATASET_HOURLY = "reanalysis-era5-single-levels"
DATASET_DAILY = "derived-era5-single-levels-daily-statistics"
DEFAULT_VARS = ["10m_u_component_of_wind", "10m_v_component_of_wind"]

WIND_COLS = [
    "wind_u",
    "wind_v",
    "wind_speed",
    "wind_alongshore",
    "wind_crossshore",
    "msl",
]


def _require_cds():
    try:
        import cdsapi
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "cdsapi required (pip install 'pa-marine[era5]' or cdsapi ecmwf-datastores-client)"
        ) from exc
    return cdsapi


def _require_xr():
    try:
        import xarray as xr
    except ImportError as exc:  # pragma: no cover
        raise ImportError("xarray+netCDF4 required for ERA5 NetCDF") from exc
    return xr


def _era5_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    e = dict(cfg.get("era5") or {})
    domain = cfg.get("domain", {})
    e.setdefault("dataset", DATASET_HOURLY)
    e.setdefault("mode", "hourly4_daily")  # or daily_statistics
    e.setdefault("t0", "2002-01-01")
    e.setdefault("t1", "2026-08-25")
    e.setdefault("variables", list(DEFAULT_VARS))
    e.setdefault("include_msl", False)
    e.setdefault(
        "area",
        [
            float(domain.get("lat_max", 56.0)),
            float(domain.get("lon_min", -11.0)),
            float(domain.get("lat_min", 51.0)),
            float(domain.get("lon_max", -5.0)),
        ],
    )
    e.setdefault("raw_dir", "data/raw")
    e.setdefault("raw_glob", "era5_wind_hourly4_{year}.zip")
    e.setdefault("station_parquet", "data/raw/era5_wind_stations.parquet")
    e.setdefault("times", ["00:00", "06:00", "12:00", "18:00"])
    return e


def _client(wait: bool = True, sleep_max: int = 120):
    cdsapi = _require_cds()
    return cdsapi.Client(quiet=False, progress=True, wait_until_complete=wait, sleep_max=sleep_max)


def _year_in_range(year: int, t0: str, t1: str) -> bool:
    return pd.Timestamp(t0).year <= year <= pd.Timestamp(t1).year


def _hourly4_request(year: int, variables: list[str], area: list[float], times: list[str]) -> dict[str, Any]:
    return {
        "product_type": ["reanalysis"],
        "variable": list(variables),
        "year": [str(year)],
        "month": [f"{m:02d}" for m in range(1, 13)],
        "day": [f"{d:02d}" for d in range(1, 32)],
        "time": list(times),
        "data_format": "netcdf",
        "download_format": "zip",
        "area": list(area),
    }


def _halfyear_months(half: str) -> list[str]:
    if half.upper() == "H1":
        return [f"{m:02d}" for m in range(1, 7)]
    if half.upper() == "H2":
        return [f"{m:02d}" for m in range(7, 13)]
    raise ValueError(f"half must be H1 or H2, got {half}")


def _daily_stats_chunk_request(
    year: int,
    half: str,
    variables: list[str],
    area: list[float],
    t0: str,
    t1: str,
    frequency: str = "1_hourly",
) -> dict[str, Any] | None:
    """Half-year daily-statistics request (yearly exceeds CDS cost limits)."""
    y0 = pd.Timestamp(t0)
    y1 = pd.Timestamp(t1)
    months = []
    for m in _halfyear_months(half):
        start = pd.Timestamp(f"{year}-{m}-01")
        end = start + pd.offsets.MonthEnd(0)
        if end < y0 or start > y1:
            continue
        months.append(m)
    if not months:
        return None
    return {
        "product_type": "reanalysis",
        "variable": list(variables),
        "year": str(year),
        "month": months,
        "day": [f"{d:02d}" for d in range(1, 32)],
        "daily_statistic": "daily_mean",
        "time_zone": "utc+00:00",
        "frequency": frequency,
        "area": list(area),
    }


def download_era5_year(
    year: int,
    cfg: dict[str, Any],
    *,
    force: bool = False,
    wait: bool = True,
) -> dict[str, Any]:
    """Download one year of ERA5 wind (default: 4× daily hourly → zip)."""
    e = _era5_cfg(cfg)
    raw_dir = Path(e["raw_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = raw_dir / e["raw_glob"].format(year=year)
    meta: dict[str, Any] = {"year": year, "path": str(out), "request_id": None, "state": None}

    if not _year_in_range(year, e["t0"], e["t1"]):
        meta["state"] = "skipped"
        meta["error"] = "outside t0..t1"
        return meta
    if out.exists() and out.stat().st_size > 1000 and not force:
        meta["state"] = "exists"
        meta["size"] = out.stat().st_size
        return meta

    variables = list(e["variables"])
    if e.get("include_msl") and "mean_sea_level_pressure" not in variables:
        variables.append("mean_sea_level_pressure")

    mode = e.get("mode", "hourly4_daily")
    if mode == "hourly4_daily":
        dataset = DATASET_HOURLY
        req = _hourly4_request(year, variables, e["area"], e.get("times", ["00:00", "06:00", "12:00", "18:00"]))
    else:
        raise ValueError("use download_era5_chunk for daily_statistics mode")

    client = _client(wait=wait)
    print(f"ERA5 year {year}: submitting {dataset} → {out.name}")
    try:
        result = client.retrieve(dataset, req, None if not wait else str(out))
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "terms" in msg.lower() or "licence" in msg.lower() or "license" in msg.lower():
            raise RuntimeError(
                f"CDS licence acceptance required for {dataset}. "
                f"Accept terms at {CDS_TERMS_URL}. Original error: {msg}"
            ) from exc
        meta["state"] = "error"
        meta["error"] = msg[:1500]
        print(f"ERA5 year {year} ERROR: {msg[:500]}")
        return meta

    reply = getattr(result, "reply", None) or {}
    rid = reply.get("request_id") or getattr(result, "request_id", None)
    meta["request_id"] = rid
    if not wait:
        meta["state"] = reply.get("state", "submitted")
        print(f"ERA5 year {year}: async request_id={rid} state={meta['state']}")
        return meta

    if out.exists():
        meta["state"] = "downloaded"
        meta["size"] = out.stat().st_size
        print(f"ERA5 year {year}: wrote {out} ({meta['size']} bytes) request_id={rid}")
    elif isinstance(result, (str, Path)) and Path(result).exists():
        Path(result).replace(out)
        meta["state"] = "downloaded"
        meta["size"] = out.stat().st_size
    else:
        meta["state"] = "missing_file"
        meta["error"] = f"retrieve finished but {out} missing"
    return meta


def download_era5_chunk(
    year: int,
    half: str,
    cfg: dict[str, Any],
    *,
    force: bool = False,
    wait: bool = True,
) -> dict[str, Any]:
    """Download half-year daily-statistics zip (fallback path)."""
    e = _era5_cfg(cfg)
    raw_dir = Path(e["raw_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    half = half.upper()
    out = raw_dir / f"era5_wind_{year}_{half}.zip"
    meta: dict[str, Any] = {"year": year, "half": half, "path": str(out), "request_id": None, "state": None}
    if out.exists() and out.stat().st_size > 1000 and not force:
        meta["state"] = "exists"
        meta["size"] = out.stat().st_size
        return meta
    variables = list(e["variables"])
    req = _daily_stats_chunk_request(year, half, variables, e["area"], e["t0"], e["t1"])
    if req is None:
        meta["state"] = "skipped"
        return meta
    client = _client(wait=wait)
    print(f"ERA5 {year} {half}: submitting {DATASET_DAILY} → {out.name}")
    try:
        result = client.retrieve(DATASET_DAILY, req, None if not wait else str(out))
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "terms" in msg.lower() or "licence" in msg.lower() or "license" in msg.lower():
            raise RuntimeError(
                f"CDS licence acceptance required. Accept at "
                f"https://cds.climate.copernicus.eu/datasets/{DATASET_DAILY}?tab=download. Error: {msg}"
            ) from exc
        meta["state"] = "error"
        meta["error"] = msg[:1500]
        print(f"ERA5 {year} {half} ERROR: {msg[:500]}")
        return meta
    reply = getattr(result, "reply", None) or {}
    meta["request_id"] = reply.get("request_id") or getattr(result, "request_id", None)
    if not wait:
        meta["state"] = reply.get("state", "submitted")
        return meta
    if out.exists():
        meta["state"] = "downloaded"
        meta["size"] = out.stat().st_size
    else:
        meta["state"] = "missing_file"
    return meta


def download_era5_years(
    cfg: dict[str, Any],
    years: list[int] | None = None,
    *,
    force: bool = False,
    wait: bool = True,
    max_years: int | None = None,
) -> list[dict[str, Any]]:
    """Download yearly ERA5 wind zips for the configured period."""
    e = _era5_cfg(cfg)
    y0 = pd.Timestamp(e["t0"]).year
    y1 = pd.Timestamp(e["t1"]).year
    years = list(years) if years is not None else list(range(y0, y1 + 1))
    if max_years is not None:
        years = years[:max_years]
    results: list[dict[str, Any]] = []
    for y in years:
        results.append(download_era5_year(y, cfg, force=force, wait=wait))
        if wait:
            time.sleep(1)
    return results


def _open_zip_dataset(path: Path):
    xr = _require_xr()
    with zipfile.ZipFile(path) as zf:
        members = [n for n in zf.namelist() if n.endswith(".nc")]
        if not members:
            raise ValueError(f"no NetCDF members in {path}")
        import tempfile

        arrays = []
        with tempfile.TemporaryDirectory(prefix="era5_") as td:
            td_path = Path(td)
            for name in members:
                zf.extract(name, td_path)
                arrays.append(xr.open_dataset(td_path / name).load())
    ds = arrays[0]
    for a in arrays[1:]:
        ds = ds.merge(a, compat="override")
    return ds


def _to_daily_means(ds):
    """Average sub-daily samples to calendar-day means (UTC)."""
    if "valid_time" not in ds.dims and "time" in ds.dims:
        ds = ds.rename({"time": "valid_time"})
    # groupby date
    daily = ds.resample(valid_time="1D").mean(keep_attrs=True)
    return daily


def load_era5_cube(cfg: dict[str, Any], years: list[int] | None = None):
    """Load downloaded yearly zips into one daily xarray Dataset (u10/v10[/msl])."""
    xr = _require_xr()
    e = _era5_cfg(cfg)
    raw_dir = Path(e["raw_dir"])
    y0 = pd.Timestamp(e["t0"]).year
    y1 = pd.Timestamp(e["t1"]).year
    years = list(years) if years is not None else list(range(y0, y1 + 1))
    frames = []
    for y in years:
        path = raw_dir / e["raw_glob"].format(year=y)
        matches = [path] if path.exists() else sorted(raw_dir.glob(f"era5_wind*{y}*.zip"))
        # prefer hourly4 yearly
        preferred = raw_dir / f"era5_wind_hourly4_{y}.zip"
        if preferred.exists():
            matches = [preferred]
        if not matches:
            print(f"ERA5 load skip missing year {y}")
            continue
        for path in matches:
            if not path.exists() or path.stat().st_size < 1000:
                continue
            print(f"ERA5 load {path}")
            ds = _open_zip_dataset(path)
            # hourly4 → daily; daily-stats already daily
            n_per_day = None
            if "valid_time" in ds.dims:
                # heuristic: >400 timesteps/year ⇒ sub-daily
                if ds.sizes.get("valid_time", 0) > 400:
                    ds = _to_daily_means(ds)
            frames.append(ds)
    if not frames:
        return xr.Dataset()
    out = xr.concat(frames, dim="valid_time")
    # drop duplicate times if any
    _, index = np.unique(out["valid_time"].values, return_index=True)
    out = out.isel(valid_time=sorted(index))
    return out.sortby("valid_time")


def _nearest_grid_map(stations: pd.DataFrame, lats: np.ndarray, lons: np.ndarray) -> pd.DataFrame:
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
    rows = []
    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]]
    for row in uniq.itertuples(index=False):
        dist = (lat_grid - float(row.latitude)) ** 2 + (lon_grid - float(row.longitude)) ** 2
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


def extract_station_daily(
    stations: pd.DataFrame,
    cfg: dict[str, Any],
    years: list[int] | None = None,
) -> pd.DataFrame:
    """Nearest-grid daily ERA5 wind at each unique HAB location_id."""
    ds = load_era5_cube(cfg, years=years)
    if len(ds.data_vars) == 0:
        return pd.DataFrame()

    lats = np.asarray(ds["latitude"].values, dtype=float)
    lons = np.asarray(ds["longitude"].values, dtype=float)
    mapping = _nearest_grid_map(stations, lats, lons)
    if mapping.empty:
        return pd.DataFrame()

    cells = mapping.drop_duplicates(["grid_lat", "grid_lon"])[["grid_lat", "grid_lon"]]
    cell_frames = []
    for cell in cells.itertuples(index=False):
        pt = ds.sel(latitude=cell.grid_lat, longitude=cell.grid_lon, method="nearest")
        times = pd.to_datetime(np.asarray(pt["valid_time"].values)).tz_localize(None)
        u = np.asarray(pt["u10"].values, dtype=float) if "u10" in pt else np.full(len(times), np.nan)
        v = np.asarray(pt["v10"].values, dtype=float) if "v10" in pt else np.full(len(times), np.nan)
        msl = np.asarray(pt["msl"].values, dtype=float) if "msl" in pt else np.full(len(times), np.nan)
        cell_frames.append(
            pd.DataFrame(
                {
                    "date": pd.to_datetime(times).normalize(),
                    "grid_lat": float(cell.grid_lat),
                    "grid_lon": float(cell.grid_lon),
                    "wind_u": u,
                    "wind_v": v,
                    "msl": msl,
                }
            )
        )
    grid_df = pd.concat(cell_frames, ignore_index=True)
    out = mapping.merge(grid_df, on=["grid_lat", "grid_lon"], how="left")
    out["wind_speed"] = np.sqrt(out["wind_u"] ** 2 + out["wind_v"] ** 2)
    out["wind_alongshore"] = out["wind_v"]
    out["wind_crossshore"] = out["wind_u"]
    cols = [
        "location_id",
        "date",
        "request_lat",
        "request_lon",
        "grid_lat",
        "grid_lon",
        "dist_deg",
        "wind_u",
        "wind_v",
        "wind_speed",
        "wind_alongshore",
        "wind_crossshore",
    ]
    if out["msl"].notna().any():
        cols.append("msl")
    return out[cols].sort_values(["location_id", "date"]).reset_index(drop=True)


def add_wind_rolls(daily: pd.DataFrame, windows: tuple[int, ...] = (7, 14)) -> pd.DataFrame:
    """Past-only rolling means of wind speed / alongshore / cross-shore / u / v."""
    base = [
        c
        for c in ["wind_speed", "wind_alongshore", "wind_crossshore", "wind_u", "wind_v", "msl"]
        if c in daily.columns
    ]
    parts = []
    for _loc, g in daily.groupby("location_id"):
        g = g.sort_values("date").copy()
        for col in base:
            for w in windows:
                g[f"{col}_roll{w}d"] = g[col].rolling(w, min_periods=max(3, w // 3)).mean()
            g[f"{col}_lag0d"] = g[col]
        parts.append(g)
    return pd.concat(parts, ignore_index=True) if parts else daily


def join_era5_to_week_panel(panel: pd.DataFrame, wind_daily: pd.DataFrame) -> pd.DataFrame:
    """Attach week-end (Sunday) ERA5 wind + 7/14d rolls onto station-week panel/features."""
    feat = add_wind_rolls(wind_daily.copy())
    feat["date"] = pd.to_datetime(feat["date"]).dt.tz_localize(None).dt.normalize()
    p = panel.copy()
    if "week_start" in p.columns:
        p["week_start"] = pd.to_datetime(p["week_start"]).dt.tz_localize(None).dt.normalize()
        if "feat_date" not in p.columns:
            p["feat_date"] = p["week_start"] + pd.Timedelta(days=6)
    elif "feat_date" in p.columns:
        p["feat_date"] = pd.to_datetime(p["feat_date"]).dt.tz_localize(None).dt.normalize()
    else:
        raise ValueError("panel needs week_start or feat_date")

    wind_cols = [c for c in feat.columns if c.startswith("wind_") or c.startswith("msl")]
    keep = ["location_id", "date"] + wind_cols
    merged = p.merge(
        feat[keep].rename(columns={"date": "feat_date"}),
        on=["location_id", "feat_date"],
        how="left",
    )
    return merged


def save_station_parquet(df: pd.DataFrame, cfg: dict[str, Any], path: str | None = None) -> Path:
    e = _era5_cfg(cfg)
    out = Path(path or e["station_parquet"])
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out
