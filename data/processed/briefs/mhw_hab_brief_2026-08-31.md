# Will this heatwave matter for HABs?

**Window:** 2026-08-02 → 2026-08-31  
**Generated:** 2026-09-02 11:41 IST  
**Product:** MHW event brief (`scripts/mhw_hab_brief.py`)  
**Audience:** aquaculture operators, processors, and agency / local-authority desk officers.

**Situational brief:** Irish-shelf marine heatwave vs HAB / closure context for **2026-08-02 → 2026-08-31**.

> **Not an official warning.** Descriptive situational awareness from open monitoring data and research prototypes in this repo. Harvest decisions remain with competent authorities and classified-area status.

## Bottom line (60 seconds)

- Over 2026-08-02 to 2026-08-31, on average 69.5% of Irish-shelf ocean pixels were in a marine heatwave (NOAA Coral Reef Watch).
- Across Irish HAB stations, 6.9% of station-weeks in this window had Dinophysis at or above 100 cells/L (18 of 259).
- In this window, 23.5% of monitored shellfish area-weeks were closed or harvest-restricted (89 of 378).
- Mace Head buoy mean temperature was 16.35 °C over the window (range 15.50–16.88 °C, 30 days).
- Treat any Dinophysis / closure signal as **context for heightened monitoring**, not proof that the heatwave caused a bloom.

## Shelf marine heatwave (CRW)

- Irish bbox (51–56°N, 11–5°W) CRW Daily Global 5 km MHW Watch — **30** days in window.
- Mean ocean fraction in MHW (cat ≥ 1): **0.695** (69.5% of ocean pixels).
- Peak frac_mhw: **0.991** on **2026-08-31** (1 day(s) ≥ 0.99).
- Peak daily mean category: **1.34** on **2026-08-28**; max category observed: **5** (0 = none … 5 = beyond extreme).
- Days with any pixel ≥ cat 3: **30** / 30.
- Plain-language severity: **moderate-to-strong shelf MHW**.

| Metric | Value |
| --- | ---: |
| Days in window | 30 |
| Mean frac_mhw | 0.695 |
| Peak frac_mhw | 0.991 (2026-08-31) |
| Peak mean_cat | 1.34 (2026-08-28) |
| Max cat | 5 |
| Days max_cat ≥ 3 | 30 |

**In plain English:** The hottest footprint day was 2026-08-31 (frac_mhw 0.991; peak mean category 1.34 on 2026-08-28; max category 5). Industry read: this window looks like a moderate-to-strong shelf MHW.

## Dinophysis exceedance (national + Connemara)

- Threshold: Dinophysis ≥ **100 cells/L** (`y_dinophysis`). ISO weeks overlapping window: 2026-W31, 2026-W32, 2026-W33, 2026-W34, 2026-W35, 2026-W36.
- National: **6.9%** of station-weeks exceeded (18/259); same-week climatology 2015–2024 excl. event: **10.4%**.
- Connemara focus (Rosmuc, Mannin, Gubbaros, Cliffden Outer, Ballynakill): **0.0%** exceeded (0/18); clim **4.9%**.
- No Dinophysis exceedance weeks in the Connemara focus set during overlapping ISO weeks.

| Scope | Station-weeks | Exceedances | Rate | Clim rate |
| --- | ---: | ---: | ---: | ---: |
| National | 259 | 18 | 6.9% | 10.4% |
| Connemara focus | 18 | 0 | 0.0% | 4.9% |

**In plain English:** In the Connemara focus set the rate was 0.0% (0 of 18). National exceedance rate is below the same-week climatology — a strong shelf MHW does not automatically mean a national Dinophysis spike in this window.

## Closure / DSP risk context

- Area-week closure rate (`habs_status` closed / closed-pending / harvest-restricted): **23.5%** (89/378 area-weeks); same-week clim **23.9%**.
- Model context (not a live forecast): area-closed LightGBM calibrated test PR-AUC **0.315** vs clim **0.208** (PR skill **0.135**) — partial SST ranking skill.
- DSP-exceed model on the same features is **not ops-ready** on 2022+ test (PR-AUC **0.009**, prevalence ~0.23%; too few positives).
- Full write-up: `data/processed/dsp_closure_risk_report.md`.

| Metric | Value |
| --- | ---: |
| Area-weeks | 378 |
| Closed / restricted | 89 |
| Closure rate | 23.5% |
| Clim closure rate | 23.9% |

**In plain English:** Closure incidence is near the same-week multi-year average. Our research prototype can partially rank closure risk from SST, but DSP toxin weeks are too scarce on the recent test window to claim a toxin early-warning product.

## Mace Head buoy temperature

- compass_mace_head daily SBE — **30** days with temperature.
- Mean / min / max T: **16.35 / 15.50 / 16.88 °C**.
- Anomaly vs other-year same-month mean (16.42 °C): **-0.08 °C**.
- Mean salinity: **34.94** PSU.
- Mean DO: **7.93** mg/L.

| Metric | Value |
| --- | ---: |
| Days | 30 |
| Mean T (°C) | 16.35 |
| Min / max T (°C) | 15.50 / 16.88 |
| Anomaly (°C) | -0.08 |
| Mean S (PSU) | 34.94 |
| Mean DO (mg/L) | 7.93 |

**In plain English:** That is about 0.08 °C cooler than the buoy's same-month average in other years.

## Freshwater (Corrib / Owenboliskey)

*No Corrib/Owenboliskey Q in this window.*

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

Outputs: `data/processed/briefs/mhw_hab_brief_2026-08-31.md` and `.txt`.

## Sources

- CRW: `crw_mhw_ireland_daily_summary.csv` (+ parquet)
- HAB: `station_week_panel.parquet`
- Closures / DSP: `status_area_week_panel.parquet`, `toxin_station_week_panel.parquet`, `dsp_closure_risk_metrics.json`
- Mace Head: `compass_mace_head_daily.parquet`
- Rivers: `rivers_daily.csv` (OPW 30061 / 31075)
- Narrative twin: `june2023_case_study.md` (when window is June 2023)
- Product note: `docs/MHW_EVENT_PRODUCT.md`
