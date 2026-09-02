# Connemara Farms — grower / co-op guide to weekly HAB scores

One-page guide for shellfish growers and co-ops using the Connemara Farms
Dinophysis risk dashboard (`data/processed/connemara_farms_scores.html`).

**This is a research nowcast — not an official Marine Institute (MI) warning.**
Harvest decisions must follow official HAB / biotoxin notices and sampling results.

## What you are looking at

Each site-week gets a **calibrated probability** that *Dinophysis* will be at or
above **100 cells per litre** in the **current or next** monitoring week
(roughly a 0–2 week nowcast). The model uses national Irish sea-surface
temperature patterns (NOAA OISST), week-of-year, and location — applied to
Connemara NMP sites (not a Connemara-only retrain).

Open the HTML dashboard for the visual “this week” cards and tables. CSV exports
(`connemara_farms_latest.csv`, `connemara_farms_scores.csv`) are for spreadsheets.

## Risk bands (plain English)

| Band | Score (probability) | What it means for a co-op |
| --- | --- | --- |
| **Higher** | ≥ 15% | **Higher watch.** Elevated chance Dinophysis is at/above the monitoring threshold in this or next week. Check MI bulletins and recent cell counts before firm harvest plans. |
| **Moderate** | 7% – < 15% | **Moderate watch.** Some seasonal / SST-linked risk. Keep reading bulletins; no automatic harvest change on the score alone. |
| **Lower** | < 7% | **Lower watch.** Below typical risk for this week-of-year, or quiet conditions. Still follow official notices — “Lower” is not a green light to ignore MI. |

Bands are **communication aids**, not regulatory cut-offs. A “Higher” band with
cell counts still near zero is a **heads-up**, not a closure. A “Lower” band
during an active MI advisory does **not** overrule the advisory.

Also check **vs seasonal usual**: how this week’s score compares to the
historical average risk for that same week-of-year. Positive = warmer/riskier
than a typical year for that week; negative = quieter than seasonal average.

## How a co-op should use this with MI bulletins

1. **Start with official MI HAB / biotoxin bulletins and your site’s latest
   cell counts / toxin results.** Those remain authoritative.
2. **Open the dashboard “latest week” banner and Killary cards** if you farm
   the fjord (Inner / Middle / Outer are listed first).
3. **Use bands as planning context:** Higher/Moderate → schedule a closer look
   at bulletins, recent samples, and logistics (harvest timing, relay, testing).
   Do not invent a closure from the model alone.
4. **Closure-risk proxy** (when present) is a national area-closed research
   head — useful context, often blank (“—”) when toxin data lag phytoplankton.
5. **Re-check after each new MI sample week**; scores only appear for weeks
   that were sampled (no sample ≠ “all clear”).

## Priority places on the map

| Place | Role on the dashboard |
| --- | --- |
| **Killary Inner / Middle / Outer** | Core NMP sites — shown first in “this week” cards. |
| **Mace Head buoy** | Sentinel hydrography only (T/S/DO/nitrate). **Not HAB-scored.** |
| **Lehanagh buoy** | Near-real-time buoy from May 2024. **Not HAB-scored.** |
| **Lehanagh (NMP)** | Sparse / historical samples (≈2009–2020). Kept for continuity; **not** in the latest grower table. |
| Mannin, Clifden, Ballynakill, Rosmuc, Gubbaros | Other scored NMP / nearby sites in the tables. |

## Limitations (honest)

- **Rosmuc:** OISST SST is null at the station pixel (landmask / inshore). Scores
  there use season + location only — treat with extra caution.
- **Lehanagh NMP:** historical-only; do not expect a current week score.
- **Mace Head / Lehanagh buoys:** no Dinophysis labels — context, not risk bands.
- **National skill ≠ local crystal ball:** the model has documented national
  ranking skill; on Connemara alone, positives are rare and local PR skill vs
  seasonal climatology is weak. Use as **seasonal + SST context** next to MI data.
- **Irregular sampling:** missing weeks mean “not sampled,” not “zero risk.”
- **Not product idea 3:** this guide does not cover the heatwave event brief.

## Regenerate (ops)

```bash
python3 scripts/score_connemara_farms.py
```

More detail for analysts: [`CONNEMARA_FARMS.md`](CONNEMARA_FARMS.md).
