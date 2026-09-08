# CPR MBA ablation vs strong Dinophysis baseline

**Generated:** 2026-09-08 09:38 UTC  
**Target:** `y_dinophysis_nowcast`  
**Protocol:** AOI x ISO-week left-join; optional nearest <=100 km same ISO week; never HAB labels as CPR features.

## Coverage

| Feature / set | Coverage % |
| --- | ---: |
| `cpr_aoi_n_samples` | 28.203 |
| `cpr_aoi_mean_large_copepods` | 28.203 |
| `cpr_aoi_mean_small_copepods` | 28.203 |
| `cpr_aoi_mean_diatoms` | 28.203 |
| `cpr_aoi_mean_dinoflagellates` | 28.203 |
| `cpr_aoi_pci` | 28.203 |
| `cpr_aoi_dino_diatom_ratio` | 25.241 |
| `cpr_near_dist_km` | 0.0 |
| `cpr_near_mean_large_copepods` | 0.0 |
| `cpr_near_mean_small_copepods` | 0.0 |
| `cpr_near_mean_diatoms` | 0.0 |
| `cpr_near_mean_dinoflagellates` | 0.0 |
| `cpr_near_pci` | 0.0 |
| `any_cpr_aoi` | 28.203 |
| `any_cpr_nearest100` | 0.0 |

## Results (LightGBM calibrated test PR-AUC)

| Setting | n_feat | test PR-AUC | clim | PR skill | Brier skill |
| --- | ---: | ---: | ---: | ---: | ---: |
| strong | 9 | 0.2845 | nan | nan | 0.0006 |
| strong+CPR_AOI | 16 | 0.2904 | nan | nan | -0.0018 |
| strong+CPR_nearest100 | 15 | 0.2845 | nan | nan | 0.0006 |
| strong+CPR_AOI+nearest100 | 22 | 0.2904 | nan | nan | -0.0018 |

## Caveats

- CPR `Mean_Dinoflagellates` is **not** Dinophysis (Ceratium-heavy aggregate).
- Connemara AOI has **0** CPR tows; stations there join via `western_shelf` / other primary AOI.
- Sparse western_shelf CPR (few tows) -> low AOI coverage for west-coast stations.
- Nearest-100 km join is best-effort and week-sparse offshore.

Metrics JSON: `data/processed/cpr_ablation_metrics.json`

