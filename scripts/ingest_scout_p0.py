#!/usr/bin/env python3
"""Ingest scout P0 datasets: CRW MHW 5km, SmartBay CTD, Met Éireann Mace Head, IMI CONN ROMS.

Pragmatic: skip re-download of OISST/OSTIA/IBI/habs_phyto. Partial success OK.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
INFO = RAW / "erddap_info"

IRISH_LAT = (51.0, 56.0)
IRISH_LON = (-11.0, -5.0)

CRW_BASE = (
    "https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/"
    "marine_heatwave/v1.0.1/category/nc"
)
CRW_PRODUCT = {
    "product": "NOAA Coral Reef Watch Daily Global 5km Satellite Marine Heatwave Watch v1.0.1",
    "algorithm": "Hobday et al. (2018) categories on CoralTemp SST",
    "info_url": "https://coralreefwatch.noaa.gov/product/marine_heatwave/",
    "pacioos_erddap_id": "mhw_5km",
    "pacioos_erddap_url": "https://pae-paha.pacioos.hawaii.edu/erddap/griddap/mhw_5km.html",
    "pacioos_status_2026_09_01": (
        "ERDDAP dataset mhw_5km returns HTTP 404; PacIOOS host TLS often fails from this box. "
        "Ingested instead from NOAA STAR HTTPS daily NetCDF category files."
    ),
    "star_nc_root": CRW_BASE + "/",
    "category_table": {
        "-127": "Land",
        "-1": "Climatology Sea Ice",
        "0": "No MHW",
        "1": "Cat 1 Moderate",
        "2": "Cat 2 Strong",
        "3": "Cat 3 Severe",
        "4": "Cat 4 Extreme",
        "5": "Cat 5 Beyond Extreme",
    },
    "bbox": {"lat_min": 51, "lat_max": 56, "lon_min": -11, "lon_max": -5},
}

MI_ERDDAP = "https://erddap.marine.ie/erddap"
UA = {"User-Agent": "pa-marine-model/scout-p0 (+research)"}


def _ensure_dirs() -> None:
    for p in [
        RAW / "crw_mhw",
        RAW / "smartbay",
        RAW / "met_eireann",
        RAW / "imi_conn",
        INFO,
        PROC,
    ]:
        p.mkdir(parents=True, exist_ok=True)


def _get(url: str, timeout: int = 180, **kw) -> requests.Response:
    r = requests.get(url, timeout=timeout, headers=UA, **kw)
    return r


def _erddap_tabledap_csv(
    dataset_id: str,
    variables: Iterable[str],
    constraints: Iterable[str],
    timeout: int = 600,
) -> pd.DataFrame:
    vars_part = ",".join(variables)
    url = f"{MI_ERDDAP}/tabledap/{dataset_id}.csv?{quote(vars_part, safe=',_()')}"
    extra = "&".join(quote(c, safe="=,&()_'\"") for c in constraints)
    extra = (
        extra.replace(">=", "%3E%3D")
        .replace("<=", "%3C%3D")
        .replace(">", "%3E")
        .replace("<", "%3C")
    )
    url = f"{url}&{extra}"
    r = _get(url, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"ERDDAP {dataset_id} HTTP {r.status_code}: {r.text[:400]}")
    text = r.text
    lines = text.splitlines()
    skip = [1] if len(lines) >= 2 and ("," in lines[1]) and not lines[1].split(",")[0].strip()[:1].isdigit() else None
    return pd.read_csv(StringIO(text), skiprows=skip)


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ---------------- CRW MHW ----------------

def _crw_url(d: date) -> str:
    return f"{CRW_BASE}/{d.year}/noaa-crw_mhw_v1.0.1_category_{d.strftime('%Y%m%d')}.nc"


def _subset_crw_nc(path: Path) -> pd.DataFrame:
    """Irish bbox extract; supports 2022-style (latdim/londim) and 2024-style (lat/lon dims)."""
    ds = xr.open_dataset(path, mask_and_scale=False, decode_timedelta=False)
    try:
        if "lat" in ds.dims and "lon" in ds.dims:
            sub = ds.sel(lat=slice(IRISH_LAT[0], IRISH_LAT[1]), lon=slice(IRISH_LON[0], IRISH_LON[1]))
            cat = np.asarray(sub["heatwave_category"].values[0])
            mask = np.asarray(sub["mask"].values[0]) if "mask" in sub else np.full(cat.shape, np.nan, dtype="float32")
            lat_s = np.asarray(sub["lat"].values)
            lon_s = np.asarray(sub["lon"].values)
            tval = sub["time"].values[0]
        else:
            lat = np.asarray(ds["lat"].values)
            lon = np.asarray(ds["lon"].values)
            ilat = np.where((lat >= IRISH_LAT[0]) & (lat <= IRISH_LAT[1]))[0]
            ilon = np.where((lon >= IRISH_LON[0]) & (lon <= IRISH_LON[1]))[0]
            if len(ilat) == 0 or len(ilon) == 0:
                raise RuntimeError(f"empty Irish subset in {path}")
            i0, i1 = int(ilat[0]), int(ilat[-1])
            j0, j1 = int(ilon[0]), int(ilon[-1])
            cat = np.asarray(ds["heatwave_category"].values[0, i0 : i1 + 1, j0 : j1 + 1])
            mask = np.asarray(ds["mask"].values[0, i0 : i1 + 1, j0 : j1 + 1]) if "mask" in ds else np.full(cat.shape, np.nan, dtype="float32")
            lat_s = lat[i0 : i1 + 1]
            lon_s = lon[j0 : j1 + 1]
            tval = ds["time"].values[0]
        # Normalize fill / land flags to NaN for analysis convenience
        cat_f = cat.astype("float32")
        cat_f[(cat_f < 0) | (cat_f > 5)] = np.nan
        t = pd.Timestamp(tval).tz_localize(None) if hasattr(pd.Timestamp(tval), 'tz_localize') else pd.Timestamp(tval)
        if getattr(t, "tzinfo", None) is not None:
            t = t.tz_localize(None)
        lon2d, lat2d = np.meshgrid(lon_s, lat_s)
        return pd.DataFrame(
            {
                "time": t,
                "latitude": lat2d.ravel(),
                "longitude": lon2d.ravel(),
                "heatwave_category": cat_f.ravel(),
                "mask": mask.astype("float32").ravel(),
            }
        )
    finally:
        ds.close()


def _download_crw_file(d: date, tmp_dir: Path) -> tuple[date, str, Path | None]:
    """Download only (thread-safe). NetCDF/HDF5 subsetting is done single-threaded."""
    url = _crw_url(d)
    tmp = tmp_dir / f"noaa-crw_mhw_v1.0.1_category_{d.strftime('%Y%m%d')}.nc"
    try:
        r = _get(url, timeout=120, stream=True)
        if r.status_code != 200:
            return d, f"http_{r.status_code}", None
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)
        if tmp.stat().st_size < 1000:
            tmp.unlink(missing_ok=True)
            return d, "too_small", None
        return d, "ok", tmp
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return d, f"err:{type(e).__name__}:{e}", None


def ingest_crw_mhw(start: date, end: date, workers: int = 8) -> dict:
    tmp_dir = RAW / "crw_mhw" / "global_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    days = list(daterange(start, end))
    results = []
    ok_paths: list[Path] = []

    downloaded: list[tuple[date, Path]] = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_download_crw_file, d, tmp_dir): d for d in days}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            d, status, path = fut.result()
            if path is not None:
                downloaded.append((d, path))
            else:
                results.append({"date": d.isoformat(), "status": status, "path": None})
            if i % 50 == 0 or i == len(futs):
                print(f"  CRW download {i}/{len(futs)} files={len(downloaded)}", flush=True)

    downloaded.sort(key=lambda x: x[0])
    for i, (d, tmp) in enumerate(downloaded, 1):
        try:
            df = _subset_crw_nc(tmp)
            out = RAW / "crw_mhw" / f"ireland_{d.strftime('%Y%m%d')}.parquet"
            df.to_parquet(out, index=False)
            tmp.unlink(missing_ok=True)
            ok_paths.append(out)
            results.append({"date": d.isoformat(), "status": "ok", "path": str(out)})
        except Exception as e:
            results.append({"date": d.isoformat(), "status": f"subset_err:{type(e).__name__}:{e}", "path": None})
            tmp.unlink(missing_ok=True)
        if i % 50 == 0 or i == len(downloaded):
            print(f"  CRW subset {i}/{len(downloaded)} ok={len(ok_paths)}", flush=True)

    frames = [pd.read_parquet(pth) for pth in sorted(ok_paths)]
    summary_rows = []
    if frames:
        stacked = pd.concat(frames, ignore_index=True)
        out_all = PROC / "crw_mhw_ireland_daily.parquet"
        stacked.to_parquet(out_all, index=False)
        ocean = stacked[stacked["heatwave_category"].between(0, 5)]
        g = (
            ocean.assign(is_mhw=ocean["heatwave_category"] >= 1)
            .groupby("time", as_index=False)
            .agg(
                n_ocean=("heatwave_category", "size"),
                n_mhw=("is_mhw", "sum"),
                mean_cat=("heatwave_category", "mean"),
                max_cat=("heatwave_category", "max"),
                frac_mhw=("is_mhw", "mean"),
            )
        )
        g.to_parquet(PROC / "crw_mhw_ireland_daily_summary.parquet", index=False)
        g.to_csv(PROC / "crw_mhw_ireland_daily_summary.csv", index=False)
        summary_rows = g.to_dict(orient="records")

    june = [r for r in results if r["date"].startswith("2023-06") and r["status"] == "ok"]
    product_path = RAW / "crw_mhw" / "product.json"
    product_path.write_text(json.dumps(CRW_PRODUCT, indent=2))
    INFO.joinpath("crw_mhw_product.json").write_text(json.dumps(CRW_PRODUCT, indent=2))

    return {
        "requested_days": len(days),
        "ok_days": len(ok_paths),
        "fail_days": len(days) - len(ok_paths),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "ireland_parquet": str(PROC / "crw_mhw_ireland_daily.parquet") if frames else None,
        "bytes_ireland_parquet": (PROC / "crw_mhw_ireland_daily.parquet").stat().st_size if frames else 0,
        "june_2023_ok_days": len(june),
        "product_doc": str(product_path),
        "failures_sample": [r for r in results if r["status"] != "ok"][:10],
        "daily_summary_rows": len(summary_rows),
    }


def _daily_agg_smartbay(df: pd.DataFrame, temp_col: str, sal_col: str, do_col: str) -> pd.DataFrame:
    df = df.copy()
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.dropna(subset=["time"])
    df["date"] = df["time"].dt.floor("D")
    ag = {"n": ("time", "size"), "temp_c": (temp_col, "mean"), "salinity": (sal_col, "mean"), "do": (do_col, "mean")}
    if "depth" in df.columns:
        ag["depth_m"] = ("depth", "mean")
    return df.groupby("date", as_index=False).agg(**ag)


def ingest_smartbay() -> dict:
    out: dict = {"datasets": {}}

    # Processed SBE16 (ends ~2023-05-08)
    vars_sbe = [
        "time",
        "depth",
        "latitude",
        "longitude",
        "temperature",
        "salinity",
        "oxygen_conc_mll",
        "oxygen_sat",
        "temperature_QC",
        "salinity_QC",
        "oxygen_conc_mll_QC",
    ]
    try:
        # chunk by year for reliability
        chunks = []
        year_ranges = [
            ("2015-10-08", "2015-12-31"),
            ("2016-01-01", "2016-12-31"),
            ("2017-01-01", "2017-12-31"),
            ("2018-01-01", "2018-12-31"),
            ("2019-01-01", "2019-12-31"),
            ("2020-01-01", "2020-12-31"),
            ("2021-01-01", "2021-12-31"),
            ("2022-01-01", "2022-12-31"),
            ("2023-01-01", "2023-05-08"),
        ]
        for y0, y1 in year_ranges:
            print(f"  SmartBay SBE16 {y0}→{y1}", flush=True)
            try:
                df = _erddap_tabledap_csv(
                    "smartbay_obs_ctd_sbe16",
                    vars_sbe,
                    [f"time>={y0}T00:00:00Z", f"time<={y1}T23:59:59Z"],
                    timeout=900,
                )
            except Exception as e:
                print(f"    skip: {e}", flush=True)
                continue
            if df.empty:
                continue
            chunks.append(df)
            raw_y = RAW / "smartbay" / f"smartbay_obs_ctd_sbe16_{y0[:4]}.csv"
            df.to_csv(raw_y, index=False)
        if not chunks:
            raise RuntimeError("no smartbay_obs_ctd_sbe16 chunks downloaded")
        sbe = pd.concat(chunks, ignore_index=True)
        raw_all = RAW / "smartbay" / "smartbay_obs_ctd_sbe16.csv"
        sbe.to_csv(raw_all, index=False)
        daily = _daily_agg_smartbay(sbe, "temperature", "salinity", "oxygen_conc_mll")
        daily = daily.rename(columns={"do": "do_mll"})
        daily_path = PROC / "smartbay_sbe16_daily.parquet"
        daily.to_parquet(daily_path, index=False)
        out["datasets"]["smartbay_obs_ctd_sbe16"] = {
            "status": "ok",
            "rows_raw": int(len(sbe)),
            "days": int(len(daily)),
            "time_min": str(sbe["time"].min()),
            "time_max": str(sbe["time"].max()),
            "raw_csv_bytes": raw_all.stat().st_size,
            "daily_parquet_bytes": daily_path.stat().st_size,
            "note": "Processed CTD+O2; coverage ends 2023-05-08 (no June 2023).",
        }
    except Exception as e:
        out["datasets"]["smartbay_obs_ctd_sbe16"] = {"status": "fail", "error": str(e)}

    # Spiddal NRT (covers June 2023)
    vars_sp = [
        "time",
        "depth",
        "latitude",
        "longitude",
        "temp",
        "sal",
        "dissolved_oxygen_ppm",
        "dissolved_oxygen_sat",
    ]
    try:
        chunks = []
        for y0, y1 in [
            ("2022-01-01", "2022-12-31"),
            ("2023-01-01", "2023-12-31"),
            ("2024-01-01", "2024-12-31"),
            ("2025-01-01", "2026-09-01"),
        ]:
            print(f"  Spiddal CTD {y0}→{y1}", flush=True)
            try:
                df = _erddap_tabledap_csv(
                    "spiddal_obs_ctd",
                    vars_sp,
                    [f"time>={y0}T00:00:00Z", f"time<={y1}T23:59:59Z"],
                    timeout=900,
                )
            except Exception as e:
                print(f"    skip chunk: {e}", flush=True)
                continue
            if df.empty:
                continue
            chunks.append(df)
            df.to_csv(RAW / "smartbay" / f"spiddal_obs_ctd_{y0[:4]}_{y1[:4]}.csv", index=False)
        if not chunks:
            raise RuntimeError("no spiddal chunks downloaded")
        sp = pd.concat(chunks, ignore_index=True)
        raw_all = RAW / "smartbay" / "spiddal_obs_ctd.csv"
        sp.to_csv(raw_all, index=False)
        daily = _daily_agg_smartbay(sp, "temp", "sal", "dissolved_oxygen_ppm")
        daily = daily.rename(columns={"do": "do_mg_l"})
        daily_path = PROC / "spiddal_ctd_daily.parquet"
        daily.to_parquet(daily_path, index=False)
        # June 2023 snapshot stats
        j = daily[(daily["date"] >= "2023-06-01") & (daily["date"] < "2023-07-01")]
        out["datasets"]["spiddal_obs_ctd"] = {
            "status": "ok",
            "rows_raw": int(len(sp)),
            "days": int(len(daily)),
            "time_min": str(sp["time"].min()),
            "time_max": str(sp["time"].max()),
            "raw_csv_bytes": raw_all.stat().st_size,
            "daily_parquet_bytes": daily_path.stat().st_size,
            "june_2023_days": int(len(j)),
            "june_2023_temp_mean": float(j["temp_c"].mean()) if len(j) else None,
            "note": "NRT/raw SmartBay Observatory CTD; includes June 2023.",
        }
    except Exception as e:
        out["datasets"]["spiddal_obs_ctd"] = {"status": "fail", "error": str(e)}

    # save info copies if present
    for name in ["smartbay_obs_ctd_sbe16_info.json", "spiddal_obs_ctd_info.json"]:
        src = INFO / name
        if not src.exists():
            try:
                did = name.replace("_info.json", "")
                r = _get(f"{MI_ERDDAP}/info/{did}/index.json", timeout=60)
                if r.status_code == 200:
                    src.write_text(r.text)
            except Exception:
                pass
    return out


# ---------------- Met Éireann ----------------

def ingest_met_eireann() -> dict:
    urls = {
        "daily": "https://clidata.met.ie/cli/climate_data/webdata/dly275.csv",
        "hourly": "https://clidata.met.ie/cli/climate_data/webdata/hly275.csv",
        "monthly": "https://clidata.met.ie/cli/climate_data/webdata/mly275.csv",
        "key_daily": "https://www.met.ie/cms/assets/uploads/2018/05/KeyDaily.txt",
        "key_monthly": "https://www.met.ie/cms/assets/uploads/2018/05/KeyMonthly.txt",
    }
    dest = {
        "daily": RAW / "met_eireann" / "mace_head_daily_dly275.csv",
        "hourly": RAW / "met_eireann" / "mace_head_hourly_hly275.csv",
        "monthly": RAW / "met_eireann" / "mace_head_monthly_mly275.csv",
        "key_daily": RAW / "met_eireann" / "KeyDaily.txt",
        "key_monthly": RAW / "met_eireann" / "KeyMonthly.txt",
    }
    meta = {
        "station": "Mace Head",
        "station_no": 275,
        "lat": 53.326,
        "lon": -9.901,
        "height_m": 21,
        "opendata2_met_ie": "https://opendata2.met.ie/ (landing page only; historical CSVs via clidata.met.ie)",
        "data_gov_ie": {
            "mace-head-daily-data": "https://data.gov.ie/dataset/mace-head-daily-data",
            "mace-head-hourly-data": "https://data.gov.ie/dataset/mace-head-hourly-data",
            "mace-head-monthly-data": "https://data.gov.ie/dataset/mace-head-monthly-data",
        },
        "urls": urls,
        "wind_fields_daily": ["wdsp", "hm", "ddhm", "hg"],
        "radiation_fields_daily": ["glorad"],
        "wind_fields_hourly": ["wdsp", "wddir", "wwdsp", "wdur"],
    }
    (RAW / "met_eireann" / "sources.json").write_text(json.dumps(meta, indent=2))

    downloaded = {}
    for key, url in urls.items():
        path = dest[key]
        if path.exists() and path.stat().st_size > 1000:
            downloaded[key] = {"status": "cached", "bytes": path.stat().st_size, "path": str(path)}
            continue
        print(f"  Met Éireann download {key}", flush=True)
        r = _get(url, timeout=300)
        if r.status_code != 200:
            downloaded[key] = {"status": f"http_{r.status_code}", "url": url}
            continue
        path.write_bytes(r.content)
        downloaded[key] = {"status": "ok", "bytes": path.stat().st_size, "path": str(path), "url": url}

    # Parse daily wind + global radiation
    daily_path = dest["daily"]
    parsed = {"status": "skip"}
    if daily_path.exists():
        # Met files have a multi-line header before the CSV table
        text = daily_path.read_text(errors="ignore").splitlines()
        hdr_i = next(i for i, l in enumerate(text) if l.lower().startswith("date,"))
        df = pd.read_csv(StringIO("\n".join(text[hdr_i:])), low_memory=False)
        # date like 01-jan-1958 or 31-jul-2026
        df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True, errors="coerce")
        for c in ["wdsp", "hm", "ddhm", "hg", "glorad", "maxtp", "mintp", "rain"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        keep = [c for c in ["date", "wdsp", "hm", "ddhm", "hg", "glorad", "maxtp", "mintp", "rain"] if c in df.columns]
        out = df[keep].dropna(subset=["date"]).sort_values("date")
        out_path = PROC / "mace_head_met_daily.parquet"
        out.to_parquet(out_path, index=False)
        out.to_csv(PROC / "mace_head_met_daily.csv", index=False)
        j = out[(out["date"] >= "2023-06-01") & (out["date"] < "2023-07-01")]
        parsed = {
            "status": "ok",
            "rows": int(len(out)),
            "date_min": str(out["date"].min().date()),
            "date_max": str(out["date"].max().date()),
            "parquet_bytes": out_path.stat().st_size,
            "june_2023_days": int(len(j)),
            "june_2023_wdsp_mean_kt": float(j["wdsp"].mean()) if len(j) and "wdsp" in j else None,
            "june_2023_glorad_mean": float(j["glorad"].mean()) if len(j) and "glorad" in j else None,
        }

    # Hourly → daily wind mean for overlap convenience
    hourly_path = dest["hourly"]
    hourly_parsed = {"status": "skip"}
    if hourly_path.exists():
        text = hourly_path.read_text(errors="ignore").splitlines()
        hdr_i = next(i for i, l in enumerate(text) if l.lower().startswith("date,"))
        hdf = pd.read_csv(StringIO("\n".join(text[hdr_i:])), low_memory=False)
        hdf["time"] = pd.to_datetime(hdf["date"], format="mixed", dayfirst=True, errors="coerce")
        for c in ["wdsp", "temp", "rhum", "msl", "rain"]:
            if c in hdf.columns:
                hdf[c] = pd.to_numeric(hdf[c], errors="coerce")
        hdf = hdf.dropna(subset=["time"])
        hdf["date"] = hdf["time"].dt.floor("D")
        hdaily = hdf.groupby("date", as_index=False).agg(
            n=("time", "size"),
            wdsp_kt=("wdsp", "mean"),
            temp_c=("temp", "mean") if "temp" in hdf.columns else ("wdsp", "mean"),
        )
        hp = PROC / "mace_head_met_hourly_daily.parquet"
        hdaily.to_parquet(hp, index=False)
        hourly_parsed = {
            "status": "ok",
            "hourly_rows": int(len(hdf)),
            "daily_rows": int(len(hdaily)),
            "time_min": str(hdf["time"].min()),
            "time_max": str(hdf["time"].max()),
            "parquet_bytes": hp.stat().st_size,
        }

    return {"downloads": downloaded, "daily_parsed": parsed, "hourly_daily_parsed": hourly_parsed, "meta": meta}


# ---------------- IMI CONN ROMS ----------------

def ingest_imi_conn() -> dict:
    """ERDDAP IMI_CONN_3D is a rolling ~8-day window; THREDDS ANALYSIS/COMBINED ~30 days.

    Download a recent surface subset + document archive paths. June 2023 not online.
    """
    info = {
        "erddap_dataset": "IMI_CONN_3D",
        "erddap_info": f"{MI_ERDDAP}/info/IMI_CONN_3D/index.html",
        "erddap_sourceUrl": "http://milas.marine.ie/thredds/dodsC/IMI-CONN_AGG",
        "thredds_paths": {
            "IMI-CONN_AGG": "http://milas.marine.ie/thredds/dodsC/IMI-CONN_AGG",
            "COMBINED_AGGREGATION": (
                "http://milas.marine.ie/thredds/dodsC/"
                "IMI_ROMS_HYDRO/CONNEMARA_250M_20L_1H/COMBINED_AGGREGATION"
            ),
            "ANALYSIS_catalog": (
                "http://milas.marine.ie/thredds/catalog/"
                "IMI_ROMS_HYDRO/CONNEMARA_NATIVE_250M_20L_1H/ANALYSIS/catalog.xml"
            ),
            "ANALYSIS_fileServer_pattern": (
                "http://milas.marine.ie/thredds/fileServer/"
                "IMI_ROMS_HYDRO/CONNEMARA_NATIVE_250M_20L_1H/ANALYSIS/CONN_YYYYMMDDHH_AN.nc"
            ),
            "native_aggregate": (
                "http://milas.marine.ie/thredds/dodsC/connemara_native/connemara_native_aggregate.nc"
            ),
        },
        "june_2023_status": (
            "Not present in public rolling aggregates (IMI-CONN_AGG / COMBINED ~Aug–Sep 2026 only; "
            "ANALYSIS catalog scan currently lists ~2026-08 files ~49 MB/hour). "
            "Full June 2023 archive deferred — use THREDDS paths above when MI extends retention."
        ),
    }
    (RAW / "imi_conn" / "thredds_archive_paths.json").write_text(json.dumps(info, indent=2))
    try:
        r = _get(f"{MI_ERDDAP}/info/IMI_CONN_3D/index.json", timeout=60)
        if r.status_code == 200:
            (INFO / "IMI_CONN_3D_info.json").write_text(r.text)
    except Exception:
        pass

    # Recent surface (altitude=1) T/S at reduced spatial stride via griddap CSV
    # time last ~7 days already on server; pull all times at stride 10 for size control
    # Query format: var[time][alt][lat][lon]
    results = {"info": info, "recent": {}}
    try:
        # Discover time bounds from info
        info_j = json.loads((INFO / "IMI_CONN_3D_info.json").read_text())
        t0 = t1 = None
        for row in info_j["table"]["rows"]:
            if row[0] == "attribute" and row[1] == "NC_GLOBAL" and row[2] == "time_coverage_start":
                t0 = row[4]
            if row[0] == "attribute" and row[1] == "NC_GLOBAL" and row[2] == "time_coverage_end":
                t1 = row[4]
        # Use last day only at surface, stride lat/lon ~10 (~0.018 deg) to keep CSV manageable
        # Pull noon-ish: every 24th hour by requesting last 24h first as sample, then full window strided
        q = (
            "Sea_water_temperature"
            f"[({t0}):24:({t1})]"
            "[(1.0):1:(1.0)]"
            "[(52.951):10:(53.729)]"
            "[(-10.798):10:(-8.897)]"
            ",Sea_water_salinity"
            f"[({t0}):24:({t1})]"
            "[(1.0):1:(1.0)]"
            "[(52.951):10:(53.729)]"
            "[(-10.798):10:(-8.897)]"
        )
        url = f"{MI_ERDDAP}/griddap/IMI_CONN_3D.csv?{q}"
        print("  IMI_CONN_3D recent surface daily-ish subset", flush=True)
        r = _get(url, timeout=300)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        raw_csv = RAW / "imi_conn" / "IMI_CONN_3D_recent_surface.csv"
        raw_csv.write_text(r.text)
        df = pd.read_csv(StringIO(r.text), skiprows=[1])
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df.to_parquet(PROC / "imi_conn_3d_recent_surface.parquet", index=False)
        # daily mean over domain
        df["date"] = df["time"].dt.floor("D")
        daily = (
            df.groupby("date", as_index=False)
            .agg(
                n=("time", "size"),
                temp_c=("Sea_water_temperature", "mean"),
                salinity=("Sea_water_salinity", "mean"),
            )
        )
        daily.to_parquet(PROC / "imi_conn_3d_recent_daily.parquet", index=False)
        results["recent"] = {
            "status": "ok",
            "time_coverage_start": t0,
            "time_coverage_end": t1,
            "rows": int(len(df)),
            "days": int(len(daily)),
            "raw_csv_bytes": raw_csv.stat().st_size,
            "parquet_bytes": (PROC / "imi_conn_3d_recent_surface.parquet").stat().st_size,
        }
    except Exception as e:
        results["recent"] = {"status": "fail", "error": str(e)}

    # Also download one ANALYSIS noon file as format sample (optional small probe via OPeNDAP ascii subset is heavy).
    # Instead fetch catalog listing snapshot for documentation.
    try:
        r = _get(
            "http://milas.marine.ie/thredds/catalog/IMI_ROMS_HYDRO/CONNEMARA_NATIVE_250M_20L_1H/ANALYSIS/catalog.xml",
            timeout=90,
        )
        if r.status_code == 200:
            cat_path = RAW / "imi_conn" / "ANALYSIS_catalog_snapshot.xml"
            cat_path.write_text(r.text)
            urls = re.findall(r'urlPath="([^"]+)"', r.text)
            results["analysis_catalog"] = {
                "status": "ok",
                "n_files": len(urls),
                "first": urls[0] if urls else None,
                "last": urls[-1] if urls else None,
                "bytes": cat_path.stat().st_size,
            }
    except Exception as e:
        results["analysis_catalog"] = {"status": "fail", "error": str(e)}

    return results


# ---------------- Report ----------------

def write_report(payload: dict) -> Path:
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    crw = payload.get("crw_mhw", {})
    sb = payload.get("smartbay", {})
    met = payload.get("met_eireann", {})
    conn = payload.get("imi_conn", {})

    def _sz(path: str | Path | None) -> str:
        if not path:
            return "—"
        p = Path(path)
        if not p.exists():
            return "missing"
        b = p.stat().st_size
        if b > 1 << 20:
            return f"{b/1e6:.1f} MB"
        if b > 1 << 10:
            return f"{b/1e3:.1f} KB"
        return f"{b} B"

    lines = [
        "# Scout P0 ingest report",
        "",
        f"Generated: **{now}** (Europe/Dublin local from box clock).",
        "",
        "Scope: highest-priority **new** scout datasets. Did **not** re-download OISST / OSTIA / IBI / `habs_phyto`.",
        "",
        "## Summary",
        "",
        "| Dataset | Status | Notes |",
        "| --- | --- | --- |",
        f"| NOAA CRW 5km MHW Watch (STAR NC; PacIOOS `mhw_5km` down) | {'OK' if crw.get('ok_days') else 'FAIL'} | {crw.get('ok_days', 0)}/{crw.get('requested_days', 0)} days Irish bbox |",
        f"| SmartBay CTD (`smartbay_obs_ctd_sbe16` / `spiddal_obs_ctd`) | mixed | see below |",
        f"| Met Éireann Mace Head wind/radiation | {'OK' if met.get('daily_parsed', {}).get('status')=='ok' else 'PARTIAL'} | clidata.met.ie CSVs |",
        f"| MI Connemara ROMS `IMI_CONN_3D` | PARTIAL | recent window only; June 2023 archive not online |",
        "",
        "## 1. NOAA Coral Reef Watch 5km MHW Watch",
        "",
        "Product: **Daily Global 5km Marine Heatwave Watch v1.0.1** (Hobday et al. 2018 categories on CoralTemp).",
        "",
        "- Product page: https://coralreefwatch.noaa.gov/product/marine_heatwave/",
        "- PacIOOS ERDDAP id `mhw_5km`: **unavailable** from this environment (HTTP 404 / TLS EOF).",
        "- Fallback: NOAA STAR HTTPS daily NetCDF `noaa-crw_mhw_v1.0.1_category_YYYYMMDD.nc`.",
        f"- Irish bbox extract 51–56°N, 11–5°W for **{crw.get('start')} → {crw.get('end')}**.",
        f"- Days OK: **{crw.get('ok_days')}** / {crw.get('requested_days')} (June 2023 OK days: **{crw.get('june_2023_ok_days')}**).",
        f"- Stacked Ireland parquet: `{crw.get('ireland_parquet')}` ({_sz(crw.get('ireland_parquet'))}).",
        f"- Daily ocean summary CSV: `data/processed/crw_mhw_ireland_daily_summary.csv`.",
        f"- Product JSON: `{crw.get('product_doc')}`.",
        "",
        "### June 2023 snapshot (Berthou MHW paper link)",
        "",
        "Irish waters on **2023-06-15** (probe day) showed widespread elevated categories (cats 1–5 present in the bbox).",
        "Use `crw_mhw_ireland_daily_summary.csv` filtered to 2023-06 for event timing vs Irish HAB / Berthou et al. North-East Atlantic MHW context.",
        "Category meanings: 0=no MHW … 5=beyond extreme; NaN/land masked separately.",
        "",
        "## 2. SmartBay Observatory CTD",
        "",
    ]
    for did, st in (sb.get("datasets") or {}).items():
        lines += [
            f"### `{did}`",
            "",
            f"- Status: **{st.get('status')}**",
        ]
        if st.get("status") == "ok":
            lines += [
                f"- Raw rows: {st.get('rows_raw')} | daily rows: {st.get('days')}",
                f"- Time: {st.get('time_min')} → {st.get('time_max')}",
                f"- Raw bytes: {st.get('raw_csv_bytes')} | daily parquet: {st.get('daily_parquet_bytes')}",
                f"- Note: {st.get('note')}",
            ]
            if "june_2023_days" in st:
                lines.append(f"- June 2023 daily rows: {st.get('june_2023_days')} (mean T={st.get('june_2023_temp_mean')})")
        else:
            lines.append(f"- Error: `{st.get('error')}`")
        lines.append("")

    lines += [
        "## 3. Met Éireann — Mace Head historical wind / radiation",
        "",
        "Open CSVs (no API key) via **clidata.met.ie** (data.gov.ie package pages point here). `opendata2.met.ie` is only a welcome landing page.",
        "",
        "Exact URLs:",
        "",
        "- Daily: https://clidata.met.ie/cli/climate_data/webdata/dly275.csv (includes `wdsp`, `glorad`)",
        "- Hourly: https://clidata.met.ie/cli/climate_data/webdata/hly275.csv",
        "- Monthly: https://clidata.met.ie/cli/climate_data/webdata/mly275.csv",
        "- Keys: https://www.met.ie/cms/assets/uploads/2018/05/KeyDaily.txt / KeyMonthly.txt",
        "",
        f"- Daily parse: **{met.get('daily_parsed', {}).get('status')}** — rows={met.get('daily_parsed', {}).get('rows')} "
        f"({met.get('daily_parsed', {}).get('date_min')} → {met.get('daily_parsed', {}).get('date_max')}), "
        f"parquet `{_sz(PROC / 'mace_head_met_daily.parquet')}`",
        f"- June 2023: days={met.get('daily_parsed', {}).get('june_2023_days')}, "
        f"mean wind={met.get('daily_parsed', {}).get('june_2023_wdsp_mean_kt')} kt, "
        f"mean glorad={met.get('daily_parsed', {}).get('june_2023_glorad_mean')}",
        f"- Hourly→daily: **{met.get('hourly_daily_parsed', {}).get('status')}** rows_hourly={met.get('hourly_daily_parsed', {}).get('hourly_rows')}",
        "",
        "## 4. MI Connemara ROMS (`IMI_CONN_3D`)",
        "",
        f"- ERDDAP recent pull: **{conn.get('recent', {}).get('status')}** "
        f"({conn.get('recent', {}).get('time_coverage_start')} → {conn.get('recent', {}).get('time_coverage_end')}), "
        f"rows={conn.get('recent', {}).get('rows')}, bytes={conn.get('recent', {}).get('raw_csv_bytes')}",
        f"- ANALYSIS catalog snapshot files: {conn.get('analysis_catalog', {}).get('n_files')} "
        f"({conn.get('analysis_catalog', {}).get('first')} … {conn.get('analysis_catalog', {}).get('last')})",
        "",
        "**June 2023 subset:** not available on public rolling THREDDS/ERDDAP windows (only ~last 8–30 days).",
        "Documented archive paths in `data/raw/imi_conn/thredds_archive_paths.json` for later when MI publishes longer retention:",
        "",
        "- `http://milas.marine.ie/thredds/dodsC/IMI-CONN_AGG`",
        "- `http://milas.marine.ie/thredds/dodsC/IMI_ROMS_HYDRO/CONNEMARA_250M_20L_1H/COMBINED_AGGREGATION`",
        "- `http://milas.marine.ie/thredds/catalog/IMI_ROMS_HYDRO/CONNEMARA_NATIVE_250M_20L_1H/ANALYSIS/catalog.xml`",
        "",
        "## Artifacts (committed reports / small summaries)",
        "",
        "- `data/processed/scout_ingest_report.md` (this file)",
        "- `data/processed/scout_ingest_summary.json`",
        "- `data/processed/crw_mhw_ireland_daily_summary.csv`",
        "- `data/raw/crw_mhw/product.json`",
        "- `data/raw/met_eireann/sources.json`",
        "- `data/raw/imi_conn/thredds_archive_paths.json`",
        "",
        "Large raw CSVs / parquets remain gitignored under `data/raw/` and `data/processed/*`.",
        "",
    ]
    path = PROC / "scout_ingest_report.md"
    path.write_text("\n".join(lines))
    (PROC / "scout_ingest_summary.json").write_text(json.dumps(payload, indent=2, default=str))
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crw-start", default="2022-01-01")
    ap.add_argument("--crw-end", default="2024-12-31")
    ap.add_argument("--crw-workers", type=int, default=10)
    ap.add_argument("--skip-crw", action="store_true")
    ap.add_argument("--skip-smartbay", action="store_true")
    ap.add_argument("--skip-met", action="store_true")
    ap.add_argument("--skip-conn", action="store_true")
    args = ap.parse_args(argv)

    _ensure_dirs()
    payload: dict = {"started_utc": datetime.now(timezone.utc).isoformat()}

    if not args.skip_crw:
        print("== CRW MHW ==", flush=True)
        payload["crw_mhw"] = ingest_crw_mhw(
            date.fromisoformat(args.crw_start),
            date.fromisoformat(args.crw_end),
            workers=args.crw_workers,
        )
    if not args.skip_smartbay:
        print("== SmartBay ==", flush=True)
        payload["smartbay"] = ingest_smartbay()
    if not args.skip_met:
        print("== Met Éireann ==", flush=True)
        payload["met_eireann"] = ingest_met_eireann()
    if not args.skip_conn:
        print("== IMI CONN ==", flush=True)
        payload["imi_conn"] = ingest_imi_conn()

    payload["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report = write_report(payload)
    print(f"Wrote {report}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
