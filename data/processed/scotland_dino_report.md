# Scotland SMC Dinophysis nowcast (OISST strong)

Generated: 2026-09-01 19:53 IST (Europe/Dublin). Target: `y_dinophysis_nowcast`.
Feature mode: **strong** (9 feats). Metrics: `data/processed/scotland_dino_metrics.json`.

## Data filter

- Panel SINs: **131** → keep confidence ∈ {high, medium} → **96** SINs (**73.3%** of sites)
- Station-weeks: **21417** → **16729** (78.1% of rows; high/medium sites are denser)
- Week span: **2009-02-23 → 2026-08-31**
- Coords: lat [54.96, 60.76],
  lon [-7.23, -0.83]
- OISST: nearest-ocean 0.25° pixels, `2002-01-01` → `2026-08-16` (climatology buffer before first SMC week)
- Rows with finite SST after join: **16619** / 16729 (99.3%)
- Same-week / nowcast prevalence: **0.201** /
  **0.335**

## Time split (Irish years)

| split | n (with SST) | nowcast + | years |
| --- | ---: | ---: | --- |
| train | 9044 | 3143 | [2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018] |
| val | 2977 | 1032 | [2019, 2020, 2021] |
| test | 4598 | 1398 | [2022, 2023, 2024, 2025, 2026] |

## Test metrics vs week-of-year climatology

| model | PR-AUC | clim PR-AUC | PR skill | Brier | Brier skill | n | prevalence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LightGBM calibrated | 0.673 | 0.592 | 0.199 | 0.143 | 0.074 | 4533 | 0.302 |
| LogReg calibrated | 0.594 | 0.592 | 0.007 | 0.152 | 0.013 | 4533 | 0.302 |
| Irish strong LGBM (ref) | 0.293 | 0.183 | 0.135 | 0.053 | -0.012 | 14270 | 0.052 |

Features: `sst, sst_lag0d, sst_lag21d, sst_roll7d, sst_roll30d, woy_sin, woy_cos, latitude, longitude`.

## Notes

- Low-confidence geocodes excluded from SST join (ambiguous Nominatim / island fallbacks).
- Coastal OISST snaps use **nearest ocean pixel** (many Scottish loch/voe snaps are land on the 0.25° grid).
- No ERA5 / IBI / OSTIA in this path.
- Calibration fitted on **val only** (isotonic/sigmoid auto).

## Reproduce

```bash
python scripts/train_scotland_dino.py
# reuse SST:
python scripts/train_scotland_dino.py --skip-download
```
