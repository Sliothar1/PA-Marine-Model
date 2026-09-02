from __future__ import annotations

import pandas as pd


def year_split(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """Return split labels from ISO year. Never random."""
    y = df["iso_year"].astype(int)
    tr0, tr1 = cfg["splits"]["train"]
    va0, va1 = cfg["splits"]["val"]
    te = cfg["splits"]["test_from"]
    out = pd.Series("drop", index=df.index)
    out[(y >= tr0) & (y <= tr1)] = "train"
    out[(y >= va0) & (y <= va1)] = "val"
    out[y >= te] = "test"
    return out


def purge_boundary_rows(
    df: pd.DataFrame,
    split: pd.Series,
    label_horizon_days: int = 14,
    week_start_col: str = "week_start",
) -> pd.Series:
    """Drop rows whose label window reaches into the next split.

    `y_<tax>_nowcast` covers [week_start, week_start + 14d], which spans three ISO
    weeks. So a train row dated late December 2018 has a label that ORs in
    observations from January 2019 - the validation period. The last ~2 weeks of
    every split therefore leak labels forward across the boundary. Small in volume
    (roughly 2 boundary weeks x 207 stations x 2 boundaries) but it is genuine
    train-on-future contamination, and the standard fix is to purge the boundary
    rather than argue about the magnitude.

    Returns a copy of `split` with the offending rows relabelled "drop".
    """
    out = split.copy()
    ws = pd.to_datetime(df[week_start_col], utc=True, errors="coerce")
    ws = ws.dt.tz_localize(None).dt.normalize()
    horizon = pd.Timedelta(days=int(label_horizon_days))

    # start date of each downstream split, in temporal order
    order = ["train", "val", "test"]
    starts = {s: ws[split == s].min() for s in order if (split == s).any()}
    for i, s in enumerate(order):
        if s not in starts:
            continue
        later = [starts[t] for t in order[i + 1 :] if t in starts]
        if not later:
            continue
        next_start = min(later)
        if pd.isna(next_start):
            continue
        bad = (split == s) & ((ws + horizon) >= next_start)
        out[bad] = "drop"
    return out
