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


# ---------------------------------------------------------------------------
# ODYSSEA L4 fallback (CMEMS product SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025)
# Anonymous ARCO zarr on CloudFerro — works when auth.marine.copernicus.eu is down.
# ---------------------------------------------------------------------------

ODYSSEA_ARCO_TIMECHUNKED = (
    "https://s3.waw3-1.cloudferro.com/mdl-arco-time-045/arco/"
    "SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025/"
    "IFREMER-ATL-SST-L4-NRT-OBS_FULL_TIME_SERIE_201904/timeChunked.zarr"
)

ODYSSEA_META = {
    "product_id": "SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025",
    "dataset_id": "IFREMER-ATL-SST-L4-NRT-OBS_FULL_TIME_SERIE",
    "variable": "analysed_sst",
    "licence": "Copernicus Marine open data (see product licence / citation)",
    "doi": "10.48670/moi-00152",
    "access": "anonymous ARCO zarr (CloudFerro S3 HTTPS)",
    "arco_uri": ODYSSEA_ARCO_TIMECHUNKED,
    "note": "ODYSSEA L4 ingests OSI SAF among other IR/MW inputs; gap-free daily foundation SST ~0.02°",
}


def open_odyssea_arco(uri: str | None = None):
    """Open ODYSSEA L4 ARCO zarr anonymously (zarr v2 consolidated)."""
    import xarray as xr

    return xr.open_zarr(uri or ODYSSEA_ARCO_TIMECHUNKED, consolidated=True, zarr_format=2)


def download_odyssea_for_stations(
    stations: pd.DataFrame,
    t0: str,
    t1: str,
    *,
    max_stations: int | None = None,
    kelvin_to_celsius: bool = True,
    uri: str | None = None,
) -> pd.DataFrame:
    """Nearest-grid ODYSSEA foundation SST (°C) per location_id (station-day).

    Uses anonymous CloudFerro ARCO — no CMEMS toolbox login required.
    """
    import xarray as xr

    uniq = stations.drop_duplicates("location_id")[["location_id", "latitude", "longitude"]].copy()
    if max_stations is not None:
        uniq = uniq.head(int(max_stations))

    ds = open_odyssea_arco(uri)
    da = ds["analysed_sst"].sel(time=slice(t0, t1))
    # Irish-ish pad so nearest ocean pixels resolve for coastal stations
    lat_min = float(uniq["latitude"].min()) - 0.15
    lat_max = float(uniq["latitude"].max()) + 0.15
    lon_min = float(uniq["longitude"].min()) - 0.15
    lon_max = float(uniq["longitude"].max()) + 0.15
    da = da.sel(latitude=slice(lat_min, lat_max), longitude=slice(lon_min, lon_max))

    # Ocean mask from first day
    mask = da.isel(time=0).load()
    lats = np.asarray(mask.latitude.values, dtype=float)
    lons = np.asarray(mask.longitude.values, dtype=float)
    ocean = np.isfinite(np.asarray(mask.values, dtype=float))
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")

    pix_rows = []
    for row in uniq.itertuples(index=False):
        dist = (lat_grid - float(row.latitude)) ** 2 + (lon_grid - float(row.longitude)) ** 2
        dist = np.where(ocean, dist, np.inf)
        if not np.isfinite(dist).any():
            print(f"ODYSSEA skip {row.location_id}: no ocean pixel", flush=True)
            continue
        i, j = np.unravel_index(int(np.argmin(dist)), dist.shape)
        pix_rows.append(
            {
                "location_id": int(row.location_id),
                "request_lat": float(row.latitude),
                "request_lon": float(row.longitude),
                "grid_lat": float(lats[i]),
                "grid_lon": float(lons[j]),
                "dist_deg": float(np.sqrt(dist[i, j])),
            }
        )
    pixel_map = pd.DataFrame(pix_rows)
    if pixel_map.empty:
        return pd.DataFrame()

    pix = (
        pixel_map[["grid_lat", "grid_lon"]]
        .drop_duplicates()
        .reset_index(drop=True)
        .reset_index(names="pixel_id")
    )
    station_pix = pixel_map.merge(pix, on=["grid_lat", "grid_lon"], how="inner")
    print(
        f"ODYSSEA ARCO: {len(station_pix)} stations → {len(pix)} pixels "
        f"(median dist {pixel_map['dist_deg'].median():.3f}°)",
        flush=True,
    )

    lat_da = xr.DataArray(pix["grid_lat"].to_numpy(dtype=float), dims="pixel")
    lon_da = xr.DataArray(pix["grid_lon"].to_numpy(dtype=float), dims="pixel")
    print(f"ODYSSEA load {t0}..{t1} …", flush=True)
    pts = da.sel(latitude=lat_da, longitude=lon_da, method="nearest").load()
    times = pd.to_datetime(np.asarray(pts.time.values)).tz_localize(None)
    vals = np.asarray(pts.values, dtype=float)  # (time, pixel)
    if kelvin_to_celsius:
        vals = vals - 273.15
    n_t, n_p = vals.shape
    pixel_daily = pd.DataFrame(
        {
            "date": np.repeat(times, n_p),
            "sst": vals.reshape(-1),
            "pixel_id": np.tile(pix["pixel_id"].to_numpy(), n_t),
            "grid_lat": np.tile(pix["grid_lat"].to_numpy(), n_t),
            "grid_lon": np.tile(pix["grid_lon"].to_numpy(), n_t),
        }
    )
    out = pixel_daily.merge(
        station_pix[
            ["location_id", "request_lat", "request_lon", "pixel_id", "grid_lat", "grid_lon"]
        ],
        on=["pixel_id", "grid_lat", "grid_lon"],
        how="inner",
    )
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["source"] = "odyssea_l4_arco"
    out = out.drop_duplicates(["location_id", "date"])
    out = out[
        [
            "date",
            "location_id",
            "sst",
            "request_lat",
            "request_lon",
            "grid_lat",
            "grid_lon",
            "source",
        ]
    ]
    print(
        f"ODYSSEA rows={len(out)} days={out['date'].nunique()} "
        f"stations={out['location_id'].nunique()} "
        f"nan_frac={float(np.isnan(out['sst']).mean()):.3f}",
        flush=True,
    )
    return out.reset_index(drop=True)


def write_odyssea_bbox_netcdf(
    out_path: Path,
    t0: str,
    t1: str,
    *,
    lat_min: float = 51.0,
    lat_max: float = 56.0,
    lon_min: float = -11.0,
    lon_max: float = -5.0,
    uri: str | None = None,
) -> Path:
    """Write Irish-bbox ODYSSEA analysed_sst cube (Kelvin) for pilot days."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ds = open_odyssea_arco(uri)
    sub = ds[["analysed_sst", "analysis_error", "mask"]].sel(
        time=slice(t0, t1),
        latitude=slice(lat_min, lat_max),
        longitude=slice(lon_min, lon_max),
    )
    print(f"ODYSSEA bbox load {t0}..{t1} shape≈{dict(sub['analysed_sst'].sizes)} …", flush=True)
    loaded = sub.load()
    # CF-ish attrs
    loaded.attrs.update(
        {
            "title": "ODYSSEA ATL L4 SST Irish bbox pilot",
            "cmems_product_id": ODYSSEA_META["product_id"],
            "dataset_id": ODYSSEA_META["dataset_id"],
            "source_arco": uri or ODYSSEA_ARCO_TIMECHUNKED,
            "licence_note": ODYSSEA_META["licence"],
            "doi": ODYSSEA_META["doi"],
        }
    )
    loaded.to_netcdf(out_path)
    print(f"wrote {out_path} size={out_path.stat().st_size}", flush=True)
    return out_path
