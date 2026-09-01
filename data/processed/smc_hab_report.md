# Scotland SMC HAB ingest

Generated: 2026-09-01 (Europe/Dublin).

## Phytoplankton station-week panel

- Raw rows: **21621** → `data/raw/smc_phytoplankton.csv`
- Station-weeks: **21417**
- Unique SINs (sites): **131**
- Unique AreaName: **109**
- Week span: **2009-02-23 → 2026-08-31**
- Dinophysis ≥100 prevalence: **0.1856**
- Pseudo-nitzschia ≥50,000 prevalence: **0.0881**
- Alexandrium ≥40 prevalence: **0.2136**
- Fraction of station-weeks with Sin in `smc_areas.csv`: **0.871**

## Coordinates / SST

**No lat/lon in the SMC HAB export.** The first panel leaves `latitude`/`longitude` null.
Geocode `Sin` → WGS84 coords (e.g. from FSS production-area GIS) before joining OISST/OSTIA.

## Biotoxins station-week panel

- Raw rows: **43218** → `data/raw/smc_biotoxins.csv`
- Station-weeks: **42757**
- Unique SINs: **289**
- Week span: **2009-03-23 → 2026-08-24**
- DSP (OA+DTX+PTX ≥160) prevalence: **0.0373**
- ASP (≥20) prevalence: **0.0001**
- PSP (≥800) prevalence: **0.0044**

Raw CSVs stay gitignored under `data/raw/`. Parquet panels are gitignored; this report + JSON summary are committed.

## Rebuild

```bash
python scripts/ingest_smc_hab.py
```

