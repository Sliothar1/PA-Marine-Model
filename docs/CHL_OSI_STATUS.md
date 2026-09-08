# Status: OC Chl + OSI SAF SST fold-in

**Updated:** 2026-09-08 (Europe/Dublin, ~12:00 IST)  
**Repo:** `/workspace/pa-marine-model` (github.com/Sliothar1/PA-Marine-Model)

## Product choices

| Layer | Choice | IDs / path |
| --- | --- | --- |
| **OC Chl** | Atlantic GlobColour L4 **gap-free** daily CHL | Product `OCEANCOLOUR_ATL_BGC_L4_MY_009_118` · dataset `cmems_obs-oc_atl_bgc-plankton_my_l4-gapfree-multi-1km_P1D` · var `CHL` |
| **OSI SAF SST** | **OSI-202-c** NAR L3C Metop-B (independent of OISST/OSTIA) | GHRSST `AVHRR_SST_METOP_B_NAR-OSISAF-L3C-v1.0` · DOI 10.15770/EUM_SAF_OSI_NRT_2012 · CC BY 4.0 |
| Fallback SST | OSI-201-b global Metop L3C 0.05° | `AVHRR_SST_METOP_B_GLB-OSISAF-L3C-v1.0` |

Catalogue describe for Chl succeeded (bbox covers Irish shelf). Prior OSTIA/IBI parquets already on disk from earlier CMEMS pulls.

## Scripts / modules added

| Path | Role |
| --- | --- |
| `src/pa_marine/oc_chl.py` | Station-pixel CMEMS Chl download |
| `src/pa_marine/osi_saf_sst.py` | CMR manifest + week-mean / NC extract helpers |
| `scripts/download_oc_chl.py` | CLI → `data/raw/oc_chl_daily.parquet` |
| `scripts/download_osi_saf_sst.py` | CLI → CMR manifest under `data/raw/osi_saf_sst/` |
| `scripts/join_oc_osi_week.py` | Week join onto `joined_features` |
| `scripts/oc_osi_ablation.py` | Ablation vs `STRONG_OISST` (+ optional `--apr-sep`) |
| `configs/default.yaml` | `ocean_colour:` + `osi_saf_sst:` + paths |
| `src/pa_marine/features.py` | `OC_CHL_CORE`, `OSI_SAF_WEEK`, modes `strong_chl*` |
| `docs/CLIMATE_DRIVERS.md` §7 | Locked product / join / ablation notes |

**Not touched:** `docs/CPR_MBA.md`.

## What’s downloading / on disk

| Item | State |
| --- | --- |
| Chl station-pixel parquet | **Not started** — blocked on CMEMS auth TLS (see below) |
| OSI SAF NAR June 2023 CMR manifest | **Done** — 60 granules → `data/raw/osi_saf_sst/nar_metop_b_manifest.csv` (gitignored raw) |
| OSI SAF netCDF granules | **Not downloaded** — need Earthdata `~/.netrc` or Ifremer FTP session |
| Ablation metrics | **None** — no invented numbers; run after join |

## Blockers

1. **`auth.marine.copernicus.eu` TLS failure** from this box (`curl` EOF during handshake). Credentials file `~/.copernicusmarine/.copernicusmarine-credentials` loads (INI-in-base64; username present). Toolbox prompts interactively when auth cannot validate → **no new CMEMS subset/open_dataset** until auth recovers or egress allows the Keycloak token endpoint.
2. **No Earthdata / OSI SAF FTP session** on box for protected PO.DAAC NAR granules; Ifremer FTP listing timed out / hung in probe.
3. Describe/catalogue + CloudFerro S3 HTTPS respond; problem is specifically the **auth** host.

## Week-join + next ablation commands

```bash
cd /workspace/pa-marine-model
# when auth.marine.copernicus.eu works:
.venv/bin/python scripts/download_oc_chl.py
# OSI SAF discover (works now):
.venv/bin/python scripts/download_osi_saf_sst.py --t0 2023-06-01 --t1 2023-06-30
# after granules → daily clear-sky extract parquet:
.venv/bin/python scripts/join_oc_osi_week.py \
  --osi-daily data/raw/osi_saf_sst/osi_sst_daily.parquet
.venv/bin/python scripts/oc_osi_ablation.py
.venv/bin/python scripts/oc_osi_ablation.py --apr-sep
```

Baseline reminder (prior, not re-run here): strong 9-feat test PR-AUC ~0.29 vs clim ~0.18 (`data/processed/metrics_dino_strong.json`).

## Local anchors

Mace Head / Lehanagh Pool remain in `configs/default.yaml` sentinel block; Chl pixels will snap to nearest ocean cell for all 207 HAB `location_id`s in `station_week_panel` (lat 51.47–55.28, lon −10.57…−6.03).

## ODYSSEA station-day / week (Climate Drivers — ARCO)

**Status 2026-09-08:** Full Irish HAB station extract via CloudFerro ARCO (no CMEMS auth).

| Table | Path | Coverage |
| --- | --- | --- |
| Station-day | `data/processed/odyssea_station_day.parquet` (gitignored `*.parquet`) | **207** locations · **2022-01-01 → 2024-12-31** · 226 872 rows · 100% finite `sst_c` |
| Station-week | `data/processed/odyssea_station_week.parquet` | **207** locs · ISO weeks spanning 2021–2025 · 32 706 rows · cols `odyssea_sst_week`, `iso_year`, `iso_week` |
| Pilot (5 Connemara) | `data/processed/osi_saf_station_day.parquet` / Gatekeeper `data/raw/osi_saf/odyssea_pilot_2023_jun.parquet` | May–Aug / Jun 2023 |

**Access:** ARCO zarr `…/SST_ATL_SST_L4_NRT_OBSERVATIONS_010_025/…/timeChunked.zarr` (`zarr_format=2`). Scripts: `scripts/extract_odyssea_station_day_arco.py`, `scripts/download_odyssea_arco_station_day.py`, `scripts/ingest_odyssea_sst.py`. Sources: `data/raw/osi_saf/odyssea_station_day_sources.json`.

**Next:** Gatekeeper week-join onto HAB panel + provider-swap ablation vs `STRONG_OISST`. OSI-202-c NAR still blocked (Earthdata/FTP).

