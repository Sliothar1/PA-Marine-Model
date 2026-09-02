#!/usr/bin/env python3
"""Ingest open Met Éireann west-coast climate drivers for HAB explanation.

Extends Mace Head (275) already in ingest_scout_p0 with Belmullet + other
west/north synoptic stations that carry glorad and/or sunshine + long wind.

Open CSVs: https://clidata.met.ie/cli/climate_data/webdata/{dly,hly,mly}{STN}.csv
No API key. Station IDs verified by HTTP GET (not invented).
"""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "met_eireann"
PROC = ROOT / "data" / "processed"
UA = {"User-Agent": "pa-marine-model/climate-drivers (+research)"}
CLIDATA = "https://clidata.met.ie/cli/climate_data/webdata"

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
            "monthly": "https://data.gov.ie/dataset/belmullet-monthly-data",
        },
        "want": ["daily", "hourly", "monthly"],
    },
    2275: {
        "name": "Valentia Observatory",
        "slug": "valentia",
        "lat": 51.938,
        "lon": -10.241,
        "height_m": 24,
        "role": "sw_west_coast_long_wind_radiation",
        "want": ["daily", "monthly"],
    },
    1575: {
        "name": "Malin Head",
        "slug": "malin_head",
        "lat": 55.372,
        "lon": -7.339,
        "height_m": 20,
        "role": "nw_long_wind_sunshine_radiation",
        "want": ["daily", "monthly"],
    },
    1175: {
        "name": "Newport",
        "slug": "newport",
        "lat": 53.924,
        "lon": -9.573,
        "height_m": 22,
        "role": "mayo_connemara_adjacent_glorad",
        "want": ["daily"],
    },
    275: {
        "name": "Mace Head",
        "slug": "mace_head",
        "lat": 53.326,
        "lon": -9.901,
        "height_m": 21,
        "role": "connemara_already_ingested_refresh_ok",
        "want": ["daily", "monthly"],
        "refresh_if_missing_only": False,
    },
}

DAILY_NUM = [
    "wdsp", "hm", "ddhm", "hg", "glorad", "sun", "maxtp", "mintp", "rain",
    "soil", "cbl", "pe", "evap",
]
PREFIX = {"daily": "dly", "hourly": "hly", "monthly": "mly"}


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
    # drop duplicate indicator columns named 'ind' — keep first occurrence after rename later
    # Met files often have repeated 'ind' column names; pandas suffixes .1, .2
    if "date" not in df.columns:
        return {"status": "no_date_col", "columns": list(df.columns)}
    df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True, errors="coerce")
    # glorad may appear once; sun once
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
    # weekly means for HAB join
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
    for c in ["year", "month", "meant", "maxtp", "mintp", "mnmax", "mnmin", "rain", "wdsp", "sun", "maxgt", "mxgt"]:
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
    return {
        "status": "ok",
        "rows": int(len(out)),
        "year_min": int(out["year"].min()),
        "year_max": int(out["year"].max()),
        "fields": keep,
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
    # Pivot key radiation/wind stations onto common week index
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
            # concat of stations leaves NaN-only columns (e.g. Mace has no sun)
            if src in sub.columns and sub[src].notna().any():
                cols[src] = dst
        p = sub.rename(columns=cols)[list(cols.values())]
        pieces.append(p)
    if not pieces:
        return {"status": "no_pieces"}
    panel = pieces[0]
    for p in pieces[1:]:
        panel = panel.merge(p, on=["iso_year", "iso_week"], how="outer")
    # Regional composites (mean of available west stations)
    glorad_cols = [c for c in panel.columns if c.endswith("_glorad")]
    sun_cols = [c for c in panel.columns if c.endswith("_sun")]
    wdsp_cols = [c for c in panel.columns if c.endswith("_wdsp")]
    if glorad_cols:
        panel["met_west_glorad"] = panel[glorad_cols].mean(axis=1)
    if sun_cols:
        panel["met_west_sun"] = panel[sun_cols].mean(axis=1)
    if wdsp_cols:
        panel["met_west_wdsp"] = panel[wdsp_cols].mean(axis=1)
    # Prefer Belmullet sun for radiation narrative when Mace lacks sun
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


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)
    report: dict = {"stations": {}, "downloads": {}, "daily_parsed": {}, "monthly_parsed": {}}

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

    report["west_week_panel"] = build_west_coast_week_panel(report["daily_parsed"])

    # Update sources JSON (merge with existing Mace Head sources)
    sources_path = RAW / "sources_climate_drivers.json"
    sources = {
        "generated": "scripts/ingest_met_climate_drivers.py",
        "clidata_pattern": f"{CLIDATA}/{{dly|hly|mly}}{{STN}}.csv",
        "stations": report["stations"],
        "downloads": report["downloads"],
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
        ],
    }
    sources_path.write_text(json.dumps(sources, indent=2))
    report["sources_json"] = str(sources_path)

    out_json = PROC / "met_climate_drivers_ingest_summary.json"
    out_json.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({
        "summary": {
            "n_stations": len(STATIONS),
            "daily_ok": {k: v.get("status") for k, v in report["daily_parsed"].items()},
            "west_week": report["west_week_panel"].get("status"),
            "out": str(out_json),
        }
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
