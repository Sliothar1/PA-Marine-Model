"""Nearest-ocean pixel selection and SST coverage reporting.

Pixel selection previously used Euclidean distance in degrees, which treats 1 deg of
longitude as costing the same as 1 deg of latitude. At Irish latitudes 1 deg of
longitude is ~66 km against ~111 km for latitude, so that metric over-penalises
east-west displacement by ~1.7x and can select a pixel materially farther away than
one it rejects.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pa_marine.erddap import lon_to_oisst_360
from pa_marine.sst import (
    haversine_km,
    map_stations_to_nearest_oisst_ocean,
    sst_coverage_report,
)

KILLARY_LAT, KILLARY_LON = 53.61472, -9.83306  # real Killary Outer coordinates


# ------------------------------------------------------------------- haversine


@pytest.mark.parametrize(
    "a, b, expected_km, tol",
    [
        ((53.5, 0.0), (54.5, 0.0), 111.2, 0.5),   # one degree of latitude
        ((53.5, 0.0), (53.5, 1.0), 66.1, 0.5),    # one degree of longitude at 53.5N
        ((53.35, -6.26), (53.27, -9.05), 186.0, 3.0),  # Dublin - Galway
        ((0.0, 0.0), (0.0, 1.0), 111.2, 0.5),     # one degree of longitude at equator
    ],
)
def test_haversine_known_distances(a, b, expected_km, tol):
    assert haversine_km(a[0], a[1], b[0], b[1]) == pytest.approx(expected_km, abs=tol)


def test_haversine_zero_and_symmetric_and_vectorised():
    assert haversine_km(53.5, -9.8, 53.5, -9.8) == pytest.approx(0.0, abs=1e-9)
    assert haversine_km(53.5, -9.8, 54.0, -9.0) == pytest.approx(
        haversine_km(54.0, -9.0, 53.5, -9.8), abs=1e-9
    )
    out = haversine_km(53.5, -9.8, np.array([53.5, 54.5]), np.array([-9.8, -9.8]))
    assert out.shape == (2,)
    assert out[0] == pytest.approx(0.0, abs=1e-9)
    assert out[1] == pytest.approx(111.2, abs=0.5)


def test_longitude_costs_less_than_latitude_at_irish_latitudes():
    """The whole point of the fix: a degree of longitude is not a degree of latitude."""
    lat_deg = haversine_km(53.5, 0.0, 54.5, 0.0)
    lon_deg = haversine_km(53.5, 0.0, 53.5, 1.0)
    assert lon_deg / lat_deg == pytest.approx(0.595, abs=0.01)


# --------------------------------------------------------- nearest ocean pixel


def test_picks_true_nearest_when_metrics_disagree():
    """dlat < dlon < 1.68*dlat is where degrees and km give different answers.

    0.50 deg north vs 0.75 deg west: degrees prefers north, km prefers west.
    """
    lon360 = lon_to_oisst_360(KILLARY_LON)
    north = {"grid_lat": 54.125, "grid_lon": lon_to_oisst_360(-9.875), "sst": 11.0}
    west = {"grid_lat": 53.625, "grid_lon": lon_to_oisst_360(-10.625), "sst": 11.0}
    cube = pd.DataFrame([north, west])

    d_deg_north = np.hypot(north["grid_lat"] - KILLARY_LAT, north["grid_lon"] - lon360)
    d_deg_west = np.hypot(west["grid_lat"] - KILLARY_LAT, west["grid_lon"] - lon360)
    d_km_north = haversine_km(KILLARY_LAT, lon360, north["grid_lat"], north["grid_lon"])
    d_km_west = haversine_km(KILLARY_LAT, lon360, west["grid_lat"], west["grid_lon"])
    assert d_deg_north < d_deg_west, "degrees should prefer north (the wrong answer)"
    assert d_km_west < d_km_north, "km should prefer west (the right answer)"

    st = pd.DataFrame(
        [{"location_id": "killary", "latitude": KILLARY_LAT, "longitude": KILLARY_LON}]
    )
    got = map_stations_to_nearest_oisst_ocean(st, cube)
    assert got["grid_lat"].iloc[0] == pytest.approx(west["grid_lat"])
    assert got["dist_km"].iloc[0] == pytest.approx(d_km_west, abs=0.1)


def test_land_pixels_are_excluded_from_selection():
    """NaN-SST pixels are land; a nearer land pixel must not win."""
    lon360 = lon_to_oisst_360(KILLARY_LON)
    cube = pd.DataFrame(
        [
            {"grid_lat": 53.625, "grid_lon": lon360, "sst": np.nan},          # on top, land
            {"grid_lat": 53.625, "grid_lon": lon360 - 0.5, "sst": 11.0},      # ocean
        ]
    )
    st = pd.DataFrame(
        [{"location_id": "x", "latitude": KILLARY_LAT, "longitude": KILLARY_LON}]
    )
    got = map_stations_to_nearest_oisst_ocean(st, cube)
    assert len(got) == 1
    assert got["grid_lon"].iloc[0] == pytest.approx(lon360 - 0.5)


def test_distance_gate_is_in_km_and_rejects_far_pixels():
    lon360 = lon_to_oisst_360(KILLARY_LON)
    cube = pd.DataFrame([{"grid_lat": 53.625, "grid_lon": lon360 - 2.0, "sst": 11.0}])
    st = pd.DataFrame(
        [{"location_id": "x", "latitude": KILLARY_LAT, "longitude": KILLARY_LON}]
    )
    assert map_stations_to_nearest_oisst_ocean(st, cube, max_dist_km=60.0).empty
    kept = map_stations_to_nearest_oisst_ocean(st, cube, max_dist_km=200.0)
    assert len(kept) == 1 and kept["dist_km"].iloc[0] > 60.0


def test_legacy_max_dist_deg_still_accepted():
    lon360 = lon_to_oisst_360(KILLARY_LON)
    cube = pd.DataFrame([{"grid_lat": 53.625, "grid_lon": lon360 - 0.25, "sst": 11.0}])
    st = pd.DataFrame(
        [{"location_id": "x", "latitude": KILLARY_LAT, "longitude": KILLARY_LON}]
    )
    assert len(map_stations_to_nearest_oisst_ocean(st, cube, max_dist_deg=1.0)) == 1


def test_empty_cube_returns_empty_frame_with_dist_km():
    st = pd.DataFrame([{"location_id": "x", "latitude": 53.6, "longitude": -9.8}])
    out = map_stations_to_nearest_oisst_ocean(st, pd.DataFrame({"grid_lat": [], "grid_lon": [], "sst": []}))
    assert out.empty
    assert "dist_km" in out.columns


# ------------------------------------------------------------ coverage report


def test_coverage_report_flags_land_snapped_and_thin_stations(capsys):
    d = pd.date_range("2015-01-01", periods=400)
    rng = np.random.default_rng(0)
    frames = []
    for loc, finite in [("good", 1.0), ("ok", 0.98), ("land", 0.0), ("thin", 0.3)]:
        sst = np.where(rng.random(len(d)) < finite, 11.0, np.nan)
        frames.append(pd.DataFrame({"location_id": loc, "date": d, "sst": sst}))
    rep = sst_coverage_report(pd.concat(frames), label="TEST")

    assert set(rep["location_id"]) == {"good", "ok", "land", "thin"}
    assert rep.loc[rep.location_id == "land", "n_finite"].iloc[0] == 0
    assert rep.loc[rep.location_id == "good", "finite_frac"].iloc[0] == pytest.approx(1.0)

    out = capsys.readouterr().out
    assert "NO finite SST" in out and "land" in out
    assert "below 50%" in out and "thin" in out


def test_coverage_report_quiet_when_all_stations_fine(capsys):
    d = pd.date_range("2015-01-01", periods=50)
    df = pd.DataFrame({"location_id": "a", "date": d, "sst": 11.0})
    sst_coverage_report(df, label="TEST")
    assert "usable SST coverage" in capsys.readouterr().out


def test_coverage_report_handles_empty_frame(capsys):
    assert sst_coverage_report(pd.DataFrame(), label="TEST").empty
    assert "nothing to report" in capsys.readouterr().out
