from pa_marine.mhw import detect_mhw
import pandas as pd
import numpy as np


def _series_with_spike(spike_slice, n_years=20):
    dates = pd.date_range("1985-01-01", periods=365 * n_years, freq="D")
    sst = np.full(len(dates), 10.0)
    sst[spike_slice] = 20.0
    return dates, sst


def test_hobday_detects_five_day_event():
    # Spike in a long baseline so the 90th-pctl climatology stays near 10 C.
    dates, sst = _series_with_spike(slice(200, 208))
    df = detect_mhw(dates, sst, min_duration=5, max_gap=2, percentile=90, doy_window=11)
    assert df["in_mhw"].sum() >= 5
    assert df.loc[df["in_mhw"] == 1, "mhw_duration"].max() >= 5
    assert df.loc[df["in_mhw"] == 1, "mhw_cum_intensity"].max() > 0


def test_short_spike_not_mhw():
    dates, sst = _series_with_spike(slice(200, 203))
    df = detect_mhw(dates, sst, min_duration=5, max_gap=2, percentile=90, doy_window=11)
    assert int(df["in_mhw"].sum()) == 0


def test_two_day_gap_merged():
    dates = pd.date_range("1985-01-01", periods=365 * 20, freq="D")
    sst = np.full(len(dates), 10.0)
    sst[200:206] = 20.0
    sst[206:208] = 10.0
    sst[208:214] = 20.0
    df = detect_mhw(dates, sst, min_duration=5, max_gap=2, percentile=90, doy_window=11)
    assert df["in_mhw"].iloc[200:214].min() == 1


def test_rich_mhw_intensity_and_category():
    dates, sst = _series_with_spike(slice(200, 220))
    df = detect_mhw(dates, sst, min_duration=5, max_gap=2, percentile=90, doy_window=11)
    assert "mhw_intensity" in df.columns
    assert "mhw_max_intensity" in df.columns
    assert "mhw_category" in df.columns
    assert "days_since_mhw" in df.columns
    assert "ssta_pctile" in df.columns
    assert "mhw_i_ratio" in df.columns
    in_evt = df["in_mhw"] == 1
    assert (df.loc[in_evt, "mhw_intensity"] > 0).all()
    assert (df.loc[in_evt, "mhw_category"] >= 1).all()
    assert (df.loc[in_evt, "days_since_mhw"] == 0).all()
    # after event, days_since should increase
    last_idx = df.index[in_evt][-1]
    after = df.loc[last_idx + 1 : last_idx + 5, "days_since_mhw"]
    assert list(after) == [1.0, 2.0, 3.0, 4.0, 5.0]
