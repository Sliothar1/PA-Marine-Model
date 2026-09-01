# Scotland SMC site geocoding

Generated: 2026-09-01 19:38 IST (Europe/Dublin).

## Coverage

- Panel SINs with coords: **131/131** (100.0%)
- Panel rows with coords: **21417/21417** (100.0%)
- By source: `{'nominatim': 39, 'osgb_closure': 14, 'sepa_swpa': 78}`
- By confidence: `{'high': 48, 'low': 35, 'medium': 48}`
- Missing panel SINs: **0**

### Honest confidence split

- **high** (OSGB closures + exact SEPA): **48/131** SINs
- **medium** (SEPA fuzzy / solid Nominatim): **48**
- **low** (ambiguous Nominatim / island fallbacks): **35** — treat cautiously for SST joins

## Sources

1. **osgb_closure** — OSGB grid refs parsed from `smc_closures.csv` Description → WGS84 mean (high).
2. **sepa_swpa** — SEPA Shellfish Water Protected Areas centroids (public ArcGIS REST; name/alias match).
3. **nominatim** — OpenStreetMap Nominatim with LocalAuthority/region fallbacks (rate-limited).

**FSS GIS:** Marine Scotland GeoServer layer nmp:fss_shellfish_classified_areas is OGL-licensed but HTTP 401 without login — not used.

## Caveats

- Many Scottish loch / voe / bay names are ambiguous; Nominatim often returns a plausible but non-unique hit → `confidence=low`.
- Closure OSGB polygons cover only recent closed areas (small subset).
- SEPA SWPAs are designated waters, not 1:1 with FSS production-area SINs.
- Some SEPA published lat/lon values were corrupt (lon copied from lat); recomputed from OSGB easting/northing.
- `North Bay Oysters - Hoy` uses Hoy island centroid (low).

## Rebuild

```bash
python scripts/geocode_smc_sites.py
```
