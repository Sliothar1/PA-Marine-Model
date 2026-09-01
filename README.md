# PA-Marine-Model

Train models that, **at each Irish HAB monitoring station**, predict whether a species-group **HAB exceedance occurs in the next 0–2 weeks** from SST and marine-heatwave (MHW) features.

This is a research nowcast / short-range forecast pipeline, not an operational warning product.

**Primary target:** `dinophysis`. Keep `pseudo_nitzschia`. Treat `karenia_mikimotoi` as exploratory (threshold too high / too rare for useful skill).

## Verified data sources (HTTP, 2026-09-01)

**Labels** — Marine Institute ERDDAP `tabledap/habs_phyto`  
https://erddap3.marine.ie/erddap/tabledap/habs_phyto  

Columns used (from `info.json` + a real CSV pull): `scientific_name`, `time`, `latitude`, `longitude`, `location_name`, `location_id`, `count`, `week_no`.  
Counts are cells L⁻¹. Domain filter: 51–56°N, 11–5°W.

Taxon groups (name match on `scientific_name`):

| Target | Match | Exceedance |
| --- | --- | --- |
| `dinophysis` | names containing `Dinophysis` (acuminata, acuta, spp., …) | ≥ 100 cells L⁻¹ |
| `pseudo_nitzschia` | `Pseudo-nitzschia` (delicatissima / seriata complexes) | ≥ 50,000 cells L⁻¹ |
| `karenia_mikimotoi` | `Karenia mikimotoi` | **95th percentile of positive station-week counts on the training split** (fallback 1000 cells L⁻¹ if too few positives). Fitted threshold on the 2026-09-01 full run: **~128,300 cells L⁻¹**. |

**SST** — NOAA OISST v2.1 daily via public ERDDAP `ncdcOisst21Agg` (no Copernicus login)  
https://coastwatch.pfeg.noaa.gov/erddap/info/ncdcOisst21Agg/index.html  

Verified variables: `sst`, `anom`, `err`, `ice` on `(time, zlev, latitude, longitude)`. Longitudes are **0–360**. Irish −11…−5° maps to 349…355. `zlev=0`.

Copernicus OSTIA is listed in `configs/default.yaml` as a future option (`sst.copernicus_ostia.enabled: false`). v1 does not call CMEMS.

Tomcat on the Marine Institute ERDDAP **rejects unencoded `>` / `<`** in the query string; the client percent-encodes constraints.

## MHW (Hobday et al. 2016)

Self-contained implementation in `src/pa_marine/mhw.py` (no `xmhw` dependency):

- Seasonal 90th-percentile threshold and seasonal mean climatology by day-of-year, 11-day window.
- Event if SST > threshold for ≥ 5 days; gaps ≤ 2 days are merged.
- Features: SST, SSTA (SST − seasonal mean), `in_mhw`, duration (day-in-event), cumulative intensity (running sum of SSTA in-event).
- Lags 0/7/14/21 d, rolling 7/14/30 d means, week-of-year sin/cos, lon/lat.

Attached to the **Sunday (ISO week end)** so features use only SST through the monitoring week.

## Horizons (no leakage from future SST)

| Name | Label window from ISO week start | Features |
| --- | --- | --- |
| **nowcast** | days 0–14 (current week + next) | SST/MHW known through week end |
| **ahead_7d** (`ahead7`) | days 7–14 (next week only) | same feature timestamp (no extra future SST) |

## Time split (never random)

- train: ISO years 2003–2018  
- val: 2019–2021  
- test: 2022+

Climatology baseline: mean exceedance rate by ISO week-of-year on **train** only.

## Models, calibration & metrics

- sklearn logistic regression (balanced)  
- LightGBM or XGBoost if installed; otherwise sklearn `HistGradientBoostingClassifier`  
- **Probability calibration:** isotonic (fallback sigmoid if too few positives) fitted on the **validation split only**, then applied to test. Use `scripts/evaluate.py --calibration auto` (default).

Per taxon and horizon: **PR-AUC**, **Brier**, **skill vs week-of-year climatology** — reported raw and calibrated in `data/processed/metrics.json`.

### Full-run test numbers (2026-09-01; see `data/processed/run_summary.md`)

207 stations, 53,172 station-weeks; HAB through 2026-08-30; OISST through **2026-08-16** (ERDDAP axis max).

**Dinophysis nowcast (primary)** — LightGBM: PR-AUC **0.296 → 0.280** after calibration (clim 0.183; PR skill ~**0.12**). Brier skill **−1.10 → −0.01** (raw over-confidence from `class_weight=balanced`; calibration fixes reliability without large ranking change).

**Pseudo-nitzschia nowcast** — LightGBM: small PR skill (~0.04–0.05); Brier skill **−1.23 → +0.02** after calibration.

**Karenia** — fails: test prevalence ≪ 0.1%; PR ≈ / below climatology. Exploratory only.

Ahead-7d Dinophysis LightGBM: PR skill ~0.08 after calibration; Brier skill **−1.89 → −0.05**.

Honest summary: modest PR skill on Dinophysis vs seasonal climatology; calibration is required for usable probabilities; Karenia is not a viable target at the fitted threshold.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# optional: pip install lightgbm xgboost
```

## Run (offline fixture)

```bash
python scripts/run_pipeline.py --fixture
# or pytest
pytest -q
```

## Run (full ERDDAP)

Full Irish HAB extract + per-station OISST time series is large; start with a station cap:

```bash
python scripts/download.py
python scripts/build_panel.py
python scripts/compute_mhw.py --max-stations 5 --t0 2015-01-01 --t1 2024-12-31
python scripts/join_features.py
python scripts/evaluate.py --horizon both --calibration auto
```

Re-evaluate on existing joined features (no OISST re-download):

```bash
python scripts/evaluate.py --joined data/processed/joined_features.parquet --horizon both
```

Probe connectivity:

```bash
python -m pa_marine.cli probe
```

## Caveats

- HAB sampling is irregular; a station-week with no sample is absent (not a true negative).
- Species names change over time; matching is substring-based on verified `scientific_name` values.
- OISST 0.25° is coarse vs inshore stations; nearest-neighbour, no coastal mask.
- MHW climatology in v1 uses the full local series (not a fixed 30-year baseline).
- Do not treat skill on the tiny fixture as scientific evidence.
- Raw (uncalibrated) Brier skill is negative vs week-of-year climatology; use calibrated probabilities for reliability.

## License

MIT. HAB data © Marine Institute (see ERDDAP license). OISST © NOAA.
