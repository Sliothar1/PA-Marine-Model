# Scout P0 ingest report

Generated: **2026-09-01 20:58 IST** (Europe/Dublin).

Scope: highest-priority **new** scout datasets. Did **not** re-download OISST / OSTIA / IBI / `habs_phyto`.

## Summary

| Dataset | Status | Notes |
| --- | --- | --- |
| NOAA CRW 5km MHW Watch (STAR NC; PacIOOS `mhw_5km` down) | OK | 1096/1096 days Irish bbox |
| SmartBay CTD (`smartbay_obs_ctd_sbe16` / `spiddal_obs_ctd`) | OK | SBE16 sparse; Spiddal has June 2023 |
| Met Éireann Mace Head wind/radiation | OK | clidata.met.ie CSVs |
| MI Connemara ROMS `IMI_CONN_3D` | PARTIAL | recent surface OK; June 2023 archive not online |

## 1. NOAA Coral Reef Watch 5km MHW Watch

Product: **Daily Global 5km Marine Heatwave Watch v1.0.1** (Hobday et al. 2018 categories on CoralTemp).

- Product page: https://coralreefwatch.noaa.gov/product/marine_heatwave/
- PacIOOS ERDDAP id `mhw_5km`: **unavailable** from this environment (HTTP 404 / TLS EOF).
- Fallback: NOAA STAR HTTPS daily NetCDF `noaa-crw_mhw_v1.0.1_category_YYYYMMDD.nc`.
- Irish bbox extract 51–56°N, 11–5°W for **2022-01-01 → 2024-12-31**.
- Days OK: **1096** / 1096 (June 2023 OK days: **30**).
- Stacked Ireland parquet: `/workspace/pa-marine-model/data/processed/crw_mhw_ireland_daily.parquet` (2.6 MB).
- Daily ocean summary CSV: `data/processed/crw_mhw_ireland_daily_summary.csv`.
- Product JSON: `/workspace/pa-marine-model/data/raw/crw_mhw/product.json`.

### June 2023 snapshot (Berthou MHW paper link)

Irish waters on **2023-06-15** (probe day) showed widespread elevated categories (cats 1–5 present in the bbox).
Use `crw_mhw_ireland_daily_summary.csv` filtered to 2023-06 for event timing vs Irish HAB / Berthou et al. North-East Atlantic MHW context.
Category meanings: 0=no MHW … 5=beyond extreme; NaN/land masked separately.

June 2023 Irish-bbox ocean stats from CRW categories: mean `frac_mhw`=0.964, peak day **2023-06-19** with frac_mhw=1.000, mean_cat=2.64, max_cat=5. All 30 June days ingested.


## 2. SmartBay Observatory CTD

### `smartbay_obs_ctd_sbe16`

- Status: **ok**
- Raw rows: 118975 | daily rows: 146
- Time: 2021-10-06T06:20:00Z → 2023-05-08T13:20:54Z
- Raw bytes: 9641875 | daily parquet: 9503
- Note: Processed CTD+O2; coverage ends 2023-05-08 (no June 2023).

### `spiddal_obs_ctd`

- Status: **ok**
- Raw rows: 5820818 | daily rows: 787
- Time: 2022-04-22T14:49:11Z → 2026-09-01T19:54:16Z
- Raw bytes: 368787638 | daily parquet: 29438
- Note: NRT/raw SmartBay Observatory CTD; includes June 2023.
- June 2023 daily rows: 30 (mean T=12.85585878313736)

## 3. Met Éireann — Mace Head historical wind / radiation

Open CSVs (no API key) via **clidata.met.ie** (data.gov.ie package pages point here). `opendata2.met.ie` is only a welcome landing page.

Exact URLs:

- Daily: https://clidata.met.ie/cli/climate_data/webdata/dly275.csv (includes `wdsp`, `glorad`)
- Hourly: https://clidata.met.ie/cli/climate_data/webdata/hly275.csv
- Monthly: https://clidata.met.ie/cli/climate_data/webdata/mly275.csv
- Keys: https://www.met.ie/cms/assets/uploads/2018/05/KeyDaily.txt / KeyMonthly.txt

- Daily parse: **ok** — rows=8336 (2003-08-14 → 2026-07-31), parquet `162.0 KB`
- June 2023: days=30, mean wind=11.093333333333335 kt, mean glorad=2106.9
- Hourly→daily: **ok** rows_hourly=201336

## 4. MI Connemara ROMS (`IMI_CONN_3D`)

- ERDDAP recent pull: **ok** (2026-08-27T00:00:00Z → 2026-09-04T00:00:00Z), rows=25344, bytes=2200410
- ANALYSIS catalog snapshot files: 504 (IMI_ROMS_HYDRO/CONNEMARA_NATIVE_250M_20L_1H/ANALYSIS/CONN_2026080501_AN.nc … IMI_ROMS_HYDRO/CONNEMARA_NATIVE_250M_20L_1H/ANALYSIS/CONN_2026082600_AN.nc)

**June 2023 subset:** not available on public rolling THREDDS/ERDDAP windows (only ~last 8–30 days).
Documented archive paths in `data/raw/imi_conn/thredds_archive_paths.json` for later when MI publishes longer retention:

- `http://milas.marine.ie/thredds/dodsC/IMI-CONN_AGG`
- `http://milas.marine.ie/thredds/dodsC/IMI_ROMS_HYDRO/CONNEMARA_250M_20L_1H/COMBINED_AGGREGATION`
- `http://milas.marine.ie/thredds/catalog/IMI_ROMS_HYDRO/CONNEMARA_NATIVE_250M_20L_1H/ANALYSIS/catalog.xml`

## Artifacts (committed reports / small summaries)

- `data/processed/scout_ingest_report.md` (this file)
- `data/processed/scout_ingest_summary.json`
- `data/processed/crw_mhw_ireland_daily_summary.csv`
- `data/raw/crw_mhw/product.json`
- `data/raw/met_eireann/sources.json`
- `data/raw/imi_conn/thredds_archive_paths.json`

Large raw CSVs / parquets remain gitignored under `data/raw/` and `data/processed/*`.
