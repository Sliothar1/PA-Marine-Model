"""National Marine Institute biotoxin + harvest-status ingest (ERDDAP).

Verified 2026-09-01 against erddap3.marine.ie info.json for:
  - habs_biotoxin / habs_biotoxin_pivot
  - habs_status
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

TOXINS = ("dsp", "asp", "azp", "psp", "ptx", "ytx")

PIVOT_COLUMNS = [
    "species",
    "sampleid",
    "time",
    "latitude",
    "longitude",
    "location_name",
    "week_no",
    "weekdatefrom",
    "location_id",
    "region_name",
    "parent_area_id",
    "parent_area_code",
    "parent_area_name",
    "location_code",
    "tissue_type_name",
    "samplecode",
    "dsp_resultvalue",
    "dsp_threshold",
    "dsp_result_value_text",
    "asp_resultvalue",
    "asp_threshold",
    "asp_result_value_text",
    "azp_resultvalue",
    "azp_threshold",
    "azp_result_value_text",
    "psp_resultvalue",
    "psp_threshold",
    "psp_result_value_text",
    "ptx_resultvalue",
    "ptx_threshold",
    "ptx_result_value_text",
    "ytx_resultvalue",
    "ytx_threshold",
    "ytx_result_value_text",
]

LONG_COLUMNS = [
    "species",
    "sampleid",
    "time",
    "latitude",
    "longitude",
    "location_name",
    "week_no",
    "weekdatefrom",
    "region_name",
    "parent_area_id",
    "parent_area_code",
    "parent_area_name",
    "location_code",
    "publishedbiotoxinstatusesid",
    "publishedbiotoxindecisionsid",
    "resultname",
    "resultvalue",
    "unitshortname",
    "threshold",
    "samplecode",
    "result_value_text",
    "tissue_type_name",
    "location_id",
    "PublishedDT",
]

STATUS_COLUMNS = [
    "species",
    "periodstart_date",
    "parentarea_name",
    "periodend_date",
    "statuseffective_startdate",
    "statusexpiry_date",
    "reason_name",
    "productionareastatusname",
    "productionstatusestatusname",
    "publisheddt",
]

CLOSED_STATUSES = {"Closed", "Closed Pending", "Harvest Restricted"}


def download_biotoxin_pivot(cfg: dict[str, Any], out_path: str | Path | None = None) -> pd.DataFrame:
    from pa_marine.erddap import tabledap_csv

    bt = cfg["biotoxin"]
    df = tabledap_csv(bt["erddap_base"], bt["pivot_dataset_id"], PIVOT_COLUMNS, timeout=600)
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
    return df


def download_biotoxin_long(cfg: dict[str, Any], out_path: str | Path | None = None) -> pd.DataFrame:
    from pa_marine.erddap import tabledap_csv

    bt = cfg["biotoxin"]
    df = tabledap_csv(bt["erddap_base"], bt["long_dataset_id"], LONG_COLUMNS, timeout=600)
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
    return df


def download_hab_status(cfg: dict[str, Any], out_path: str | Path | None = None) -> pd.DataFrame:
    from pa_marine.erddap import tabledap_csv

    bt = cfg["biotoxin"]
    df = tabledap_csv(bt["erddap_base"], bt["status_dataset_id"], STATUS_COLUMNS, timeout=600)
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
    return df


def _coerce_pivot(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["time"] = pd.to_datetime(out["time"], utc=True, errors="coerce")
    out["location_id"] = pd.to_numeric(out["location_id"], errors="coerce")
    for t in TOXINS:
        out[f"{t}_resultvalue"] = pd.to_numeric(out[f"{t}_resultvalue"], errors="coerce")
        out[f"{t}_threshold"] = pd.to_numeric(out[f"{t}_threshold"], errors="coerce")
        # exceed when both present and value >= regulatory threshold
        out[f"exceed_{t}"] = (
            out[f"{t}_resultvalue"].notna()
            & out[f"{t}_threshold"].notna()
            & (out[f"{t}_resultvalue"] >= out[f"{t}_threshold"])
        ).astype(int)
        # measured flag (had a numeric result)
        out[f"measured_{t}"] = out[f"{t}_resultvalue"].notna().astype(int)
    return out


def toxin_station_week_panel(pivot: pd.DataFrame) -> pd.DataFrame:
    """Aggregate biotoxin pivot to location_id × ISO week.

    Exceedance: max over samples/species of (resultvalue >= threshold).
    Max toxin value kept for diagnostics.
    """
    df = _coerce_pivot(pivot)
    df = df.dropna(subset=["time", "location_id"])
    df["location_id"] = df["location_id"].astype(int)
    iso = df["time"].dt.isocalendar()
    df["iso_year"] = iso.year.astype(int)
    df["iso_week"] = iso.week.astype(int)
    df["week_start"] = df["time"].dt.tz_convert("UTC") - pd.to_timedelta(df["time"].dt.dayofweek, unit="D")
    df["week_start"] = df["week_start"].dt.normalize()

    keys = ["location_id", "iso_year", "iso_week", "week_start"]
    meta = df.groupby(keys, as_index=False).agg(
        latitude=("latitude", "median"),
        longitude=("longitude", "median"),
        location_name=("location_name", "first"),
        parent_area_name=("parent_area_name", "first"),
        parent_area_code=("parent_area_code", "first"),
        region_name=("region_name", "first"),
        n_toxin_samples=("sampleid", "nunique"),
        n_species=("species", "nunique"),
    )
    for t in TOXINS:
        g = (
            df.groupby(keys, as_index=False)
            .agg(
                **{
                    f"exceed_{t}": (f"exceed_{t}", "max"),
                    f"measured_{t}": (f"measured_{t}", "max"),
                    f"max_{t}": (f"{t}_resultvalue", "max"),
                    f"thr_{t}": (f"{t}_threshold", "median"),
                }
            )
        )
        meta = meta.merge(g, on=keys, how="left")
        meta[f"exceed_{t}"] = meta[f"exceed_{t}"].fillna(0).astype(int)
        meta[f"measured_{t}"] = meta[f"measured_{t}"].fillna(0).astype(int)
    meta["exceed_any"] = meta[[f"exceed_{t}" for t in TOXINS]].max(axis=1).astype(int)
    return meta.sort_values(keys).reset_index(drop=True)


def status_area_week_panel(status: pd.DataFrame) -> pd.DataFrame:
    """Expand harvest-status intervals onto parent-area × ISO week with closed flag.

    habs_status has no lat/lon/location_id — key is parentarea_name only.
    """
    st = status.copy()
    for c in ("statuseffective_startdate", "statusexpiry_date", "periodstart_date", "periodend_date"):
        st[c] = pd.to_datetime(st[c], utc=True, errors="coerce")
    st = st.dropna(subset=["parentarea_name", "statuseffective_startdate"])
    st["statusexpiry_date"] = st["statusexpiry_date"].fillna(st["statuseffective_startdate"] + pd.Timedelta(days=14))
    st["is_closed"] = st["productionareastatusname"].isin(CLOSED_STATUSES).astype(int)
    st["is_open"] = (st["productionareastatusname"] == "Open").astype(int)

    # Sample each status row onto Mondays it covers (cap long intervals at 12 weeks).
    rows = []
    for _, r in st.iterrows():
        start = r["statuseffective_startdate"]
        end = r["statusexpiry_date"]
        if pd.isna(start) or pd.isna(end) or end < start:
            continue
        # Monday of start week
        mon = start - pd.Timedelta(days=int(start.dayofweek))
        mon = mon.normalize()
        end_n = end.normalize()
        n_weeks = int(((end_n - mon).days) // 7) + 1
        n_weeks = max(1, min(n_weeks, 12))
        for k in range(n_weeks):
            ws = mon + pd.Timedelta(days=7 * k)
            if ws > end_n:
                break
            iso = ws.isocalendar()
            rows.append(
                {
                    "parent_area_name": r["parentarea_name"],
                    "species": r["species"],
                    "week_start": ws,
                    "iso_year": int(iso.year),
                    "iso_week": int(iso.week),
                    "is_closed": int(r["is_closed"]),
                    "is_open": int(r["is_open"]),
                    "status_name": r["productionareastatusname"],
                    "reason_name": r.get("reason_name"),
                }
            )
    if not rows:
        return pd.DataFrame()
    exp = pd.DataFrame(rows)
    # Any closed species in area-week => closed
    g = (
        exp.groupby(["parent_area_name", "iso_year", "iso_week", "week_start"], as_index=False)
        .agg(
            closed=("is_closed", "max"),
            open_flag=("is_open", "max"),
            n_status_rows=("status_name", "size"),
            status_modes=("status_name", lambda s: s.mode().iloc[0] if len(s) else None),
        )
    )
    return g.sort_values(["parent_area_name", "week_start"]).reset_index(drop=True)


def attach_status_to_toxin_panel(toxin_panel: pd.DataFrame, status_week: pd.DataFrame) -> pd.DataFrame:
    """Left-join closed flag via parent_area_name + ISO week."""
    tp = toxin_panel.copy()
    if status_week is None or status_week.empty or "parent_area_name" not in tp.columns:
        tp["closed"] = np.nan
        tp["status_join"] = "no_status"
        return tp
    sw = status_week.copy()
    sw["week_start"] = pd.to_datetime(sw["week_start"], utc=True)
    tp["week_start"] = pd.to_datetime(tp["week_start"], utc=True)
    # normalize names lightly
    tp["_area_key"] = tp["parent_area_name"].fillna("").astype(str).str.strip().str.lower()
    sw["_area_key"] = sw["parent_area_name"].fillna("").astype(str).str.strip().str.lower()
    merged = tp.merge(
        sw[["_area_key", "iso_year", "iso_week", "closed", "status_modes", "n_status_rows"]],
        on=["_area_key", "iso_year", "iso_week"],
        how="left",
        suffixes=("", "_st"),
    )
    merged["status_join"] = np.where(merged["closed"].notna(), "matched", "unmatched_area_week")
    return merged.drop(columns=["_area_key"])


def dinophysis_dsp_agreement(
    phyto_panel: pd.DataFrame,
    toxin_panel: pd.DataFrame,
) -> dict[str, Any]:
    """Same location_id × ISO week: phyto Dinophysis exceedance vs DSP toxin exceedance."""
    p = phyto_panel.copy()
    t = toxin_panel.copy()
    p["location_id"] = pd.to_numeric(p["location_id"], errors="coerce").astype("Int64")
    t["location_id"] = pd.to_numeric(t["location_id"], errors="coerce").astype("Int64")
    keys = ["location_id", "iso_year", "iso_week"]
    cols_p = keys + [c for c in ("y_dinophysis", "count_dinophysis") if c in p.columns]
    cols_t = keys + [c for c in ("exceed_dsp", "measured_dsp", "max_dsp") if c in t.columns]
    m = p[cols_p].merge(t[cols_t], on=keys, how="inner")
    out: dict[str, Any] = {
        "n_joined_station_weeks": int(len(m)),
        "n_shared_locations": int(m["location_id"].nunique()) if len(m) else 0,
        "phyto_locations": int(p["location_id"].nunique()),
        "toxin_locations": int(t["location_id"].nunique()),
        "location_overlap": int(len(set(p["location_id"].dropna()) & set(t["location_id"].dropna()))),
    }
    if len(m) == 0 or "y_dinophysis" not in m.columns or "exceed_dsp" not in m.columns:
        out["usable"] = False
        out["note"] = "No overlapping station-weeks or missing columns"
        return out
    # only weeks with DSP measured
    mm = m[m.get("measured_dsp", 1) == 1].copy() if "measured_dsp" in m.columns else m
    if len(mm) < 20:
        out["usable"] = False
        out["note"] = f"Too few DSP-measured overlaps ({len(mm)})"
        return out
    y = mm["y_dinophysis"].astype(int)
    x = mm["exceed_dsp"].astype(int)
    tp_ = int(((y == 1) & (x == 1)).sum())
    fp = int(((y == 0) & (x == 1)).sum())
    fn = int(((y == 1) & (x == 0)).sum())
    tn = int(((y == 0) & (x == 0)).sum())
    # Pearson on binary + count vs max_dsp if available
    corr_bin = float(np.corrcoef(y, x)[0, 1]) if y.nunique() > 1 and x.nunique() > 1 else float("nan")
    out.update(
        {
            "usable": True,
            "n_dsp_measured_overlaps": int(len(mm)),
            "phyto_positive_rate": float(y.mean()),
            "dsp_exceed_rate": float(x.mean()),
            "confusion": {"tp": tp_, "fp": fp, "fn": fn, "tn": tn},
            "precision_dsp_given_phyto": float(tp_ / (tp_ + fp)) if (tp_ + fp) else None,
            "recall_dsp_given_phyto": float(tp_ / (tp_ + fn)) if (tp_ + fn) else None,
            "precision_phyto_given_dsp": float(tp_ / (tp_ + fn)) if (tp_ + fn) else None,
            "agreement_rate": float((tp_ + tn) / len(mm)),
            "pearson_binary": corr_bin,
        }
    )
    if "count_dinophysis" in mm.columns and "max_dsp" in mm.columns:
        sub = mm[["count_dinophysis", "max_dsp"]].dropna()
        if len(sub) >= 20 and sub["count_dinophysis"].nunique() > 1 and sub["max_dsp"].nunique() > 1:
            out["pearson_count_vs_max_dsp"] = float(
                np.corrcoef(sub["count_dinophysis"].to_numpy(), sub["max_dsp"].to_numpy())[0, 1]
            )
            out["spearman_count_vs_max_dsp"] = float(sub["count_dinophysis"].corr(sub["max_dsp"], method="spearman"))
    return out


def document_sst_join(
    toxin_panel: pd.DataFrame,
    mhw_daily: pd.DataFrame | None,
    phyto_panel: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Report whether location_id joins to existing Irish SST/MHW features."""
    t_locs = set(pd.to_numeric(toxin_panel["location_id"], errors="coerce").dropna().astype(int))
    doc: dict[str, Any] = {
        "toxin_join_key": "location_id (int) + week_start / ISO week",
        "n_toxin_locations": len(t_locs),
    }
    if mhw_daily is not None and "location_id" in mhw_daily.columns:
        m_locs = set(pd.to_numeric(mhw_daily["location_id"], errors="coerce").dropna().astype(int))
        inter = t_locs & m_locs
        doc.update(
            {
                "mhw_locations": len(m_locs),
                "toxin_mhw_overlap": len(inter),
                "toxin_only_locations": len(t_locs - m_locs),
                "mhw_only_locations": len(m_locs - t_locs),
                "sst_join_works": len(inter) > 0,
                "note": (
                    "SST/MHW daily features were built on phyto location_ids. "
                    "Toxin sites that appear in phyto share the same location_id and join cleanly; "
                    "toxin-only sites need new OISST pixel pulls."
                ),
            }
        )
    else:
        doc["sst_join_works"] = False
        doc["note"] = "mhw_daily missing"
    if phyto_panel is not None:
        p_locs = set(pd.to_numeric(phyto_panel["location_id"], errors="coerce").dropna().astype(int))
        doc["phyto_locations"] = len(p_locs)
        doc["toxin_phyto_overlap"] = len(t_locs & p_locs)
    # status key problem
    doc["status_join_key"] = "parent_area_name (string) + ISO week — no lat/lon/location_id on habs_status"
    return doc
