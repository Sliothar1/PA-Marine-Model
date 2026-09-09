#!/usr/bin/env python3
"""Export Felix demo instance windows as JSON for GrokD4M ``/marine``.

Windows
  2018 JJA  — NE Atlantic / Connemara focus (HAB season vs modest MHW)
  2022 JJA  — Galway inner-bay vs Connemara contrast
  2023 June — flagship shelf MHW (heatwave ≠ bloom; national HAB below clim)

Reads processed tables only (no network). Prefers
``data/processed/joined_features.parquet``, then the committed
``joined_features_osi_sst.parquet`` (same OISST/MHW columns + ODYSSEA extras;
ODYSSEA is **not** used as a predictive quote). Falls back to
``connemara_farms_scores.csv`` / ``june2023_case_study_hab_weekly.csv``.

Copy into GrokD4M::

    mkdir -p /path/to/GrokD4M/data/marine/instances
    cp data/processed/demo_instances/2018_jja_ne_atlantic.json \\
       /path/to/GrokD4M/data/marine/instances/
    cp data/processed/demo_instances/2022_jja_galway_connemara.json \\
       /path/to/GrokD4M/data/marine/instances/
    cp data/processed/demo_instances/2023_june_flagship.json \\
       /path/to/GrokD4M/data/marine/instances/

Large full dumps under ``data/processed/demo_instances/*.json`` are gitignored.
Small samples under ``samples/`` are committed.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from pa_marine.demo_features import attach_demo_features

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT = PROC / "demo_instances"
SAMPLES = OUT / "samples"

# Connemara NMP + nearby (farms table + Killary variants).
CONNEMARA_IDS = {
    163,
    171,
    172,
    174,
    175,
    177,
    179,
    374,
    517,
    601,
    633,
    650,
    702,
}
# Inner Galway Bay / south Galway (Inverin → Kinvarra cluster).
GALWAY_INNER_IDS = {156, 164, 165, 168, 170, 178, 489, 491}

WEEK_FIELDS = [
    "location_id",
    "location_name",
    "latitude",
    "longitude",
    "week_start",
    "iso_year",
    "iso_week",
    "sst",
    "ssta",
    "in_mhw",
    "mhw_duration",
    "mhw_cum_intensity",
    "count_dinophysis",
    "y_dinophysis",
    "y_dinophysis_nowcast",
    "cov_sst_missing",
    "cov_sst_always_missing",
    "demo_sw_station_week_rate",
    "demo_sw_station_rate",
    "demo_sw_week_rate",
    "region",
]

CORK_LOCK = {
    "spine": "STRONG_OISST",
    "judge_quote": "STRONG_OISST ~0.295 calibrated test PR-AUC",
    "chl_odyssea": "narrative-only",
    "heatwave_neq_bloom": True,
}


def _clean_num(v: Any) -> Any:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return int(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if math.isnan(f) or math.isinf(f):
        return None
    if abs(f - round(f)) < 1e-9 and abs(f) < 1e12:
        return int(round(f))
    return round(f, 5)


def _loc_id(v: Any) -> Any:
    if pd.isna(v):
        return None
    try:
        f = float(v)
        if abs(f - round(f)) < 1e-9:
            return int(round(f))
    except (TypeError, ValueError):
        pass
    return v


def find_panel_path(explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    for rel in (
        "joined_features.parquet",
        "joined_features_osi_sst.parquet",
        "connemara_farms_scores.csv",
        "june2023_case_study_hab_weekly.csv",
    ):
        p = PROC / rel
        if p.exists():
            return p
    return None


def load_panel(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    df["week_start"] = pd.to_datetime(df["week_start"], utc=False, errors="coerce")
    if "location_id" in df.columns:
        df["location_id"] = df["location_id"].map(_loc_id)
    if "exceedance" in df.columns and "y_dinophysis" not in df.columns:
        df["y_dinophysis"] = pd.to_numeric(df["exceedance"], errors="coerce")
    return df


def tag_region(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    def _reg(lid: Any) -> str:
        try:
            i = int(lid)
        except (TypeError, ValueError):
            return "other"
        if i in CONNEMARA_IDS:
            return "connemara"
        if i in GALWAY_INNER_IDS:
            return "galway_inner"
        return "other"

    out["region"] = out["location_id"].map(_reg) if "location_id" in out.columns else "other"
    return out


def load_crw() -> pd.DataFrame | None:
    p = PROC / "crw_mhw_ireland_daily_summary.csv"
    if not p.exists():
        return None
    crw = pd.read_csv(p, parse_dates=["time"])
    crw["time"] = pd.to_datetime(crw["time"], utc=True, errors="coerce").dt.tz_localize(None)
    return crw


def crw_summary(crw: pd.DataFrame | None, start: str, end: str) -> dict[str, Any]:
    if crw is None:
        return {"available": False, "note": "crw_mhw_ireland_daily_summary.csv missing or empty for window"}
    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    sub = crw[(crw["time"] >= t0) & (crw["time"] <= t1 + pd.Timedelta(days=1))]
    if sub.empty:
        return {
            "available": False,
            "note": "CRW Irish-bbox summary on disk starts 2022-01-01; this window has no rows",
            "window": [start, end],
        }
    peak_idx = sub["frac_mhw"].idxmax()
    peak_row = sub.loc[peak_idx]
    return {
        "available": True,
        "source": "data/processed/crw_mhw_ireland_daily_summary.csv",
        "bbox": "51–56°N, 11–5°W",
        "n_days": int(len(sub)),
        "mean_frac_mhw": _clean_num(sub["frac_mhw"].mean()),
        "peak_frac_mhw": _clean_num(peak_row["frac_mhw"]),
        "peak_frac_date": pd.Timestamp(peak_row["time"]).strftime("%Y-%m-%d"),
        "mean_cat": _clean_num(sub["mean_cat"].mean()),
        "max_cat": _clean_num(sub["max_cat"].max()),
    }


def hab_block(sub: pd.DataFrame, full: pd.DataFrame, year: int) -> dict[str, Any]:
    def _scope(name: str, d: pd.DataFrame) -> dict[str, Any]:
        if d.empty or "y_dinophysis" not in d.columns:
            return {"scope": name, "n_station_weeks": 0}
        y = pd.to_numeric(d["y_dinophysis"], errors="coerce")
        n = int(y.notna().sum())
        k = int((y == 1).sum())
        iso_weeks = set(pd.to_numeric(d["iso_week"], errors="coerce").dropna().astype(int))
        clim = None
        if iso_weeks and "y_dinophysis" in full.columns:
            mask = (
                full["iso_year"].between(2015, 2024)
                & (full["iso_year"] != year)
                & full["iso_week"].isin(iso_weeks)
            )
            if "location_id" in d.columns and name != "national":
                mask = mask & full["location_id"].isin(set(d["location_id"]))
            cy = pd.to_numeric(full.loc[mask, "y_dinophysis"], errors="coerce")
            if cy.notna().any():
                clim = _clean_num(float(cy.mean()))
        rate = float(y.mean()) if n else None
        vs = None
        if rate is not None and clim is not None:
            vs = "below" if rate < clim else ("above" if rate > clim else "equal")
        sst = pd.to_numeric(d["sst"], errors="coerce") if "sst" in d.columns else pd.Series(dtype=float)
        ssta = pd.to_numeric(d["ssta"], errors="coerce") if "ssta" in d.columns else pd.Series(dtype=float)
        inm = pd.to_numeric(d["in_mhw"], errors="coerce") if "in_mhw" in d.columns else pd.Series(dtype=float)
        return {
            "scope": name,
            "n_station_weeks": n,
            "n_exceedances": k,
            "exceedance_rate": _clean_num(rate),
            "same_week_clim_2015_2024_excl_event": clim,
            "vs_clim": vs,
            "sst_coverage": _clean_num(float(sst.notna().mean()) if len(d) else None),
            "mean_sst": _clean_num(float(sst.mean()) if sst.notna().any() else None),
            "mean_ssta": _clean_num(float(ssta.mean()) if ssta.notna().any() else None),
            "mean_in_mhw": _clean_num(float(inm.mean()) if inm.notna().any() else None),
        }

    conn = sub[sub["region"] == "connemara"] if "region" in sub.columns else sub.iloc[0:0]
    gal = sub[sub["region"] == "galway_inner"] if "region" in sub.columns else sub.iloc[0:0]
    return {
        "national": _scope("national", sub),
        "connemara": _scope("connemara", conn),
        "galway_inner": _scope("galway_inner", gal),
    }


def weekly_records(sub: pd.DataFrame, *, limit: int | None = None) -> list[dict[str, Any]]:
    cols = [c for c in WEEK_FIELDS if c in sub.columns]
    d = sub[cols].copy()
    d = d.sort_values([c for c in ("week_start", "region", "location_id") if c in d.columns])
    if limit is not None:
        d = d.head(limit)
    rows = []
    for rec in d.to_dict(orient="records"):
        row = {}
        for k, v in rec.items():
            if k == "week_start":
                row[k] = pd.Timestamp(v).strftime("%Y-%m-%d") if pd.notna(v) else None
            elif k in {"location_id", "iso_year", "iso_week", "y_dinophysis", "y_dinophysis_nowcast",
                       "cov_sst_missing", "cov_sst_always_missing", "in_mhw"}:
                row[k] = _loc_id(v) if k == "location_id" else _clean_num(v)
            else:
                row[k] = v if isinstance(v, str) else _clean_num(v)
        rows.append(row)
    return rows


def _rel(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def missing_inputs_note(panel_path: Path | None) -> list[str]:
    notes = []
    if panel_path is None:
        notes.append(
            "No panel found. Rebuild locally: "
            "`python scripts/build_panel.py && python scripts/compute_mhw.py && "
            "python scripts/join_features.py` → data/processed/joined_features.parquet"
        )
    elif panel_path.name != "joined_features.parquet":
        notes.append(
            f"Using {_rel(panel_path)} "
            "(canonical joined_features.parquet not present; this is OK for demo export)."
        )
    if not (PROC / "crw_mhw_ireland_daily_summary.csv").exists():
        notes.append("CRW daily summary missing — 2022/2023 shelf MHW fraction will be absent.")
    return notes


SPECS: list[dict[str, Any]] = [
    {
        "id": "2018_jja_ne_atlantic",
        "year": 2018,
        "title": "2018 JJA — NE Atlantic / Connemara HAB season",
        "season": "JJA",
        "start": "2018-06-01",
        "end": "2018-08-31",
        "focus": "Connemara + Irish west-coast HAB stations (NE Atlantic shelf)",
        "story": (
            "2018 was a strong Irish HAB season (national Dinophysis exceedance above "
            "same-week climatology) without a 2023-style wall-to-wall shelf MHW. "
            "Use as the ‘bloom without exceptional CRW MHW’ foil."
        ),
        "honesty": {
            **CORK_LOCK,
            "national_hab_vs_clim_expected": "above",
            "split_note": "2018 is the last train year (2003–2018); station×week rates are in-sample here.",
        },
    },
    {
        "id": "2022_jja_galway_connemara",
        "year": 2022,
        "title": "2022 JJA — Galway inner bay vs Connemara",
        "season": "JJA",
        "start": "2022-06-01",
        "end": "2022-08-31",
        "focus": "Galway inner-bay cluster vs Connemara NMP",
        "story": (
            "Test-era summer: national Dinophysis below same-week climatology; "
            "modest CRW MHW fraction vs 2023. Contrast inner Galway Bay stations "
            "with Connemara (Killary / Mannin / Clifden) for local storytelling."
        ),
        "honesty": {
            **CORK_LOCK,
            "national_hab_vs_clim_expected": "below",
            "split_note": "2022 is test (2022+). Station×week rates are out-of-sample vs train 2003–2018.",
        },
    },
    {
        "id": "2023_june_flagship",
        "year": 2023,
        "title": "2023 June — flagship NW European shelf MHW",
        "season": "June",
        "start": "2023-06-01",
        "end": "2023-06-30",
        "focus": "Irish-bbox CRW + Connemara NMP (Berthou et al. 2024)",
        "story": (
            "Flagship: CRW mean frac_mhw ≈ 0.96, yet national Dinophysis/closures "
            "were not above climatology. Heatwave ≠ bloom. Rosmuc exceedance is late May "
            "(week of 2023-05-29), bookending rather than peaking with mid-June MHW."
        ),
        "honesty": {
            **CORK_LOCK,
            "national_hab_vs_clim_expected": "below",
            "cite": "Berthou et al. 2024 doi:10.1038/s43247-024-01413-8",
            "split_note": "2023 is test. Do not claim MHW→bloom causation.",
        },
    },
]


def build_instance(
    spec: dict[str, Any],
    panel: pd.DataFrame | None,
    panel_path: Path | None,
    crw: pd.DataFrame | None,
    *,
    sample_n: int = 24,
) -> tuple[dict[str, Any], dict[str, Any]]:
    start, end, year = spec["start"], spec["end"], spec["year"]
    notes = missing_inputs_note(panel_path)
    if panel is None:
        payload = {
            "schema": "pa_marine.demo_instance.v1",
            "id": spec["id"],
            "status": "needs_local_parquet",
            "title": spec["title"],
            "window": {"start": start, "end": end, "season": spec["season"]},
            "notes": notes,
            "honesty": spec["honesty"],
            "copy_to_grokd4m": f"data/marine/instances/{spec['id']}.json",
        }
        return payload, payload

    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    sub = panel[(panel["week_start"] >= t0) & (panel["week_start"] <= t1)].copy()
    hab = hab_block(sub, panel, year) if not sub.empty else {}
    national_vs = (hab.get("national") or {}).get("vs_clim")
    weekly = weekly_records(sub)
    # Prefer Connemara (+ Galway for 2022) rows in the committed sample.
    sample_src = sub
    if spec["id"].startswith("2022"):
        sample_src = sub[sub["region"].isin(["connemara", "galway_inner"])]
    elif spec["id"].startswith("2018") or spec["id"].startswith("2023"):
        sample_src = sub[sub["region"] == "connemara"]
    if sample_src.empty:
        sample_src = sub
    sample_weekly = weekly_records(sample_src, limit=sample_n)

    payload = {
        "schema": "pa_marine.demo_instance.v1",
        "id": spec["id"],
        "status": "ok" if len(weekly) else "empty_window",
        "title": spec["title"],
        "year": year,
        "season": spec["season"],
        "window": {"start": start, "end": end},
        "focus": spec["focus"],
        "story": spec["story"],
        "honesty": {
            **spec["honesty"],
            "national_hab_vs_clim": national_vs,
            "station_week_baseline": (
                "Train-only logit-additive station×week rates attached as "
                "demo_sw_* columns. Claude CONTEXT on review/claude-patch-2 "
                "cited ≈0.284 PR-AUC for this class of baseline — motivation "
                "only; not a Cork skill claim on this branch."
            ),
        },
        "sources": {
            "panel": _rel(panel_path),
            "n_panel_rows": int(len(panel)),
            "n_window_rows": int(len(sub)),
            "crw": "data/processed/crw_mhw_ireland_daily_summary.csv",
        },
        "shelf_mhw_crw": crw_summary(crw, start, end),
        "hab": hab,
        "narrative_keys": [
            "heatwave ≠ bloom",
            "quote STRONG_OISST ~0.295 only",
            "Chl/ODYSSEA narrative-only",
            "2023 national HAB below climatology" if year == 2023 else f"{year} HAB vs climatology in hab.national.vs_clim",
        ],
        "weekly": weekly,
        "copy_to_grokd4m": f"data/marine/instances/{spec['id']}.json",
        "notes": notes,
    }
    sample = {
        **{k: payload[k] for k in payload if k != "weekly"},
        "weekly": sample_weekly,
        "sample": True,
        "sample_note": f"First {len(sample_weekly)} focus-region rows; full weekly array is gitignored.",
    }
    return payload, sample


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--joined", default=None, help="Override panel path (parquet/csv)")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--sample-n", type=int, default=24)
    args = p.parse_args()
    out = Path(args.out)
    samples = out / "samples"
    out.mkdir(parents=True, exist_ok=True)
    samples.mkdir(parents=True, exist_ok=True)

    panel_path = find_panel_path(args.joined)
    panel = None
    if panel_path is not None:
        panel = tag_region(attach_demo_features(load_panel(panel_path)))
        print(f"panel: {panel_path} n={len(panel)}")
    else:
        print("panel: MISSING — writing needs_local_parquet stubs")

    crw = load_crw()
    manifest = {
        "schema": "pa_marine.demo_instance_manifest.v1",
        "copy_into": "GrokD4M data/marine/instances/",
        "branch": "pa/demo-workstream",
        "instances": [],
    }
    for spec in SPECS:
        full, sample = build_instance(spec, panel, panel_path, crw, sample_n=args.sample_n)
        dest = out / f"{spec['id']}.json"
        sdest = samples / f"{spec['id']}.sample.json"
        dest.write_text(
            json.dumps(full, indent=2, allow_nan=False, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        sdest.write_text(
            json.dumps(sample, indent=2, allow_nan=False, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {dest.relative_to(ROOT)} status={full.get('status')} weekly={len(full.get('weekly') or [])}")
        print(f"wrote {sdest.relative_to(ROOT)}")
        hab_n = ((full.get("hab") or {}).get("national") or {}).get("n_station_weeks")
        manifest["instances"].append(
            {
                "id": spec["id"],
                "status": full.get("status"),
                "file": str(dest.relative_to(ROOT)),
                "sample": str(sdest.relative_to(ROOT)),
                "copy_to_grokd4m": full.get("copy_to_grokd4m"),
                "n_weekly": len(full.get("weekly") or []),
                "n_station_weeks_national": hab_n,
            }
        )
    man_path = out / "manifest.json"
    man_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {man_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
