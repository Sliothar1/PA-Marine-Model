# Diagnostics - `y_dinophysis_nowcast`

feature mode `strong` (9 features), estimator `hist_gbdt`, bootstrap 200 clustered on `location_id`.

## 1. Skill against progressively fairer baselines

The model receives `latitude`/`longitude`, so a week-of-year-only baseline rewards it for knowing which stations bloom. `station_week` removes that.

| baseline | baseline PR-AUC | model PR-AUC | PR skill | 95% CI | P(>0) |
| --- | ---: | ---: | ---: | --- | ---: |
| `prevalence` | 0.052 | 0.292 | **0.253** | [0.189, 0.304] | 1.00 |
| `week` | 0.183 | 0.292 | **0.133** | [0.072, 0.188] | 1.00 |
| `week_smooth` | 0.183 | 0.292 | **0.133** | [0.071, 0.186] | 1.00 |
| `station` | 0.095 | 0.292 | **0.217** | [0.163, 0.269] | 1.00 |
| `station_week` | 0.284 | 0.292 | **0.010** | [-0.039, 0.043] | 0.59 |

## 2. Negative controls (labels permuted, model refit)

Skill measured against the `station_week` baseline. `global` must be ~0 or the plumbing is broken. `within_station_month` preserves station base rate and seasonality while destroying the residual SST/MHW link, so surviving skill there is real dynamical signal.

| control | repeats | mean PR skill | p95 | max |
| --- | ---: | ---: | ---: | ---: |
| `global` | 10 | -0.001 | 0.002 | 0.002 |
| `within_station` | 10 | -0.005 | -0.004 | -0.003 |
| `within_week` | 10 | -0.007 | 0.001 | 0.002 |
| `within_station_month` | 10 | 0.026 | 0.038 | 0.041 |

Real PR skill 0.010 vs permuted p95 0.038: **does NOT clear the permutation ceiling** - not distinguishable from station+season structure.

## Generalisation to unseen `location_id`

The fixed temporal split asks whether we can forecast at a station we already monitor. Holding out whole stations asks whether we can forecast at one we have never sampled - the question a new farm site poses. The model receives lat/lon, so in-sample station identity may be carrying the skill.

- folds scored: **11** of 25
- median PR skill: **0.085** (IQR 0.008 to 0.322)
- folds with positive skill: **0.73**

**The null here is not zero.** A held-out group has no station effect, so the baseline degenerates to week-of-year, and the model's smooth Fourier seasonality beats 52 independent week bins on estimator variance alone. On synthetic panels with no dynamical signal this still produced 86-93% of folds positive at a median skill of 0.03-0.07. Treat these numbers as comparable only against a permuted-label run of the same configuration, not against zero.

## 3. Skill by label-window sampling coverage

`y_*_nowcast` ORs over whichever weeks were sampled in the window, and sampling effort is seasonal. If skill only appears in the well-sampled strata, it may be tracking the sampling calendar.

| weeks sampled | n | prevalence | model PR-AUC | baseline | PR skill |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 694 | 0.020 | 0.267 | 0.247 | **0.027** |
| 2 | 2867 | 0.051 | 0.281 | 0.302 | **-0.030** |
| 3 | 10719 | 0.054 | 0.300 | 0.288 | **0.018** |
