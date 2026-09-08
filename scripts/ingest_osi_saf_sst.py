#!/usr/bin/env python3
"""Ingest EUMETSAT OSI SAF SST (OSI-203-a Metop-B L3C NHL) for Irish shelf.

Independent spring–summer MHW cross-check vs OISST/OSTIA (not a duplicate narrative).

Source: MET Norway THREDDS fileServer (anonymous HTTPS), product OSI-203-a
  AVHRR METOP-B L3C Ice and Sea Surface Temperature (poleward of 50°N).
  Catalog: https://thredds.met.no/thredds/catalog/osisaf/met.no/sst/203a/catalog.html

Downloads midday (12:00) granules for May–Aug, extracts HAB station pixels
(using onboard lat/lon), writes daily + week panels under data/external/osi_saf_sst/
and data/processed/.
"""
from __future__ import annotations

import argparse
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "external" / "osi_saf_sst"
PROC = ROOT / "data" / "processed"
JOINED = PROC / "joined_features.parquet"
CAT_BASE = "https://thredds.met.no/thredds/catalog/osisaf/met.no/sst/203a"
FILE_BASE = "https://thredds.met.no/thredds/fileServer/osisaf/met.no/sst/203a"
PRODUCT_ID = "OSI-203-a"
GHRSST_ID = "AVHRR_METOP_B-OSISAF-L3C-v1.0"


def stations_from_joined() -> pd.DataFrame:
    df = pd.read_parquet(JOINED, columns=["location_id", "latitude", "longitude"])
    return df.drop_duplicates("location_id").reset_index(drop=True)


def list_midday_files(year: int, month: int, day: int) -> list[str]:
    url = f"{CAT_BASE}/{year:04d}/{month:02d}/{day:02d}/catalog.xml"
    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        return []
    root = ET.fromstring(r.content)
    ns = {"t": "http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"}
    names = []
    for ds in root.findall(".//t:dataset", ns):
        name = ds.attrib.get("name", "")
        if name.endswith(".nc") and "120000" in name:
            names.append(name)
    return names


def download_file(year: int, month: int, day: int, name: str, dest: Path) -> Path | None:
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    url = f"{FILE_BASE}/{year:04d}/{month:02d}/{day:02d}/{name}"
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=300)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            return dest
        except Exception as exc:  # noqa: BLE001
            print(f"  dl retry {attempt+1} {name}: {exc}", flush=True)
            time.sleep(1.5 * (attempt + 1))
    return None


def extract_stations(nc_path: Path, stations: pd.DataFrame, ql_min: int = 3) -> pd.DataFrame:
    import xarray as xr

    ds = xr.open_dataset(nc_path)
    lat = np.asarray(ds["lat"].values, dtype=float)
    lon = np.asarray(ds["lon"].values, dtype=float)
    sst_k = np.asarray(ds["sea_surface_temperature"].isel(time=0).values, dtype=float)
    ql = np.asarray(ds["quality_level"].isel(time=0).values, dtype=float)
    t = pd.to_datetime(ds["time"].values[0]).tz_localize(None).normalize()
    # ocean candidates near Ireland
    cand = (
        (lat >= 50.5)
        & (lat <= 56.5)
        & (lon >= -12.0)
        & (lon <= -5.0)
        & np.isfinite(sst_k)
        & (ql >= ql_min)
    )
    if not cand.any():
        # relax quality
        cand = (
            (lat >= 50.5)
            & (lat <= 56.5)
            & (lon >= -12.0)
            & (lon <= -5.0)
            & np.isfinite(sst_k)
        )
    if not cand.any():
        return pd.DataFrame()
    iy, ix = np.where(cand)
    lat_c = lat[iy, ix]
    lon_c = lon[iy, ix]
    sst_c = sst_k[iy, ix] - 273.15
    ql_c = ql[iy, ix]
    rows = []
    for row in stations.itertuples(index=False):
        dist2 = (lat_c - float(row.latitude)) ** 2 + (lon_c - float(row.longitude)) ** 2
        j = int(np.argmin(dist2))
        dist = float(np.sqrt(dist2[j]))
        if dist > 1.0:
            continue
        rows.append(
            {
                "date": t,
                "location_id": row.location_id,
                "sst": float(sst_c[j]),
                "quality_level": float(ql_c[j]) if np.isfinite(ql_c[j]) else np.nan,
                "grid_lat": float(lat_c[j]),
                "grid_lon": float(lon_c[j]),
                "request_lat": float(row.latitude),
                "request_lon": float(row.longitude),
                "dist_deg": dist,
            }
        )
    return pd.DataFrame(rows)


def to_week(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.dropna(subset=["sst"]).copy()
    iso = d["date"].dt.isocalendar()
    d["iso_year"] = iso.year.astype(int)
    d["iso_week"] = iso.week.astype(int)
    g = (
        d.groupby(["location_id", "iso_year", "iso_week"], as_index=False)
        .agg(
            osi_sst_mean=("sst", "mean"),
            osi_sst_max=("sst", "max"),
            osi_sst_n=("sst", "count"),
            osi_ql_mean=("quality_level", "mean"),
        )
    )
    g = g.sort_values(["location_id", "iso_year", "iso_week"])
    g["osi_sst_lag1w"] = g.groupby("location_id")["osi_sst_mean"].shift(1)
    return g


def mhw_crosscheck(daily: pd.DataFrame) -> dict:
    """Light spring–summer MHW-style flags vs climatology within OSI series."""
    if daily.empty:
        return {"status": "empty"}
    d = daily.copy()
    d["doy"] = d["date"].dt.dayofyear
    # Hobday-lite: 90th percentile doy clim with ±5 day window using available years
    records = []
    for loc, sub in d.groupby("location_id"):
        sub = sub.sort_values("date")
        clim = {}
        for doy in range(1, 367):
            window = sub[sub["doy"].between(doy - 5, doy + 5)]["sst"]
            if len(window) >= 10:
                clim[doy] = float(window.quantile(0.9))
        if not clim:
            continue
        thresh = sub["doy"].map(clim)
        hot = sub["sst"] > thresh
        # consecutive runs >= 5 days
        run = 0
        in_mhw = []
        for h in hot.fillna(False):
            run = run + 1 if h else 0
            in_mhw.append(run >= 5)
        # backfill run membership
        arr = np.array(in_mhw, dtype=bool)
        # expand: once run hits 5, mark previous 4 too
        out = arr.copy()
        i = 0
        n = len(out)
        while i < n:
            if hot.iloc[i]:
                j = i
                while j < n and bool(hot.iloc[j]):
                    j += 1
                if j - i >= 5:
                    out[i:j] = True
                i = j
            else:
                i += 1
        part = sub.assign(osi_in_mhw=out, osi_sst_thresh90=thresh.values)
        records.append(part[["date", "location_id", "sst", "osi_in_mhw", "osi_sst_thresh90"]])
    if not records:
        return {"status": "no_clim"}
    flagged = pd.concat(records, ignore_index=True)
    out_path = PROC / "osi_saf_sst_mhw_daily.parquet"
    flagged.to_parquet(out_path, index=False)
    spring_summer = flagged[flagged["date"].dt.month.between(5, 8)]
    summary = {
        "status": "ok",
        "path": str(out_path.relative_to(ROOT)),
        "n_days": int(len(flagged)),
        "spring_summer_mhw_frac": float(spring_summer["osi_in_mhw"].mean()) if len(spring_summer) else None,
        "june2023_mhw_frac": float(
            flagged.loc[
                (flagged["date"] >= "2023-06-01") & (flagged["date"] <= "2023-06-30"),
                "osi_in_mhw",
            ].mean()
        )
        if ((flagged["date"] >= "2023-06-01") & (flagged["date"] <= "2023-06-30")).any()
        else None,
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--y0", type=int, default=2018)
    ap.add_argument("--y1", type=int, default=2024)
    ap.add_argument("--months", default="5,6,7,8", help="spring–summer months")
    ap.add_argument("--keep-nc", action="store_true")
    ap.add_argument("--max-days", type=int, default=None, help="debug cap")
    args = ap.parse_args()
    months = [int(m) for m in args.months.split(",") if m.strip()]

    EXT.mkdir(parents=True, exist_ok=True)
    raw_dir = EXT / "raw_nc"
    stations = stations_from_joined()
    print(f"OSI SAF stations={len(stations)} years={args.y0}-{args.y1} months={months}", flush=True)

    parts = []
    n_days = 0
    n_ok = 0
    for y in range(args.y0, args.y1 + 1):
        for m in months:
            # days in month
            for day in range(1, 32):
                try:
                    pd.Timestamp(year=y, month=m, day=day)
                except Exception:
                    continue
                names = list_midday_files(y, m, day)
                if not names:
                    continue
                n_days += 1
                if args.max_days is not None and n_ok >= args.max_days:
                    break
                name = names[0]
                dest = raw_dir / f"{y:04d}" / f"{m:02d}" / name
                path = download_file(y, m, day, name, dest)
                if path is None:
                    continue
                try:
                    extr = extract_stations(path, stations)
                    if not extr.empty:
                        parts.append(extr)
                        n_ok += 1
                        if n_ok % 20 == 0:
                            print(f"  extracted days={n_ok} last={path.name} rows={len(extr)}", flush=True)
                except Exception as exc:  # noqa: BLE001
                    print(f"  extract fail {path.name}: {exc}", flush=True)
                finally:
                    if not args.keep_nc and path.exists():
                        path.unlink(missing_ok=True)
            if args.max_days is not None and n_ok >= args.max_days:
                break
        if args.max_days is not None and n_ok >= args.max_days:
            break

    source = {
        "product_id": PRODUCT_ID,
        "ghrsst_id": GHRSST_ID,
        "catalog": CAT_BASE,
        "role": "independent_spring_summer_MHW_crosscheck_not_OISST_OSTIA_duplicate",
        "years": [args.y0, args.y1],
        "months": months,
        "pass": "120000_midday",
        "n_days_seen": n_days,
        "n_days_extracted": n_ok,
    }

    if not parts:
        (EXT / "sources.json").write_text(json.dumps(source, indent=2))
        print("no OSI SAF extracts", flush=True)
        return 1

    daily = pd.concat(parts, ignore_index=True).drop_duplicates(["location_id", "date"])
    daily_path = EXT / "osi_saf_sst_station_daily.parquet"
    daily.to_parquet(daily_path, index=False)
    # small CSV sample (not full) for docs — week is the join artifact
    daily.head(2000).to_csv(EXT / "osi_saf_sst_station_daily_sample.csv", index=False)
    print(
        f"daily {daily_path} n={len(daily)} "
        f"{daily['date'].min().date()}..{daily['date'].max().date()} "
        f"stations={daily['location_id'].nunique()}",
        flush=True,
    )

    week = to_week(daily)
    week_path = PROC / "osi_saf_sst_week.parquet"
    week.to_parquet(week_path, index=False)
    week.to_csv(PROC / "osi_saf_sst_week.csv", index=False)

    mhw = mhw_crosscheck(daily)
    source.update(
        {
            "daily_path": str(daily_path.relative_to(ROOT)),
            "week_path": str(week_path.relative_to(ROOT)),
            "n_daily": int(len(daily)),
            "n_week": int(len(week)),
            "date_min": str(daily["date"].min().date()),
            "date_max": str(daily["date"].max().date()),
            "n_stations": int(daily["location_id"].nunique()),
            "join_keys": ["location_id", "iso_year", "iso_week"],
            "units": "deg_C_subskin",
            "mhw_crosscheck": mhw,
        }
    )
    (EXT / "sources.json").write_text(json.dumps(source, indent=2))
    (PROC / "osi_saf_sst_ingest_summary.json").write_text(json.dumps(source, indent=2))
    print("MHW cross-check:", json.dumps(mhw), flush=True)
    print("wrote OSI SAF sources + week", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
