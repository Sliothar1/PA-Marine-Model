# MBA Continuous Plankton Recorder (CPR) — IrishHeatwaves extract

**Role:** Climate Drivers **AOI-week covariates** (community aggregates + PCI) for Irish Sea / Celtic / Scotland-west / heatwave–shelf narrative.  
**Not** a replacement for Met Éireann radiation/wind or NAO/EA/AMO ([`CLIMATE_DRIVERS.md`](CLIMATE_DRIVERS.md), [`MACRO_CLIMATE.md`](MACRO_CLIMATE.md)).  
**Script:** `scripts/build_cpr_aoi_week.py` (complements PA `scripts/ingest_cpr_mba.py`; does not redo sample ingest / taxon QC / HAB ablation).  
**Python:** `/workspace/pa-marine-model/.venv/bin/python`

---

## 1. What it is

MBA CPR extraction **“IrishHeatwaves”** by **Pierre Hélaouët** (07/09/2026).

| | |
| --- | --- |
| **DOI** | [10.17031/6a9e6f4a00142](https://doi.org/10.17031/6a9e6f4a00142) |
| **Web** | https://doi.mba.ac.uk/data/3793 |
| **On disk** | `data/external/cpr_mba/` (large raw sample CSV gitignored) |
| **Main CSV** | `raw/CPR_IrishHeatwaves_Data_04092026.csv` — **41 884** samples, **1982–2022** |
| **Bbox** | 49–61°N, −16–0°E |
| **Sample volume** | One CPR sample ≈ **3 m³** filtered water |

Group mean abundances only (not species counts):

- `Mean_LargeCopepods` / `Mean_SmallCopepods` (+ week helper `Mean_Copepods` = Large+Small)
- `Mean_Diatoms` / `Mean_Dinoflagellates`
- `PCI` — Phytoplankton Colour Index (silk greenness: 0 / 1 / 2 / 6.5)

Taxon lists: `raw/CPR_IrishHeatwaves_List_*.csv`. README: `README_from_docx.txt`.

---

## 2. Honest limitations

| Limit | Implication |
| --- | --- |
| **Aggregates only — no Dinophysis spp.** | Dinoflagellate list is Ceratium-heavy with **0 Dinophysis**. Cannot train/validate HAB Dinophysis from CPR dino means. |
| **Connemara nested = 0 tows** | No local CPR week features for Connemara farms; use MI HAB + buoy/Met. |
| **Western Irish shelf sparse (~35)** | Prefer Irish Sea / Celtic Sea / Scotland west for narrative. |
| **Ends Dec 2022** | Cannot attribute June 2023 shelf MHW with this CPR extract. |
| **Not Met / NAO** | AOI-week covariates only — does **not** replace Met Éireann or NAO/EA/AMO. |

---

## 3. AOIs (Climate Drivers ids)

| AOI id | Bbox (lat × lon) | Expected coverage |
| --- | --- | --- |
| `full_extract` | 49–61°N × −16–0°E | All CSV samples (~41 884) |
| `connemara_nested` | 53.1–53.6°N × −10.2–−9.3°E | **0** tows |
| `western_irish_shelf` | 52.5–55.0°N × −11.5–−9.0°E | **~35** tows (sparse) |
| `irish_sea` | 52.5–54.5°N × −6.2–−3.2°E | Good |
| `celtic_sea` | 49.5–52.0°N × −10.5–−5.5°E | Good |
| `scotland_west` | 54.75–60.76°N × −7.5–−0.83°E | Better than west Ireland coast |

Exact `n_samples` / `n_weeks`: `data/processed/cpr_aoi_summary.json`.

---

## 4. Build and use as AOI-week covariates

```bash
cd /workspace/pa-marine-model
.venv/bin/python scripts/build_cpr_aoi_week.py
```

| Path | Contents |
| --- | --- |
| `data/processed/cpr_aoi_week.csv` | One row per `(aoi, iso_year, iso_week)` — week means of group abundances + PCI + `n_samples` |
| `data/processed/cpr_aoi_summary.json` | Provenance + **per-AOI sample counts** (includes Connemara = 0) |

**Left-join onto a HAB week panel** (same ISO-week keys as `climate_indices_week` / `met_west_climate_week`):

1. Choose an AOI (`celtic_sea`, `irish_sea`, or `scotland_west` — **not** `connemara_nested`).
2. Filter `cpr_aoi_week` to that `aoi`.
3. Left-join on **`iso_year` + `iso_week`**.

```python
import pandas as pd
cpr = pd.read_csv("data/processed/cpr_aoi_week.csv")
cpr = cpr.loc[
    cpr["aoi"] == "celtic_sea",
    ["iso_year", "iso_week", "n_samples",
     "Mean_Dinoflagellates", "Mean_Diatoms", "Mean_Copepods", "PCI"],
]
panel = panel.merge(cpr, on=["iso_year", "iso_week"], how="left")
```

Coverage is sparse even in well-sampled seas — **explanatory context**, not a dense Met/NAO-style driver.

PA also ships `scripts/ingest_cpr_mba.py` (sample parquet + alternate AOI naming) and `scripts/join_cpr_hab_week.py`. If ingest overwrites `cpr_aoi_week.csv`, re-run `build_cpr_aoi_week.py` for the Climate Drivers AOI ids.

---

## 5. Boundary

- **In scope:** AOI-week aggregates, summary JSON, this doc + pointers from climate docs.
- **Out of scope:** Species-level Dinophysis, farm HTML / grower dashboard, replacing Met or NAO.
- Large raw CSV / control-map PNG stay gitignored; taxa lists, README, small processed CSV/JSON are whitelisted.
