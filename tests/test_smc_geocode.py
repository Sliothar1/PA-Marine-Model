import pandas as pd

from pa_marine.smc_geocode import (
    apply_coords_to_panel,
    build_site_coords,
    centroids_from_closures,
    extract_osgb_refs,
    normalize_place_name,
    osgb_refs_centroid,
)


def test_extract_osgb_spaced_and_compact():
    desc = "Area bounded by lines drawn between NM 6490 7268, NM 6494 7200, NM64587179"
    refs = extract_osgb_refs(desc)
    assert "NM64907268" in refs
    assert "NM64947200" in refs
    assert any(r.startswith("NM6458") for r in refs)


def test_extract_osgb_spelve_style():
    desc = "between points NM69653000 to NM 71123000 and extending to MHWS"
    refs = extract_osgb_refs(desc)
    assert "NM69653000" in refs
    assert "NM71123000" in refs


def test_centroid_moidart_ish():
    lon, lat = osgb_refs_centroid(["NM64907268", "NM64947200"])
    assert 56.7 < lat < 56.9
    assert -6.0 < lon < -5.7


def test_normalize_strips_species():
    assert normalize_place_name("Loch Spelve Cockles") == "loch spelve"
    assert "oyster" not in normalize_place_name("Loch Fyne: Ardkinglas Oysters")


def test_build_prefers_osgb_over_sepa():
    sites = pd.DataFrame(
        [
            {
                "Sin": "HL-179-227-13",
                "AreaName": "Loch Moidart",
                "SiteName": "South Channel",
            }
        ]
    )
    closures = pd.DataFrame(
        [
            {
                "AreaName": "Loch Moidart",
                "Description": "between NM 6490 7268, NM 6494 7200",
                "Sin": "HL-179-227-13",
            }
        ]
    )
    sepa = pd.DataFrame(
        [
            {
                "site": "Loch Moidart, South Channel",
                "latitude": 56.8,
                "longitude": -5.85,
                "pa_id": "SWPA1",
                "name_norm": "loch moidart south channel",
            }
        ]
    )
    coords = build_site_coords(sites, closures=closures, sepa=sepa, use_nominatim=False)
    assert coords.iloc[0]["source"] == "osgb_closure"
    assert coords.iloc[0]["confidence"] == "high"


def test_apply_coords_sets_has_coords():
    panel = pd.DataFrame(
        {
            "Sin": ["A-1", "A-2"],
            "latitude": [None, None],
            "longitude": [None, None],
            "has_coords": [False, False],
        }
    )
    coords = pd.DataFrame(
        [
            {
                "Sin": "A-1",
                "AreaName": "X",
                "SiteName": "",
                "latitude": 57.0,
                "longitude": -6.0,
                "source": "sepa_swpa",
                "confidence": "high",
            }
        ]
    )
    out = apply_coords_to_panel(panel, coords)
    assert bool(out.loc[out.Sin == "A-1", "has_coords"].iloc[0]) is True
    assert bool(out.loc[out.Sin == "A-2", "has_coords"].iloc[0]) is False


def test_centroids_from_closures_table():
    clos = pd.DataFrame(
        [
            {
                "AreaName": "Loch Beag",
                "Description": "between NM 7223 8370 and NM 7200 8319",
                "Sin": "HL-118-215-08",
            }
        ]
    )
    c = centroids_from_closures(clos)
    assert len(c) == 1
    assert c.iloc[0]["source"] == "osgb_closure"
