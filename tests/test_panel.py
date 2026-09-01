from pathlib import Path

import pandas as pd

from pa_marine.config import load_config
from pa_marine.features import feature_columns, join_week_panel
from pa_marine.hab import add_binary_labels, add_horizon_labels, resolve_thresholds, station_week_panel
from pa_marine.mhw import mhw_for_stations
from pa_marine.splits import year_split


FIXTURE = Path(__file__).parent / "fixtures"


def test_station_week_and_labels():
    cfg = load_config()
    hab = pd.read_csv(FIXTURE / "tiny_hab.csv")
    hab["time"] = pd.to_datetime(hab["time"], utc=True)
    panel = station_week_panel(hab, cfg)
    assert panel["location_id"].nunique() == 2
    split = year_split(panel, cfg)
    assert (split == "train").any()
    thr = resolve_thresholds(panel, cfg, split == "train")
    assert thr["dinophysis"] == 100.0
    assert thr["pseudo_nitzschia"] == 50000.0
    assert "karenia_mikimotoi" in thr
    panel = add_binary_labels(panel, thr)
    panel = add_horizon_labels(panel, list(thr))
    assert "y_dinophysis_nowcast" in panel.columns
    assert panel["y_dinophysis"].max() == 1


def test_join_offline():
    cfg = load_config()
    hab = pd.read_csv(FIXTURE / "tiny_hab.csv")
    hab["time"] = pd.to_datetime(hab["time"], utc=True)
    panel = station_week_panel(hab, cfg)
    sst = pd.read_csv(FIXTURE / "tiny_sst.csv")
    mhw = mhw_for_stations(sst, cfg)
    joined = join_week_panel(panel, mhw)
    cols = feature_columns(joined)
    assert any(c.startswith("sst") for c in cols)
    assert "woy_sin" in cols
    assert "latitude" in cols
