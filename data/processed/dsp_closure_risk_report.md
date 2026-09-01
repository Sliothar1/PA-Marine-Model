# DSP / harvest-closure risk (ops prototype)

Generated: **2026-09-01 21:43 IST**. Script: `scripts/train_dsp_closure_risk.py`.

Product thesis: **shellfish DSP exceedance and harvest closures** are closer to euro-loss than cell counts. This run asks whether the same Irish **OISST strong** features that give modest Dinophysis-cell skill also rank **toxin exceedance** and **area closed** weeks.

## Data

- Joined panel: `/workspace/pa-marine-model/data/processed/toxin_joined_features.parquet` (48158 rows, 128 `location_id`s overlapping phyto OISST/MHW).
- SST non-null rate: **0.3145894763071556** (require complete strong features: `False`).
- Feature mode `strong` (9 cols): `sst, sst_lag0d, sst_lag21d, sst_roll7d, sst_roll30d, woy_sin, woy_cos, latitude, longitude`.
- Time split: train [2003, 2018] / val [2019, 2021] / test≥2022.
- Target `y_dsp_exceed`: station-week max(`exceed_dsp`, `exceed_ptx`) among DSP-measured weeks (MI pivot: DSP = OA/DTX family; PTX co-thresholded, historically ~0 exceedances).
- Target `y_closed`: `habs_status` closed / closed-pending / harvest-restricted, joined on `parent_area_name` + ISO week (same as biotoxin ingest).

## Test metrics (primary = calibrated LightGBM PR-AUC)

| Target | Model | Test n | Prevalence | PR-AUC | Clim PR-AUC | PR skill | Brier |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DSP exceed | LightGBM cal | 8346 | 0.002 | **0.009** | 0.004 | 0.005 | 0.013 |
| DSP exceed | LightGBM raw | 8346 | 0.002 | **0.020** | 0.004 | 0.016 | 0.116 |
| DSP exceed | LogReg cal | 8346 | 0.002 | **0.006** | 0.004 | 0.002 | 0.010 |
| Area closed | LightGBM cal | 8432 | 0.190 | **0.315** | 0.208 | 0.135 | 0.158 |
| Area closed | LightGBM raw | 8432 | 0.190 | **0.323** | 0.208 | 0.146 | 0.223 |
| Area closed | LogReg cal | 8432 | 0.190 | **0.227** | 0.208 | 0.023 | 0.166 |
| Dinophysis cells (ref) | LightGBM cal | 14270 | 0.052 | **0.293** | 0.183 | 0.135 | 0.053 |

### Split prevalence (important)

- DSP train prevalence: **0.042**; test prevalence: **0.002** (~19 test positives).
- Closed train prevalence: **0.328**; test: **0.190**.

DSP toxin exceedances became **much rarer** on the 2022+ test window than in train/val. That shrinks the economic-event sample and inflates uncertainty in PR-AUC — do not over-read a single point estimate.

## Is closure / DSP predictable from SST alone?

- DSP exceedance: **not reliably assessable from SST alone on this test window** (only ~19 positives; PR-AUC is noisy). Prefer more years / denser toxin sampling before claiming ops skill.
- Area closed: **partially predictable from SST strong features** (PR skill 0.135 vs week-of-year clim).

Context: almost every DSP-exceed week is closed in the matched panel (P(closed|DSP+)≈0.9969173859432799; P(DSP+|closed)≈0.11622223819449436; Pearson≈0.2902054179490157). Closures are driven by **multiple** toxins and admin rules — SST→DSP cells≠SST→closure.

## Honest comparison to cell-based Dinophysis model

| | Dinophysis cells (`y_dinophysis_nowcast`) | DSP toxin exceed | Area closed |
| --- | ---: | ---: | ---: |
| Test PR-AUC (LGBM cal) | 0.293 | 0.009 | 0.315 |
| Clim PR-AUC | 0.183 | 0.004 | 0.208 |
| PR skill | 0.135 | 0.005 | 0.135 |
| Test prevalence | 0.052 | 0.002 | 0.190 |

- Cell model (Ireland strong OISST): modest but real ranking skill (~0.29 cal PR-AUC vs ~0.18 clim).
- DSP toxin head: economically closer to harvest loss, but **positives are scarce on test** and agreement with Dinophysis cells was only moderate at ingest (Pearson ~0.29; see `biotoxin_ingest_report.md`). Expect weaker / noisier SST skill than cells.
- Closed head: higher prevalence and more stable — better powered — but mixes DSP with ASP/AZP/PSP and non-toxin admin closures, so SST-alone skill is an upper-bound on 'toxin-weather' signal, not a drop-in ops product.

## Caveats

- OISST landmask → ~30–40% SST coverage at toxin sites; LightGBM sees NaNs, logreg median-imputes.
- `habs_status` has **no** `location_id`/lat-lon — area-name string join only.
- Not an operational warning system; research prototype for Cork Ocean Hackathon Challenge 4.

## Re-run

```bash
python scripts/train_dsp_closure_risk.py
# or, after re-ingest:
python scripts/ingest_biotoxin.py --skip-download
python scripts/train_dsp_closure_risk.py --require-sst
```

Metrics JSON: `/workspace/pa-marine-model/data/processed/dsp_closure_risk_metrics.json`.

## Sensitivity: complete strong-SST rows only (`--require-sst`)

Restricting to rows with all 9 strong features non-null (~31% of panel):

| Target | LightGBM cal PR-AUC | Clim | PR skill | Test n / positives |
| --- | ---: | ---: | ---: | --- |
| DSP exceed | 0.025 | 0.009 | 0.017 | 2602 / ~12 |
| Area closed | **0.457** | 0.208 | **0.314** | 2613 / ~542 |

Closure skill **strengthens** when SST is observed (less imputation noise). DSP remains too rare on test for a solid claim. Default metrics above keep NaN rows so protocol matches Ireland Dinophysis `evaluate.py`.

