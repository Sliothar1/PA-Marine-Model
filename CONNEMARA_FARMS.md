# Connemara Farms — weekly HAB risk scores (product idea 2)

Grower-facing **Dinophysis exceedance risk** (and optional harvest-closure proxy) for
Connemara shellfish sites, built on the existing Irish **strong OISST** Dinophysis
pipeline. Research nowcast — **not** an official Marine Institute warning.

Generated / regenerated: run the one-liner under [How to regenerate](#how-to-regenerate).

**Grower / co-op one-pager:** [`CONNEMARA_GROWER_README.md`](CONNEMARA_GROWER_README.md) (how to read bands, what to do with MI bulletins, limitations).

## Station set

Config: [`configs/connemara_farms_stations.yaml`](configs/connemara_farms_stations.yaml)  
Export: [`data/processed/connemara_farms_stations.csv`](data/processed/connemara_farms_stations.csv)

| Grower label | NMP `location_id` | NMP name | Role | Status |
| --- | ---: | --- | --- | --- |
| Killary Inner | 171 | Killary Harbour Inner | nmp_core | active |
| Killary Middle | 172 | Killary Harbour Middle | nmp_core | active |
| Killary Outer | 175 | Killary Harbour Outer | nmp_core | active |
| Mannin | 177 | Mannin | nmp_core | active |
| Rosmuc | 174 | Rosmuc | nmp_core | **active_oisst_gap** (SST null at OISST pixel) |
| Clifden | 650 | Cliffden Outer | nmp_core | active (NMP spelling "Cliffden") |
| Ballynakill | 163 | Ballynakill | nmp_core | active |
| Lehanagh (NMP) | 633 | Lehannagh Pool | nmp_nearby | **sparse_historical** (2009–2020 only) |
| Gubbaros (nearby) | 179 | Gubbaros | nmp_nearby | active (Clifden/Mannin reference) |
| Mace Head buoy | — | `compass_mace_head` | sentinel_buoy | buoy_only (no HAB labels) |
| Lehanagh buoy | — | `sentinel_lehanagh` | sentinel_buoy | buoy_only (NRT from 2024-05) |

Lat/lon come from existing NMP metadata in `station_week_panel.parquet`. Buoy
coordinates match [`data/processed/local_sites_report.md`](data/processed/local_sites_report.md).

## Model choice: **national apply** (not local retrain)

**Choice:** Fit the national Irish Dinophysis **strong OISST** LightGBM on the full
Irish joined panel (train ISO years **2003–2018**), calibrate probabilities on val
(**2019–2021**, isotonic), then **score Connemara station-weeks**. Optional second
head: national **area-closed** model from `toxin_joined_features.parquet` (same
strong features), merged where toxin/status weeks exist.

**Why not local retrain:** Core Connemara NMP sites have too few Dinophysis
positives for a stable site-level model (often single-digit to low-dozens of
`y_dinophysis=1` weeks per site across the whole record). A Connemara-only fit
would overfit seasonality and be unusable for ops. The national strong feature set
already has documented ranking skill.

**Features (9):** `sst`, `sst_lag0d`, `sst_lag21d`, `sst_roll7d`, `sst_roll30d`,
`woy_sin`, `woy_cos`, `latitude`, `longitude` — same as `STRONG_OISST` /
`scripts/evaluate.py --feature-mode strong`.

**Target:** `y_dinophysis_nowcast` — Dinophysis ≥ 100 cells L⁻¹ in the current or
next ISO week (0–2 week label window). Thresholds / horizons match the main README.

**Reuse:** Irish Dinophysis strong eval (`metrics_dino_strong.json`), DSP closure
prototype (`scripts/train_dsp_closure_risk.py`), sentinel buoy ingest / local sites
report, June 2023 case study, existing NMP + OISST joined panel. No new credentials.

## Key metrics

From a local regenerate on existing `joined_features.parquet` (see
`data/processed/connemara_farms_metrics.json`):

| Scope | n (test) | Prevalence | Calibrated PR-AUC | Clim PR-AUC | PR skill |
| --- | ---: | ---: | ---: | ---: | ---: |
| **National** (Ireland, 2022+) | 14270 | 0.052 | **0.293** | 0.183 | **0.135** |
| **Connemara subset** (9 NMP IDs, 2022+) | 1558 | 0.029 | 0.068 | 0.075 | ≈ 0 (no extra ranking skill locally) |

Honest read: use the **national** skill number as the model’s documented ability;
on Connemara alone, positives are rare and PR skill vs week-of-year climatology is
not better than clim on this test window. Scores are still useful as a
**transparent seasonal + SST contextualisation** for growers when paired with
official MI bulletins and recent cell counts.

**Coverage:** 9 NMP stations scored · **4796** station-weeks · week span ~2002–2026-08
(per site; Lehannagh NMP ends 2020) · SST non-null ≈ 91% overall (0% at Rosmuc).

DSP / closure proxy: toxin panel currently ends ~**2026-04**, so late-summer grower
rows often show "—" for closure risk even when Dinophysis scores are present.

## Outputs

| Path | Contents |
| --- | --- |
| `data/processed/connemara_farms_scores.csv` | All scored station-weeks (risk, clim, cells, optional closure proxy) |
| `data/processed/connemara_farms_latest.csv` | Grower table: last 4 **sampled** weeks per active site |
| `data/processed/connemara_farms_scores.html` | Grower-facing HTML dashboard (latest week + bands) |
| `CONNEMARA_GROWER_README.md` | One-page co-op guide to reading scores |
| `data/processed/connemara_farms_stations.csv` | Flattened station config |
| `data/processed/connemara_farms_metrics.json` | Model choice, national + subset metrics, coverage |

Risk bands (calibrated probability): **Higher** ≥ 0.15 · **Moderate** ≥ 0.07 · else **Lower** (plain English: Higher / Moderate / Lower **watch**). Bands are heuristic communication aids, not regulatory cut-offs — see the grower README.

## Gaps / blockers

1. **Rosmuc (174):** HAB labels exist; **OISST SST is entirely null** (landmask /
   inshore pixel). Scores rely on week-of-year + lat/lon only.
2. **Lehannagh Pool NMP (633):** Only 25 weeks, last sample **2020** — kept for
   continuity; excluded from the grower "latest" table.
3. **Mace Head / Lehanagh buoys:** Hydrography only; **no Dinophysis labels** —
   context via `local_sites_report.md`, not scored.
4. **DSP / closure join:** National closed-head scores only where
   `toxin_joined_features` overlaps; toxin ingest lags phyto (ends earlier in 2026).
5. **Irregular sampling:** Station-weeks appear only when MI sampled; no sample ≠
   true negative. Grower table uses last sampled weeks per site.
6. **Do not touch** heatwave event-brief / product idea 3 (`data/processed/briefs/`).

## How to regenerate

Requires existing processed joins (no ERDDAP login beyond what is already on disk):

```bash
python scripts/score_connemara_farms.py
```

Optional:

```bash
python scripts/score_connemara_farms.py --latest-weeks 6 --skip-dsp
```

Upstream rebuild (only if you need fresher national features / toxins):

```bash
python scripts/join_features.py          # after OISST/MHW refresh
python scripts/ingest_biotoxin.py --skip-download
python scripts/score_connemara_farms.py
```

## Related

- `docs/HACKATHON_DEMO.md` — Challenge 4 demo path
- `data/processed/local_sites_report.md` — Mace Head / Lehanagh sentinels
- `data/processed/june2023_case_study.md` — June 2023 Connemara MHW × Dinophysis
- `data/processed/dsp_closure_risk_report.md` — national DSP / closed prototype
- `scripts/evaluate.py --feature-mode strong` — national Dinophysis metrics
