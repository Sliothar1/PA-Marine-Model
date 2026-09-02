# Climate drivers — Met Éireann, rivers, SST warming

**Agent:** Climate Drivers · **Date:** 2026-09-02 (Europe/Dublin)  
**Repo:** `pa-marine-model` / [Sliothar1/PA-Marine-Model](https://github.com/Sliothar1/PA-Marine-Model)  
**Goal:** Explanatory power beyond the strong 9-feature Dinophysis OISST model (`STRONG_OISST`).

## What was added

### 1. Met Éireann west-coast open CSVs (clidata)

Script: `scripts/ingest_met_climate_drivers.py`  
Pattern: `https://clidata.met.ie/cli/climate_data/webdata/{dly|hly|mly}{STN}.csv` (same as Mace Head `275`).  
Station IDs **verified by HTTP GET** (not invented).

| Station | ID | Role | Products | Daily range | Key fields | Raw / processed |
| --- | ---: | --- | --- | --- | --- | --- |
| **Belmullet** | **2375** | Primary radiation + sunshine (NW Mayo / west) | dly, hly, mly | 1956-09-17 → 2026-07-31 | `glorad`, `sun`, `wdsp`, rain, temps | `data/raw/met_eireann/belmullet_*` → `belmullet_met_daily.*`, `_week.*`, `_monthly.*` |
| Valentia Observatory | 2275 | SW west-coast long wind + rad/sun | dly, mly | 1942-01-01 → 2026-07-31 | `glorad`, `sun`, `wdsp` | `valentia_*` |
| Malin Head | 1575 | NW long wind + rad/sun | dly, mly | 1955-05-01 → 2026-07-31 | `glorad`, `sun`, `wdsp` | `malin_head_*` |
| Newport | 1175 | Mayo / Clew Bay adjacent `glorad` | dly | 2005-02-22 → 2026-07-31 | `glorad`, `wdsp` (no `sun`) | `newport_*` |
| Mace Head (refresh) | 275 | Connemara (already in scout P0) | dly, mly | 2003-08-14 → 2026-07-31 | `glorad`, `wdsp` (no `sun`) | `mace_head_*` |

**Regional week panel:** `data/processed/met_west_climate_week.parquet` (+ `.csv`)  
Broadcast columns for HAB joins: `met_glorad` (Mace→Belmullet fill), `met_sun` (Belmullet), `met_wdsp`, plus per-station and `met_west_*` composites.

**June 2023 Belmullet check:** mean `glorad` ≈ 2005 J/cm², mean `sun` ≈ 7.48 h, mean `wdsp` ≈ 9.3 kt (vs Mace Head June 2023 glorad ≈ 2107, wind ≈ 11.1 kt).

**Sources JSON:** `data/raw/met_eireann/sources_climate_drivers.json`  
**Ingest summary:** `data/processed/met_climate_drivers_ingest_summary.json`

data.gov.ie packages for Belmullet point at the same clidata CSVs (`belmullet-daily-data`, `belmullet-monthly-data`).

### 2. Irish-shelf June SST warming context

Script: `scripts/build_sst_warming_context.py`

| Artefact | Path |
| --- | --- |
| Figure | `docs/climate_assets/irish_shelf_june_sst_trend.png` (copy: `data/processed/figures/…`) |
| Series CSV | `data/processed/irish_shelf_june_sst_series.csv` |
| Metrics JSON | `data/processed/sst_warming_context_metrics.json` |
| Year features (ablation) | `data/processed/sst_warming_year_features.csv` |
| Short markdown | `docs/SST_WARMING_CONTEXT.md` |

**Headline (OISST station-mean June, 2002–2026):**  
**+0.30 °C/decade** (R² ≈ 0.07). First-5 Junes ≈ 13.52 °C → last-5 ≈ 14.33 °C (Δ ≈ +0.81 °C).  
OSTIA cross-check: **+0.17 °C/decade** (2002–2025). Soft trend — useful narrative context, not a strong standalone predictor.

### 3. Ablation vs strong Dinophysis baseline

Script: `scripts/climate_drivers_ablation.py`  
Outputs: `data/processed/climate_drivers_ablation_metrics.json`, `climate_drivers_ablation_report.md`

Target: `y_dinophysis_nowcast`. Headline metric: **LightGBM test calibrated PR-AUC**.

| config | n_feat | val cal PR-AUC | test cal PR-AUC | Δ test vs strong |
| --- | ---: | ---: | ---: | ---: |
| `strong` | 9 | 0.543 | **0.295** | 0 |
| `strong_met_rad` | 15 | 0.549 | 0.253 | −0.042 |
| `strong_river_Q` | 12 | 0.553 | 0.249 | −0.046 |
| `strong_warming` | 12 | 0.561 | 0.294 | −0.001 |
| `strong_met_river` | 18 | 0.551 | 0.240 | −0.055 |
| `strong_climate_all` | 21 | 0.574 | 0.285 | −0.010 |

Reference file baseline (`metrics_dino_strong.json` LightGBM test cal): **0.293**.

**Verdict (honest):** Met radiation/sunshine, Corrib/Owenboliskey Q, and year-level warming proxies **do not lift** national Irish Dinophysis test PR-AUC vs the strong 9-feature model. Val often improves (overfit risk); test drops or ties. Same story as ERA5 wind. Still valuable for **Connemara narrative / case studies** (June 2023 high solar + weak winds) and for local farm scoring context — not for replacing `strong` nationally.

Coverage: Met week ~96–99% non-null on panel weeks; river Q ~76–89%; warming year features 100%. Spatial caveat: Met is west-coast point/composite broadcast nationally; Q is Galway Bay regional.

Closure-risk ablation was **not** re-run (optional; Dinophysis national result already negative — not worth DSP rework).

## Rivers (already on disk)

See `data/processed/rivers_hab_join_note.md`. Primary Q week file: `rivers_week_primary_Q.csv` (31075 Owenboliskey, 30061 Corrib Wolfe Tone, 30031 Cong).

## Manual Met Éireann leftovers for Garry

Open clidata covered the main synoptic need. Items that may still need **manual export / browser** (login or non-CSV):

1. **Monthly / annual Climate Statements (narrative PDFs)** — met.ie climate-change / climate-statements pages are JS/CMS-heavy; PDF URL patterns 404’d from this box. Useful for paper prose (e.g. “June 2023 was …”). Export from [met.ie climate pages](https://www.met.ie/climate/) or press archive when needed.
2. **Shannon Airport (`dly518`)** — long wind + `sun`, **no `glorad`** in open daily CSV. Optional if a mid-west wind series is wanted.
3. **Knock Airport (`dly4935`)** — `sun` + wind, no `glorad`.
4. **Roundstone (`dly1725`)** — Connemara-local but **rain-only**; open CSV already available if precip narrative needed.
5. **Homogenised long series / special radiation networks** — anything behind Met Éireann request forms or non-clidata portals.
6. **Hourly Belmullet** is already downloaded (`belmullet_hourly_hly2375.csv`, ~52 MB, gitignored under `data/raw/`); re-download via the ingest script if wiped.

Prefer **clidata / data.gov.ie** over anything needing credentials.

## How to re-run

```bash
source .venv/bin/activate
python scripts/ingest_met_climate_drivers.py
python scripts/build_sst_warming_context.py
python scripts/climate_drivers_ablation.py
```

Do not use Cloud Agents for this track. Large raw CSVs/parquets stay gitignored; commit scripts, docs, and whitelisted metrics/reports only.

## data.gov.ie Monthly Agmet + external mirror (2026-09-02, while Garry away)

Pulled **without login** into `data/external/met_eireann/`. Agmet endpoints are JSON from `prodapi.met.ie` (data.gov.ie “Monthly weather …” packages); tidy CSVs derived locally. Classic long monthly/daily CSVs from open `clidata.met.ie` (no form required).

### Files landed

| File | Source | Coverage | Solar / radiation |
| --- | --- | --- | --- |
| `monthly_agmet_mace_head.json` + `.csv` (+ `_LTA.csv`) | [Monthly weather Mace Head](https://data.gov.ie/dataset/monthly-weather-mace-head) → `https://prodapi.met.ie/monthly-data/Mace%20Head` | 2023-01 → 2026-08 (`up_to` 31-08-2026); LTA sidecar | **Yes** — `solar_radiation` / `global_solar_radiation` (monthly total **J/cm²**; matches sum of daily `glorad`) |
| `monthly_agmet_newport.json` + `.csv` (+ `_LTA.csv`) | [Monthly weather Newport](https://data.gov.ie/dataset/monthly-weather-newport) → `…/Newport%20Furnace` | 2023-01 → 2026-08 | **Yes** (same field) |
| `monthly_agmet_belmullet.json` + `.csv` (+ `_LTA.csv`) | [Monthly weather Belmullet](https://data.gov.ie/dataset/monthly-weather-belmullet) → `…/Belmullet` | 2023-01 → 2026-08 | **Yes** |
| `monthly_agmet_malin_head.json` + `.csv` (+ `_LTA.csv`) | [Monthly weather Malin head](https://data.gov.ie/dataset/monthly-weather-malin-head) → `…/Malin%20Head` | 2023-01 → 2026-08 | **Yes** |
| `daily_mace_head_dly275.csv` | Open clidata `dly275` ([Mace Head Daily Data](https://data.gov.ie/dataset/mace-head-daily-data)) | **2003-08-14 → 2026-07-31** (8336 days) | **Yes** — `glorad` Global Radiation (J/cm²); ~98.5% filled |
| `monthly_classic_mace_head_mly275.csv` (+ pre-existing `mace_head_monthly.csv` same series) | clidata `mly275` | 2003-11 → 2026-07 | **No usable sun** — `sun` column blank for all months (classic monthly) |
| `monthly_classic_malin_head_mly1575.csv` | clidata `mly1575` / [Malin head Monthly Data](https://data.gov.ie/dataset/malin-head-monthly-data) | 1955-05 → 2026-07 | Sunshine hours `sun` (not global radiation); some blanks in recent months |

Agmet also includes rain, mean temp, soil 10 cm (empty at Mace Head in this extract), PE, evaporation, degree-days below 15.5 °C. Metadata on data.gov.ie: “Current plus previous 3 years” — matches the short Agmet window; **use daily `glorad` / classic long CSVs for multi-decade solar**.

### Historical Data page vs scriptable downloads

- UI: https://www.met.ie/climate/available-data/historical-data embeds a human iframe (`clidata.met.ie/cli/climate_data/showdata.php`) — form/map picker.
- **Scriptable without the form:** direct open CSVs `https://clidata.met.ie/cli/climate_data/webdata/{dly\|hly\|mly}{STN}.csv` (Mace Head daily = `dly275.csv`). Daily Mace Head **was pulled** this way; no Garry login needed.
- Blocker for form-only extras: none for this pull. Remaining manual items stay under “Manual Met Éireann leftovers” above (Climate Statement PDFs, etc.).

**Attribution:** Copyright Met Éireann · Source www.met.ie · CC BY 4.0.
