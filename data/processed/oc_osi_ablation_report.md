# Ocean colour + OSI/ODYSSEA ablation — Irish Dinophysis (full Chl)

**Generated:** 2026-09-08 (Europe/Dublin).  
**Target:** `y_dinophysis_nowcast`. Baseline `STRONG_OISST`. Chl coverage=0.993.

## Verdict

Chl/OSI extras **do not beat** STRONG_OISST nationally (best delta=+0.0000 at strong).

| config | n_feat | val cal PR-AUC | test cal PR-AUC | Δ vs strong |
| --- | ---: | ---: | ---: | ---: |
| `strong` | 9 | 0.5428 | 0.2953 | +0.0000 |
| `strong_chl` | 19 | 0.5352 | 0.2833 | -0.0120 |
| `strong_osi` | 12 | 0.5671 | 0.2764 | -0.0189 |
| `strong_chl_osi` | 22 | 0.5603 | 0.2850 | -0.0103 |

JSON: `data/processed/oc_osi_ablation_metrics.json`.
