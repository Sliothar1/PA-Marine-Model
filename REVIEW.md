# PA-Marine-Model — review

Reviewed at `ae51c4b` (2026-09-02). 28/28 tests passing on arrival; fixture pipeline runs
clean; `pip install -e ".[dev]"` resolves.

First, the honest headline: this is a well-built repo. The time split is never random, the
calibrator is fitted on validation only, the ERDDAP column names are verified against
`info.json` rather than assumed, the percent-encoding workaround for Tomcat is documented,
and the README reports a negative Karenia result instead of hiding it. The `Caveats`
section already names several of the things a reviewer would reach for. That is rarer than
it should be, and it made the real problems easier to find.

Three of those real problems are below, all confirmed by execution rather than reading, and
all fixed on branch `review/mhw-labels-uncertainty`.

---

## 1. MHW event assembly is in the wrong order — ~55% over-detection

**Severity: high.** `src/pa_marine/mhw.py`

`detect_mhw` merged gaps of ≤ `max_gap` days *before* applying the ≥ `min_duration` filter.
Hobday et al. (2016), and Eric Oliver's reference `marineHeatWaves` implementation, do the
opposite: identify above-threshold runs of ≥ 5 days first, *then* join surviving events
across gaps of ≤ 2 days.

The order matters because merging first lets two runs that are each too short to be events
bootstrap each other into one:

| exceedance pattern | v1 | Hobday order | correct |
| --- | ---: | ---: | ---: |
| 3d + 2d gap + 3d | **8 MHW days** | 0 | 0 |
| 4d + 1d gap + 4d + 1d gap + 4d | **14 MHW days** | 0 | 0 |
| 3d + 2d gap + 6d | **11 MHW days** | 6 | 6 |
| 6d + 2d gap + 6d | 14 | 14 | 14 ✓ |
| 6d + 3d gap + 6d | 12 | 12 | 12 ✓ |

On 30-year AR(1) red-noise SST with a 10-day decorrelation scale and a realistic seasonal
cycle (12 seeds), v1 flagged **919 MHW days per 30 years vs 591** under the correct
ordering — **55.5% over-detection**, consistent across every seed (39–72%). v1 put 8.4% of
all days in a marine heatwave; the corrected version gives 5.4%, which is in the right
range for a 90th-percentile definition.

The existing `test_two_day_gap_merged` uses 6d + 2d gap + 6d, which passes under *both*
orderings — that is why the bug survived. The three cases that discriminate are now in
`tests/test_mhw_event_order.py`.

**Why this matters beyond tidiness.** The project's central scientific question is whether
MHW features predict HAB exceedance, and the answer on record is that `in_mhw*` and
duration features are "near-zero noise". Those features were computed with a ~55% inflated,
noise-contaminated event indicator. Attenuating a real signal is exactly what that kind of
label noise does. The negative MHW result needs re-running before it can be trusted — and
note the direction: the fix can only *help* the MHW features, so the current conclusion is
not conservative in the way one might assume.

**Fixed:** `event_order="hobday"` is now the default; `"legacy"` reproduces pre-fix numbers.
Exposed as `mhw.event_order` in config.

---

## 2. MHW climatology is fitted on the full series, including the test years

**Severity: high.** `src/pa_marine/mhw.py`

`_doy_climatology` pooled the entire local record to compute both the seasonal mean and the
90th-percentile threshold. The README lists this under caveats ("not a fixed 30-year
baseline"), but it is understated as a fidelity issue when it is actually two separate
problems.

**(a) Test-set leakage.** Every day's `thresh`, `clim`, `ssta`, `ssta_pctile`, `in_mhw` and
`mhw_category` for 2022+ was computed using 2022+ SST.

**(b) A method-induced train/test shift, which is the worse one.** Irish shelf SST is
warming. Pooling all years lets the trend raise the threshold, so recent warm anomalies get
graded against a warmer bar. Simulating 2003–2026 with +0.3 °C/decade on the project's own
split:

| era | MHW days, full-series climatology | MHW days, baseline fixed to 2003–2018 |
| --- | ---: | ---: |
| train 2003–2018 | 8.1% | 9.9% |
| val 2019–2021 | 5.5% | 8.2% |
| test 2022+ | 13.6% | 17.2% |

The current approach under-detects test-era MHW by ~21% relative. So a model trained on
train-era MHW features is applied to test-era features whose distribution shifted because
*the estimator* changed, not because the ocean did. This degrades exactly the features the
ablation then reports as worthless. Findings 1 and 2 both push in the same direction, and
they compound.

**Fixed:** `baseline_years=(y0, y1)` restricts the climatology *pool* while still applying
the fitted threshold to every day. Config default `mhw.climatology_baseline: [2003, 2018]`
(the training split). Set `[1983, 2012]` for the Hobday convention, or `null` for v1.

Note that the default `--feature-mode strong` uses only `sst`, `sst_roll*`, `woy_*` and
lat/lon — no threshold-derived columns — so **the headline Dinophysis number is clean**.
Every MHW and IBI ablation is affected.

---

## 3. The horizon label silently encodes sampling effort

**Severity: high (methodological, not a crash).** `src/pa_marine/hab.py`

`y_<tax>_nowcast` is an OR over whichever station-weeks happen to be sampled in
`[week_start, week_start + 14d]`. HAB sampling is irregular and *seasonal* — heavier in
summer, which is also bloom season. So a station-week whose window contains three samples
has three independent chances to be positive; one with a single sample has one.

On a simulated panel with realistic seasonal sampling effort:

| sampled weeks in window | station-weeks | label positive rate | underlying weekly rate |
| ---: | ---: | ---: | ---: |
| 1 | 6,755 | 0.070 | 0.070 |
| 2 | 10,205 | 0.326 | 0.187 |
| 3 | 23,228 | 0.608 | 0.271 |

The label rate rises **8.7×** across coverage strata while the underlying bloom rate rises
3.9×. The excess is pure OR-inflation. And mean window coverage is 2.71 in weeks 18–40
versus 1.55 off-season.

This is the uncomfortable part: the project's own feature study found LightGBM gain and
permutation importance **dominated by `woy_cos`, `woy_sin`, `latitude`, `longitude`** — and
those are precisely the variables that predict *when and where people sample*. Some
unknown fraction of the reported PR skill over climatology may be the model recovering the
sampling calendar rather than bloom dynamics. The week-of-year climatology baseline does
not control for this, because it is computed on the same effort-confounded labels.

I don't think this invalidates the result — but it is currently unmeasured, and it is
measurable.

**Fixed:** `add_horizon_labels` now emits `n_obs_<tax>_<horizon>`, the number of sampled
station-weeks in each label window. Enough to (a) restrict to fully-observed windows, or
(b) stratify metrics by coverage. Recommended next step: report Dinophysis nowcast PR skill
separately for `n_obs == 3` rows. If the skill survives there, the result is solid and much
more defensible.

Same commit vectorises the label construction via `searchsorted` — it was an O(k²) pairwise
date-difference scan per station per taxon. **7× faster** on a 40k-row panel, verified
bit-identical to the original loop against an oracle implementation retained in
`tests/test_horizon_labels.py`.

---

## 4. No uncertainty on any reported metric

**Severity: medium-high.** `src/pa_marine/metrics.py`

"PR-AUC 0.296 vs climatology 0.183, PR skill ~0.12" is quoted as a point estimate. With
test prevalence near 18% and a few thousand positives spread over 207 stations, the
sampling error is not negligible, and there is no way to tell whether 0.293 (`strong`) beats
0.281 (`all`) or whether that +0.012 is noise. The same applies to the whole ablation table
— it currently ranks feature modes on differences that may be smaller than their own error
bars, and then the winner gets hard-coded as the default (`STRONG_OISST`), which is a
selection-on-noise risk.

The right resampling unit is the **station**, not the row: station-weeks within a station
share a location, an SST series and a sampling regime, and neighbouring stations co-bloom.
On a panel sized like the real test split (207 stations × 250 weeks):

| bootstrap unit | PR skill | 95% CI | width |
| --- | ---: | --- | ---: |
| rows (i.i.d.) | 0.262 | [0.251, 0.276] | 0.025 |
| stations (cluster) | 0.262 | [0.225, 0.303] | **0.078** |

An i.i.d. row bootstrap would have reported intervals **3.1× too tight**.

**Added:** `bootstrap_summary(...)` — percentile CIs on PR-AUC, Brier and both skill scores,
plus `pr_auc_skill_gt0` (bootstrap P(model beats climatology)). Wired into `evaluate.py` as
`--bootstrap N --bootstrap-cluster location_id`; results land in `metrics.json`. Degenerate
replicates (no positives) are skipped and reported via `n_boot_used`, so the Karenia case
returns NaN instead of crashing.

---

## Smaller items (not fixed)

- **`join_features.py` → `features.join_week_panel`**: column selection uses
  `c.endswith("d")`, which matches `location_id`. Harmless today because `feature_columns`
  skips it explicitly, but it is the same naïve-suffix bug the README says was fixed in
  `feature_columns`, still live one function away. Worth an allow-list.
- **`evaluate.py`**: `fit_predict(est, Xtr, ytr, Xtr)` discards its return value — it is
  called only for the fitting side effect, and predicts over the whole training set for
  nothing. Use `est.fit(...)`.
- **`evaluate.py`**: `ytr = train[tgt].astype(int)` then `mtr = ytr.notna()` — `astype(int)`
  cannot produce NaN, so every `notna()` mask in this script is a no-op. Either mask before
  the cast or drop the masks; as written they imply a missing-label guard that isn't there.
- **`requirements.txt`** is stale against `pyproject.toml` (no `pyproj`, which
  `uk_fsa.py` and `smc_geocode.py` both import). Anyone following it instead of the README
  gets 6 test failures — which is exactly what happened to me. Consider deleting it and
  pointing at the extras.
- **Leap years**: `dayofyear` shifts by one after 28 Feb in leap years, so the DOY
  climatology mixes calendar positions. Minor at an 11-day window, but standard MHW
  implementations handle it.
- **`mhw_i_ratio`** is computed twice — once inside the event loop (used for
  `mhw_category`) and once globally (stored as the column). They differ outside events.
  Intentional, probably, but undocumented.
- **`data/processed` whitelist** in `.gitignore` is ~90 lines of `!` exceptions. It works,
  but a `data/reports/` directory that is committed wholesale would be easier to maintain
  than a growing list of negations.

---

## What I'd do next, in order

1. **Re-run the MHW ablations** with `event_order: hobday` and
   `climatology_baseline: [2003, 2018]`. The claim "MHW features are near-zero noise" is
   the project's most interesting finding and it was measured through two compounding
   defects, both of which biased against MHW features. This is the single highest-value
   thing on the list.
2. **Re-run the feature-mode ablation with `--bootstrap 1000`.** If `strong` (0.293) and
   `all` (0.281) have overlapping CIs, say so in the README and stop treating `strong` as
   an established winner. Selecting a default on a 0.012 difference is how ablation tables
   turn into folklore.
3. **Stratify Dinophysis PR skill by `n_obs_dinophysis_nowcast`.** If skill holds on
   fully-observed windows, finding 3 is answered and the headline number gets much stronger.
   If it collapses, better to know now.
4. **Add leave-one-station-out and leave-one-year-out** alongside the fixed temporal split.
   `evaluate_uk_dino.py` already does LOYO — that machinery should be promoted to the Irish
   path, where 207 stations make grouped CV cheap and informative.
5. **A negative control.** Train on shuffled-within-station labels and confirm PR skill
   collapses to ~0. With seasonality and geography dominating the model, this is the
   cheapest guard against the whole pipeline quietly learning the sampling calendar.

## Changes on this branch

```
configs/default.yaml           |   9 +   mhw.event_order, mhw.climatology_baseline
scripts/evaluate.py            |  47 +   --bootstrap / --bootstrap-cluster
src/pa_marine/hab.py           |  51 +   vectorised labels + n_obs_* coverage
src/pa_marine/metrics.py       |  77 +   bootstrap_summary, cluster resampling
src/pa_marine/mhw.py           | 130 +   event_order, baseline_years
tests/test_horizon_labels.py   | 118 +   new (5 tests, incl. oracle equivalence)
tests/test_metrics.py          |  44 +   bootstrap tests
tests/test_mhw_event_order.py  | 104 +   new (12 tests)
```

47/47 tests pass. Fixture pipeline and `evaluate.py --bootstrap` verified end-to-end.
All existing tests pass unmodified under the new defaults — no test was weakened to
accommodate a fix.

---

# Addendum — second patch (`diagnostics`)

Adds `src/pa_marine/diagnostics.py`, `scripts/run_diagnostics.py`, and
`tests/test_diagnostics.py`. New files only, so it will not conflict with concurrent
work elsewhere in the repo. 57/57 tests pass.

## 5. The climatology baseline is too weak to support the headline claim

**Severity: high. This supersedes item 4 as the most important finding.**

`metrics.climatology_probs` is a week-of-year mean pooled across all stations. But the
model is handed `latitude` and `longitude`, and Irish HAB stations differ enormously in
base exceedance rate. So the model can beat that baseline purely by learning *which
farms are risky* — which every operator already knows — without any forecasting skill.

I tested this by simulating a panel with station effects and seasonality but **no
dynamical signal at all**, then scoring an oracle that sees exactly that structure and
nothing more:

| baseline | baseline PR-AUC | model PR-AUC | PR skill |
| --- | ---: | ---: | ---: |
| prevalence | 0.218 | 0.610 | 0.501 |
| **week (current)** | 0.437 | 0.610 | **0.307** |
| station | 0.358 | 0.610 | 0.392 |
| **station × week (added)** | 0.599 | 0.610 | **0.028** |

A model with zero dynamical information scores **PR skill 0.307** against the baseline
currently used in `metrics.json`, and correctly ~0.03 against a station × week baseline.

The reported Dinophysis figure is **PR skill ~0.12**. On a second, more realistic
simulation (48,880 station-weeks, 24 years, AR(1) SST, correct train/val/test split) a
zero-signal panel produced **PR skill 0.102 against the week baseline and −0.109 against
station × week** — statistically indistinguishable from the project's headline number.

To be precise about what this does and does not establish: I could not run this on the
real panel, because `joined_features.parquet` is gitignored and not in the repo. So this
does **not** show the model lacks skill. It shows the current baseline cannot tell the
difference, and that the headline number is fully consistent with having none. That
question is now answerable in one command.

`station_week` is logit-additive with empirical-Bayes shrinkage (station effect + week
effect over a global rate) rather than raw station × week cell means, because 207 stations
× 52 weeks is far too sparse to estimate directly. Unseen stations and weeks fall back to
the global rate, so it is always defined on the evaluation split.

## 6. Negative controls

Four graded permutation controls, each refitting the model on shuffled labels. Verified
that each destroys exactly the structure it claims to and preserves the rest:

| control | corr(y, SST) | station rate kept | seasonality kept |
| --- | ---: | ---: | ---: |
| unpermuted | 0.212 | 1.000 | 1.000 |
| `global` | −0.004 | 0.001 | 0.119 |
| `within_station` | 0.001 | 1.000 | −0.092 |
| `within_week` | 0.011 | −0.034 | 1.000 |
| `within_station_month` | 0.012 | **1.000** | **0.983** |

`within_station_month` is the one that matters: it preserves station base rate *and*
seasonality while destroying only the residual within-station, within-season variation —
which is precisely the SST/MHW signal the project claims to forecast. Any skill surviving
it is real dynamical signal. It gives the honest ceiling that a headline number has to
clear.

End-to-end validation against known ground truth (`global` sits at ~0.000 in both cases,
confirming the metric plumbing is sound):

| truth | PR skill vs `station_week` | `within_station_month` p95 | verdict |
| --- | ---: | ---: | --- |
| no dynamical signal (β=0) | −0.109 | −0.082 | correctly **no signal** |
| real SST signal (β=1.0) | 0.567 | −0.036 | correctly **signal detected** |

The tool returns the right answer in both directions, which is the minimum bar before
trusting it on real data.

## 7. Coverage stratification

Wires finding 3 into a report: PR skill split by `n_obs_<tax>_<horizon>`. If skill only
appears in well-sampled strata, it is tracking the sampling calendar.

## Run it

```bash
python scripts/run_diagnostics.py \
    --joined data/processed/joined_features.parquet \
    --target y_dinophysis_nowcast --feature-mode strong \
    --bootstrap 500 --permutation-repeats 50
```

Writes `data/processed/diagnostics.json` and `diagnostics_report.md`. Reads existing
joined features; no network, no re-download, nothing upstream retrained. Coverage
stratification needs a panel rebuilt with the patched `add_horizon_labels` to emit the
`n_obs_*` columns; it skips with a clear message otherwise.

**Do this before the ablations.** If the Dinophysis skill does not clear the
`within_station_month` ceiling under a `station_week` baseline, then re-running feature
ablations is measuring noise, and the honest headline is "seasonality and station identity
carry the signal; SST/MHW add little" — which is still a publishable result, just a
different one.

---

# Addendum — third patch (`sst` data layer)

Reviewed the data layer, which the first two patches did not touch. Two findings, both
affecting which ocean pixel each farm is scored against. 71/71 tests pass.

## 8. Nearest-pixel selection uses Euclidean distance in degrees

**Severity: medium-high.** `sst.py`, `ibi.py`, `era5.py`

Four functions selected the nearest ocean pixel with
`(lat_grid - lat)**2 + (lon_grid - lon)**2` — Euclidean distance in *degrees*, which
treats one degree of longitude as costing the same as one degree of latitude. At Irish
latitudes it does not: at 53.5°N a degree of longitude is **66.1 km** against **111.2 km**
for latitude, a ratio of 0.595. So the metric over-penalises east-west displacement by
**~1.68×**.

Measured on the 11 real Connemara station coordinates, over every candidate pixel pair
within the 1° search radius:

| station | candidate pixels | pairs mis-ranked | worst mis-selection |
| --- | ---: | ---: | ---: |
| Killary Harbour Outer | 49 | 15.1% | 40.8 km |
| Rosmuc | 50 | 14.0% | 41.6 km |
| Lehannagh Pool | 50 | 14.9% | 40.7 km |
| Mace Head | 51 | 15.2% | 39.6 km |
| *(mean over all 11)* | | **14.4%** | |

"Worst mis-selection" is the km penalty in the worst case where the old metric preferred
pixel A while A was actually farther away than the pixel B it rejected — up to **41.6 km**.

This only bites when the ocean mask is anisotropic, which is exactly the coastal case:
in a fjord like Killary, ocean pixels exist in some directions and not others, so the
ranking decides which water body a farm is scored against. The concrete failure mode is
picking a pixel across a headland instead of the open Atlantic pixel in the same water.

The `max_dist_deg=1.0` gate had the same defect: it admitted pixels **111 km** away
north-south but only **66 km** east-west.

**Fixed:** shared `haversine_km` helper; all four call sites converted. The gate is now
`max_dist_km` (default 60 km); `max_dist_deg` is still accepted and converted. The pixel
map column `dist_deg` becomes `dist_km`. Note the old column name was live in
`sst.py`, `ibi.py` and `era5.py` print statements, so a partial rename would have
crashed at runtime — all references were updated together.

## 9. The Irish path has no ocean mask, and never says so

**Severity: high, and it connects to findings 3 and 5.**

There are two OISST paths, and only one of them masks land:

- `download_oisst_for_stations_nearest_ocean` — has an ocean mask. Used **only** by
  `train_scotland_dino.py`.
- `_download_oisst_for_stations` — naive `snap_oisst` to whichever 0.25° pixel contains
  the station, **no ocean mask**. This is what `compute_mhw.py` calls, so it is the path
  behind the **Irish headline model**.

The README caveat ("nearest-neighbour, no coastal mask") is therefore accurate for
Ireland and outdated for Scotland. And the repo already documents a live instance —
`data/processed/connemara_farms_stations.csv`, Rosmuc:

> "HAB samples present, but OISST SST is null at this pixel (landmask / inshore).
> Scores use week-of-year + lat/lon; SST features missing."

Nothing in the pipeline counted how many of the 207 Irish stations are in that state.
Land-snapped stations still carry HAB labels, so they contribute station-weeks whose
SST and MHW features are entirely NaN — median-imputed for logistic regression, routed
down the missing branch for LightGBM.

**This is a coherent mechanism for the project's central findings.** Inshore Irish HAB
sites are fjords, bays and harbours — precisely the geometry that snaps to land on a
0.25° grid. For an unknown share of stations there is simply no SST to learn from, so:

- week-of-year and lat/lon dominate feature importance (finding: the feature study),
- MHW features look like noise (finding 1's ablation),
- and skill is consistent with a station-plus-season model (finding 5).

Findings 1, 2, 8 and 9 all degrade the SST/MHW features specifically, and all four point
the same way. That is now four independent reasons the "MHW doesn't matter" conclusion
needs re-testing before it is believed.

**Fixed:** `sst_coverage_report()` prints per-station finite-SST fractions and warns
loudly about stations with zero usable SST; it is now called on every SST frame the
pipeline uses. And `compute_mhw.py --ocean-mask` routes Ireland through the masked
nearest-ocean path that Scotland already uses.

```bash
# see how many Irish stations are land-snapped
python scripts/compute_mhw.py --max-stations 5 --t0 2015-01-01 --t1 2024-12-31

# then re-run with the ocean mask
python scripts/compute_mhw.py --ocean-mask --t0 2003-01-01 --t1 2026-08-16
```

Run the diagnostic first — the station count it prints is the single most informative
number available about why the SST features underperform.
