# Will this heatwave matter for HABs?

**Window:** 2023-06-01 → 2023-06-30  
**Generated:** 2026-09-02 11:41 IST  
**Product:** MHW event brief (`scripts/mhw_hab_brief.py`)  
**Audience:** aquaculture operators, processors, and agency / local-authority desk officers.

**Situational brief:** Irish-shelf marine heatwave vs HAB / closure context for **2023-06-01 → 2023-06-30**.

> **Not an official warning.** Descriptive situational awareness from open monitoring data and research prototypes in this repo. Harvest decisions remain with competent authorities and classified-area status.

## Flagship event

- This window is the **flagship June 2023** shelf MHW (Berthou et al. 2024). Numbers below are recomputed from the same processed sources as `data/processed/june2023_case_study.md`.
- Machine-readable case-study metrics: `data/processed/june2023_case_study_summary.csv`.

## Bottom line (60 seconds)

- Over 2023-06-01 to 2023-06-30, on average 96.4% of Irish-shelf ocean pixels were in a marine heatwave (NOAA Coral Reef Watch).
- Across Irish HAB stations, 10.0% of station-weeks in this window had Dinophysis at or above 100 cells/L (31 of 309).
- In this window, 16.3% of monitored shellfish area-weeks were closed or harvest-restricted (55 of 338).
- Mace Head buoy mean temperature was 15.98 °C over the window (range 15.05–17.05 °C, 30 days).
- Corrib (Wolfe Tone) mean discharge was 25.43 m³/s, about 75% of the multi-year same-month average.
- Treat any Dinophysis / closure signal as **context for heightened monitoring**, not proof that the heatwave caused a bloom.

## Shelf marine heatwave (CRW)

- Irish bbox (51–56°N, 11–5°W) CRW Daily Global 5 km MHW Watch — **30** days in window.
- Mean ocean fraction in MHW (cat ≥ 1): **0.964** (96.4% of ocean pixels).
- Peak frac_mhw: **1.000** on **2023-06-19** (13 day(s) ≥ 0.99).
- Peak daily mean category: **2.77** on **2023-06-20**; max category observed: **5** (0 = none … 5 = beyond extreme).
- Days with any pixel ≥ cat 3: **30** / 30.
- Plain-language severity: **severe shelf-wide MHW**.

| Metric | Value |
| --- | ---: |
| Days in window | 30 |
| Mean frac_mhw | 0.964 |
| Peak frac_mhw | 1.000 (2023-06-19) |
| Peak mean_cat | 2.77 (2023-06-20) |
| Max cat | 5 |
| Days max_cat ≥ 3 | 30 |

**In plain English:** The hottest footprint day was 2023-06-19 (frac_mhw 1.000; peak mean category 2.77 on 2023-06-20; max category 5). Industry read: this window looks like a severe shelf-wide MHW.

## Dinophysis exceedance (national + Connemara)

- Threshold: Dinophysis ≥ **100 cells/L** (`y_dinophysis`). ISO weeks overlapping window: 2023-W22, 2023-W23, 2023-W24, 2023-W25, 2023-W26.
- National: **10.0%** of station-weeks exceeded (31/309); same-week climatology 2015–2024 excl. event: **14.4%**.
- Connemara focus (Rosmuc, Mannin, Gubbaros, Cliffden Outer, Ballynakill, Killary Harbour Inner): **3.6%** exceeded (1/28); clim **6.5%**.
- Focus-set exceedance weeks:
  - Rosmuc (174): week of 2023-05-29 — 320 cells/L

| Scope | Station-weeks | Exceedances | Rate | Clim rate |
| --- | ---: | ---: | ---: | ---: |
| National | 309 | 31 | 10.0% | 14.4% |
| Connemara focus | 28 | 1 | 3.6% | 6.5% |

**In plain English:** In the Connemara focus set the rate was 3.6% (1 of 28). National exceedance rate is below the same-week climatology — a strong shelf MHW does not automatically mean a national Dinophysis spike in this window. Noted exceedance: Rosmuc in the week of 2023-05-29 (320 cells/L).

## Closure / DSP risk context

- Area-week closure rate (`habs_status` closed / closed-pending / harvest-restricted): **16.3%** (55/338 area-weeks); same-week clim **24.3%**.
- DSP toxin exceedance among measured station-weeks: **0.5%** (1/182). DSP events are rare — treat rates as descriptive.
- Model context (not a live forecast): area-closed LightGBM calibrated test PR-AUC **0.315** vs clim **0.208** (PR skill **0.135**) — partial SST ranking skill.
- DSP-exceed model on the same features is **not ops-ready** on 2022+ test (PR-AUC **0.009**, prevalence ~0.23%; too few positives).
- Full write-up: `data/processed/dsp_closure_risk_report.md`.

| Metric | Value |
| --- | ---: |
| Area-weeks | 338 |
| Closed / restricted | 55 |
| Closure rate | 16.3% |
| Clim closure rate | 24.3% |

**In plain English:** That is below the same-week multi-year average — MHW alone did not coincide with a national closure surge here. DSP (OA/DTX family) toxin exceedances were recorded in 0.5% of measured station-weeks (1 of 182). Our research prototype can partially rank closure risk from SST, but DSP toxin weeks are too scarce on the recent test window to claim a toxin early-warning product.

## Mace Head buoy temperature

- compass_mace_head daily SBE — **30** days with temperature.
- Mean / min / max T: **15.98 / 15.05 / 17.05 °C**.
- Anomaly vs other-year same-month mean (13.70 °C): **2.28 °C**.
- Mean salinity: **34.42** PSU.
- Mean DO: **8.05** mg/L.

| Metric | Value |
| --- | ---: |
| Days | 30 |
| Mean T (°C) | 15.98 |
| Min / max T (°C) | 15.05 / 17.05 |
| Anomaly (°C) | 2.28 |
| Mean S (PSU) | 34.42 |
| Mean DO (mg/L) | 8.05 |

**In plain English:** That is about 2.28 °C warmer than the buoy's same-month average in other years.

## Freshwater (Corrib / Owenboliskey)

- OPW Hydro-Data daily mean discharge (bay-scale / local coastal proxies — not estuary flux).
- **Corrib (Wolfe Tone)** `30061`: mean **25.43** m³/s (med 25.31; 20.57–31.04; n=30) — **75%** of same-month clim mean 33.83 m³/s.
- **Owenboliskey (Shannagurraun)** `31075`: mean **0.15** m³/s (med 0.10; 0.08–0.54; n=30) — **15%** of same-month clim mean 0.99 m³/s.

| Gauge | Mean (m³/s) | Median | Clim mean | % of clim |
| --- | ---: | ---: | ---: | ---: |
| Corrib (Wolfe Tone) | 25.43 | 25.31 | 33.83 | 75% |
| Owenboliskey (Shannagurraun) | 0.15 | 0.10 | 0.99 | 15% |

**In plain English:** Owenboliskey (Shannagurraun) mean discharge was 0.15 m³/s, about 15% of the multi-year same-month average. Lower-than-usual freshwater fits a dry / anticyclonic shelf story and can alter bay stratification and retention — relevant context for HAB risk, not a cause on its own.

## Limits & caveats

- CRW categories are shelf-scale; inshore embayments can differ from the Irish-bbox mean.
- HAB sampling is irregular — a missing week is not a confirmed negative.
- OISST / CRW coastal landmask leaves some inshore stations without SST (e.g. Rosmuc).
- Closure status mixes multiple toxins and administrative rules; SST→cells ≠ SST→closure.
- DSP toxin exceedances are rare on recent years — rates are noisy.
- Freshwater gauges are proxies (tidal influence / sluice) — wetness context, not exact flux.
- This brief does **not** issue a harvest open/close recommendation.

## How to regenerate

```bash
python scripts/mhw_hab_brief.py                  # June 2023 flagship
python scripts/mhw_hab_brief.py --latest         # last ~30 days of CRW
python scripts/mhw_hab_brief.py --start 2023-06-01 --end 2023-06-30
```

Outputs: `data/processed/briefs/mhw_hab_brief_2023-06-30.md` and `.txt`.

## Sources

- CRW: `crw_mhw_ireland_daily_summary.csv` (+ parquet)
- HAB: `station_week_panel.parquet`
- Closures / DSP: `status_area_week_panel.parquet`, `toxin_station_week_panel.parquet`, `dsp_closure_risk_metrics.json`
- Mace Head: `compass_mace_head_daily.parquet`
- Rivers: `rivers_daily.csv` (OPW 30061 / 31075)
- Narrative twin: `june2023_case_study.md` (when window is June 2023)
- Product note: `docs/MHW_EVENT_PRODUCT.md`
