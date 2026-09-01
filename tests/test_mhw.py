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
