#!/usr/bin/env python3
"""Build June 2023 MHW × Dinophysis case-study tables, plots, and markdown.

Uses existing processed artifacts only (no network). Outputs under data/processed/.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
FIG = OUT / "figures"
THRESH = 100  # cells/L Dinophysis exceedance (panel y_dinophysis)
FOCUS_IDS = [174, 177, 179, 650, 163, 171]
D0, D1 = pd.Timestamp("2023-05-01"), pd.Timestamp("2023-08-31")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)

    crw = pd.read_csv(OUT / "crw_mhw_ireland_daily_summary.csv", parse_dates=["time"])
    crw["date"] = pd.to_datetime(crw["time"]).dt.normalize()

    panel = pd.read_parquet(OUT / "station_week_panel.parquet")
    panel["week_start"] = pd.to_datetime(panel["week_start"], utc=True).dt.tz_localize(None)

    joined = pd.read_parquet(OUT / "joined_features.parquet")
    joined["week_start"] = pd.to_datetime(joined["week_start"])

    mh = pd.read_parquet(OUT / "compass_mace_head_daily.parquet")
    mh["date"] = pd.to_datetime(mh["date"], utc=True).dt.tz_localize(None)

    sp = pd.read_parquet(OUT / "spiddal_ctd_daily.parquet")
    sp["date"] = pd.to_datetime(sp["date"], utc=True).dt.tz_localize(None)

    met = pd.read_csv(OUT / "mace_head_met_daily.csv", parse_dates=["date"])

    crw_w = crw[(crw["date"] >= D0) & (crw["date"] <= D1)][
        ["date", "n_ocean", "n_mhw", "mean_cat", "max_cat", "frac_mhw"]
    ].sort_values("date")
    met_w = met[(met["date"] >= D0) & (met["date"] <= D1)][
        ["date", "wdsp", "hm", "ddhm", "hg", "glorad", "maxtp", "mintp", "rain"]
    ]
    mh_w = mh[(mh["date"] >= D0) & (mh["date"] <= D1)][
        ["date", "temp_c", "salinity", "do_mg_l", "nitrate_umol_l", "wind_speed_ms", "air_temp_c"]
    ]
    sp_w = sp[(sp["date"] >= D0) & (sp["date"] <= D1)][
        ["date", "temp_c", "salinity", "do_mg_l", "depth_m", "n"]
    ]

    hab = panel[panel["location_id"].isin(FOCUS_IDS)].copy()
    hab = hab[(hab["week_start"] >= "2023-04-24") & (hab["week_start"] <= "2023-09-04")]
    hab = hab[
        [
            "location_id",
            "location_name",
            "latitude",
            "longitude",
            "week_start",
            "count_dinophysis",
            "y_dinophysis",
            "count_pseudo_nitzschia",
            "count_karenia_mikimotoi",
            "n_samples",
        ]
    ]
    jsub = joined[joined["location_id"].isin(FOCUS_IDS)].copy()
    jsub = jsub[(jsub["week_start"] >= "2023-04-24") & (jsub["week_start"] <= "2023-09-04")]
    jsub = jsub[
        ["location_id", "week_start", "sst", "ssta", "in_mhw", "mhw_duration", "mhw_cum_intensity"]
    ]
    hab = hab.merge(jsub, on=["location_id", "week_start"], how="left")
    hab_out = hab.sort_values(["week_start", "location_id"]).copy()
    hab_out["exceedance"] = (hab_out["count_dinophysis"] >= THRESH).astype(int)

    daily = crw_w.rename(
        columns={
            "frac_mhw": "crw_frac_mhw",
            "mean_cat": "crw_mean_cat",
            "max_cat": "crw_max_cat",
            "n_mhw": "crw_n_mhw",
            "n_ocean": "crw_n_ocean",
        }
    )
    daily = daily.merge(
        mh_w.rename(
            columns={
                "temp_c": "mace_temp_c",
                "salinity": "mace_salinity",
                "do_mg_l": "mace_do_mg_l",
                "nitrate_umol_l": "mace_nitrate_umol_l",
                "wind_speed_ms": "mace_wind_ms",
                "air_temp_c": "mace_air_temp_c",
            }
        ),
        on="date",
        how="left",
    )
    daily = daily.merge(
        sp_w.rename(
            columns={
                "temp_c": "spiddal_temp_c",
                "salinity": "spiddal_salinity",
                "do_mg_l": "spiddal_do_mg_l",
                "depth_m": "spiddal_depth_m",
                "n": "spiddal_n",
            }
        ),
        on="date",
        how="left",
    )
    daily = daily.merge(
        met_w.rename(
            columns={
                "wdsp": "met_wdsp_kt",
                "glorad": "met_glorad",
                "maxtp": "met_maxtp",
                "mintp": "met_mintp",
                "rain": "met_rain_mm",
                "hm": "met_hm",
                "ddhm": "met_ddhm",
                "hg": "met_hg",
            }
        ),
        on="date",
        how="left",
    )

    daily.to_csv(OUT / "june2023_case_study_daily.csv", index=False)
    hab_out.to_csv(OUT / "june2023_case_study_hab_weekly.csv", index=False)

    june_crw = crw_w[(crw_w.date >= "2023-06-01") & (crw_w.date <= "2023-06-30")]
    june_mh = mh_w[(mh_w.date >= "2023-06-01") & (mh_w.date <= "2023-06-30")]
    june_sp = sp_w[(sp_w.date >= "2023-06-01") & (sp_w.date <= "2023-06-30")]
    june_met = met_w[(met_w.date >= "2023-06-01") & (met_w.date <= "2023-06-30")]
    peak = june_crw.loc[june_crw["frac_mhw"].idxmax()]
    peak_cat = june_crw.loc[june_crw["mean_cat"].idxmax()]

    summary = pd.DataFrame(
        [
            {
                "metric": "crw_june_mean_frac_mhw",
                "value": round(float(june_crw.frac_mhw.mean()), 4),
                "unit": "fraction",
                "note": "Irish bbox ocean pixels CRW cat>=1",
            },
            {
                "metric": "crw_june_peak_frac_mhw",
                "value": round(float(peak.frac_mhw), 4),
                "unit": "fraction",
                "note": f"peak date {peak['date'].date()}",
            },
            {
                "metric": "crw_june_peak_mean_cat",
                "value": round(float(peak_cat.mean_cat), 3),
                "unit": "category",
                "note": f"peak mean_cat date {peak_cat['date'].date()}; 0=none … 5=beyond extreme",
            },
            {
                "metric": "crw_june_max_cat_any_day",
                "value": float(june_crw.max_cat.max()),
                "unit": "category",
                "note": "Hobday CRW category",
            },
            {
                "metric": "mace_june_mean_temp_c",
                "value": round(float(june_mh.temp_c.mean()), 3),
                "unit": "°C",
                "note": "compass_mace_head SBE",
            },
            {
                "metric": "mace_june_mean_salinity",
                "value": round(float(june_mh.salinity.mean()), 3),
                "unit": "PSU",
                "note": "",
            },
            {
                "metric": "mace_june_mean_do_mg_l",
                "value": round(float(june_mh.do_mg_l.mean()), 3),
                "unit": "mg/L",
                "note": "",
            },
            {
                "metric": "spiddal_june_mean_temp_c",
                "value": round(float(june_sp.temp_c.mean()), 3),
                "unit": "°C",
                "note": f"spiddal_obs_ctd ~20 m; n_days={len(june_sp)}",
            },
            {
                "metric": "spiddal_june_max_temp_c",
                "value": round(float(june_sp.temp_c.max()), 3),
                "unit": "°C",
                "note": "",
            },
            {
                "metric": "met_june_mean_wdsp_kt",
                "value": round(float(june_met.wdsp.mean()), 3),
                "unit": "knots",
                "note": "Met Éireann dly275 Mace Head",
            },
            {
                "metric": "met_june_mean_glorad",
                "value": round(float(june_met.glorad.mean()), 1),
                "unit": "J/cm²",
                "note": "global radiation",
            },
            {
                "metric": "dino_rosmuc_max_count",
                "value": float(hab_out.loc[hab_out.location_id == 174, "count_dinophysis"].max()),
                "unit": "cells/L",
                "note": "May–Aug 2023 station-weeks",
            },
            {
                "metric": "dino_mannin_max_count",
                "value": float(hab_out.loc[hab_out.location_id == 177, "count_dinophysis"].max()),
                "unit": "cells/L",
                "note": "",
            },
            {
                "metric": "dino_gubbaros_max_count",
                "value": float(hab_out.loc[hab_out.location_id == 179, "count_dinophysis"].max()),
                "unit": "cells/L",
                "note": "",
            },
            {
                "metric": "dino_cliffden_max_count",
                "value": float(hab_out.loc[hab_out.location_id == 650, "count_dinophysis"].max()),
                "unit": "cells/L",
                "note": "",
            },
            {
                "metric": "dino_exceedance_weeks_connemara",
                "value": int(hab_out["y_dinophysis"].sum()),
                "unit": "weeks",
                "note": f"threshold >={THRESH} cells/L",
            },
            {
                "metric": "lehanagh_coverage_starts",
                "value": 2024.0,
                "unit": "year",
                "note": "no 2023 overlap — gap",
            },
            {
                "metric": "imi_conn_roms_june2023",
                "value": 0.0,
                "unit": "available",
                "note": "archive not on public rolling ERDDAP/THREDDS",
            },
        ]
    )
    summary.to_csv(OUT / "june2023_case_study_summary.csv", index=False)

    _plot_mhw_met(crw_w, mh_w, sp_w, met_w)
    _plot_dino(hab_out)
    _plot_mace(mh_w)
    _write_md(summary, hab_out, crw_w, june_crw, june_mh, june_sp, june_met, peak, peak_cat, mh_w)
    print("Wrote case study artifacts to", OUT)


def _plot_mhw_met(crw_w, mh_w, sp_w, met_w) -> None:
    fig, axes = plt.subplots(
        3, 1, figsize=(10, 8), sharex=True, gridspec_kw={"height_ratios": [1.2, 1.0, 1.0]}
    )
    ax = axes[0]
    ax.fill_between(crw_w["date"], crw_w["frac_mhw"], alpha=0.35, color="crimson", label="CRW frac MHW")
    ax.plot(crw_w["date"], crw_w["frac_mhw"], color="crimson", lw=1.2)
    ax.plot(
        crw_w["date"],
        crw_w["mean_cat"] / 5.0,
        color="darkred",
        lw=1.0,
        ls="--",
        label="mean category / 5",
    )
    ax.axvspan(pd.Timestamp("2023-06-01"), pd.Timestamp("2023-06-30"), color="orange", alpha=0.15, label="June 2023")
    ax.set_ylabel("Fraction / scaled cat")
    ax.set_ylim(0, 1.05)
    ax.set_title("Irish bbox CRW 5km MHW Watch (May–Aug 2023)")
    ax.legend(loc="lower left", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    ax.plot(mh_w["date"], mh_w["temp_c"], color="teal", lw=1.2, label="Mace Head buoy T")
    ax.plot(sp_w["date"], sp_w["temp_c"], color="steelblue", lw=1.0, alpha=0.85, label="Spiddal CTD T (~20 m)")
    ax.plot(met_w["date"], met_w["maxtp"], color="gray", lw=0.8, alpha=0.7, label="Met Éireann max air T")
    ax.axvspan(pd.Timestamp("2023-06-01"), pd.Timestamp("2023-06-30"), color="orange", alpha=0.15)
    ax.set_ylabel("Temperature (°C)")
    ax.set_title("In-situ temperature")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[2]
    ax.plot(met_w["date"], met_w["wdsp"], color="purple", lw=1.0, label="Wind speed (kt)")
    ax2 = ax.twinx()
    ax2.plot(met_w["date"], met_w["glorad"], color="goldenrod", lw=1.0, alpha=0.8, label="Global rad.")
    ax.axvspan(pd.Timestamp("2023-06-01"), pd.Timestamp("2023-06-30"), color="orange", alpha=0.15)
    ax.set_ylabel("Wind (knots)")
    ax2.set_ylabel("Global radiation (J/cm²)")
    ax.set_title("Met Éireann Mace Head (dly275)")
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG / "june2023_mhw_met_temp.png", dpi=140)
    plt.close(fig)


def _plot_dino(hab_out) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    palette = {
        174: "#d62728",
        177: "#1f77b4",
        179: "#2ca02c",
        650: "#ff7f0e",
        163: "#9467bd",
        171: "#8c564b",
    }
    for lid, g in hab_out.groupby("location_id"):
        name = g["location_name"].iloc[0]
        ax.plot(
            g["week_start"],
            g["count_dinophysis"],
            marker="o",
            ms=5,
            lw=1.2,
            color=palette.get(lid, "gray"),
            label=f"{name} ({lid})",
        )
        exc = g[g["y_dinophysis"] == 1]
        if len(exc):
            ax.scatter(
                exc["week_start"],
                exc["count_dinophysis"],
                s=90,
                facecolors="none",
                edgecolors=palette.get(lid, "black"),
                linewidths=2,
                zorder=5,
            )
    ax.axhline(THRESH, color="black", ls=":", lw=1, label=f"exceedance ≥ {THRESH} cells/L")
    ax.axvspan(
        pd.Timestamp("2023-06-01"),
        pd.Timestamp("2023-06-30"),
        color="orange",
        alpha=0.15,
        label="June 2023 MHW peak",
    )
    ax.set_ylabel("Dinophysis (cells/L)")
    ax.set_title("Connemara HAB stations — Dinophysis counts (May–Aug 2023)")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG / "june2023_dinophysis_connemara.png", dpi=140)
    plt.close(fig)


def _plot_mace(mh_w) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
    sub = mh_w[(mh_w.date >= "2023-05-15") & (mh_w.date <= "2023-07-15")]
    axes[0].plot(sub["date"], sub["temp_c"], color="teal")
    axes[0].set_ylabel("Temp (°C)")
    axes[0].set_title("Mace Head compass buoy (mid-May → mid-Jul 2023)")
    axes[0].axvspan(pd.Timestamp("2023-06-01"), pd.Timestamp("2023-06-30"), color="orange", alpha=0.15)
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(sub["date"], sub["salinity"], color="navy")
    axes[1].set_ylabel("Salinity")
    axes[1].axvspan(pd.Timestamp("2023-06-01"), pd.Timestamp("2023-06-30"), color="orange", alpha=0.15)
    axes[1].grid(True, alpha=0.3)
    axes[2].plot(sub["date"], sub["do_mg_l"], color="darkgreen")
    axes[2].set_ylabel("DO (mg/L)")
    axes[2].axvspan(pd.Timestamp("2023-06-01"), pd.Timestamp("2023-06-30"), color="orange", alpha=0.15)
    axes[2].grid(True, alpha=0.3)
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG / "june2023_mace_head_tsdo.png", dpi=140)
    plt.close(fig)


def _write_md(summary, hab_out, crw_w, june_crw, june_mh, june_sp, june_met, peak, peak_cat, mh_w) -> None:
    def mmean(df, col, a, b):
        s = df[(df.date >= a) & (df.date <= b)][col]
        return float(s.mean()) if len(s) else float("nan")

    may_frac = mmean(crw_w, "frac_mhw", "2023-05-01", "2023-05-31")
    jul_frac = mmean(crw_w, "frac_mhw", "2023-07-01", "2023-07-31")
    aug_frac = mmean(crw_w, "frac_mhw", "2023-08-01", "2023-08-31")
    exc = hab_out[hab_out["y_dinophysis"] == 1].sort_values("week_start")

    # monthly buoy table
    months = []
    for lab, a, b in [
        ("May", "2023-05-01", "2023-05-31"),
        ("Jun", "2023-06-01", "2023-06-30"),
        ("Jul", "2023-07-01", "2023-07-31"),
        ("Aug", "2023-08-01", "2023-08-31"),
    ]:
        s = mh_w[(mh_w.date >= a) & (mh_w.date <= b)]
        months.append(
            f"| {lab} | {s.temp_c.mean():.2f} | {s.salinity.mean():.2f} | {s.do_mg_l.mean():.2f} | {len(s)} |"
        )

    exc_rows = []
    for _, r in exc.iterrows():
        sst = "—" if pd.isna(r.sst) else f"{r.sst:.2f}"
        ssta = "—" if pd.isna(r.ssta) else f"{r.ssta:.2f}"
        exc_rows.append(
            f"| {r.location_name} ({int(r.location_id)}) | {pd.Timestamp(r.week_start).date()} | "
            f"{r.count_dinophysis:.0f} | {sst} | {ssta} |"
        )

    hab_peak = (
        hab_out.groupby(["location_id", "location_name"], as_index=False)
        .agg(max_dino=("count_dinophysis", "max"), exceed=("y_dinophysis", "sum"), n=("count_dinophysis", "count"))
        .sort_values("max_dino", ascending=False)
    )
    hab_rows = [
        f"| {int(r.location_id)} | {r.location_name} | {r.n:.0f} | {r.max_dino:.0f} | {int(r.exceed)} |"
        for _, r in hab_peak.iterrows()
    ]

    md = f"""# June 2023 marine heatwave × Dinophysis — Connemara case study

Generated: **2026-09-01** (Europe/Dublin). Rebuild: `python scripts/build_june2023_case_study.py`.

Hackathon / paper narrative link to **Berthou et al. (2024)** — *Exceptional atmospheric conditions in June 2023 generated a northwest European marine heatwave which contributed to breaking land temperature records* (Commun Earth Environ 5:287; https://doi.org/10.1038/s43247-024-01413-8). That study describes an unprecedented ~16-day category-II Northwest European shelf MHW in June 2023 (local SST anomalies up to ~5 °C north of Ireland), forced by anticyclonic weather (weak winds, high solar radiation, tropical air) with shallow-ocean feedbacks.

This case study places **Irish-bbox CRW MHW categories**, **Connemara HAB Dinophysis**, **Mace Head / Spiddal in-situ T–S–DO**, and **Met Éireann Mace Head wind/radiation** on a common May–Aug 2023 timeline. It is **descriptive**, not a causal attribution of Dinophysis blooms to the MHW.

## Key numbers (June 2023)

| Metric | Value | Notes |
| --- | ---: | --- |
| CRW mean ocean frac in MHW | {float(june_crw.frac_mhw.mean()):.3f} | Irish bbox 51–56°N, 11–5°W |
| CRW peak frac_mhw | {float(peak.frac_mhw):.3f} on {peak['date'].date()} | also 1.000 on 2023-06-20 |
| CRW peak mean category | {float(peak_cat.mean_cat):.2f} on {peak_cat['date'].date()} | max_cat reached **5** many June days |
| Mace Head buoy mean T | {float(june_mh.temp_c.mean()):.2f} °C | salinity {float(june_mh.salinity.mean()):.2f}, DO {float(june_mh.do_mg_l.mean()):.2f} mg/L |
| Spiddal CTD mean / max T | {float(june_sp.temp_c.mean()):.2f} / {float(june_sp.temp_c.max()):.2f} °C | ~20 m; early→late June warm-up |
| Met Éireann mean wind / glorad | {float(june_met.wdsp.mean()):.1f} kt / {float(june_met.glorad.mean()):.0f} J/cm² | station dly275 Mace Head |
| Dinophysis exceedance weeks (≥{THRESH} cells/L) | {int(hab_out.y_dinophysis.sum())} | Rosmuc + Mannin in focus set |

Compact machine-readable summary: `data/processed/june2023_case_study_summary.csv`.

## Honest gaps

| Gap | Status | Impact on narrative |
| --- | --- | --- |
| **IMI Connemara ROMS (`IMI_CONN_3D`)** June 2023 archive | **Missing** on public rolling ERDDAP/THREDDS (only ~last 8–30 days online). Paths noted in `data/raw/imi_conn/thredds_archive_paths.json`. | No high-res 3-D hydro / stratification for the event week. |
| **Lehanagh Pool sentinel** | NRT starts **2024-05-27** — **no June 2023** overlap. | No Chl / turbidity / EXO2 for the event; cannot use Lehanagh DO–Chl story here. |
| **SmartBay SBE16** (`smartbay_obs_ctd_sbe16`) | Coverage ends **2023-05-08**. | No June QC CTD+O₂; use `spiddal_obs_ctd` NRT instead (T/S only; DO missing). |
| **Chlorophyll at Mace Head / Spiddal** | Not in these daily products for May–Aug 2023. | HAB–chl coupling not shown in situ. |
| **Rosmuc OISST join** | `sst` always NaN (coastal landmask / point off-ocean in 0.25° OISST). | Use Mannin / Gubbaros / Cliffden Outer for OISST MHW flags; Rosmuc HAB-only. |
| **Causal claim** | Not made. | Two exceedance weeks bookend / follow the peak; sample size tiny. |

## Timeline (May–Aug 2023)

### 1. CRW Marine Heatwave Watch (Irish bbox)

NOAA Coral Reef Watch Daily Global 5 km MHW Watch v1.0.1 (Hobday categories on CoralTemp). Categories: 0 = no MHW … 5 = beyond extreme. Source summary: `crw_mhw_ireland_daily_summary.csv` (1096 days 2022–2024; June 2023 complete).

| Month | Mean frac_mhw | Mean of daily mean_cat | Max cat observed |
| --- | ---: | ---: | ---: |
| May 2023 | {may_frac:.3f} | {mmean(crw_w,'mean_cat','2023-05-01','2023-05-31'):.2f} | {int(crw_w[(crw_w.date>='2023-05-01')&(crw_w.date<='2023-05-31')].max_cat.max())} |
| **June 2023** | **{float(june_crw.frac_mhw.mean()):.3f}** | **{float(june_crw.mean_cat.mean()):.2f}** | **{int(june_crw.max_cat.max())}** |
| July 2023 | {jul_frac:.3f} | {mmean(crw_w,'mean_cat','2023-07-01','2023-07-31'):.2f} | {int(crw_w[(crw_w.date>='2023-07-01')&(crw_w.date<='2023-07-31')].max_cat.max())} |
| August 2023 | {aug_frac:.3f} | {mmean(crw_w,'mean_cat','2023-08-01','2023-08-31'):.2f} | {int(crw_w[(crw_w.date>='2023-08-01')&(crw_w.date<='2023-08-31')].max_cat.max())} |

Narrative beats consistent with Berthou et al. (rapid mid-June intensification on the NW European shelf):

- **Late May build-up:** frac_mhw rises from ~0.59 (May mean) to **0.97 on 31 May**.
- **June plateau:** mean frac_mhw **0.96**; **19–20 June** hit frac_mhw = **1.00** with mean_cat **2.64–2.77** and max_cat **5**.
- **Early July decay:** frac_mhw falls from ~0.91 (1 Jul) toward ~0.55 by 7 Jul; August mean ~0.28.

OISST station-week flags (strong Irish panel `joined_features.parquet`) at **Mannin (177)** show `in_mhw=1` from the week of **2023-05-22** through **2023-06-26**, with `ssta` peaking ~**+2.6 °C** (week of 12 Jun) and `mhw_duration` reaching **37 days** by 26 Jun — then clear by early July. Same pattern at Gubbaros / Cliffden Outer.

### 2. Atmosphere — Met Éireann Mace Head (`dly275`)

June mean wind **{float(june_met.wdsp.mean()):.1f} kt**, mean global radiation **{float(june_met.glorad.mean()):.0f} J/cm²**. Aligns qualitatively with Berthou’s “weak winds + high sunshine” forcing story (not a re-analysis of their weather regimes). Daily series in `june2023_case_study_daily.csv` (`met_wdsp_kt`, `met_glorad`, `met_maxtp`, …).

### 3. In-situ hydrography

**Mace Head** `compass_mace_head` daily (full May–Aug coverage):

| Month | Mean T (°C) | Mean S | Mean DO (mg/L) | Days |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(months)}

June buoy T (~16 °C) is warmer than May by ~3.4 °C; DO declines through summer.

**SmartBay Spiddal** `spiddal_obs_ctd` (~20 m): **30/30 June days**. Mean T **{float(june_sp.temp_c.mean()):.2f} °C**, but strongly stratified in time — early June ~10.2 °C → late June ~17.3 °C, max **{float(june_sp.temp_c.max()):.2f} °C on {june_sp.loc[june_sp.temp_c.idxmax(),'date'].date()}**. DO column empty in this NRT daily product. July–Aug Spiddal coverage is sparse (only a few days).

### 4. Dinophysis — Connemara HAB stations

Stations chosen from `local_sites_report.md` nearest-to-sentinel demo set (Mannin, Rosmuc, Gubbaros, Cliffden Outer) plus nearby Ballynakill / Killary Inner. Exceedance label `y_dinophysis` = count ≥ **{THRESH} cells/L**.

| location_id | name | weeks (Apr 24–Sep 4) | max Dinophysis | exceedance weeks |
| ---: | --- | ---: | ---: | ---: |
{chr(10).join(hab_rows)}

**Exceedance events in window:**

| Station | week_start | count (cells/L) | OISST SST | SSTA |
| --- | --- | ---: | ---: | ---: |
{chr(10).join(exc_rows) if exc_rows else "| — | — | — | — | — |"}

Reading for the paper narrative (cautious):

1. **Rosmuc** spikes to **320 cells/L** in the week of **29 May** — as CRW frac_mhw is already >0.9 and OISST MHWs are lighting up outer Connemara stations (Rosmuc itself has no OISST SST).
2. During the **peak CRW June** weeks, Connemara Dinophysis counts in this set stay **low** (0–40 cells/L).
3. **Mannin** exceeds at **120 cells/L** in the week of **10 Jul**, after CRW Irish-bbox MHW fraction has begun decaying and OISST `in_mhw` has cleared at Mannin — consistent with a lagged / transport-mediated HAB response hypothesis, **not proven** here.
4. Gubbaros / Cliffden Outer peak at **80 cells/L** (below threshold) in May–Aug 2023.

## Artifacts

| File | Contents |
| --- | --- |
| `data/processed/june2023_case_study.md` | This narrative |
| `data/processed/june2023_case_study_summary.csv` | One-row-per-metric plot/paper table |
| `data/processed/june2023_case_study_daily.csv` | May–Aug daily CRW + Mace + Spiddal + Met join |
| `data/processed/june2023_case_study_hab_weekly.csv` | Focus-station Dinophysis + OISST MHW flags |
| `data/processed/figures/june2023_mhw_met_temp.png` | CRW frac / temps / Met wind+radiation |
| `data/processed/figures/june2023_dinophysis_connemara.png` | Dinophysis time series |
| `data/processed/figures/june2023_mace_head_tsdo.png` | Mace Head T / S / DO around June |

## Sources (existing repo artifacts)

- CRW: `crw_mhw_ireland_daily_summary.csv`, `crw_mhw_ireland_daily.parquet` (scout P0 ingest)
- Irish HAB panel + OISST-strong join: `station_week_panel.parquet`, `joined_features.parquet`
- Mace Head buoy: `compass_mace_head_daily.parquet` (`local_sites_report.md`)
- Spiddal CTD: `spiddal_ctd_daily.parquet`
- Met Éireann: `mace_head_met_daily.csv` (clidata `dly275`)
- Station selection rationale: `local_sites_report.md` (Mannin 177, Rosmuc 174, Cliffden Outer 650, Gubbaros 179)

## How to use in the hackathon story

1. Open with Berthou et al. 2024 shelf-wide June 2023 MHW → zoom to Irish CRW frac_mhw = 1.0 mid-June.
2. Show Met Éireann weakish June winds + radiation and Mace Head / Spiddal warming.
3. Overlay Connemara Dinophysis: pre-peak Rosmuc exceedance, quiet peak June, post-peak Mannin exceedance.
4. Call out gaps (CONN ROMS archive, Lehanagh 2024+, no Chl) as future data asks — not as silent omissions.
"""
    (OUT / "june2023_case_study.md").write_text(md)
    print("Wrote", OUT / "june2023_case_study.md")


if __name__ == "__main__":
    main()
