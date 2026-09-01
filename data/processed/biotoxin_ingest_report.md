# National biotoxin / harvest-status ingest

Source: Marine Institute ERDDAP `erddap3.marine.ie` — `habs_biotoxin`, `habs_biotoxin_pivot`, `habs_status`.
Schemas verified via `info.json` before download (see `data/raw/erddap_info/`).

## Ingested

| Dataset | Rows |
| --- | ---: |
| habs_biotoxin_pivot (CSV) | 81836 |
| habs_biotoxin long-form | 222519 |
| habs_status | 62544 |
| toxin station-weeks | 48818 (154 locations) |
| status area-weeks | 85734 (161 parent areas) |
| time span (toxin weeks) | 2001-12-24 00:00:00+00:00 → 2026-04-20 00:00:00+00:00 |

## Exceedance / closed rates (station-week)

- DSP exceed: **0.03326641812446229**
- ASP exceed: 0.02015649965176779
- AZP exceed: 0.03050104469662829
- PSP exceed: 0.00047113769511245853
- any toxin exceed: 0.07874144782662133
- closed among status-matched weeks: 0.3000392505216188 (match frac 0.9915809742308165)

**Toxin target usable:** `True` — DSP exceedance rate=0.0333; measured_dsp=0.976. Usable if national coverage, non-degenerate positive rate, and DSP often measured.

## SST / MHW join

- Join key: `location_id (int) + week_start / ISO week`
- Toxin ∩ MHW locations: **128** / 154 toxin (phyto overlap 128)
- SST join works: `True`
- Joined toxin×SST rows: 48158 (SST coverage 0.3145894763071556)
- Status key caveat: parent_area_name (string) + ISO week — no lat/lon/location_id on habs_status
- Note: SST/MHW daily features were built on phyto location_ids. Toxin sites that appear in phyto share the same location_id and join cleanly; toxin-only sites need new OISST pixel pulls.

**SST coverage caveat:** OISST often land-masks nearshore pixels; existing `mhw_daily` SST non-null rate is ~40% (phyto joined ~40%). Toxin joined SST coverage ~31% is the same join key working with slightly worse coastal sampling — not a broken key. 26 toxin-only `location_id`s lack MHW rows until new OISST pixels are pulled.

## Dinophysis cells vs DSP toxin

- Overlapping station-weeks (DSP measured): **25071** (116 shared locations; location_id overlap 128)
- Phyto positive rate: 0.0567; DSP exceed rate: 0.0420
- Confusion TP/FP/FN/TN: 402/651/1019/22999
- Agreement rate: 0.933; Pearson(binary): 0.2943776820510271
- Recall of DSP given phyto+: 0.282899366643209; precision DSP: 0.3817663817663818
- Spearman(count_dinophysis, max_dsp): 0.298 (Pearson 0.13889196912588217)

Raw CSVs are gitignored under `data/raw/`. Summaries committed.
