# Irish-shelf June SST warming context

**Generated:** 2026-09-02 (Europe/Dublin).  
**Purpose:** Long-term warming backdrop for Dinophysis / HAB narrative (paper + hackathon). Not a causal claim.

## Method

- Source: on-disk `data/raw/oisst_daily.parquet` (NOAA OISST at Irish HAB station pixels).
- Optional cross-check: `data/raw/ostia_daily.parquet` (CMEMS OSTIA).
- Aggregate: mean SST across station pixels → June daily means → June annual mean.
- Irish shelf proxy bbox via station set (~51.5–55.3°N, ~10.6–6.0°W).
- Trend: ordinary least-squares linear fit; report °C/decade and R².

## Headline — OISST June

- Period: **2002–2026** (25 Junes)
- Trend: **+0.298 °C/decade** (R² = 0.073)
- Early vs late: first-5 June mean **13.52 °C** → last-5 **14.33 °C** (Δ = +0.81 °C)

## Cross-check — OSTIA June

- Period: **2002–2025**
- Trend: **+0.165 °C/decade** (R² = 0.040)

## Artefacts

- Figure: `docs/climate_assets/irish_shelf_june_sst_trend.png`
- Series CSV: `data/processed/irish_shelf_june_sst_series.csv`
- Metrics JSON: `data/processed/sst_warming_context_metrics.json`

## Interpretation for HAB work

- Use as **context**: warmer June shelf waters shift seasonal baselines; the strong Dinophysis model already uses SST + lags + rolls.
- A simple year / June-climatology-anomaly feature is a **warming proxy**, not a substitute for local synoptic forcing (wind, radiation).
- Do not claim MHW→bloom causation from this trend alone.
