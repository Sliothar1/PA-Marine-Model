#!/usr/bin/env python3
"""Download Connemara sentinel buoys, find nearby HAB stations, optional DO/Chl joins."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from pa_marine.config import load_config
from pa_marine.sentinel import (
    BUOY_SITES,
    correlate_signal,
    ingest_site,
    join_buoy_to_hab_weeks,
    nearest_hab_stations,
    week_aggregate_from_daily,
)

ROOT = Path(__file__).resolve().parents[1]


def _fmt_table(df: pd.DataFrame, cols: list[str], n: int = 12) -> str:
    if df.empty:
        return "_(none)_"
    show = df[cols].head(n).copy()
    if "dist_km" in show.columns:
        show["dist_km"] = show["dist_km"].map(lambda x: f"{x:.1f}")
    try:
        return show.to_markdown(index=False)
    except ImportError:
        headers = list(show.columns)
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        for _, row in show.iterrows():
            lines.append("| " + " | ".join(str(row[h]) for h in headers) + " |")
        return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--skip-download", action="store_true")
    p.add_argument("--t1", default="2026-08-31", help="Inclusive end date for NRT pulls")
    p.add_argument("--max-km", type=float, default=30.0)
    p.add_argument("--report", default=str(ROOT / "data/processed/local_sites_report.md"))
    p.add_argument("--summary", default=str(ROOT / "data/processed/local_sites_summary.json"))
    args = p.parse_args()

    cfg = load_config(args.config)
    raw_dir = ROOT / "data/raw/sentinel"
    proc_dir = ROOT / "data/processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)

    panel_path = ROOT / cfg["paths"]["panel"]
    panel = pd.read_parquet(panel_path)

    results = {}
    for key, min_year in [("mace_head", 2018), ("lehanagh", 2024)]:
        info = ingest_site(key, raw_dir, t1=args.t1, skip_download=args.skip_download)
        # ensure week parquet under processed with clean path
        week = info["week"]
        week_path = proc_dir / f"{info['dataset_id']}_week.parquet"
        week.to_parquet(week_path, index=False)
        daily_proc = proc_dir / f"{info['dataset_id']}_daily.parquet"
        info["daily"].to_parquet(daily_proc, index=False)
        info["week_parquet"] = str(week_path)
        info["daily_processed"] = str(daily_proc)

        near = nearest_hab_stations(panel, info["lat"], info["lon"], max_km=args.max_km, min_year=min_year)
        near_path = proc_dir / f"nearest_hab_{key}.csv"
        near.to_csv(near_path, index=False)

        # Prefer overlapping stations within 30 km for join (fallback: closest with any overlap).
        candidates = near[near.get("overlap_years", True) == True] if "overlap_years" in near.columns else near
        if candidates.empty:
            candidates = near
        # take up to 8 nearest overlapping
        join_ids = candidates.head(8)["location_id"].tolist()

        # signal columns
        if key == "mace_head":
            buoy_cols = ["temp_c", "salinity", "do_mg_l", "nitrate_umol_l", "ph_sami", "pco2_uatm", "wind_speed_ms"]
            x_focus = ["do_mg_l", "nitrate_umol_l", "temp_c", "salinity"]
        else:
            buoy_cols = [
                "temp_c",
                "salinity",
                "do_mg_l",
                "chl_ug_l",
                "phycoerythrin",
                "turbidity_ntu",
                "exo_do_sat_pct",
                "wind_speed_ms",
            ]
            x_focus = ["do_mg_l", "chl_ug_l", "phycoerythrin", "temp_c", "turbidity_ntu"]

        y_cols = [
            "count_dinophysis",
            "count_pseudo_nitzschia",
            "count_karenia_mikimotoi",
            "y_dinophysis",
            "y_dinophysis_nowcast",
        ]
        joined = join_buoy_to_hab_weeks(week, panel, join_ids, buoy_cols, min_year=min_year)
        joined_path = proc_dir / f"buoy_hab_join_{key}.parquet"
        if not joined.empty:
            joined.to_parquet(joined_path, index=False)
        corr = correlate_signal(joined, x_focus, y_cols) if not joined.empty else pd.DataFrame()
        corr_path = proc_dir / f"buoy_hab_corr_{key}.csv"
        if not corr.empty:
            corr.to_csv(corr_path, index=False)

        # drop heavy frames from JSON summary
        slim = {k: v for k, v in info.items() if k not in ("daily", "week")}
        slim.update(
            {
                "min_year_for_join": min_year,
                "nearest_csv": str(near_path),
                "n_near_30km": int(len(near)),
                "n_near_overlap": int(len(candidates)),
                "join_location_ids": join_ids,
                "n_joined_station_weeks": int(len(joined)),
                "corr_csv": str(corr_path) if not corr.empty else None,
                "joined_parquet": str(joined_path) if not joined.empty else None,
                "nearest": near.head(15).to_dict(orient="records"),
                "correlations": corr.to_dict(orient="records") if not corr.empty else [],
            }
        )
        results[key] = slim
        print(
            f"{key}: rows={slim['n_rows']} days={slim['n_days']} near30={slim['n_near_30km']} "
            f"joined={slim['n_joined_station_weeks']}"
        )

    # Write markdown report
    report_lines = []
    report_lines.append("# Local Connemara sentinel sites")
    report_lines.append("")
    report_lines.append("Hackathon add-on: Marine Institute sentinel buoys near Connemara HAB stations.")
    report_lines.append("")
    report_lines.append("Schemas verified **2026-09-01** via `info.json` + small `tabledap` CSV probes on")
    report_lines.append("`https://erddap.marine.ie/erddap`. NRT feeds are **raw** (not fully QC'd).")
    report_lines.append("")
    report_lines.append("## Dataset IDs")
    report_lines.append("")
    report_lines.append("| Site | NRT dataset | QC / delayed | Lat, Lon | Coverage (info.json / pull) |")
    report_lines.append("| --- | --- | --- | --- | --- |")
    m = results["mace_head"]
    l = results["lehanagh"]
    qc = m.get("qc") or {}
    report_lines.append(
        f"| Mace Head | `compass_mace_head` | `sbe37_macehead` (SBE37 T/S/O₂, ~2018-06→2022-03) | "
        f"{m['lat']}, {m['lon']} | NRT pull {m['t_min']} → {m['t_max']} ({m['n_rows']} rows, {m['n_days']} days) |"
    )
    report_lines.append(
        f"| Lehanagh Pool | `sentinel_lehanagh` | _(none published)_ | "
        f"{l['lat']}, {l['lon']} | NRT pull {l['t_min']} → {l['t_max']} ({l['n_rows']} rows, {l['n_days']} days) |"
    )
    report_lines.append("")
    report_lines.append("### Variables of interest (verified column names)")
    report_lines.append("")
    report_lines.append("**Mace Head (`compass_mace_head`):** `sbe_temp_avg`, `sbe_salinity_avg`, `sbe_do_avg`,")
    report_lines.append("`suna_nitrate_conc_avg`, `sami_ph_avg` / `seafet_ph_ext_avg`, `contros_pco2_avg`,")
    report_lines.append("`wind_speed`, `wind_direction`, `wind_gust`.")
    report_lines.append("")
    report_lines.append("**Lehanagh (`sentinel_lehanagh`):** `SBE_Temp_Avg`, `SBE_Salinity_Avg`, `SBE_DO_Avg`,")
    report_lines.append("`EXO2_Chlorophyll_ug`, `EXO2_Phycoerythrin`, `EXO2_Turbidity`, `EXO2_RDO_Saturation`,")
    report_lines.append("`Wind_Speed`, … (EXO2 sonde + SBE CTD + met).")
    report_lines.append("")
    report_lines.append("Raw CSVs: `data/raw/sentinel/`. Daily + ISO-week aggregates: `data/processed/*_{daily,week}.parquet`.")
    report_lines.append("")

    for key, min_year, title in [
        ("mace_head", 2018, "Mace Head — nearest Irish `habs_phyto` stations"),
        ("lehanagh", 2024, "Lehanagh Pool — nearest Irish `habs_phyto` stations"),
    ]:
        r = results[key]
        near = pd.DataFrame(r["nearest"])
        report_lines.append(f"## {title}")
        report_lines.append("")
        report_lines.append(f"Within ~{args.max_km:.0f} km of buoy; flag stations with `year_max >= {min_year}` for join.")
        report_lines.append("")
        cols = ["location_id", "location_name", "latitude", "longitude", "dist_km", "n_weeks", "year_min", "year_max"]
        if "overlap_years" in near.columns:
            cols.append("overlap_years")
        report_lines.append(_fmt_table(near, [c for c in cols if c in near.columns], n=15))
        report_lines.append("")
        if "overlap_years" in near.columns:
            active = near[near["overlap_years"] == True].sort_values("dist_km")
            report_lines.append(f"### Active stations with year_max ≥ {min_year} (demo join set)")
            report_lines.append("")
            report_lines.append(_fmt_table(active, [c for c in cols if c in active.columns], n=12))
            report_lines.append("")
        report_lines.append(
            f"**Join set (up to 8 nearest with overlap):** `{r['join_location_ids']}` → "
            f"{r['n_joined_station_weeks']} station-weeks from {min_year}+."
        )
        report_lines.append("")
        corr = pd.DataFrame(r["correlations"])
        report_lines.append("### Optional buoy ↔ HAB correlation (station-weeks)")
        report_lines.append("")
        if corr.empty:
            report_lines.append("_No overlapping station-weeks with non-null buoy + HAB pairs._")
        else:
            report_lines.append(
                "Pearson *r* between weekly buoy means and HAB counts / Dinophysis labels "
                "(even tiny |r| is reported)."
            )
            report_lines.append("")
            cshow = corr.copy()
            if "pearson_r" in cshow.columns:
                cshow["pearson_r"] = cshow["pearson_r"].map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
            report_lines.append(_fmt_table(cshow, list(cshow.columns), n=max(len(cshow), 1)))
            # highlight DO/Chl
            focus = corr[corr["x"].isin(["do_mg_l", "chl_ug_l"])].dropna(subset=["pearson_r"])
            if not focus.empty:
                best = focus.reindex(focus["pearson_r"].abs().sort_values(ascending=False).index).head(3)
                bits = [
                    f"{row.x} vs {row.y}: r={row.pearson_r:.3f} (n={int(row.n)})"
                    for row in best.itertuples()
                ]
                report_lines.append("")
                report_lines.append("**DO/Chl signal note:** " + "; ".join(bits) + ".")
            else:
                report_lines.append("")
                report_lines.append(
                    "**DO/Chl signal note:** insufficient non-null pairs for DO/Chl (EXO Chl often sparse/NaN in NRT)."
                )
        report_lines.append("")

    report_lines.append("## How to demo")
    report_lines.append("")
    report_lines.append("```bash")
    report_lines.append("# re-download + rebuild report")
    report_lines.append("python scripts/ingest_sentinel_sites.py")
    report_lines.append("# or reuse raw CSVs")
    report_lines.append("python scripts/ingest_sentinel_sites.py --skip-download")
    report_lines.append("```")
    report_lines.append("")
    report_lines.append("1. Show `data/processed/local_sites_report.md` (this file) + nearest-station tables.")
    report_lines.append("2. Plot daily DO / temp from `data/processed/compass_mace_head_daily.parquet`")
    report_lines.append("   and Chl / turbidity from `sentinel_lehanagh_daily.parquet`.")
    report_lines.append("3. Overlay Dinophysis station-weeks for Mannin (`177`), Rosmuc (`174`),")
    report_lines.append("   Cliffden Outer (`650`), Gubbaros (`179`) — closest active sites with 2018+/2024+ overlap.")
    report_lines.append("4. QC contrast: delayed-mode `sbe37_macehead` (flags) vs NRT `compass_mace_head`.")
    report_lines.append("5. Live ERDDAP graphs:")
    report_lines.append("   - https://erddap.marine.ie/erddap/tabledap/compass_mace_head.graph")
    report_lines.append("   - https://erddap.marine.ie/erddap/tabledap/sentinel_lehanagh.graph")
    report_lines.append("")
    report_lines.append("Ingest code: `src/pa_marine/sentinel.py`, `scripts/ingest_sentinel_sites.py`.")
    report_lines.append("")

    report_path = Path(args.report)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    summary_path = Path(args.summary)
    # JSON-safe
    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_clean(v) for v in o]
        if isinstance(o, (pd.Timestamp,)):
            return str(o)
        if hasattr(o, "item"):
            try:
                return o.item()
            except Exception:
                return str(o)
        return o

    summary_path.write_text(json.dumps(_clean(results), indent=2, default=str), encoding="utf-8")
    print(f"wrote {report_path}")
    print(f"wrote {summary_path}")


if __name__ == "__main__":
    main()
