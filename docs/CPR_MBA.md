# Continuous Plankton Recorder (CPR) — MBA IrishHeatwaves extract

**Received:** 2026-09 (Europe/Dublin) from **Pierre Hélaouët** (MBA / CPR Survey).  
**DOI:** [10.17031/6a9e6f4a00142](https://doi.org/10.17031/6a9e6f4a00142) · [doi.mba.ac.uk/data/3793](https://doi.mba.ac.uk/data/3793)  
**PA scripts:** `scripts/ingest_cpr_mba.py`, `scripts/join_cpr_hab_week.py`.  
**Climate-Drivers helper:** `scripts/build_cpr_aoi_week.py` → `cpr_aoi_week_climate_drivers.csv` (must not overwrite PA `cpr_aoi_week.csv`).  
**Related:** [`CORK_CHEAT_SHEET.md`](CORK_CHEAT_SHEET.md) · [`CLIMATE_DRIVERS.md`](CLIMATE_DRIVERS.md) · [`MACRO_CLIMATE.md`](MACRO_CLIMATE.md).

Control map: [`climate_assets/cpr_irish_heatwaves_control_map.png`](climate_assets/cpr_irish_heatwaves_control_map.png).

---

## 1. What we got

| File | Role |
| --- | --- |
| `data/external/cpr_mba/raw/CPR_IrishHeatwaves_Data_04092026.csv` | **41 884** samples · group means + PCI |
| Taxa lists `List_*.csv` | Diatoms 61 · Dinos 44 (**0 Dinophysis**; Ceratium-dominated) · copepods |
| Control map PNG | under `docs/climate_assets/` + `data/processed/figures/` |
| `README_from_docx.txt` | Pierre extract notes |

**Columns:** SampleId, Latitude, Longitude, Year, Month, Day, Hour, Minute, Mean_LargeCopepods, Mean_SmallCopepods, Mean_Diatoms, Mean_Dinoflagellates, PCI.  
**Span:** **1982–2022** (before June 2023 MHW); lat ≈ 49–61°N, lon ≈ −16–0°E; ~3 m³/sample.

**COMMUNITY AGGREGATES, not species counts.** Do **not** claim CPR Dinophysis labels.

---

## 2. Honest limitations

| Limit | Implication |
| --- | --- |
| No Dinophysis spp. | Regime / community covariate only |
| Connemara nested = 0 tows | No local CPR for Connemara farms |
| Ends Dec 2022 | Cannot speak to June 2023 MHW with CPR |
| Spatial mismatch vs HAB stations | AOI-week or nearest ≤100 km same ISO week |

---

## 3. Strategy

**Covariates:** Mean_Dinoflagellates, Mean_Diatoms, dino/diatom ratio, PCI, copepods as offshore regime indicators.

**Weekly AOI aggregates** (`ingest_cpr_mba.py` — 6 AOIs + total box):

| AOI | Sample n |
| --- | ---: |
| western_shelf | 35 |
| celtic | 5783 |
| irish_sea | 3944 |
| shelf_break | 863 |
| malin | 300 |
| scotland | 11673 |
| total_box | 33270 |
| connemara (nested) | **0** |

Outputs: `cpr_samples.parquet`, `cpr_aoi_week.csv` (`year`, `week`, `aoi`, `n`, mean dino/diatom/copepods/pci + ratio), `cpr_ingest_summary.json`.

**Join to HAB station-weeks:** `join_cpr_hab_week.py` — AOI×ISO-week (+ optional nearest ≤100 km) vs strong 9-feature OISST; overlap ≤2022.

**Cork narrative:** control map + multi-year dino/diatom seasonality; **do not overclaim heatwave 2023** (no 2023 CPR).

---

## 4. Reproduce

```bash
.venv/bin/python scripts/ingest_cpr_mba.py
.venv/bin/python scripts/join_cpr_hab_week.py --skip-nearest
.venv/bin/python scripts/build_cpr_aoi_week.py   # climate-drivers CSV only
```

---

## 5. Ablation snapshot (AOI join; `--skip-nearest`)

| | |
| --- | --- |
| Panel AOI coverage | ~28.2% |
| Strong test PR-AUC (cal) | ~0.29–0.30 |
| Strong+CPR_AOI | ~0.28–0.29 (≈ flat / slight down) |

Exploratory only — CPR is not Dinophysis; do not claim operational lift. See `data/processed/cpr_ablation_report.md`.

---

## 6. Follow-up asks to Pierre (MBA)

1. **Species-level Dinophysis** (or DSP-relevant dinoflagellates) if available for the same AOI/period.  
2. **Post-2022 extract**, especially June 2023 shelf MHW.  
3. Optional: AOI polygon confirmation / PCI QC flags.

## 7. Credit

MBA CPR Survey / Pierre Hélaouët — DOI 10.17031/6a9e6f4a00142. Users verify fitness for purpose.
