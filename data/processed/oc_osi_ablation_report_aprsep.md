# OC/OSI ablation vs STRONG_OISST (apr_sep)

Joined: `/workspace/pa-marine-model/data/processed/joined_features_oc_osi.parquet`
Apr–Sep: **True**  Connemara: **False**
Chl features: ['chl', 'chl_lag0d', 'chl_lag7d', 'chl_log1p', 'chl_log1p_lag0d', 'chl_log1p_roll14d', 'chl_log1p_roll30d', 'chl_roll14d', 'chl_roll30d', 'chl_roll7d']
OSI features: ['osi_minus_oisst', 'osi_sst_n_clear', 'osi_sst_week']

| Config | n_feat | LGBM test cal PR-AUC | Δ vs strong |
| --- | ---: | ---: | ---: |
| STRONG_OISST | 9 | 0.29042271571127914 | 0.0 |
| STRONG+OSI | 12 | 0.2496685023771441 | -0.04075421333413504 |
| STRONG+CHL | 19 | 0.2866433879768969 | -0.0037793277343822207 |
| STRONG+CHL+OSI | 22 | 0.2822691881242381 | -0.00815352758704102 |

Lean LGBM-only run. Numbers from this run only.
JSON: `data/processed/oc_osi_ablation_metrics_aprsep.json`
