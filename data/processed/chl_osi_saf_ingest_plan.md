# Chl + OSI SAF ingest / join plan (gatekeeper)

**Date:** 2026-09-08 (Europe/Dublin)  
**Owner:** Prediction Gatekeeper + Climate Drivers  
**Baseline to beat:** `STRONG_OISST` (9 feats) — LightGBM test calibrated PR-AUC ≈ **0.293** (`data/processed/metrics_dino_strong.json`). Alert only on real lift / Cork unlock / blocker.  
**Rules:** open-data spine only; no Sextant weekend dumps into public git; do **not** rewrite `docs/CPR_MBA.md`.

## Why this test (Felix / onion)

Spring–summer MHW × phytoplankton story needs a **Chl / bloom proxy** the strong SST model lacks. IBI already folded `kd`/`zeu` (optics) with **no national lift** — satellite **CHL** is the missing OC layer. OSI SAF (or CMEMS ODYSSEA L4 that ingests OSI SAF) is an independent SST spine for honesty vs OISST/OSTIA.

## Products (candidates — verify IDs on pull)

| Lane | Preferred product | Why | Fallbacks |
| --- | --- | --- | --- |
| **Ocean colour Chl** | Copernicus GlobColour Atlantic L4 **MY** Chl (`OCEANCOLOUR_ATL_BGC_L4_MY_*` / successor of NRT `009_116`) | Gap-filled daily CHL; MY covers train 2003–2018 | NRT L4 for recent years only; IBI BGC modelled Chl only as secondary (model≠obs) |
| **OSI SAF SST** | OSI SAF NAR L3C **OSI-202-c** (Metop/VIIRS, ~2 km, anonymous FTP/HTTPS) | Direct EUMETSAT open SST | CMEMS **ODYSSEA** L4 `SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025` (uses OSI SAF inputs; already-credentialed CMEMS path) |

Domain: Irish HAB bbox **51–56°N, 11–5°W**. Station-pixel / nearest-grid extract preferred (same pattern as IBI/OISST).

## Paths (box-local)

| Stage | Path |
| --- | --- |
| Raw Chl | `data/raw/ocean_colour/` |
| Raw OSI / ODYSSEA | `data/raw/osi_saf/` (and/or `data/raw/odyssea_daily.parquet`) |
| Week join | `data/processed/joined_features_chl.parquet`, `data/processed/joined_features_osi_sst.parquet` |
| Ablation metrics | `data/processed/chl_ablation_metrics.json` + `.md`; `data/processed/osi_saf_ablation_metrics.json` + `.md` |
| Pilot status | `data/processed/chl_osi_saf_pilot_status.json` |

## Feature recipes (honest ablations)

Attach to **Sunday ISO week end** (no future leakage), same splits: train 2003–2018 / val 2019–2021 / test 2022+.

**Chl set (add-on to strong):**
- `chl`, `chl_lag7d`, `chl_lag14d`, `chl_roll7d`, `chl_roll14d` (log1p variants if skewed)
- Optional: `chl_anom` vs station DOY clim fitted on **train only**

**OSI / ODYSSEA SST set:**
- Rebuild MHW + **same 9 strong names** from OSI/ODYSSEA SST (provider swap), **or** add `sst_osi` residual vs OISST — prefer full provider swap first (cleaner)

**Eval slices (high-EV, report separately):**
1. Full national Dinophysis nowcast (canonical)
2. **Apr–Sep** only
3. **`in_mhw==1`** weeks only
4. Connemara / west subset (Mace Head neighbourhood)

Primary metric: LightGBM **test calibrated PR-AUC** vs strong; also PR skill vs clim. Flat/negative → stay quiet.

## Work split

| Who | Owns |
| --- | --- |
| **Climate Drivers** | OSI SAF / ODYSSEA SST download + station-day series; document sources JSON; help CMEMS auth issues |
| **Prediction Gatekeeper** | Chl product choice + pilot; week join; ablation harness mirroring `climate_drivers_ablation.py`; EV gate + PA alert |
| **PA** | Push / Cork framing only when metrics beat strong or unlock a slide |

## Kickoff sequence

1. Verify MY Chl + ODYSSEA/OSI dataset IDs (`copernicusmarine describe` / OSI SAF catalogue).
2. Pilot: ≤5 stations, May–Aug 2023 Chl (+ optional Jun 2023 OSI/ODYSSEA).
3. Full Irish station-pixel Chl MY extract → week join → ablation.
4. OSI/ODYSSEA SST provider swap ablation (can run in parallel after pilot).
5. Report paths + first metrics to PA **only if** ΔPR-AUC meaningfully >0 on test (or hard blocker).

## Non-goals

- No rewrite of locked CPR docs.
- No Sextant / weekend-only layers in public git.
- No claiming skill without metrics files on disk.
