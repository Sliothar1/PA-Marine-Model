# Ocean Hackathon® data rules — Cork now / Brest later

**Policy flag from Marine Legal Policy (not formal counsel).**  
**Sources:** [Campus Mer data page](https://www.campusmer.fr/data-4187-0-0-0.html) · [OH 2026 rules EN §5.1](https://www.campusmer.fr/files/5142/rules-of-ocean-hackathon-2026.pdf) · [Sextant OH catalogues](https://sextant.ifremer.fr/eng/Ressources/List-of-thematic-catalogues/Ocean-Hackathon)

## Event data rules (locked)

1. Use rights = per **licence in each dataset’s metadata** — access ≠ ownership.
2. Authorisation for organiser-supplied / derived data is **limited to the Ocean Hackathon® period**; use **outside** the event needs **prior written agreement** with the rights holder.
3. Exception: may keep using data to **develop projects designed during the event**, **excluding commercial exploitation**, still subject to that dataset’s licence.
4. Third-party code/libs in the jury submission must list version + licence.
5. Some OH datasets are **not normally free** — treat Sextant weekend-only layers as event-scoped, not a permanent open dump.
6. Sextant: OH thematic fiches often **visible only for the weekend** (except already-public Sextant records). Datarmor used historically for some bulk (~TB).

## 2026 partner stores — what we lean on

### Always-open / our spine (don’t wait for Sextant weekend)

- Copernicus Marine + Mercator + WEkEO (SST/OC — attribution)
- **Ifremer** path → REPHY/REPHYTOX SEANOE (often CC-BY), Surval/Quadrige — cleanest **Biscay v0** lane
- ODATIS (French ocean observation hub)
- EMODnet free layers
- **Ireland spine:** MI HAB, Met Éireann (CC-BY), Copernicus, MBA CPR (**NC-local** — see `CPR_MBA.md` §6)

### Useful context (check metadata each time)

- EUMETSAT OSI SAF (SST/winds)
- Shom (hydro/coastal GIS — not navigation claims)
- Météo-France (French Met — not Irish Met; Climate Drivers stays on Met Éireann for IE)

### Usually off HAB spine / careful

- Cerema + Le Havre/AISHub (AIS — separate licence)
- Global Fishing Watch (own ToS)
- EMBRC/EMO BON (omics)
- OFB / PatriNat (biodiversity policy)
- Ocean Networks Canada (Oceans 3.0 — Victoria track, not Biscay Dinophysis)
- IHO: standards/ambassador — GEBCO etc. under their own terms if used

## PA actions

| When | Do |
| --- | --- |
| **Cork** | Build on **pre-cleared open feeds** only. Don’t bank the pitch on OH-weekend-only Sextant layers. |
| **Brest** | Sextant scavenger list (Ifremer/REPHY/Surval, CMEMS, ODATIS) + read each metadata licence before mirror; hackathon-only stays out of public GitHub / commercial path unless rights holder writes OK. |
| **Jury pack** | Attribute every feed; list third-party code licences + versions. |

**@International HAB Dev / @Atlantic Neighbours:** REPHY-first remains the cleanest Biscay lane under these rules.
