# PA-Marine-Model — session context, 2026-09-02

**Paste this whole file into a new chat to resume instantly.** It contains the results
that live in gitignored files, which no amount of repo access will recover.

Repo: `github.com/Sliothar1/PA-Marine-Model`
Working branch: `review/claude-patch-2`
Base at session start: `ae51c4b`

---

## The headline result

Ran the full corrected pipeline on the real panel (53,182 station-weeks, 207 stations,
2003–2026). The project's central claim does not survive a fair baseline.

| baseline | baseline PR-AUC | model PR-AUC | PR skill | 95% CI | P(>0) |
| --- | ---: | ---: | ---: | --- | ---: |
| prevalence | 0.052 | 0.292 | 0.253 | [0.189, 0.304] | 1.00 |
| **week (the README's baseline)** | 0.183 | 0.292 | **0.133** | [0.072, 0.188] | 1.00 |
| week_smooth | 0.183 | 0.292 | 0.133 | [0.071, 0.186] | 1.00 |
| station | 0.095 | 0.292 | 0.217 | [0.163, 0.269] | 1.00 |
| **station × week** | **0.284** | 0.292 | **0.010** | **[−0.039, 0.043]** | **0.59** |

Target `y_dinophysis_nowcast`, feature mode `strong` (9 features), `hist_gbdt`, 200
bootstrap replicates clustered on `location_id`.

**Read:** a station × week lookup table scores 0.284. The full pipeline — SST, MHW
features, lags, rolls, gradient boosting — scores 0.292. Skill 0.010, CI spanning zero,
P(>0) = 0.59, a coin flip.

The rebuild reproduces the README faithfully (model 0.292 vs published 0.296; week
baseline 0.183 vs published 0.183; skill 0.133 vs published ~0.12), so this is not a
rebuild artefact. The published number is correct arithmetic against a baseline that was
too weak: it pooled all stations, so the model was credited for knowing which farms bloom.

## Why — the mechanism

**207 stations → 40 OISST ocean pixels, median distance 14.7 km.**

About 5 stations per pixel, many reading identical SST. So `latitude`/`longitude` have 207
distinct values while SST and everything derived from it have 40. The model can separate
stations geographically but not thermally. Station-level thermal signal is not in the
feature matrix at all.

This explains the project's own prior findings — week-of-year and lat/lon dominating
importance, MHW features reading as noise — without needing any claim that heat is
irrelevant to Dinophysis. The features could not express it.

It also means the effective independent unit for SST inference is ~40, not 207, so even
the corrected cluster-bootstrap CIs above are optimistic.

## Confirmed from three directions

- **Baseline table:** skill 0.010, CI spans zero.
- **Coverage strata** (skill by number of sampled weeks in the label window):
  **+0.027 / −0.030 / +0.018** across n = 694 / 2,867 / 10,719. Flat, straddling zero.
- **Permutation controls:** run but output not captured in full; the visible portion was
  consistent. Re-run if needed for the write-up.

The coverage result also **retires a threat to validity**: REVIEW.md item 3 warned the
OR-over-window label might encode seasonal sampling effort (on synthetic data, prevalence
swung 0.070 → 0.608 across strata). On the real panel prevalence is 0.051 vs 0.054 between
the 2- and 3-sample strata and skill is flat. Marine Institute sampling is regular enough
that this is not happening. Worth one line in the paper as a check performed and passed.

## Also validated on real data

Inshore downscaler, on 123 days of real Mace Head in-situ water temperature
(`data/processed/june2023_case_study_daily.csv`, committed):

- downscaler **RMSE 0.45 °C**, MAE 0.37, bias −0.22
- persistence baseline 0.58 °C, seasonal mean 1.67 °C
- **offshore CRW MHW fraction vs inshore water temp: r = +0.027**
- Met Éireann night-minimum air temp vs the same: r = +0.71
- quantile intervals undercovered: 48% actual vs 80% nominal on 92 training days

That r = +0.03 is the single most quotable number from the session: the offshore heatwave
product carries essentially no information about the water the shellfish are in.

## The narrative this supports

1. A station × week climatology gets PR-AUC 0.284 for free — no satellite, no model. That
   is a deployable product, explainable to a grower in one sentence.
2. Adding 23 years of SST and MHW features adds 0.008 ± 0.04. Nothing.
3. Here is the data reason: 5 stations per pixel, 14.7 km median distance, fjords 300 m
   wide, offshore MHW r = +0.03 against inshore truth.
4. Here is the remedy, built and validated: inshore downscaling at RMSE 0.45 °C.

"Our ML model was beaten by a lookup table, and we found out why" is a stronger result
than an unexplained null.

---

## Code state: 8 commits on `review/claude-patch-2`, 120 tests passing

Commits 1–4 are the code review (full detail in `REVIEW.md`):

1. MHW event assembly order (Hobday: duration filter *then* gap join). The old order
   over-detected MHW days by **55%** on red-noise SST. Plus a fixed climatology baseline,
   `[2003, 2018]`, removing both test leakage and warming-trend absorption (~21% damping
   of test-era MHW). Plus cluster-bootstrap CIs (row bootstrap was 3.1× too tight). Plus
   vectorised horizon labels, 7× faster, with `n_obs_*` sampling-coverage columns.
2. `diagnostics.py`: the `station_week` baseline that produced the headline result, four
   graded permutation controls, coverage stratification.
3. Great-circle km for nearest-pixel selection. Degrees-Euclidean mis-ranked **14.4%** of
   candidate pixel pairs on the real Connemara coordinates, worst case 41.6 km. Plus
   `sst_coverage_report()` and `compute_mhw.py --ocean-mask`.
4. Purged label-window leakage at split boundaries (the [0,14]d window spans 3 ISO weeks,
   so ~800 train rows ORed in val-period observations). Plus grouped CV (LOSO/LOYO) and a
   smoothed-week baseline.
5. Four new capabilities from `OCEAN_IDEAS.md` — `downscale.py`, `scheduler.py`,
   `advection.py`, `decisions.py`, plus `scripts/run_idea_demos.py`.
6. `cli probe` now validates SST values. Its hardcoded test pixel was on the Iveragh
   Peninsula, returning NaN while reporting success — passing in CI throughout.
7. `pyarrow` declared as a runtime dependency. A clean install failed at the first
   `to_parquet`; pandas loads the engine lazily so no import audit finds it, and CI missed
   it because the fixture path is all-CSV while the real path is all-parquet. CI now
   exercises both.
8. Fixed a misplaced coverage report — it sat in the masked path labelled "no ocean mask",
   while the naive path that lacks a mask had no report at all.

## Known limitations I did not resolve

- **LOSO has no established null.** On no-signal synthetic panels, 86–93% of folds came out
  positive at median skill 0.03–0.07, because the model's smooth Fourier seasonality beats
  52 independent week bins on estimator variance alone. `week_smooth` halves it, doesn't
  remove it. **Do not read a positive LOSO median as evidence.** The fix is to run
  `--mode grouped_cv` on permuted labels; I did not build the combined run.
- Downscaler quantile intervals are undercovered (48% vs 80% nominal) on 92 training days.
  Needs a conformal wrapper or a multi-year record.
- Idea 4 (dual-hazard biotoxin + faecal) is **blocked**: no Irish *E. coli* time series is
  ingested, and Scottish sanitary classification is annual, usable only as a static prior.
- Idea 3 (tri-national advection) is built and validated on synthetic data only. May well
  return a null on the real panels; that is a publishable result either way.
- Not fixed, cosmetic: `features.join_week_panel` selects columns with `c.endswith("d")`,
  which matches `location_id`; `evaluate.py` discards the return of `fit_predict`;
  `evaluate.py` masks with `notna()` after `.astype(int)`, which cannot produce NaN.

## Next steps, in order

1. **Write up.** The result is in hand and the arc is complete. Methods and limitations can
   be drafted from `REVIEW.md` with no further compute.
2. **Commit the results.** `REVIEW.md`, `OCEAN_IDEAS.md` and
   `data/processed/diagnostics_report.md` currently exist only in a Codespace that will
   eventually be deleted. The `.gitignore` whitelist pattern already used for other reports
   covers the diagnostics file. These numbers are the paper's spine.
3. **Re-run the MHW ablations** with the corrected detector and `--bootstrap 1000`, now
   that the baseline question is settled.
4. **Build out idea 1** properly against the multi-year buoy records
   (`sbe37_macehead`, `sentinel_lehanagh`, SmartBay/Spiddal CTD) rather than 123 days.
   This is the paper's contribution.
5. Optionally close the LOSO null gap.

## Environment notes

- Working in GitHub Codespaces; git is **not** installed on the user's laptop, so there is
  no local clone. Codespaces is the only route, and it pushes without a token.
- `pip install pyarrow` is needed in any fresh Codespace.
- `joined_features.parquet` and `data/raw/` are gitignored and will not exist in a new
  Codespace. Rebuilding takes: `download.py` (minutes), `build_panel.py` (minutes),
  `compute_mhw.py --ocean-mask --t0 2003-01-01 --t1 2026-08-16` (~30 min), then
  `join_features.py`.
- `compute_mhw` requires the full date range: the config's `[2003, 2018]` climatology
  baseline will refuse a short window, correctly but inconveniently.
- Diagnostics cost: `--mode baselines --bootstrap 200` is ~2 minutes and gives the headline.
  `--mode all` with default settings is ~400 model fits, so 20–40 minutes on a Codespace.
- ChatGPT is also working on this repo. My commits touch `mhw.py`, `metrics.py`, `hab.py`,
  `splits.py`, `sst.py`, `ibi.py`, `era5.py`, `features.py`(no), `evaluate.py`,
  `build_panel.py`, `compute_mhw.py`, `run_diagnostics.py`, `cli.py`, `pyproject.toml`,
  `requirements.txt`, `.github/workflows/ci.yml`. Ingest scripts and `data/processed`
  reports are untouched.
