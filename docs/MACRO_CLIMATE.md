# Macro climate drivers (NAO / EA / AMO)

**Generated:** 2026-09-02 (Europe/Dublin).  
**Purpose:** Open North Atlantic teleconnection / multidecadal indices for **explanatory power** and Cork / Irish-shelf narrative — not expected to beat the strong 9-feature national Dinophysis baseline.  
**Scripts:** `scripts/ingest_climate_indices.py`, `scripts/join_climate_indices.py`, `scripts/macro_climate_ablation.py`.  
**Related:** Met Éireann / SST package in [`CLIMATE_DRIVERS.md`](CLIMATE_DRIVERS.md) (local radiation, normals, shelf SST). Skip MÉRA / TRANSLATE / ENSO-heavy work here.

---

## 1. Series pulled (open, no login)

| Index | Source | URL | Units | Raw path | Processed |
| --- | --- | --- | --- | --- | --- |
| **NAO monthly** | NOAA CPC | https://www.cpc.ncep.noaa.gov/products/precip/CWlink/pna/norm.nao.monthly.b5001.current.ascii.table | Standardized index | `data/external/climate_indices/raw/nao_monthly_cpc.ascii.table` | `…/processed/nao_monthly.csv` |
| **NAO daily** | NOAA CPC CDAS z500 | https://ftp.cpc.ncep.noaa.gov/cwlinks/norm.daily.nao.cdas.z500.19500101_current.csv | Standardized (monthly SD 1950–2000) | `…/raw/nao_daily_cpc.csv` (+ ascii alt) | `…/processed/nao_daily.csv` |
| **EA monthly** | NOAA CPC teleconnections | https://ftp.cpc.ncep.noaa.gov/wd52dg/data/indices/ea_index.tim | Standardized (1981–2010); −99.90 → NaN | `…/raw/ea_index.tim` | `…/processed/ea_monthly.csv` |
| **AMO / AMV monthly** | NOAA NCEI ERSST v5 | https://www.ncei.noaa.gov/pub/data/cmb/ersst/v5/index/ersst.v5.amo.dat | °C SSTA N. Atlantic 0–60°N | `…/raw/amo_ersst_v5.dat` | `…/processed/amo_monthly.csv` |

**Optional cross-check:** CPC NH teleconnection bundle (NAO + EA columns)  
https://ftp.cpc.ncep.noaa.gov/wd52dg/data/indices/tele_index.nh → `raw/nao_tele_from_nh.tim`.

**KNMI Climate Explorer** (alternate browse / CRU station NAO, not used as primary):  
https://climexp.knmi.nl/ — e.g. CRU NAO http://climexp.knmi.nl/data/inao.dat. Prefer CPC for consistency with daily NAO.

**Note on AMO:** PSL Kaplan-based AMO is **discontinued** (not updating). ERSST v5 AMO from NCEI is the maintained open monthly series used here (often called AMO / AMV interchangeably in applications).

Provenance: `data/external/climate_indices/sources.json`.

### Date ranges (this ingest)

| Series | Start | End | N |
| --- | --- | --- | --- |
| NAO monthly | 1950-01 | 2026-07 | 919 |
| NAO daily | 1950-01-01 | 2026-08-30 | 28 001 |
| EA monthly | 1950-01 | 2026-07 | 919 (valid; −99.90 cleared) |
| AMO monthly | 1854-01 | 2026-07 | 2 071 |

---

## 2. Join helpers (week / month)

**Ingest / build:**

```bash
cd /workspace/pa-marine-model
.venv/bin/python scripts/ingest_climate_indices.py          # or --force to re-download
.venv/bin/python scripts/join_climate_indices.py             # optional panel attach
```

**Bundles:**

| File | Role |
| --- | --- |
| `data/external/climate_indices/processed/climate_indices_monthly.csv` | year, month, `nao`/`ea`/`amo` + lag1–3m + roll3m |
| `data/external/climate_indices/processed/climate_indices_week.csv` | ISO week helper (same cols + daily NAO week aggs) |
| `data/processed/climate_indices_monthly.csv` | mirror for pipeline convenience |
| `data/processed/climate_indices_week.csv` | mirror used by ablation |

**Join keys**

- **Month:** `year` + `month` (calendar month of interest).
- **HAB week panel:** `iso_year` + `iso_week` (same as `joined_features.parquet` / station week panel).

**Week convention**

- Monthly indices are attached via the **calendar month of `week_start`** (Monday of the ISO week).
- Month lags (`*_lag1m` …) are prior **calendar months** on the monthly series, then mapped to that week.
- Daily NAO is aggregated to week: `nao_daily_mean` / min / max / n, plus `nao_daily_mean_lag1w` and `nao_daily_mean_roll4w`.

**Coverage on Irish HAB panel** (`joined_features`, ~2002–2026): ≈ **99.6%** non-null for monthly NAO/EA/AMO; daily NAO week mean ≈ **100%**.

```python
import pandas as pd
panel = pd.read_parquet("data/processed/joined_features.parquet")
week = pd.read_csv("data/processed/climate_indices_week.csv")
week = week.drop(columns=[c for c in ("year", "month", "week_start") if c in week.columns])
panel = panel.merge(week, on=["iso_year", "iso_week"], how="left")
```

Or: `.venv/bin/python scripts/join_climate_indices.py` → `data/processed/joined_features_with_climate_indices.parquet` (does **not** overwrite baseline joined features).

---

## 3. Ablation vs strong 9-feature baseline

- Baseline: `STRONG_OISST` in `src/pa_marine/features.py`; reference PR-AUC ≈ **0.293** (`data/processed/metrics_dino_strong.json`, LightGBM test calibrated).
- Script: `scripts/macro_climate_ablation.py`.
- Report: `data/processed/macro_climate_ablation_report.md`  
- Metrics: `data/processed/macro_climate_ablation_metrics.json`

| config | n_feat | LGBM test cal PR-AUC | Δ vs strong |
| --- | ---: | ---: | ---: |
| `strong` | 9 | **0.2953** | 0 |
| `strong_nao_ea` | 17 | 0.2905 | −0.0048 |
| `strong_amo` | 13 | 0.2572 | −0.0381 |
| `strong_nao_ea_amo` | 21 | 0.2711 | −0.0242 |
| `nao_ea_only` | 8 | 0.0558 | −0.24 |

**Honest verdict:** NAO/EA/AMO lags **do not lift** national Irish Dinophysis nowcast PR-AUC vs strong OISST. Val can look slightly better for `strong_nao_ea` — treat as non-generalising. Keep indices for **regime / Cork narrative** (e.g. NAO/EA phase during June 2023-type events), not as a national feature upgrade. Consistent with Met radiation / ERA5 wind ablations.

---

## 4. Scout only — Bay of Biscay / Galicia Dinophysis (later transfer)

**Not ingested.** URLs + what’s available for a future Iberian transfer / domain-adaptation note:

### Galicia (INTECMAR)

- Production-zone status (biotoxins + microbiology): https://www.intecmar.gal/informacion/  
- Phytoplankton / HAB weekly informes (oceanographic + coastal stations, toxic species counts incl. Dinophysis context): https://www.intecmar.gal/Informacion/fito/informes/  
- REST API for zone status (biotoxins / micro classification) — documented from the información portal (“API REST” link on same site).  
- THREDDS / OPeNDAP (HF radar, bathymetry, etc. — oceanography more than cell counts): https://opendap.intecmar.gal/thredds/catalog.html  
- **What’s available:** operational shellfish-zone closures + weekly phytoplankton reports for Rías (Vigo, Pontevedra, Arousa, …); dense spatial network; API for current zone state. Historical bulk Dinophysis time series may need scrape/PDF/report harvest or a data request — not a single open CSV twin of MI HAB.

### Bay of Biscay / France (Ifremer)

- **REPHY** phytoplankton + hydrology metropolitan dataset (SEANOE): https://doi.org/10.17882/47248 — long coastal phytoplankton records including Dinophysis-related taxa.  
- SEANOE landing: https://www.seanoe.org/data/00361/47248/  
- **REPHYTOX** / sanitary phycotoxin procedures and related Ifremer docs via Archimer / DOI network (linked from REPHY metadata).  
- Surval / envlit portals for coastal surveillance visualisation (Ifremer; URLs shift — start from REPHY DOI + https://wwz.ifremer.fr/surval ).  
- **What’s available:** research-grade open REPHY tables suitable for transfer learning / climatology of Dinophysis along Biscay–Channel; separate from Galician operational ría closures.

### Transfer note (later)

Map Irish MI week panel schema → (1) Galicia zone-week closure / Dinophysis presence from INTECMAR reports/API, (2) REPHY station-week counts on Biscay French coast. Shared drivers candidate: **same NAO/EA/AMO week helper** + OISST/OSTIA shelf SST. Do not deep-ingest until a dedicated Iberian ticket.

---

## 5. Re-run checklist

```bash
.venv/bin/python scripts/ingest_climate_indices.py --force
.venv/bin/python scripts/macro_climate_ablation.py
```

Large raw under `data/external/climate_indices/raw/` may stay box-local / gitignored; small monthly CSVs, week helper, sources.json, and ablation md/json are whitelisted for commit.
