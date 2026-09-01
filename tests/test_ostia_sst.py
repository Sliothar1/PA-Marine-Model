"""OSTIA helpers (no network)."""
from __future__ import annotations

import pandas as pd
import pytest

from pa_marine.sst import snap_ostia, download_sst_for_stations


def test_snap_ostia_grid():
    assert abs(snap_ostia(51.47, origin=-89.975, step=0.05) - 51.475) < 1e-6
    assert abs(snap_ostia(-9.71, origin=-179.975, step=0.05) - (-9.725)) < 1e-6


def test_download_dispatch_ostia(monkeypatch):
    cfg = {
        "sst": {"provider": "ncdcOisst21Agg", "copernicus_ostia": {"enabled": True}},
        "domain": {"lat_min": 51, "lat_max": 56, "lon_min": -11, "lon_max": -5},
    }
    stations = pd.DataFrame(
        {"location_id": [1], "latitude": [51.5], "longitude": [-9.5]}
    )
    called = {}

    def fake_ostia(stations, cfg, t0, t1, max_stations=None):
        called["ok"] = (t0, t1, max_stations)
        return pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01"]),
                "sst": [12.0],
                "anom": [float("nan")],
                "grid_lat": [51.475],
                "grid_lon": [-9.525],
                "location_id": [1],
                "request_lat": [51.5],
                "request_lon": [-9.5],
            }
        )

    monkeypatch.setattr("pa_marine.sst.download_ostia_for_stations", fake_ostia)
    out = download_sst_for_stations(stations, cfg, "2020-01-01", "2020-01-02", provider="ostia")
    assert called["ok"] == ("2020-01-01", "2020-01-02", None)
    assert len(out) == 1 and float(out["sst"].iloc[0]) == 12.0
