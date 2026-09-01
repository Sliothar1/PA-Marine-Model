# Paper outline — Dinophysis / HAB response to the June 2023 NW European shelf MHW (Irish shelf + Connemara)

**Status:** working outline for a follow-on to Berthou et al. (2024).  
**Repo evidence base:** PA-Marine-Model artifacts dated 2026-09-01 (Europe/Dublin).  
**Path:** `docs/PAPER_OUTLINE.md`

---

## Working title

**Dinophysis exceedance risk on the Irish shelf during the June 2023 northwest European marine heatwave: national nowcasts and a Connemara (Mace Head) case study**

*Alt:* *Marine heatwaves and Dinophysis on the Irish shelf: linking the June 2023 NW European MHW to HAB exceedance risk and Connemara in situ observations*

---

## Research questions

1. **National skill.** Relative to week-of-year climatology, how well can SST / Hobday–style MHW features (and a lean “strong” feature set) nowcast Dinophysis exceedance (≥ 100 cells L⁻¹ in the current + next ISO week) at Irish HAB stations?
2. **Event context.** How did Irish-bbox CRW MHW intensity, Connemara in situ T–S–DO (Mace Head / Spiddal), and Met Éireann Mace Head wind/radiation evolve through May–Aug 2023 relative to Berthou et al. (2024)’s ~16-day category-II NW European shelf MHW?
3. **Local HAB timing.** At nearby NMP / HAB stations (Mannin, Rosmuc, Gubbaros, Cliffden Outer, …), did Dinophysis exceedances coincide with, lead, or lag the June 2023 MHW peak — and what does that imply for a lagged / transport-mediated vs coincidental response?
4. **Honest attribution bound.** What can (and cannot) be claimed given archive gaps (IMI CONN ROMS, Lehanagh Pool from 2024) and the absence of a 1:1 June peak HAB spike in the Connemara focus set?

---

## Data already in hand (paths & key metrics)

| Role | Path(s) | Key numbers |
| --- | --- | --- |
| HAB labels (MI ERDDAP `habs_phyto`) | `data/raw/habs_phyto.csv` | 765,005 rows; 2002-11-18 → 2026-08-30; **207** stations |
| Station-week panel | `data/processed/station_week_panel.parquet` | **53,172** station-weeks (train 29,683 / val 9,189 / test 14,270) |
| OISST + daily MHW | `data/raw/oisst_daily.parquet`, `data/processed/mhw_daily.parquet` | 1.86M station-days; 57 unique 0.25° pixels (Irish bbox) |
| Joined features | `data/processed/joined_features.parquet` | 2.4 MB; nowcast / ahead7 labels |
| Full-run metrics | `data/processed/metrics.json`, `run_summary.md` | Dinophysis panel rate **0.0623** (3,312 positives); test nowcast prev ≈ **0.052** |
| Strong-mode metrics | `data/processed/metrics_dino_strong.json`, `dino_feature_report.md`, `dino_ablation_metrics.json` | Best LightGBM test PR-AUC cal **0.293** (clim **0.183**; PR skill cal **~0.135**) |
| CRW Irish bbox MHW | `data/processed/crw_mhw_ireland_daily_summary.csv` (+ parquet) | June 2023 mean frac_mhw **0.964**; peak **1.000** on 19–20 Jun; peak mean_cat **2.77** (20 Jun); max_cat **5** |
| June 2023 case study | `june2023_case_study.md`, `*_summary.csv`, `*_daily.csv`, `*_hab_weekly.csv` | Mace Head June mean T **15.98 °C**, S **34.42**, DO **8.05** mg/L; Met mean wind **11.1 kt**, glorad **2107 J/cm²**; Spiddal CTD mean/max T **12.86 / 17.65 °C** |
| Sentinel / local | `compass_mace_head_daily.parquet`, `spiddal_ctd_daily.parquet`, `mace_head_met_daily.csv`, `local_sites_report.md` | Mace Head NRT 2018→; Lehanagh NRT from **2024-05-27**; focus HAB IDs 174/177/179/650 (+ 163/171) |
| Figures (case study) | `data/processed/figures/june2023_*.png` | CRW/Met/temps; Dinophysis Connemara; Mace Head T–S–DO |
| Supporting experiments | `ostia_vs_oisst_report.md`, `era5_wind_dino_report.md`, `ibi_light_mhw_report.md` | OSTIA alone ~0.24 cal PR (worse); ERA5 wind Δ ≈ −0.006; IBI light/MLD hurt |

**Primary exceedance:** Dinophysis ≥ **100 cells L⁻¹**. Splits: train 2003–2018 / val 2019–2021 / test 2022+.

---

## Methods (planned paper structure)

### 1. MHW detection (Hobday / CRW)

- **Station-pixel OISST:** self-contained Hobday et al. (2016) in `src/pa_marine/mhw.py` — seasonal 90th-percentile threshold (11-day window), ≥5-day events, ≤2-day gap merge; features SST, SSTA, `in_mhw`, duration, cumulative intensity + lags/rolls.
- **Shelf context:** NOAA Coral Reef Watch Daily Global 5 km MHW Watch (Hobday categories on CoralTemp) aggregated over Irish bbox 51–56°N, 11–5°W — frac_mhw, mean/max category (already in CRW daily summary).
- Link narrative to Berthou et al. (2024) forcing story (weak winds, high solar, tropical air) using Met Éireann `dly275` Mace Head, without re-analysing their weather regimes.

### 2. Strong ML nowcast model

- Targets: `y_dinophysis_nowcast` (days 0–14 from ISO week start); report `ahead7` as secondary.
- Models: balanced logistic regression + **LightGBM**; **val-only** isotonic/sigmoid calibration (`--calibration auto`).
- **Feature mode `strong` (ablation winner, 9 cols):** `woy_sin`, `woy_cos`, `latitude`, `longitude`, `sst`, `sst_lag0d`, `sst_lag21d`, `sst_roll7d`, `sst_roll30d`.
- Metrics: PR-AUC and Brier vs **train** week-of-year climatology; quote **calibrated** test numbers (raw Brier skill strongly negative from class weighting).
- Headline Ireland result to report: LightGBM strong test PR-AUC cal **≈0.293** vs clim **≈0.183** (PR skill **≈0.12–0.14**); baseline-all was **0.281**. Seasonality + geography dominate gain/permutation; binary MHW flags add little once SST rolls/lags are present.

### 3. Event study (June 2023 × Connemara)

- Common May–Aug 2023 timeline: CRW Irish-bbox categories + Mace Head / Spiddal hydro + Met wind/radiation + weekly Dinophysis at focus NMP stations.
- Descriptive alignment only: Rosmuc **320 cells/L** week of **2023-05-29** (pre-peak); quiet counts through peak June CRW; Mannin **120 cells/L** week of **2023-07-10** (post-peak / after OISST `in_mhw` clear at Mannin).
- OISST station-week at Mannin (177): `in_mhw=1` from week of **2023-05-22** through **2023-06-26**; SSTA peak ~**+2.6 °C**; `mhw_duration` up to **37 days**.
- Optional: Scotland SMC Dinophysis panel as regional contrast (higher prevalence; strong-mode PR skill ~0.20) — short sidebar, not core claim.

---

## Expected figures

1. **Study map** — Irish HAB stations + Connemara inset (Mace Head, Spiddal, Lehanagh, focus NMP IDs).
2. **National skill** — PR curves / PR-AUC skill table (logreg vs LightGBM; all vs strong; clim baseline); optional permutation/gain bar chart (`dino_feature_report.md`).
3. **CRW June 2023 shelf MHW** — Irish-bbox frac_mhw and mean/max category May–Aug 2023 (reuse / polish `june2023_mhw_met_temp.png`).
4. **Atmosphere + in situ** — Met Éireann wind + global radiation; Mace Head T–S–DO; Spiddal ~20 m T (`june2023_mace_head_tsdo.png`).
5. **Dinophysis event panel** — weekly counts at Rosmuc / Mannin / Gubbaros / Cliffden Outer with CRW/OISST MHW shading (`june2023_dinophysis_connemara.png`).
6. **Schematic timeline** — Berthou shelf MHW window vs local exceedance weeks (lead / lag annotation; no causal arrow).

---

## Limitations (must state explicitly)

| Limitation | Evidence in repo | Implication |
| --- | --- | --- |
| **Modest skill vs climatology** | Strong LGBM test PR skill ~**0.12–0.14**; Brier skill cal ≈ **0** (raw ≪ 0) | Useful ranking lift, not an operational warning product; quote calibrated probs |
| **No 1:1 June peak HAB** | Focus Connemara set: peak CRW weeks stay **0–40 cells/L**; only **2** exceedance weeks (May Rosmuc, Jul Mannin) | Event study is descriptive / lag-hypothesis only — **not** causal attribution |
| **IMI CONN 3-D ROMS archive gap** | `IMI_CONN_3D` June 2023 missing on public rolling ERDDAP/THREDDS (~last 8–30 d online); `data/raw/imi_conn/thredds_archive_paths.json` | No high-res stratification / transport for the event week |
| **Lehanagh Pool from 2024** | `sentinel_lehanagh` NRT starts **2024-05-27** — no June 2023 overlap | No Chl / turbidity / EXO2 for the event; cannot tell a Lehanagh DO–Chl story here |
| Coarse SST / coastal mask | OISST 0.25°; Rosmuc `sst` always NaN (landmask); OSTIA alone underperformed OISST in our test | Inshore Dinophysis poorly resolved; keep OISST default pending better coastal SST |
| Sampling & Karenia | Irregular HAB weeks ≠ true negatives; Karenia threshold ~**128k** cells/L → prevalence ≪ 0.1%, no useful PR skill | Primary paper target remains Dinophysis |

---

## Target venue suggestions (short list)

1. **Harmful Algae** — HAB–environment coupling; event + model skill fits scope.  
2. **Marine Pollution Bulletin** / **Estuarine, Coastal and Shelf Science** — Irish shelf case + monitoring relevance.  
3. **Ocean Science** (EGU) or **Frontiers in Marine Science** (Marine Ecosystem Ecology / Coastal Ocean Processes) — open, methods + reproducible pipeline friendly.  
4. **Short / data note track:** *Commun Earth Environ* Matters Arising / Brief Communication **only if** framed strictly as an observational HAB addendum to Berthou et al. (2024) — likely a stretch given ML + local case study length; prefer (1)–(3) for the full package.

**Suggested package length:** ~5–8k words + 5–6 figures; code/data DOI from this repo + processed case-study CSVs.

---

## One-paragraph abstract seed

Following Berthou et al. (2024)’s documentation of an exceptional June 2023 northwest European shelf marine heatwave, we examine Dinophysis exceedance risk on the Irish shelf using Marine Institute HAB monitoring (207 stations; 53k station-weeks), Hobday-style OISST MHW features, and NOAA CRW 5 km categories. A calibrated LightGBM nowcast with a nine-feature “strong” set achieves test PR-AUC ≈ 0.293 versus week-of-year climatology ≈ 0.183 (PR skill ≈ 0.13). A Connemara case study aligning CRW MHW (June mean ocean fraction in MHW ≈ 0.96; peak 1.0 mid-June), Mace Head / Spiddal hydrography, and Met Éireann radiation/wind with nearby NMP Dinophysis shows exceedances bookending rather than peaking with the MHW maximum. We report archive gaps (Connemara ROMS, Lehanagh Pool from 2024) and treat the local timeline as descriptive, not causal.

---

## Key citations (seed)

- Berthou et al. (2024), *Commun Earth Environ* 5:287 — https://doi.org/10.1038/s43247-024-01413-8  
- Hobday et al. (2016), *Prog Oceanogr* — MHW definition  
- Marine Institute ERDDAP `habs_phyto` / sentinel tabledaps; NOAA OISST v2.1; NOAA CRW MHW Watch v1.0.1
