# Climate drivers package (Met Éireann + Irish-shelf SST)

**Generated:** 2026-09-02 (Europe/Dublin).  
**Purpose:** Open climate context for Dinophysis / HAB explanation (Connemara + Irish shelf).  
**Scripts:** `scripts/ingest_met_climate_drivers.py`, `scripts/build_sst_warming_context.py`, `scripts/climate_drivers_ablation.py`, `scripts/extract_connemara_normals_9120.py`, `scripts/build_cpr_aoi_week.py`.

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

### Historical Data gold (Garry drop — box-local)

CSVs live under `data/external/met_eireann/historical/` (**gitignored**; keep on the shared box). Manifest: `historical/sources.json` (committed).

| File | Use |
| --- | --- |
| `belmullet_daily_dly2375.csv` | **Prefer as west-coast radiation/sunshine truth** (`glorad` + `sun`). Range 1956-09-17→2026-07-31; sun/glorad essentially complete from ~2000 onward. **MD5-identical** to `data/raw/met_eireann/belmullet_daily_dly2375.csv` (clidata ingest) — `met_west_climate_week` already uses Belmullet for `met_sun` / glorad fill. No re-download needed. |
| `mace_head_hourly_hly275.csv` | Mace Head **hourly** Aug 2003→Aug 2026 (~201k rows): rain / temp / `wdsp` / `wddir` / `msl`. **No sun/glorad.** Use for **sub-daily wind/pressure case studies** (e.g. June 2023), not week-panel radiation. Also at `data/raw/met_eireann/mace_head_hourly_hly275.csv`. |

National Dinophysis ablation was **not** re-run for this drop (Belmullet already in the week panel; hourly is case-study scale).

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

**Also in `data/external/met_eireann/`:** `daily_mace_head_dly275.csv` (~743 KB), `monthly_classic_mace_head_mly275.csv`, `monthly_classic_malin_head_mly1575.csv` (~45 KB). See **1991–2020 normals** section below for `normals_9120/` (IE_*.txt gitignored; **zips + Readmes + extract** committed).

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
Script: `scripts/extract_connemara_normals_9120.py` (WGS84→TM65 via **EPSG:29902**; nearest 1 km cell for Mace Head, Lehanagh Pool, Killary, Belmullet; plus Connemara bbox mean/median over lat 53.20–53.55, lon −10.20–−9.40). Periods: June (`m6`), `JJA`, `ANN` for RR + TMEAN/TMAX/TMIN.

| Site | June TMEAN | June RR | JJA TMEAN | ANN TMEAN |
| --- | ---: | ---: | ---: | ---: |
| Mace Head nearest | **13.7 °C** | **79.0 mm** | 14.6 °C | 10.6 °C |
| Lehanagh Pool nearest | 13.8 °C | 94.6 mm | 14.8 °C | 10.5 °C |
| Killary nearest | 13.9 °C | 114.6 mm | 14.8 °C | 10.6 °C |
| Belmullet nearest | 13.4 °C | 77.9 mm | 14.4 °C | 10.4 °C |
| Connemara bbox mean (1303 cells) | 13.4 °C | 105.7 mm | 14.4 °C | 10.1 °C |

**June 2023 vs normal (Mace):** Garry / Agmet monthly **meant = 17.0 °C**, rain **56.1 mm** → approx. **+3.3 °C** vs June TMEAN normal, **drier** than June RR normal (~79 mm). Comparable as monthly mean air temperature vs the same station/coastal cell — not an SST anomaly.

Large `*.txt` grids and `*.zip` archives under `normals_9120/` stay **gitignored** (~30 MB); **Readmes** + `connemara_normals_9120_extract.csv` are tracked. Re-drop / unzip grids locally from the Met catalogue to re-run the extract script.

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

---

## 5. Macro teleconnections (NAO / EA / AMO)

Open CPC / NCEI indices for explanatory / Cork narrative live in **[`MACRO_CLIMATE.md`](MACRO_CLIMATE.md)**.

- Ingest: `scripts/ingest_climate_indices.py` → `data/external/climate_indices/`
- Week join: `data/processed/climate_indices_week.csv` (`iso_year`, `iso_week`)
- Ablation: `scripts/macro_climate_ablation.py` — **no national PR-AUC lift** vs `STRONG_OISST`

## 6. MBA CPR IrishHeatwaves (AOI-week covariates — not Met/NAO)

MBA Continuous Plankton Recorder extract (Pierre Hélaouët; DOI [10.17031/6a9e6f4a00142](https://doi.org/10.17031/6a9e6f4a00142)) — **group aggregates only**. Full notes: **[`CPR_MBA.md`](CPR_MBA.md)**.

CPR is **AOI-week covariates** (dinoflagellates / diatoms / copepods / PCI) for Irish Sea / Celtic / Scotland-west / heatwave–shelf narrative. It is **not** a replacement for Met Éireann radiation/wind (`met_west_climate_week`) or NAO/EA/AMO teleconnections ([`MACRO_CLIMATE.md`](MACRO_CLIMATE.md)).

- **Build:** `scripts/build_cpr_aoi_week.py` → `data/processed/cpr_aoi_week.csv` + `cpr_aoi_summary.json`.
- **Join:** left-join HAB week panel on `iso_year` + `iso_week` after filtering `aoi` (Connemara nested = **0** tows; west shelf sparse ~35).
- **Not** species-level Dinophysis; heavy CPR ingest stays with PA (`scripts/ingest_cpr_mba.py`).

## 7. Ocean colour Chl + OSI SAF SST (spring–summer MHW × Dinophysis)

**Purpose:** Fold **open** Copernicus/WEkEO chlorophyll and **EUMETSAT OSI SAF** SST into the Cork Ocean Hackathon story as shelf bloom context + independent SST/MHW check. Not a Sextant weekend dump.

### (a) Ocean colour — chlorophyll

| | |
| --- | --- |
| **Product** | `OCEANCOLOUR_ATL_BGC_L4_MY_009_118` (Copernicus-GlobColour Atlantic L4) |
| **Dataset** | `cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D` |
| **Variable** | `CHL` (mg m⁻³), daily **gap-free** multi-sensor, ~1 km |
| **Coverage** | 1997 → ongoing; bbox includes Irish shelf (−46…13°E, 20…66°N) |
| **Why this one** | Long MY series for station-weeks 2002–2026; gap-free so week joins don’t die on cloud; WEkEO mirrors the same CMEMS IDs |
| **Not chosen (yet)** | NWS/IBI HR Sentinel-2 Chl (`OCEANCOLOUR_NWS_BGC_HR_*`) — coastal 100 m but short/gappy; better for case-study maps than national week ML |
| **Access** | Prefer public CloudFerro **ARCO** zarr (`zarr_format=2`); `copernicusmarine` TLS broken on box |
| **Script** | `scripts/download_oc_chl.py` → `data/raw/oc_chl_daily.parquet` |
| **Module** | `src/pa_marine/oc_chl.py` |

### (b) OSI SAF / ODYSSEA SST lane — Climate Drivers (full extract 2026-09-08)

| | |
| --- | --- |
| **Preferred** | **OSI-202-c** NAR L3C Metop-B/AVHRR (~2 km, GHRSST `AVHRR_SST_METOP_B_NAR-OSISAF-L3C-v1.0`) · DOI [10.15770/EUM_SAF_OSI_NRT_2012](https://doi.org/10.15770/EUM_SAF_OSI_NRT_2012) · **CC BY 4.0** |
| **Working product** | CMEMS **ODYSSEA** L4 `SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025` / `IFREMER-ATL-SST-L4-NRT-OBS_FULL_TIME_SERIE` · DOI [10.48670/moi-00152](https://doi.org/10.48670/moi-00152) (OSI SAF among IR/MW inputs; gap-free ~0.02°) |
| **Auth note (Gatekeeper)** | `copernicusmarine` login to `auth.marine.copernicus.eu` fails **TLS EOF** from this box (creds present; CLI auth broken). **Working path:** public CloudFerro ARCO zarr HTTPS with `zarr_format=2` |
| **ARCO URI** | `https://s3.waw3-1.cloudferro.com/mdl-arco-time-045/arco/SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025/IFREMER-ATL-SST-L4-NRT-OBS_FULL_TIME_SERIE_201904/timeChunked.zarr` |
| **Full extract** | **207** Irish HAB stations (nearest-ocean grid from `station_week_panel`) · **2018-01-01 → 2026-09-06** (catalogue) · **656 190** station-days · **3170**/3171 days (skipped ARCO-403 day **2018-10-22**) · 0% NaN on kept days |
| **Pilot reuse** | `data/raw/osi_saf/odyssea_pilot_2023_jun.parquet` (150 rows, 5 Connemara stations, Jun 2023) kept; bit-identical overlap vs full extract |
| **Paths** | `data/processed/odyssea_station_day.parquet` (~2.2 MB) · `data/processed/odyssea_station_week.parquet` · `data/processed/joined_features_osi_sst.parquet` · `data/processed/odyssea_arco_summary.json` · `data/processed/odyssea_station_pixel_map.csv` · `data/raw/osi_saf/sources.json` · status: `docs/CHL_OSI_STATUS.md` |
| **Scripts** | `PYTHONPATH=src .venv/bin/python scripts/extract_odyssea_station_day_arco.py` · helpers `open_odyssea_arco` / `download_odyssea_for_stations` in `src/pa_marine/osi_saf_sst.py` |
| **OSI-202-c access (this box)** | Anonymous **Ifremer FTP via `curl --ftp-pasv`** works (`nar_avhrr_metop_b/{year}/{doy}/{granule}.nc`); ftplib NLST often times out; HTTPS TLS EOF; PO.DAAC needs Earthdata. Sample NAR L3C extract: **4** granules → `data/processed/osi_saf_nar_station_day.parquet` (5 stations × 3 clear-sky days in Jun 2023; cloudy L3C → prefer ODYSSEA for gap-free week joins). Script: `scripts/download_osi_saf_nar_pilot.py` |
| **Not owned here** | Ocean-colour Chl ingest — do **not** pull Chl in this lane (Gatekeeper) |

### Week-join schema

1. **Chl daily** at nearest ocean pixel → `chl`, `chl_log1p` + lags `{0,7,14,21}` + rolls `{7,14,30}` → attach at `feat_date = week_start + 6d` (same as SST/MHW).
2. **OSI SAF** clear-sky daily → ISO-week mean `osi_sst_week`, `osi_sst_n_clear`; optional `osi_minus_oisst` vs OISST week-end `sst`.
3. Join script: `scripts/join_oc_osi_week.py` → `data/processed/joined_features_oc_osi.parquet`.

Feature sets in `src/pa_marine/features.py`: `OC_CHL_CORE`, `OSI_SAF_WEEK`; modes `strong_chl`, `strong_osi`, `strong_chl_osi`.

### Ablation plan vs strong 9-feature baseline

Baseline = `STRONG_OISST` (test PR-AUC ~0.29 vs clim ~0.18 from prior runs — **do not re-invent**).

| Config | Features |
| --- | --- |
| STRONG_OISST | season + lat/lon + SST lags/rolls |
| STRONG+CHL | + `OC_CHL_CORE` |
| STRONG+OSI | + `OSI_SAF_WEEK` |
| STRONG+CHL+OSI | both |

Optional: `--apr-sep` (spring–summer filter on `week_start` month).

```bash
.venv/bin/python scripts/download_oc_chl.py
.venv/bin/python scripts/download_osi_saf_sst.py --t0 2023-06-01 --t1 2023-06-30
# after Earthdata/FTP granule pull + daily extract:
.venv/bin/python scripts/join_oc_osi_week.py --osi-daily data/raw/osi_saf_sst/osi_sst_daily.parquet
.venv/bin/python scripts/oc_osi_ablation.py
.venv/bin/python scripts/oc_osi_ablation.py --apr-sep
```

Status scratchpad: `docs/CHL_OSI_STATUS.md`.

### (c) Pull status + ablation (2026-09-08, Europe/Dublin)

| Lane | On disk | Product IDs | Date range | Join keys |
| --- | --- | --- | --- | --- |
| **OC Chl** | `data/external/ocean_colour/chl_station_daily.parquet` · week `data/processed/ocean_colour_chl_week.csv` · sources `data/external/ocean_colour/sources.json` | Product `OCEANCOLOUR_ATL_BGC_L4_MY_009_118` · dataset `cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D` · var `CHL` | **2003-01-01 → 2026-08-31** · 207 stations · **1 789 308** station-days · week 255 852 · train chl cov **99.64%** | `location_id` + `feat_date=week_start+6d` (lags/rolls) or `iso_year`+`iso_week` |
| **OSI SAF cross-check (working)** | `data/external/osi_saf_sst/osi_sst_daily.parquet` (+ ODYSSEA week) · sources `data/external/osi_saf_sst/sources.json` | ODYSSEA L4 `SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025` / `IFREMER-ATL-SST-L4-NRT-OBS_FULL_TIME_SERIE` (OSI SAF among IR/MW inputs) | **2018-01-01 → 2026-09-06** | `location_id`,`iso_year`,`iso_week` → `osi_sst_week` |
| **True OSI SAF (partial)** | OSI-202-c NAR FTP pilot + OSI-203-a Metop-B NHL L3C spring–summer extract in progress (`scripts/ingest_osi_saf_sst.py` → `data/external/osi_saf_sst/`) | OSI-202-c / OSI-203-a | spring–summer midday passes | same week keys when complete |

**Auth blockers:** `auth.marine.copernicus.eu` TLS EOF (`CouldNotConnectToAuthenticationSystem`) — Chl + ODYSSEA pulled via **anonymous CloudFerro ARCO** instead of toolbox login. Ifremer HTTPS TLS EOF; NAR granules via anonymous `curl --ftp-pasv`.

**Joined panel:** `data/processed/joined_features_oc_osi.parquet` (Chl train/test coverage ≈ **0.994**).

**Ablation vs `STRONG_OISST` (LightGBM test calibrated PR-AUC; full Chl 2003–2026, cov≈0.993):**

| config | n_feat | test cal PR-AUC | Δ vs strong |
| --- | ---: | ---: | ---: |
| `strong` | 9 | **0.2953** | — |
| `strong_chl` | 19 | 0.2833 | −0.0120 |
| `strong_osi` (ODYSSEA week) | 12 | 0.2764 | −0.0189 |
| `strong_chl_osi` | 22 | 0.2850 | −0.0103 |

**Honest verdict: no national lift** — STRONG alone wins. Report: `data/processed/oc_osi_ablation_report.md` · metrics JSON beside it.



### (d) Multi-decade SST L4 for OISST provider-swap — decision (2026-09-08)

**PA ask:** longer **open SST L4** (≤2003, train 2003–2018) on CloudFerro ARCO / anonymous HTTPS, not OISST rebranded?

**Answer: No for ARCO swap.** Multi-decade L4 that *does* cover train is **OSTIA REP** — already on disk and **already lost to OISST** as predictive provider.

| Product | Train coverage | Access | Outcome |
| --- | --- | --- | --- |
| ODYSSEA Atl L4 NRT `010_025` | starts **2018** | CloudFerro ARCO zarr (working) | **Park predictive swap** |
| OSTIA GLO L4 REP `010_011` | disk **2002-01-01 → 2026-03-31** | `copernicusmarine` (local parquet; auth TLS broken from box) | Tested — cal PR-AUC **~0.24 vs OISST ~0.29** (`ostia_vs_oisst_report.md`); keep OISST default |
| Other CCI/MY L4 anonymous ARCO | — | not located like ODYSSEA | Stop hunting; no invented URLs/creds |


**Cork:** narrative SST (June 2023) only. ODYSSEA 2018+ extract = **exploratory-only** — **no judge-card quote**, no national Δ.

**Chl MY gate (2026-09-08):** train covered (~99%); STRONG+CHL Δ test cal PR-AUC **−0.008** vs STRONG **0.295** — no skill claim; Cork quote unchanged. See `CHL_OSI_STATUS.md`.
**Pivot:** GlobColour Chl MY `OCEANCOLOUR_ATL_BGC_L4_MY_009_118` (~1997 → ongoing) covers the locked train. See §7(a) and `docs/CHL_OSI_STATUS.md`.
**Chl fill update (Climate Drivers, 2026-09-08 12:37 IST):** late-only / 2018+ / 2023 pilot was **not** Cork-claimable. Full MY station daily now on disk: `data/raw/oc_chl_daily.parquet` **1 789 308** rows · **207** stn · **2003-01-01 → 2026-08-31** (ARCO span 1997-10-01→2026-08-31; early years optional). Week: `data/processed/ocean_colour_chl_week.parquet`. Coverage on `joined_features`: train **99.64%** / val **99.66%** / test **99.67%** finite `chl_mean` (was ~11% train when ODYSSEA-dated / late-only). See `docs/CHL_OSI_STATUS.md`. Do not duplicate download — Prediction Gatekeeper should join/ablate only.

