# Irish Dinophysis: IBI light/MLD + richer MHW ablations

Generated: 2026-09-01 (Europe/Dublin). Target: `y_dinophysis_nowcast`.
Joined: `/workspace/pa-marine-model/data/processed/joined_features_ibi.parquet` (53172 rows). MHW source: `/workspace/pa-marine-model/data/processed/mhw_daily_enriched.parquet`.
Runtime ~30s.

## Context

- Prior best: OISST + strong features + val calibration → test PR-AUC ~**0.293**.
- OSTIA alone was worse (~0.24); OISST remains the SST default.
- This run keeps strong OISST and adds continuous MHW intensity + IBI MLD/light (and SSS/currents if downloaded).

## Ablation table (LightGBM; val-only auto calibration)

| ablation | n_feat | val PR raw | val PR cal | test PR raw | test PR cal | test PR skill cal | Δ vs strong |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strong_oisst | 9 | 0.553 | 0.543 | 0.306 | **0.293** | 0.135 | +0.000 |
| strong_rich_mhw_top3 | 12 | 0.556 | 0.546 | 0.303 | **0.292** | 0.133 | -0.001 |
| strong_rich_mhw_lean | 18 | 0.555 | 0.546 | 0.297 | **0.287** | 0.127 | -0.007 |
| strong_rich_mhw | 38 | 0.557 | 0.546 | 0.300 | **0.282** | 0.121 | -0.012 |
| strong_ibi_mld_light | 31 | 0.518 | 0.509 | 0.199 | **0.195** | 0.014 | -0.098 |
| strong_rich_mhw_lean_ibi | 40 | 0.523 | 0.511 | 0.201 | **0.192** | 0.011 | -0.102 |
| strong_rich_mhw_ibi | 60 | 0.528 | 0.517 | 0.197 | **0.188** | 0.006 | -0.105 |
| strong_rich_mhw_ibi_full | 75 | 0.527 | 0.518 | 0.202 | **0.194** | 0.014 | -0.099 |

**Best calibrated test PR-AUC:** `strong_oisst` = **0.2933** (strong OISST 0.2933; Δ = +0.0000).

## What helped

- Improved: none meaningfully above strong OISST
- Flat: `strong_rich_mhw_top3` Δ=-0.0015 (test cal PR-AUC 0.2918, n=12)
- Hurt: `strong_rich_mhw_lean` Δ=-0.0066 (test cal PR-AUC 0.2867, n=18), `strong_rich_mhw` Δ=-0.0115 (test cal PR-AUC 0.2817, n=38), `strong_ibi_mld_light` Δ=-0.0983 (test cal PR-AUC 0.1950, n=31), `strong_rich_mhw_lean_ibi` Δ=-0.1015 (test cal PR-AUC 0.1917, n=40), `strong_rich_mhw_ibi` Δ=-0.1052 (test cal PR-AUC 0.1881, n=60), `strong_rich_mhw_ibi_full` Δ=-0.0990 (test cal PR-AUC 0.1943, n=75)

## Top LightGBM gain (best mode)

| rank | feature | gain_pct |
| --- | --- | ---: |
| 1 | `woy_cos` | 38.44 |
| 2 | `latitude` | 25.57 |
| 3 | `woy_sin` | 12.74 |
| 4 | `longitude` | 9.30 |
| 5 | `sst` | 5.08 |
| 6 | `sst_lag21d` | 2.84 |
| 7 | `sst_roll7d` | 2.79 |
| 8 | `sst_roll30d` | 2.48 |
| 9 | `sst_lag0d` | 0.75 |

## Honest takeaways

- **Best remains strong OISST** (9 features): calibrated test PR-AUC **0.293**. No ablation beat it by >0.002.
- **Richer MHW** (continuous intensity / category / days-since / SSTA percentile): lean packs are ~flat to mildly worse; dumping many correlated MHW columns hurts (~−0.01). A 3-feature intensity add is essentially flat (Δ≈−0.0015).
- **IBI MLD + light (`mlotst`, `rsntds`, `kd`, `zeu`) hurt** on the full test (~−0.10 PR-AUC). Null physics after the IBI product end date amplifies the damage; after extending IBI to **2026-05-19** and using a coverage-matched subset, IBI still underperforms strong OISST by ~**−0.013** PR-AUC. Single-feature adds of MLD/light all reduced test PR-AUC.
- **SSS + detided currents** (`so`, `uo`, `vo`, `current_speed`) in the full pack do not recover performance (still ~−0.10 vs strong).
- Seasonal Fourier + geography still dominate LightGBM gain; coastal Dinophysis signal is not yet helped by these IBI fields at station-week resolution.
- Keep OISST as SST default; IBI physics/light are downloaded and joinable but **not** default features until a better transform/target pairing is found.

## Data notes

- SST/MHW: NOAA OISST station series; Hobday events retained; added continuous intensity (`mhw_intensity`, `mhw_max_intensity`, `mhw_cum_intensity`), `mhw_i_ratio` / category I–IV, `days_since_mhw`, `ssta_pctile`.
- IBI PHY `IBI_MULTIYEAR_PHY_005_002`: `mlotst`, `rsntds` (+ `so`, detided `uo`/`vo` when downloaded).
- IBI BGC `IBI_MULTIYEAR_BGC_005_003` optics: surface `kd`, `zeu` as light proxies (preferred over 1 km OC L3 KD490 volume).
- Downloads are station-pixel / unique-grid extracts (not full Irish NetCDF cubes); parquet under `data/` is gitignored.

## Coverage-matched IBI subset

IBI multi-year currently ends **2026-05-19**. Full-test rows after that (and previously when IBI was capped at 2024-12-31) have null physics and can crash PR-AUC if those features are used. Table below restricts train/val/test to weeks with non-null `mlotst` so IBI vs strong is fair.

| ablation | n_feat | test PR cal | n_test | Δ vs strong (cov) |
| --- | ---: | ---: | ---: | ---: |
| cov_strong_oisst | 9 | **0.235** | 13496 | +0.000 |
| cov_strong_rich_mhw_top3 | 12 | **0.234** | 13496 | -0.001 |
| cov_strong_ibi_mld_light | 31 | **0.223** | 13496 | -0.013 |
| cov_strong_rich_mhw_lean_ibi | 40 | **0.220** | 13496 | -0.015 |

## Artifacts

- Report: `/workspace/pa-marine-model/data/processed/ibi_light_mhw_report.md`
- Ablation JSON: `/workspace/pa-marine-model/data/processed/ibi_ablation_metrics.json`
- Best-mode metrics: `/workspace/pa-marine-model/data/processed/metrics_dino_ibi.json`
- Joined features: `/workspace/pa-marine-model/data/processed/joined_features_ibi.parquet`

