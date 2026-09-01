"""Geocode Scotland SMC shellfish sites (Sin) to WGS84 for SST joins.

Priority:
  1. OSGB grid refs in SMC area-closure Descriptions → polygon centroid (high)
  2. SEPA Shellfish Water Protected Areas centroids by name (medium–high)
  3. Nominatim geocode of AreaName / SiteName, Scotland, UK (medium/low)

FSS classified-areas WFS (nmp:fss_shellfish_classified_areas on Marine Scotland
GeoServer) exists under OGL but currently returns HTTP 401 without login — not used.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from pa_marine.uk_fsa import osgb_to_lonlat

# OSGB: letters + digit pairs with optional spaces / concatenated forms
_OSGB_TOKEN = re.compile(
    r"\b([HJNST][A-HJ-Z])\s*(\d{2,5})\s+(\d{2,5})\b"
    r"|\b([HJNST][A-HJ-Z])(\d{6,10})\b",
    re.IGNORECASE,
)

_SPECIES_NOISE = re.compile(
    r"\b(mussels?|oysters?|cockles?|scallops?|clams?|razors?|"
    r"pacific|native|common|king|queen|gigas)\b",
    re.I,
)


def normalize_place_name(name: object) -> str:
    """Lowercase, strip species suffixes, collapse punctuation for matching."""
    if pd.isna(name):
        return ""
    s = str(name).lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"[:/,()\-]+", " ", s)
    s = _SPECIES_NOISE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_osgb_refs(text: object) -> list[str]:
    """Extract OSGB alphanumeric grid refs from closure Description text."""
    if pd.isna(text):
        return []
    s = str(text)
    out: list[str] = []
    for m in _OSGB_TOKEN.finditer(s):
        if m.group(1):
            letters, e, n = m.group(1).upper(), m.group(2), m.group(3)
            # pad unequal halves to equal length (rare) then compact
            out.append(f"{letters}{e}{n}")
        else:
            out.append(f"{m.group(4).upper()}{m.group(5)}")
    # also catch no-space forms adjacent to letters after stripping spaces in tokens
    compact = re.sub(r"\s+", "", s.upper())
    for m in re.finditer(r"([HJNST][A-HJ-Z])(\d{6,10})", compact):
        tok = m.group(0)
        if tok not in out:
            out.append(tok)
    # de-dupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for r in out:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq


def osgb_refs_centroid(refs: list[str]) -> tuple[float, float] | tuple[float, float]:
    """Mean WGS84 lon/lat of OSGB refs; (nan, nan) if none convert."""
    if not refs:
        return (float("nan"), float("nan"))
    lon, lat = osgb_to_lonlat(pd.Series(refs))
    ok = lon.notna() & lat.notna()
    if not ok.any():
        return (float("nan"), float("nan"))
    return (float(lon[ok].mean()), float(lat[ok].mean()))


def centroids_from_closures(closures: pd.DataFrame) -> pd.DataFrame:
    """Per-AreaName centroid from OSGB points in Description; source=osgb_closure."""
    rows = []
    for area, g in closures.groupby("AreaName", dropna=False):
        refs: list[str] = []
        for desc in g["Description"].tolist():
            refs.extend(extract_osgb_refs(desc))
        # unique refs
        refs = list(dict.fromkeys(refs))
        lon, lat = osgb_refs_centroid(refs)
        if np.isnan(lat) or np.isnan(lon):
            continue
        # prefer Sin column if present
        sin = None
        if "Sin" in g.columns and g["Sin"].notna().any():
            sin = str(g["Sin"].dropna().iloc[0])
        rows.append(
            {
                "AreaName": area,
                "Sin": sin,
                "latitude": lat,
                "longitude": lon,
                "source": "osgb_closure",
                "confidence": "high",
                "n_osgb_points": len(refs),
            }
        )
    return pd.DataFrame(rows)


def load_sepa_swpa_centroids(path: str | Path) -> pd.DataFrame:
    """Load SEPA SWPA ArcGIS JSON (or a thin CSV with site,lat,lon)."""
    path = Path(path)
    if not path.is_file():
        return pd.DataFrame(columns=["site", "latitude", "longitude", "pa_id", "name_norm"])
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        rename = {}
        for c in df.columns:
            cl = c.lower()
            if cl in {"site", "name", "swpa_name"}:
                rename[c] = "site"
            elif cl in {"lat", "latitude"}:
                rename[c] = "latitude"
            elif cl in {"lon", "longitude", "long"}:
                rename[c] = "longitude"
            elif cl == "pa_id":
                rename[c] = "pa_id"
        df = df.rename(columns=rename)
    else:
        data = json.loads(path.read_text())
        feats = data.get("features", data if isinstance(data, list) else [])
        rows = []
        for f in feats:
            a = f.get("attributes", f)
            rows.append(
                {
                    "site": a.get("site") or a.get("SITE"),
                    "latitude": a.get("lat") or a.get("LAT"),
                    "longitude": a.get("lon") or a.get("LON"),
                    "easting": a.get("easting") or a.get("EASTING"),
                    "northing": a.get("northing") or a.get("NORTHING"),
                    "pa_id": a.get("pa_id") or a.get("PA_ID"),
                }
            )
        df = pd.DataFrame(rows)
    df = df.dropna(subset=["site"]).copy()
    # SEPA REST sometimes duplicates lat into lon; prefer OSGB easting/northing when suspect
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)

    def _fix_lonlat(row):
        lat = row.get("latitude")
        lon = row.get("longitude")
        e, n = row.get("easting"), row.get("northing")
        suspect = (
            pd.isna(lat)
            or pd.isna(lon)
            or (abs(float(lat) - float(lon)) < 1e-6)
            or float(lon) > 0.5  # Scotland is west of Greenwich
            or not (54.0 <= float(lat) <= 61.5)
        )
        if suspect and pd.notna(e) and pd.notna(n):
            lon2, lat2 = transformer.transform(float(e), float(n))
            return lat2, lon2
        return lat, lon

    fixed = df.apply(_fix_lonlat, axis=1, result_type="expand")
    df["latitude"] = fixed[0]
    df["longitude"] = fixed[1]
    df = df.dropna(subset=["latitude", "longitude"]).copy()
    df["name_norm"] = df["site"].map(normalize_place_name)
    return df.reset_index(drop=True)


# Hand aliases: SMC AreaName → SEPA SWPA site (when names diverge but refer to same water)
SEPA_ALIASES: dict[str, str] = {
    "inner loch torridon": "upper loch torridon",
    "cromarty firth": "cromarty bay",
    "basta voe cove": "basta voe yell",
    "basta voe outer": "basta voe yell",
    "ronas voe east": "ronas voe area",
}

# AreaName → preferred Nominatim query (reproducible fallbacks for stubborn names)
NOMINATIM_AREA_SEEDS: dict[str, str] = {
    "Aith Voe Sletta": "Aith, Shetland",
    "Bay of Backaskaill": "Backaskaill Bay, Orkney",
    "Busta Voe Lee North": "Busta Voe, Shetland",
    "Dales Voe: Scarvar Ayre": "Dales Voe, Shetland",
    "Gallochoille Old Pier": "Gallochoille, Argyll, Scotland",
    "Kirkcudbright Bay Razors": "Kirkcudbright Bay, Scotland",
    "Mainland: Tingwall Pier": "Tingwall, Orkney",
    "North Bay Oysters - Hoy": "Hoy, Orkney",
    "Olna Firth Outer": "Olna Firth, Shetland",
    "South of Houss Holm": "Houss, Burra, Shetland",
    "Vementry South": "Vementry, Shetland",
    "Wigtown Bay: Islands of Fleet": "Islands of Fleet, Scotland",
    "Loch Na Keal West": "Loch na Keal",
    "Loch Riddon Cockles": "Loch Riddon, Argyll, Scotland",
    "Ganavan Cockles": "Ganavan, Oban, Scotland",
    "Luce Bay Razors": "Luce Bay, Dumfries, Scotland",
    "Firth of Forth: North": "Anstruther, Fife, Scotland",
    "Forth Estuary: Largo Bay": "Largo Bay, Fife, Scotland",
}



def _token_set(s: str) -> set[str]:
    stop = {"loch", "bay", "voe", "firth", "sound", "of", "the", "and", "inner", "outer", "east", "west", "north", "south", "upper", "lower", "area"}
    return {t for t in s.split() if t and t not in stop and len(t) > 2}


def match_sepa(
    sites: pd.DataFrame,
    sepa: pd.DataFrame,
) -> pd.DataFrame:
    """Match sites to SEPA SWPA by normalized AreaName then SiteName."""
    if sepa.empty or sites.empty:
        return sites.copy()
    by_norm = (
        sepa.drop_duplicates("name_norm")
        .set_index("name_norm")[["latitude", "longitude", "site", "pa_id"]]
    )
    out = sites.copy()
    out["sepa_lat"] = np.nan
    out["sepa_lon"] = np.nan
    out["sepa_site"] = pd.NA
    out["sepa_match"] = pd.NA

    area_n = out["AreaName"].map(normalize_place_name)
    site_n = (
        out["SiteName"].map(normalize_place_name)
        if "SiteName" in out.columns
        else pd.Series("", index=out.index)
    )

    for i, (an, sn) in enumerate(zip(area_n, site_n)):
        hit = None
        kind = None
        alias_key = SEPA_ALIASES.get(an)
        if alias_key and alias_key in by_norm.index:
            hit = by_norm.loc[alias_key]
            kind = "alias"
        elif an and an in by_norm.index:
            hit = by_norm.loc[an]
            kind = "area_exact"
        elif sn and sn in by_norm.index:
            hit = by_norm.loc[sn]
            kind = "site_exact"
        else:
            candidates = []
            for key in (an, sn):
                if not key or len(key) < 5:
                    continue
                for nn in by_norm.index:
                    if key in nn or nn in key:
                        candidates.append(nn)
            # token overlap unique match
            if not candidates and an:
                toks = _token_set(an)
                if toks:
                    scored = []
                    for nn in by_norm.index:
                        ot = _token_set(nn)
                        if not ot:
                            continue
                        inter = toks & ot
                        if inter and (len(inter) >= 1 and (inter == toks or inter == ot or len(inter) >= 2)):
                            scored.append(nn)
                    candidates = scored
            candidates = list(dict.fromkeys(candidates))
            if len(candidates) == 1:
                hit = by_norm.loc[candidates[0]]
                kind = "fuzzy_unique"
            elif len(candidates) > 1:
                kind = "fuzzy_ambiguous"
        if hit is not None and kind != "fuzzy_ambiguous":
            out.iat[i, out.columns.get_loc("sepa_lat")] = float(hit["latitude"])
            out.iat[i, out.columns.get_loc("sepa_lon")] = float(hit["longitude"])
            out.iat[i, out.columns.get_loc("sepa_site")] = str(hit["site"])
            out.iat[i, out.columns.get_loc("sepa_match")] = kind
    return out


def nominatim_geocode(
    query: str,
    *,
    session: requests.Session | None = None,
    user_agent: str = "pa-marine-model/0.1 (research; scotland-shellfish-geocode)",
    sleep_s: float = 1.1,
    countrycodes: str = "gb",
    viewbox: str = "-8.0,54.5,-0.5,61.0",  # rough Scotland bbox
) -> dict[str, Any] | None:
    """Single Nominatim search; polite rate-limit. Returns best hit or None."""
    sess = session or requests.Session()
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "limit": 3,
        "countrycodes": countrycodes,
        "viewbox": viewbox,
        "bounded": 0,
        "addressdetails": 0,
    }
    headers = {"User-Agent": user_agent}
    time.sleep(sleep_s)
    r = sess.get(url, params=params, headers=headers, timeout=60)
    r.raise_for_status()
    hits = r.json()
    if not hits:
        return None
    # Prefer water/bay/loch/coastal class
    def score(h: dict) -> tuple:
        cls = (h.get("class") or "", h.get("type") or "")
        waterish = 1 if cls[0] in {"natural", "waterway", "place", "bay"} or "water" in cls[1] or "bay" in cls[1] or "loch" in (h.get("display_name") or "").lower() else 0
        return (waterish, float(h.get("importance") or 0))

    best = sorted(hits, key=score, reverse=True)[0]
    return {
        "latitude": float(best["lat"]),
        "longitude": float(best["lon"]),
        "display_name": best.get("display_name"),
        "class": best.get("class"),
        "type": best.get("type"),
        "importance": best.get("importance"),
        "n_hits": len(hits),
    }


def geocode_unique_names(
    names: list[str],
    *,
    cache: dict[str, dict[str, Any] | None] | None = None,
    sleep_s: float = 1.1,
    query_suffix: str = ", Scotland, UK",
) -> dict[str, dict[str, Any] | None]:
    """Nominatim-geocode unique place strings; returns map name → hit|None."""
    cache = cache if cache is not None else {}
    sess = requests.Session()
    for name in names:
        if not name or name in cache:
            continue
        q = f"{name}{query_suffix}"
        try:
            hit = nominatim_geocode(q, session=sess, sleep_s=sleep_s)
            # retry with 'loch' hint if miss and name lacks loch
            if hit is None and "loch" not in name.lower():
                hit = nominatim_geocode(
                    f"{name} shellfish loch{query_suffix}",
                    session=sess,
                    sleep_s=sleep_s,
                )
            cache[name] = hit
        except Exception as exc:  # noqa: BLE001 — keep going
            cache[name] = {"error": str(exc)}
    return cache


def build_site_coords(
    sites: pd.DataFrame,
    closures: pd.DataFrame | None = None,
    sepa: pd.DataFrame | None = None,
    nominatim_cache: dict[str, dict[str, Any] | None] | None = None,
    use_nominatim: bool = True,
    nominatim_sleep_s: float = 1.1,
) -> pd.DataFrame:
    """Build Sin-level coord table with source + confidence.

    sites columns: Sin, AreaName, SiteName (optional), LocalAuthorityName (optional).
    """
    base = sites.copy()
    for c in ("Sin", "AreaName"):
        if c not in base.columns:
            raise ValueError(f"sites missing {c}")
    if "SiteName" not in base.columns:
        base["SiteName"] = pd.NA
    base["Sin"] = base["Sin"].astype(str)
    base = base.drop_duplicates("Sin").reset_index(drop=True)

    # 1) OSGB from closures by AreaName
    closure_cent = (
        centroids_from_closures(closures)
        if closures is not None and len(closures)
        else pd.DataFrame()
    )
    by_area_osgb = (
        closure_cent.set_index("AreaName")
        if len(closure_cent)
        else pd.DataFrame()
    )

    # 2) SEPA
    if sepa is not None and len(sepa):
        matched = match_sepa(base, sepa)
    else:
        matched = base.copy()
        matched["sepa_lat"] = np.nan
        matched["sepa_lon"] = np.nan
        matched["sepa_match"] = pd.NA
        matched["sepa_site"] = pd.NA

    # 3) Nominatim for remaining — try AreaName, then LA-scoped, then SiteName
    nom_cache = nominatim_cache if nominatim_cache is not None else {}
    has_la = "LocalAuthorityName" in matched.columns

    def _queries_for(row) -> list[str]:
        an = str(row["AreaName"])
        sn = str(row["SiteName"]) if pd.notna(row.get("SiteName")) else ""
        la = str(row["LocalAuthorityName"]) if has_la and pd.notna(row.get("LocalAuthorityName")) else ""
        la_short = la.split(":")[-1].strip() if la else ""
        region = ""
        lu = la.lower()
        if "shetland" in lu:
            region = "Shetland"
        elif "orkney" in lu:
            region = "Orkney"
        elif "fife" in lu:
            region = "Fife"
        elif "dumfries" in lu:
            region = "Dumfries and Galloway"
        elif "argyll" in lu:
            region = "Argyll"
        elif la_short:
            region = la_short

        # progressive cores: full name, before colon, first 2 tokens, normalized
        cores = [an]
        if ":" in an:
            cores.append(an.split(":")[0].strip())
            cores.append(an.split(":")[-1].strip())
        parts = re.split(r"[\s/:]+", an)
        if len(parts) >= 2:
            cores.append(" ".join(parts[:2]))
        if len(parts) >= 3:
            cores.append(" ".join(parts[:3]))
        core_norm = normalize_place_name(an)
        if core_norm:
            cores.append(core_norm.title() if core_norm.islower() else core_norm)
            cores.append(core_norm)

        qs: list[str] = []
        seed = NOMINATIM_AREA_SEEDS.get(an)
        if seed:
            qs.append(seed)
        for c in cores:
            qs.append(c)
            if region:
                qs.append(f"{c}, {region}")
                qs.append(f"{c}, {region}, Scotland")
        if sn and sn.lower() not in {"inner", "outer", "north", "south", "east", "west"} and len(sn) > 3:
            qs.append(sn)
            if region:
                qs.append(f"{sn}, {region}")
        out_q, seen = [], set()
        for q in qs:
            q = str(q).strip(" ,")
            if q and q not in seen and len(q) > 2:
                seen.add(q)
                out_q.append(q)
        return out_q

    need_rows = []
    for _, row in matched.iterrows():
        an = row["AreaName"]
        has_osgb = an in by_area_osgb.index if len(by_area_osgb) else False
        has_sepa = pd.notna(row.get("sepa_lat"))
        if not has_osgb and not has_sepa:
            need_rows.append(row)

    if use_nominatim and need_rows:
        # Only fetch queries that are required to resolve a row: stop per-row once
        # a cache hit exists for any of its candidate queries.
        sess_queries = []
        for row in need_rows:
            qs = _queries_for(row)
            if any(
                (nom_cache.get(q) and isinstance(nom_cache.get(q), dict) and "latitude" in nom_cache.get(q))
                for q in qs
            ):
                continue
            # Prefer first 3 candidates only (avoid combinatorial Nominatim spam)
            for q in qs[:3]:
                if q not in nom_cache:
                    sess_queries.append(q)
        sess_queries = list(dict.fromkeys(sess_queries))
        if sess_queries:
            geocode_unique_names(sess_queries, cache=nom_cache, sleep_s=nominatim_sleep_s)

    def _pick_nom(row) -> dict | None:
        for q in _queries_for(row):
            hit = nom_cache.get(q)
            if hit and "latitude" in hit:
                hit = dict(hit)
                hit["_query"] = q
                return hit
        return None

    rows = []
    for _, row in matched.iterrows():
        sin = str(row["Sin"])
        an = row["AreaName"]
        sn = row.get("SiteName")
        lat = lon = np.nan
        source = "none"
        confidence = "none"
        detail = ""

        if len(by_area_osgb) and an in by_area_osgb.index:
            hit = by_area_osgb.loc[an]
            if isinstance(hit, pd.DataFrame):
                hit = hit.iloc[0]
            lat, lon = float(hit["latitude"]), float(hit["longitude"])
            source = "osgb_closure"
            confidence = "high"
            detail = f"n_osgb={int(hit.get('n_osgb_points', 0))}"
        elif pd.notna(row.get("sepa_lat")):
            lat, lon = float(row["sepa_lat"]), float(row["sepa_lon"])
            source = "sepa_swpa"
            kind = str(row.get("sepa_match") or "area_exact")
            confidence = "high" if kind.endswith("exact") or kind == "alias" else "medium"
            detail = f"match={kind};sepa={row.get('sepa_site')}"
        else:
            hit = _pick_nom(row) if use_nominatim else None
            if hit and "latitude" in hit:
                lat, lon = float(hit["latitude"]), float(hit["longitude"])
                source = "nominatim"
                n_hits = int(hit.get("n_hits") or 1)
                imp = float(hit.get("importance") or 0)
                if n_hits > 1 or imp < 0.3:
                    confidence = "low"
                else:
                    confidence = "medium"
                detail = f"q={hit.get('_query')};{hit.get('display_name') or ''}"
                if not (54.0 <= lat <= 61.5 and -9.0 <= lon <= 0.5):
                    confidence = "low"
                    detail = f"out_of_bbox;{detail}"

        rows.append(
            {
                "Sin": sin,
                "AreaName": an,
                "SiteName": sn if pd.notna(sn) else "",
                "latitude": lat if not (isinstance(lat, float) and np.isnan(lat)) else np.nan,
                "longitude": lon if not (isinstance(lon, float) and np.isnan(lon)) else np.nan,
                "source": source,
                "confidence": confidence,
                "detail": detail,
            }
        )

    out = pd.DataFrame(rows)
    # Prefer OSGB Sin from closure when AreaName maps to multiple SINs: already per-Sin
    return out.sort_values(["source", "AreaName", "Sin"]).reset_index(drop=True)


def apply_coords_to_panel(panel: pd.DataFrame, coords: pd.DataFrame) -> pd.DataFrame:
    """Left-join coords onto phyto/toxin panel by Sin; set has_coords."""
    c = coords[["Sin", "latitude", "longitude", "source", "confidence"]].copy()
    c["Sin"] = c["Sin"].astype(str)
    c = c.rename(
        columns={
            "latitude": "latitude_geo",
            "longitude": "longitude_geo",
            "source": "coord_source",
            "confidence": "coord_confidence",
        }
    )
    out = panel.copy()
    out["Sin"] = out["Sin"].astype(str)
    # drop prior coord columns so re-runs are idempotent
    drop_cols = [
        "latitude",
        "longitude",
        "coord_source",
        "coord_confidence",
        "latitude_geo",
        "longitude_geo",
    ]
    out = out.drop(columns=[x for x in drop_cols if x in out.columns], errors="ignore")
    out = out.merge(c, on="Sin", how="left")
    out = out.rename(columns={"latitude_geo": "latitude", "longitude_geo": "longitude"})
    out["has_coords"] = out["latitude"].notna() & out["longitude"].notna()
    return out


def coverage_stats(panel: pd.DataFrame, coords: pd.DataFrame) -> dict[str, Any]:
    """Coverage percentages for Sin-level coords and panel row coverage."""
    n_sin = int(panel["Sin"].nunique()) if "Sin" in panel.columns else 0
    coord_ok = coords.dropna(subset=["latitude", "longitude"])
    sins_with = set(coord_ok["Sin"].astype(str))
    panel_sins = set(panel["Sin"].astype(str)) if "Sin" in panel.columns else set()
    covered = panel_sins & sins_with
    n_rows = len(panel)
    n_rows_covered = int(panel["Sin"].astype(str).isin(sins_with).sum()) if n_rows else 0
    by_source = (
        coord_ok.groupby("source").size().to_dict() if len(coord_ok) else {}
    )
    by_conf = (
        coord_ok.groupby("confidence").size().to_dict() if len(coord_ok) else {}
    )
    return {
        "n_panel_sins": n_sin,
        "n_coord_rows": int(len(coords)),
        "n_coords_with_latlon": int(len(coord_ok)),
        "n_panel_sins_with_coords": int(len(covered)),
        "pct_panel_sins_with_coords": round(100.0 * len(covered) / n_sin, 2) if n_sin else 0.0,
        "n_panel_rows": n_rows,
        "n_panel_rows_with_coords": n_rows_covered,
        "pct_panel_rows_with_coords": round(100.0 * n_rows_covered / n_rows, 2) if n_rows else 0.0,
        "coords_by_source": {str(k): int(v) for k, v in by_source.items()},
        "coords_by_confidence": {str(k): int(v) for k, v in by_conf.items()},
        "n_panel_sins_missing_coords": int(len(panel_sins - sins_with)),
        "fss_wfs_note": (
            "Marine Scotland GeoServer layer nmp:fss_shellfish_classified_areas "
            "is OGL-licensed but HTTP 401 without login — not used."
        ),
    }
