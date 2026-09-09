# PA ↔ Meta handoff (Cork / demo week)

**Date:** 2026-09-09  
**Purpose:** Keep PA demo + GrokD4M work off the Meta/Claude Mac science-review branches so neither lane collides.

This file is the map for tomorrow. Science numbers below are **locks / citations**, not new claims.

---

## Two lanes (do not mix)

| Lane | Who | Git | What it is for |
| --- | --- | --- | --- |
| **PA demo** | PA + GrokD4M `/marine` | **This branch** `pa/demo-workstream` (PA-Marine-Model, off `main`) **and** GrokD4M branch `hackathon-marine-demo` | Cork storytelling, Felix’s 3 instance windows, grower/demo JSON, light feature exporters |
| **Meta / Claude Mac** | Meta | `review/claude-patch-2` (and frozen predecessor `review/claude-patch`) | Science review: Hobday event **order**, diagnostics, downscale / scheduler / advection / decisions |

**Do not** checkout, rebase, merge, or force-push `review/claude-patch` or `review/claude-patch-2` from the PA lane.  
**Do not** land PA demo JSON / handoff docs onto those branches.

Divergence (as of this branch’s cut from `main`): `review/claude-patch-2` is **7 commits ahead / ~58 behind `main`**. It needs a **careful rebase later**, not a casual merge during demo week.

---

## Cork judge-quote lock (both lanes)

Quote **only**:

- Spine: `STRONG_OISST` (9 columns) — calibrated LightGBM test PR-AUC **~0.295** (`metrics_dino_strong.json` → 0.293)
- Week-of-year climatology on the same protocol ≈ **0.183**; PR skill ≈ **0.13**
- Chl / ODYSSEA / OSI SAF: **narrative-only** for Cork (June 2023 onion). **No** national predictive claim. See `docs/CHL_OSI_STATUS.md` Cork weekend lock.
- Heatwave **≠** bloom. June 2023: CRW mean `frac_mhw` ≈ **0.96**, national Dinophysis **below** same-week climatology (`mhw_hab_brief_2023-06-30.md`).

Do **not** rewrite `docs/CPR_MBA.md`.  
Do **not** claim a new national skill number without an honest ablation **gate file**.

---

## What’s safe to pull vs leave alone

### Safe for PA to use from `main` (already here)

- Cork pack: `docs/HACKATHON_DEMO.md`, `docs/CORK_CHEAT_SHEET.md`, `docs/demo.html`
- STRONG_OISST in `src/pa_marine/features.py` (do not shrink or replace this set)
- Committed metrics / June 2023 case study / MHW briefs / Connemara Farms tables
- `data/processed/joined_features_osi_sst.parquet` (tracked) as a **demo panel** if `joined_features.parquet` is gitignored/missing locally
- This branch’s `scripts/export_demo_instances.py` → `data/processed/demo_instances/`

### Leave for Meta (on `review/claude-patch-2` only)

| Area | Why PA stays out |
| --- | --- |
| Hobday duration-filter **then** gap-join (MHW event assembly order) | Changes `mhw.py` detector; would shift every `in_mhw` flag vs Cork-quoted case study |
| Fixed climatology baseline years `[2003, 2018]` inside the detector | Same — MHW intensity / duration would no longer match committed June 2023 tables |
| `diagnostics.py` / permutation / cluster bootstrap | Science-review result; PA cites CONTEXT **0.284** as motivation only |
| Inshore downscale / sampling scheduler / advection graph / decision layer | New modules on the patch branch; rebase later |
| Label-window purge / grouped CV / great-circle nearest-ocean rewrite | Touches `hab.py`, `splits.py`, `sst.py` — high merge conflict with demo-week `main` |

PA **may cite** Claude CONTEXT (station×week ≈ 0.284; skill vs that baseline CI spans zero) in demo narrative. PA **must not** copy those detector/split changes onto this branch to “make the number appear.”

### Safe for Meta to ignore on this PR

- `docs/PA_META_HANDOFF.md`, `docs/PA_FEATURE_NOTES.md`
- `src/pa_marine/demo_features.py` (additive; does not change `STRONG_OISST`)
- `scripts/export_demo_instances.py` + `data/processed/demo_instances/samples/`
- Light pointers in `docs/HACKATHON_DEMO.md`

Meta can keep working on `review/claude-patch-2` against their Codespace/Mac clone. When rebase time comes: rebase **onto `main` after this PR**, not onto `pa/demo-workstream`, unless PA demo code is already merged.

---

## GrokD4M `/marine` copy path

After `python scripts/export_demo_instances.py`:

```bash
# In GrokD4M (branch hackathon-marine-demo)
mkdir -p data/marine/instances
cp /path/to/PA-Marine-Model/data/processed/demo_instances/2018_jja_ne_atlantic.json data/marine/instances/
cp /path/to/PA-Marine-Model/data/processed/demo_instances/2022_jja_galway_connemara.json data/marine/instances/
cp /path/to/PA-Marine-Model/data/processed/demo_instances/2023_june_flagship.json data/marine/instances/
```

Schema: `pa_marine.demo_instance.v1` (see instance JSON `copy_to_grokd4m` key).  
Small committed samples: `data/processed/demo_instances/samples/*.sample.json`.

---

## Tomorrow checklist

1. PA: stay on `pa/demo-workstream`; run exporter if local `joined_features.parquet` is newer than the OSI-joined copy.
2. Meta: stay on `review/claude-patch-2` (Mac / Codespace). Do not merge main into it mid-demo unless you have time for a full MHW-table re-verify.
3. Both: same judge card — **0.295 STRONG_OISST**, Chl/ODYSSEA narrative, 2023 MHW ≠ bloom.
4. Rebase of the Claude patch is a **later** science task, not a demo-day task.
