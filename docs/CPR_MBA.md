# MBA Continuous Plankton Recorder (CPR) — IrishHeatwaves extract

**Role:** Climate-Drivers **support** — AOI × ISO-week aggregates for shelf / heatwave narrative.  
**Owner of heavy ingest:** PA/executor (species-level, full CPR pipeline). This package does **not** duplicate that.  
**Script:** `scripts/build_cpr_aoi_week.py`  
**Python:** `/workspace/pa-marine-model/.venv/bin/python`

---

## 1. What it is

MBA CPR data extraction **“IrishHeatwaves”** prepared by **Pierre Hélaouët** (07/09/2026).

| | |
| --- | --- |
| **DOI** | [10.17031/6a9e6f4a00142](https://doi.org/10.17031/6a9e6f4a00142) |
| **Web** | https://doi.mba.ac.uk/data/3793 |
| **On disk** | `data/external/cpr_mba/` (large raw gitignored) |
| **Main CSV** | `raw/CPR_IrishHeatwaves_Data_04092026.csv` — **41 884** samples, **1982–2022** |
| **Bbox** | 49–61°N, −16–0°E |
| **Sample volume** | One CPR sample ≈ **3 m³** filtered water |

Each row already carries **group mean abundances** (not raw taxon counts):

- `Mean_LargeCopepods` (≥2 mm; 44 taxa retained since 1982)
- `Mean_SmallCopepods` (&lt;2 mm; 33 taxa)
- `Mean_Diatoms` (61 taxa)
- `Mean_Dinoflagellates` (44 taxa)
- `PCI` — Phytoplankton Colour Index (silk greenness: 0 / 1 / 2 / 6.5)

Taxon membership lists sit beside the CSV (`raw/CPR_IrishHeatwaves_List_*.csv`). Control map PNG documents spatial coverage.

README excerpt (from MBA docx): `data/external/cpr_mba/README_from_docx.txt`.

---

## 2. Aggregates only — cannot validate Dinophysis

**This product cannot validate *Dinophysis* spp. abundance.**

- The CSV exposes **Mean_Dinoflagellates** (and other **group** means) only.
- The accompanying dinoflagellate taxon list has **no Dinophysis** entries (Ceratium, Gymnodinium, Prorocentrum spp., etc., but not Dinophysis).
- Do **not** treat `Mean_Dinoflagellates` as a Dinophysis proxy for HAB exceedance validation or grower scoring.
- Species-level CPR work (if any) is **out of scope** here — leave to PA ingest.

Honest use: phytoplankton/zooplankton **community context** and PCI for Irish Sea / Celtic Sea / Scotland-west / heatwave–shelf narrative.

---

## 3. Spatial honesty

| AOI id | Bbox (lat × lon) | Role |
| --- | --- | --- |
| `full_extract` | 49–61°N × −16–0°E | Entire MBA extract |
| `irish_sea` | 52–55°N × −6.5–−2.5°E | Irish Sea — **good** coverage |
| `celtic_sea` | 49–52°N × −11–−5°E | Celtic Sea — **good** coverage |
| `western_irish_shelf` | 51.5–54.5°N × −11–−9.5°E | Coastal western Irish shelf — **sparse** (~tens of tows; mostly SW approaches) |
| `connemara_nested` | 53.1–53.6°N × −10.2–−9.3°E | Connemara farm/HAB nested box — **0 tows** |
| `scotland_west` | 55.5–59.5°N × −8–−4°E | West Scotland approaches — **well covered** vs west Ireland coast |

**Takeaways**

- **Connemara nested = empty.** No local CPR week features for Connemara farms from this extract.
- **Western Irish shelf coastal strip is sparse** (~35–45 samples depending on exact box; we use the table above and report exact counts in the summary JSON). Not a primary ML feature source for west-coast HAB weeks.
- Prefer **Irish Sea / Celtic Sea / Scotland west** (and `full_extract`) for CPR narrative and heatwave/shelf context.
- Deeper offshore west of Ireland has more tows than the coastal shelf strip; that is **not** the `western_irish_shelf` AOI above.

Exact `n_samples` / `n_weeks` per AOI: `data/processed/cpr_aoi_week_summary.json` (regenerate with the script).

---

## 4. AOI-week product and HAB panel join

**Build**

```bash
cd /workspace/pa-marine-model
.venv/bin/python scripts/build_cpr_aoi_week.py
```

**Outputs**

| Path | Contents |
| --- | --- |
| `data/processed/cpr_aoi_week.csv` | One row per `(aoi, iso_year, iso_week)` with mean group abundances + PCI + `n_samples` |
| `data/processed/cpr_aoi_week_summary.json` | Provenance + **AOI sample counts** (includes zeros for Connemara) |

Week columns (means over samples in that AOI-week):

- `Mean_Dinoflagellates`, `Mean_Diatoms`, `Mean_Copepods` (= Large+Small per sample, then week-mean)
- `Mean_LargeCopepods`, `Mean_SmallCopepods`, `PCI`
- `n_samples`, `week_start` (Monday of the ISO week)

**Left-join keys onto the HAB week panel** (same convention as `climate_indices_week` / `met_west_climate_week`):

1. Choose an AOI (e.g. `celtic_sea` or `irish_sea` — **not** `connemara_nested`).
2. Filter `cpr_aoi_week` to that `aoi`.
3. **Left-join** the HAB panel on **`iso_year` + `iso_week`**.

```python
import pandas as pd
cpr = pd.read_csv("data/processed/cpr_aoi_week.csv")
cpr = cpr.loc[cpr["aoi"] == "celtic_sea"].drop(columns=["aoi", "week_start"], errors="ignore")
panel = panel.merge(cpr, on=["iso_year", "iso_week"], how="left")
```

Coverage will be sparse/missing for many HAB weeks even in well-sampled seas — treat as **explanatory context**, not a dense feature.

---

## 5. What this is not (PA boundary)

- **Not** a replacement for PA CPR ingest / taxon expansion / QC.
- **Not** a Dinophysis abundance series.
- **Not** a Connemara local driver (0 nested tows).
- Farm HTML / grower dashboard products are untouched.

Large raw CSV + control-map PNG stay under `data/external/cpr_mba/` and are **gitignored**; small processed CSV/JSON and this doc are whitelisted.
