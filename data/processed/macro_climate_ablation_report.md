# Macro climate (NAO / EA / AMO) ablation — Irish Dinophysis nowcast

**Generated:** 2026-09-02 (Europe/Dublin).  
**Target:** `y_dinophysis_nowcast`. **Headline:** LightGBM test calibrated PR-AUC.
**Baseline:** strong 9-feature OISST (`STRONG_OISST`).

## Verdict

NAO/EA/AMO lags **do not beat** strong nationally (best delta=+0.0000 at strong). Use for explanatory / Cork narrative, not as a national feature upgrade.

## Coverage (left-join on iso_year, iso_week)

| feature | fraction non-null |
| --- | ---: |
| `amo` | 0.996 |
| `amo_lag1m` | 0.996 |
| `amo_lag3m` | 0.996 |
| `amo_roll3m` | 0.996 |
| `ea` | 0.996 |
| `ea_lag1m` | 0.996 |
| `ea_lag2m` | 0.996 |
| `nao` | 0.996 |
| `nao_daily_mean` | 1.000 |
| `nao_daily_mean_lag1w` | 1.000 |
| `nao_lag1m` | 0.996 |
| `nao_lag2m` | 0.996 |

## Results

| config | n_feat | LGBM val cal PR-AUC | LGBM test cal PR-AUC | Δ test vs strong |
| --- | ---: | ---: | ---: | ---: |
| `strong` | 9 | 0.5428 | 0.2953 | +0.0000 |
| `strong_nao_ea` | 17 | 0.5511 | 0.2905 | -0.0048 |
| `strong_amo` | 13 | 0.5381 | 0.2572 | -0.0381 |
| `strong_nao_ea_amo` | 21 | 0.5487 | 0.2711 | -0.0242 |
| `nao_ea_only` | 8 | 0.1747 | 0.0558 | -0.2395 |

Indices from `scripts/ingest_climate_indices.py` → `data/processed/climate_indices_week.csv`.
Full JSON: `data/processed/macro_climate_ablation_metrics.json`. Elapsed: 3.1 s.
