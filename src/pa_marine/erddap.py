"""Minimal ERDDAP tabledap / griddap client.

Column names are never guessed: callers pass variables verified from info.json.
"""
from __future__ import annotations

from io import StringIO
from typing import Iterable
from urllib.parse import quote

import pandas as pd
import requests


class ErddapError(RuntimeError):
    pass


def _get(url: str, timeout: int = 180) -> str:
    r = requests.get(url, timeout=timeout)
    if r.status_code != 200:
        raise ErddapError(f"HTTP {r.status_code} for {url[:180]}\n{r.text[:500]}")
    return r.text


def tabledap_csv(
    base: str,
    dataset_id: str,
    variables: Iterable[str],
    constraints: Iterable[str] | None = None,
    timeout: int = 300,
) -> pd.DataFrame:
    """Fetch tabledap CSV. Constraints must already be URL-safe except we encode them.

    ERDDAP/Tomcat rejects unencoded '>' '<' in the request target. All operators
    are percent-encoded.
    """
    vars_part = ",".join(variables)
    url = f"{base.rstrip('/')}/tabledap/{dataset_id}.csv?{quote(vars_part, safe=',_()')}"
    if constraints:
        extra = "&".join(quote(c, safe="=,&()_'\"") for c in constraints)
        # encode comparison operators that Tomcat rejects
        extra = (
            extra.replace(">=", "%3E%3D")
            .replace("<=", "%3C%3D")
            .replace(">", "%3E")
            .replace("<", "%3C")
        )
        url = f"{url}&{extra}"
    text = _get(url, timeout=timeout)
    df = pd.read_csv(StringIO(text), skiprows=[1] if _has_units_row(text) else None)
    return df


def griddap_csv(
    base: str,
    dataset_id: str,
    query: str,
    timeout: int = 300,
) -> pd.DataFrame:
    """query is the ERDDAP griddap expression after '?' (already encoded or safe)."""
    url = f"{base.rstrip('/')}/griddap/{dataset_id}.csv?{query}"
    text = _get(url, timeout=timeout)
    return pd.read_csv(StringIO(text), skiprows=[1] if _has_units_row(text) else None)


def _has_units_row(text: str) -> bool:
    lines = text.splitlines()
    return len(lines) >= 2 and ("," in lines[1]) and not lines[1].split(",")[0].strip()[:1].isdigit()


def lon_to_oisst_360(lon: float) -> float:
    """Map geographic longitude (−180…180) to OISST 0…360."""
    return lon + 360.0 if lon < 0 else lon
