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

**Coordinates:** the HAB export has **no lat/lon**. Panels leave `latitude`/`longitude` null and set `has_coords=False`. **Geocode Sin → WGS84 before any OISST/OSTIA join.** Area lookup is joined on `Sin` only (`in_smc_areas` flag).

Rebuild: `python scripts/ingest_smc_hab.py`.
