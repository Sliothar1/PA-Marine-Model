# Cork Ocean Hackathon — MHW Demo Pitch Pack

**Audience:** Demo Coordinator + Demo Teams 1–5  
**Repo spine:** open data already in `PA-Marine-Model` only  
**Research demo — not an official warning / harvest open-close product**

---

## Meta

### Locked episodes

| Team | Episode | Region / hook | Repo depth |
| ---: | --- | --- | --- |
| **1** | **June 2023** Irish shelf / Connemara flagship | Mace Head, Lehanagh Pool (gap), Berthou NW European shelf MHW | **Full** case study + brief |
| **2** | **Summer 2018** NE Atlantic / European MHW | Irish-shelf OISST June #2 warmest (2002–2026) | OISST/MHW + HAB weeks; **no CRW** |
| **3** | **Summer 2003** European heatwave marine imprint | Irish/UK shelf; late-summer OISST MHW (Aug) | OISST/MHW + national HAB; **no CRW**; Connemara focus IDs thin |
| **4** | **Summer 2019** Irish/UK shelf MHW or near-MHW | Weak OISST MHW; high national Dinophysis weeks | OISST/MHW + HAB; **no CRW** — label **near-MHW / contrast** |
| **5** | **Summer 2022** European/NE Atlantic MHW | CRW Aug peak vs June 2023 contrast | CRW briefs Jun/Jul/Aug 2022 + OISST |

### Target branch

Commit this file on **`pa/demo-workstream` only** ([PR #2](https://github.com/Sliothar1/PA-Marine-Model/pull/2)) — not `main`, not `review/claude-patch*`.

### Predictive freeze (one-liner)

**Only quote judge skill:** `STRONG_OISST` LightGBM test calibrated PR-AUC **0.2952993265675829** (~**0.295**) — source `data/processed/oc_osi_ablation_report.md` (same figure in `chl_ablation_report.md`, `docs/CLIMATE_DRIVERS.md` Cork weekend lock).  
Companion committed eval: `metrics_dino_strong.json` → LightGBM test cal **0.29326665676644725** (~0.293) vs clim ~0.183 — use for deck footnotes; **judge card = ~0.295**.  
**ODYSSEA and Chl = narrative context only — never claim predictive skill** (ablations: no national lift; Gatekeeper parked).

### Open-data rule

Build Cork pitches on **pre-cleared open feeds** already in-repo (MI HAB, NOAA OISST, CRW Irish-bbox summary, Met Éireann, OPW rivers, sentinel buoys). Do **not** bank the pitch on OH-weekend-only Sextant layers. See `docs/OCEAN_HACKATHON_DATA_RULES.md`.

---

## Pitch A — MHW in Ireland: observations

**Story:** Shelf heatwaves are measurable; they do **not** auto-fire national Dinophysis/closures.

| Beat | Fact (repo) |
| --- | --- |
| Flagship severity | June 2023 Irish-bbox CRW mean **frac_mhw = 0.964**; peak **1.000** on **2023-06-19**; max cat **5** |
| Warming backdrop | Irish-shelf June OISST ≈ **+0.30 °C/decade** (2002–2026; first-5→last-5 June means **13.52→14.33 °C**); June 2023 station-mean **15.97 °C** = warmest June (rank 1/25, anom **+2.22 °C** vs 2002–20 clim). Figure: `docs/climate_assets/irish_shelf_june_sst_trend.png` |
| Contrast 2022 | Aug 2022 CRW mean frac_mhw **0.521**, peak **0.914** (31 Aug); max cat **5** mid-Aug — strong but **not** June-2023 wall-to-wall |
| HAB decoupling | June 2023 national Dinophysis exceedance **10.0%** vs clim **14.4%**; closures **16.3%** vs clim **24.3%** |
| Skill (judge) | `STRONG_OISST` test cal PR-AUC **~0.295** — modest ranking skill from SST + seasonality/geography |

**Demo artifacts:** `june2023_case_study.md`, `briefs/mhw_hab_brief_2023-06-30.md`, `crw_mhw_ireland_daily_summary.csv`, `irish_shelf_june_sst_series.csv`.

**Assumption (marked):** Episodes 2–4 predate local CRW summary (starts **2022-01-01**); use OISST Hobday `in_mhw` / June SST ranks instead of inventing CRW fractions.

---

## Pitch B — MHW in main data-collection bays

**Story:** Zoom from shelf CRW/OISST to **Connemara NMP + sentinel** — growers see local weeks, not just Irish-bbox averages.

| Bay / site | Role | Locked facts |
| --- | --- | --- |
| **Mace Head** buoy | Sentinel T/S/DO | June 2023 mean T **15.98 °C** (~**+2.28 °C** vs other-year June buoy mean); Met wind **11.1 kt**, glorad **2107 J/cm²** |
| **Lehanagh Pool** buoy | Sentinel (EXO2 Chl etc.) | NRT from **2024-05-27** — **no June 2023**; demo as **future bay sensor**, not flagship event |
| **Mannin (177)** | NMP core | OISST `in_mhw=1` **2023-05-22 → 2023-06-26**; SSTA peak ~**+2.6 °C**; exceedance **120 cells/L** week of **2023-07-10** (post-peak) |
| **Rosmuc (174)** | NMP / OISST gap | Exceedance **320 cells/L** week of **2023-05-29**; **SST always NaN** (coastal landmask) |
| **Cliffden Outer / Gubbaros / Killary / Ballynakill** | Connemara Farms set | Scored with **national** strong OISST apply; local test PR skill ≈ **0** (rare positives) — quote **national ~0.295 / ~0.293** |
| **Corrib / Owenboliskey** | Freshwater context | June 2023 Q **75%** / **15%** of 2015–24 June clim — dry anticyclonic bay context |

**Products:** Connemara Farms HTML (`CONNEMARA_FARMS.md`); DSP/closure research head test PR-AUC **~0.315** vs clim **~0.208** (`dsp_closure_risk_report.md`).

---

## Pitch C — Galway-focused MHW effects + Cork replication path

**Galway / Connemara onion (Team 1):**

1. Berthou et al. 2024 NW European shelf MHW → Irish CRW frac_mhw → 1.0 mid-June.  
2. Mace Head / Spiddal (Spiddal June mean **12.86 °C**, max **17.65 °C** ~20 m) + Met radiation/wind.  
3. Low Corrib/Owenboliskey Q.  
4. Dinophysis **bookends** peak MHW (Rosmuc late May, Mannin mid-July) — **descriptive, not causal**.  
5. Honest gaps: IMI_CONN_3D archive missing; Lehanagh no 2023; Rosmuc OISST gap.

**Cork replication path (open data only):**

| Step | Action | Artifact |
| --- | --- | --- |
| 1 | CRW Irish-bbox (or `--latest`) | `scripts/mhw_hab_brief.py` → `data/processed/briefs/` |
| 2 | Strong OISST join + evaluate | `metrics_dino_strong.json` / judge **0.295** from ablation report |
| 3 | Local bay overlay | Nearest HAB + any buoy/Met/river already ingested |
| 4 | Grower table | `scripts/score_connemara_farms.py` pattern → other bay station YAML |
| 5 | Do **not** swap ODYSSEA/Chl onto judge card | Narrative SST/Chl only (`CLIMATE_DRIVERS.md` Cork lock) |

**Climate Drivers / Gatekeeper (grounded):** Chl MY + ODYSSEA week ablations show **no national lift** vs `STRONG_OISST` (~0.295); predictive Chl/ODYSSEA **parked** for Cork.

---

## Cross-episode compare (Teams 1–5)

| | **T1 2023 Jun** | **T2 2018 JJA** | **T3 2003 JJA** | **T4 2019 JJA** | **T5 2022 JJA** |
| --- | --- | --- | --- | --- | --- |
| **CRW mean frac (Jun / Aug)** | **0.964** Jun | *no CRW* | *no CRW* | *no CRW* | Jun **0.237** / Aug **0.521** |
| **CRW peak frac** | **1.000** (19 Jun) | — | — | — | **0.914** (31 Aug) |
| **June OISST shelf mean (°C)** | **15.97** (#1) | **14.90** (#2) | 13.61 (#17) | 13.70 (#15) | 13.88 (#13) |
| **OISST JJA `in_mhw` rate** | **0.142** (Jun **0.364**) | **0.111** (Jun **0.194**) | **0.082** (Aug **0.243**) | **0.036** (weak) | **0.035** (Aug **0.105**) |
| **Nat. Dinophysis ≥100 (ISO w22–35)** | **5.5%** (46/842) | **17.4%** (160/920) | **17.4%** (76/437) | **23.7%** (227/957) | **9.0%** (76/846) |
| **Connemara focus exceed (w22–35)** | **2** weeks (Rosmuc+Mannin) | **10** weeks (Gubbaros peak **880**) | **0 rows** for focus IDs | **3** weeks | **6** weeks (Jun cluster + Rosmuc Jul) |
| **Pitch angle** | Flagship severe MHW, HAB **below** clim | Warm June + active Connemara blooms | **August-weighted** imprint; Cork/south hotter than Galway/west; HAB ≈ clim | Near-MHW + **elevated** Dinophysis (Cork/south peaks **off-MHW**) | Recent contrast: Aug CRW ↑, Jun Connemara busy |
| **Needs team fill** | Figures live | CRW N/A; cite literature NE Atl 2018 carefully | CRW N/A; UK shelf literature; older station map | Team pack in; cork_south Dinophysis **52%** with `in_mhw` ~1% | Optional: merge Jun+Aug briefs into one deck |

**Headline compare:** Strongest shelf MHW in-repo (**2023**) had **lowest** national summer Dinophysis rate among the five; **2019** (weak MHW) had the **highest** — use this to kill “MHW ⇒ bloom” slides.

---

## Climate Drivers — descriptive onion (no skill)

Narrative/Met/macro only. **Do not** cite Chl/ODYSSEA/Met/NAO ablations as Cork skill. Spine for model talk remains `STRONG_OISST` ~**0.295**. Sources: `docs/CLIMATE_DRIVERS.md`, `docs/SST_WARMING_CONTEXT.md`, `docs/MACRO_CLIMATE.md`, `docs/CHL_OSI_STATUS.md`, `docs/climate_assets/irish_shelf_june_sst_trend.png`, `data/processed/irish_shelf_june_sst_series.csv`, `data/processed/connemara_normals_9120_extract.csv` (Mace June TMEAN **13.7 °C**, RR **79 mm**). Island-of-Ireland air T ≈ **+0.09 °C/decade** (1900–2024).

| Episode | SST / MHW (shelf) | Met (Mace / Belmullet) | Macro (JJA) | Bay / slide note |
| --- | --- | --- | --- | --- |
| **T1 Jun 2023** | OISST **15.97 °C** (#1); OSTIA Jun **15.42 °C**; JJA mean **15.89 °C**; ODYSSEA 5-stn Connemara Jun pilot ~**15.4 °C** (DOI 10.48670/moi-00152, descriptive) | Garry monthly meant **17.0 °C**, rain **56.1 mm** (~+3.3 °C vs normal, drier); Belmullet glorad ≈ **2005**, Mace ≈ **2107** J/cm² | NAO **negative**; EA Jul/Aug **+1.8/+2.1**; AMO ~**1.3–1.4** | Sub-daily: Mace wind/pressure; radiation weeks prefer Belmullet |
| **T2 2018** | Jun **14.90 °C** (#2, +1.15); JJA mean **15.70 °C** (warmest JJA of the five) | Jun–Jul warm/dryish (15.6/15.9 °C); Aug wetter (**110 mm**) + windier | NAO **strongly +**; EA Jul–Aug **+2.4/+1.8**; AMO moderate + | Contrast vs 2023: **+NAO** warm June vs **−NAO** + record June + high AMO |
| **T3 2003** | Jun **13.61 °C** (~clim); JJA **15.25 °C**; p95/max-day ~**17.4 / 17.6 °C** | No Jun–Aug 2003 on Mace Garry monthly (starts Nov 2003) — use long-term air + shelf peaks | NAO ~neutral; EA early ~**+1.3**; AMO **0.26→0.62** | “European HW with shelf peak-day imprint,” **not** warmest Irish June |
| **T4 2019** | Jun **13.70 °C**; JJA **15.37 °C**; peak days ~**17.3 °C** | Jun cool (13.5); Jul–Aug 15.8/15.6; Aug **173 mm** + wdsp **15.9** | NAO **strongly −**; EA Aug **+1.9**; AMO **0.58→0.74** | Stormy/wet late summer vs mild June SST |
| **T5 2022** | Jun **13.88 °C**; JJA **15.18 °C**; max-day ~**17.5 °C** | Jun cool/wet (13.7 °C, 89 mm); Jul–Aug warmer/drier (15.4/16.3) | NAO → Aug **+1.5**; EA Jul/Aug ~**1.4**; AMO **0.55→0.88** | Pair with 2023: European extremes; **June-mean spike is 2023’s signature** |

---

## Felix 3-instance stories (exporter samples)

From `pa/demo-workstream` `data/processed/demo_instances/` (`manifest.json` + `samples/*.sample.json`). Regenerated by `scripts/export_demo_instances.py`. Copy path for GrokD4M: `data/marine/instances/`. **No `model_p` invented** — weekly rows carry HAB/SST/`demo_sw_*` only; judge quote stays `STRONG_OISST` ~**0.295**.

| Instance id | Window | Story (exporter) | Shelf CRW | National HAB vs same-week clim | Connemara HAB | Galway inner HAB |
| --- | --- | --- | --- | --- | --- | --- |
| `2018_jja_ne_atlantic` (↔ **T2**) | 2018-06-01 → 08-31 | Strong HAB season **without** 2023-style wall-to-wall shelf MHW — “bloom without exceptional CRW MHW” foil | **unavailable** (CRW summary starts 2022-01-01) | **above** — rate **0.176** vs clim **0.126** (150/854) | **above** — **0.138** vs clim **0.051** (13/94); mean `in_mhw` **0.128** | **above** — **0.134** vs clim **0.060** (9/67); SST landmask (coverage 0) |
| `2022_jja_galway_connemara` (↔ **T5**) | 2022-06-01 → 08-31 | Test-era summer; modest CRW vs 2023; contrast **Galway inner** vs Connemara (Killary/Mannin/Clifden) | mean frac **0.347**, peak **0.914** on **2022-08-31**, max cat **5** | **below** — **0.085** vs clim **0.136** (67/789) | **above** — **0.097** vs clim **0.060** (9/93); mean `in_mhw` **0.011** | **above** — **0.087** vs clim **0.068** (4/46); SST coverage 0 |
| `2023_june_flagship` (↔ **T1**) | 2023-06-01 → 06-30 | Flagship CRW ≈0.96 yet national HAB **not** above clim; heatwave ≠ bloom; Rosmuc late-May bookend | mean frac **0.964**, peak **1.0** on **2023-06-19**, max cat **5** | **below** — **0.119** vs clim **0.151** (30/252); mean SSTA **+1.89**, mean `in_mhw` **0.337** | **below** — **0** exceedances / 31 weeks; mean `in_mhw` **0.871** | **below** — **0.063** vs clim **0.115** (1/16) |

**Honesty (all three samples):** spine `STRONG_OISST`; judge quote ~0.295; Chl/ODYSSEA narrative-only; `heatwave_neq_bloom: true`. `demo_sw_*` = train-only station×week empirical rates (Claude CONTEXT ≈0.284 cited as motivation only — **not** a Cork skill claim). Split notes: 2018 last train year (in-sample rates); 2022/2023 are test.

**Map to pitches:** Felix trio = live GrokD4M instances for A/B/C; Teams 3 (2003) + 4 (2019) remain **compare-only** in the five-episode table (no Felix exporter yet).

---


## Five-angle heatwave ≠ bloom (Teams 1–5 closed)

| Cell | Episode | Beat |
| --- | --- | --- |
| Severe MHW, quiet HAB | **T1** 2023 Jun | CRW wall-to-wall; national HAB **below** clim |
| Warm June, elevated HAB | **T2** 2018 | #2 warm June; national Dinophysis **above** clim (CRW N/A) |
| Continental HW, ≈clim HAB | **T3** 2003 | August-weighted OISST; Cork/south hotter than Galway/west |
| Near-MHW, elevated HAB | **T4** 2019 | JJA `in_mhw` **3.57%**; nat. Dinophysis **23.7%**; cork_south **52%** with peaks off-MHW |
| CRW Aug peak, June busy | **T5** 2022 | June Connemara busy / Aug CRW high + quieter HAB nationally |

Same Cork spine: `STRONG_OISST` ~**0.295** only. Team briefs: `/workspace/demo-team3/summer2003-review.md`, `/workspace/demo_team4_summer2019_brief.md`.

---

## Slide-ready bullet bank

Tagged `A`/`B`/`C` + episode `T1`…`T5`.

1. **[A/T1]** June 2023 CRW Irish-box: mean frac_mhw **0.964**, peak **1.0** on 19 Jun, max cat **5**.  
2. **[A/T1]** National Dinophysis that June: **10%** vs clim **14%**; closures **16%** vs clim **24%** — severe MHW ≠ surge.  
3. **[B/T1]** Mace Head June mean **15.98 °C** (~+2.3 °C vs other Junes); Corrib Q **75%** clim, Owenboliskey **15%**.  
4. **[B/T1]** Rosmuc **320 cells/L** (29 May) + Mannin **120** (10 Jul) bookend peak — not coincident bloom.  
5. **[C]** Judge skill only: `STRONG_OISST` test cal PR-AUC **0.295** (`oc_osi_ablation_report.md`).  
6. **[C]** Area-closed research head **~0.315** vs clim **~0.208**; DSP toxin head **not** ops-ready.  
7. **[A]** June SST warming context: **+0.30 °C/decade** (OISST 2002–2026).  
8. **[T2]** June 2018 OISST **14.90 °C** = **#2** warmest June; JJA `in_mhw` **11%**; Connemara Gubbaros **880 cells/L** (18 Jun).  
9. **[T3]** 2003: June coolish (**13.61 °C**); marine imprint in **August** (`in_mhw` **24%**, mean SSTA ~**+1.1 °C**) — needs team literature fill.  
10. **[T4]** 2019: JJA `in_mhw` only **3.6%** but national Dinophysis weeks **23.7%** — near-MHW / contrast episode.  
11. **[T5]** Aug 2022 CRW mean frac **0.521**, peak **0.914**; Connemara focus **0** exceedances in August weeks.  
12. **[T5]** June 2022: CRW mean frac **0.237** but Connemara focus exceed **18.5%** (5/27) vs clim **4.6%**.  
13. **[B]** Lehanagh Pool: demo **sensor path**, not 2023 event (NRT 2024+).  
14. **[C]** ODYSSEA / Chl: narrative only; Gatekeeper — **no** predictive claim.  
15. **[C]** Cork replicate: `mhw_hab_brief.py` + strong OISST + local HAB YAML — open feeds only.

---

16. **[CD/T1]** Mace Jun 2023 meant **17.0 °C** / rain **56.1 mm** vs normals **13.7 °C** / **79 mm**; JJA NAO negative + AMO ~1.3–1.4.  
17. **[CD/T2]** 2018 = warmest locked JJA mean (**15.70 °C**) with **strongly +NAO** — opposite macro sign to 2023.  
18. **[CD/T3]** 2003: mild Irish June mean; tell **peak-day** shelf imprint (~17.6 °C), not record June.  
19. **[CD/T4–T5]** 2019 wet/stormy Aug vs 2022 peak-day heat; neither matches 2023’s June-mean spike.

20. **[Felix/T1]** Exporter `2023_june_flagship`: CRW mean frac **0.964** / peak **1.0** (19 Jun); national HAB **below** clim (0.119 vs 0.151); Connemara June exceedances **0/31**.  
21. **[Felix/T2]** Exporter `2018_jja_ne_atlantic`: national HAB **above** clim (0.176 vs 0.126); CRW N/A; Connemara exceed **0.138** vs clim **0.051**.  
22. **[Felix/T5]** Exporter `2022_jja_galway_connemara`: CRW mean frac **0.347**, peak **0.914** (31 Aug); national HAB **below** clim; local Connemara/Galway still **above** their clim.  
23. **[Felix]** No `model_p` in samples — quote judge **0.295** only; `demo_sw_*` are empirical rates, not Cork skill.

## Sources (paths only)

- `docs/HACKATHON_DEMO.md`
- `docs/MHW_EVENT_PRODUCT.md`
- `docs/CORK_CHEAT_SHEET.md`
- `docs/OCEAN_HACKATHON_DATA_RULES.md`
- `docs/CLIMATE_DRIVERS.md`
- `docs/SST_WARMING_CONTEXT.md`
- `CONNEMARA_FARMS.md`
- `data/processed/june2023_case_study.md`
- `data/processed/june2023_case_study_summary.csv`
- `data/processed/local_sites_report.md`
- `data/processed/crw_mhw_ireland_daily_summary.csv`
- `data/processed/irish_shelf_june_sst_series.csv`
- `data/processed/sst_warming_context_metrics.json`
- `data/processed/run_summary.md`
- `data/processed/metrics_dino_strong.json`
- `data/processed/oc_osi_ablation_report.md`
- `data/processed/chl_ablation_report.md`
- `data/processed/dsp_closure_risk_report.md`
- `data/processed/connemara_farms_metrics.json`
- `data/processed/mhw_daily.parquet`
- `data/processed/joined_features.parquet`
- `data/processed/briefs/mhw_hab_brief_2023-06-30.md`
- `data/processed/briefs/mhw_hab_brief_2022-06-30.md`
- `data/processed/briefs/mhw_hab_brief_2022-07-31.md`
- `data/processed/briefs/mhw_hab_brief_2022-08-31.md`
- `data/processed/briefs/mhw_demo_pitch_facts.json`

- `docs/climate_assets/irish_shelf_june_sst_trend.png`
- `data/processed/connemara_normals_9120_extract.csv`
- `data/processed/demo_instances/manifest.json` (`pa/demo-workstream`)
- `data/processed/demo_instances/samples/2018_jja_ne_atlantic.sample.json`
- `data/processed/demo_instances/samples/2022_jja_galway_connemara.sample.json`
- `data/processed/demo_instances/samples/2023_june_flagship.sample.json`
- `data/processed/demo_instances/README.md`
- `docs/PA_META_HANDOFF.md`
*(Do not rewrite `docs/CPR_MBA.md`.)*
