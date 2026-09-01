# Dinophysis feature importance & ablations

Generated: 2026-09-01 (Europe/Dublin). Target: `y_dinophysis_nowcast`.
Joined features: `/workspace/pa-marine-model/data/processed/joined_features.parquet` (53172 rows). Runtime ~23s.

## Baseline (LightGBM, all joined features)

- Val PR-AUC raw/cal: **0.538** / **0.534**
- Test PR-AUC raw/cal: **0.295** / **0.281** (clim 0.183; PR skill cal **0.120**)
- Test Brier skill raw → cal: -1.152 → **-0.006**

## LightGBM gain importance (train fit)

| rank | feature | gain_pct | split_count |
| --- | --- | ---: | ---: |
| 1 | `woy_cos` | 37.41 | 448 |
| 2 | `latitude` | 23.72 | 1165 |
| 3 | `woy_sin` | 12.62 | 558 |
| 4 | `longitude` | 8.77 | 951 |
| 5 | `sst` | 2.33 | 234 |
| 6 | `ssta_roll30d` | 1.60 | 297 |
| 7 | `sst_roll7d` | 1.27 | 164 |
| 8 | `sst_lag21d` | 1.26 | 199 |
| 9 | `sst_lag0d` | 1.13 | 44 |
| 10 | `sst_roll30d` | 1.11 | 160 |
| 11 | `ssta_lag14d` | 1.10 | 239 |
| 12 | `ssta_roll14d` | 1.09 | 215 |
| 13 | `ssta` | 0.91 | 169 |
| 14 | `ssta_roll7d` | 0.91 | 168 |
| 15 | `sst_roll14d` | 0.78 | 127 |
| 16 | `sst_lag14d` | 0.75 | 143 |
| 17 | `sst_lag7d` | 0.71 | 146 |
| 18 | `ssta_lag21d` | 0.67 | 156 |
| 19 | `ssta_lag7d` | 0.65 | 140 |
| 20 | `mhw_cum_intensity_roll30d` | 0.41 | 83 |
| 21 | `in_mhw_roll30d` | 0.22 | 46 |
| 22 | `mhw_duration_roll30d` | 0.17 | 40 |
| 23 | `ssta_lag0d` | 0.14 | 27 |
| 24 | `mhw_cum_intensity_roll14d` | 0.08 | 24 |
| 25 | `in_mhw_roll14d` | 0.04 | 7 |
| 26 | `mhw_duration_lag21d` | 0.03 | 6 |
| 27 | `mhw_cum_intensity` | 0.02 | 5 |
| 28 | `mhw_cum_intensity_roll7d` | 0.02 | 4 |
| 29 | `mhw_duration_roll14d` | 0.02 | 7 |
| 30 | `mhw_cum_intensity_lag21d` | 0.01 | 5 |
| 31 | `mhw_duration_lag14d` | 0.01 | 4 |
| 32 | `in_mhw_roll7d` | 0.01 | 5 |
| 33 | `mhw_cum_intensity_lag7d` | 0.01 | 4 |
| 34 | `mhw_cum_intensity_lag14d` | 0.01 | 3 |
| 35 | `mhw_duration_lag7d` | 0.00 | 2 |
| 36 | `mhw_duration_roll7d` | 0.00 | 1 |
| 37 | `in_mhw_lag21d` | 0.00 | 1 |
| 38 | `mhw_duration` | 0.00 | 1 |
| 39 | `mhw_cum_intensity_lag0d` | 0.00 | 1 |
| 40 | `in_mhw_lag14d` | 0.00 | 1 |
| 41 | `in_mhw` | 0.00 | 0 |
| 42 | `mhw_duration_lag0d` | 0.00 | 0 |
| 43 | `in_mhw_lag0d` | 0.00 | 0 |
| 44 | `in_mhw_lag7d` | 0.00 | 0 |

## Permutation importance (val, scoring=average_precision, 8 repeats)

| rank | feature | perm_mean ΔPR-AUC | perm_std |
| --- | --- | ---: | ---: |
| 1 | `woy_cos` | 0.3159 | 0.0083 |
| 2 | `latitude` | 0.2506 | 0.0093 |
| 3 | `woy_sin` | 0.0439 | 0.0101 |
| 4 | `longitude` | 0.0401 | 0.0043 |
| 5 | `sst` | 0.0095 | 0.0027 |
| 6 | `sst_roll14d` | 0.0068 | 0.0014 |
| 7 | `sst_roll7d` | 0.0062 | 0.0023 |
| 8 | `sst_lag21d` | 0.0054 | 0.0018 |
| 9 | `sst_lag0d` | 0.0011 | 0.0016 |
| 10 | `in_mhw_roll14d` | 0.0007 | 0.0008 |
| 11 | `sst_roll30d` | 0.0005 | 0.0014 |
| 12 | `in_mhw_roll7d` | 0.0001 | 0.0006 |
| 13 | `mhw_duration_roll30d` | 0.0001 | 0.0010 |
| 14 | `mhw_cum_intensity_lag7d` | 0.0000 | 0.0003 |
| 15 | `in_mhw_lag14d` | 0.0000 | 0.0000 |
| 16 | `mhw_duration` | 0.0000 | 0.0000 |
| 17 | `in_mhw` | 0.0000 | 0.0000 |
| 18 | `mhw_duration_lag0d` | 0.0000 | 0.0000 |
| 19 | `in_mhw_lag7d` | 0.0000 | 0.0000 |
| 20 | `in_mhw_lag0d` | 0.0000 | 0.0000 |
| 21 | `ssta_roll14d` | -0.0000 | 0.0017 |
| 22 | `in_mhw_lag21d` | -0.0000 | 0.0000 |
| 23 | `mhw_duration_lag21d` | -0.0000 | 0.0000 |
| 24 | `mhw_cum_intensity_lag21d` | -0.0000 | 0.0001 |
| 25 | `mhw_cum_intensity_lag0d` | -0.0000 | 0.0000 |
| 26 | `mhw_duration_roll7d` | -0.0000 | 0.0000 |
| 27 | `mhw_cum_intensity` | -0.0001 | 0.0000 |
| 28 | `mhw_duration_lag7d` | -0.0001 | 0.0000 |
| 29 | `mhw_duration_roll14d` | -0.0002 | 0.0003 |
| 30 | `mhw_duration_lag14d` | -0.0003 | 0.0001 |
| 31 | `ssta_roll30d` | -0.0003 | 0.0015 |
| 32 | `mhw_cum_intensity_lag14d` | -0.0005 | 0.0000 |
| 33 | `ssta_lag0d` | -0.0007 | 0.0004 |
| 34 | `mhw_cum_intensity_roll30d` | -0.0014 | 0.0008 |
| 35 | `sst_lag14d` | -0.0016 | 0.0012 |
| 36 | `mhw_cum_intensity_roll7d` | -0.0016 | 0.0001 |
| 37 | `in_mhw_roll30d` | -0.0020 | 0.0007 |
| 38 | `ssta` | -0.0021 | 0.0010 |
| 39 | `sst_lag7d` | -0.0024 | 0.0013 |
| 40 | `ssta_roll7d` | -0.0027 | 0.0010 |
| 41 | `ssta_lag21d` | -0.0028 | 0.0008 |
| 42 | `mhw_cum_intensity_roll14d` | -0.0034 | 0.0006 |
| 43 | `ssta_lag7d` | -0.0038 | 0.0013 |
| 44 | `ssta_lag14d` | -0.0049 | 0.0019 |

### Takeaways from importance
- Top gain: `woy_cos`, `latitude`, `woy_sin`, `longitude`, `sst`
- Top permutation: `woy_cos`, `latitude`, `woy_sin`, `longitude`, `sst`
- Seasonal Fourier (`woy_sin`/`woy_cos`) and geography usually dominate; SST/SSTA rolls/lags add modest discrimination beyond climatology.

## Ablations (LightGBM; val-only isotonic/sigmoid calibration)

| ablation | n_feat | val PR raw | val PR cal | test PR raw | test PR cal | test PR skill cal | test Brier skill cal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_all | 44 | 0.538 | 0.534 | 0.295 | 0.281 | 0.120 | -0.006 |
| drop_weak_gain_perm | 9 | 0.553 | 0.543 | 0.306 | 0.293 | 0.135 | -0.012 |
| sst_ssta_woy_geo | 20 | 0.543 | 0.537 | 0.301 | 0.292 | 0.133 | -0.006 |
| lags_0_3_7_14_rolls_7_14 | 39 | 0.547 | 0.536 | 0.290 | 0.279 | 0.117 | -0.006 |

**Best calibrated test PR-AUC:** `drop_weak` = **0.293** (baseline 0.281; Δ = +0.013).

### Ablation notes
- **drop_weak**: removed features with gain_pct < 1% or non-positive permutation mean (kept {'longitude', 'woy_cos', 'woy_sin', 'latitude'}). Dropped: `in_mhw`, `in_mhw_lag0d`, `in_mhw_lag14d`, `in_mhw_lag21d`, `in_mhw_lag7d`, `in_mhw_roll14d`, `in_mhw_roll30d`, `in_mhw_roll7d`, `mhw_cum_intensity`, `mhw_cum_intensity_lag0d`, `mhw_cum_intensity_lag14d`, `mhw_cum_intensity_lag21d`, `mhw_cum_intensity_lag7d`, `mhw_cum_intensity_roll14d`, `mhw_cum_intensity_roll30d`, `mhw_cum_intensity_roll7d`, `mhw_duration`, `mhw_duration_lag0d`, `mhw_duration_lag14d`, `mhw_duration_lag21d`, `mhw_duration_lag7d`, `mhw_duration_roll14d`, `mhw_duration_roll30d`, `mhw_duration_roll7d`, `sst_lag14d`, `sst_lag7d`, `sst_roll14d`, `ssta`, `ssta_lag0d`, `ssta_lag14d`, `ssta_lag21d`, `ssta_lag7d`, `ssta_roll14d`, `ssta_roll30d`, `ssta_roll7d`
- **sst_ssta_woy_geo**: dropped all `in_mhw*` / `mhw_duration*` / `mhw_cum_intensity*` columns.
- **lags_0_3_7_14_rolls_7_14**: rebuilt from `mhw_daily.parquet` (no OISST re-download); denser short lags, dropped lag21 and roll30.
- **Wind:** Skipped wind proxies: no local ERA5; Open-Meteo archive for 207 stations × ~24 y daily would exceed the 30‑min cheap-source budget. Revisit with CDS/ERA5 single-level u10/v10 at station pixels if credentials available.

## What improved / what didn't
- Improved: drop_weak (ΔPR-AUC cal +0.013), sst_ssta_only (ΔPR-AUC cal +0.011)
- Did not help / flat: lag_tweak (ΔPR-AUC cal -0.002)

## Artifacts

- Report: `/workspace/pa-marine-model/data/processed/dino_feature_report.md`
- Ablation metrics JSON: `/workspace/pa-marine-model/data/processed/dino_ablation_metrics.json`
- Full multi-taxon metrics remain in `data/processed/metrics.json`

**Best next lever:** replace 0.25° OISST with Copernicus **OSTIA 0.05° (~5 km)** SST at station pixels (and/or add ERA5 wind) — coastal Dinophysis is poorly resolved at OISST scale.
