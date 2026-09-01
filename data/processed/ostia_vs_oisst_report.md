# OSTIA vs OISST — Dinophysis comparison (2026-09-01)

**One-liner:** OSTIA calibrated Dinophysis test PR-AUC ≈ **0.24** vs OISST strong ≈ **0.29**; keep **OISST** as default, OSTIA optional (`--provider ostia`).

## Setup

| | NOAA OISST v2.1 | Copernicus OSTIA L4 REP |
| --- | --- | --- |
| Product | `ncdcOisst21Agg` (ERDDAP) | `SST_GLO_SST_L4_REP_OBSERVATIONS_010_011` / `METOFFICE-GLO-SST-L4-REP-OBS-SST` |
| Resolution | 0.25° | ~0.05° |
| Extract | Irish bbox → station pixels | **Station ocean-pixel** extract (125 unique pixels / 207 stations; nearest finite ocean cell) |
| Variable | `sst` (°C) + NOAA `anom` | `analysed_sst` (Kelvin → °C); anomaly from Hobday clim only |
| Time axis used | 2002-01-01 → **2026-08-16** | 2002-01-01 → **2026-03-31** (MY/REP axis max) |
| Auth | none | `~/.copernicusmarine` (not committed) |

Pipeline: rebuild MHW (Hobday 2016) → join to existing Irish HAB station-week panel → LightGBM / logreg, **`--feature-mode strong`**, **`--calibration auto`** (isotonic on val).

- OISST baseline: `data/processed/metrics_dino_strong.json`
- OSTIA run: `data/processed/metrics_dino_ostia.json`

## Data sizes (local, gitignored parquet)

| File | Size | Rows | Stations | Date span |
| --- | ---: | ---: | ---: | --- |
| `data/raw/oisst_daily.parquet` | 2.15 MB | 1,857,825 | 207 | 2002-01-01 … 2026-08-16 |
| `data/raw/ostia_daily.parquet` | 3.26 MB | 1,833,192 | 207 | 2002-01-01 … 2026-03-31 |
| `data/processed/mhw_daily.parquet` | 9.86 MB | 1,861,758 | 207 | (OISST) |
| `data/processed/mhw_daily_ostia.parquet` | 19.93 MB | 1,833,192 | 207 | (OSTIA) |
| `data/processed/joined_features.parquet` | 2.50 MB | 53,172 | 207 | panel |
| `data/processed/joined_features_ostia.parquet` | 5.77 MB | 53,172 | 207 | panel |

OSTIA raw SST has **0% NaN** at mapped ocean pixels. On the joined panel, **~8% of test rows** (1,140 station-weeks with `week_start` 2026-03-30 … 2026-08-24) lack OSTIA SST because the REP product ends 2026-03-31.

## PR-AUC before / after (full available series each)

Feature mode `strong` (9 features). **Calibrated** = isotonic fit on val only. Test n = 14,270; prevalence ≈ 0.052.

### `y_dinophysis_nowcast` (primary)

| Model / split | OISST PR-AUC | OSTIA PR-AUC | Δ (OSTIA−OISST) | OISST PR skill | OSTIA PR skill |
| --- | ---: | ---: | ---: | ---: | ---: |
| LightGBM test raw | 0.3059 | 0.2417 | -0.0642 | 0.1502 | 0.0717 |
| LightGBM test **cal** | 0.2933 | 0.2345 | -0.0587 | 0.1348 | 0.0629 |
| LogReg test **cal** | 0.2333 | 0.2388 | +0.0055 | 0.0614 | 0.0681 |
| LightGBM val **cal** | 0.5433 | 0.5197 | -0.0236 | 0.3609 | 0.3279 |

### `y_dinophysis_ahead7`

| Model / split | OISST PR-AUC | OSTIA PR-AUC | Δ | OISST PR skill | OSTIA PR skill |
| --- | ---: | ---: | ---: | ---: | ---: |
| LightGBM test **cal** | 0.2310 | 0.1894 | -0.0416 | 0.1166 | 0.0687 |
| LightGBM test raw | 0.2391 | 0.1979 | -0.0411 | 0.1258 | 0.0785 |

## Fair common-period check (feat_date ≤ 2026-03-31)

Truncating both joins to the OSTIA REP end removes late-2026 test weeks where OSTIA is missing (peak Dinophysis season). Test n → **13,130**.

| Target | Model | OISST PR-AUC cal | OSTIA PR-AUC cal | Δ |
| --- | --- | ---: | ---: | ---: |
| nowcast | LightGBM | 0.2366 | 0.2406 | +0.0040 |
| nowcast | LogReg | 0.1708 | 0.1598 | -0.0109 |
| ahead7 | LightGBM | 0.1816 | 0.1892 | +0.0076 |

## Takeaways

1. **Headline (full series):** OISST LightGBM calibrated test PR-AUC **0.293 → OSTIA 0.235** (Δ ≈ -0.059). Much of this gap is **coverage**, not resolution: OSTIA MY/REP stops at 2026-03-31 while OISST covers through mid-August 2026.
2. **Fair window:** on a shared ≤2026-03-31 panel, LightGBM calibrated nowcast is essentially tied (**OISST 0.237 vs OSTIA 0.241**, Δ ≈ +0.004). Ahead-7d also slightly favours OSTIA.
3. Finer 0.05° OSTIA coastal pixels did **not** yield a large Dinophysis PR-AUC lift vs 0.25° OISST under the current `strong` feature set (seasonality + lat/lon still dominate).
4. Default provider remains **OISST** for the main pipeline; OSTIA is enabled in config and selectable via `--provider ostia` on `scripts/compute_mhw.py`.
5. No NetCDF / credentials committed. Raw OSTIA parquet stays under `data/raw/` (gitignored).

## How to reproduce

```bash
# requires copernicusmarine login already present on the box
python scripts/compute_mhw.py --provider ostia --t0 2002-01-01 --t1 2026-03-31
python scripts/join_features.py \
  --mhw data/processed/mhw_daily_ostia.parquet \
  --out data/processed/joined_features_ostia.parquet
python scripts/evaluate.py \
  --joined data/processed/joined_features_ostia.parquet \
  --horizon both --calibration auto --feature-mode strong \
  --out data/processed/metrics_dino_ostia.json
```
