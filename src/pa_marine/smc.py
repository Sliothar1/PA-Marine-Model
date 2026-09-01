"""Scotland SMC sanitary classifications + HAB phytoplankton / biotoxin labels.

Sanitary classifications (A/B/C by SIN) are NOT HAB labels.
Phytoplankton and biotoxin CSVs from Food Standards Scotland / SMC monitoring
provide Dinophysis / Pseudo-nitzschia / Alexandrium cell counts and shellfish
toxin results keyed by Sin (no lat/lon in the export).

Area-closure CSVs are toxin-/E.coli-driven harvest closures (OA/DTX/PTX etc.),
not Copernicus SST. Link to AreaName / Pod / Sin via smc_areas where possible.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_COLS = [
    "AreaName",
    "SpeciesCommonName",
    "LocalAuthorityName",
    "OverallCategory",
    "OverallStartDate",
    "OverallEndDate",
    "Decision",
    "ConfidenceLevel",
    "Type",
    "Status",
    "Sin",
]

DATE_COLS = ["OverallStartDate", "OverallEndDate"]

# Official-control style triggers used for England/Wales/Scotland shellfish monitoring
DEFAULT_DINO_THRESHOLD = 100.0
DEFAULT_PN_THRESHOLD = 50_000.0
DEFAULT_ALEX_THRESHOLD = 40.0  # common UK Alexandrium trigger (cells L⁻¹)

# UK/Scotland shellfish flesh regulatory limits (approx.)
DEFAULT_DSP_THRESHOLD = 160.0  # µg OA eq/kg (OA+DTX+PTX)
DEFAULT_ASP_THRESHOLD = 20.0  # mg/kg
DEFAULT_PSP_THRESHOLD = 800.0  # µg STX eq/kg
DEFAULT_AZA_THRESHOLD = 160.0  # µg/kg
DEFAULT_YTX_THRESHOLD = 3.75  # mg/kg

PHYTO_COUNT_COLS = [
    "DinophysisResultValue",
    "PseudoNitzschiaResultValue",
    "AlexandriumResultValue",
    "ProrocentrumLimaResultValue",
    "ProrocentrumCordatumResultValue",
]


def load_smc_classifications(path: str | Path) -> pd.DataFrame:
    """Load annual sanitary classification CSV; parse date columns day-first."""
    path = Path(path)
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"SMC classifications missing columns: {missing}")
    out = df[REQUIRED_COLS].copy()
    for c in DATE_COLS:
        out[c] = pd.to_datetime(out[c], dayfirst=True, errors="coerce")
    return out


def unique_areas(df: pd.DataFrame) -> pd.DataFrame:
    """Unique (AreaName, Sin, LocalAuthorityName) lookup, sorted."""
    cols = ["AreaName", "Sin", "LocalAuthorityName"]
    return (
        df[cols]
        .drop_duplicates()
        .sort_values(["LocalAuthorityName", "AreaName", "Sin"])
        .reset_index(drop=True)
    )


def write_area_lookup(
    classifications_path: str | Path,
    out_path: str | Path,
) -> pd.DataFrame:
    """Load classifications and write data/processed/smc_areas.csv."""
    areas = unique_areas(load_smc_classifications(classifications_path))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    areas.to_csv(out_path, index=False)
    return areas


def _parse_count(val) -> float:
    """Parse SMC phytoplankton cell-count cells; Rejected/Unsuitable → NaN."""
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    if not s:
        return np.nan
    su = s.upper()
    if su in {
        "REJECTED",
        "UNSUITABLE",
        "ND",
        "N/A",
        "NA",
        "-",
        "NONE",
        "NIL",
        "NS",
    }:
        # ND-style non-detects → 0; Rejected/Unsuitable stay NaN via REJECTED/UNSUITABLE
        if su in {"ND", "N/A", "NA", "-", "NONE", "NIL", "NS"}:
            return 0.0
        return np.nan
    s = s.replace(",", "")
    m = re.search(r"[-+]?\d*\.?\d+", s)
    if not m:
        return np.nan
    return float(m.group(0))


def _parse_toxin_value(val) -> float:
    """Parse SMC toxin Value / ValueAndFlag (<RL, <LOQ, -, numeric)."""
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    if not s or s in {"-", "—"}:
        return np.nan
    su = s.upper().replace(" ", "")
    if su in {"<RL", "<LOQ", "<LOD", "ND", "NA", "N/A", "NONE"}:
        return 0.0
    if "LESSTHAN" in su.replace(" ", "") or su.startswith("<"):
        # treat below-limit as 0 for exceedance labelling
        return 0.0
    s = s.replace(",", "")
    m = re.search(r"[-+]?\d*\.?\d+", s)
    if not m:
        return np.nan
    return float(m.group(0))


def load_smc_phytoplankton(path: str | Path) -> pd.DataFrame:
    """Load SMC phytoplankton CSV; dates day-first; counts coerced to float."""
    path = Path(path)
    df = pd.read_csv(path, low_memory=False)
    need = ["CollectedTimestamp", "Sin", "DinophysisResultValue"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"SMC phytoplankton missing columns: {missing}")
    out = df.copy()
    out["date"] = pd.to_datetime(out["CollectedTimestamp"], dayfirst=True, errors="coerce")
    for c in PHYTO_COUNT_COLS:
        if c in out.columns:
            out[c] = out[c].map(_parse_count)
    out["location_id"] = out["Sin"].astype(str)
    out["country"] = "Scotland"
    return out.dropna(subset=["date", "Sin"])


def smc_phyto_station_week_panel(
    df: pd.DataFrame,
    areas: pd.DataFrame | None = None,
    dino_threshold: float = DEFAULT_DINO_THRESHOLD,
    pn_threshold: float = DEFAULT_PN_THRESHOLD,
    alex_threshold: float = DEFAULT_ALEX_THRESHOLD,
) -> pd.DataFrame:
    """SIN × ISO-week panel with Dinophysis / Pseudo-nitzschia / Alexandrium labels.

    No lat/lon — geocode Sin → coords before any SST / MHW join.
    Optionally left-join sanitary area lookup on Sin.
    """
    x = df.copy()
    x = x.dropna(subset=["date", "Sin"])
    x["location_id"] = x["Sin"].astype(str)
    iso = x["date"].dt.isocalendar()
    x["iso_year"] = iso.year.astype(int)
    x["iso_week"] = iso.week.astype(int)
    x["week_start"] = (x["date"] - pd.to_timedelta(x["date"].dt.dayofweek, unit="D")).dt.normalize()

    keys = ["location_id", "iso_year", "iso_week", "week_start"]
    agg: dict[str, Any] = {
        "Sin": ("Sin", "first"),
        "AreaName": ("AreaName", "first") if "AreaName" in x.columns else ("Sin", "first"),
        "SiteName": ("SiteName", "first") if "SiteName" in x.columns else ("Sin", "first"),
        "LocalAuthorityName": ("LocalAuthorityName", "first")
        if "LocalAuthorityName" in x.columns
        else ("Sin", "first"),
        "n_samples": ("DinophysisResultValue", "size"),
        "count_dinophysis": ("DinophysisResultValue", "max"),
    }
    if "PseudoNitzschiaResultValue" in x.columns:
        agg["count_pseudo_nitzschia"] = ("PseudoNitzschiaResultValue", "max")
    if "AlexandriumResultValue" in x.columns:
        agg["count_alexandrium"] = ("AlexandriumResultValue", "max")

    g = x.groupby(keys, as_index=False).agg(**{k: v for k, v in agg.items()})
    g["count_dinophysis"] = g["count_dinophysis"].fillna(0.0)
    if "count_pseudo_nitzschia" not in g.columns:
        g["count_pseudo_nitzschia"] = 0.0
    else:
        g["count_pseudo_nitzschia"] = g["count_pseudo_nitzschia"].fillna(0.0)
    if "count_alexandrium" not in g.columns:
        g["count_alexandrium"] = 0.0
    else:
        g["count_alexandrium"] = g["count_alexandrium"].fillna(0.0)

    g["y_dinophysis"] = (g["count_dinophysis"] >= dino_threshold).astype(int)
    g["y_pseudo_nitzschia"] = (g["count_pseudo_nitzschia"] >= pn_threshold).astype(int)
    g["y_alexandrium"] = (g["count_alexandrium"] >= alex_threshold).astype(int)
    g["latitude"] = np.nan
    g["longitude"] = np.nan
    g["country"] = "Scotland"
    g["has_coords"] = False

    if areas is not None and len(areas):
        a = areas.copy()
        a["Sin"] = a["Sin"].astype(str)
        # Prefer phyto AreaName/LocalAuthority; fill from lookup when missing
        g = g.merge(
            a.rename(
                columns={
                    "AreaName": "AreaName_lookup",
                    "LocalAuthorityName": "LocalAuthorityName_lookup",
                }
            ),
            on="Sin",
            how="left",
        )
        g["in_smc_areas"] = g["AreaName_lookup"].notna()
        g["AreaName"] = g["AreaName"].fillna(g["AreaName_lookup"])
        g["LocalAuthorityName"] = g["LocalAuthorityName"].fillna(g["LocalAuthorityName_lookup"])
        g = g.drop(columns=[c for c in ("AreaName_lookup", "LocalAuthorityName_lookup") if c in g.columns])
    else:
        g["in_smc_areas"] = False

    return g.sort_values(keys).reset_index(drop=True)


def load_smc_biotoxins(path: str | Path) -> pd.DataFrame:
    """Load SMC biotoxin CSV; parse key toxin value/flag columns."""
    path = Path(path)
    df = pd.read_csv(path, low_memory=False)
    if "CollectedTimestamp" not in df.columns or "Sin" not in df.columns:
        raise ValueError("SMC biotoxins missing CollectedTimestamp or Sin")
    out = df.copy()
    out["date"] = pd.to_datetime(out["CollectedTimestamp"], dayfirst=True, errors="coerce")

    # Prefer numeric ActualResultValue; fall back to ValueAndFlag strings
    pairs = [
        ("dsp", "TotalOaDtxPtxActualResultValue", "TotalOaDtxPtxActualResultValueAndFlag"),
        ("asp", "AspResultValue", "AspResultValueAndFlag"),
        ("psp", "PspHplcQuantActualResultValue", "PspHplcQuantActualResultValueAndFlag"),
        ("aza", "TotalAzaActualResultValue", "TotalAzaActualResultValueAndFlag"),
        ("ytx", "TotalYtxActualResultValue", "TotalYtxActualResultValueAndFlag"),
    ]
    for name, val_col, flag_col in pairs:
        vals = out[val_col].map(_parse_toxin_value) if val_col in out.columns else pd.Series(np.nan, index=out.index)
        flags = (
            out[flag_col].map(_parse_toxin_value) if flag_col in out.columns else pd.Series(np.nan, index=out.index)
        )
        out[f"{name}_value"] = vals.fillna(flags)
    # PSP MBA fallback when HPLC actual missing
    if "PspMbaResultValue" in out.columns:
        mba = out["PspMbaResultValue"].map(_parse_toxin_value)
        out["psp_value"] = out["psp_value"].fillna(mba)

    out["location_id"] = out["Sin"].astype(str)
    out["country"] = "Scotland"
    return out.dropna(subset=["date", "Sin"])


def smc_toxin_station_week_panel(
    df: pd.DataFrame,
    areas: pd.DataFrame | None = None,
    dsp_threshold: float = DEFAULT_DSP_THRESHOLD,
    asp_threshold: float = DEFAULT_ASP_THRESHOLD,
    psp_threshold: float = DEFAULT_PSP_THRESHOLD,
    aza_threshold: float = DEFAULT_AZA_THRESHOLD,
    ytx_threshold: float = DEFAULT_YTX_THRESHOLD,
) -> pd.DataFrame:
    """SIN × ISO-week toxin panel with regulatory exceedance flags (no lat/lon)."""
    x = df.copy()
    x = x.dropna(subset=["date", "Sin"])
    x["location_id"] = x["Sin"].astype(str)
    iso = x["date"].dt.isocalendar()
    x["iso_year"] = iso.year.astype(int)
    x["iso_week"] = iso.week.astype(int)
    x["week_start"] = (x["date"] - pd.to_timedelta(x["date"].dt.dayofweek, unit="D")).dt.normalize()
    keys = ["location_id", "iso_year", "iso_week", "week_start"]

    g = x.groupby(keys, as_index=False).agg(
        Sin=("Sin", "first"),
        AreaName=("AreaName", "first") if "AreaName" in x.columns else ("Sin", "first"),
        SiteName=("SiteName", "first") if "SiteName" in x.columns else ("Sin", "first"),
        LocalAuthorityName=("LocalAuthorityName", "first")
        if "LocalAuthorityName" in x.columns
        else ("Sin", "first"),
        n_samples=("dsp_value", "size"),
        max_dsp=("dsp_value", "max"),
        max_asp=("asp_value", "max"),
        max_psp=("psp_value", "max"),
        max_aza=("aza_value", "max"),
        max_ytx=("ytx_value", "max"),
    )
    for c in ("max_dsp", "max_asp", "max_psp", "max_aza", "max_ytx"):
        g[c] = g[c].fillna(0.0)
    g["y_dsp"] = (g["max_dsp"] >= dsp_threshold).astype(int)
    g["y_asp"] = (g["max_asp"] >= asp_threshold).astype(int)
    g["y_psp"] = (g["max_psp"] >= psp_threshold).astype(int)
    g["y_aza"] = (g["max_aza"] >= aza_threshold).astype(int)
    g["y_ytx"] = (g["max_ytx"] >= ytx_threshold).astype(int)
    g["latitude"] = np.nan
    g["longitude"] = np.nan
    g["country"] = "Scotland"
    g["has_coords"] = False

    if areas is not None and len(areas):
        a = areas.copy()
        a["Sin"] = a["Sin"].astype(str)
        g = g.merge(
            a.rename(
                columns={
                    "AreaName": "AreaName_lookup",
                    "LocalAuthorityName": "LocalAuthorityName_lookup",
                }
            ),
            on="Sin",
            how="left",
        )
        g["in_smc_areas"] = g["AreaName_lookup"].notna()
        g["AreaName"] = g["AreaName"].fillna(g["AreaName_lookup"])
        g["LocalAuthorityName"] = g["LocalAuthorityName"].fillna(g["LocalAuthorityName_lookup"])
        g = g.drop(columns=[c for c in ("AreaName_lookup", "LocalAuthorityName_lookup") if c in g.columns])
    else:
        g["in_smc_areas"] = False

    return g.sort_values(keys).reset_index(drop=True)


def summarize_phyto_panel(panel: pd.DataFrame, n_raw: int) -> dict[str, Any]:
    """Quick summary metrics for the Scotland phyto station-week panel."""
    return {
        "n_raw_rows": int(n_raw),
        "n_station_weeks": int(len(panel)),
        "n_sites_sin": int(panel["location_id"].nunique()),
        "n_area_names": int(panel["AreaName"].nunique()) if "AreaName" in panel.columns else None,
        "date_min": str(panel["week_start"].min().date()) if len(panel) else None,
        "date_max": str(panel["week_start"].max().date()) if len(panel) else None,
        "prevalence_dinophysis_ge100": float(panel["y_dinophysis"].mean()) if len(panel) else None,
        "prevalence_pseudo_nitzschia_ge50000": float(panel["y_pseudo_nitzschia"].mean())
        if len(panel)
        else None,
        "prevalence_alexandrium_ge40": float(panel["y_alexandrium"].mean()) if len(panel) else None,
        "frac_sin_in_smc_areas": float(panel["in_smc_areas"].mean())
        if "in_smc_areas" in panel.columns and len(panel)
        else None,
        "has_lat_lon": False,
        "note": (
            "First Scotland HAB panel has no lat/lon. Geocode Sin→coords before SST/MHW join. "
            "Thresholds: Dinophysis≥100, Pseudo-nitzschia≥50000, Alexandrium≥40 cells/L."
        ),
    }



CLOSURE_REQUIRED_COLS = [
    "Id",
    "AreaId",
    "AreaClosureStart",
    "AreaClosureEnd",
    "AreaName",
    "Description",
    "Reason",
    "Pod",
]

_SIN_IN_REASON = re.compile(r"\b([A-Z]{2})\s+(\d+)\s+(\d+)\s+(\d+)\b")


def _sin_from_reason(reason) -> str | None:
    """Parse 'HL 179 996 08' style site codes from closure Reason text."""
    if pd.isna(reason):
        return None
    m = _SIN_IN_REASON.search(str(reason))
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}"


def _toxin_tags(reason) -> str:
    """Coarse tag(s) from Reason: OA/DTX/PTX, ASP, PSP, AZA, YTX, Ecoli, other."""
    if pd.isna(reason) or not str(reason).strip():
        return "unspecified"
    s = str(reason)
    tags: list[str] = []
    su = s.upper()
    if "OA/DTX/PTX" in su or "OA/DTX" in su:
        tags.append("OA/DTX/PTX")
    if re.search(r"\bASP\b", su):
        tags.append("ASP")
    if re.search(r"\bPSP\b", su):
        tags.append("PSP")
    if re.search(r"\bAZA\b", su):
        tags.append("AZA")
    if re.search(r"\bYTX\b", su):
        tags.append("YTX")
    if re.search(r"\bE\s*COLI\b|\bECOLI\b", su, re.I):
        tags.append("Ecoli")
    return "|".join(tags) if tags else "other"


def load_smc_area_closures(path: str | Path) -> pd.DataFrame:
    """Load SMC area-closure CSV; parse start/end day-first; keep Pod as nullable Int64."""
    path = Path(path)
    df = pd.read_csv(path)
    missing = [c for c in CLOSURE_REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"SMC area closures missing columns: {missing}")
    out = df[CLOSURE_REQUIRED_COLS].copy()
    out["AreaClosureStart"] = pd.to_datetime(
        out["AreaClosureStart"], dayfirst=True, errors="coerce"
    )
    out["AreaClosureEnd"] = pd.to_datetime(
        out["AreaClosureEnd"], dayfirst=True, errors="coerce"
    )
    out["Pod"] = pd.to_numeric(out["Pod"], errors="coerce").astype("Int64")
    return out


def process_smc_area_closures(
    closures: pd.DataFrame,
    areas: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """One row per closure Id, linked to smc_areas on AreaName (+ Sin from Reason).

    Adds:
      Sin_trigger — site code parsed from Reason (may differ from sanitary Sin)
      Sin — preferred link: Sin_trigger if present in areas, else first AreaName Sin
      AreaSins — pipe-joined SINs for AreaName in smc_areas
      LocalAuthorityName, in_smc_areas, n_area_sins
      toxin_tags, is_open (no AreaClosureEnd)
    """
    g = closures.copy()
    g["Sin_trigger"] = g["Reason"].map(_sin_from_reason)
    g["toxin_tags"] = g["Reason"].map(_toxin_tags)
    g["is_open"] = g["AreaClosureEnd"].isna()

    if areas is None or areas.empty:
        g["Sin"] = g["Sin_trigger"]
        g["AreaSins"] = pd.NA
        g["LocalAuthorityName"] = pd.NA
        g["in_smc_areas"] = False
        g["n_area_sins"] = 0
        g["sin_trigger_in_smc_areas"] = False
        return g

    area_sins = set(areas["Sin"].dropna().astype(str))
    by_name = (
        areas.groupby("AreaName", as_index=False)
        .agg(
            AreaSins=("Sin", lambda s: "|".join(sorted(set(map(str, s))))),
            LocalAuthorityName=("LocalAuthorityName", "first"),
            Sin_area_primary=("Sin", "first"),
            n_area_sins=("Sin", "nunique"),
        )
    )
    g = g.merge(by_name, on="AreaName", how="left")
    g["in_smc_areas"] = g["AreaSins"].notna()
    g["n_area_sins"] = g["n_area_sins"].fillna(0).astype(int)
    g["sin_trigger_in_smc_areas"] = g["Sin_trigger"].isin(area_sins)

    def _pick_sin(row):
        trig = row.get("Sin_trigger")
        if pd.notna(trig) and str(trig) in area_sins:
            return str(trig)
        primary = row.get("Sin_area_primary")
        if pd.notna(primary):
            return str(primary)
        return trig if pd.notna(trig) else pd.NA

    g["Sin"] = g.apply(_pick_sin, axis=1)
    g = g.drop(columns=["Sin_area_primary"])
    return g.reset_index(drop=True)

