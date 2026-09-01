# Scotland SMC area closures

Generated: 2026-09-01 (Europe/Dublin).

## What this is

Food Standards Scotland / SMC **production-area harvest closures** driven by
official-control biotoxin (mostly OA/DTX/PTX) or E. coli results — **not**
Copernicus SST/ocean products and **not** annual sanitary A/B/C classification.

**Raw (gitignored):** `data/raw/smc_area_closures.csv` — 18 closure rows.

**Processed (committed):** `data/processed/smc_closures.csv` — 18 rows,
one per closure `Id`, linked to `smc_areas` on `AreaName` where possible.

## Linkage

- AreaName found in `smc_areas.csv`: **18/18**
- Sin parsed from Reason present in `smc_areas`: **14/18**
  (Reason site codes can differ from sanitary SINs — species suffix or site id.)
- `Sin` column prefers Reason Sin when it exists in areas; else first AreaName Sin.
- `Pod` retained from the closure export (monitoring pod).

## Coverage

- Closure starts: **2026-05-28 → 2026-08-24**
- Still open (null AreaClosureEnd): **18**
- Pods: [5, 7, 16, 23, 28, 31, 39, 47, 48, 49, 85, 126, 137]
- toxin_tags counts: {'OA/DTX/PTX': 16, 'unspecified': 1, 'Ecoli': 1}

## Rebuild

```bash
python scripts/ingest_smc_closures.py
```
