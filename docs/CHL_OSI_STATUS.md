# Status: OC Chl + OSI SAF / ODYSSEA SST fold-in

**Updated:** 2026-09-08 12:46 IST
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


## PA ask — multi-decade open SST L4 via ARCO? (2026-09-08)

**Answer: No** — no anonymous CloudFerro ARCO (or similar HTTPS zarr) SST L4 honestly covers Irish HAB **train 2003–2018** as an OISST provider-swap beyond what we already have/tested. Hunting stopped; evidence from disk + prior report.

| Candidate | Start | Covers train 2003–2018? | ARCO / open HTTPS? | Notes |
| --- | --- | --- | --- | --- |
| **ODYSSEA** `SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025` | **2018-01-01** | **No** (~11% train = 2018 only) | Yes — CloudFerro `…/timeChunked.zarr` (`zarr_format=2`) | Working Climate Drivers extract; **not** full-train swap-capable |
| **OSTIA L4 REP** `SST_GLO_SST_L4_REP_OBSERVATIONS_010_011` / `METOFFICE-GLO-SST-L4-REP-OBS-SST` | disk **2002-01-01 → 2026-03-31** (catalogue ~1981+) | **Yes** | **No** ARCO URI in repo — `copernicusmarine` only (auth TLS broken here) | **Already extracted + tested**; cal LightGBM test PR-AUC **~0.24 vs OISST ~0.29** (`data/processed/ostia_vs_oisst_report.md`). Not OISST rebranded (~0.05° Met Office) — but **lost** as predictive default |
| ESA CCI / other MY SST L4 | multi-decade (catalogue) | likely | **Not** found as working anonymous ARCO like ODYSSEA | Do not invent URLs/creds |

**Recommendation**
1. **Park** ODYSSEA / OSI SAF as a **predictive** OISST-swap lane (train hard-limit; OSTIA already answered “finer multi-decade L4 ≠ skill lift”).
2. Keep ODYSSEA ARCO only as **descriptive / Climate Drivers** context (2018+, agreement vs OISST on overlap).
3. **Pivot** open multi-decade driver work to GlobColour Chl MY `OCEANCOLOUR_ATL_BGC_L4_MY_009_118` (~**1997+**, covers locked train) — expand beyond the 2023 pilot.
4. Default SST remains **NOAA OISST**; OSTIA stays optional `--provider ostia` (local parquet exists).

**Done (this cycle):** full-history Chl station-day/week + ablation vs `STRONG_OISST` — see GlobColour MY Chl section below. ODYSSEA predictive remains parked.

### Cork / protocol lock (PA + Int’l HAB Dev, 2026-09-08)

- **Cork use only:** ODYSSEA as **June 2023 narrative SST** (+ DOI 10.48670/moi-00152). Do **not** spend Cork hours on partial ~2018+ extracts hoping for a national skill claim.
- **2018+ ARCO extract on disk:** **exploratory-only** — late-train / val / test honesty or documented short-history protocols. **Not** comparable to locked STRONG_OISST (train 2003–2018). **No judge-card quote**; no national Δ claim.
- **`hard_block` stands** for full-history provider-swap. STRONG_OISST ~0.295 remains the only national SST baseline to cite.
- Multi-decade open SST already answered by **OSTIA REP** (lost ~0.24 vs ~0.295). Pivot Climate Drivers cycles to **Chl MY** week features.

## ODYSSEA station-day / week (Climate Drivers — ARCO)

**Updated:** 2026-09-08 12:25 IST

Full Irish HAB station extract via public CloudFerro ARCO zarr (`zarr_format=2`), no CMEMS auth. Scripts: `extract_odyssea_station_day_arco.py` / `download_odyssea_arco_station_day.py` (append/merge). Catalogue product start **2018-01-01**; single ARCO gap **2018-10-22** (403).

| Table | Path | Coverage |
| --- | --- | --- |
| Station-day | `data/processed/odyssea_station_day.parquet` | **207** locs · **2018-01-01 → 2026-09-06** · **656 190** rows · 100% finite `sst_c` (2018–2024 slice: 529 092 rows / 2556 days) |
| Station-week | `data/processed/odyssea_station_week.parquet` | **207** locs · ISO **2018–2026** · **93 771** rows · cols `odyssea_sst_week`, `iso_year`, `iso_week` |
| Joined panel | `data/processed/joined_features_osi_sst.parquet` | left-join on `location_id`+ISO week · `odyssea_sst_week` / `odyssea_minus_oisst` · ~50% coverage (HAB weeks outside 2018+) |
| Summary | `data/processed/odyssea_arco_summary.json` + `data/raw/osi_saf/sources.json` | extract meta / skipped day |
| Joined panel (prior) | `data/processed/joined_features_oc_osi.parquet` | still reflects **pre-extend** join — re-run `join_oc_osi_week.py` |
| Gate JSON | `data/processed/odyssea_ablation_gate.json` | **EXTENDED** provider-swap: hard_block=true, Δ=−0.074, alert_pa=true |

**Access:** ARCO zarr `…/SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025/…/timeChunked.zarr` (`zarr_format=2`). DOI 10.48670/moi-00152.

### Expected ODYSSEA coverage on HAB panel (by locked split; week join estimate)

| Split | n rows | n with `odyssea_sst_week` | coverage |
| --- | ---: | ---: | ---: |
| train (2003–2018) | 29 683 | 3 354 | **11.3%** (2018 only) |
| val (2019–2021) | 9 189 | 9 189 | **100%** |
| test (2022+) | 14 270 | 14 270 | **100%** |
| all | 53 172 | 26 813 | **50.4%** |

### Hard limit — full 2003–2018 train still impossible

ODYSSEA / this ARCO product **starts ~2018-01-01**. Under the locked **2003–2018** train split, pre-2018 years remain empty → **full-history OISST→ODYSSEA provider-swap is still impossible**. Prior gate `hard_block` (0% train from 2022–2024-only extract) is outdated on coverage, but the **protocol conclusion stands**: do not claim SST-provider substitution skill over the full locked train.

**Allowed exploratory uses only:** late-train (2018 overlap), val/test, or alternate **2018+** splits marked `exploratory_not_protocol`. EXTENDED provider-swap re-run confirms **`hard_block`** + **Δ < 0**; no national skill claim.

Secondary (honest, non-swap; from prior test ∩ ODYSSEA window): `corr(odyssea_sst_week, sst)` ≈ **0.971**, MAE ≈ 0.61 °C, bias (ODY−OISST) ≈ −0.39 °C. Product agreement only.

## Ablation results (LightGBM — EXTENDED provider-swap, 2026-09-08)

Canonical run: `scripts/odyssea_provider_swap_ablation.py` on ODYSSEA **2018-01-01 → 2026-09-06** (rebuild same 9 `STRONG_OISST` feats from `sst_c`; not stacked). Cite DOI 10.48670/moi-00152.

| Split | ODYSSEA sst coverage |
| --- | ---: |
| train (2003–2018) | **11.3%** (2018 only; n_train with ODYSSEA=**3354**) |
| val (2019–2021) | **100%** |
| test (2022+) | **100%** |

| Config | LGBM test cal PR-AUC | PR skill vs WoY |
| --- | ---: | ---: |
| STRONG_OISST (OISST re-run) | **0.2953** | 0.1373 |
| ODYSSEA_STRONG (require_sst fit) | **0.2217** | 0.0805 |
| **Δ (ODY − OISST)** | **−0.0736** | — |

| Subset (≠ national) | n / prev (test∩ODY) | OISST PR-AUC | ODYSSEA PR-AUC |
| --- | --- | ---: | ---: |
| Apr–Sep | 7610 / 0.096 | 0.2904 | 0.2182 |
| Connemara 53.2–53.7N, −10.2…−9.4 | 1654 / 0.029 | 0.0781 | 0.0982 |

- **`hard_block`:** **true** — partial late-train ≠ full history (11.3% train ≠ 2003–2018).
- **`skill_claim`:** **false** (Δ ≤ 0 and hard_block).
- **`alert_pa`:** **true** (hard_block).
- Fit was **attempted** on late-2018 overlap (diagnostic only). Gate: `odyssea_ablation_gate.json`; report: `odyssea_provider_swap_ablation_report.md`.

Prior stacked STRONG+ODYSSEA Δ=0 JSONs (`odyssea_ablation_{national,apr_sep,connemara}.json`) are **non-protocol** / superseded.

## Ablation results (LightGBM — Gatekeeper 2018+ exploratory, 2026-09-08)

Label if cited: **`exploratory_short_history_not_cork_spine`**. Does **not** replace Cork spine STRONG_OISST ~0.295. DOI [10.48670/moi-00152](https://doi.org/10.48670/moi-00152).

| Slice / metric | Value |
| --- | ---: |
| Train ODYSSEA coverage | **11.3%** (2018-only; n_train with SST=3354) |
| Val / test coverage | **100%** |
| STRONG_OISST test cal PR-AUC | **0.295** |
| ODYSSEA_STRONG test cal PR-AUC | **0.222** |
| Δ | **−0.074** |
| `skill_claim` | **false** |
| `hard_block` | **true** (partial late-train ≠ full history) |

Gate/metrics: `data/processed/odyssea_ablation_gate.json`, `data/processed/odyssea_provider_swap_ablation_metrics.json`.

**Lane:** ODYSSEA/OSI predictive parked (Cork narrative only). Active open driver = **Chl MY** — **1997-10-01 → 2026-08-31 daily+week on disk**; Gatekeeper handoff ready.

## Chl — full MY station extract (Climate Drivers fill, 2026-09-08 12:46 IST)

**Prior late-only / pilot state is NOT Cork-claimable.** The 2018-only and 2023 MJJA pilot extracts are superseded by a full Irish HAB station ARCO fill covering the locked train.

| Item | State |
| --- | --- |
| Product | `OCEANCOLOUR_ATL_BGC_L4_MY_009_118` / `cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D` · var `CHL` |
| Access | Public CloudFerro ARCO zarr HTTPS (`zarr_format=2`); CMEMS toolbox TLS still broken on box |
| Daily | `data/raw/oc_chl_daily.parquet` (+ mirror `data/external/ocean_colour/chl_station_daily.parquet`) |
| Daily rows / stations | **2 179 503** / **207** |
| Daily date range | **1997-10-01 → 2026-08-31** (full ARCO MY catalogue span) |
| Year chunks | `data/raw/oc_chl/chunks/chl_YYYY.parquet` for **1997 (Q4)–2017** (2008 rebuilt after snappy corruption; 2018+ from prior daily) |
| Week table | `data/processed/ocean_colour_chl_week.parquet` (+ `.csv`) · **310 128** rows · ISO **1997–2026** · cols `chl_mean` / median / max / lags / roll4w |
| Meta | `data/raw/oc_chl_daily_meta.json` · `data/processed/oc_chl_coverage_by_split.json` |

### Chl week coverage on `joined_features` (finite `chl_mean`)

| Split | n rows | n with finite chl | coverage |
| --- | ---: | ---: | ---: |
| train (2003–2018) | 29 683 | 29 577 | **99.64%** |
| val (2019–2021) | 9 189 | 9 158 | **99.66%** |
| test (2022+) | 14 270 | 14 223 | **99.67%** |

Train coverage ≫ prior **11%** (2018-only) / pilot ~0.03%. **Handoff to Prediction Gatekeeper** — do not re-download; daily+week cover full MY **1997-10-01 → 2026-08-31**.

National Chl **skill** still requires Gatekeeper ablation vs `STRONG_OISST` (coverage gate is cleared for full-train joins).

## GlobColour MY Chl — full train coverage (Climate Drivers pivot)

**Updated:** 2026-09-08 12:44 IST

**ODYSSEA predictive parked.** Pivot is GlobColour MY Chl add-on beside OISST (`STRONG+OC_CHL_CORE`), **not** an SST provider-swap.

**Cite:** Copernicus Marine Service Ocean Colour Atlantic BGC L4 MY gap-free multi-sensor chlorophyll-a — product `OCEANCOLOUR_ATL_BGC_L4_MY_009_118` / dataset `cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D` (var `CHL`) via public CloudFerro ARCO (`zarr_format=2`).

| Table | Path | Coverage |
| --- | --- | --- |
| Station-day | `data/raw/oc_chl_daily.parquet` | **207** locs · **2003-01-01 → 2026-08-31** · **1 789 308** rows · ~98.9% finite `chl` |
| Meta | `data/raw/ocean_colour/oc_chl_daily_sources_meta.json` (+ `oc_chl_daily_meta.json`) | ARCO URI, pixel reuse note, hist append 2003–2017 |
| Year chunks | `data/raw/oc_chl/chunks/chl_YYYY.parquet` | 2003–2017 append intermediates |
| Joined panel | `data/processed/joined_features_oc_osi.parquet` | Chl lags/rolls + ODYSSEA aliases (ODYSSEA descriptive only) |
| Gate | `data/processed/chl_ablation_gate.json` | coverage, PR-AUCs, Δ, `alert_pa` |
| Metrics | `data/processed/chl_ablation_metrics.json` / `.md` | national + apr–sep + Connemara |

**Pixel map:** reused nearest-ocean pixels from the prior 2018+ extract (170 unique pixels; median dist ≈ 0.009°). Appended **2003-01-01 → 2017-12-31** via ARCO, then merged with existing 2018+ rows.

### Week-panel Chl coverage (locked splits)

| Split | n | n with `chl` | coverage |
| --- | ---: | ---: | ---: |
| train (2003–2018) | 29 683 | 29 491 | **99.35%** |
| val (2019–2021) | 9 189 | 9 132 | **99.38%** |
| test (2022+) | 14 270 | 14 191 | **99.45%** |
| all | 53 172 | 52 814 | **99.33%** |

`hard_block`: **false** (train cov ≫ 0).

### Ablation — STRONG_OISST vs STRONG+OC_CHL_CORE (add-on beside OISST)

LightGBM isotonic-calibrated test PR-AUC. Features: `OC_CHL_CORE` = chl / chl_log1p + lag0/7 + roll7/14/30 (+ log1p rolls).

| Slice | STRONG | STRONG+OC_CHL_CORE | Δ |
| --- | ---: | ---: | ---: |
| National | 0.2953 | 0.2874 | **−0.0079** |
| Apr–Sep | 0.2904 | 0.2866 | **−0.0038** |
| Connemara bbox | 0.0781 | 0.0665 | **−0.0116** |

**`alert_pa`:** **false** — national Δ ≤ 0; train coverage healthy; **no Cork / national skill claim**.
**`skill_claim`:** **false**.

Scripts: `scripts/join_oc_osi_week.py --chl-daily data/raw/oc_chl_daily.parquet`, `scripts/run_chl_ablation_gate.py` (also `scripts/chl_oc_core_ablation_gate.py`).

## Chl ablation vs STRONG_OISST (Gatekeeper, 2026-09-08 12:46 IST)

Full-history ARCO station-day CHL is on disk and week-joined. Honest national / Apr–Sep / Connemara LightGBM ablation vs locked `STRONG_OISST`.

| Item | Value |
| --- | --- |
| Daily | `data/raw/oc_chl_daily.parquet` · **2,179,503** rows · **207** stations · **1997-10-01 → 2026-08-31** |
| ARCO | `https://s3.waw3-1.cloudferro.com/mdl-arco-time-042/arco/OCEANCOLOUR_ATL_BGC_L4_MY_009_118/cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D_202603/timeChunked.zarr` (`zarr_format=2`) |
| Sources meta | `data/raw/ocean_colour/oc_chl_daily_sources_meta.json` |
| Joined panel | `data/processed/joined_features_oc_osi.parquet` (Chl lags/rolls + ODYSSEA aliases) |
| Gate | `data/processed/chl_ablation_gate.json` |
| Metrics / report | `data/processed/chl_ablation_metrics.json` · `chl_ablation_metrics.md` |

### Week-panel `chl` coverage (by locked split)

| Split | coverage % |
| --- | ---: |
| train (2003–2018) | **99.353** |
| val (2019–2021) | **99.38** |
| test (2022+) | **99.446** |
| all | **99.327** |

### LGBM test cal PR-AUC (OC_CHL_CORE fold-in)

| Slice | STRONG_OISST | STRONG+CHL | Δ |
| --- | ---: | ---: | ---: |
| National | 0.2953 | 0.2874 | **-0.0079** |
| Apr–Sep | 0.2904 | 0.2866 | **-0.0038** |
| Connemara | 0.0781 | 0.0665 | **-0.0116** |

- **`hard_block`:** **false** (train Chl cov ≫ 5%).
- **`skill_claim`:** **false** (national Δ ≤ 0).
- **`alert_pa`:** **false** — no alert: national Δ=-0.007933879043937664; train_cov=0.9935; no skill claim without Δ>0

Also ran `scripts/oc_osi_ablation.py` (national / `--apr-sep` / `--connemara`) → `oc_osi_ablation_{national,apr_sep,connemara}.json`. Stacked STRONG+ODYSSEA / STRONG+CHL+ODYSSEA remain non-protocol for SST provider-swap (ODYSSEA train still ~11%); Chl fold-in is the fair full-train comparison above.

**No CPR_MBA edits. No push.**

## OSI-202-c NAR still blocked

Earthdata / Ifremer FTP session still missing on box for protected PO.DAAC NAR granules. ODYSSEA ARCO is the working Climate Drivers SST path for now.

## Re-run commands

```bash
cd /workspace/pa-marine-model
PYTHONPATH=src .venv/bin/python scripts/odyssea_provider_swap_ablation.py
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

Mace Head / Lehanagh Pool remain in `configs/default.yaml` sentinel block. **OC Chl** now covers all **207** HAB `location_id`s for **1997-10-01 → 2026-08-31** (train coverage ~99.6%). ODYSSEA SST remains **2018-01-01 → 2026-09-06** only (product start prevents full-train SST swap).


## Update 2026-09-08 12:47 IST (Climate Drivers fill complete)

- **Chl ARCO full MY:** **1997-10-01 → 2026-08-31**, **207** stations, **2 179 503** daily rows → `data/raw/oc_chl_daily.parquet` + mirror `data/external/ocean_colour/chl_station_daily.parquet`.
- **Week:** `data/processed/ocean_colour_chl_week.parquet` (**310 128**).
- **Coverage:** train **99.64%** / val **99.66%** / test **99.67%** finite `chl_mean` on `joined_features` (late-only was ~11% train — **not** Cork-claimable; now is).
- **CMEMS auth:** still TLS-broken; ARCO anonymous path used.
- **Handoff:** Prediction Gatekeeper — do not re-download.

## Chl MY add-on gate (Gatekeeper, 2026-09-08)

Train-covered MY fold-in vs `STRONG_OISST`. Cite: CMEMS `OCEANCOLOUR_ATL_BGC_L4_MY_009_118`.

| Item | Value |
| --- | --- |
| `oc_chl_daily` | **207** locs · **1997-10-01 → 2026-08-31** · **2.18M** rows |
| Coverage by split | train/val/test ~**99.3–99.5%** (`hard_block=false`) |
| STRONG test cal PR-AUC | **0.295** |
| STRONG+CHL test cal PR-AUC | **0.287** |
| Δ national | **−0.008** (apr–sep −0.004; Connemara −0.012) |
| `skill_claim` | **false** |
| `alert_pa` | **false** |
| Cork quote | **unchanged** (STRONG_OISST ~0.295) |

Gate/metrics: `data/processed/chl_ablation_gate.json`, `data/processed/chl_ablation_metrics.json`.

**Do not overwrite** `oc_chl_daily` without coordinating with Gatekeeper — ablation already used this merge.

