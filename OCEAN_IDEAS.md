# Five ways to monitor and predict ocean change

*A twelve-lens brainstorm, grounded in the datasets already verified in PA-Marine-Model.*

A note on method: these are twelve perspectives argued in turn, not twelve independent
systems. The value is in the friction between them — the operator and the regulator want
opposite things from a false positive, and that tension is where the good ideas came from.

Every idea below names the specific datasets it would use, all of which are already
ingested and schema-verified in this repo. Nothing here requires a new satellite. Where
an idea needs data that is *not* yet present, that is stated explicitly.

---

## The twelve lenses

| # | Lens | The provocation it contributed | Fed idea |
|---|---|---|---|
| 1 | **Killary mussel grower** | "A closure costs me the same whether the bloom was real or not. Tell me *when to harvest*, not what the probability is." | 5 |
| 2 | **Dinophysis ecologist** | "You are modelling a thin sub-surface layer with a skin-temperature product. Dinophysis sits at the pycnocline, not the surface." | 1 |
| 3 | **Physical oceanographer** | "A 0.25° pixel cannot see a fjord. Killary is 300 m wide. You are scoring farms against the open Atlantic." | 1 |
| 4 | **Food-safety regulator (SFPA/FSAI)** | "I cannot act on a probability. I can act on 'sample here next Tuesday'." | 2 |
| 5 | **Statistical methodologist** | "Your label is an OR over whatever got sampled. Fix the sampling design and the model gets easier." | 2 |
| 6 | **Ocean-colour remote sensing** | "Chlorophyll is a biomass proxy, not a species one. Dinophysis blooms at densities invisible to satellite." | 1, 3 |
| 7 | **Sensor engineer** | "You already have four in-situ sites with T/S/DO. That is a training set for everything you cannot measure." | 1 |
| 8 | **Citizen-science lead** | "Growers are on the water daily. They see slicks and mortalities before any lab does." | 2 |
| 9 | **Climate attribution scientist** | "You have a 1711 precipitation series. Almost nobody in HAB forecasting has three centuries of context." | 4 |
| 10 | **Parametric insurance analyst** | "I need a trigger index that is objective, cheap to verify, and hard to game. Closure days are perfect." | 5 |
| 11 | **Coastal community historian** | "Norovirus from oysters closed more beds than algae in some years. Why is only half the hazard modelled?" | 4 |
| 12 | **Marine spatial planner** | "Three national monitoring networks share one shelf and never talk. The water crosses the border; the data does not." | 3 |

---

## Idea 1 — The Virtual Inshore Thermometer

**Downscale offshore SST to the actual water each farm sits in.**

### The problem it solves

This came directly out of the code review. The Irish pipeline snaps each station to
whichever 0.25° OISST pixel contains it. Inshore sites — fjords, bays, harbours — land on
land pixels and get NaN SST for the entire record. The repo already documents one:

> Rosmuc: *"HAB samples present, but OISST SST is null at this pixel (landmask / inshore).
> Scores use week-of-year + lat/lon; SST features missing."*

Killary Harbour is a 16 km fjord roughly 300 m wide. No 0.25° product resolves it. So the
project's central question — does marine heat drive Dinophysis? — is being asked with
temperatures from up to 40 km offshore, or with no temperature at all.

### What it is

A model that predicts **daily inshore water temperature at each farm** from things that
*are* measured everywhere, trained against the handful of sites where inshore truth exists.

**Training truth** (all already ingested):
- `sbe37_macehead` — QC delayed-mode T/S/O₂, ~2018–2022
- `compass_mace_head` — Mace Head NRT, 2018–
- `sentinel_lehanagh` — Lehanagh Pool NRT, May 2024–
- `smartbay_obs_ctd_sbe16`, `spiddal_obs_ctd` — SmartBay/Spiddal CTD T/S/DO

**Predictors** (all already ingested):
- Offshore OISST 0.25° and OSTIA 0.05° at the nearest *ocean* pixel
- Met Éireann Mace Head daily: air temperature, wind, `glorad` (solar radiation)
- River discharge: Shannagurraun (31075, local Connemara), Corrib (30061), Cong Weir (30031)
- Copernicus IBI: `mlotst` (mixed-layer depth), `rsntds` (surface shortwave)
- Tidal phase — derivable from harmonic constants, no new data needed

The physics is tractable: a shallow embayment's temperature is offshore temperature plus
solar heating, minus wind mixing, modified by freshwater stratification and tidal exchange.
Every one of those terms is available.

**Output:** daily inshore SST per station, *with uncertainty*, filling the gap where OISST
returns NaN — plus a stratification proxy from the freshwater and wind terms, which is
what lens 2 actually wants.

### Real-world impact

Roughly one in five Irish HAB stations may currently have unusable SST (the coverage
report added in the review will give the exact number). Fixing that:

- makes the MHW hypothesis genuinely testable for the first time
- gives growers a temperature number that refers to *their* water
- **transfers directly** to every coastal aquaculture region worldwide with the same
  pixel-versus-fjord mismatch — Chile, Norway, British Columbia, Tasmania

### Honest feasibility

Strongest idea here, and the most likely to work. But there are only 3–4 in-situ sites, all
in Connemara. Validate leave-one-buoy-out, and do not claim national coverage from a
Connemara-trained model. A downscaler that works at Mace Head and fails at Bantry is still
useful — but say which.

---

## Idea 2 — The Value-of-Information Sampling Scheduler

**Stop asking "will there be a bloom?" Start asking "where should the boat go on Tuesday?"**

### The problem it solves

The review found that `y_nowcast` is an OR over however many station-weeks happen to be
sampled in a 14-day window. Label prevalence swings from **0.07 to 0.61** purely with
sampling density, and sampling effort is seasonal — which entangles it with the
week-of-year features that dominate the model.

That is a bug in the analysis. It is also a **product**. The monitoring programme already
makes an allocation decision every week under a fixed boat-and-lab budget. Nothing in the
pipeline helps with it.

### What it is

Invert the model. Instead of outputting risk, output **the marginal value of sampling each
station next week**:

1. Current calibrated closure-risk probability per station (existing model)
2. Predictive *uncertainty* per station — widest where risk is near the decision threshold
3. Consequence weight — production tonnage, or the size of the parent closure area from
   `habs_status`
4. Expected reduction in decision error from one more sample there
5. Greedy allocation under next week's actual capacity

The 23-year `habs_phyto` record contains the full sampling history, so the counterfactual
is testable retrospectively: **would this schedule have caught known DSP events earlier
than the schedule actually used?** That is a clean, honest evaluation on data already held.

### Real-world impact

The highest-leverage idea on this list, because it changes a decision that is already
being made rather than adding a dashboard nobody reads.

- **Earlier detection.** DSP causes acute gastrointestinal illness. Days matter.
- **Fewer unnecessary closures.** Blanket precautionary closures cost growers directly;
  better-targeted sampling narrows them.
- **Same budget.** No new boats, no new sensors, no new funding line.
- **It de-confounds the science.** More even coverage weakens the sampling-effort
  confound, which improves every model trained afterwards.

### Honest feasibility

The hard part is institutional, not technical. Statutory minimum sampling exists for good
reason and this must never be framed as "sample less." Frame it strictly as **where to put
the marginal sample above the statutory floor**. Also: lens 8's point deserves a channel —
grower observations of slicks and mortalities are a free, real-time signal with no ingest
path in this repo. A one-tap report form feeding the scheduler is cheap and would probably
outperform some of the physics.

---

## Idea 3 — The Tri-national Advection Early-Warning Graph

**Three countries monitor one shelf and never look at each other's data.**

### The problem it solves

This repo has something genuinely rare: parallel, schema-harmonised phytoplankton panels
for **Ireland** (`habs_phyto`, 207 stations), **Scotland** (SMC/FSS, SIN-level, geocoded),
and **England & Wales** (FSA/Cefas). The hard part — reconciling three schemas, three
taxonomic conventions, three grid systems, OSGB→WGS84 — is already done.

They are not joined. The README says so: *"Not merged into Irish training yet."*

Meanwhile Dinophysis does not respect borders. It advects with the Irish Coastal Current
and the Scottish Coastal Current.

### What it is

Treat the three networks as **one directed spatiotemporal graph**:

- **Nodes** = monitoring sites across all three countries
- **Edges** = residual-current transit time between sites, computed from Copernicus IBI
  `uo`/`vo` surface currents (already ingested)
- **Edge modulation** = ERA5 alongshore wind, which drives downwelling-favourable
  transport (already ingested, with alongshore/crossshore components already derived)

Then the testable question: **does an exceedance upstream predict one downstream, at the
lag the currents imply?** If SW Ireland or the Malin Shelf leads Connemara by 7–14 days
along a physically plausible path, that is real warning lead time.

The falsifiable version matters here: a *physically-implied* lag must outperform an
arbitrary one. If it doesn't, the correlation is shared seasonality, not transport.

### Real-world impact

**Lead time is the whole game.** The current nowcast is essentially concurrent — it tells
you about a bloom you could already sample. A grower given 10 days' notice can harvest
early, relay stock, or halt. A grower told on the day can only stop.

And it turns each country's monitoring investment into a shared asset. Ireland gets early
warning from Scottish sampling it does not pay for, and vice versa.

### Honest feasibility

Scientifically the most interesting, and the most likely to return a **null result**.
Shelf-scale advective connectivity at 1–2 week lags is plausible but unproven for these
species, and the three networks have different thresholds and sampling cadences that could
easily manufacture spurious correlation. Use the diagnostics from the review — permutation
controls and the `station_week` baseline — before believing any of it.

A well-tested null is publishable and would still be a contribution: "national HAB networks
are not advectively predictive of each other at operational lags" is worth knowing.

---

## Idea 4 — The Dual-Hazard Closure Forecast

**Shellfish beds close for two unrelated reasons. Only one is being modelled.**

### The problem it solves

Lens 11's observation, and it is the most under-exploited data in the repo. Shellfish
harvesting closes for:

1. **Biotoxin** — bloom-driven. Warm, stratified, calm. This is what the project models.
2. **Faecal contamination / norovirus** — rainfall-driven. Storms, combined sewer
   overflows, river plumes. **Not modelled at all.**

These have *opposite* weather signatures. A grower facing both needs one combined answer,
and currently gets half of one.

Sitting unused in `data/processed/`: `smc_areas.csv` (Scottish A/B/C sanitary
classifications), `sepa_swpa_centroids.csv` (Scottish Water protected areas),
`smc_closures.csv`. Plus the rainfall machinery is already built — river discharge for
Corrib and Shannagurraun, Met Éireann daily precipitation for five west-coast stations, and
1991–2020 1km normals for anomaly context.

### What it is

A two-channel risk product per harvest area:

- **Channel A (biotoxin):** the existing Dinophysis/DSP model, fixed per the review
- **Channel B (faecal):** rainfall-driven contamination risk from antecedent precipitation,
  river discharge anomaly against 1991–2020 normals, catchment wetness lag (Cong Weir as
  the upper-catchment proxy), and sanitary classification as the static baseline
- **Combined:** probability the area closes *for any reason*, decomposed so the grower
  knows which hazard and therefore what to do — biotoxin means wait for depuration,
  faecal means wait for the plume to flush

### Real-world impact

Norovirus in oysters is a recurring, genuinely serious public-health problem in Europe,
and it is strongly rainfall-linked — which makes it *more* forecastable than biotoxin, not
less. Under climate change, intense-rainfall frequency is rising alongside marine
heatwaves, so both channels are trending the wrong way.

Decomposing the hazard also enables something a single risk score cannot: **targeted rather
than blanket closures.** A rainfall event affects river-influenced beds; a bloom affects
offshore-exposed ones. Different sets.

### Honest feasibility

**The blocker is real and specific: there is no Irish faecal-indicator (E. coli) time
series ingested.** Scottish sanitary classification is annual, not a time series, so it can
only serve as a static prior. Getting the SFPA/Marine Institute *E. coli* monitoring
results is a prerequisite, and I do not know whether they are openly available. Channel B
is unbuildable until that lands — but the rainfall and discharge predictors are all in
place, so it is an ingest problem rather than a modelling one.

---

## Idea 5 — Closure-Day Index for Harvest Timing and Parametric Insurance

**Turn a calibrated probability into a decision, and a decision into a financial product.**

### The problem it solves

Lens 1's complaint: a probability is not actionable. Lens 10's: aquaculture is
under-insured because there is no objective, cheap-to-verify, hard-to-game trigger.

This is where the project's existing calibration work pays off. Isotonic calibration on the
validation split was the right call, and the README is honest that raw probabilities are
over-confident. A *calibrated* probability is exactly what a decision rule and an insurance
trigger both require. An uncalibrated one is worthless for both.

### What it is

**Layer A — harvest timing.** Convert probability into expected value. The grower's
decision is harvest now versus wait, and both have costs: harvesting into an undetected
closure risks destroyed product and reputational damage; waiting risks losing condition,
market window, or the whole season. With a calibrated probability, a cost matrix, and stock
condition, the optimal action is a straightforward expected-value calculation. Output is
"harvest this week" or "wait, re-evaluate Thursday" — not a number.

**Layer B — closure-day index.** A published, area-level count of forecast closure days per
season, built from `habs_status` history. This is a good parametric trigger because it is
objective, independently verifiable from a public regulator feed, and effectively
impossible for either party to manipulate.

**Layer C — the 300-year context.** This is where lens 9's asset comes in. The repo holds
`iip_composite_1711_2016` (Island of Ireland precipitation, 1711–2016),
`island_of_ireland_temperature_annual`, and `iip_national_1850_2010_monthly`. Almost nobody
in HAB forecasting has three centuries of regional climate context. It lets you say how
unusual a June 2023 actually was — which is what both an insurer pricing a novel risk and a
community meeting need to hear.

### Real-world impact

- **Growers** get an action, not a dashboard.
- **Insurers** get a trigger they can underwrite, which is the actual barrier to
  aquaculture parametric cover.
- **Small operators** benefit most. A large firm can absorb a lost harvest; a
  family-run bed cannot. Insurability is a resilience question, not a finance one.
- **Communities** get change communicated in a frame that lands — "the warmest June in
  three centuries of records" rather than "SSTA +2.8 °C".

### Honest feasibility

Layers A and B are buildable now and the repo already has a DSP closure-risk prototype to
extend. **Layer C is the most speculative thing in this document.** The 1711 series is
*terrestrial* and *precipitation-led*; land air temperature is an imperfect proxy for SST,
and the relationship would need calibrating over the modern overlap period with the
uncertainty carried through honestly. Do not let a striking three-century headline outrun
what a land-based proxy can actually support. And Layer A needs real cost numbers from
actual growers — invented ones would make the whole thing theatre.

---

## What I would build first

Ranked by impact per unit of effort, for a 48-hour window:

| Rank | Idea | Effort | Data ready? | Why |
|---|---|---|---|---|
| 1 | **Virtual Inshore Thermometer** (1) | Medium | ✅ all present | Fixes a known live defect; makes the core hypothesis testable; transferable globally |
| 2 | **Sampling Scheduler** (2) | Low | ✅ all present | Changes a decision already being made; retrospectively evaluable; needs no new data |
| 3 | **Harvest Timing, Layers A+B** (5) | Low | ✅ mostly | Extends the existing DSP prototype; makes the calibration work pay off |
| 4 | **Tri-national Graph** (3) | High | ✅ all present | Most scientifically interesting, highest chance of a null |
| 5 | **Dual-Hazard** (4) | Medium | ❌ needs *E. coli* ingest | Best public-health case, but blocked on data |

**For the hackathon specifically:** idea 2. It is the cheapest to demo, it is honest about
uncertainty rather than hiding it, the retrospective evaluation is compelling ("this
schedule would have caught the June 2023 event N days earlier"), and it turns the review's
most awkward finding — the sampling-effort confound — into the product's foundation. Judges
tend to reward that kind of reframing.

**For the paper:** idea 1. It addresses a defect that plausibly explains why the MHW result
came out null, which makes it a genuine scientific contribution rather than an engineering
fix.

---

## Two caveats over the whole document

**These are hypotheses, not results.** Every idea above is stated as something to test.
None has been run. Idea 3 in particular may simply not be true.

**Apply the review patches first.** Four defects in the current pipeline all degrade the
SST/MHW features specifically — the over-counting heatwave detector, the trend-absorbing
climatology threshold, the degrees-not-kilometres pixel selection, and the missing inshore
SST. Building new ideas on top of those would inherit all four. Idea 1 in particular is
partly a fix for the fourth.
