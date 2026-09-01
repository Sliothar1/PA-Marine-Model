# UK FSA Dinophysis evaluation

Generated: 2026-09-01 (Europe/Dublin). Target: `y_dinophysis_nowcast` on England & Wales FSA
Dinophysiaceae (≥100 cells L⁻¹) as Dinophysis proxy. Features: `woy_sin, woy_cos, latitude, longitude`
only (no UK OISST join; no OSTIA). Metrics: `data/processed/uk_dino_metrics.json`.

## Data adequacy vs Irish year split

UK panel years are **[2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]** (7246 station-weeks after
coord filter). Applying the Irish split (train ≤2018 / val 2019–2021 / test ≥2022) leaves
**only ISO 2018 as train** (~one year, few hundred positives at most across folds) — **too
little for a solid UK-only fit**. We therefore use a **UK-adapted time split**
(train 2018–2021, val 2022 for calibration, test 2023+) plus **leave-one-year-out** and an
**Ireland→UK transfer** check on aligned ≥100 cells L⁻¹ labels.

## UK vs Irish PR-AUC / rates

Same-week Dinophysis exceedance rate is similar on the two coasts (**UK 0.053**
vs **Irish 0.062**; nowcast rates **0.078** vs
**0.105**). On the UK-adapted test set, LightGBM val-calibrated
PR-AUC is **0.444** (clim 0.190, prevalence 0.076),
versus Irish strong-mode LightGBM test-calibrated PR-AUC **0.293** (clim 0.183,
prevalence 0.052, SST+seasonality features). Ireland→UK transfer with
shared seasonality/geo features yields LightGBM UK-test PR-AUC **0.132** (below week-of-year clim;
logreg transfer ~0.20) — geo ranges differ (IE −11…−5°E vs EW −5…+2°E), so treat this as a
cross-shelf sanity check, not a replacement for UK SST features. LOYO LightGBM test PR-AUC by
held-out year: 2018=0.529, 2019=0.294, 2020=0.494, 2021=0.421, 2022=0.318, 2023=0.615, 2024=0.203, 2025=0.505. Honest takeaway:
UK labels are usable and rates align with Ireland, but without joined UK SST the ranking skill
is mostly seasonal/geographic; treat UK numbers as a parallel baseline until OISST is attached
(still no Copernicus/OSTIA without credentials).

## Split counts (UK-adapted)

| split | n | positives (same-week) | years |
| --- | ---: | ---: | --- |
| train | 3534 | 190 | [2018, 2019, 2020, 2021] |
| val | 884 | 52 | [2022] |
| test | 2828 | 141 | [2023, 2024, 2025] |

## Reproduce

```bash
python scripts/ingest_uk_fsa.py          # refresh panel (cp1252-safe)
python scripts/evaluate_uk_dino.py
```
