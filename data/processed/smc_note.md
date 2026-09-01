# Scotland SMC data note

**Source file:** `data/raw/smc_classifications.csv` (gitignored; ~3.8k rows, 2006–2026).

**What it is:** Food Standards Scotland / SMC **annual sanitary shellfish classification** (A/B/C by production area and species). Columns include `AreaName`, `Sin`, `LocalAuthorityName`, `OverallCategory`, classification window dates, `Decision`, `ConfidenceLevel`, `Type`, `Status`.

**What it is not:** This is **not** phytoplankton, HAB cell counts, or biotoxin results. It cannot train the HAB exceedance targets used in this repo (Dinophysis / Pseudo-nitzschia / etc.).

**Area lookup:** `data/processed/smc_areas.csv` — unique `(AreaName, Sin, LocalAuthorityName)` (~448 SINs / ~390 area names). Loader: `src/pa_marine/smc.py`; rebuild with `python scripts/ingest_smc.py`.

**Still needed for Scotland HAB labels:** a separate SMC **phytoplankton and/or toxin** monitoring export (analogous to Marine Institute `habs_phyto` / `habs_biotoxin`, or England & Wales FSA phytoplankton CSVs). Until that arrives, Scotland areas here are for geographic / sanitary context only.
