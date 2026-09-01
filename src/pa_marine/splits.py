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
