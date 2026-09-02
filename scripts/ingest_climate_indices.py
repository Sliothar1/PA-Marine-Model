#!/usr/bin/env python3
"""Ingest open NAO / EA / AMO climate indices and build week/month join helpers.

Sources (no login):
  - NOAA CPC monthly NAO table
  - NOAA CPC daily NAO ascii
  - NOAA CPC East Atlantic (ea_index.tim)
  - NOAA NCEI ERSST v5 AMO monthly

Outputs under data/external/climate_indices/ and data/processed/.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "external" / "climate_indices" / "raw"
PROC_EXT = ROOT / "data" / "external" / "climate_indices" / "processed"
PROC = ROOT / "data" / "processed"

SOURCES = {
    "nao_monthly_cpc": {
        "url": "https://www.cpc.ncep.noaa.gov/products/precip/CWlink/pna/norm.nao.monthly.b5001.current.ascii.table",
        "file": "nao_monthly_cpc.ascii.table",
        "note": "CPC monthly NAO (1950–present), standardized; year × month table",
    },
    "nao_daily_cpc": {
        "url": "https://ftp.cpc.ncep.noaa.gov/cwlinks/norm.daily.nao.cdas.z500.19500101_current.csv",
        "alt_url": "https://www.ftp.cpc.ncep.noaa.gov/cwlinks/norm.daily.nao.index.b500101.current.ascii",
        "file": "nao_daily_cpc.csv",
        "note": "CPC daily NAO CDAS z500 CSV (1950–present); ascii alt has rare glued -99 missings",
    },
    "ea_monthly_cpc": {
        "url": "https://ftp.cpc.ncep.noaa.gov/wd52dg/data/indices/ea_index.tim",
        "file": "ea_index.tim",
        "note": "CPC East Atlantic monthly teleconnection; 1981–2010 norm; -99.90 = missing/not leading",
    },
    "tele_index_nh": {
        "url": "https://ftp.cpc.ncep.noaa.gov/wd52dg/data/indices/tele_index.nh",
        "file": "nao_tele_from_nh.tim",
        "note": "CPC NH teleconnection bundle (NAO col3, EA col4); optional cross-check",
    },
    "amo_ersst_v5": {
        "url": "https://www.ncei.noaa.gov/pub/data/cmb/ersst/v5/index/ersst.v5.amo.dat",
        "file": "amo_ersst_v5.dat",
        "note": "NCEI ERSST v5 AMO (N Atl 0–60N SSTA °C); Kaplan/PSL AMO discontinued",
    },
}


def _download(force: bool = False) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    meta = {}
    for key, spec in SOURCES.items():
        dest = RAW / spec["file"]
        if dest.exists() and dest.stat().st_size > 100 and not force:
            meta[key] = {"path": str(dest.relative_to(ROOT)), "downloaded": False, "bytes": dest.stat().st_size}
            continue
        urls = [spec["url"]] + ([spec["alt_url"]] if "alt_url" in spec else [])
        err = None
        for u in urls:
            try:
                urlretrieve(u, dest)
                meta[key] = {
                    "path": str(dest.relative_to(ROOT)),
                    "downloaded": True,
                    "url": u,
                    "bytes": dest.stat().st_size,
                }
                err = None
                break
            except Exception as e:  # noqa: BLE001
                err = e
        if err is not None:
            raise RuntimeError(f"Failed to download {key}: {err}")
    return meta


def parse_nao_monthly(path: Path) -> pd.DataFrame:
    # Header line with month names; then YEAR + 12 values (partial year OK)
    lines = path.read_text().strip().splitlines()
    rows = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        year = int(parts[0])
        for m, val in enumerate(parts[1:13], start=1):
            rows.append({"year": year, "month": m, "nao": float(val)})
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))
    return df.sort_values("date").reset_index(drop=True)


def parse_nao_daily(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        # year,month,day,nao_index_cdas
        colmap = {c.lower(): c for c in df.columns}
        y = colmap.get("year")
        m = colmap.get("month")
        d = colmap.get("day")
        nao_col = next(c for c in df.columns if "nao" in c.lower())
        out = pd.DataFrame(
            {
                "year": df[y].astype(int),
                "month": df[m].astype(int),
                "day": df[d].astype(int),
                "nao": pd.to_numeric(df[nao_col], errors="coerce"),
            }
        )
    else:
        # Fixed-ish ASCII: YYYY MM DD value; rare lines glue day+-99.000
        rows = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            # normalize glued missing: "26-99.000" -> "26 -99.000"
            import re

            line = re.sub(r"(\d{1,2})(-99(?:\.\d+)?)", r"\1 \2", line)
            parts = line.split()
            if len(parts) < 4:
                continue
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            val = float(parts[3])
            if val <= -99.0:
                val = float("nan")
            rows.append({"year": year, "month": month, "day": day, "nao": val})
        out = pd.DataFrame(rows)
    out = out[out["nao"].notna() | True]
    out.loc[out["nao"] <= -99.0, "nao"] = pd.NA
    out["nao"] = pd.to_numeric(out["nao"], errors="coerce")
    out["date"] = pd.to_datetime(dict(year=out["year"], month=out["month"], day=out["day"]))
    return out.sort_values("date").reset_index(drop=True)


def parse_ea_monthly(path: Path) -> pd.DataFrame:
    rows = []
    started = False
    for line in path.read_text().splitlines():
        if line.strip().startswith("YEAR"):
            started = True
            continue
        if not started:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        year, month, idx = int(parts[0]), int(parts[1]), float(parts[2])
        if idx <= -99.0:
            idx = np.nan
        rows.append({"year": year, "month": month, "ea": idx})
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))
    return df.sort_values("date").reset_index(drop=True)


def parse_amo_monthly(path: Path) -> pd.DataFrame:
    rows = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            year, month = int(parts[0]), int(parts[1])
            ssta = float(parts[2])
        except ValueError:
            continue
        if not (1 <= month <= 12) or year < 1800:
            continue
        rows.append({"year": year, "month": month, "amo": ssta})
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))
    return df.sort_values("date").reset_index(drop=True)


def _iso_week_frame(dates: pd.Series) -> pd.DataFrame:
    iso = dates.dt.isocalendar()
    return pd.DataFrame(
        {
            "iso_year": iso.year.astype(int),
            "iso_week": iso.week.astype(int),
            "week_start": dates - pd.to_timedelta(dates.dt.weekday, unit="D"),
        }
    )


def build_monthly_bundle(nao: pd.DataFrame, ea: pd.DataFrame, amo: pd.DataFrame) -> pd.DataFrame:
    m = nao[["year", "month", "date", "nao"]].merge(
        ea[["year", "month", "ea"]], on=["year", "month"], how="outer"
    )
    m = m.merge(amo[["year", "month", "amo"]], on=["year", "month"], how="outer")
    m = m.sort_values(["year", "month"]).reset_index(drop=True)
    m["date"] = pd.to_datetime(dict(year=m["year"], month=m["month"], day=1))
    # lags (calendar month)
    for col in ("nao", "ea", "amo"):
        m[f"{col}_lag1m"] = m[col].shift(1)
        m[f"{col}_lag2m"] = m[col].shift(2)
        m[f"{col}_lag3m"] = m[col].shift(3)
        m[f"{col}_roll3m"] = m[col].rolling(3, min_periods=1).mean()
    return m


def monthly_to_week(monthly: pd.DataFrame, week_starts: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Attach monthly indices to ISO weeks via month-of-week_start (as-of join).

    For each week, use the index for the calendar month containing week_start,
    plus precomputed month lags from the monthly series.
    """
    m = monthly.copy()
    m["ym"] = m["year"] * 100 + m["month"]
    value_cols = [c for c in m.columns if c.startswith(("nao", "ea", "amo"))]

    if week_starts is None:
        # Week grid from NAO/EA era (1950); earlier AMO-only months stay on monthly bundle
        d0 = max(m["date"].min(), pd.Timestamp("1950-01-01"))
        d1 = m["date"].max() + pd.offsets.MonthEnd(0)
        ws0 = (d0 - pd.to_timedelta(int(d0.weekday()), unit="D")).normalize()
        week_starts = pd.date_range(ws0, d1, freq="W-MON")

    w = pd.DataFrame({"week_start": pd.to_datetime(week_starts)})
    w["year"] = w["week_start"].dt.year
    w["month"] = w["week_start"].dt.month
    w["ym"] = w["year"] * 100 + w["month"]
    iso = w["week_start"].dt.isocalendar()
    w["iso_year"] = iso.year.astype(int)
    w["iso_week"] = iso.week.astype(int)

    out = w.merge(m[["ym"] + value_cols], on="ym", how="left")
    # Prefer iso keys for HAB panel join
    keep = ["iso_year", "iso_week", "week_start", "year", "month"] + value_cols
    return out[keep].drop_duplicates(["iso_year", "iso_week"]).sort_values(["iso_year", "iso_week"])


def daily_nao_to_week(nao_daily: pd.DataFrame) -> pd.DataFrame:
    d = nao_daily.copy()
    d["week_start"] = d["date"] - pd.to_timedelta(d["date"].dt.weekday, unit="D")
    iso = d["week_start"].dt.isocalendar()
    d["iso_year"] = iso.year.astype(int)
    d["iso_week"] = iso.week.astype(int)
    g = (
        d.groupby(["iso_year", "iso_week"], as_index=False)
        .agg(
            week_start=("week_start", "min"),
            nao_daily_mean=("nao", "mean"),
            nao_daily_min=("nao", "min"),
            nao_daily_max=("nao", "max"),
            nao_daily_n=("nao", "count"),
        )
        .sort_values(["iso_year", "iso_week"])
    )
    g["nao_daily_mean_lag1w"] = g["nao_daily_mean"].shift(1)
    g["nao_daily_mean_roll4w"] = g["nao_daily_mean"].rolling(4, min_periods=1).mean()
    return g


def write_sources_json(dl_meta: dict, ranges: dict) -> None:
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {k: {**v, **SOURCES[k]} for k, v in dl_meta.items()},
        "date_ranges": ranges,
        "units": {
            "nao": "standardized index (CPC; monthly SD 1950–2000 for daily)",
            "ea": "standardized index (CPC; 1981–2010 clim); NaN where -99.90",
            "amo": "°C SSTA North Atlantic 0–60N (ERSST v5 AMO)",
        },
        "join": {
            "month": "merge on year+month",
            "week": "merge on iso_year+iso_week from climate_indices_week.csv / .parquet",
            "lag_convention": "month lags are prior calendar months; week lags from weekly aggregates",
        },
    }
    (RAW.parent / "sources.json").write_text(json.dumps(payload, indent=2))


def main() -> int:
    force = "--force" in sys.argv
    PROC_EXT.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)

    dl_meta = _download(force=force)
    nao_m = parse_nao_monthly(RAW / SOURCES["nao_monthly_cpc"]["file"])
    nao_d = parse_nao_daily(RAW / SOURCES["nao_daily_cpc"]["file"])
    ea = parse_ea_monthly(RAW / SOURCES["ea_monthly_cpc"]["file"])
    amo = parse_amo_monthly(RAW / SOURCES["amo_ersst_v5"]["file"])

    monthly = build_monthly_bundle(nao_m, ea, amo)
    week_from_month = monthly_to_week(monthly)
    week_nao_daily = daily_nao_to_week(nao_d)

    # Combined week helper: monthly-as-of + daily NAO week aggs
    week = week_from_month.merge(
        week_nao_daily.drop(columns=["week_start"], errors="ignore"),
        on=["iso_year", "iso_week"],
        how="outer",
    )
    week = week.sort_values(["iso_year", "iso_week"]).reset_index(drop=True)

    # Paths
    paths = {
        "nao_monthly": PROC_EXT / "nao_monthly.csv",
        "nao_daily": PROC_EXT / "nao_daily.csv",
        "ea_monthly": PROC_EXT / "ea_monthly.csv",
        "amo_monthly": PROC_EXT / "amo_monthly.csv",
        "monthly_bundle": PROC_EXT / "climate_indices_monthly.csv",
        "week_helper": PROC_EXT / "climate_indices_week.csv",
        "week_helper_proc": PROC / "climate_indices_week.csv",
        "monthly_proc": PROC / "climate_indices_monthly.csv",
    }
    nao_m.to_csv(paths["nao_monthly"], index=False)
    nao_d.to_csv(paths["nao_daily"], index=False)
    ea.to_csv(paths["ea_monthly"], index=False)
    amo.to_csv(paths["amo_monthly"], index=False)
    monthly.to_csv(paths["monthly_bundle"], index=False)
    week.to_csv(paths["week_helper"], index=False)
    # Mirror small join helpers into processed for ablation convenience
    week.to_csv(paths["week_helper_proc"], index=False)
    monthly.to_csv(paths["monthly_proc"], index=False)
    try:
        week.to_parquet(PROC_EXT / "climate_indices_week.parquet", index=False)
        monthly.to_parquet(PROC_EXT / "climate_indices_monthly.parquet", index=False)
    except Exception as e:  # noqa: BLE001
        print("parquet skip:", e)

    ranges = {
        "nao_monthly": [str(nao_m["date"].min().date()), str(nao_m["date"].max().date()), int(len(nao_m))],
        "nao_daily": [str(nao_d["date"].min().date()), str(nao_d["date"].max().date()), int(len(nao_d))],
        "ea_monthly": [str(ea["date"].min().date()), str(ea["date"].max().date()), int(ea["ea"].notna().sum())],
        "amo_monthly": [str(amo["date"].min().date()), str(amo["date"].max().date()), int(len(amo))],
        "week_helper": [
            f"{int(week.iloc[0].iso_year)}-W{int(week.iloc[0].iso_week):02d}",
            f"{int(week.iloc[-1].iso_year)}-W{int(week.iloc[-1].iso_week):02d}",
            int(len(week)),
        ],
    }
    write_sources_json(dl_meta, ranges)

    summary = {
        "ranges": ranges,
        "outputs": {k: str(v.relative_to(ROOT)) for k, v in paths.items()},
        "columns_week": list(week.columns),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    (PROC / "climate_indices_ingest_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(ranges, indent=2))
    print("Wrote", paths["week_helper_proc"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
