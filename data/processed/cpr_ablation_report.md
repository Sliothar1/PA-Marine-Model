# CPR MBA ablation vs strong Dinophysis baseline

**Generated:** 2026-09-08 09:50 UTC  
**Target:** `y_dinophysis_nowcast`  
**Protocol:** AOI × ISO-week left-join; optional nearest ≤100 km same ISO week; never HAB labels as CPR features.

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
| `cpr_near_dist_km` | 3.987 |
| `cpr_near_mean_large_copepods` | 3.987 |
| `cpr_near_mean_small_copepods` | 3.987 |
| `cpr_near_mean_diatoms` | 3.987 |
| `cpr_near_mean_dinoflagellates` | 3.987 |
| `cpr_near_pci` | 3.987 |
| `any_cpr_aoi` | 28.203 |
| `any_cpr_nearest100` | 3.987 |

## Results (LightGBM calibrated test PR-AUC)

| Setting | n_feat | test PR-AUC | clim | PR skill | Brier skill |
| --- | ---: | ---: | ---: | ---: | ---: |
| strong | 9 | 0.2987 | 0.1831 | 0.1414 | 0.0086 |
| strong+CPR_AOI | 16 | 0.2838 | 0.1831 | 0.1232 | -0.0106 |
| strong+CPR_nearest100 | 15 | 0.2925 | 0.1831 | 0.1338 | -0.0038 |
| strong+CPR_AOI+nearest100 | 22 | 0.2915 | 0.1831 | 0.1326 | -0.0022 |

## Caveats

- CPR `Mean_Dinoflagellates` is **not** Dinophysis (Ceratium-heavy aggregate).
- Connemara AOI has **0** CPR tows; stations there join via `western_shelf` / other primary AOI.
- Sparse western_shelf CPR (few tows) → low AOI coverage for west-coast stations.
- Nearest-100 km coverage is ~4%; treat any metric bump cautiously.
- Honest takeaway: CPR AOI add-on ≈ flat vs strong nationally.

Metrics JSON: `data/processed/cpr_ablation_metrics.json`

