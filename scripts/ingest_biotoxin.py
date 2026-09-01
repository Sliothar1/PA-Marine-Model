#!/usr/bin/env python3
"""Ingest national MI biotoxin + harvest status from ERDDAP; build week panel; check joins."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from pa_marine.biotoxin import (
    TOXINS,
    attach_status_to_toxin_panel,
    dinophysis_dsp_agreement,
    document_sst_join,
    download_biotoxin_long,
    download_biotoxin_pivot,
    download_hab_status,
    status_area_week_panel,
    toxin_station_week_panel,
)
from pa_marine.config import load_config
from pa_marine.features import join_week_panel

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, low_memory=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--skip-download", action="store_true", help="Use existing raw CSVs")
    p.add_argument("--summary", default=str(ROOT / "data/processed/biotoxin_ingest_summary.json"))
    p.add_argument("--report", default=str(ROOT / "data/processed/biotoxin_ingest_report.md"))
    args = p.parse_args()
    cfg = load_config(args.config)
    bt = cfg["biotoxin"]
    paths = cfg["paths"]

    raw_pivot = ROOT / paths.get("raw_biotoxin_pivot", "data/raw/habs_biotoxin_pivot.csv")
    raw_long = ROOT / paths.get("raw_biotoxin", "data/raw/habs_biotoxin.csv")
    raw_status = ROOT / paths.get("raw_hab_status", "data/raw/habs_status.csv")
    out_panel = ROOT / paths.get("toxin_panel", "data/processed/toxin_station_week_panel.parquet")
    out_status = ROOT / paths.get("status_panel", "data/processed/status_area_week_panel.parquet")
    out_joined = ROOT / paths.get("toxin_joined", "data/processed/toxin_joined_features.parquet")

    if not args.skip_download:
        print("downloading pivot...")
        download_biotoxin_pivot(cfg, raw_pivot)
        print("downloading long...")
        download_biotoxin_long(cfg, raw_long)
        print("downloading status...")
        download_hab_status(cfg, raw_status)

    pivot = _read(raw_pivot)
    status = _read(raw_status)
    long_n = len(_read(raw_long)) if raw_long.exists() else None

    toxin_panel = toxin_station_week_panel(pivot)
    status_week = status_area_week_panel(status)
    toxin_panel = attach_status_to_toxin_panel(toxin_panel, status_week)

    out_panel.parent.mkdir(parents=True, exist_ok=True)
    toxin_panel.to_parquet(out_panel, index=False)
    status_week.to_parquet(out_status, index=False)
    print(f"toxin panel n={len(toxin_panel)} locs={toxin_panel['location_id'].nunique()} -> {out_panel}")
    print(f"status panel n={len(status_week)} areas={status_week['parent_area_name'].nunique()} -> {out_status}")

    phyto_path = ROOT / paths["panel"]
    mhw_path = ROOT / paths["mhw"]
    phyto = _read(phyto_path) if phyto_path.exists() else None
    mhw = _read(mhw_path) if mhw_path.exists() else None

    join_doc = document_sst_join(toxin_panel, mhw, phyto)
    joined_n = None
    sst_coverage = None
    if mhw is not None and join_doc.get("sst_join_works"):
        # Restrict join to toxin locs present in MHW (same location_id space as phyto)
        m_locs = set(pd.to_numeric(mhw["location_id"], errors="coerce").dropna().astype(int))
        tp = toxin_panel[toxin_panel["location_id"].isin(m_locs)].copy()
        joined = join_week_panel(tp, mhw)
        joined.to_parquet(out_joined, index=False)
        joined_n = int(len(joined))
        sst_coverage = float(joined["sst"].notna().mean()) if "sst" in joined.columns else None
        print(f"toxin+SST joined n={joined_n} sst_cov={sst_coverage} -> {out_joined}")
    else:
        print("SST join skipped or failed:", join_doc.get("note"))

    agreement = {}
    if phyto is not None:
        agreement = dinophysis_dsp_agreement(phyto, toxin_panel)
        print("Dinophysis vs DSP:", json.dumps({k: agreement[k] for k in list(agreement)[:12]}, indent=2))

    rates = {f"exceed_{t}_rate": float(toxin_panel[f"exceed_{t}"].mean()) for t in TOXINS}
    rates["exceed_any_rate"] = float(toxin_panel["exceed_any"].mean())
    rates["closed_rate_among_matched"] = (
        float(toxin_panel.loc[toxin_panel["closed"].notna(), "closed"].mean())
        if toxin_panel["closed"].notna().any()
        else None
    )
    rates["status_match_frac"] = float((toxin_panel["status_join"] == "matched").mean())

    # Usability: DSP exceedance rate in useful range for modeling
    dsp_rate = rates["exceed_dsp_rate"]
    toxin_usable = bool(
        len(toxin_panel) >= 1000
        and toxin_panel["location_id"].nunique() >= 20
        and 0.005 <= dsp_rate <= 0.5
        and float(toxin_panel["measured_dsp"].mean()) > 0.3
    )

    summary = {
        "raw_pivot_rows": int(len(pivot)),
        "raw_long_rows": int(long_n) if long_n is not None else None,
        "raw_status_rows": int(len(status)),
        "toxin_station_weeks": int(len(toxin_panel)),
        "toxin_locations": int(toxin_panel["location_id"].nunique()),
        "status_area_weeks": int(len(status_week)),
        "status_areas": int(status_week["parent_area_name"].nunique()),
        "time_min": str(toxin_panel["week_start"].min()),
        "time_max": str(toxin_panel["week_start"].max()),
        "rates": rates,
        "toxin_target_usable": toxin_usable,
        "toxin_target_note": (
            f"DSP exceedance rate={dsp_rate:.4f}; measured_dsp={float(toxin_panel['measured_dsp'].mean()):.3f}. "
            "Usable if national coverage, non-degenerate positive rate, and DSP often measured."
        ),
        "sst_join": join_doc,
        "toxin_joined_rows": joined_n,
        "toxin_joined_sst_coverage": sst_coverage,
        "dinophysis_dsp_agreement": agreement,
        "artifacts": {
            "raw_pivot": str(raw_pivot.relative_to(ROOT)),
            "raw_long": str(raw_long.relative_to(ROOT)),
            "raw_status": str(raw_status.relative_to(ROOT)),
            "toxin_panel": str(out_panel.relative_to(ROOT)),
            "status_panel": str(out_status.relative_to(ROOT)),
            "toxin_joined": str(out_joined.relative_to(ROOT)) if joined_n else None,
        },
    }
    Path(args.summary).write_text(json.dumps(summary, indent=2, default=str))
    _write_report(Path(args.report), summary)
    print(f"summary -> {args.summary}")
    print(f"report  -> {args.report}")
    print("toxin_target_usable:", toxin_usable)


def _write_report(path: Path, s: dict) -> None:
    agr = s.get("dinophysis_dsp_agreement") or {}
    join = s.get("sst_join") or {}
    rates = s.get("rates") or {}
    lines = [
        "# National biotoxin / harvest-status ingest",
        "",
        "Source: Marine Institute ERDDAP `erddap3.marine.ie` — `habs_biotoxin`, `habs_biotoxin_pivot`, `habs_status`.",
        "Schemas verified via `info.json` before download (see `data/raw/erddap_info/`).",
        "",
        "## Ingested",
        "",
        f"| Dataset | Rows |",
        f"| --- | ---: |",
        f"| habs_biotoxin_pivot (CSV) | {s.get('raw_pivot_rows')} |",
        f"| habs_biotoxin long-form | {s.get('raw_long_rows')} |",
        f"| habs_status | {s.get('raw_status_rows')} |",
        f"| toxin station-weeks | {s.get('toxin_station_weeks')} ({s.get('toxin_locations')} locations) |",
        f"| status area-weeks | {s.get('status_area_weeks')} ({s.get('status_areas')} parent areas) |",
        f"| time span (toxin weeks) | {s.get('time_min')} → {s.get('time_max')} |",
        "",
        "## Exceedance / closed rates (station-week)",
        "",
        f"- DSP exceed: **{rates.get('exceed_dsp_rate')}**",
        f"- ASP exceed: {rates.get('exceed_asp_rate')}",
        f"- AZP exceed: {rates.get('exceed_azp_rate')}",
        f"- PSP exceed: {rates.get('exceed_psp_rate')}",
        f"- any toxin exceed: {rates.get('exceed_any_rate')}",
        f"- closed among status-matched weeks: {rates.get('closed_rate_among_matched')} "
        f"(match frac {rates.get('status_match_frac')})",
        "",
        f"**Toxin target usable:** `{s.get('toxin_target_usable')}` — {s.get('toxin_target_note')}",
        "",
        "## SST / MHW join",
        "",
        f"- Join key: `{join.get('toxin_join_key')}`",
        f"- Toxin ∩ MHW locations: **{join.get('toxin_mhw_overlap')}** / {join.get('n_toxin_locations')} toxin "
        f"(phyto overlap {join.get('toxin_phyto_overlap')})",
        f"- SST join works: `{join.get('sst_join_works')}`",
        f"- Joined toxin×SST rows: {s.get('toxin_joined_rows')} (SST coverage {s.get('toxin_joined_sst_coverage')})",
        f"- Status key caveat: {join.get('status_join_key')}",
        f"- Note: {join.get('note')}",
        "",
        "## Dinophysis cells vs DSP toxin",
        "",
    ]
    if agr.get("usable"):
        conf = agr.get("confusion") or {}
        lines += [
            f"- Overlapping station-weeks (DSP measured): **{agr.get('n_dsp_measured_overlaps')}** "
            f"({agr.get('n_shared_locations')} shared locations; location_id overlap {agr.get('location_overlap')})",
            f"- Phyto positive rate: {agr.get('phyto_positive_rate'):.4f}; DSP exceed rate: {agr.get('dsp_exceed_rate'):.4f}",
            f"- Confusion TP/FP/FN/TN: {conf.get('tp')}/{conf.get('fp')}/{conf.get('fn')}/{conf.get('tn')}",
            f"- Agreement rate: {agr.get('agreement_rate'):.3f}; Pearson(binary): {agr.get('pearson_binary')}",
            f"- Recall of DSP given phyto+: {agr.get('recall_dsp_given_phyto')}; "
            f"precision DSP: {agr.get('precision_dsp_given_phyto')}",
        ]
        if "spearman_count_vs_max_dsp" in agr:
            lines.append(
                f"- Spearman(count_dinophysis, max_dsp): {agr.get('spearman_count_vs_max_dsp'):.3f} "
                f"(Pearson {agr.get('pearson_count_vs_max_dsp')})"
            )
    else:
        lines.append(f"- Not usable / incomplete: {agr}")
    lines += ["", "Raw CSVs are gitignored under `data/raw/`. Summaries committed.", ""]
    path.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
