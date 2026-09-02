# Climate drivers package (Met Éireann + Irish-shelf SST)

**Generated:** 2026-09-02 (Europe/Dublin).  
**Purpose:** Open climate context for Dinophysis / HAB explanation (Connemara + Irish shelf).  
**Scripts:** `scripts/ingest_met_climate_drivers.py`, `scripts/build_sst_warming_context.py`, `scripts/climate_drivers_ablation.py`, `scripts/extract_connemara_normals_9120.py`.

Catalogue landing: [Available Data](https://www.met.ie/climate/available-data).

---

## 1. What we added (ingested)

### West-coast synoptic stations (clidata free CSV)

Pattern (no API key): `https://clidata.met.ie/cli/climate_data/webdata/{dly|hly|mly}{STN}.csv`

| ID | Station | Role | Products | Key fields | Date range (daily) | Raw path prefix |
| ---: | --- | --- | --- | --- | --- | --- |
| **2375** | Belmullet | **Primary radiation / sunshine (west)** | daily, hourly, monthly | `glorad`, `sun`, `wdsp`, rain, temps | 1956-09-17 → 2026-07-31 | `data/raw/met_eireann/belmullet_*` |
| **275** | Mace Head | Connemara local | daily, monthly (+ scout hourly) | `glorad`, `wdsp`, rain, temps (**no sun**) | 2003-08-14 → 2026-07-31 | `data/raw/met_eireann/mace_head_*` |
| **1175** | Newport | Mayo / Connemara-adjacent glorad | daily, monthly | `glorad`, `wdsp` (**no sun**) | 2005-02-22 → 2026-07-31 | `data/raw/met_eireann/newport_*` |
| **2275** | Valentia Observatory | SW long wind + radiation | daily, monthly | `glorad`, `sun`, `wdsp` | 1942-01-01 → 2026-07-31 | `data/raw/met_eireann/valentia_*` |
| **1575** | Malin Head | NW long wind + sun/radiation | daily, monthly | `glorad`, `sun`, `wdsp` | 1955-05-01 → 2026-07-31 | `data/raw/met_eireann/malin_head_*` |

Processed daily / week / monthly: `data/processed/{slug}_met_{daily|week|monthly}.{csv,parquet}`.

**Week-scale HAB join panel:** `data/processed/met_west_climate_week.{csv,parquet}`  
Prefer columns `met_glorad` (Mace→Belmullet fill), `met_sun` (**Belmullet**), `met_wdsp`, plus station-prefixed and `met_west_*` composites.

**June 2023 radiation snapshot (daily means):** Belmullet glorad ≈ 2005 J/cm², sun ≈ 7.5 h; Mace Head glorad ≈ 2107 (sun blank).

data.gov.ie mirrors (Belmullet):

- Daily: https://data.gov.ie/dataset/belmullet-daily-data  
- Hourly: https://data.gov.ie/dataset/belmullet-hourly-data  
- Monthly Agmet: https://data.gov.ie/dataset/monthly-weather-belmullet  

### Garry monthly drop (Mace Head)

- **Path:** `data/external/met_eireann/mace_head_monthly.csv`  
- Station: 53.326, −9.901, 21 m; **268 months** Nov 2003–Jul 2026.  
- Columns: `year,month,meant,maxtp,mintp,mnmax,mnmin,rain,gmin,wdsp,maxgt,sun`.  
- **`sun` is 100% blank** — do **not** expect sunshine from this file.  
- rain / meant / wdsp mostly complete. **June 2023 `meant` = 17.0 °C** (heatwave narrative).  
- Folded to: `data/processed/mace_head_garry_monthly.{csv,parquet}` + lag features `data/processed/mace_head_garry_monthly_lag_features.csv` (`meant`/`rain`/`wdsp` lag1m + meant roll3m).  
- Same blank-sun story on open clidata `mly275.csv`.

### Recent Agmet monthly solar (prodapi — ~3 years)

Open JSON (no credentials):

- Belmullet: https://prodapi.met.ie/monthly-data/Belmullet  
- Mace Head: https://prodapi.met.ie/monthly-data/mace-head  
- Valentia: https://prodapi.met.ie/monthly-data/Valentia  
- Malin Head: https://prodapi.met.ie/monthly-data/Malin-Head  

Includes **`solar_radiation`** (total global solar, J/cm²), rainfall, mean temperature, soil T, PE, evaporation. Coverage typically **2023–2026** only.  
Processed: `data/processed/{slug}_agmet_monthly.{csv,parquet}`; raw JSON under `data/raw/met_eireann/*_agmet_monthly.json`.

**Sibling Agmet JSON already on disk (prefer merge — do not re-download):**

| Station | External path |
| --- | --- |
| Mace Head | `data/external/met_eireann/monthly_agmet_mace_head.json` (~6.5 KB) |
| Belmullet | `data/external/met_eireann/monthly_agmet_belmullet.json` (~7.5 KB) |
| Newport | `data/external/met_eireann/monthly_agmet_newport.json` (~7.5 KB) |
| Malin Head | `data/external/met_eireann/monthly_agmet_malin_head.json` (~7.5 KB) |

Flat CSV + LTA companions sit beside each JSON. Ingest should **merge with these files** when present rather than hitting prodapi again.

**Also in `data/external/met_eireann/`:** `daily_mace_head_dly275.csv` (~743 KB), `monthly_classic_mace_head_mly275.csv`, `monthly_classic_malin_head_mly1575.csv` (~45 KB). See **1991–2020 normals** section below for `normals_9120/` (grids gitignored; Connemara extract committed).

**Long radiation/sunshine for HAB weeks → use Belmullet daily `glorad`/`sun` (clidata), not Agmet alone.**


### 1991–2020 1 km climatological NORMALS (Garry drop)

**These are long-term climatological averages, not observations and not HAB week ML features.**

| | |
| --- | --- |
| **What** | Ireland-wide **1×1 km** monthly / seasonal / annual **normals** for 1991–2020 |
| **On disk** | `data/external/met_eireann/normals_9120/` |
| **Grids** | `IE_RR_9120_V2.txt` (+ zip); `IE_TMEAN` / `TMAX` / `TMIN_9120_V2.txt` (+ `IE_T_9120_V2.zip`) |
| **Readmes** | `Readme_9120.txt` (rainfall, Climatological Note **22**), `ReadmeTemp_9120.txt` (temps, Note **23**) |
| **Coords** | Irish Grid **TM65** east/north; columns monthly `m1`–`m12` + `ANN` + `DJF`/`MAM`/`JJA`/`SON` |
| **Units** | Rainfall mm; temperatures °C (to 0.1 °C) |
| **Catalogue** | [Available data](https://www.met.ie/climate/available-data) |

**Use for:** Connemara **anomaly maps** and paper climate context (compare a month/season to the 1991–2020 normal).

**Do NOT use for:** Dinophysis / HAB **week ML feature joins**. Normals have **no time axis** — they are static climatology. Week-scale Met joins stay on **clidata daily/hourly** (Mace Head `275`, Belmullet `2375`, etc.).

**Vs other Met products in this package:**

| Product | Role | HAB week ML? |
| --- | --- | --- |
| **1991–2020 1 km normals** | Climatology baseline for anomalies / maps | **No** |
| Garry `mace_head_monthly.csv` + Agmet monthlies | Monthly **actuals** (meant, rain, Agmet solar) | No (month scale; Agmet ~3 yr) |
| clidata **daily/hourly** Mace + Belmullet | Synoptic actuals → week panel | **Yes** (already ingested) |
| MÉRA / TRANSLATE | Paper / demo story only | **No** |

**Connemara extract (committed):** `data/processed/connemara_normals_9120_extract.csv`  
Script: `scripts/extract_connemara_normals_9120.py` (WGS84→TM65 via EPSG:29903; nearest 1 km cell for Mace Head, Lehanagh Pool, Killary, Belmullet). Periods: June, `JJA`, `ANN` for RR + TMEAN/TMAX/TMIN.

| Site | June TMEAN | June RR | JJA TMEAN | ANN TMEAN |
| --- | ---: | ---: | ---: | ---: |
| Mace Head nearest cell | **13.7 °C** | **79.0 mm** | 14.6 °C | 10.6 °C |
| Connemara bbox mean | 13.4 °C | 105.7 mm | 14.4 °C | 10.1 °C |

**June 2023 vs normal (Mace):** Garry / Agmet monthly **meant = 17.0 °C**, rain **56.1 mm** → approx. **+3.3 °C** vs June TMEAN normal, **drier** than June RR normal (~79 mm). Comparable as monthly mean air temperature vs the same station/coastal cell — not an SST anomaly.

Repo keeps **zips + Readmes +** `connemara_normals_9120_extract.csv`; expanded `IE_*.txt` (~25 MB) stay local/gitignored. Unzip locally to re-run the extract script.

### Island of Ireland long-term T + P (warming narrative)

| Product | URL | Local |
| --- | --- | --- |
| **Temperature** provisional annual series (1900–2024) | https://www.met.ie/cms/assets/uploads/2025/01/longseries_2024.csv | `data/raw/met_eireann_longterm/island_of_ireland_temperature_longseries_2024.csv` → `data/processed/island_of_ireland_temperature_annual.csv` |
| Temperature page | https://www.met.ie/climate/what-we-measure/temperature | — |
| **IIP network** (1850–2010, 25 stations + national) | https://www.met.ie/cms/assets/uploads/2018/01/Long-Term-IIP-network-1.zip | `data/raw/met_eireann_longterm/Long-Term-IIP-network-1.zip` → `data/processed/iip_national_1850_2010_monthly.csv` |
| **IIP composite** 1711–2016 | https://www.met.ie/cms/assets/uploads/2018/01/Long-Term-IIP-1711-2016.zip | → `data/processed/iip_composite_1711_2016.csv` |
| Long-term data sets hub | https://www.met.ie/climate/available-data/long-term-data-sets | — |
| IIP handle / paper archive | http://hdl.handle.net/20.500.14765/76134 | — |

Island of Ireland **air** temperature OLS ≈ **+0.089 °C/decade** (1900–2024; R²≈0.38; clim 1961–1990 ≈ 9.55 °C). Separate from shelf **SST** trend below.

### Irish-shelf June SST warming (OISST / OSTIA)

See **`docs/SST_WARMING_CONTEXT.md`**.

- OISST June station-mean: **≈ +0.30 °C/decade** (2002–2026, R²≈0.07).  
- OSTIA cross-check: **≈ +0.17 °C/decade** (2002–2025).  
- Figure: `docs/climate_assets/irish_shelf_june_sst_trend.png` (also `data/processed/figures/`).  
- Series / metrics: `data/processed/irish_shelf_june_sst_series.csv`, `sst_warming_context_metrics.json`, year features `sst_warming_year_features.csv`.

### Ablation vs strong 9-feature Dinophysis baseline

- Baseline: `STRONG_OISST` in `src/pa_marine/features.py`; reference `data/processed/metrics_dino_strong.json`.  
- Extras: Met radiation/sun/wdsp (+lags), Connemara river Q (`rivers_week_primary_Q.csv`), June SST warming proxies.  
- **Honest verdict: no national lift.** Best LightGBM test calibrated PR-AUC remains **strong** (~0.295); Met / river / warming configs are flat or worse on test (val can look better — treat as overfitting / spatial mismatch).  
- Report: `data/processed/climate_drivers_ablation_report.md`  
- Metrics: `data/processed/climate_drivers_ablation_metrics.json`

---

## 2. MÉRA + TRANSLATE (paper / demo story only)

**Not ingested** into the HAB feature store (no new credentials; full archives are heavy GRIB / projection stacks).

| Resource | URL | Note |
| --- | --- | --- |
| MÉRA landing | https://www.met.ie/climate/available-data/mera | Systematic Irish climate reanalysis |
| MÉRA data list | https://www.met.ie/climate/mera-data-list/ | Parameter catalogue |
| MÉRA sample GRIBs | https://www.met.ie/downloads/MERA_PRODYEAR_2015_06_*.grb | Tiny samples only |
| MÉRA parameter PDF | https://www.met.ie/cms/assets/uploads/2017/10/MERA-available-parameters.pdf | |
| MÉRA download guide PDF | https://www.met.ie/cms/assets/uploads/2017/10/meraDataForDownload.pdf | Access workflow — do not invent credentials |
| TRANSLATE science | https://www.met.ie/science/translate | Standardised future climate projections for Ireland |
| TRANSLATE portal | https://www.met.ie/translate2 | Decision-maker climate services |

Use for narrative (“Ireland’s reanalysis / standardised projections exist”) — not for week-scale Dinophysis joins in this package.

---

## 3. What Garry might still export manually (if blocked / incomplete)

Open clidata + Agmet cover most operational needs. **Already on disk for HAB week joins:** clidata daily (and Belmullet hourly) for **Mace Head + Belmullet** — use those, not the 1991–2020 normals grids. Manual / browser export still useful when:

1. **Mace Head sunshine** — blank on Garry monthly + open `mly275`. Prefer **Belmullet daily `sun`/`glorad`** (`dly2375`) or Belmullet monthly `sun` (`mly2375`, 701 non-null months). Optional: Met Climate Statement PDFs for narrative months.  
2. **Climate Statements** (monthly/annual narrative PDFs) — https://www.met.ie/climate/climate-change and monthly data hub https://www.met.ie/climate/available-data/monthly-data — not open bulk CSV.  
3. **Local Connemara precip** — Roundstone `dly1725` is open but rain-only.  
4. **Airport sun without glorad** — Shannon `dly518`, Knock `dly4935` (documented candidates; not required for west panel).  
5. **Full MÉRA fields / TRANSLATE grids** — follow Met Éireann access workflow on pages above (no credentials in-repo).  
6. **Updated Island of Ireland Temperature CSV** — re-download from temperature page when Met publishes post-2024 provisional updates.

Ingest provenance JSON: `data/raw/met_eireann/sources_climate_drivers.json`  
Ingest summary: `data/processed/met_climate_drivers_ingest_summary.json`

---

## 4. How to re-run

```bash
cd /workspace/pa-marine-model
.venv/bin/python scripts/ingest_met_climate_drivers.py
.venv/bin/python scripts/build_sst_warming_context.py
.venv/bin/python scripts/climate_drivers_ablation.py
# optional — needs local normals_9120/*.txt grids
.venv/bin/python scripts/extract_connemara_normals_9120.py
```

Large raw CSVs / parquets / `normals_9120` grids stay gitignored; small metrics/markdown/figures / Connemara normals extract / normals Readmes are whitelisted in `.gitignore`.
