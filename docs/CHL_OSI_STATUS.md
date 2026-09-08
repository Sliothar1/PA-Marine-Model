# Status: OC Chl + OSI SAF / ODYSSEA SST fold-in

**Updated:** 2026-09-08 (IST, ~12:14)
**Repo:** `/workspace/pa-marine-model` (github.com/Sliothar1/PA-Marine-Model)

## Product choices

| Layer | Choice | IDs / path |
| --- | --- | --- |
| **OC Chl** | Atlantic GlobColour L4 **gap-free** daily CHL | Product `OCEANCOLOUR_ATL_BGC_L4_MY_009_118` · dataset `cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D` · var `CHL` |
| **OSI SAF SST** | **OSI-202-c** NAR L3C Metop-B (independent of OISST/OSTIA) | GHRSST `AVHRR_SST_METOP_B_NAR-OSISAF-L3C-v1.0` · DOI 10.15770/EUM_SAF_OSI_NRT_2012 · CC BY 4.0 |
| **ODYSSEA (Climate Drivers)** | CMEMS Atlantic L4 NRT SST via CloudFerro ARCO | `SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025` · station-day/week extracts on disk |
| Fallback SST | OSI-201-b global Metop L3C 0.05° | `AVHRR_SST_METOP_B_GLB-OSISAF-L3C-v1.0` |

Catalogue describe for Chl succeeded (bbox covers Irish shelf). Prior OSTIA/IBI parquets already on disk from earlier CMEMS pulls.

## Scripts / modules

| Path | Role |
| --- | --- |
| `src/pa_marine/oc_chl.py` | Station-pixel CMEMS Chl download |
| `src/pa_marine/osi_saf_sst.py` | CMR manifest + week-mean / NC / ODYSSEA helpers |
| `scripts/download_oc_chl.py` | CLI → `data/raw/oc_chl_daily.parquet` |
| `scripts/download_osi_saf_sst.py` | CLI → CMR manifest under `data/raw/osi_saf_sst/` |
| `scripts/extract_odyssea_station_day_arco.py` / `download_odyssea_arco_station_day.py` | Full 207-station ODYSSEA day extract |
| `scripts/ingest_odyssea_sst.py` | Pilot ODYSSEA ingest |
| `scripts/join_oc_osi_week.py` | Week join Chl + ODYSSEA (`osi_sst_week` aliases) onto `joined_features` |
| `scripts/oc_osi_ablation.py` | Ablation vs `STRONG_OISST` (+ `--apr-sep` / `--connemara`) |
| `configs/default.yaml` | `ocean_colour:` + `osi_saf_sst:` + paths |
| `src/pa_marine/features.py` | `OC_CHL_CORE`, `OSI_SAF_WEEK`, modes `strong_chl*` |

**Not touched:** `docs/CPR_MBA.md`.


## ODYSSEA coverage update (2018+ ARCO — 2026-09-08)

Extended CloudFerro ARCO extract supersedes the 2022–2024-only hard_block extract:

| Table | Coverage |
| --- | --- |
| `odyssea_station_day.parquet` | **207** locs · **2018-01-01 → 2026-09-06** · 656 190 rows · 0% NaN |
| `odyssea_station_week.parquet` | **207** locs · ISO **2018–2026** · 93 771 rows |

**Implication for locked split:** train 2003–2018 still mostly empty (product starts 2018) — expect **~1 year** of late-train overlap, full val 2019–2021, full test 2022+. Gatekeeper should **re-run** provider-swap ablation; prior `hard_block` (0% train) is outdated. Still cannot claim full-history OISST train parity. Cite DOI 10.48670/moi-00152. Commit `be15664`.


## ODYSSEA station-day / week (Climate Drivers — ARCO)

**Status 2026-09-08:** Full Irish HAB station extract via CloudFerro ARCO (no CMEMS auth).

| Table | Path | Coverage |
| --- | --- | --- |
| Station-day | `data/processed/odyssea_station_day.parquet` | **207** locations · **2022-01-01 → 2024-12-31** · 226 872 rows · 100% finite `sst_c` |
| Station-week | `data/processed/odyssea_station_week.parquet` | **207** locs · 32 706 rows · cols `odyssea_sst_week`, `iso_year`, `iso_week` |
| Joined panel | `data/processed/joined_features_oc_osi.parquet` (+ alias `joined_features_odyssea.parquet`) | HAB panel + `osi_sst_week` (= `odyssea_sst_week`) + `osi_minus_oisst` + pilot Chl lags |
| Join summary | `data/processed/oc_osi_join_summary.json` | coverage by split |
| Gate JSON | `data/processed/odyssea_ablation_gate.json` | deltas + hard_block + `alert_pa` |

**Access:** ARCO zarr `…/SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025/…/timeChunked.zarr` (`zarr_format=2`). Sources: `data/raw/osi_saf/odyssea_station_day_sources.json`.

### ODYSSEA coverage on HAB panel (by split)

| Split | n rows | n with `odyssea_sst_week` | coverage |
| --- | ---: | ---: | ---: |
| train (2003–2018) | 29 683 | **0** | **0.0%** |
| val (2019–2021) | 9 189 | 3 | 0.03% |
| test (2022+) | 14 270 | 9 317 | **65.3%** |
| all | 53 172 | 9 320 | 17.5% |

### HARD BLOCK — true OISST→ODYSSEA provider-swap

**Cannot rebuild STRONG features from ODYSSEA across train 2003–2018 with the current extract.**  
ODYSSEA station-week is ~2022–2024 only → train coverage = 0. Ablation `STRONG+ODYSSEA` is an **add-on** with missing→0 fill on train/val, **not** a fair provider swap. Do not claim SST-provider substitution skill.

Secondary (honest, non-swap): on **test ∩ ODYSSEA** (n=3 813 rows with both SSTs), `corr(odyssea_sst_week, sst)` ≈ **0.971**, MAE ≈ 0.61 °C, bias (ODY−OISST) ≈ −0.39 °C. This is product agreement only.

## Ablation results (LightGBM, val isotonic cal, `y_dinophysis_nowcast`)

Reference prior strong run: test cal PR-AUC ≈ **0.293** (`metrics_dino_strong.json`).

| Slice | STRONG test cal PR-AUC | STRONG+ODYSSEA | Δ | clim |
| --- | ---: | ---: | ---: | ---: |
| National | 0.295 | 0.295 | **0.000** | 0.183 |
| Apr–Sep | 0.290 | 0.290 | **0.000** | 0.184 |
| Connemara bbox | 0.078 | 0.078 | **0.000** | 0.084 |

Δ=0 is expected under the hard block: ODYSSEA columns are all-missing (→0) on train, so trees never split on them. JSON: `odyssea_ablation_{national,apr_sep,connemara}.json`.

**`alert_pa`:** **true** — reason: `hard_block` (provider-swap impossible with current extract); national Δ is not >0.

## Chl — still pilot-only

| Item | State |
| --- | --- |
| `data/raw/oc_chl_daily.parquet` | **5** stations · **2023-05-01 → 2023-08-31** only |
| Week coverage on full panel | ~0.028% (15 test weeks) |
| National Chl skill | **Do NOT claim** — coverage too tiny |

Attached via `join_oc_osi_week.py` lags for plumbing only. Ablation configs that include Chl are diagnostic, not national evidence.

## OSI-202-c NAR still blocked

Earthdata / Ifremer FTP session still missing on box for protected PO.DAAC NAR granules. ODYSSEA ARCO is the working Climate Drivers SST path for now.

## Re-run commands

```bash
cd /workspace/pa-marine-model
PYTHONPATH=src .venv/bin/python scripts/join_oc_osi_week.py
PYTHONPATH=src .venv/bin/python scripts/oc_osi_ablation.py \
  --out-json data/processed/odyssea_ablation_national.json \
  --out-md data/processed/odyssea_ablation_national.md
PYTHONPATH=src .venv/bin/python scripts/oc_osi_ablation.py --apr-sep \
  --out-json data/processed/odyssea_ablation_apr_sep.json \
  --out-md data/processed/odyssea_ablation_apr_sep.md
PYTHONPATH=src .venv/bin/python scripts/oc_osi_ablation.py --connemara \
  --out-json data/processed/odyssea_ablation_connemara.json \
  --out-md data/processed/odyssea_ablation_connemara.md
```

## Local anchors

Mace Head / Lehanagh Pool remain in `configs/default.yaml` sentinel block; Chl pilot snaps to 5 stations only. ODYSSEA covers all 207 HAB `location_id`s in the 2022–2024 window (lat 51.47–55.28, lon −10.57…−6.03).
