#!/usr/bin/env python3
"""Ingest open Met Éireann west-coast climate drivers for HAB explanation.

Extends Mace Head (275) already in ingest_scout_p0 with Belmullet + other
west/north synoptic stations that carry glorad and/or sunshine + long wind.

Open CSVs: https://clidata.met.ie/cli/climate_data/webdata/{dly,hly,mly}{STN}.csv
No API key. Station IDs verified by HTTP GET (not invented).

Also:
- Fold Garry manual monthly drop (data/external/met_eireann/mace_head_monthly.csv)
- Recent Agmet monthly solar via prodapi.met.ie (Belmullet + Mace Head)
- Island of Ireland long-term Temperature + Precipitation series (warming narrative)
- MÉRA / TRANSLATE documented as paper/demo story only (no credentials / no heavy GRIB ingest)
"""
from __future__ import annotations

import json
import sys
import zipfile
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "met_eireann"
RAW_LT = ROOT / "data" / "raw" / "met_eireann_longterm"
EXT = ROOT / "data" / "external" / "met_eireann"
PROC = ROOT / "data" / "processed"
UA = {"User-Agent": "pa-marine-model/climate-drivers (+research)"}
CLIDATA = "https://clidata.met.ie/cli/climate_data/webdata"
AGMET = "https://prodapi.met.ie/monthly-data"

# Verified open stations (2026-09-02 HTTP 200 + header Station Name)
STATIONS = {
    2375: {
        "name": "Belmullet",
        "slug": "belmullet",
        "lat": 54.228,
        "lon": -10.007,
        "height_m": 9,
        "role": "primary_radiation_sunshine_west",
        "data_gov": {
            "daily": "https://data.gov.ie/dataset/belmullet-daily-data",
            "monthly": "https://data.gov.ie/dataset/monthly-weather-belmullet",
            "hourly": "https://data.gov.ie/dataset/belmullet-hourly-data",
        },
        "agmet_slug": "Belmullet",
        "want": ["daily", "hourly", "monthly"],
    },
    2275: {
        "name": "Valentia Observatory",
        "slug": "valentia",
        "lat": 51.938,
        "lon": -10.241,
        "height_m": 24,
        "role": "sw_west_coast_long_wind_radiation",
        "agmet_slug": "Valentia",
        "want": ["daily", "monthly"],
    },
    1575: {
        "name": "Malin Head",
        "slug": "malin_head",
        "lat": 55.372,
        "lon": -7.339,
        "height_m": 20,
        "role": "nw_long_wind_sunshine_radiation",
        "agmet_slug": "Malin-Head",
        "want": ["daily", "monthly"],
    },
    1175: {
        "name": "Newport",
        "slug": "newport",
        "lat": 53.924,
        "lon": -9.573,
        "height_m": 22,
        "role": "mayo_connemara_adjacent_glorad",
        "want": ["daily", "monthly"],
    },
    275: {
        "name": "Mace Head",
        "slug": "mace_head",
        "lat": 53.326,
        "lon": -9.901,
        "height_m": 21,
        "role": "connemara_already_ingested_refresh_ok",
        "agmet_slug": "mace-head",
        "want": ["daily", "monthly"],
        "refresh_if_missing_only": False,
    },
}

DAILY_NUM = [
    "wdsp", "hm", "ddhm", "hg", "glorad", "sun", "maxtp", "mintp", "rain",
    "soil", "cbl", "pe", "evap",
]
PREFIX = {"daily": "dly", "hourly": "hly", "monthly": "mly"}

# Catalogue URLs (document + light ingest where free/small)
CATALOGUE = {
    "available_data": "https://www.met.ie/climate/available-data",
    "historical_data": "https://www.met.ie/climate/available-data/historical-data",
    "monthly_data": "https://www.met.ie/climate/available-data/monthly-data",
    "long_term_data_sets": "https://www.met.ie/climate/available-data/long-term-data-sets",
    "island_of_ireland_temperature_csv": "https://www.met.ie/cms/assets/uploads/2025/01/longseries_2024.csv",
    "island_of_ireland_temperature_page": "https://www.met.ie/climate/what-we-measure/temperature",
    "iip_network_zip": "https://www.met.ie/cms/assets/uploads/2018/01/Long-Term-IIP-network-1.zip",
    "iip_composite_1711_2016_zip": "https://www.met.ie/cms/assets/uploads/2018/01/Long-Term-IIP-1711-2016.zip",
    "iip_handle": "http://hdl.handle.net/20.500.14765/76134",
    "mera_page": "https://www.met.ie/climate/available-data/mera",
    "mera_data_list": "https://www.met.ie/climate/mera-data-list/",
    "translate_science": "https://www.met.ie/science/translate",
    "translate2": "https://www.met.ie/translate2",
    "agmet_belmullet": "https://prodapi.met.ie/monthly-data/Belmullet",
    "agmet_mace_head": "https://prodapi.met.ie/monthly-data/mace-head",
    "clidata_pattern": f"{CLIDATA}/{{dly|hly|mly}}{{STN}}.csv",
}


def _get(url: str, timeout: int = 300) -> requests.Response:
    return requests.get(url, timeout=timeout, headers=UA)


def parse_met_csv(path: Path) -> pd.DataFrame:
    """Skip Met multi-line header until a line starting with date,/year,."""
    text = path.read_text(errors="ignore").splitlines()
    hdr_i = next(
        (i for i, l in enumerate(text) if l.lower().startswith(("date,", "year,"))),
        None,
    )
    if hdr_i is None:
        raise ValueError(f"No date/year header in {path}")
    return pd.read_csv(StringIO("\n".join(text[hdr_i:])), low_memory=False)


def download_product(stn: int, product: str, force: bool = False) -> dict:
    prefix = PREFIX[product]
    url = f"{CLIDATA}/{prefix}{stn}.csv"
    slug = STATIONS[stn]["slug"]
    dest = RAW / f"{slug}_{product}_{prefix}{stn}.csv"
    if dest.exists() and dest.stat().st_size > 1000 and not force:
        return {"status": "cached", "bytes": dest.stat().st_size, "path": str(dest), "url": url}
    print(f"  download {product} stn={stn} {url}", flush=True)
    r = _get(url)
    if r.status_code != 200:
        return {"status": f"http_{r.status_code}", "url": url}
    # soft-404 HTML
    if b"<html" in r.content[:200].lower():
        return {"status": "html_not_csv", "url": url}
    dest.write_bytes(r.content)
    return {"status": "ok", "bytes": dest.stat().st_size, "path": str(dest), "url": url}


def process_daily(stn: int, raw_path: Path) -> dict:
    meta = STATIONS[stn]
    df = parse_met_csv(raw_path)
    if "date" not in df.columns:
        return {"status": "no_date_col", "columns": list(df.columns)}
    df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True, errors="coerce")
    for c in DAILY_NUM:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    keep = ["date"] + [c for c in DAILY_NUM if c in df.columns]
    out = df[keep].dropna(subset=["date"]).sort_values("date").drop_duplicates("date")
    out["station_no"] = stn
    out["station_name"] = meta["name"]
    pq = PROC / f"{meta['slug']}_met_daily.parquet"
    csv = PROC / f"{meta['slug']}_met_daily.csv"
    out.to_parquet(pq, index=False)
    out.to_csv(csv, index=False)
    out = out.copy()
    iso = out["date"].dt.isocalendar()
    out["iso_year"] = iso.year.astype(int)
    out["iso_week"] = iso.week.astype(int)
    agg = {c: "mean" for c in ["wdsp", "glorad", "sun", "maxtp", "mintp", "rain"] if c in out.columns}
    if agg:
        week = out.groupby(["iso_year", "iso_week"], as_index=False).agg(agg)
        week["station_no"] = stn
        week["station_name"] = meta["name"]
        week.to_parquet(PROC / f"{meta['slug']}_met_week.parquet", index=False)
        week.to_csv(PROC / f"{meta['slug']}_met_week.csv", index=False)
    j = out[(out["date"] >= "2023-06-01") & (out["date"] < "2023-07-01")]
    return {
        "status": "ok",
        "rows": int(len(out)),
        "date_min": str(out["date"].min().date()),
        "date_max": str(out["date"].max().date()),
        "fields": [c for c in keep if c != "date"],
        "n_glorad_nonnull": int(out["glorad"].notna().sum()) if "glorad" in out else 0,
        "n_sun_nonnull": int(out["sun"].notna().sum()) if "sun" in out else 0,
        "june_2023_glorad_mean": float(j["glorad"].mean()) if len(j) and "glorad" in j else None,
        "june_2023_sun_mean": float(j["sun"].mean()) if len(j) and "sun" in j and j["sun"].notna().any() else None,
        "june_2023_wdsp_mean_kt": float(j["wdsp"].mean()) if len(j) and "wdsp" in j else None,
        "parquet": str(pq),
        "csv": str(csv),
    }


def process_monthly(stn: int, raw_path: Path) -> dict:
    meta = STATIONS[stn]
    df = parse_met_csv(raw_path)
    for c in ["year", "month", "meant", "maxtp", "mintp", "mnmax", "mnmin", "rain", "wdsp", "sun", "maxgt", "mxgt", "gmin"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "year" not in df.columns or "month" not in df.columns:
        return {"status": "no_year_month", "columns": list(df.columns)}
    keep = [c for c in df.columns if c in {
        "year", "month", "meant", "maxtp", "mintp", "mnmax", "mnmin", "rain",
        "wdsp", "sun", "maxgt", "mxgt", "gmin",
    }]
    out = df[keep].dropna(subset=["year", "month"]).copy()
    out["station_no"] = stn
    out["station_name"] = meta["name"]
    pq = PROC / f"{meta['slug']}_met_monthly.parquet"
    csv = PROC / f"{meta['slug']}_met_monthly.csv"
    out.to_parquet(pq, index=False)
    out.to_csv(csv, index=False)
    sun_nn = int(out["sun"].notna().sum()) if "sun" in out else 0
    return {
        "status": "ok",
        "rows": int(len(out)),
        "year_min": int(out["year"].min()),
        "year_max": int(out["year"].max()),
        "fields": keep,
        "n_sun_nonnull": sun_nn,
        "sun_blank_note": (
            "sun 100% blank on open mly CSV — use Belmullet daily/monthly sun or Agmet solar_radiation"
            if sun_nn == 0 and meta["slug"] == "mace_head"
            else None
        ),
        "parquet": str(pq),
        "csv": str(csv),
    }


def fold_garry_monthly() -> dict:
    """Fold Garry's Mace Head monthly drop into processed + lag-friendly features."""
    src = EXT / "mace_head_monthly.csv"
    if not src.exists():
        return {"status": "missing", "expected": str(src)}
    df = parse_met_csv(src)
    for c in ["year", "month", "meant", "maxtp", "mintp", "mnmax", "mnmin", "rain", "wdsp", "sun", "maxgt", "mxgt", "gmin"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    keep = [c for c in [
        "year", "month", "meant", "maxtp", "mintp", "mnmax", "mnmin", "rain",
        "gmin", "wdsp", "maxgt", "mxgt", "sun",
    ] if c in df.columns]
    out = df[keep].dropna(subset=["year", "month"]).copy()
    out["station_no"] = 275
    out["station_name"] = "Mace Head"
    out["source"] = "garry_external_drop"
    # Prefer open clidata monthly if present; Garry drop is authoritative Connemara context copy
    pq = PROC / "mace_head_garry_monthly.parquet"
    csv = PROC / "mace_head_garry_monthly.csv"
    out.to_parquet(pq, index=False)
    out.to_csv(csv, index=False)

    # Optional lag features for Connemara context (month-level)
    feat = out[["year", "month", "meant", "rain", "wdsp"]].sort_values(["year", "month"]).copy()
    feat["meant_lag1m"] = feat["meant"].shift(1)
    feat["rain_lag1m"] = feat["rain"].shift(1)
    feat["wdsp_lag1m"] = feat["wdsp"].shift(1)
    feat["meant_roll3m"] = feat["meant"].rolling(3, min_periods=1).mean()
    feat_path = PROC / "mace_head_garry_monthly_lag_features.csv"
    feat.to_csv(feat_path, index=False)

    j = out[(out["year"] == 2023) & (out["month"] == 6)]
    sun_nn = int(out["sun"].notna().sum()) if "sun" in out else 0
    return {
        "status": "ok",
        "source_path": str(src),
        "rows": int(len(out)),
        "year_min": int(out["year"].min()),
        "year_max": int(out["year"].max()),
        "fields": keep,
        "n_sun_nonnull": sun_nn,
        "sun_note": "100% blank — do not expect sunshine from Garry monthly; use Belmullet daily sun/glorad",
        "june_2023_meant_c": float(j["meant"].iloc[0]) if len(j) and pd.notna(j["meant"].iloc[0]) else None,
        "parquet": str(pq),
        "csv": str(csv),
        "lag_features": str(feat_path),
        "station_meta": {"lat": 53.326, "lon": -9.901, "height_m": 21},
    }


def _flatten_agmet_report(report: dict, value_col: str) -> pd.DataFrame:
    month_map = {
        "january": 1, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12,
    }
    rows = []
    for year_s, months in (report or {}).items():
        if year_s == "LTA" or not isinstance(months, dict):
            continue
        try:
            year = int(year_s)
        except ValueError:
            continue
        for mk, mv in months.items():
            m = month_map.get(str(mk).lower())
            if m is None:
                continue
            val = pd.to_numeric(mv, errors="coerce")
            rows.append({"year": year, "month": m, value_col: val})
    return pd.DataFrame(rows)


def ingest_agmet_monthly(stn: int) -> dict:
    """Recent (~3y) Agmet monthly including total global solar radiation (J/cm2)."""
    meta = STATIONS[stn]
    slug_api = meta.get("agmet_slug")
    if not slug_api:
        return {"status": "no_agmet_slug"}
    url = f"{AGMET}/{slug_api}"
    print(f"  agmet monthly {meta['name']} {url}", flush=True)
    r = _get(url, timeout=60)
    if r.status_code != 200:
        return {"status": f"http_{r.status_code}", "url": url}
    try:
        data = r.json()
    except Exception as e:
        return {"status": f"json_err:{e}", "url": url}
    if not isinstance(data, dict) or "station" not in data:
        return {"status": "empty_or_unexpected", "url": url, "preview": str(data)[:200]}

    raw_path = RAW / f"{meta['slug']}_agmet_monthly.json"
    raw_path.write_text(json.dumps(data, indent=2))

    frames = []
    mapping = {
        "total_rainfall": "rain",
        "mean_temperature": "meant",
        "soil_temperature": "soil",
        "solar_radiation": "solar_radiation_jcm2",
        "potential_evapotranspiration": "pe",
        "evaporation": "evap",
        "degree_days_below_fiften_point_five_degrees_celsius": "dd_below_15_5",
    }
    for src, dst in mapping.items():
        if src in data and isinstance(data[src], dict) and "report" in data[src]:
            frames.append(_flatten_agmet_report(data[src]["report"], dst))
    if not frames:
        return {"status": "no_frames", "url": url, "raw": str(raw_path)}
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on=["year", "month"], how="outer")
    out["station_no"] = stn
    out["station_name"] = meta["name"]
    out["source"] = "prodapi_agmet_monthly"
    out = out.sort_values(["year", "month"])
    pq = PROC / f"{meta['slug']}_agmet_monthly.parquet"
    csv = PROC / f"{meta['slug']}_agmet_monthly.csv"
    out.to_parquet(pq, index=False)
    out.to_csv(csv, index=False)
    solar_nn = int(out["solar_radiation_jcm2"].notna().sum()) if "solar_radiation_jcm2" in out else 0
    return {
        "status": "ok",
        "url": url,
        "raw_json": str(raw_path),
        "rows": int(len(out)),
        "year_min": int(out["year"].min()) if len(out) else None,
        "year_max": int(out["year"].max()) if len(out) else None,
        "n_solar_nonnull": solar_nn,
        "note": "Agmet API typically current + previous ~3 years only; long glorad/sun from clidata daily",
        "parquet": str(pq),
        "csv": str(csv),
    }


def build_west_coast_week_panel(parsed_daily: dict) -> dict:
    """Combine Mace Head + Belmullet (+ Newport) week means as regional columns."""
    frames = []
    for stn, info in parsed_daily.items():
        if info.get("status") != "ok":
            continue
        slug = STATIONS[stn]["slug"]
        wp = PROC / f"{slug}_met_week.csv"
        if not wp.exists():
            continue
        w = pd.read_csv(wp)
        frames.append(w)
    if not frames:
        return {"status": "empty"}
    allw = pd.concat(frames, ignore_index=True)
    key_stns = {
        275: "mace",
        2375: "belmullet",
        1175: "newport",
        2275: "valentia",
        1575: "malin",
    }
    pieces = []
    for stn, prefix in key_stns.items():
        sub = allw[allw["station_no"] == stn]
        if sub.empty:
            continue
        cols = {"iso_year": "iso_year", "iso_week": "iso_week"}
        for src, dst in [
            ("glorad", f"met_{prefix}_glorad"),
            ("sun", f"met_{prefix}_sun"),
            ("wdsp", f"met_{prefix}_wdsp"),
            ("rain", f"met_{prefix}_rain"),
        ]:
            if src in sub.columns:
                cols[src] = dst
        p = sub.rename(columns=cols)[list(cols.values())]
        pieces.append(p)
    if not pieces:
        return {"status": "no_pieces"}
    panel = pieces[0]
    for p in pieces[1:]:
        panel = panel.merge(p, on=["iso_year", "iso_week"], how="outer")
    glorad_cols = [c for c in panel.columns if c.endswith("_glorad")]
    sun_cols = [c for c in panel.columns if c.endswith("_sun")]
    wdsp_cols = [c for c in panel.columns if c.endswith("_wdsp")]
    if glorad_cols:
        panel["met_west_glorad"] = panel[glorad_cols].mean(axis=1)
    if sun_cols:
        panel["met_west_sun"] = panel[sun_cols].mean(axis=1)
    if wdsp_cols:
        panel["met_west_wdsp"] = panel[wdsp_cols].mean(axis=1)
    if "met_belmullet_sun" in panel.columns:
        panel["met_sun"] = panel["met_belmullet_sun"]
    elif sun_cols:
        panel["met_sun"] = panel[sun_cols[0]]
    if "met_mace_glorad" in panel.columns:
        panel["met_glorad"] = panel["met_mace_glorad"]
        if "met_belmullet_glorad" in panel.columns:
            panel["met_glorad"] = panel["met_glorad"].fillna(panel["met_belmullet_glorad"])
    elif glorad_cols:
        panel["met_glorad"] = panel[glorad_cols[0]]
    if "met_mace_wdsp" in panel.columns:
        panel["met_wdsp"] = panel["met_mace_wdsp"]
    elif wdsp_cols:
        panel["met_wdsp"] = panel[wdsp_cols[0]]

    out_pq = PROC / "met_west_climate_week.parquet"
    out_csv = PROC / "met_west_climate_week.csv"
    panel = panel.sort_values(["iso_year", "iso_week"])
    panel.to_parquet(out_pq, index=False)
    panel.to_csv(out_csv, index=False)
    return {
        "status": "ok",
        "rows": int(len(panel)),
        "columns": list(panel.columns),
        "parquet": str(out_pq),
        "csv": str(out_csv),
        "year_min": int(panel["iso_year"].min()),
        "year_max": int(panel["iso_year"].max()),
    }


def ingest_island_of_ireland_series() -> dict:
    """Long-term Island of Ireland Temperature + Precipitation (warming narrative)."""
    RAW_LT.mkdir(parents=True, exist_ok=True)
    out: dict = {"temperature": {}, "precipitation": {}}

    # Temperature annual series (small CSV)
    t_url = CATALOGUE["island_of_ireland_temperature_csv"]
    print(f"  Island of Ireland Temperature {t_url}", flush=True)
    r = _get(t_url, timeout=60)
    if r.status_code == 200 and b"<html" not in r.content[:200].lower():
        dest = RAW_LT / "island_of_ireland_temperature_longseries_2024.csv"
        dest.write_bytes(r.content)
        df = pd.read_csv(dest)
        # columns: year, Annual
        rename = {c: c.strip() for c in df.columns}
        df = df.rename(columns=rename)
        ycol = "year" if "year" in df.columns else df.columns[0]
        vcol = "Annual" if "Annual" in df.columns else df.columns[1]
        df[ycol] = pd.to_numeric(df[ycol], errors="coerce")
        df[vcol] = pd.to_numeric(df[vcol], errors="coerce")
        df = df.dropna(subset=[ycol]).sort_values(ycol)
        df = df.rename(columns={ycol: "year", vcol: "annual_mean_c"})
        # anomaly vs 1961-1990 (Met page cites 9.55°C)
        clim = df[(df["year"] >= 1961) & (df["year"] <= 1990)]["annual_mean_c"].mean()
        df["anom_vs_1961_1990"] = df["annual_mean_c"] - clim
        # decade trend
        years = df["year"].to_numpy(dtype=float)
        vals = df["annual_mean_c"].to_numpy(dtype=float)
        import numpy as np
        slope, intercept = np.polyfit(years, vals, 1)
        pq = PROC / "island_of_ireland_temperature_annual.parquet"
        csv = PROC / "island_of_ireland_temperature_annual.csv"
        df.to_parquet(pq, index=False)
        df.to_csv(csv, index=False)
        out["temperature"] = {
            "status": "ok",
            "url": t_url,
            "raw": str(dest),
            "rows": int(len(df)),
            "year_min": int(df["year"].min()),
            "year_max": int(df["year"].max()),
            "clim_1961_1990_c": float(clim),
            "c_per_decade": float(slope * 10),
            "r2": float(1 - ((vals - (intercept + slope * years)) ** 2).sum() / ((vals - vals.mean()) ** 2).sum()),
            "parquet": str(pq),
            "csv": str(csv),
        }
    else:
        out["temperature"] = {"status": f"http_{r.status_code}", "url": t_url}

    # Precipitation zips (network + composite) — light archive for narrative
    for key, fname in [
        ("iip_network_zip", "Long-Term-IIP-network-1.zip"),
        ("iip_composite_1711_2016_zip", "Long-Term-IIP-1711-2016.zip"),
    ]:
        url = CATALOGUE[key]
        dest = RAW_LT / fname
        print(f"  IIP {fname} {url}", flush=True)
        if dest.exists() and dest.stat().st_size > 1000:
            info = {"status": "cached", "path": str(dest), "url": url, "bytes": dest.stat().st_size}
        else:
            r = _get(url, timeout=180)
            if r.status_code != 200 or b"<html" in r.content[:200].lower():
                info = {"status": f"http_{r.status_code}", "url": url}
                out["precipitation"][key] = info
                continue
            dest.write_bytes(r.content)
            info = {"status": "ok", "path": str(dest), "url": url, "bytes": dest.stat().st_size}
        # list members; extract composite CSV if obvious
        try:
            with zipfile.ZipFile(dest) as zf:
                names = zf.namelist()
                info["members"] = names[:40]
                info["n_members"] = len(names)
                # Prefer a composite / island series CSV for processed copy
                prefer = [n for n in names if n.lower().endswith(".csv") and (
                    "composite" in n.lower() or "island" in n.lower() or "iip" in n.lower()
                )]
                pick = prefer[0] if prefer else next((n for n in names if n.lower().endswith(".csv")), None)
                if pick:
                    extracted = RAW_LT / Path(pick).name
                    extracted.write_bytes(zf.read(pick))
                    info["extracted_csv"] = str(extracted)
                    try:
                        pdf = pd.read_csv(extracted)
                        proc_csv = PROC / f"iip_{Path(pick).stem}.csv"
                        pdf.to_csv(proc_csv, index=False)
                        info["processed_csv"] = str(proc_csv)
                        info["columns"] = list(pdf.columns)[:20]
                        info["rows"] = int(len(pdf))
                    except Exception as e:
                        info["csv_parse"] = str(e)
        except Exception as e:
            info["zip_err"] = str(e)
        out["precipitation"][key] = info

    out["catalogue_urls"] = {
        "temperature_page": CATALOGUE["island_of_ireland_temperature_page"],
        "long_term_data_sets": CATALOGUE["long_term_data_sets"],
        "iip_handle": CATALOGUE["iip_handle"],
    }
    return out


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "stations": {},
        "downloads": {},
        "daily_parsed": {},
        "monthly_parsed": {},
        "agmet": {},
        "catalogue_urls": CATALOGUE,
        "mera_translate_note": (
            "MÉRA reanalysis and TRANSLATE climate projections: paper/demo story only. "
            "Sample GRIBs exist under met.ie/downloads but full archives need Met Éireann "
            "access workflow — no credentials invented; no heavy GRIB ingest in this package."
        ),
    }

    for stn, meta in STATIONS.items():
        report["stations"][stn] = {
            k: meta[k] for k in ("name", "slug", "lat", "lon", "height_m", "role")
        }
        for product in meta["want"]:
            key = f"{stn}_{product}"
            report["downloads"][key] = download_product(stn, product)
            dinfo = report["downloads"][key]
            if dinfo.get("status") not in {"ok", "cached"}:
                continue
            path = Path(dinfo["path"])
            if product == "daily":
                report["daily_parsed"][stn] = process_daily(stn, path)
            elif product == "monthly":
                report["monthly_parsed"][stn] = process_monthly(stn, path)

        if meta.get("agmet_slug"):
            report["agmet"][stn] = ingest_agmet_monthly(stn)

    report["garry_monthly"] = fold_garry_monthly()
    report["west_week_panel"] = build_west_coast_week_panel(report["daily_parsed"])
    report["island_of_ireland"] = ingest_island_of_ireland_series()

    sources_path = RAW / "sources_climate_drivers.json"
    sources = {
        "generated": "scripts/ingest_met_climate_drivers.py",
        "catalogue": CATALOGUE,
        "stations": report["stations"],
        "downloads": report["downloads"],
        "garry_monthly": report["garry_monthly"],
        "agmet": report["agmet"],
        "island_of_ireland": {
            k: {kk: vv for kk, vv in v.items() if kk != "members"}
            if isinstance(v, dict)
            else v
            for k, v in report["island_of_ireland"].items()
        },
        "note_climate_statements": (
            "Met Éireann monthly/annual Climate Statements are narrative PDFs on met.ie "
            "(not open CSV). Documented for manual export in docs/CLIMATE_DRIVERS.md."
        ),
        "manual_export_candidates": [
            "https://www.met.ie/climate/available-data/monthly-data",
            "https://www.met.ie/climate/climate-change (climate statements landing)",
            "Roundstone dly1725 rain-only (Connemara local precip) — already open but rain-only",
            "Shannon Airport dly518 long wind + sun (no glorad in open daily CSV)",
            "Knock Airport dly4935 sun + wind (no glorad)",
            "Mace Head monthly sun blank on open mly275 / Garry drop — export Belmullet daily sun or Agmet solar",
            "MÉRA full fields via https://www.met.ie/climate/available-data/mera (access workflow; not ingested)",
            "TRANSLATE projections https://www.met.ie/science/translate (story only)",
        ],
    }
    sources_path.write_text(json.dumps(sources, indent=2, default=str))
    report["sources_json"] = str(sources_path)

    out_json = PROC / "met_climate_drivers_ingest_summary.json"
    # Slim precipitation member lists for summary size
    slim = json.loads(json.dumps(report, default=str))
    out_json.write_text(json.dumps(slim, indent=2, default=str))
    print(json.dumps({
        "summary": {
            "n_stations": len(STATIONS),
            "daily_ok": {str(k): v.get("status") for k, v in report["daily_parsed"].items()},
            "monthly_ok": {str(k): v.get("status") for k, v in report["monthly_parsed"].items()},
            "garry": report["garry_monthly"].get("status"),
            "agmet": {str(k): v.get("status") for k, v in report["agmet"].items()},
            "ii_temp": report["island_of_ireland"].get("temperature", {}).get("status"),
            "west_week": report["west_week_panel"].get("status"),
            "out": str(out_json),
        }
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
