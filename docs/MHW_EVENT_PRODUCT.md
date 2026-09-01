# Product: “Will this heatwave matter for HABs?”

**Path:** `docs/MHW_EVENT_PRODUCT.md`  
**Script:** `scripts/mhw_hab_brief.py`  
**Flagship example:** `data/processed/briefs/mhw_hab_brief_2023-06-30.md` (+ `.txt`)

---

## What it is

An **automated situational brief** for periods when a **shelf marine heatwave (MHW)** is underway (or just ended) on the Irish shelf. It answers, in policy / industry language:

> *Given this heatwave footprint, what do we already know about Dinophysis exceedance, harvest-closure pressure, local buoy warmth, and freshwater context?*

It is a **desk product** — markdown + plain-English text — assembled from processed open data already in this repo. It is **not** a live forecast model run and **not** an official harvest open/close notice.

The June 2023 Northwest European shelf MHW ([Berthou et al. 2024](https://doi.org/10.1038/s43247-024-01413-8)) is the **flagship worked example**, aligned with `data/processed/june2023_case_study.md`.

---

## Who it is for

| Audience | How they use it |
| --- | --- |
| **Aquaculture operators / processors** | Early situational awareness when CRW / press flags a shelf heatwave — what national and Connemara Dinophysis rates look like vs climatology, and whether closures are already elevated. |
| **Agency / local authority desk officers** | One-pager to brief colleagues during an event week; points to underlying panels and the DSP/closure research prototype. |
| **Hackathon / research demos** | Concrete “ops-shaped” output on top of the science stack (CRW + HAB + sentinel + rivers). |

**Not for:** regulatory harvest decisions, public health alerts, or insurance claims. Those stay with competent authorities and classified-area status.

---

## What the brief contains

For a date window (default **June 2023**; or `--latest` CRW days):

1. **CRW Irish-bbox MHW** — mean/peak ocean fraction in MHW, peak mean category, max Hobday category (51–56°N, 11–5°W).
2. **Dinophysis exceedance** — national station-week rate (≥ 100 cells/L) and Connemara focus subset, vs same-ISO-week climatology.
3. **Closure / DSP context** — area-week closure rate from `habs_status` (if panel present), DSP toxin exceedance rate (if toxin panel present), plus calibrated model skill notes from `dsp_closure_risk_metrics.json`.
4. **Mace Head buoy** — mean/min/max temperature and anomaly vs other-year same-month mean (if sentinel daily present).
5. **Corrib / Owenboliskey Q** — mean discharge vs multi-year same-month climatology (if `rivers_daily.csv` present).

Missing layers are skipped with an explicit note — the product **degrades gracefully**.

---

## How to run

From the repo root (venv with project deps; **no network** required if processed files exist):

```bash
# Flagship June 2023 brief
python scripts/mhw_hab_brief.py

# Most recent ~30 days of CRW Irish-bbox coverage
python scripts/mhw_hab_brief.py --latest
python scripts/mhw_hab_brief.py --latest --latest-days 14

# Custom window
python scripts/mhw_hab_brief.py --start 2023-06-01 --end 2023-06-30
```

**Outputs** (dated on the window end date):

```
data/processed/briefs/mhw_hab_brief_YYYY-MM-DD.md   # structured brief
data/processed/briefs/mhw_hab_brief_YYYY-MM-DD.txt   # plain-English email/SMS-ready text
```

### Expected inputs (all under `data/processed/`)

| Layer | File | Required? |
| --- | --- | --- |
| CRW daily summary | `crw_mhw_ireland_daily_summary.csv` (or `.parquet`) | **Yes** |
| HAB station-weeks | `station_week_panel.parquet` | Optional (Dinophysis section) |
| Area status | `status_area_week_panel.parquet` | Optional (closures) |
| Toxins | `toxin_station_week_panel.parquet` | Optional (DSP rates) |
| DSP model metrics | `dsp_closure_risk_metrics.json` | Optional (skill context) |
| Mace Head | `compass_mace_head_daily.parquet` | Optional |
| Rivers | `rivers_daily.csv` | Optional |

Rebuild upstream pieces via `scripts/ingest_scout_p0.py`, `scripts/ingest_sentinel_sites.py`, `scripts/ingest_biotoxin.py`, OPW river ingest, and `scripts/build_june2023_case_study.py` as needed.

---

## How to read the June 2023 flagship

Headline takeaways from `mhw_hab_brief_2023-06-30.*` (aligned with the case study):

- **Severe shelf-wide MHW:** mean CRW frac_mhw ≈ **0.96**; peak **1.0** on 19 Jun; max category **5**.
- **Dinophysis was not nationally elevated** vs same-week climatology (~10% vs ~14%); Connemara focus was quiet during peak June weeks aside from the late-May Rosmuc exceedance overlapping W22.
- **Closures were not surged** vs climatology in that window (~16% vs ~24%).
- **Mace Head ~+2 °C** vs other-year June means; **Corrib / Owenboliskey Q low** (~75% / ~15% of clim) — dry anticyclonic freshwater context.

**Product lesson:** a dramatic shelf heatwave can coincide with **below-average** national Dinophysis/closure rates in the same weeks. The brief’s job is to show that clearly so operators heighten monitoring **without** assuming every MHW equals an immediate bloom.

---

## Limits

- **Not operational warning.** No SLA, no guaranteed latency, no authority stamp.
- **Shelf ≠ bay.** Irish-bbox CRW averages can differ from embayment conditions.
- **Sampling gaps.** Missing HAB weeks ≠ confirmed all-clear.
- **Coastal SST mask.** Some inshore sites lack OISST/CRW SST (e.g. Rosmuc).
- **Closures are multi-toxin / admin.** SST→Dinophysis cells ≠ SST→harvest closure.
- **DSP positives rare** on recent test years — toxin rates and toxin-model skill are noisy.
- **River gauges are proxies** (tidal influence, sluice) — wetness context only.
- **No causal claim.** Lead/lag HAB timing around an MHW remains a hypothesis (see case study).

---

## Relationship to other repo products

| Artifact | Role |
| --- | --- |
| `june2023_case_study.md` | Full scientific narrative + figures for the flagship event |
| `train_dsp_closure_risk.py` / report | Research ranking skill for closure / DSP heads |
| `evaluate.py` (strong OISST) | National Dinophysis nowcast skill |
| `docs/HACKATHON_DEMO.md` | 48 h demo pack — links this brief as idea 3 productised |
| `docs/PAPER_OUTLINE.md` | Paper framing for the June 2023 follow-on |

---

## Suggested next steps (productisation)

1. Cron / GitHub Action: `--latest` after CRW summary refresh; attach `.txt` to an internal mail list.
2. Threshold trigger: only emit when CRW mean frac_mhw (7-day) ≥ 0.5 or max_cat ≥ 3.
3. Optional one-page PDF export for agency packs.
4. Bay-level variants (Connemara / southwest) once coastal SST / ROMS archives are denser.
