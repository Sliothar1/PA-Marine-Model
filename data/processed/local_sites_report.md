# Local Connemara sentinel sites

Hackathon add-on: Marine Institute sentinel buoys near Connemara HAB stations.

Schemas verified **2026-09-01** via `info.json` + small `tabledap` CSV probes on
`https://erddap.marine.ie/erddap`. NRT feeds are **raw** (not fully QC'd).

## Dataset IDs

| Site | NRT dataset | QC / delayed | Lat, Lon | Coverage (info.json / pull) |
| --- | --- | --- | --- | --- |
| Mace Head | `compass_mace_head` | `sbe37_macehead` (SBE37 T/S/O₂, ~2018-06→2022-03) | 53.3306, -9.9326 | NRT pull 2018-05-01 13:50:00+00:00 → 2026-08-31 00:00:00+00:00 (232298 rows, 2999 days) |
| Lehanagh Pool | `sentinel_lehanagh` | _(none published)_ | 53.4001, -9.8207 | NRT pull 2024-05-27 13:30:00+00:00 → 2026-08-31 00:00:00+00:00 (106549 rows, 821 days) |

### Variables of interest (verified column names)

**Mace Head (`compass_mace_head`):** `sbe_temp_avg`, `sbe_salinity_avg`, `sbe_do_avg`,
`suna_nitrate_conc_avg`, `sami_ph_avg` / `seafet_ph_ext_avg`, `contros_pco2_avg`,
`wind_speed`, `wind_direction`, `wind_gust`.

**Lehanagh (`sentinel_lehanagh`):** `SBE_Temp_Avg`, `SBE_Salinity_Avg`, `SBE_DO_Avg`,
`EXO2_Chlorophyll_ug`, `EXO2_Phycoerythrin`, `EXO2_Turbidity`, `EXO2_RDO_Saturation`,
`Wind_Speed`, … (EXO2 sonde + SBE CTD + met).

Raw CSVs: `data/raw/sentinel/`. Daily + ISO-week aggregates: `data/processed/*_{daily,week}.parquet`.

## Mace Head — nearest Irish `habs_phyto` stations

Within ~30 km of buoy; flag stations with `year_max >= 2018` for join.

|   location_id | location_name       |   latitude |   longitude |   dist_km |   n_weeks |   year_min |   year_max | overlap_years   |
|--------------:|:--------------------|-----------:|------------:|----------:|----------:|-----------:|-----------:|:----------------|
|           634 | Letterard           |    53.3747 |    -9.8687  |       6.5 |        24 |       2009 |       2012 | False           |
|           628 | Crumpan Pier        |    53.3122 |    -9.82692 |       7.3 |       330 |       2008 |       2016 | False           |
|           160 | Illaungorm          |    53.3811 |    -9.85556 |       7.6 |         3 |       2004 |       2004 | False           |
|           373 | Saltpoint           |    53.3846 |    -9.85832 |       7.8 |        20 |       2002 |       2011 | False           |
|           372 | Letterard           |    53.3846 |    -9.85832 |       7.8 |       174 |       2005 |       2014 | False           |
|           374 | Outer Bertragh Buoi |    53.3846 |    -9.85832 |       7.8 |         5 |       2003 |       2013 | False           |
|           633 | Lehannagh Pool      |    53.4012 |    -9.8266  |      10.5 |        25 |       2009 |       2020 | True            |
|           622 | Carraig Na Meachain |    53.2499 |    -9.82501 |      11.5 |         3 |       2008 |       2008 | False           |
|           400 | Ardmore             |    53.3003 |    -9.76548 |      11.6 |        69 |       2003 |       2015 | False           |
|           401 | Birbeg              |    53.2806 |    -9.77923 |      11.6 |         8 |       2007 |       2008 | False           |
|           416 | Birmore             |    53.273  |    -9.785   |      11.7 |         1 |       2007 |       2007 | False           |
|           176 | Illauneragh         |    53.2783 |    -9.74806 |      13.6 |         1 |       2005 |       2005 | False           |
|           396 | Oilean Iarthach     |    53.2882 |    -9.73658 |      13.9 |        12 |       2004 |       2008 | False           |
|           399 | Red Flag            |    53.2371 |    -9.78851 |      14.1 |        47 |       2003 |       2010 | False           |
|           398 | Danoish             |    53.2662 |    -9.74297 |      14.5 |       116 |       2003 |       2014 | False           |

### Active stations with year_max ≥ 2018 (demo join set)

|   location_id | location_name   |   latitude |   longitude |   dist_km |   n_weeks |   year_min |   year_max | overlap_years   |
|--------------:|:----------------|-----------:|------------:|----------:|----------:|-----------:|-----------:|:----------------|
|           633 | Lehannagh Pool  |    53.4012 |     -9.8266 |      10.5 |        25 |       2009 |       2020 | True            |

**Join set (up to 8 nearest with overlap):** `[633, 177, 169, 179, 174, 650, 163, 825]` → 1706 station-weeks from 2018+.

### Optional buoy ↔ HAB correlation (station-weeks)

Pearson *r* between weekly buoy means and HAB counts / Dinophysis labels (even tiny |r| is reported).

| x              | y                       |    n |   pearson_r | note   |
|:---------------|:------------------------|-----:|------------:|:-------|
| do_mg_l        | count_dinophysis        | 1564 |      -0.092 |        |
| do_mg_l        | count_pseudo_nitzschia  | 1564 |      -0.046 |        |
| do_mg_l        | count_karenia_mikimotoi | 1564 |      -0.05  |        |
| do_mg_l        | y_dinophysis            | 1564 |      -0.041 |        |
| do_mg_l        | y_dinophysis_nowcast    | 1564 |      -0.025 |        |
| nitrate_umol_l | count_dinophysis        | 1476 |      -0.104 |        |
| nitrate_umol_l | count_pseudo_nitzschia  | 1476 |      -0.093 |        |
| nitrate_umol_l | count_karenia_mikimotoi | 1476 |      -0.021 |        |
| nitrate_umol_l | y_dinophysis            | 1476 |      -0.061 |        |
| nitrate_umol_l | y_dinophysis_nowcast    | 1476 |      -0.102 |        |
| temp_c         | count_dinophysis        | 1672 |       0.137 |        |
| temp_c         | count_pseudo_nitzschia  | 1672 |       0.097 |        |
| temp_c         | count_karenia_mikimotoi | 1672 |       0.044 |        |
| temp_c         | y_dinophysis            | 1672 |       0.099 |        |
| temp_c         | y_dinophysis_nowcast    | 1672 |       0.126 |        |
| salinity       | count_dinophysis        | 1656 |      -0.019 |        |
| salinity       | count_pseudo_nitzschia  | 1656 |       0.035 |        |
| salinity       | count_karenia_mikimotoi | 1656 |       0.01  |        |
| salinity       | y_dinophysis            | 1656 |      -0.093 |        |
| salinity       | y_dinophysis_nowcast    | 1656 |      -0.144 |        |

**DO/Chl signal note:** do_mg_l vs count_dinophysis: r=-0.092 (n=1564); do_mg_l vs count_karenia_mikimotoi: r=-0.050 (n=1564); do_mg_l vs count_pseudo_nitzschia: r=-0.046 (n=1564).

## Lehanagh Pool — nearest Irish `habs_phyto` stations

Within ~30 km of buoy; flag stations with `year_max >= 2024` for join.

|   location_id | location_name       |   latitude |   longitude |   dist_km |   n_weeks |   year_min |   year_max | overlap_years   |
|--------------:|:--------------------|-----------:|------------:|----------:|----------:|-----------:|-----------:|:----------------|
|           633 | Lehannagh Pool      |    53.4012 |    -9.8266  |       0.4 |        25 |       2009 |       2020 | False           |
|           374 | Outer Bertragh Buoi |    53.3846 |    -9.85832 |       3   |         5 |       2003 |       2013 | False           |
|           373 | Saltpoint           |    53.3846 |    -9.85832 |       3   |        20 |       2002 |       2011 | False           |
|           372 | Letterard           |    53.3846 |    -9.85832 |       3   |       174 |       2005 |       2014 | False           |
|           160 | Illaungorm          |    53.3811 |    -9.85556 |       3.1 |         3 |       2004 |       2004 | False           |
|           634 | Letterard           |    53.3747 |    -9.8687  |       4.3 |        24 |       2009 |       2012 | False           |
|           628 | Crumpan Pier        |    53.3122 |    -9.82692 |       9.8 |       330 |       2008 |       2016 | False           |
|           400 | Ardmore             |    53.3003 |    -9.76548 |      11.7 |        69 |       2003 |       2015 | False           |
|           401 | Birbeg              |    53.2806 |    -9.77923 |      13.6 |         8 |       2007 |       2008 | False           |
|           396 | Oilean Iarthach     |    53.2882 |    -9.73658 |      13.6 |        12 |       2004 |       2008 | False           |
|           416 | Birmore             |    53.273  |    -9.785   |      14.3 |         1 |       2007 |       2007 | False           |
|           176 | Illauneragh         |    53.2783 |    -9.74806 |      14.4 |         1 |       2005 |       2005 | False           |
|           395 | Lettercallow        |    53.2916 |    -9.70244 |      14.4 |        19 |       2004 |       2008 | False           |
|           392 | The Gurrig          |    53.319  |    -9.647   |      14.6 |         7 |       2003 |       2008 | False           |
|           391 | Annaghbhan          |    53.3189 |    -9.64703 |      14.6 |         5 |       2002 |       2009 | False           |

### Active stations with year_max ≥ 2024 (demo join set)

_(none)_

**Join set (up to 8 nearest with overlap):** `[174, 177, 179, 163, 171, 172, 650, 175]` → 719 station-weeks from 2024+.

### Optional buoy ↔ HAB correlation (station-weeks)

Pearson *r* between weekly buoy means and HAB counts / Dinophysis labels (even tiny |r| is reported).

| x             | y                       |   n |   pearson_r | note   |
|:--------------|:------------------------|----:|------------:|:-------|
| do_mg_l       | count_dinophysis        | 703 |      -0.129 |        |
| do_mg_l       | count_pseudo_nitzschia  | 703 |      -0.005 |        |
| do_mg_l       | count_karenia_mikimotoi | 703 |       0.033 |        |
| do_mg_l       | y_dinophysis            | 703 |      -0.056 |        |
| do_mg_l       | y_dinophysis_nowcast    | 703 |      -0.002 |        |
| chl_ug_l      | count_dinophysis        | 603 |       0.049 |        |
| chl_ug_l      | count_pseudo_nitzschia  | 603 |       0.003 |        |
| chl_ug_l      | count_karenia_mikimotoi | 603 |      -0.03  |        |
| chl_ug_l      | y_dinophysis            | 603 |       0.025 |        |
| chl_ug_l      | y_dinophysis_nowcast    | 603 |       0.016 |        |
| phycoerythrin | count_dinophysis        | 603 |       0.029 |        |
| phycoerythrin | count_pseudo_nitzschia  | 603 |      -0.02  |        |
| phycoerythrin | count_karenia_mikimotoi | 603 |      -0.032 |        |
| phycoerythrin | y_dinophysis            | 603 |       0.017 |        |
| phycoerythrin | y_dinophysis_nowcast    | 603 |      -0.001 |        |
| temp_c        | count_dinophysis        | 703 |       0.22  |        |
| temp_c        | count_pseudo_nitzschia  | 703 |       0.157 |        |
| temp_c        | count_karenia_mikimotoi | 703 |      -0.016 |        |
| temp_c        | y_dinophysis            | 703 |       0.08  |        |
| temp_c        | y_dinophysis_nowcast    | 703 |       0.14  |        |
| turbidity_ntu | count_dinophysis        | 603 |       0.102 |        |
| turbidity_ntu | count_pseudo_nitzschia  | 603 |      -0     |        |
| turbidity_ntu | count_karenia_mikimotoi | 603 |      -0.017 |        |
| turbidity_ntu | y_dinophysis            | 603 |       0.132 |        |
| turbidity_ntu | y_dinophysis_nowcast    | 603 |       0.119 |        |

**DO/Chl signal note:** do_mg_l vs count_dinophysis: r=-0.129 (n=703); do_mg_l vs y_dinophysis: r=-0.056 (n=703); chl_ug_l vs count_dinophysis: r=0.049 (n=603).

## How to demo

```bash
# re-download + rebuild report
python scripts/ingest_sentinel_sites.py
# or reuse raw CSVs
python scripts/ingest_sentinel_sites.py --skip-download
```

1. Show `data/processed/local_sites_report.md` (this file) + nearest-station tables.
2. Plot daily DO / temp from `data/processed/compass_mace_head_daily.parquet`
   and Chl / turbidity from `sentinel_lehanagh_daily.parquet`.
3. Overlay Dinophysis station-weeks for Mannin (`177`), Rosmuc (`174`),
   Cliffden Outer (`650`), Gubbaros (`179`) — closest active sites with 2018+/2024+ overlap.
4. QC contrast: delayed-mode `sbe37_macehead` (flags) vs NRT `compass_mace_head`.
5. Live ERDDAP graphs:
   - https://erddap.marine.ie/erddap/tabledap/compass_mace_head.graph
   - https://erddap.marine.ie/erddap/tabledap/sentinel_lehanagh.graph

Ingest code: `src/pa_marine/sentinel.py`, `scripts/ingest_sentinel_sites.py`.

