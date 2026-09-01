"""England & Wales FSA/Cefas phytoplankton official-control labels.

Public CSVs from data.gov.uk / data.food.gov.uk (Open Government Licence).
Schema varies by year: tidy headers through ~2023; 2024+ Excel-export with
a title row then header row. Counts use ND for non-detect.
Coordinates are British National Grid (OSGB36 / EPSG:27700) grid references.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

# Canonical tidy column names after normalisation
CANON = {
    "sample_number": ["samplenumber", "sample number"],
    "production_area": ["productionarea", "production area"],
    "bed_id": ["bedid", "bed id"],
    "local_authority": ["localauthority", "local authority"],
    "grid_reference": ["gridreference", "grid reference", "grid referencenote 1"],
    "sampling_point": ["samplingpoint", "sampling point"],
    "date": ["datesamplecollected", "date sample collected"],
    "alexandrium": ["psp-alexandrium_spp.cellsl-1", "alexandrium spp. cells l-1 (psp)"],
    "dinophysiaceae": ["dsp-dinophysiaceaecellsl-1", "dinophysiaceae cells l-1 (dsp)"],
    "prorocentrum_lima": ["dsp-prorocentrumlimacellsl-1", "prorocentrum lima cells l-1 (dsp)"],
    "pseudo_nitzschia": [
        "asp-pseudo-nitzschia_spp.cellsl-1",
        "pseudo-nitzschia spp. cells l-1 (asp)",
    ],
}

# FSA Dinophysiaceae trigger commonly used in England/Wales monitoring: 100 cells/L
DEFAULT_DINO_THRESHOLD = 100.0
DEFAULT_PN_THRESHOLD = 50000.0

FSA_RESOURCE_URLS = [
    # Recent Azure blob uploads (names can change year-to-year)
    "https://fsaopendata.blob.core.windows.net/opendatacatalog/PhytoplanktonResultsSummary2025.csv",
    "https://fsaopendata.blob.core.windows.net/opendatacatalog/PhytoplanktonMonitoringResults2024(3).csv",
    "https://fsaopendata.blob.core.windows.net/opendatacatalog/fsa-catalogue2/PhytoplanktonResults2023.csv",
    "https://fsaopendata.blob.core.windows.net/opendatacatalog/fsa-catalogue2/PhytoplanktonResults060423.csv",
    "https://fsaopendata.blob.core.windows.net/opendatacatalog/fsa-catalogue2/Phytoplankton%202021.csv",
    # Stable GitHub Pages archive for older years
    "https://fsadata.github.io/shellfish-monitoring/data/phytoplankton-results-january-2020-to-december-2020.csv",
    "https://fsadata.github.io/shellfish-monitoring/data/phytoplankton-results-january-2019-to-december-2019.csv",
    "https://fsadata.github.io/shellfish-monitoring/data/phytoplankton-results-january-2018-to-december-2018.csv",
    "https://fsadata.github.io/shellfish-monitoring/data/phytoplankton-results-january-2017-to-december-2017.csv",
    "https://fsadata.github.io/shellfish-monitoring/data/phytoplankton-results-september-2012-to-december-2016.csv",
]


def _norm_header(s: str) -> str:
    s = str(s).replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s).strip().lower()
    # drop parenthetical notes sometimes glued on
    s = s.replace("note 1", "").strip()
    return s


def _map_columns(cols: Iterable[str]) -> dict[str, str]:
    """Map raw column -> canonical name."""
    inv = {}
    for canon, aliases in CANON.items():
        for a in aliases:
            inv[a] = canon
    out = {}
    for c in cols:
        key = _norm_header(c)
        # also try compacted (no spaces/punct)
        compact = re.sub(r"[^a-z0-9]+", "", key)
        if key in inv:
            out[c] = inv[key]
        else:
            for alias, canon in inv.items():
                if re.sub(r"[^a-z0-9]+", "", alias) == compact:
                    out[c] = canon
                    break
    return out


def _parse_count(val) -> float:
    if pd.isna(val):
        return 0.0
    s = str(val).strip().upper()
    if s in {"", "ND", "N/A", "NA", "-", "NONE", "NIL"}:
        return 0.0
    s = s.replace(",", "")
    # values like "<20" or ">100000"
    m = re.search(r"[-+]?\d*\.?\d+", s)
    if not m:
        return 0.0
    return float(m.group(0))


def osgb_to_lonlat(grid_refs: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Convert OSGB alphanumeric grid refs (e.g. TM00001301) to WGS84 lon/lat."""
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    letters = "ABCDEFGHJKLMNOPQRSTUVWXYZ"  # no I

    lons, lats = [], []
    for raw in grid_refs.fillna("").astype(str):
        gr = re.sub(r"\s+", "", raw).upper()
        if len(gr) < 4 or not gr[:2].isalpha():
            lons.append(np.nan)
            lats.append(np.nan)
            continue
        try:
            e100 = letters.index(gr[0]) % 5
            n100 = 4 - (letters.index(gr[0]) // 5)
            e20 = letters.index(gr[1]) % 5
            n20 = 4 - (letters.index(gr[1]) // 5)
            digits = gr[2:]
            if len(digits) % 2 != 0 or len(digits) == 0:
                raise ValueError("bad digits")
            half = len(digits) // 2
            e_num = digits[:half].ljust(5, "0")
            n_num = digits[half:].ljust(5, "0")
            easting = e100 * 500_000 + e20 * 100_000 + int(e_num)
            northing = n100 * 500_000 + n20 * 100_000 + int(n_num)
            # false origin offset for 100km letters uses SV as origin (0,0)
            # Standard OSGB lettering: first letter is 500km square from SV
            # Recalculate with correct 500km origin:
            # First letter: A=NW ... V around SV; common implementation:
            a1 = letters.index(gr[0])
            a2 = letters.index(gr[1])
            e500 = (a1 % 5) * 500_000
            n500 = (4 - a1 // 5) * 500_000
            e100k = (a2 % 5) * 100_000
            n100k = (4 - a2 // 5) * 100_000
            easting = e500 + e100k + int(e_num)
            northing = n500 + n100k + int(n_num)
            # OSGB false origin is SW of SV; letter index origin assumes A at NW of
            # 5x5 grid covering GB with false northing. Apply known offset so SV=0,0:
            # SV is letter index for first letter S (index 18): e500=3*500k, n500=1*500k
            # Standard formula subtracts 1e6 easting / adds nothing? Use verified offset:
            easting = easting - 1_000_000
            northing = northing - 500_000
            lon, lat = transformer.transform(easting, northing)
            lons.append(float(lon))
            lats.append(float(lat))
        except Exception:
            lons.append(np.nan)
            lats.append(np.nan)
    return pd.Series(lons, index=grid_refs.index), pd.Series(lats, index=grid_refs.index)


def _read_raw_csv(path: Path) -> pd.DataFrame:
    # Try tidy header first
    peek = pd.read_csv(path, nrows=3, encoding="utf-8", on_bad_lines="skip")
    cols0 = [_norm_header(c) for c in peek.columns]
    if any("samplenumber" in c.replace(" ", "") or c == "sample number" for c in cols0) or any(
        "datesamplecollected" in c.replace(" ", "") for c in cols0
    ):
        return pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
    # Excel-export: title row then header
    df = pd.read_csv(path, header=1, encoding="utf-8", on_bad_lines="skip")
    # drop fully empty trailing columns
    df = df.dropna(axis=1, how="all")
    return df


def load_fsa_csv(path: str | Path) -> pd.DataFrame:
    """Load one annual FSA phytoplankton CSV into a tidy frame."""
    path = Path(path)
    raw = _read_raw_csv(path)
    mapping = _map_columns(raw.columns)
    if "date" not in mapping.values() or "dinophysiaceae" not in mapping.values():
        raise ValueError(f"Could not map required columns in {path}: got {list(raw.columns)}")
    df = raw.rename(columns=mapping)
    # keep first occurrence if duplicate mapped names
    df = df.loc[:, ~df.columns.duplicated()]
    keep = [c for c in CANON if c in df.columns]
    out = df[keep].copy()
    # Prefer ISO (YYYY-MM-DD); fall back to day-first UK formats (DD/MM/YYYY).
    d1 = pd.to_datetime(out["date"], format="ISO8601", errors="coerce")
    d2 = pd.to_datetime(out["date"], dayfirst=True, errors="coerce")
    out["date"] = d1.fillna(d2)
    for c in ("alexandrium", "dinophysiaceae", "prorocentrum_lima", "pseudo_nitzschia"):
        if c in out.columns:
            out[c] = out[c].map(_parse_count)
        else:
            out[c] = 0.0
    if "grid_reference" in out.columns:
        lon, lat = osgb_to_lonlat(out["grid_reference"])
        out["longitude"] = lon
        out["latitude"] = lat
    else:
        out["longitude"] = np.nan
        out["latitude"] = np.nan
    out["source_file"] = path.name
    return out.dropna(subset=["date"])


def load_fsa_dir(directory: str | Path) -> pd.DataFrame:
    directory = Path(directory)
    frames = []
    for p in sorted(directory.glob("*.csv")):
        try:
            frames.append(load_fsa_csv(p))
        except Exception as exc:  # noqa: BLE001 — collect per-file errors for caller
            frames.append(pd.DataFrame({"_error": [f"{p.name}: {exc}"]}))
    if not frames:
        return pd.DataFrame()
    # drop error-only frames but keep note
    good = [f for f in frames if "_error" not in f.columns]
    if not good:
        raise RuntimeError("No UK FSA CSVs parsed successfully")
    return pd.concat(good, ignore_index=True)


def uk_station_week_panel(
    df: pd.DataFrame,
    dino_threshold: float = DEFAULT_DINO_THRESHOLD,
    pn_threshold: float = DEFAULT_PN_THRESHOLD,
) -> pd.DataFrame:
    """Aggregate FSA samples to BedID × ISO-week with Dinophysiaceae / Pseudo-nitzschia labels.

    Dinophysiaceae is the England & Wales DSP family group (proxy for Dinophysis).
    """
    x = df.copy()
    x = x.dropna(subset=["date"])
    if "bed_id" not in x.columns:
        x["bed_id"] = x.get("sampling_point", pd.Series(index=x.index)).astype(str)
    x["location_id"] = x["bed_id"].astype(str)
    iso = x["date"].dt.isocalendar()
    x["iso_year"] = iso.year.astype(int)
    x["iso_week"] = iso.week.astype(int)
    x["week_start"] = x["date"] - pd.to_timedelta(x["date"].dt.dayofweek, unit="D")
    x["week_start"] = x["week_start"].dt.normalize()
    keys = ["location_id", "iso_year", "iso_week", "week_start"]
    g = (
        x.groupby(keys, as_index=False)
        .agg(
            latitude=("latitude", "median"),
            longitude=("longitude", "median"),
            location_name=("sampling_point", "first")
            if "sampling_point" in x.columns
            else ("location_id", "first"),
            production_area=("production_area", "first")
            if "production_area" in x.columns
            else ("location_id", "first"),
            n_samples=("dinophysiaceae", "size"),
            count_dinophysis=("dinophysiaceae", "max"),
            count_pseudo_nitzschia=("pseudo_nitzschia", "max"),
        )
    )
    g["y_dinophysis"] = (g["count_dinophysis"] >= dino_threshold).astype(int)
    g["y_pseudo_nitzschia"] = (g["count_pseudo_nitzschia"] >= pn_threshold).astype(int)
    g["country"] = "England_Wales"
    return g.sort_values(keys).reset_index(drop=True)


def download_fsa_csvs(out_dir: str | Path, urls: list[str] | None = None, timeout: int = 60) -> list[Path]:
    """Download listed FSA CSVs into out_dir. Skips failures; returns saved paths."""
    import requests

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for url in urls or FSA_RESOURCE_URLS:
        name = url.rstrip("/").split("/")[-1]
        name = re.sub(r"[^\w.\-()%]+", "_", name)
        dest = out_dir / name
        try:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            dest.write_bytes(r.content)
            saved.append(dest)
        except Exception:
            continue
    return saved
