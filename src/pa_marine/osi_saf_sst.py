"""EUMETSAT OSI SAF SST helpers for independent MHW / shelf SST checks.

Preferred product (Irish shelf / NE Atlantic):
  OSI-202-c  NAR L3C Metop-B/AVHRR  (~2 km, 4× daily, GHRSST)
  GHRSST id: AVHRR_SST_METOP_B_NAR-OSISAF-L3C-v1.0
  Licence: CC BY 4.0 (OSI SAF)
  DOI: 10.15770/EUM_SAF_OSI_NRT_2012

Fallback / coarser independent check:
  OSI-201-b  Global Metop L3C  (0.05°, 2× daily)
  GHRSST id: AVHRR_SST_METOP_B_GLB-OSISAF-L3C-v1.0

Access paths (open-data; no Sextant):
  1) PO.DAAC / Earthdata (CMR) — needs ~/.netrc Earthdata login for protected granules
  2) Ifremer OSI SAF FTP — ftp://ftp.ifremer.fr/ifremer/cersat/projects/osisaf/sst/l3c/...
     (anonymous username per OSI SAF product page; may require registered OSI SAF account
      for full archive — check current access notes)

L3C has cloud gaps → not a drop-in Hobday daily MHW series. Use week-mean clear-sky
SST (quality_level ≥ 3) as an independent check vs OISST/OSTIA week means.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"

DEFAULT_NAR = {
    "osi_id": "OSI-202-c",
    "ghrsst_short_name": "AVHRR_SST_METOP_B_NAR-OSISAF-L3C-v1.0",
    "doi": "10.15770/EUM_SAF_OSI_NRT_2012",
    "licence": "CC BY 4.0",
    "variable": "sea_surface_temperature",
    "quality_min": 3,
    "kelvin_to_celsius": True,
}

DEFAULT_GLB = {
    "osi_id": "OSI-201-b",
    "ghrsst_short_name": "AVHRR_SST_METOP_B_GLB-OSISAF-L3C-v1.0",
    "doi": None,  # confirm on osi-saf.eumetsat.int/products/osi-201-b
    "licence": "CC BY 4.0",
    "variable": "sea_surface_temperature",
    "quality_min": 3,
    "kelvin_to_celsius": True,
}


def _osi_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    osi = dict(cfg.get("osi_saf_sst") or {})
    product = (osi.get("product") or "nar").lower()
    base = dict(DEFAULT_NAR if product == "nar" else DEFAULT_GLB)
    base.update(osi)
    base.setdefault("product", product)
    return base


def cmr_list_granules(
    short_name: str,
    t0: str,
    t1: str,
    bbox: tuple[float, float, float, float] | None = None,
    page_size: int = 50,
    max_pages: int = 40,
) -> list[dict[str, Any]]:
    """List PO.DAAC/CMR granules (metadata only; download may need Earthdata)."""
    # bbox = (lon_min, lat_min, lon_max, lat_max)
    entries: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        params: dict[str, Any] = {
            "short_name": short_name,
            "temporal": f"{t0}T00:00:00Z,{t1}T23:59:59Z",
            "page_size": page_size,
            "page_num": page,
        }
        if bbox is not None:
            params["bounding_box"] = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
        url = f"{CMR_GRANULES}?{urlencode(params)}"
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        batch = payload.get("feed", {}).get("entry", []) or []
        if not batch:
            break
        entries.extend(batch)
        if len(batch) < page_size:
            break
    return entries


def granule_download_urls(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract HTTPS data links from CMR granule entries."""
    rows = []
    for e in entries:
        href = None
        for link in e.get("links") or []:
            rel = link.get("rel") or ""
            h = link.get("href") or ""
            if "fedsearch/1.1/data#" in rel and h.endswith(".nc"):
                href = h
                break
        if not href:
            continue
        rows.append(
            {
                "title": e.get("title") or "",
                "time_start": e.get("time_start") or "",
                "href": href,
            }
        )
    return rows


def write_granule_manifest(
    out_path: Path,
    cfg: dict[str, Any],
    t0: str,
    t1: str,
) -> pd.DataFrame:
    """CMR discover NAR/GLB granules for Irish domain → CSV manifest (no download)."""
    osi = _osi_cfg(cfg)
    domain = cfg.get("domain", {})
    bbox = (
        float(domain.get("lon_min", -11.0)),
        float(domain.get("lat_min", 51.0)),
        float(domain.get("lon_max", -5.0)),
        float(domain.get("lat_max", 56.0)),
    )
    entries = cmr_list_granules(osi["ghrsst_short_name"], t0, t1, bbox=bbox)
    urls = granule_download_urls(entries)
    df = pd.DataFrame(urls)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "osi_id": osi["osi_id"],
        "ghrsst_short_name": osi["ghrsst_short_name"],
        "doi": osi.get("doi"),
        "licence": osi.get("licence"),
        "t0": t0,
        "t1": t1,
        "bbox": bbox,
        "n_granules": int(len(df)),
    }
    df.to_csv(out_path, index=False)
    meta_path = out_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"wrote {out_path} n={len(df)} meta={meta_path}", flush=True)
    return df


def week_mean_from_daily_clearsky(
    daily: pd.DataFrame,
    sst_col: str = "osi_sst",
    min_clear: int = 2,
) -> pd.DataFrame:
    """Aggregate clear-sky daily OSI SST to ISO week means per location_id."""
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    iso = d["date"].dt.isocalendar()
    d["iso_year"] = iso.year.astype(int)
    d["iso_week"] = iso.week.astype(int)
    g = (
        d.groupby(["location_id", "iso_year", "iso_week"], as_index=False)
        .agg(
            osi_sst_week=(sst_col, "mean"),
            osi_sst_n_clear=(sst_col, "count"),
            osi_sst_week_min=(sst_col, "min"),
            osi_sst_week_max=(sst_col, "max"),
        )
    )
    g.loc[g["osi_sst_n_clear"] < min_clear, "osi_sst_week"] = np.nan
    return g


def extract_station_pixels_from_nc(
    nc_path: Path,
    stations: pd.DataFrame,
    variable: str = "sea_surface_temperature",
    quality_min: int = 3,
    kelvin_to_celsius: bool = True,
) -> pd.DataFrame:
    """Nearest-pixel extract from one GHRSST L3C netCDF (quality-filtered)."""
    import xarray as xr

    ds = xr.open_dataset(nc_path)
    if variable not in ds:
        # some files use 'analysed_sst'
        for alt in ("analysed_sst", "sst", "sea_surface_temperature"):
            if alt in ds:
                variable = alt
                break
    da = ds[variable]
    q = ds["quality_level"] if "quality_level" in ds else None

    # Handle lon/lat naming
    lat_name = "lat" if "lat" in da.coords or "lat" in da.dims else "latitude"
    lon_name = "lon" if "lon" in da.coords or "lon" in da.dims else "longitude"

    times = pd.to_datetime(np.asarray(ds["time"].values)).tz_localize(None)
    rows = []
    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]]
    for row in uniq.itertuples(index=False):
        try:
            pt = da.sel({lat_name: float(row.latitude), lon_name: float(row.longitude)}, method="nearest")
            if q is not None:
                qpt = q.sel(
                    {lat_name: float(row.latitude), lon_name: float(row.longitude)},
                    method="nearest",
                )
            else:
                qpt = None
        except Exception:
            continue
        vals = np.asarray(pt.values, dtype=float).reshape(-1)
        qvals = (
            np.asarray(qpt.values, dtype=float).reshape(-1)
            if qpt is not None
            else np.full(len(vals), quality_min)
        )
        for t, v, qv in zip(times, vals, qvals, strict=False):
            if not np.isfinite(v) or qv < quality_min:
                continue
            sst = float(v) - 273.15 if kelvin_to_celsius and float(v) > 200 else float(v)
            rows.append(
                {
                    "location_id": row.location_id,
                    "date": pd.Timestamp(t).normalize(),
                    "osi_sst": sst,
                    "quality_level": float(qv),
                    "source_file": nc_path.name,
                }
            )
    ds.close()
    return pd.DataFrame(rows)


def ftp_hint(product: str = "nar") -> str:
    if product.lower() == "glb":
        return (
            "ftp://ftp.ifremer.fr/ifremer/cersat/projects/osisaf/sst/l3c/global/"
            " (OSI-201-b Metop-B)"
        )
    return (
        "ftp://ftp.ifremer.fr/ifremer/cersat/projects/osisaf/sst/l3c/north_atlantic/"
        " (OSI-202-c NAR Metop-B / NOAA-20)"
    )
