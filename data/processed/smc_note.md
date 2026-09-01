# Scotland SMC data note

## Sanitary classifications (existing)

**Source file:** `data/raw/smc_classifications.csv` (gitignored; ~3.8k rows, 2006–2026).

**What it is:** Food Standards Scotland / SMC **annual sanitary shellfish classification** (A/B/C by production area and species). Columns include `AreaName`, `Sin`, `LocalAuthorityName`, `OverallCategory`, classification window dates, `Decision`, `ConfidenceLevel`, `Type`, `Status`.

**Area lookup:** `data/processed/smc_areas.csv` — unique `(AreaName, Sin, LocalAuthorityName)` (~448 SINs). Loader: `src/pa_marine/smc.py`; rebuild with `python scripts/ingest_smc.py`.

## HAB phytoplankton + biotoxins (2026-09-01 ingest)

**Raw (gitignored):**

- `data/raw/smc_phytoplankton.csv` — 21,621 sample rows; cell counts for Dinophysis, Pseudo-nitzschia, Alexandrium, etc.; keyed by `Sin` / `AreaName` / `SiteName`; `CollectedTimestamp` day-first.
- `data/raw/smc_biotoxins.csv` — 43,218 sample rows; OA/DTX/PTX, ASP, PSP, AZA, YTX result columns; same Sin keys.

**Processed panels (parquet, gitignored):**

- `data/processed/smc_station_week_panel.parquet` — SIN × ISO-week phyto panel
- `data/processed/smc_toxin_station_week_panel.parquet` — SIN × ISO-week toxin panel

**Summaries (committed):** `smc_hab_ingest_summary.json`, `smc_hab_report.md`.

**Labels / thresholds:** Dinophysis ≥100, Pseudo-nitzschia ≥50,000, Alexandrium ≥40 cells L⁻¹; DSP ≥160 µg OA eq/kg, ASP ≥20 mg/kg, PSP ≥800 µg STX eq/kg.

**Coordinates:** see **Site coordinates** below. Panels are updated in-place with `latitude`/`longitude`/`has_coords` when geocode is run.

Rebuild: `python scripts/ingest_smc_hab.py`.

## Area closures (2026-09-01 ingest)

**Raw (gitignored):** `data/raw/smc_area_closures.csv` — toxin/E.coli harvest closures (OA/DTX/PTX etc.), not Copernicus.

**Processed:** `data/processed/smc_closures.csv` + `smc_closures_note.md`. Linked to `smc_areas` on AreaName; Pod retained; Sin preferred from Reason when present in areas.

Rebuild: `python scripts/ingest_smc_closures.py`.

## Site coordinates (2026-09-01 geocode)

**Processed:** `data/processed/smc_site_coords.csv` — one row per phyto-panel Sin
(`Sin, AreaName, SiteName, latitude, longitude, source, confidence[, detail]`).

**SEPA centroids:** `data/processed/sepa_swpa_centroids.csv` (from public SEPA REST;
easting/northing used when published lon is corrupt).

**Sources (priority):**
1. OSGB grid refs in `smc_closures.csv` Description → WGS84 mean (`osgb_closure`, high)
2. SEPA Shellfish Water Protected Areas name match (`sepa_swpa`, high/medium)
3. Nominatim `{AreaName}, Scotland, UK` with LA/region fallbacks (`nominatim`, often low)

**FSS classified-areas WFS** (`nmp:fss_shellfish_classified_areas` on Marine Scotland
GeoServer) is OGL-licensed but returns **HTTP 401 without login** — not used.

**Coverage (phyto panel):** 131/131 SINs (100% rows) have coords; confidence mix is
roughly high ~37%, medium ~37%, low ~27%. Many loch/voe Nominatim hits are ambiguous.

Rebuild: `python scripts/geocode_smc_sites.py`

