# CPR MBA ablation vs strong Dinophysis baseline

**Generated:** 2026-09-08T09:47:48.094259+00:00 (UTC)  
**Target:** `y_dinophysis_nowcast`  
**This run:** AOI × ISO-week join (`--skip-nearest`).

## Coverage

| Set | Coverage % |
| --- | ---: |
| any_cpr_aoi | 28.203 |
| cpr_aoi_dino_diatom_ratio | 25.241 |
| any_cpr_nearest100 | 0.0 |

## LightGBM calibrated test PR-AUC

| Setting | n_feat | PR-AUC | clim | PR skill | Brier skill |
| --- | ---: | ---: | ---: | ---: | ---: |
| strong | 9 | 0.2963 | 0.1831 | 0.1386 | 0.0024 |
| strong+CPR_AOI | 16 | 0.2856 | 0.1831 | 0.1254 | -0.0012 |
| strong+CPR_nearest100 | 15 | 0.2963 | 0.1831 | 0.1386 | 0.0024 |
| strong+CPR_AOI+nearest100 | 22 | 0.2856 | 0.1831 | 0.1254 | -0.0012 |

## Caveats

- CPR Mean_Dinoflagellates is **not** Dinophysis (Ceratium-heavy).
- Connemara = 0 CPR tows; western_shelf sparse (35).
- AOI add-on is essentially **flat** vs strong OISST at ~28% coverage; exploratory only.

See `docs/CPR_MBA.md`.
