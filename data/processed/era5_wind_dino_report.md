# Irish Dinophysis: ERA5 wind ablation (strong vs strong+wind)

Generated: 2026-09-01 (Europe/Dublin).
Joined: `data/processed/joined_features_era5.parquet` (53172 rows; train/val/test = 29683/9189/14270).
Protocol: same as `scripts/evaluate.py` — time split from config (train 2003–2018, val 2019–2021, test from 2022); LightGBM + val-only auto calibration (isotonic when enough positives).

## Feature sets

| mode | n_feat | features |
| --- | ---: | --- |
| `strong` | 9 | `woy_sin`, `woy_cos`, `latitude`, `longitude`, `sst`, `sst_lag0d`, `sst_lag21d`, `sst_roll7d`, `sst_roll30d` |
| `strong_era5_wind` | 18 | strong + `wind_speed`, `wind_alongshore`, `wind_crossshore` + each `*_roll7d` / `*_roll14d` |

Wind null rate ≈ 0% train/val; ≈ 0.34% test (LightGBM handles NaN; logreg median-imputes).

## Primary metric: LightGBM PR-AUC (before → after)

### Nowcast (`y_dinophysis_nowcast`)

| mode | n_feat | val PR raw | val PR cal | test PR raw | test PR cal | test PR skill cal | Δ test cal vs strong |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strong | 9 | 0.553020 | 0.543279 | 0.305870 | **0.293267** | 0.134817 | +0.000000 |
| strong_era5_wind | 18 | 0.556387 | 0.547062 | 0.296614 | **0.286963** | 0.127100 | -0.006304 |

- Strong OISST baseline test PR-AUC cal: **0.293267** (matches prior ~0.293).
- Strong + ERA5 wind test PR-AUC cal: **0.286963** (Δ = **-0.006304**).
- Clim PR-AUC (test): 0.183140. Prevalence test: 0.051787. n_test: 14270.
- Calibration method: isotonic (val-fit).

### Ahead-7 (`y_dinophysis_ahead7`)

| mode | n_feat | val PR raw | val PR cal | test PR raw | test PR cal | test PR skill cal | Δ test cal vs strong |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strong | 9 | 0.436808 | 0.434995 | 0.239062 | **0.231038** | 0.116555 | +0.000000 |
| strong_era5_wind | 18 | 0.431803 | 0.426272 | 0.234642 | **0.217812** | 0.101359 | -0.013226 |

- Strong test PR-AUC cal: **0.231038**.
- Strong + ERA5 wind test PR-AUC cal: **0.217812** (Δ = **-0.013226**).

## LogReg (sanity; same splits/calibration)

| target | mode | test PR raw | test PR cal |
| --- | --- | ---: | ---: |
| nowcast | strong | 0.244883 | 0.233329 |
| nowcast | strong_era5_wind | 0.252000 | 0.220559 |
| ahead7 | strong | 0.181678 | 0.164711 |
| ahead7 | strong_era5_wind | 0.182665 | 0.159386 |

## LightGBM gain (`strong_era5_wind`, nowcast train fit)

Seasonality/geo still dominate; wind rolls take modest mid-rank gain but do not lift hold-out PR-AUC.

| rank | feature | gain_pct (approx) |
| --- | --- | ---: |
| 1 | `woy_cos` | 38.5 |
| 2 | `latitude` | 20.4 |
| 3 | `woy_sin` | 9.1 |
| 4 | `longitude` | 7.3 |
| 5 | `wind_speed_roll14d` | 2.8 |
| 6 | `sst` | 2.5 |
| 7 | `wind_crossshore_roll14d` | 2.4 |
| 8 | `wind_alongshore_roll14d` | 2.4 |

## Honest takeaways

- **Best remains strong OISST (9 features)** on this parquet: calibrated test PR-AUC **0.293267** nowcast / **0.231038** ahead7.
- Adding ERA5 `wind_speed` / `wind_alongshore` / `wind_crossshore` (+ 7/14d rolls) **does not improve** Dinophysis discrimination: nowcast Δ **-0.006304**, ahead7 Δ **-0.013226**.
- Val PR-AUC for wind is slightly higher nowcast (in-sample/calibrator-adjacent), but test drops — classic mild overfit / noise dilution.
- Keep ERA5 wind joinable for future transforms (coast-oriented upwelling indices, event filters); do **not** add to the default strong set yet.

## How to reproduce

```bash
python scripts/evaluate.py \
  --joined data/processed/joined_features_era5.parquet \
  --feature-mode strong --horizon both --calibration auto \
  --out data/processed/metrics_dino_era5_strong.json

python scripts/evaluate.py \
  --joined data/processed/joined_features_era5.parquet \
  --feature-mode strong_era5_wind --horizon both --calibration auto \
  --out data/processed/metrics_dino_era5_wind.json
```

## Artifacts

- Report: `data/processed/era5_wind_dino_report.md`
- Metrics strong: `data/processed/metrics_dino_era5_strong.json`
- Metrics wind: `data/processed/metrics_dino_era5_wind.json`
- Joined features: `data/processed/joined_features_era5.parquet` (gitignored parquet)
- Feature mode: `strong_era5_wind` in `src/pa_marine/features.py` / `scripts/evaluate.py`
