# Corrib / Galway Bay rivers → Connemara HAB join note

**Generated:** 2026-09-01 (Europe/Dublin).  
**Source:** OPW Hydro-Data open JSON archives (`waterlevel.ie/hydro-data`), CC-BY via data.gov.ie.  
**Raw:** `data/raw/rivers/` (gitignored). **Daily / ISO-week:** `data/processed/rivers_daily.csv`, `rivers_week.csv`.

## Why these gauges

Connemara HAB stations sit on the **western Galway Bay / coastal embayments** (Mace Head, Lehanagh, Mannin, etc.). Freshwater signals relevant to salinity / bloom timing are:

| Priority | Station | No. | Parameter | Role for HAB |
| --- | --- | --- | --- | --- |
| 1 | Shannagurraun | **31075** | daily mean discharge Q (m³/s) | **Local Connemara coastal** — Owenboliskey; nearest OPW flow gauge to Spiddal / mid-bay HAB cluster |
| 2 | Wolfe Tone Br | **30061** | daily mean discharge Q (m³/s) | **Corrib → Galway Bay outflow** (fluvial component; tidal site — use OPW quality codes) |
| 3 | Cong Weir | **30031** | daily mean Q | Upper Corrib / Mask inflow — catchment wetness lag proxy |

Level-only sites (Dangan 30098, Galway Barrage 30099/30097) are kept as raw/level context but are **not** primary HAB predictors.

## Join keys (recommended)

1. Aggregate OPW `WEB.Day.Mean` to **ISO week** → already in `rivers_week.csv` (`iso_year`, `iso_week`, `station_no`, `parameter=Q`, `mean_value`).
2. Left-join onto Irish HAB panel on `(iso_year, iso_week)` **without** requiring spatial nearest-neighbour per station.
3. Attach **both** `Q_31075` and `Q_30061` (and optionally `Q_30031`) as **regional columns** to every Connemara focus station.

Rationale: Corrib and Owenboliskey are **point-source bay forcings**, not a continuous field. Nearest-river assignment would mis-assign western embayment stations to distant inland gauges.

## Demo HAB station set (from local sentinel join)

Same active set as Mace Head buoy join (`local_sites_report.md`):

`[633, 177, 169, 179, 174, 650, 163, 825]` (Lehannagh Pool, Mannin, Ardbear, …).

Full distance map for all nearest-HAB candidates: `rivers_hab_station_map.csv` (141 rows).

### Distances (km) — active year_max≥2018 stations → proxies

| location_id | name | →31075 | →30061 | →30031 |
| --- | --- | ---: | ---: | ---: |
| 169 | Ardbear | 53.0 | 68.7 | 49.9 |
| 163 | Ballynakill | 56.4 | 70.8 | 46.9 |
| 825 | Cleggan | 62.0 | 77.1 | 54.3 |
| 650 | Cliffden Outer | 59.8 | 75.6 | 56.1 |
| 179 | Gubbaros | 56.9 | 72.4 | 51.8 |
| 702 | Killary Approaches | 55.0 | 67.9 | 40.4 |
| 171 | Killary Harbour Inner | 46.8 | 59.1 | 31.6 |
| 172 | Killary Harbour Middle | 49.1 | 61.9 | 34.7 |
| 175 | Killary Harbour Outer | 51.4 | 64.2 | 36.9 |
| 601 | Killary Outer Mouth | 55.5 | 68.4 | 40.9 |
| 633 | Lehannagh Pool | 37.2 | 53.2 | 38.7 |
| 177 | Mannin | 54.6 | 70.5 | 52.4 |
| 174 | Rosmuc | 20.3 | 36.7 | 30.8 |

## Caveats

- OPW discharge is **rating-derived**, not continuous ADP at most sites; respect `quality_code`.
- **30061** is tidally influenced; fluvial Q uses tidal-peak removal / Dangan gaugings — treat as bay-scale freshwater pulse, not exact estuary flux.
- **31075** is below a sluice barrage — unsuitable for flood-peak hydrology; still useful as local wetness / release proxy for HAB salinity stories.
- Do **not** claim MHW→bloom causation from discharge alone; use as ablation feature vs strong OISST.

## Next model step

```bash
# Feature columns from rivers_week.csv pivoted:
# q_owenboliskey_week ← station 31075 Q
# q_corrib_wolfe_week ← station 30061 Q
# Join to station_week_panel / joined_features on iso_year+iso_week for Connemara subset; ablate AUC.
```
