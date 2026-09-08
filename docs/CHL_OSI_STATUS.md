# Status: OC Chl + OSI SAF / ODYSSEA SST fold-in

**Updated:** 2026-09-08 12:25 IST
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

**Next step:** full-history Chl station-week extract + ablation vs `STRONG_OISST` — not more SST ARCO hunting.

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

**Lane:** ODYSSEA/OSI predictive parked (Cork narrative only). Active open driver = **Chl MY** fill (2003–2017 ARCO in progress → week handoff to Gatekeeper).

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

Mace Head / Lehanagh Pool remain in `configs/default.yaml` sentinel block; Chl pilot snaps to 5 stations only. ODYSSEA covers all 207 HAB `location_id`s for **2018-01-01 → 2026-09-06** (lat 51.47–55.28, lon −10.57…−6.03); product start prevents full 2003–2018 train.
