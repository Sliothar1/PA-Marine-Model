#!/usr/bin/env python3
"""Irish-shelf June SST long-term warming context from on-disk OISST (and OSTIA).

Builds a station-mean June SST time series over Irish HAB locations already in
data/raw/oisst_daily.parquet, fits a linear trend (°C/decade), writes figure +
markdown + CSV for paper/hackathon narrative.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
ASSETS = ROOT / "docs" / "climate_assets"
DOCS = ROOT / "docs"


def june_series(path: Path, label: str) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=["date", "sst", "location_id"])
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"].dt.month == 6].copy()
    df["year"] = df["date"].dt.year
    # station-mean then June monthly mean across days (Irish shelf proxy)
    daily = df.groupby(["year", "date"], as_index=False)["sst"].mean()
    june = daily.groupby("year", as_index=False).agg(
        june_sst=("sst", "mean"),
        n_days=("sst", "size"),
        n_obs=("sst", "size"),
    )
    june["source"] = label
    return june


def fit_trend(years: np.ndarray, y: np.ndarray) -> dict:
    mask = np.isfinite(years) & np.isfinite(y)
    x = years[mask].astype(float)
    yy = y[mask].astype(float)
    if len(x) < 5:
        return {"status": "too_few", "n": int(len(x))}
    # linear: y = a + b * year
    b, a = np.polyfit(x, yy, 1)  # polyfit returns highest degree first → slope, intercept
    yhat = a + b * x
    ss_res = float(np.sum((yy - yhat) ** 2))
    ss_tot = float(np.sum((yy - yy.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    # °C per decade
    per_decade = float(b * 10.0)
    return {
        "status": "ok",
        "n_years": int(len(x)),
        "year_min": int(x.min()),
        "year_max": int(x.max()),
        "slope_c_per_year": float(b),
        "intercept_c": float(a),
        "c_per_decade": per_decade,
        "r2": float(r2),
        "june_mean_first5": float(yy[:5].mean()),
        "june_mean_last5": float(yy[-5:].mean()),
        "delta_last5_minus_first5": float(yy[-5:].mean() - yy[:5].mean()),
    }


def plot_series(june: pd.DataFrame, trend: dict, title: str, out_png: Path) -> None:
    years = june["year"].to_numpy()
    y = june["june_sst"].to_numpy()
    fig, ax = plt.subplots(figsize=(8.5, 4.2), dpi=140)
    ax.plot(years, y, "o-", color="#0b6e99", ms=4, lw=1.2, label="June mean SST (station-mean)")
    if trend.get("status") == "ok":
        xline = np.linspace(years.min(), years.max(), 50)
        yline = trend["intercept_c"] + trend["slope_c_per_year"] * xline
        ax.plot(
            xline,
            yline,
            "--",
            color="#c44e52",
            lw=1.6,
            label=f"Linear trend {trend['c_per_decade']:+.2f} °C/decade (R²={trend['r2']:.2f})",
        )
    ax.set_xlabel("Year")
    ax.set_ylabel("June SST (°C)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)


def write_markdown(oisst_t: dict, ostia_t: dict | None, paths: dict) -> str:
    lines = [
        "# Irish-shelf June SST warming context",
        "",
        f"**Generated:** 2026-09-02 (Europe/Dublin).  ",
        "**Purpose:** Long-term warming backdrop for Dinophysis / HAB narrative "
        "(paper + hackathon). Not a causal claim.",
        "",
        "## Method",
        "",
        "- Source: on-disk `data/raw/oisst_daily.parquet` (NOAA OISST at Irish HAB station pixels).",
        "- Optional cross-check: `data/raw/ostia_daily.parquet` (CMEMS OSTIA).",
        "- Aggregate: mean SST across station pixels → June daily means → June annual mean.",
        "- Irish shelf proxy bbox via station set (~51.5–55.3°N, ~10.6–6.0°W).",
        "- Trend: ordinary least-squares linear fit; report °C/decade and R².",
        "",
        "## Headline — OISST June",
        "",
    ]
    if oisst_t.get("status") == "ok":
        lines += [
            f"- Period: **{oisst_t['year_min']}–{oisst_t['year_max']}** ({oisst_t['n_years']} Junes)",
            f"- Trend: **{oisst_t['c_per_decade']:+.3f} °C/decade** (R² = {oisst_t['r2']:.3f})",
            f"- Early vs late: first-5 June mean **{oisst_t['june_mean_first5']:.2f} °C** → "
            f"last-5 **{oisst_t['june_mean_last5']:.2f} °C** "
            f"(Δ = {oisst_t['delta_last5_minus_first5']:+.2f} °C)",
            "",
        ]
    if ostia_t and ostia_t.get("status") == "ok":
        lines += [
            "## Cross-check — OSTIA June",
            "",
            f"- Period: **{ostia_t['year_min']}–{ostia_t['year_max']}**",
            f"- Trend: **{ostia_t['c_per_decade']:+.3f} °C/decade** (R² = {ostia_t['r2']:.3f})",
            "",
        ]
    lines += [
        "## Artefacts",
        "",
        f"- Figure: `{paths['figure']}`",
        f"- Series CSV: `{paths['csv']}`",
        f"- Metrics JSON: `{paths['json']}`",
        "",
        "## Interpretation for HAB work",
        "",
        "- Use as **context**: warmer June shelf waters shift seasonal baselines; "
        "the strong Dinophysis model already uses SST + lags + rolls.",
        "- A simple year / June-climatology-anomaly feature is a **warming proxy**, "
        "not a substitute for local synoptic forcing (wind, radiation).",
        "- Do not claim MHW→bloom causation from this trend alone.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)

    oisst_path = RAW / "oisst_daily.parquet"
    if not oisst_path.exists():
        print("ERROR: missing", oisst_path, file=sys.stderr)
        return 1

    june_o = june_series(oisst_path, "oisst")
    trend_o = fit_trend(june_o["year"].to_numpy(), june_o["june_sst"].to_numpy())

    june_ost = None
    trend_ost = None
    ostia_path = RAW / "ostia_daily.parquet"
    if ostia_path.exists():
        june_ost = june_series(ostia_path, "ostia")
        trend_ost = fit_trend(june_ost["year"].to_numpy(), june_ost["june_sst"].to_numpy())

    # Combined table
    series = june_o[["year", "june_sst", "n_days"]].rename(
        columns={"june_sst": "oisst_june_sst", "n_days": "oisst_n_days"}
    )
    if june_ost is not None:
        series = series.merge(
            june_ost[["year", "june_sst", "n_days"]].rename(
                columns={"june_sst": "ostia_june_sst", "n_days": "ostia_n_days"}
            ),
            on="year",
            how="outer",
        )
    series = series.sort_values("year")
    csv_path = PROC / "irish_shelf_june_sst_series.csv"
    series.to_csv(csv_path, index=False)

    fig_path = ASSETS / "irish_shelf_june_sst_trend.png"
    plot_series(
        june_o,
        trend_o,
        "Irish-shelf June SST (OISST station-mean) — long-term warming context",
        fig_path,
    )
    # also copy under processed/figures for whitelist pattern
    fig_proc = PROC / "figures" / "irish_shelf_june_sst_trend.png"
    fig_proc.parent.mkdir(parents=True, exist_ok=True)
    fig_proc.write_bytes(fig_path.read_bytes())

    metrics = {
        "bbox_note": "Irish HAB station pixels (~51.5–55.3N, 10.6–6.0W)",
        "oisst": trend_o,
        "ostia": trend_ost,
        "paths": {
            "figure_docs": str(fig_path.relative_to(ROOT)),
            "figure_processed": str(fig_proc.relative_to(ROOT)),
            "csv": str(csv_path.relative_to(ROOT)),
        },
    }
    json_path = PROC / "sst_warming_context_metrics.json"
    json_path.write_text(json.dumps(metrics, indent=2))

    md = write_markdown(
        trend_o,
        trend_ost,
        {
            "figure": str(fig_path.relative_to(ROOT)),
            "csv": str(csv_path.relative_to(ROOT)),
            "json": str(json_path.relative_to(ROOT)),
        },
    )
    md_path = DOCS / "SST_WARMING_CONTEXT.md"
    md_path.write_text(md)

    # Year-level warming feature for ablation join: June SST residual vs long-term trend
    # and year-as-warming-proxy
    if trend_o["status"] == "ok":
        feat = series[["year"]].copy()
        feat["june_sst_oisst"] = series["oisst_june_sst"]
        feat["june_sst_trend"] = (
            trend_o["intercept_c"] + trend_o["slope_c_per_year"] * feat["year"]
        )
        feat["june_sst_trend_residual"] = feat["june_sst_oisst"] - feat["june_sst_trend"]
        # climatology anomaly vs full-period June mean
        clim = float(series["oisst_june_sst"].mean())
        feat["june_sst_clim_anom"] = feat["june_sst_oisst"] - clim
        # year centred as warming proxy (decade units)
        y0 = float(feat["year"].min())
        feat["warming_year_decade"] = (feat["year"] - y0) / 10.0
        feat_path = PROC / "sst_warming_year_features.csv"
        feat.to_csv(feat_path, index=False)
        metrics["year_features"] = str(feat_path.relative_to(ROOT))
        json_path.write_text(json.dumps(metrics, indent=2))

    print(json.dumps(metrics, indent=2))
    print("Wrote", md_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
