#!/usr/bin/env python3
"""Automated MHW × HAB situational brief for Irish shelf heatwaves.

Product question: "Will this heatwave matter for HABs?"

Reads existing processed artifacts (no network) and writes:
  data/processed/briefs/mhw_hab_brief_YYYY-MM-DD.md
  data/processed/briefs/mhw_hab_brief_YYYY-MM-DD.txt

Default date window is June 2023 (flagship Berthou shelf MHW). Use --latest
for the most recent ~30 days of CRW Irish-bbox coverage, or --start/--end.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
BRIEF_DIR = PROC / "briefs"
THRESH = 100  # cells/L Dinophysis exceedance
FOCUS_IDS = [174, 177, 179, 650, 163, 171]  # Connemara focus (case study)
FOCUS_NAMES = {
    174: "Rosmuc",
    177: "Mannin",
    179: "Gubbaros",
    650: "Cliffden Outer",
    163: "Ballynakill",
    171: "Killary Harbour Inner",
}
CORRIB_STN = 30061  # Wolfe Tone Br
OWEN_STN = 31075  # Shannagurraun
CLIM_YEARS = range(2015, 2025)
IRISH_BBOX = "51–56°N, 11–5°W"
TZ = ZoneInfo("Europe/Dublin")


def _now_local() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M %Z")


def _pct(x: float | None, digits: int = 1) -> str:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "—"
    return f"{100.0 * float(x):.{digits}f}%"


def _f(x: float | None, digits: int = 2) -> str:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "—"
    return f"{float(x):.{digits}f}"


def _load_crw() -> pd.DataFrame:
    csv = PROC / "crw_mhw_ireland_daily_summary.csv"
    pq = PROC / "crw_mhw_ireland_daily_summary.parquet"
    if csv.exists():
        df = pd.read_csv(csv, parse_dates=["time"])
    elif pq.exists():
        df = pd.read_parquet(pq)
        df["time"] = pd.to_datetime(df["time"])
    else:
        raise FileNotFoundError(
            "Missing CRW summary: crw_mhw_ireland_daily_summary.csv / .parquet"
        )
    df["date"] = pd.to_datetime(df["time"]).dt.tz_localize(None).dt.normalize()
    return df.sort_values("date")


def _resolve_window(args: argparse.Namespace, crw: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    if args.latest:
        end = pd.Timestamp(crw["date"].max())
        start = end - pd.Timedelta(days=max(args.latest_days - 1, 0))
        return start.normalize(), end.normalize()
    if args.start or args.end:
        start = pd.Timestamp(args.start or "2023-06-01")
        end = pd.Timestamp(args.end or args.start or "2023-06-30")
        if end < start:
            raise SystemExit("--end must be on or after --start")
        return start.normalize(), end.normalize()
    # Flagship default: June 2023
    return pd.Timestamp("2023-06-01"), pd.Timestamp("2023-06-30")


def _iso_weeks_covering(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[int, int]]:
    """ISO (year, week) pairs that overlap [start, end] inclusive."""
    days = pd.date_range(start, end, freq="D")
    pairs = {(int(d.isocalendar().year), int(d.isocalendar().week)) for d in days}
    return sorted(pairs)


@dataclass
class Section:
    available: bool
    title: str
    bullets: list[str] = field(default_factory=list)
    plain: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    missing_note: str = ""


def summarise_crw(crw: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> Section:
    sub = crw[(crw["date"] >= start) & (crw["date"] <= end)].copy()
    if sub.empty:
        return Section(
            False,
            "Shelf marine heatwave (CRW)",
            missing_note="No CRW rows in this window.",
        )
    mean_frac = float(sub["frac_mhw"].mean())
    peak_frac = float(sub["frac_mhw"].max())
    peak_frac_date = pd.Timestamp(sub.loc[sub["frac_mhw"].idxmax(), "date"]).date()
    peak_mean_cat = float(sub["mean_cat"].max())
    peak_mean_cat_date = pd.Timestamp(sub.loc[sub["mean_cat"].idxmax(), "date"]).date()
    max_cat = float(sub["max_cat"].max())
    days_full = int((sub["frac_mhw"] >= 0.99).sum())
    days_cat3 = int((sub["max_cat"] >= 3).sum())
    days = len(sub)

    # Severity band for industry language
    if mean_frac >= 0.75 and max_cat >= 4:
        band = "severe shelf-wide MHW"
    elif mean_frac >= 0.5 or max_cat >= 3:
        band = "moderate-to-strong shelf MHW"
    elif mean_frac >= 0.25:
        band = "elevated MHW footprint"
    else:
        band = "limited / patchy MHW footprint"

    bullets = [
        f"Irish bbox ({IRISH_BBOX}) CRW Daily Global 5 km MHW Watch — **{days}** days in window.",
        f"Mean ocean fraction in MHW (cat ≥ 1): **{_f(mean_frac, 3)}** ({_pct(mean_frac)} of ocean pixels).",
        f"Peak frac_mhw: **{_f(peak_frac, 3)}** on **{peak_frac_date}**"
        + (f" ({days_full} day(s) ≥ 0.99)" if days_full else "")
        + ".",
        f"Peak daily mean category: **{_f(peak_mean_cat, 2)}** on **{peak_mean_cat_date}**; "
        f"max category observed: **{int(max_cat)}** (0 = none … 5 = beyond extreme).",
        f"Days with any pixel ≥ cat 3: **{days_cat3}** / {days}.",
        f"Plain-language severity: **{band}**.",
    ]
    plain = [
        f"Over {start.date()} to {end.date()}, on average {_pct(mean_frac)} of Irish-shelf ocean "
        f"pixels were in a marine heatwave (NOAA Coral Reef Watch).",
        f"The hottest footprint day was {peak_frac_date} "
        f"(frac_mhw {_f(peak_frac, 3)}; peak mean category {_f(peak_mean_cat, 2)} on {peak_mean_cat_date}; "
        f"max category {int(max_cat)}).",
        f"Industry read: this window looks like a {band}.",
    ]
    table = (
        "| Metric | Value |\n| --- | ---: |\n"
        f"| Days in window | {days} |\n"
        f"| Mean frac_mhw | {_f(mean_frac, 3)} |\n"
        f"| Peak frac_mhw | {_f(peak_frac, 3)} ({peak_frac_date}) |\n"
        f"| Peak mean_cat | {_f(peak_mean_cat, 2)} ({peak_mean_cat_date}) |\n"
        f"| Max cat | {int(max_cat)} |\n"
        f"| Days max_cat ≥ 3 | {days_cat3} |\n"
    )
    return Section(True, "Shelf marine heatwave (CRW)", bullets, plain, [table])


def summarise_dinophysis(start: pd.Timestamp, end: pd.Timestamp) -> Section:
    path = PROC / "station_week_panel.parquet"
    if not path.exists():
        return Section(
            False,
            "Dinophysis exceedance (national + Connemara)",
            missing_note="station_week_panel.parquet not found.",
        )
    sw = pd.read_parquet(path)
    sw["week_start"] = pd.to_datetime(sw["week_start"]).dt.tz_localize(None).dt.normalize()
    weeks = _iso_weeks_covering(start, end)
    if not weeks:
        return Section(False, "Dinophysis exceedance (national + Connemara)", missing_note="Empty week set.")

    mask = pd.Series(False, index=sw.index)
    for y, w in weeks:
        mask |= (sw["iso_year"] == y) & (sw["iso_week"] == w)
    sub = sw.loc[mask].copy()
    if sub.empty:
        return Section(
            False,
            "Dinophysis exceedance (national + Connemara)",
            missing_note="No HAB station-weeks overlapping this window.",
        )

    # Climatology: same ISO week numbers in CLIM_YEARS, excluding the event week pairs
    week_nums = sorted({w for _, w in weeks})
    week_set = set(weeks)
    clim = sw[sw["iso_week"].isin(week_nums) & sw["iso_year"].isin(CLIM_YEARS)].copy()
    clim = clim[
        ~clim.apply(lambda r: (int(r["iso_year"]), int(r["iso_week"])) in week_set, axis=1)
    ]

    nat_rate = float(sub["y_dinophysis"].mean())
    nat_n = int(len(sub))
    nat_pos = int(sub["y_dinophysis"].sum())
    clim_nat = float(clim["y_dinophysis"].mean()) if len(clim) else float("nan")

    foc = sub[sub["location_id"].isin(FOCUS_IDS)]
    foc_rate = float(foc["y_dinophysis"].mean()) if len(foc) else float("nan")
    foc_n = int(len(foc))
    foc_pos = int(foc["y_dinophysis"].sum()) if len(foc) else 0
    clim_foc = clim[clim["location_id"].isin(FOCUS_IDS)]
    clim_foc_rate = float(clim_foc["y_dinophysis"].mean()) if len(clim_foc) else float("nan")

    events = foc[foc["y_dinophysis"] == 1][
        ["location_id", "location_name", "week_start", "count_dinophysis"]
    ].sort_values("week_start")

    bullets = [
        f"Threshold: Dinophysis ≥ **{THRESH} cells/L** (`y_dinophysis`). ISO weeks overlapping window: "
        + ", ".join(f"{y}-W{w:02d}" for y, w in weeks)
        + ".",
        f"National: **{_pct(nat_rate)}** of station-weeks exceeded ({nat_pos}/{nat_n})"
        + (f"; same-week climatology {CLIM_YEARS.start}–{CLIM_YEARS.stop - 1} excl. event: **{_pct(clim_nat)}**." if len(clim) else "."),
        f"Connemara focus ({', '.join(FOCUS_NAMES[i] for i in FOCUS_IDS if i in set(foc['location_id']))}): "
        f"**{_pct(foc_rate)}** exceeded ({foc_pos}/{foc_n})"
        + (f"; clim **{_pct(clim_foc_rate)}**." if len(clim_foc) else "."),
    ]
    if len(events):
        bullets.append("Focus-set exceedance weeks:")
        for _, r in events.iterrows():
            bullets.append(
                f"  - {r['location_name']} ({int(r['location_id'])}): week of "
                f"{pd.Timestamp(r['week_start']).date()} — {int(r['count_dinophysis'])} cells/L"
            )
    else:
        bullets.append("No Dinophysis exceedance weeks in the Connemara focus set during overlapping ISO weeks.")

    # Interpretation vs clim
    if not np.isnan(clim_nat) and clim_nat > 0:
        if nat_rate > clim_nat * 1.25:
            read = "National exceedance rate is above the same-week climatology — elevated HAB vigilance is warranted."
        elif nat_rate < clim_nat * 0.75:
            read = (
                "National exceedance rate is below the same-week climatology — a strong shelf MHW does not "
                "automatically mean a national Dinophysis spike in this window."
            )
        else:
            read = "National exceedance rate is near the same-week climatology."
    else:
        read = "Compare against local monitoring; climatology comparison limited."

    plain = [
        f"Across Irish HAB stations, {_pct(nat_rate)} of station-weeks in this window had Dinophysis "
        f"at or above {THRESH} cells/L ({nat_pos} of {nat_n}).",
        f"In the Connemara focus set the rate was {_pct(foc_rate)} ({foc_pos} of {foc_n}).",
        read,
    ]
    if len(events):
        for _, r in events.iterrows():
            plain.append(
                f"Noted exceedance: {r['location_name']} in the week of "
                f"{pd.Timestamp(r['week_start']).date()} ({int(r['count_dinophysis'])} cells/L)."
            )

    table = (
        "| Scope | Station-weeks | Exceedances | Rate | Clim rate |\n"
        "| --- | ---: | ---: | ---: | ---: |\n"
        f"| National | {nat_n} | {nat_pos} | {_pct(nat_rate)} | {_pct(clim_nat)} |\n"
        f"| Connemara focus | {foc_n} | {foc_pos} | {_pct(foc_rate)} | {_pct(clim_foc_rate)} |\n"
    )
    return Section(True, "Dinophysis exceedance (national + Connemara)", bullets, plain, [table])


def summarise_closure(start: pd.Timestamp, end: pd.Timestamp) -> Section:
    status_path = PROC / "status_area_week_panel.parquet"
    toxin_path = PROC / "toxin_station_week_panel.parquet"
    metrics_path = PROC / "dsp_closure_risk_metrics.json"
    report_path = PROC / "dsp_closure_risk_report.md"

    if not status_path.exists() and not metrics_path.exists():
        return Section(
            False,
            "Closure / DSP risk context",
            missing_note="No status_area_week_panel.parquet or dsp_closure_risk_metrics.json.",
        )

    weeks = _iso_weeks_covering(start, end)
    bullets: list[str] = []
    plain: list[str] = []
    tables: list[str] = []

    if status_path.exists():
        st = pd.read_parquet(status_path)
        st["week_start"] = pd.to_datetime(st["week_start"]).dt.tz_localize(None)
        mask = pd.Series(False, index=st.index)
        for y, w in weeks:
            mask |= (st["iso_year"] == y) & (st["iso_week"] == w)
        sub = st.loc[mask]
        week_nums = sorted({w for _, w in weeks})
        event_years = {y for y, _ in weeks}
        clim = st[st["iso_week"].isin(week_nums) & st["iso_year"].isin(CLIM_YEARS)]
        clim = clim[~clim["iso_year"].isin(event_years)]

        if len(sub):
            rate = float(sub["closed"].mean())
            n_closed = int(sub["closed"].sum())
            n = int(len(sub))
            clim_rate = float(clim["closed"].mean()) if len(clim) else float("nan")
            bullets.append(
                f"Area-week closure rate (`habs_status` closed / closed-pending / harvest-restricted): "
                f"**{_pct(rate)}** ({n_closed}/{n} area-weeks)"
                + (f"; same-week clim **{_pct(clim_rate)}**." if len(clim) else ".")
            )
            plain.append(
                f"In this window, {_pct(rate)} of monitored shellfish area-weeks were closed or "
                f"harvest-restricted ({n_closed} of {n})."
            )
            if not np.isnan(clim_rate):
                if rate > clim_rate * 1.15:
                    plain.append("That is above the same-week multi-year average — plan for harvest disruption.")
                elif rate < clim_rate * 0.85:
                    plain.append(
                        "That is below the same-week multi-year average — MHW alone did not coincide with "
                        "a national closure surge here."
                    )
                else:
                    plain.append("Closure incidence is near the same-week multi-year average.")
            tables.append(
                "| Metric | Value |\n| --- | ---: |\n"
                f"| Area-weeks | {n} |\n"
                f"| Closed / restricted | {n_closed} |\n"
                f"| Closure rate | {_pct(rate)} |\n"
                f"| Clim closure rate | {_pct(clim_rate)} |\n"
            )
        else:
            bullets.append("Status panel has no rows for overlapping ISO weeks.")

    if toxin_path.exists():
        tp = pd.read_parquet(toxin_path)
        mask = pd.Series(False, index=tp.index)
        for y, w in weeks:
            mask |= (tp["iso_year"] == y) & (tp["iso_week"] == w)
        sub = tp.loc[mask]
        if len(sub) and "exceed_dsp" in sub.columns:
            # only measured weeks if measured_dsp present
            if "measured_dsp" in sub.columns:
                meas = sub[sub["measured_dsp"] == 1]
            else:
                meas = sub
            if len(meas):
                dsp_rate = float(meas["exceed_dsp"].mean())
                dsp_n = int(meas["exceed_dsp"].sum())
                bullets.append(
                    f"DSP toxin exceedance among measured station-weeks: **{_pct(dsp_rate)}** "
                    f"({dsp_n}/{len(meas)}). DSP events are rare — treat rates as descriptive."
                )
                plain.append(
                    f"DSP (OA/DTX family) toxin exceedances were recorded in {_pct(dsp_rate)} of "
                    f"measured station-weeks ({dsp_n} of {len(meas)})."
                )

    if metrics_path.exists():
        try:
            m = json.loads(metrics_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            m = {}
        closed = (
            m.get("y_closed", {})
            .get("models", {})
            .get("lightgbm_test_calibrated", {})
        )
        dsp = (
            m.get("y_dsp_exceed", {})
            .get("models", {})
            .get("lightgbm_test_calibrated", {})
        )
        if closed:
            bullets.append(
                f"Model context (not a live forecast): area-closed LightGBM calibrated test PR-AUC "
                f"**{_f(closed.get('pr_auc'), 3)}** vs clim **{_f(closed.get('pr_auc_clim'), 3)}** "
                f"(PR skill **{_f(closed.get('pr_auc_skill'), 3)}**) — partial SST ranking skill."
            )
        if dsp:
            bullets.append(
                f"DSP-exceed model on the same features is **not ops-ready** on 2022+ test "
                f"(PR-AUC **{_f(dsp.get('pr_auc'), 3)}**, prevalence ~{_pct(dsp.get('prevalence'), 2)}; "
                f"too few positives)."
            )
            plain.append(
                "Our research prototype can partially rank closure risk from SST, but DSP toxin "
                "weeks are too scarce on the recent test window to claim a toxin early-warning product."
            )
        if report_path.exists():
            bullets.append(f"Full write-up: `{report_path.relative_to(ROOT)}`.")

    available = bool(bullets)
    return Section(
        available,
        "Closure / DSP risk context",
        bullets,
        plain,
        tables,
        missing_note="" if available else "Closure/DSP artifacts present but empty for this window.",
    )


def summarise_mace(start: pd.Timestamp, end: pd.Timestamp) -> Section:
    path = PROC / "compass_mace_head_daily.parquet"
    if not path.exists():
        return Section(
            False,
            "Mace Head buoy temperature",
            missing_note="compass_mace_head_daily.parquet not found.",
        )
    mh = pd.read_parquet(path)
    mh["date"] = pd.to_datetime(mh["date"]).dt.tz_localize(None).dt.normalize()
    sub = mh[(mh["date"] >= start) & (mh["date"] <= end) & mh["temp_c"].notna()].copy()
    if sub.empty:
        return Section(
            False,
            "Mace Head buoy temperature",
            missing_note="No Mace Head temperature in this window (coverage gap).",
        )

    mean_t = float(sub["temp_c"].mean())
    max_t = float(sub["temp_c"].max())
    min_t = float(sub["temp_c"].min())
    n = int(len(sub))

    # Climatology: same calendar month(s) / DOY band from other years
    months = sorted(sub["date"].dt.month.unique())
    clim = mh[
        mh["temp_c"].notna()
        & mh["date"].dt.month.isin(months)
        & mh["date"].dt.year.isin(range(2018, 2026))
        & ~((mh["date"] >= start) & (mh["date"] <= end))
    ]
    clim_mean = float(clim["temp_c"].mean()) if len(clim) else float("nan")
    anom = mean_t - clim_mean if not np.isnan(clim_mean) else float("nan")

    mean_s = float(sub["salinity"].mean()) if "salinity" in sub and sub["salinity"].notna().any() else float("nan")
    mean_do = float(sub["do_mg_l"].mean()) if "do_mg_l" in sub and sub["do_mg_l"].notna().any() else float("nan")

    bullets = [
        f"compass_mace_head daily SBE — **{n}** days with temperature.",
        f"Mean / min / max T: **{_f(mean_t)} / {_f(min_t)} / {_f(max_t)} °C**.",
    ]
    if not np.isnan(anom):
        bullets.append(
            f"Anomaly vs other-year same-month mean ({_f(clim_mean)} °C): **{_f(anom, 2)} °C**."
        )
    if not np.isnan(mean_s):
        bullets.append(f"Mean salinity: **{_f(mean_s, 2)}** PSU.")
    if not np.isnan(mean_do):
        bullets.append(f"Mean DO: **{_f(mean_do, 2)}** mg/L.")

    plain = [
        f"Mace Head buoy mean temperature was {_f(mean_t)} °C over the window "
        f"(range {_f(min_t)}–{_f(max_t)} °C, {n} days)."
    ]
    if not np.isnan(anom):
        sign = "warmer" if anom >= 0 else "cooler"
        plain.append(
            f"That is about {_f(abs(anom), 2)} °C {sign} than the buoy's same-month average in other years."
        )

    table = (
        "| Metric | Value |\n| --- | ---: |\n"
        f"| Days | {n} |\n"
        f"| Mean T (°C) | {_f(mean_t)} |\n"
        f"| Min / max T (°C) | {_f(min_t)} / {_f(max_t)} |\n"
        f"| Anomaly (°C) | {_f(anom)} |\n"
        f"| Mean S (PSU) | {_f(mean_s)} |\n"
        f"| Mean DO (mg/L) | {_f(mean_do)} |\n"
    )
    return Section(True, "Mace Head buoy temperature", bullets, plain, [table])


def summarise_rivers(start: pd.Timestamp, end: pd.Timestamp) -> Section:
    path = PROC / "rivers_daily.csv"
    if not path.exists():
        return Section(
            False,
            "Freshwater (Corrib / Owenboliskey)",
            missing_note="rivers_daily.csv not found.",
        )
    rd = pd.read_csv(path, parse_dates=["date"])
    rd["date"] = pd.to_datetime(rd["date"]).dt.normalize()
    q = rd[rd["parameter"] == "Q"].copy()

    def _stn_stats(stn: int) -> dict | None:
        s = q[q["station_no"] == stn]
        win = s[(s["date"] >= start) & (s["date"] <= end)]
        if win.empty:
            return None
        months = sorted(win["date"].dt.month.unique())
        # Same-month climatology over CLIM_YEARS (matches june2023 case-study convention)
        clim = s[s["date"].dt.year.isin(CLIM_YEARS) & s["date"].dt.month.isin(months)]
        mean_v = float(win["value"].mean())
        clim_v = float(clim["value"].mean()) if len(clim) else float("nan")
        pct = 100.0 * mean_v / clim_v if clim_v and not np.isnan(clim_v) else float("nan")
        return {
            "n": int(len(win)),
            "mean": mean_v,
            "median": float(win["value"].median()),
            "min": float(win["value"].min()),
            "max": float(win["value"].max()),
            "clim": clim_v,
            "pct_clim": pct,
            "name": str(win["station_name"].iloc[0]) if "station_name" in win.columns else str(stn),
        }

    cor = _stn_stats(CORRIB_STN)
    owen = _stn_stats(OWEN_STN)
    if cor is None and owen is None:
        return Section(
            False,
            "Freshwater (Corrib / Owenboliskey)",
            missing_note="No Corrib/Owenboliskey Q in this window.",
        )

    bullets = [
        "OPW Hydro-Data daily mean discharge (bay-scale / local coastal proxies — not estuary flux).",
    ]
    plain = []
    rows = []
    for label, stn, stats in (
        ("Corrib (Wolfe Tone)", CORRIB_STN, cor),
        ("Owenboliskey (Shannagurraun)", OWEN_STN, owen),
    ):
        if stats is None:
            bullets.append(f"{label} `{stn}`: no data in window.")
            continue
        bullets.append(
            f"**{label}** `{stn}`: mean **{_f(stats['mean'], 2)}** m³/s "
            f"(med {_f(stats['median'], 2)}; {_f(stats['min'], 2)}–{_f(stats['max'], 2)}; n={stats['n']})"
            + (
                f" — **{_f(stats['pct_clim'], 0)}%** of same-month clim mean {_f(stats['clim'], 2)} m³/s."
                if not np.isnan(stats["pct_clim"])
                else "."
            )
        )
        plain.append(
            f"{label} mean discharge was {_f(stats['mean'], 2)} m³/s"
            + (
                f", about {_f(stats['pct_clim'], 0)}% of the multi-year same-month average."
                if not np.isnan(stats["pct_clim"])
                else "."
            )
        )
        rows.append(
            f"| {label} | {_f(stats['mean'], 2)} | {_f(stats['median'], 2)} | "
            f"{_f(stats['clim'], 2)} | {_f(stats['pct_clim'], 0)}% |"
        )

    if any(
        s is not None and not np.isnan(s["pct_clim"]) and s["pct_clim"] < 80
        for s in (cor, owen)
    ):
        plain.append(
            "Lower-than-usual freshwater fits a dry / anticyclonic shelf story and can alter "
            "bay stratification and retention — relevant context for HAB risk, not a cause on its own."
        )

    table = (
        "| Gauge | Mean (m³/s) | Median | Clim mean | % of clim |\n"
        "| --- | ---: | ---: | ---: | ---: |\n"
        + "\n".join(rows)
        + "\n"
    )
    return Section(True, "Freshwater (Corrib / Owenboliskey)", bullets, plain, [table])


def _june2023_flagship_note(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    if start == pd.Timestamp("2023-06-01") and end == pd.Timestamp("2023-06-30"):
        summary = PROC / "june2023_case_study_summary.csv"
        extra = [
            "This window is the **flagship June 2023** shelf MHW (Berthou et al. 2024). "
            "Numbers below are recomputed from the same processed sources as "
            "`data/processed/june2023_case_study.md`.",
        ]
        if summary.exists():
            extra.append(f"Machine-readable case-study metrics: `{summary.relative_to(ROOT)}`.")
        return extra
    return []


def build_headline(sections: dict[str, Section], start: pd.Timestamp, end: pd.Timestamp) -> tuple[str, str]:
    """Return (markdown headline, plain headline)."""
    md = (
        f"**Situational brief:** Irish-shelf marine heatwave vs HAB / closure context for "
        f"**{start.date()} → {end.date()}**."
    )
    plain = (
        f"Will this heatwave matter for HABs? Brief for {start.date()} to {end.date()} "
        f"(Irish shelf). This is a situational summary for industry and agencies — not an "
        f"official warning or harvest decision."
    )
    return md, plain


def render_markdown(
    start: pd.Timestamp,
    end: pd.Timestamp,
    sections: dict[str, Section],
    out_stem: str,
) -> str:
    headline_md, _ = build_headline(sections, start, end)
    lines = [
        f"# Will this heatwave matter for HABs?",
        "",
        f"**Window:** {start.date()} → {end.date()}  ",
        f"**Generated:** {_now_local()}  ",
        f"**Product:** MHW event brief (`scripts/mhw_hab_brief.py`)  ",
        f"**Audience:** aquaculture operators, processors, and agency / local-authority desk officers.",
        "",
        headline_md,
        "",
        "> **Not an official warning.** Descriptive situational awareness from open monitoring "
        "data and research prototypes in this repo. Harvest decisions remain with competent authorities "
        "and classified-area status.",
        "",
    ]
    flag = _june2023_flagship_note(start, end)
    if flag:
        lines.append("## Flagship event")
        lines.append("")
        for f in flag:
            lines.append(f"- {f}")
        lines.append("")

    lines.extend(
        [
            "## Bottom line (60 seconds)",
            "",
        ]
    )
    # Assemble bottom line from available plains
    bl: list[str] = []
    for key in ("crw", "dino", "closure", "mace", "rivers"):
        sec = sections.get(key)
        if sec and sec.available and sec.plain:
            bl.append(f"- {sec.plain[0]}")
    if not bl:
        bl.append("- Insufficient processed data to summarise this window.")
    bl.append(
        "- Treat any Dinophysis / closure signal as **context for heightened monitoring**, "
        "not proof that the heatwave caused a bloom."
    )
    lines.extend(bl)
    lines.append("")

    order = [
        ("crw",),
        ("dino",),
        ("closure",),
        ("mace",),
        ("rivers",),
    ]
    for (key,) in order:
        sec = sections[key]
        lines.append(f"## {sec.title}")
        lines.append("")
        if not sec.available:
            lines.append(f"*{sec.missing_note or 'Data not available.'}*")
            lines.append("")
            continue
        for b in sec.bullets:
            if b.lstrip().startswith("- "):
                lines.append(b)
            else:
                lines.append(f"- {b}")
        lines.append("")
        for t in sec.tables:
            lines.append(t)
            if not t.endswith("\n"):
                lines.append("")
        if sec.plain[1:]:
            lines.append("**In plain English:** " + " ".join(sec.plain[1:]))
            lines.append("")

    lines.extend(
        [
            "## Limits & caveats",
            "",
            "- CRW categories are shelf-scale; inshore embayments can differ from the Irish-bbox mean.",
            "- HAB sampling is irregular — a missing week is not a confirmed negative.",
            "- OISST / CRW coastal landmask leaves some inshore stations without SST (e.g. Rosmuc).",
            "- Closure status mixes multiple toxins and administrative rules; SST→cells ≠ SST→closure.",
            "- DSP toxin exceedances are rare on recent years — rates are noisy.",
            "- Freshwater gauges are proxies (tidal influence / sluice) — wetness context, not exact flux.",
            "- This brief does **not** issue a harvest open/close recommendation.",
            "",
            "## How to regenerate",
            "",
            "```bash",
            "python scripts/mhw_hab_brief.py                  # June 2023 flagship",
            "python scripts/mhw_hab_brief.py --latest         # last ~30 days of CRW",
            "python scripts/mhw_hab_brief.py --start 2023-06-01 --end 2023-06-30",
            "```",
            "",
            f"Outputs: `data/processed/briefs/{out_stem}.md` and `.txt`.",
            "",
            "## Sources",
            "",
            "- CRW: `crw_mhw_ireland_daily_summary.csv` (+ parquet)",
            "- HAB: `station_week_panel.parquet`",
            "- Closures / DSP: `status_area_week_panel.parquet`, `toxin_station_week_panel.parquet`, "
            "`dsp_closure_risk_metrics.json`",
            "- Mace Head: `compass_mace_head_daily.parquet`",
            "- Rivers: `rivers_daily.csv` (OPW 30061 / 31075)",
            "- Narrative twin: `june2023_case_study.md` (when window is June 2023)",
            "- Product note: `docs/MHW_EVENT_PRODUCT.md`",
            "",
        ]
    )
    return "\n".join(lines)


def render_plain(
    start: pd.Timestamp,
    end: pd.Timestamp,
    sections: dict[str, Section],
) -> str:
    _, headline = build_headline(sections, start, end)
    lines = [
        "WILL THIS HEATWAVE MATTER FOR HABs?",
        f"Window: {start.date()} to {end.date()}",
        f"Generated: {_now_local()}",
        "",
        headline,
        "",
        "BOTTOM LINE",
    ]
    for key in ("crw", "dino", "closure", "mace", "rivers"):
        sec = sections.get(key)
        if sec and sec.available:
            for p in sec.plain:
                lines.append(f"- {p}")
        elif sec and not sec.available:
            lines.append(f"- {sec.title}: {sec.missing_note or 'not available'}")
    lines.extend(
        [
            "- This is situational awareness for industry and government — not an official warning.",
            "",
            "DETAILS",
        ]
    )
    for key in ("crw", "dino", "closure", "mace", "rivers"):
        sec = sections[key]
        lines.append("")
        lines.append(sec.title.upper())
        if not sec.available:
            lines.append(sec.missing_note or "Data not available.")
            continue
        for b in sec.bullets:
            # strip markdown bold
            text = b.replace("**", "")
            lines.append(f"- {text}" if not text.startswith("- ") else text)
    lines.extend(
        [
            "",
            "LIMITS",
            "- Shelf CRW averages can differ from your bay.",
            "- Missing HAB samples are not confirmed all-clears.",
            "- Do not treat this brief as a harvest open/close decision.",
            "",
            "Regenerate: python scripts/mhw_hab_brief.py [--latest | --start YYYY-MM-DD --end YYYY-MM-DD]",
            "Product note: docs/MHW_EVENT_PRODUCT.md",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", type=str, default=None, help="Window start YYYY-MM-DD")
    p.add_argument("--end", type=str, default=None, help="Window end YYYY-MM-DD")
    p.add_argument(
        "--latest",
        action="store_true",
        help=(
            "Use the last N days of available CRW Irish-bbox data (default 30). "
            "Coverage ends at the last day in crw_mhw_ireland_daily_summary — "
            "extend with scripts/ingest_scout_p0.py (NOAA STAR). "
            "June 2023 remains the flagship demo window (default without --latest)."
        ),
    )
    p.add_argument("--latest-days", type=int, default=30, help="Length for --latest (default 30)")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=BRIEF_DIR,
        help="Output directory (default data/processed/briefs)",
    )
    args = p.parse_args(argv)

    crw = _load_crw()
    crw_min, crw_max = pd.Timestamp(crw["date"].min()), pd.Timestamp(crw["date"].max())
    print(
        f"CRW Irish-bbox coverage: {crw_min.date()} → {crw_max.date()} "
        f"({len(crw)} days in summary)",
        flush=True,
    )
    start, end = _resolve_window(args, crw)
    if args.latest:
        print(
            f"--latest window: {start.date()} → {end.date()} "
            f"(ends at last available CRW day, not calendar today)",
            flush=True,
        )
        lag_days = (pd.Timestamp.now(tz=None).normalize() - crw_max.normalize()).days
        if lag_days > 14:
            nxt = (crw_max + pd.Timedelta(days=1)).date()
            print(
                f"Note: CRW summary lags calendar by ~{lag_days} days. "
                "Extend NOAA STAR downloads:",
                file=sys.stderr,
            )
            print(
                "  python scripts/ingest_scout_p0.py --skip-smartbay --skip-met --skip-conn "
                f"--crw-start {nxt} --crw-end auto",
                file=sys.stderr,
            )
            print(
                "Flagship demo remains June 2023: python scripts/mhw_hab_brief.py",
                file=sys.stderr,
            )
    if end < crw_min or start > crw_max:
        print(
            f"Warning: requested window {start.date()}–{end.date()} outside CRW coverage "
            f"{crw_min.date()}–{crw_max.date()}",
            file=sys.stderr,
        )

    sections = {
        "crw": summarise_crw(crw, start, end),
        "dino": summarise_dinophysis(start, end),
        "closure": summarise_closure(start, end),
        "mace": summarise_mace(start, end),
        "rivers": summarise_rivers(start, end),
    }

    # Filename date: end of window (event brief dated on last day summarised)
    stamp = end.strftime("%Y-%m-%d")
    stem = f"mhw_hab_brief_{stamp}"
    out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    # default BRIEF_DIR is absolute-ish via PROC; normalise
    if args.out_dir == BRIEF_DIR:
        out_dir = BRIEF_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    md = render_markdown(start, end, sections, stem)
    txt = render_plain(start, end, sections)
    md_path = out_dir / f"{stem}.md"
    txt_path = out_dir / f"{stem}.txt"
    md_path.write_text(md, encoding="utf-8")
    txt_path.write_text(txt, encoding="utf-8")

    print(f"Wrote {md_path.relative_to(ROOT)}")
    print(f"Wrote {txt_path.relative_to(ROOT)}")
    avail = [k for k, s in sections.items() if s.available]
    miss = [k for k, s in sections.items() if not s.available]
    print(f"Sections available: {', '.join(avail) or 'none'}")
    if miss:
        print(f"Sections missing: {', '.join(miss)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
