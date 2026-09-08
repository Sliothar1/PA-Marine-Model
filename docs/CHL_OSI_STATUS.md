# Status: OC Chl + OSI SAF / ODYSSEA SST fold-in

**Updated:** 2026-09-08 12:47 IST
**Repo:** `/workspace/pa-marine-model` (github.com/Sliothar1/PA-Marine-Model)

## Cork weekend lock (PA + Dev, 2026-09-08)

**Predictive Chl / ODYSSEA / OSI SAF closed for Cork.** No further Cork national ablation cycles.

| Lane | Cork use |
| --- | --- |
| **Spine** | `STRONG_OISST` ~**0.295** test cal PR-AUC only |
| **Narrative** | June 2023 onion (Met / ODYSSEA DOI 10.48670/moi-00152 descriptive SST / heatwave context) |
| ODYSSEA provider-swap | parked — exploratory Δ=−0.074; `hard_block`; label `exploratory_short_history_not_cork_spine` |
| Chl MY add-on | parked predictive — train covered but Δ=−0.008 (national); no skill claim |
| OSTIA | already lost (~0.24 vs ~0.295); keep OISST default |

Climate Drivers remaining work (if any): descriptive context only — not Cork national skill hunts.

## Product choices

| Layer | Choice | IDs / path |
| --- | --- | --- |
| **OC Chl** | Atlantic GlobColour L4 **gap-free** daily CHL | Product `OCEANCOLOUR_ATL_BGC_L4_MY_009_118` · dataset `cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D` · var `CHL` |
| **OSI-proxy SST** | ODYSSEA L4 (OSI SAF inputs) via ARCO | Product `SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025` · dataset `IFREMER-ATL-SST-L4-NRT-OBS_FULL_TIME_SERIE` · col `osi_sst` |
| Preferred OSI SAF (blocked) | OSI-202-c NAR L3C Metop-B | GHRSST `AVHRR_SST_METOP_B_NAR-OSISAF-L3C-v1.0` — Earthdata/FTP not available on box |

## ARCO workaround (auth TLS blocker)

- `auth.marine.copernicus.eu` TLS still fails from this box (`SSL UNEXPECTED_EOF`).
- **Download path:** `scripts/download_oc_chl.py` tries copernicusmarine first; on auth/TLS failure (or `--prefer-arco`) falls back to public CloudFerro ARCO zarr (`zarr_format=2`).
- Chl ARCO: `https://s3.waw3-1.cloudferro.com/mdl-arco-time-042/arco/OCEANCOLOUR_ATL_BGC_L4_MY_009_118/cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D_202603/timeChunked.zarr`
- ODYSSEA ARCO: `https://s3.waw3-1.cloudferro.com/mdl-arco-time-045/arco/SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025/IFREMER-ATL-SST-L4-NRT-OBS_FULL_TIME_SERIE_201904/timeChunked.zarr`
- Module: `src/pa_marine/oc_chl.py` (`download_oc_chl_via_arco` / `download_oc_chl_for_stations`).
- ODYSSEA helper: `src/pa_marine/osi_saf_sst.py` (`download_odyssea_for_stations` / `ODYSSEA_ARCO_TIMECHUNKED`).

## Paths on disk

| Path | Role |
| --- | --- |
| `data/raw/oc_chl_daily.parquet` | Station-pixel daily Chl (`location_id,date,chl,chl_log1p`) |
| `data/raw/oc_chl_daily_meta.json` | Extract meta |
| `data/raw/osi_saf_sst/osi_sst_daily.parquet` | ODYSSEA daily as `osi_sst` |
| `data/raw/osi_saf_sst/osi_sst_daily_meta.json` | ODYSSEA meta (1× 2018-Q4 chunk 403 skipped) |
| `data/processed/joined_features_oc_osi.parquet` | Week join |
| `data/processed/oc_osi_join_summary.json` | Coverage summary |
| `data/processed/oc_osi_ablation_metrics.json` (+ `_aprsep`, `_connemara`) | Ablation metrics |
| `data/processed/oc_osi_ablation_report.md` (+ `_aprsep`, `_connemara`) | Ablation reports |

## Coverage (week-panel after join)

Chl note: National ARCO Chl attached: stations=207 train_cov=0.994 test_cov=0.994 all_cov=0.993.

| Split | Chl coverage | OSI/`osi_sst_week` coverage |
| --- | ---: | ---: |
| train | 0.9935 (29491/29683) | 0.1130 (3354/29683) |
| val | 0.9938 (9132/9189) | 1.0000 (9189/9189) |
| test | 0.9945 (14191/14270) | 1.0000 (14270/14270) |
| all | 0.9933 (52814/53172) | 0.5043 (26813/53172) |

Chl daily rows≈1789308 stations=207. Honesty gate: test Chl coverage ≫ 5% → national ablation is a real coverage claim (not fillna(0) noise).

## Ablation — LGBM test cal PR-AUC vs STRONG_OISST

Baseline reminder: strong ~0.293 historically; this run strong national = **0.295299**.

### National

| Config | n_feat | test cal PR-AUC | Δ vs strong |
| --- | ---: | ---: | ---: |
| STRONG_OISST | 9 | 0.295299 | 0.000000 |
| STRONG+OSI | 12 | 0.266238 | -0.029061 |
| STRONG+CHL | 19 | 0.287365 | -0.007934 |
| STRONG+CHL+OSI | 22 | 0.290342 | -0.004957 |

### Apr–Sep

| Config | n_feat | test cal PR-AUC | Δ vs strong |
| --- | ---: | ---: | ---: |
| STRONG_OISST | 9 | 0.290423 | 0.000000 |
| STRONG+OSI | 12 | 0.249669 | -0.040754 |
| STRONG+CHL | 19 | 0.286643 | -0.003779 |
| STRONG+CHL+OSI | 22 | 0.282269 | -0.008154 |

### Connemara (53.2–53.7N, 10.2–9.4W)

| Config | n_feat | test cal PR-AUC | Δ vs strong |
| --- | ---: | ---: | ---: |
| STRONG_OISST | 9 | 0.078124 | 0.000000 |
| STRONG+OSI | 12 | 0.068838 | -0.009286 |
| STRONG+CHL | 19 | 0.066507 | -0.011617 |
| STRONG+CHL+OSI | 22 | 0.070960 | -0.007164 |

## Verdict

- **National:** best Δ = -0.004957 → **worse** (no lift).
- **Apr–Sep:** best Δ = -0.003779 → **worse** (no lift).
- **Connemara:** best Δ = -0.007164 → **worse** (no lift; absolute PR-AUC low on small AOI).
- **Δ>0?** No on any slice.
- **Alert PA?** **No** — no Δ>0 lift; coverage not a hard block (test Chl/OSI ≈99–100%).
- Cork/hard block: none from this fold-in.

## Scripts / modules

| Path | Role |
| --- | --- |
| `src/pa_marine/oc_chl.py` | CMEMS + ARCO Chl download |
| `src/pa_marine/osi_saf_sst.py` | OSI SAF helpers + ODYSSEA ARCO |
| `scripts/download_oc_chl.py` | CLI (`--prefer-arco`) |
| `scripts/join_oc_osi_week.py` | Week join |
| `scripts/oc_osi_ablation.py` | Ablation (+ `--apr-sep`, `--connemara`) |

**Not touched:** `docs/CPR_MBA.md`.

Numbers above are from this Prediction Gatekeeper run only — do not invent metrics.
