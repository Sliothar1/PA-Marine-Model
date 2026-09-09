# PA demo feature notes (`pa/demo-workstream`)

One small, coherent package for Cork **storytelling**. Not a national skill claim.

## What was added

| Piece | Where | What it is |
| --- | --- | --- |
| Station×week empirical risk | `src/pa_marine/demo_features.py` | Train-only (split=`train`) shrunk station rate, week-of-year rate, and logit-additive station×week probability → columns `demo_sw_station_rate`, `demo_sw_week_rate`, `demo_sw_station_week_rate` |
| SST coverage flags | same | `cov_sst_missing` (row), `cov_sst_always_missing` (station; Rosmuc landmask story), `cov_snap_dist_deg` / `cov_snap_dist_km` (naive 0.25° OISST snap via existing `snap_oisst` + `lon_to_oisst_360`) |
| Opt-in feature mode | `features.select_feature_mode("demo_station_week")` | `STRONG_OISST` **plus** the demo columns if present. **Default `strong` is unchanged.** |
| Baseline exporter | `station_week_baseline_probs()` | Same rates as a probability vector (for demos / later gates) |
| Instance exporter | `scripts/export_demo_instances.py` | Felix 2018 / 2022 / 2023 JSON windows |

`STRONG_OISST` still has exactly the original 9 columns. `feature_columns()` does **not** auto-include `demo_sw_*` / `cov_*`, so `evaluate.py --feature-mode strong` and the Cork quote path are untouched.

## Why

Claude CONTEXT on `review/claude-patch-2` (not merged here) found a **station×week** lookup ≈ **0.284** PR-AUC on the real Irish panel, vs published STRONG_OISST ≈ **0.292** (skill ≈ 0.010, CI spanning zero). That is a grower-explainable baseline: “this farm, this week of year.”

PA needs those rates **on `main`** for:

- Demo JSON (`demo_sw_station_week_rate` next to weekly SST / HAB)
- Coverage honesty (Rosmuc `sst` always NaN; inshore snap distance)
- A future ablation **candidate**, without pulling Meta’s detector/split rewrites

## Demo-only vs later ablation

| Column / mode | Cork demo | Later ablation candidate? |
| --- | --- | --- |
| `STRONG_OISST` | **Yes — only judge-card features** | Already gated (`metrics_dino_strong.json`) |
| `demo_sw_*` | Yes, as a **lookup-table story**, labelled | **Candidate only.** Needs a gate file (train-only rates, same splits, calibrated PR-AUC vs week **and** vs station×week). No claim until that exists. |
| `cov_*` | Yes, as missingness / landmask flags | Candidate as **masks / strata**, not as “skill features.” |
| Chl / ODYSSEA | Narrative onion only | Parked predictive (`docs/CHL_OSI_STATUS.md`) |
| Claude downscale / scheduler / advection | **Out of scope on this branch** | Meta lane |

**Do not** quote 0.284 as *this repo’s* reproduced metric on `pa/demo-workstream`. Cite it as CONTEXT from the review branch. Reproducing it requires Meta’s diagnostics script + the gitignored full `joined_features.parquet` bootstrap — not done here.

## How to attach on a local join

```python
from pa_marine.demo_features import attach_demo_features

df = attach_demo_features(joined_features)  # needs split + y_dinophysis_nowcast for rates
```

Train years: 2003–2018. **2018 demo windows are in-sample** for `demo_sw_*`. 2022 / 2023 are out-of-sample (test).

Naive snap distance is **not** nearest-ocean km (Claude reported median ~14.7 km on a mask extract). We only reuse `snap_oisst` already on `main`. If `dist_deg` is already on the frame, it is copied to `cov_nearest_ocean_dist_deg`.

## Tests

`tests/test_demo_features.py` — STRONG_OISST frozen at 9 cols; rates present; demo mode opt-in; Rosmuc-style always-missing flag; exporter schema.
