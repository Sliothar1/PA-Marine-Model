"""HAB labels from Marine Institute habs_phyto tabledap."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def download_hab(cfg: dict[str, Any], out_path: str | None = None) -> pd.DataFrame:
    from pa_marine.erddap import tabledap_csv

    hab = cfg["hab"]
    dom = cfg["domain"]
    constraints = [
        f"latitude>={dom['lat_min']}",
        f"latitude<={dom['lat_max']}",
        f"longitude>={dom['lon_min']}",
        f"longitude<={dom['lon_max']}",
    ]
    df = tabledap_csv(hab["erddap_base"], hab["dataset_id"], hab["columns"], constraints)
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce")
    if out_path:
        df.to_csv(out_path, index=False)
    return df


def _match_names(names: pd.Series, needles: list[str]) -> pd.Series:
    s = names.fillna("").astype(str)
    mask = pd.Series(False, index=s.index)
    for n in needles:
        mask = mask | s.str.contains(n, case=False, regex=False)
    return mask


def station_week_panel(hab: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Aggregate to station × ISO-week with max count per taxon group.

    Station key is location_id (verified ERDDAP column). ISO week is Monday-based
    from sample time (ISO-8601), not the source week_no string.
    """
    df = hab.copy()
    df = df.dropna(subset=["time", "location_id"])
    iso = df["time"].dt.isocalendar()
    df["iso_year"] = iso.year.astype(int)
    df["iso_week"] = iso.week.astype(int)
    # monday ISO week start
    # Monday of ISO week
    df["week_start"] = df["time"].dt.tz_convert("UTC") - pd.to_timedelta(df["time"].dt.dayofweek, unit="D")
    df["week_start"] = df["week_start"].dt.normalize()

    taxa = cfg["hab"]["taxa"]
    rows = []
    keys = ["location_id", "iso_year", "iso_week", "week_start"]
    meta = (
        df.groupby(keys, as_index=False)
        .agg(
            latitude=("latitude", "median"),
            longitude=("longitude", "median"),
            location_name=("location_name", "first") if "location_name" in df.columns else ("location_id", "first"),
            n_samples=("count", "size"),
        )
    )
    for tax_id, spec in taxa.items():
        m = _match_names(df["scientific_name"], spec["name_contains"])
        g = (
            df.loc[m]
            .groupby(keys, as_index=False)["count"]
            .max()
            .rename(columns={"count": f"count_{tax_id}"})
        )
        meta = meta.merge(g, on=keys, how="left")
        meta[f"count_{tax_id}"] = meta[f"count_{tax_id}"].fillna(0.0)
    return meta.sort_values(keys).reset_index(drop=True)


def resolve_thresholds(panel: pd.DataFrame, cfg: dict[str, Any], train_mask: pd.Series) -> dict[str, float]:
    """Fixed thresholds plus Karenia 95th percentile of *positive* counts on train."""
    out = {}
    for tax_id, spec in cfg["hab"]["taxa"].items():
        col = f"count_{tax_id}"
        if spec.get("threshold_mode") == "positive_percentile":
            pos = panel.loc[train_mask, col]
            pos = pos[pos > 0]
            p = float(spec.get("percentile", 95))
            if len(pos) >= 10:
                thr = float(np.nanpercentile(pos, p))
            else:
                thr = float(spec.get("threshold_cells_l", 1000.0))
            out[tax_id] = thr
        else:
            out[tax_id] = float(spec["threshold_cells_l"])
    return out


def add_binary_labels(panel: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    out = panel.copy()
    for tax_id, thr in thresholds.items():
        out[f"y_{tax_id}"] = (out[f"count_{tax_id}"] >= thr).astype(int)
    return out


def add_horizon_labels(
    panel: pd.DataFrame,
    tax_ids: list[str],
    nowcast=(0, 14),
    ahead=(7, 14),
    add_coverage: bool = True,
) -> pd.DataFrame:
    """For each station, rolling-or of y in future windows measured in days from week_start.

    Also emits `n_obs_<tax>_<horizon>`: how many *sampled* station-weeks fell inside the
    label window. This matters because HAB sampling is irregular, so the label is an OR
    over however many samples happen to exist in the window. A station-week whose window
    contains three samples has three chances to be positive; one with a single sample has
    one. Sampling effort is itself seasonal and station-specific, so it correlates with
    the week-of-year and lat/lon features that dominate the model - part of the apparent
    skill may be the model learning *when people sample* rather than when blooms occur.
    Use these columns to restrict to fully-observed windows or to stratify metrics by
    coverage before quoting a skill number.

    Vectorised via searchsorted over each station's sorted week starts: O(k log k) per
    station instead of the previous O(k^2) pairwise date-difference scan.
    """
    out = panel.sort_values(["location_id", "week_start"]).copy()
    windows = {"nowcast": nowcast, "ahead7": ahead}
    pieces = []
    for _, g in out.groupby("location_id", sort=False):
        g = g.copy()
        ws = pd.to_datetime(g["week_start"], utc=True).dt.tz_localize(None).dt.normalize()
        # integer days since epoch, ascending (groupby preserves the outer sort)
        d = (ws.to_numpy().astype("datetime64[D]") - np.datetime64("1970-01-01")).astype(np.int64)
        for name, (lo, hi) in windows.items():
            left = np.searchsorted(d, d + lo, side="left")
            right = np.searchsorted(d, d + hi, side="right")
            n_obs = (right - left).astype(int)
            for tax in tax_ids:
                y = g[f"y_{tax}"].to_numpy()
                cs = np.concatenate([[0], np.cumsum(y)])
                g[f"y_{tax}_{name}"] = ((cs[right] - cs[left]) > 0).astype(int)
                if add_coverage:
                    g[f"n_obs_{tax}_{name}"] = n_obs
        pieces.append(g)
    return pd.concat(pieces, ignore_index=True)
