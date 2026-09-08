# MBA Continuous Plankton Recorder (CPR) — IrishHeatwaves extract

**Climate Drivers role:** AOI × ISO-week aggregates + honest docs for shelf / heatwave narrative.  
**PA / executor role:** heavy ingest (`scripts/ingest_cpr_mba.py`), HAB week join + ablation (`scripts/join_cpr_hab_week.py`).  
**Climate rebuild helper:** `scripts/build_cpr_aoi_week.py` (reuses PA AOI boxes; does not duplicate sample ingest).  
**Python:** `/workspace/pa-marine-model/.venv/bin/python`

---

## 1. What it is

MBA CPR data extraction **“IrishHeatwaves”** prepared by **Pierre Hélaouët** (07/09/2026).

| | |
| --- | --- |
| **DOI** | [10.17031/6a9e6f4a00142](https://doi.org/10.17031/6a9e6f4a00142) |
| **Web** | https://doi.mba.ac.uk/data/3793 |
| **On disk** | `data/external/cpr_mba/` (large raw sample CSV gitignored) |
| **Main CSV** | `raw/CPR_IrishHeatwaves_Data_04092026.csv` — **41 884** samples, **1982–2022** |
| **Bbox** | 49–61°N, −16–0°E |
| **Sample volume** | One CPR sample ≈ **3 m³** filtered water |

Each row already carries **group mean abundances** (not raw taxon counts):

- `Mean_LargeCopepods` / `Mean_SmallCopepods`
- `Mean_Diatoms` / `Mean_Dinoflagellates`
- `PCI` — Phytoplankton Colour Index (silk greenness: 0 / 1 / 2 / 6.5)

Taxon lists: `raw/CPR_IrishHeatwaves_List_*.csv` (tracked). README: `README_from_docx.txt`.

---

## 2. Aggregates only — cannot validate Dinophysis

**This product cannot validate *Dinophysis* spp. abundance.**

- CSV / week product expose **group** means only (`Mean_Dinoflagellates` → `cpr_mean_dinoflagellates`).
- Accompanying dinoflagellate taxon list has **0 Dinophysis** entries (Ceratium-heavy; also Gymnodinium, Prorocentrum spp., etc.).
- Do **not** treat CPR dino means as Dinophysis labels, grower scores, or exceedance validation.
- Species-level expansion (if any) is **out of scope** for Climate Drivers — leave to PA.

Honest use: community / PCI context for Irish Sea, Celtic Sea, Scotland, and heatwave–shelf narrative.

---

## 3. Spatial honesty (PA AOIs)

Canonical AOI boxes live in `scripts/ingest_cpr_mba.py` (shared by `build_cpr_aoi_week.py`):

| AOI id | Bbox (lat_min–max × lon_min–max) | Typical role |
| --- | --- | --- |
| `total_box` | 49.5–60.76 × −15–−0.83 | Narrative outer box |
| `celtic` | 49.5–52 × −10.5–−5.5 | Celtic Sea — **good** coverage |
| `irish_sea` | 52.5–54.5 × −6.2–−3.2 | Irish Sea — **good** coverage |
| `scotland` | 54.75–60.76 × −7.5–−0.83 | Scotland west / approaches — **well covered** |
| `western_shelf` | 52.5–55 × −11.5–−9.0 | Western Irish shelf — **sparse (~35 tows)** |
| `shelf_break` | 51–55 × −15–−11.5 | Offshore west |
| `malin` | 54.5–55.8 × −8–−4.5 | Malin approaches |
| `connemara` | 53.2–53.7 × −10.2–−9.4 | Nested Connemara — **0 tows** |

Climate-facing aliases (summary JSON only; same boxes where mapped):

| Climate name | Maps to PA AOI |
| --- | --- |
| `full_extract` | MBA extract 49–61°N × −16–0°E (all CSV samples) |
| `celtic_sea` | `celtic` |
| `irish_sea` | `irish_sea` |
| `western_irish_shelf` | `western_shelf` |
| `connemara_nested` | `connemara` |
| `scotland_west` | `scotland` |

**Takeaways**

- **Connemara nested = empty** — no local CPR week features for Connemara farms.
- **Western shelf ~35 samples** — not a primary west-coast HAB ML feature.
- Prefer **Irish Sea / Celtic / Scotland** (and `total_box` / `full_extract`) for CPR narrative and heatwave/shelf context.

Exact counts: `data/processed/cpr_aoi_week_summary.json` and `cpr_ingest_summary.json`.

---

## 4. AOI-week product and HAB panel join

**PA ingest (source of truth for samples + first AOI-week build)**

```bash
.venv/bin/python scripts/ingest_cpr_mba.py
```

**Climate refresh of AOI-week + summary** (join-compatible columns; shared AOIs)

```bash
.venv/bin/python scripts/build_cpr_aoi_week.py
```

**Outputs**

| Path | Contents |
| --- | --- |
| `data/processed/cpr_samples.parquet` | PA sample table (gitignored via `*.parquet`) |
| `data/processed/cpr_aoi_week.csv` | `(aoi, iso_year, iso_week)` means + `n_samples` / `n` |
| `data/processed/cpr_aoi_week_summary.json` | Climate summary: AOI counts (zeros for Connemara) + aliases |
| `data/processed/cpr_ingest_summary.json` | PA ingest provenance |

Week metrics (means): `cpr_mean_dinoflagellates`, `cpr_mean_diatoms`, `cpr_mean_large_copepods`, `cpr_mean_small_copepods`, `cpr_pci`, `cpr_dino_diatom_ratio`.

**Left-join keys onto the HAB week panel** (same ISO week convention as `climate_indices_week` / `met_west_climate_week`):

1. Choose an AOI (`celtic`, `irish_sea`, `scotland`, … — **not** `connemara`).
2. Filter `cpr_aoi_week` to that `aoi`.
3. **Left-join** on **`iso_year` + `iso_week`**.

```python
import pandas as pd
cpr = pd.read_csv("data/processed/cpr_aoi_week.csv")
cpr = cpr.loc[cpr["aoi"] == "celtic", ["iso_year", "iso_week", "n_samples",
    "cpr_mean_dinoflagellates", "cpr_mean_diatoms", "cpr_mean_large_copepods",
    "cpr_mean_small_copepods", "cpr_pci"]]
panel = panel.merge(cpr, on=["iso_year", "iso_week"], how="left")
```

Or use PA helper: `scripts/join_cpr_hab_week.py` (station→AOI mapping + optional nearest-100 km).

Coverage is sparse even in well-sampled seas — **explanatory context**, not a dense feature.

---

## 5. Boundary

- Climate Drivers: AOI-week aggregates, summary JSON, this doc + `CLIMATE_DRIVERS.md` pointer.
- PA: raw ingest, sample parquet, HAB join, Dinophysis ablation honesty.
- **Not** a Dinophysis abundance series; **not** a Connemara local driver.
- Farm HTML / grower dashboard — untouched.

Large raw CSV + control-map PNG stay local (gitignored); taxa lists, README, small processed CSV/JSON/md are whitelisted.

---

## 6. Citation / legal (Cork slides)

**Cite:** Continuous Plankton Recorder (CPR) Survey data extract “IrishHeatwaves” by Pierre Hélaouët (MBA), DOI [10.17031/6a9e6f4a00142](https://doi.org/10.17031/6a9e6f4a00142).

**Use:** Attribution required. Treat as **research/demo citation** — do **not** redistribute the full sample CSV as a public training dump without confirming MBA licence terms on the DOI page. Users must verify fitness for purpose (per MBA extract note).

**Marine Legal Policy** should confirm licence wording (e.g. CC-BY-NC vs other) before any open release of derivatives beyond citation.

---

## 7. Ablation vs strong Dinophysis baseline (canonical)

Source of truth: `data/processed/cpr_ablation_metrics.json` + `cpr_ablation_report.md` (2026-09-08 09:38 UTC).

| Setting | n_feat | LightGBM test cal PR-AUC |
| --- | ---: | ---: |
| strong | 9 | **0.2845** |
| strong+CPR_AOI | 16 | **0.2904** (~+0.006) |
| strong+CPR_nearest100 | 15 | **0.2845** (= strong; nearest coverage **0.0%**) |
| strong+CPR_AOI+nearest100 | 22 | **0.2904** |

| Coverage | % of Irish station-weeks |
| --- | ---: |
| AOI-week CPR features | **~28.2%** |
| Nearest ≤100 km (same ISO week) | **0.0%** in this artifact |

**Verdict:** CPR does **not** beat strong for operational Cork claims. AOI add-on is a tiny exploratory bump at partial coverage; nearest join contributed nothing in this run. Use for **shelf / heatwave narrative only**.

---

## 8. Cork one-liner (locked)

> Across 40 years of MBA CPR tows on the Irish–Scottish shelf (~42k samples, 1982–2022), offshore dinoflagellate abundance in summer is ~200× winter — community context for our Dinophysis nowcast, not species counts, and the series stops before the June 2023 heatwave.

Further ask to Pierre deferred unless species-level *Dinophysis* or post-2022 data is needed.
