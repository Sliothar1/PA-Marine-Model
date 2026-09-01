# Corrib / Galway Bay river discharge ingest

**Date:** 2026-09-01 (Europe/Dublin).
**Status:** SUCCESS — OPW Hydro-Data full-archive daily means obtained without interactive download.

## Attempt order

1. **data.gov.ie / EPA HydroNet** — CKAN dataset [Water Levels and Flow](https://data.gov.ie/dataset/water-levels-and-flow) only exposes HTML → HydroNet SPA + `layers/10/index.json` which redirects to the interactive WISKI Web Public app (no bulk time-series CSV). **No open bulk series from EPA in this pass.**
2. **OPW waterlevel.ie / Hydro-Data** — **Worked.** Station register: `https://waterlevel.ie/hydro-data/data/internet/stations/stations.json`. Archive: `https://waterlevel.ie/hydro-data/data/internet/stations/0/{station_no}/{Q|S}/year.json` (`WEB.Day.Mean`). Also documented on data.gov.ie [Hydrodata discharge](https://data.gov.ie/dataset/hydrodata-discharge-complete-high-res-data) (HVD). Realtime `waterlevel.ie/data/month/` is only a ~5-week window (not needed once archive worked).
3. Browser — **not required.**

## Stations ingested

| No. | Name | Role | Q days | Q range | S days | S range |
| --- | --- | --- | ---: | --- | ---: | --- |
| 30061 | Wolfe Tone Br | primary_corrib_outflow | 6120 | 2009-03-31→2025-12-31 | 8237 | 2004-02-13→2026-09-01 |
| 31075 | Shannagurraun | connemara_coastal_local | 19300 | 1973-10-30→2026-09-01 | 19300 | 1973-10-30→2026-09-01 |
| 30031 | Cong Weir | mask_to_corrib_inflow | 9436 | 2000-11-01→2026-09-01 | 9436 | 2000-11-01→2026-09-01 |
| 30004 | Corrofin (Clare) | clare_tributary | 31741 | 1939-10-08→2026-09-01 | 22616 | 1964-10-01→2026-09-01 |
| 30005 | Foxhill | robe_tributary | 25891 | 1955-10-14→2026-09-01 | 25891 | 1955-10-14→2026-09-01 |
| 30101 | Oughterard | owenriff_to_corrib | 9336 | 2001-02-09→2026-09-01 | 9336 | 2001-02-09→2026-09-01 |
| 29004 | Clarinbridge | galway_bay_se | 19412 | 1973-07-10→2026-09-01 | 19412 | 1973-07-10→2026-09-01 |
| 29015 | Oranmore Br | galway_bay_east_tidal | 15905 | 1983-02-15→2026-09-01 | 8131 | 2004-05-29→2026-09-01 |
| 30098 | Dangan | corrib_above_barrage_level | 0 | → | 8366 | 2003-10-07→2026-09-01 |
| 30099 | Galway Barrage | barrage_level | 0 | → | 7916 | 2004-12-30→2026-09-01 |
| 30097 | Galway Barrage D/S | barrage_ds_level | 0 | → | 1818 | 2021-09-10→2026-09-01 |

## Primary discharge summaries (2015–2024 daily mean Q)

| Station | n days | mean m³/s | median m³/s |
| --- | ---: | ---: | ---: |
| 30061 Wolfe Tone / Corrib | 3412 | 113.15 | 98.74 |
| 31075 Shannagurraun / Owenboliskey | 2976 | 3.96 | 2.25 |
| 30031 Cong Weir | 3169 | 36.19 | 31.64 |

## Artifacts

| Path | Contents |
| --- | --- |
| `data/raw/rivers/opw_hydrodata_*_year.json` | Full Hydro-Data archives (Q/S) |
| `data/raw/rivers/daily_{station}_{Q|S}.csv` | Extracted `WEB.Day.Mean` |
| `data/raw/rivers/stations_selected.csv` | Station metadata + coverage |
| `data/processed/rivers_daily.csv` | Combined daily series (~252k rows) |
| `data/processed/rivers_week.csv` | ISO-week means |
| `data/processed/rivers_hab_join_note.md` | Connemara HAB join recipe |
| `data/processed/rivers_hab_station_map.csv` | Distances HAB↔proxy gauges |

## License / attribution

OPW hydrometric data via waterlevel.ie Hydro-Data; open data terms as on data.gov.ie (CC-BY 4.0 for related listings). Courtesy notice for automated access: `waterlevel@opw.ie` (per waterlevel.ie API page).

