# Cork Ocean Hackathon — 1-page talk track

**Open first:** [`docs/demo.html`](demo.html) (layman walkthrough).  
**Teammate pack:** [`docs/HACKATHON_DEMO.md`](HACKATHON_DEMO.md).  
**Research demo — not an official warning.**

---

## Problem (~20 s)

Dinophysis blooms drive **DSP shellfish closures** on Irish coasts. Growers and agencies need more than a wall calendar: which **weeks** look unusually risky at **this** bay, given recent sea temperature — and when a **shelf marine heatwave** hits, does it actually matter for HABs?

---

## Three products (one metric each)

| # | Product | One metric to quote | Open / run |
| --- | --- | --- | --- |
| **1** | **Harvest-closure risk** (ops head) | Test **PR-AUC ~0.32** vs calendar **~0.21** (area closed; LightGBM + val calibration, strong OISST) | [`dsp_closure_risk_report.md`](../data/processed/dsp_closure_risk_report.md) · `python scripts/train_dsp_closure_risk.py` |
| **2** | **Connemara Farms** weekly Dinophysis scores | National apply skill **PR-AUC ~0.29** vs clim **~0.18** (local positives too sparse to retrain) | [`connemara_farms_scores.html`](../data/processed/connemara_farms_scores.html) · [`CONNEMARA_FARMS.md`](../CONNEMARA_FARMS.md) |
| **3** | **MHW × HAB event brief** — *Will this heatwave matter for HABs?* | June 2023 flagship: Irish-box CRW mean **frac_mhw ≈ 0.96**, yet national Dinophysis/closures **not** above climatology | [`mhw_hab_brief_2023-06-30.md`](../data/processed/briefs/mhw_hab_brief_2023-06-30.md) · [`MHW_EVENT_PRODUCT.md`](MHW_EVENT_PRODUCT.md) |

Honest one-liner: modest but real ranking skill on SST; heatwaves are situational context, **not** automatic bloom alarms.

---

## Local Connemara hook (~30 s)

June 2023 NW European shelf MHW ([Berthou et al. 2024](https://doi.org/10.1038/s43247-024-01413-8)): Irish CRW nearly wall-to-wall MHW; **Mace Head ~16 °C**; Corrib Q low; Rosmuc (late May) and Mannin (mid-July) exceedances **bookend** the peak — story, not causation. Grower table: Connemara Farms HTML (Killary, Mannin, Clifden, …).

---

## Live click path (2 min)

1. Open **`docs/demo.html`** — problem → proof cards → June 2023 figures.  
2. Open **Connemara Farms** HTML — weekly risk bands for local sites.  
3. Open **June 2023 MHW brief** (`.md` / `.txt`) — shelf heatwave vs HAB/closure context.  
4. Point at **closure-risk report** for the euro-relevant metric (~0.32 PR-AUC).

```bash
# From repo root (processed artifacts already present)
python scripts/demo_snapshot.py
python scripts/mhw_hab_brief.py                 # flagship June 2023
# optional: last ~30 days of CRW coverage (see MHW_EVENT_PRODUCT.md)
python scripts/mhw_hab_brief.py --latest
```

---

## Do / don’t

| Do | Don’t |
| --- | --- |
| Quote calibrated PR-AUC vs week-of-year clim | Claim operational harvest open/close |
| Show June 2023 as monitoring context | Claim MHW → bloom causation |
| Name Connemara sites + Mace Head | Hide Rosmuc OISST gap / rare DSP toxin weeks |
