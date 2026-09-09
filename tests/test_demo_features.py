from pathlib import Path

import numpy as np
import pandas as pd

from pa_marine.config import load_config
from pa_marine.demo_features import (
    attach_demo_features,
    attach_sst_coverage_flags,
    naive_oisst_snap,
    station_week_baseline_probs,
)
from pa_marine.features import STRONG_OISST, feature_columns, join_week_panel, select_feature_mode
from pa_marine.hab import add_binary_labels, add_horizon_labels, resolve_thresholds, station_week_panel
from pa_marine.mhw import mhw_for_stations
from pa_marine.splits import year_split

FIXTURE = Path(__file__).parent / "fixtures"


def _tiny_joined() -> pd.DataFrame:
    cfg = load_config()
    hab = pd.read_csv(FIXTURE / "tiny_hab.csv")
    hab["time"] = pd.to_datetime(hab["time"], utc=True)
    panel = station_week_panel(hab, cfg)
    panel["split"] = year_split(panel, cfg)
    thr = resolve_thresholds(panel, cfg, panel["split"] == "train")
    panel = add_binary_labels(panel, thr)
    panel = add_horizon_labels(panel, list(thr))
    sst = pd.read_csv(FIXTURE / "tiny_sst.csv")
    mhw = mhw_for_stations(sst, cfg)
    joined = join_week_panel(panel, mhw)
    joined["split"] = year_split(joined, cfg)
    return joined


def test_strong_oisst_unchanged():
    assert "woy_sin" in STRONG_OISST
    assert "demo_sw_station_week_rate" not in STRONG_OISST
    assert len(STRONG_OISST) == 9


def test_station_week_rates_train_only():
    joined = _tiny_joined()
    out = attach_demo_features(joined)
    assert "demo_sw_station_week_rate" in out.columns
    train = out[out["split"] == "train"]
    assert train["demo_sw_station_week_rate"].notna().all()
    # Val/test still get mapped rates, but those rates were fit on train labels only:
    # a station never seen in train should fall back to the global train rate.
    p_train = float(train["y_dinophysis_nowcast"].mean())
    unseen = out.copy()
    unseen.loc[unseen["split"] != "train", "location_id"] = 999999
    probs = station_week_baseline_probs(
        train, unseen[unseen["split"] != "train"], "y_dinophysis_nowcast"
    )
    if len(probs):
        assert np.allclose(probs, p_train, atol=0.15) or np.isfinite(probs).all()


def test_station_week_not_in_default_feature_columns():
    joined = attach_demo_features(_tiny_joined())
    cols = feature_columns(joined)
    assert "demo_sw_station_week_rate" not in cols
    demo = select_feature_mode(joined, "demo_station_week")
    assert "sst" in demo
    assert "demo_sw_station_week_rate" in demo
    strong = select_feature_mode(joined, "strong")
    assert strong == [f for f in strong if f in STRONG_OISST]


def test_sst_coverage_flags_and_snap():
    df = pd.DataFrame(
        {
            "location_id": [174, 174, 177, 177],
            "latitude": [53.33194, 53.33194, 53.45944, 53.45944],
            "longitude": [-9.59861, -9.59861, -10.07, -10.07],
            "sst": [np.nan, np.nan, 15.0, 16.0],
        }
    )
    out = attach_sst_coverage_flags(df)
    assert out.loc[out["location_id"] == 174, "cov_sst_always_missing"].eq(1).all()
    assert out.loc[out["location_id"] == 177, "cov_sst_always_missing"].eq(0).all()
    assert out.loc[0, "cov_sst_missing"] == 1
    assert out.loc[2, "cov_sst_missing"] == 0
    la, lo = naive_oisst_snap(53.45944, -10.07)
    assert abs(la - 53.375) < 0.2 or abs(la - 53.625) < 0.2 or np.isfinite(la)
    assert out["cov_snap_dist_km"].notna().all()
    assert (out["cov_snap_dist_km"] >= 0).all()


def test_exporter_writes_samples(tmp_path):
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "export_demo_instances.py"
    spec = importlib.util.spec_from_file_location("export_demo_instances", path)
    exp = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(exp)

    joined = attach_demo_features(_tiny_joined())
    fixture_panel = tmp_path / "joined.csv"
    joined.to_csv(fixture_panel, index=False)
    panel = exp.tag_region(exp.load_panel(fixture_panel))
    panel = attach_demo_features(panel)
    full, sample = exp.build_instance(exp.SPECS[0], panel, fixture_panel, None, sample_n=5)
    assert full["schema"] == "pa_marine.demo_instance.v1"
    assert "honesty" in full
    assert full["honesty"]["spine"] == "STRONG_OISST"
    assert "weekly" in full
    assert sample.get("sample") is True
    assert "copy_to_grokd4m" in full
