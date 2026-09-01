# Cork Ocean Hackathon — Challenge 4 demo pack

**48-hour teammate guide** for [PA-Marine-Model](https://github.com/Sliothar1/PA-Marine-Model): predict **Dinophysis exceedance** (≥ 100 cells L⁻¹ in the next 0–2 weeks) at HAB stations from SST / marine-heatwave (MHW) features, with a Connemara June 2023 case study linked to the Berthou NW European shelf MHW.

This is a research nowcast demo, **not** an operational warning product.

Generated / verified artifacts: **2026-09-01** (Europe/Dublin). Snapshot without retrain:

```bash
python scripts/demo_snapshot.py
```

---

## 1. Problem (pitch in ~60 s)

| | |
| --- | --- |
| **Hazard** | Dinophysis blooms drive DSP shellfish closures on Irish / Scottish coasts. |
| **Task** | At each monitoring station, will an exceedance occur in the **current + next ISO week** (`y_dinophysis_nowcast`)? |
| **Drivers** | NOAA OISST + Hobday (2016) MHW features; seasonality + geography dominate skill. |
| **Story hook** | June 2023 NW European shelf marine heatwave ([Berthou et al. 2024, *Commun Earth Environ*](https://doi.org/10.1038/s43247-024-01413-8)) — exceptional anticyclonic June, SST anomalies up to ~5 °C north of Ireland. We overlay Irish CRW MHW, Connemara Dinophysis, Mace Head / Spiddal in situ, and Met Éireann Mace Head wind/radiation. **Descriptive**, not causal attribution. |

Labels: Marine Institute ERDDAP `habs_phyto`. SST default: NOAA OISST v2.1 (public ERDDAP). Time split: train 2003–2018 / val 2019–2021 / test 2022+.

---

## 2. Best model (numbers to quote)

**Feature mode `strong` — 9 columns** (ablation winner; drop weak `in_mhw*` / duration noise):

`woy_sin`, `woy_cos`, `latitude`, `longitude`, `sst`, `sst_lag0d`, `sst_lag21d`, `sst_roll7d`, `sst_roll30d`

Protocol: LightGBM + **val-only** isotonic calibration (`--calibration auto`). Primary metric: **PR-AUC** vs week-of-year climatology.

| Region | Model | Test PR-AUC (cal) | Clim PR-AUC | PR skill | Source |
| --- | --- | ---: | ---: | ---: | --- |
| **Ireland** (207 stations) | LightGBM strong | **~0.293** | **~0.183** | ~0.135 | `metrics_dino_strong.json` |
| **Scotland** (96 high/med SINs) | LightGBM strong | **~0.673** | **~0.592** | ~0.199 | `scotland_dino_metrics.json` |

Ireland test n ≈ 14 270, prevalence ≈ 5.2%. Scotland test n ≈ 4 533, prevalence ≈ 30% (easier ranking baseline; still beats clim).

Honest one-liner: modest but real PR skill on Irish Dinophysis; Scotland looks stronger partly because prevalence is higher. Calibration fixes raw Brier over-confidence — quote **calibrated** PR-AUC.

Full ablation notes: `data/processed/dino_feature_report.md`, `ibi_light_mhw_report.md`, `era5_wind_dino_report.md`, `ostia_vs_oisst_report.md`.

---

## 3. Local Connemara paths (Mace Head + Lehanagh + June 2023)

### Sentinel buoys

| Site | ERDDAP | Ingest | Key artifacts |
| --- | --- | --- | --- |
| **Mace Head** | `compass_mace_head` (+ QC `sbe37_macehead`) | `scripts/ingest_sentinel_sites.py` | `compass_mace_head_daily.parquet`, `buoy_hab_join_mace_head.parquet`, `local_sites_report.md` |
| **Lehanagh Pool** | `sentinel_lehanagh` | same | `sentinel_lehanagh_daily.parquet` — **NRT from 2024-05-27** (no June 2023) |

Nearest HAB stations / correlations: `nearest_hab_mace_head.csv`, `buoy_hab_corr_mace_head.csv` (and Lehanagh twins).

### June 2023 case study (Berthou link)

Rebuild from **existing** processed files (no network):

```bash
python scripts/build_june2023_case_study.py
scripts/train_dsp_closure_risk.py
```

| Artifact | Role |
| --- | --- |
| `data/processed/june2023_case_study.md` | Full narrative + honest gaps |
| `june2023_case_study_summary.csv` | One-row metrics table |
| `june2023_case_study_daily.csv` | May–Aug daily CRW + Mace + Spiddal + Met |
| `june2023_case_study_hab_weekly.csv` | Focus-station Dinophysis + OISST MHW |
| `figures/june2023_mhw_met_temp.png` | CRW frac / temps / Met wind+radiation |
| `figures/june2023_dinophysis_connemara.png` | Dinophysis time series |
| `figures/june2023_mace_head_tsdo.png` | Mace Head T / S / DO |

Demo beats (see case study for caveats): Irish-bbox CRW mean frac_mhw in June ≈ **0.96**, peak **1.0** on 19–20 Jun (max cat **5**); Mace Head June mean T ≈ **16 °C**; Rosmuc exceedance week of **29 May**, Mannin week of **10 Jul** — bookend / lag relative to peak MHW, **not** proof of causation.

Scout P0 (CRW, SmartBay, Met Éireann, CONN ROMS note): `scripts/ingest_scout_p0.py` → `scout_ingest_report.md`.

---

## 4. How to run in 48 h

### A. Zero-data smoke (CI / laptop, ~1 min)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# optional for real metrics path: pip install lightgbm
python scripts/run_pipeline.py --fixture
pytest -q
python scripts/demo_snapshot.py
```

Fixture writes tiny `data/processed/{panel,mhw,joined,metrics}.*` — **do not** treat fixture skill as science.

### B. Re-evaluate Ireland on existing join (no OISST re-download)

If `data/processed/joined_features.parquet` is present locally (gitignored parquet; rebuild from README full run if missing):

```bash
python scripts/evaluate.py \
  --joined data/processed/joined_features.parquet \
  --horizon both --calibration auto --feature-mode strong \
  --out data/processed/metrics_dino_strong.json
```

Committed reference metrics (no retrain needed for the demo deck):  
`data/processed/metrics_dino_strong.json`, `dino_feature_report.md`.

### C. Scotland strong nowcast (if SMC panels + OISST already local)

```bash
python scripts/train_scotland_dino.py --skip-download
# first time / missing SST:
# python scripts/geocode_smc_sites.py
# python scripts/train_scotland_dino.py
```

### D. Rebuild June 2023 case study + figures

```bash
python scripts/build_june2023_case_study.py
scripts/train_dsp_closure_risk.py
```

Requires processed CRW summary, HAB panel, joined features, Mace Head daily, Spiddal CTD, Met daily (see case-study “Sources” section).

### E. Optional local re-ingest (network)

```bash
python scripts/ingest_sentinel_sites.py
python scripts/ingest_scout_p0.py   # CRW / SmartBay / Met / CONN probe
```

Full national ERDDAP + OISST is large — use README station-cap path if starting cold.

---

## Ops prototype — DSP / harvest-closure risk

Highest-euro early-warning head: **shellfish DSP toxin exceedance** + optional **area closed** from `habs_status`, scored with the same **strong OISST** features / LightGBM+logreg / val calibration / clim baseline as Dinophysis cells.

```bash
python scripts/train_dsp_closure_risk.py
# optional: complete-SST rows only
python scripts/train_dsp_closure_risk.py --require-sst
```

| Target | Test PR-AUC (LGBM cal) | Clim | PR skill | Notes |
| --- | ---: | ---: | ---: | --- |
| **Area closed** | **~0.315** | ~0.208 | **~0.135** | Partially predictable from SST alone; ~0.46 / skill ~0.31 if SST complete |
| DSP exceed (OA/DTX/PTX) | ~0.009 | ~0.004 | ~0.005 | **Not reliable** — only ~19 test positives (2022+ rarity) |
| Dinophysis cells (ref) | ~0.293 | ~0.183 | ~0.135 | Same feature philosophy |

Honest takeaway: **closure risk ranks about as well as cell exceedance** on SST strong features; **DSP toxin weeks are too scarce on the test window** to claim an ops toxin model yet. Full write-up: `data/processed/dsp_closure_risk_report.md` (+ `dsp_closure_risk_metrics.json`). Ingest path: `scripts/ingest_biotoxin.py`.

---

## 5. Honest limits (what did **not** help)

Quote these so judges trust the science:

| Experiment | Result vs strong OISST (~0.293 cal test PR-AUC) | Report |
| --- | --- | --- |
| **IBI** MLD / light (`mlotst`, `rsntds`, `kd`, `zeu`) ± SSS/currents | Hurt (~−0.10 full test; still ~−0.013 on coverage-matched subset) | `ibi_light_mhw_report.md` |
| **ERA5 wind** (+ rolls) on strong set | Slightly worse (nowcast cal **0.287**, Δ ≈ −0.006) | `era5_wind_dino_report.md` |
| **OSTIA alone** as SST provider | Calibrated LightGBM ~**0.24** vs OISST ~**0.29** — keep OISST default | `ostia_vs_oisst_report.md` |
| Richer continuous MHW packs | Flat to mildly worse; dumping many correlated MHW cols hurts | `ibi_light_mhw_report.md` |
| Binary `in_mhw*` / duration in full 44-feat set | Near-zero LightGBM gain; **strong** 9-feat beats `all` | `dino_feature_report.md` |
| Karenia target | Too rare at fitted threshold — exploratory only | `README.md` / `run_summary.md` |

Other caveats: irregular HAB sampling (missing week ≠ true negative); OISST 0.25° coarse / landmask at some inshore points (e.g. Rosmuc SST NaN); June 2023 **IMI_CONN_3D** archive not on public rolling ERDDAP; Lehanagh has no June 2023; do not claim MHW→bloom causation from two exceedance weeks.

---

## 6. Suggested 48 h schedule

| Block | Focus |
| --- | --- |
| 0–2 h | Clone, `pip install -e ".[dev]"`, fixture + `demo_snapshot.py`, skim this doc + `june2023_case_study.md` |
| 2–6 h | Deck: problem → Ireland/Scotland metrics → June 2023 figures → honest limits |
| 6–12 h | Live demo path: snapshot → open three PNGs → optional `evaluate.py --feature-mode strong` if parquet present |
| Next (if time) | Ablate river Q features (see §7); **DSP/closure ops prototype** (`train_dsp_closure_risk.py`); England/Wales transfer |

---

## 7. Freshwater — OPW Corrib / Galway Bay discharge (**ingested 2026-09-01**)

EPA HydroNet remains interactive-only (data.gov.ie → SPA). **OPW Hydro-Data JSON archives worked** without a browser:

`https://waterlevel.ie/hydro-data/data/internet/stations/0/{station}/{Q|S}/year.json` (`WEB.Day.Mean`).

| Artifact | Path |
| --- | --- |
| Report | `data/processed/rivers_report.md` |
| HAB join note | `data/processed/rivers_hab_join_note.md` |
| Primary ISO-week Q (30061, 31075, 30031) | `data/processed/rivers_week_primary_Q.csv` |
| Raw archives + per-station daily | `data/raw/rivers/` (gitignored) |

**Primary proxies for Connemara HAB:** Owenboliskey **31075** (local coastal) + Corrib outflow **30061** Wolfe Tone (bay-scale). Join on `iso_year`+`iso_week` as regional columns — see join note. Next: ablate vs strong OISST (validate before claiming skill).

---

## 8. Artifact cheat-sheet

```
docs/HACKATHON_DEMO.md                 ← this file
scripts/demo_snapshot.py               ← print key metrics + figure paths
scripts/run_pipeline.py --fixture
scripts/evaluate.py --feature-mode strong
scripts/train_scotland_dino.py
scripts/build_june2023_case_study.py
scripts/train_dsp_closure_risk.py
scripts/ingest_sentinel_sites.py
scripts/ingest_scout_p0.py

data/processed/metrics_dino_strong.json
data/processed/scotland_dino_metrics.json
data/processed/dino_feature_report.md
data/processed/ibi_light_mhw_report.md
data/processed/era5_wind_dino_report.md
data/processed/ostia_vs_oisst_report.md
data/processed/dsp_closure_risk_report.md
data/processed/dsp_closure_risk_metrics.json
data/processed/local_sites_report.md
data/processed/june2023_case_study.md
data/processed/figures/june2023_*.png
```

MIT code; HAB © Marine Institute; OISST © NOAA; cite Berthou et al. (2024) for the June 2023 MHW narrative.
