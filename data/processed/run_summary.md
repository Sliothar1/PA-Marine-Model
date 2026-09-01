# Full Irish HAB + MHW pipeline run (non-fixture)

Run date: 2026-09-01. Initial wall clock **~10 minutes** for data; calibration re-eval on existing `joined_features.parquet` **~26 s** (no OISST re-download).

## Data

| Artifact | Path | Size |
| --- | --- | --- |
| HAB extract | `data/raw/habs_phyto.csv` | 65 MB, **765,005** rows, 2002-11-18 → 2026-08-30 |
| OISST (station pixels) | `data/raw/oisst_daily.parquet` | 2.1 MB, **1,857,825** station-days |
| Station-week panel | `data/processed/station_week_panel.parquet` | 285 KB |
| Daily MHW | `data/processed/mhw_daily.parquet` | 9.5 MB, 1,861,758 rows |
| Joined features | `data/processed/joined_features.parquet` | 2.4 MB |
| Metrics | `data/processed/metrics.json` | ~22 KB (raw + calibrated) |

- **n stations:** 207 (`location_id`)
- **n station-weeks:** 53,172 (train 29,683 / val 9,189 / test 14,270 / drop 30 from ISO 2002)
- Unique OISST 0.25° pixels used: 57, from a tight Irish griddap bbox **51.125–55.875N, 349.125–354.875E** (0–360 lon), yearly chunks 2002–2025 plus 2026-01-01…**2026-08-16**

## Thresholds

- dinophysis: 100 cells L⁻¹ (fixed) — **primary target**
- pseudo_nitzschia: 50,000 cells L⁻¹ (fixed) — kept
- karenia_mikimotoi: **128,302.1** cells L⁻¹ (95th percentile of positive train counts) — **exploratory only** (threshold high / too rare)

## Same-week class rates (`y_*` on the panel, all splits)

| Taxon | rate | n positives |
| --- | --- | --- |
| dinophysis | 0.0623 | 3,312 |
| pseudo_nitzschia | 0.0243 | 1,291 |
| karenia_mikimotoi | 0.00278 | 148 |

## Models & calibration

sklearn **logreg** (balanced) and **lightgbm** 4.7.0. Horizons: nowcast and ahead7. Splits: train 2003–2018, val 2019–2021, test 2022+.

**Probability calibration:** isotonic (or sigmoid if too few positives) fitted on the **validation split only** after the base model is trained on train. Test metrics below use that val-fitted calibrator (no test leakage into the calibrator).

### Test-set PR-AUC / Brier before vs after calibration

**dinophysis nowcast** (test prev 0.052) — primary

| model | PR-AUC raw | PR-AUC cal | PR clim | PR skill cal | Brier raw | Brier cal | Brier clim | Brier skill raw | Brier skill cal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| logreg | 0.237 | 0.221 | 0.183 | 0.046 | 0.167 | 0.0534 | 0.0523 | −2.189 | −0.021 |
| lightgbm | 0.296 | 0.280 | 0.183 | 0.119 | 0.110 | 0.0527 | 0.0523 | −1.095 | −0.008 |

**pseudo_nitzschia nowcast** (test prev 0.046)

| model | PR-AUC raw | PR-AUC cal | PR clim | PR skill cal | Brier raw | Brier cal | Brier clim | Brier skill raw | Brier skill cal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| logreg | 0.081 | 0.080 | 0.080 | ~0 | 0.191 | 0.0430 | 0.0431 | −3.424 | +0.002 |
| lightgbm | 0.126 | 0.116 | 0.080 | 0.039 | 0.096 | 0.0422 | 0.0431 | −1.226 | +0.021 |

**karenia_mikimotoi nowcast** (test prev 0.00091) — fails as a useful target

| model | PR-AUC raw/cal | PR clim | Brier skill raw → cal |
| --- | --- | --- | --- |
| logreg | 0.002 | 0.004 | −128 → +0.095 (sigmoid; PR still below clim) |
| lightgbm | 0.004 | 0.004 | −32 → +0.128 (sigmoid; no ranking skill) |

**dinophysis ahead7** (test prev 0.036)

| model | PR-AUC raw | PR-AUC cal | PR clim | PR skill cal | Brier skill raw → cal |
| --- | --- | --- | --- | --- | --- |
| logreg | 0.176 | 0.165 | 0.130 | 0.040 | −3.51 → −0.026 |
| lightgbm | 0.213 | 0.197 | 0.130 | 0.078 | −1.89 → −0.048 |

**pseudo_nitzschia ahead7**

| model | PR-AUC raw | PR-AUC cal | PR clim | PR skill cal | Brier skill raw → cal |
| --- | --- | --- | --- | --- | --- |
| logreg | 0.053 | 0.053 | 0.051 | 0.003 | −5.39 → ~0 |
| lightgbm | 0.085 | 0.074 | 0.051 | 0.025 | −1.90 → +0.010 |

### Takeaways (honest)

1. **Dinophysis** has small but real PR skill vs week-of-year climatology (LightGBM nowcast test PR skill ~0.12 after calibration; raw was ~0.14). Ranking is only modestly above seasonal baseline.
2. **Raw Brier skill was strongly negative** everywhere because `class_weight=balanced` over-confidences probabilities. **Val-only isotonic/sigmoid calibration** brings Brier roughly in line with climatology (skill ≈ 0) without large PR-AUC change.
3. **Pseudo-nitzschia** has weaker PR skill; calibration again fixes Brier.
4. **Karenia** is too rare / threshold too high for useful discrimination; treat as exploratory only. Calibration improves Brier by shrinking probs toward prevalence, but PR remains ~climatology.

## Failures / caveats

1. NOAA `ncdcOisst21Agg` time axis max was **2026-08-16T12:00Z**. Query to 2026-08-31 404’d; 2026 SST is **2002–2025 full years + 2026-01-01…2026-08-16**. HAB labels exist through 2026-08-30; late-Aug 2026 weeks may miss SST/MHW (left join).
2. No fabricated SST. Full global cube was not downloaded.
3. Calibrated val metrics are in-sample for the calibrator; trust **test** calibrated numbers.

## Code changes

- `src/pa_marine/calibration.py` — val-only isotonic/sigmoid calibrator
- `scripts/evaluate.py` — `--horizon both`, `--calibration auto|isotonic|sigmoid|none`, reports raw + `*_calibrated`
- `src/pa_marine/sst.py` — yearly Irish bbox download, unique 0.25° pixels, retries
- `src/pa_marine/erddap.py` — longer HTTP timeouts
- `scripts/compute_mhw.py` — default `--t1` 2026-08-16
- `.gitignore` — still ignores huge processed parquet; allows `metrics.json` + `run_summary.md`

Metrics path: `data/processed/metrics.json`
