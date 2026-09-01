# June 2023 marine heatwave × Dinophysis — Connemara case study

Generated: **2026-09-01** (Europe/Dublin). Rebuild: `python scripts/build_june2023_case_study.py`.

Hackathon / paper narrative link to **Berthou et al. (2024)** — *Exceptional atmospheric conditions in June 2023 generated a northwest European marine heatwave which contributed to breaking land temperature records* (Commun Earth Environ 5:287; https://doi.org/10.1038/s43247-024-01413-8). That study describes an unprecedented ~16-day category-II Northwest European shelf MHW in June 2023 (local SST anomalies up to ~5 °C north of Ireland), forced by anticyclonic weather (weak winds, high solar radiation, tropical air) with shallow-ocean feedbacks.

This case study places **Irish-bbox CRW MHW categories**, **Connemara HAB Dinophysis**, **Mace Head / Spiddal in-situ T–S–DO**, and **Met Éireann Mace Head wind/radiation** on a common May–Aug 2023 timeline. It is **descriptive**, not a causal attribution of Dinophysis blooms to the MHW.

## Key numbers (June 2023)

| Metric | Value | Notes |
| --- | ---: | --- |
| CRW mean ocean frac in MHW | 0.964 | Irish bbox 51–56°N, 11–5°W |
| CRW peak frac_mhw | 1.000 on 2023-06-19 | also 1.000 on 2023-06-20 |
| CRW peak mean category | 2.77 on 2023-06-20 | max_cat reached **5** many June days |
| Mace Head buoy mean T | 15.98 °C | salinity 34.42, DO 8.05 mg/L |
| Spiddal CTD mean / max T | 12.86 / 17.65 °C | ~20 m; early→late June warm-up |
| Met Éireann mean wind / glorad | 11.1 kt / 2107 J/cm² | station dly275 Mace Head |
| Dinophysis exceedance weeks (≥100 cells/L) | 2 | Rosmuc + Mannin in focus set |

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
| May 2023 | 0.594 | 0.64 | 4 |
| **June 2023** | **0.964** | **1.89** | **5** |
| July 2023 | 0.576 | 0.69 | 5 |
| August 2023 | 0.283 | 0.30 | 3 |

Narrative beats consistent with Berthou et al. (rapid mid-June intensification on the NW European shelf):

- **Late May build-up:** frac_mhw rises from ~0.59 (May mean) to **0.97 on 31 May**.
- **June plateau:** mean frac_mhw **0.96**; **19–20 June** hit frac_mhw = **1.00** with mean_cat **2.64–2.77** and max_cat **5**.
- **Early July decay:** frac_mhw falls from ~0.91 (1 Jul) toward ~0.55 by 7 Jul; August mean ~0.28.

OISST station-week flags (strong Irish panel `joined_features.parquet`) at **Mannin (177)** show `in_mhw=1` from the week of **2023-05-22** through **2023-06-26**, with `ssta` peaking ~**+2.6 °C** (week of 12 Jun) and `mhw_duration` reaching **37 days** by 26 Jun — then clear by early July. Same pattern at Gubbaros / Cliffden Outer.

### 2. Atmosphere — Met Éireann Mace Head (`dly275`)

June mean wind **11.1 kt**, mean global radiation **2107 J/cm²**. Aligns qualitatively with Berthou’s “weak winds + high sunshine” forcing story (not a re-analysis of their weather regimes). Daily series in `june2023_case_study_daily.csv` (`met_wdsp_kt`, `met_glorad`, `met_maxtp`, …).

### 3. In-situ hydrography

**Mace Head** `compass_mace_head` daily (full May–Aug coverage):

| Month | Mean T (°C) | Mean S | Mean DO (mg/L) | Days |
| --- | ---: | ---: | ---: | ---: |
| May | 12.56 | 33.94 | 8.68 | 31 |
| Jun | 15.98 | 34.42 | 8.05 | 30 |
| Jul | 16.31 | 34.54 | 7.58 | 31 |
| Aug | 16.55 | 34.27 | 7.48 | 31 |

June buoy T (~16 °C) is warmer than May by ~3.4 °C; DO declines through summer.

**SmartBay Spiddal** `spiddal_obs_ctd` (~20 m): **30/30 June days**. Mean T **12.86 °C**, but strongly stratified in time — early June ~10.2 °C → late June ~17.3 °C, max **17.65 °C on 2023-06-30**. DO column empty in this NRT daily product. July–Aug Spiddal coverage is sparse (only a few days).

### 4. Dinophysis — Connemara HAB stations

Stations chosen from `local_sites_report.md` nearest-to-sentinel demo set (Mannin, Rosmuc, Gubbaros, Cliffden Outer) plus nearby Ballynakill / Killary Inner. Exceedance label `y_dinophysis` = count ≥ **100 cells/L**.

| location_id | name | weeks (Apr 24–Sep 4) | max Dinophysis | exceedance weeks |
| ---: | --- | ---: | ---: | ---: |
| 174 | Rosmuc | 19 | 320 | 1 |
| 177 | Mannin | 14 | 120 | 1 |
| 179 | Gubbaros | 20 | 80 | 0 |
| 650 | Cliffden Outer | 17 | 80 | 0 |
| 163 | Ballynakill | 20 | 40 | 0 |
| 171 | Killary Harbour Inner | 18 | 0 | 0 |

**Exceedance events in window:**

| Station | week_start | count (cells/L) | OISST SST | SSTA |
| --- | --- | ---: | ---: | ---: |
| Rosmuc (174) | 2023-05-29 | 320 | — | — |
| Mannin (177) | 2023-07-10 | 120 | 16.11 | 0.62 |

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
