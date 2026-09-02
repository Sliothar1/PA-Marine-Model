# Climate drivers ablation — Irish Dinophysis nowcast

**Generated:** 2026-09-02 (Europe/Dublin).  
**Target:** `y_dinophysis_nowcast`. **Model headline:** LightGBM test calibrated PR-AUC.
**Baseline:** strong 9-feature OISST (`STRONG_OISST`).

## Verdict

Climate extras **do not beat** strong nationally (best delta=+0.0000 at strong). Consistent with ERA5 wind failure: single-point Met / regional Q / year warming proxy add little beyond SST seasonality for Irish Dinophysis.

## Coverage caveats

- Met radiation/sunshine is **point/regional west-coast** (Mace Head / Belmullet / composite), broadcast to all Irish HAB stations — sparse spatially for a national panel.
- River Q is **Galway Bay / Connemara** (Owenboliskey 31075, Corrib 30061), not national.
- Warming features are **year-level** June SST anomaly / decade proxy — collinear with SST seasonality.

### Feature non-null fractions (after left join)

| feature | fraction non-null |
| --- | ---: |
| `Q_30031` | 0.892 |
| `Q_30031_lag1w` | 0.893 |
| `Q_30031_log1p` | 0.892 |
| `Q_30061` | 0.803 |
| `Q_30061_lag1w` | 0.804 |
| `Q_30061_log1p` | 0.803 |
| `Q_31075` | 0.763 |
| `Q_31075_lag1w` | 0.762 |
| `Q_31075_log1p` | 0.763 |
| `june_sst_clim_anom` | 1.000 |
| `june_sst_trend_residual` | 1.000 |
| `met_belmullet_glorad` | 0.962 |
| `met_belmullet_sun` | 0.962 |
| `met_glorad` | 0.996 |
| `met_glorad_lag1w` | 0.996 |
| `met_glorad_roll4w` | 0.996 |
| `met_mace_glorad` | 0.975 |
| `met_sun` | 0.962 |
| `met_sun_lag1w` | 0.962 |
| `met_wdsp` | 0.981 |
| `met_west_glorad` | 0.996 |
| `warming_year_decade` | 1.000 |

## Results table

| config | n_feat | LGBM val cal PR-AUC | LGBM test cal PR-AUC | Δ test vs strong |
| --- | ---: | ---: | ---: | ---: |
| `strong` | 9 | 0.5428 | 0.2953 | +0.0000 |
| `strong_met_rad` | 15 | 0.5487 | 0.2533 | -0.0420 |
| `strong_river_Q` | 12 | 0.5533 | 0.2490 | -0.0463 |
| `strong_warming` | 12 | 0.5607 | 0.2941 | -0.0012 |
| `strong_met_river` | 18 | 0.5511 | 0.2404 | -0.0549 |
| `strong_climate_all` | 21 | 0.5744 | 0.2852 | -0.0101 |

Full JSON: `data/processed/climate_drivers_ablation_metrics.json`.
Elapsed: 3.8 s.
