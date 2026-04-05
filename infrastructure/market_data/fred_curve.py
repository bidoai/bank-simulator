"""
FRED rate curve fetcher.

Pulls the latest UST constant-maturity yields and SOFR from the St. Louis
Fed FRED public CSV endpoint. No API key required.

Series fetched and their SOFR_OIS tensor mappings:
  SOFR    → 0.003  (O/N)
  DTB4WK  → 0.083  (1M)
  DTB3    → 0.25   (3M)
  DTB6    → 0.50   (6M)
  DGS1    → 1.00   (1Y)
  DGS2    → 2.00   (2Y)
  DGS3    → 3.00   (3Y)
  DGS5    → 5.00   (5Y)
  DGS7    → 7.00   (7Y)
  DGS10   → 10.00  (10Y)
  DGS20   → 20.00  (20Y)
  DGS30   → 30.00  (30Y)

FRED returns CSV with columns DATE,VALUE.  Missing observations are "."
(weekends/holidays) — the fetcher scans backward to find the latest
valid value.
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Optional

log = logging.getLogger(__name__)

_BASE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="

# FRED series ID → SOFR_OIS tenor key (years)
_FRED_SERIES: dict[str, float] = {
    "SOFR":   0.003,
    "DTB4WK": 0.083,
    "DTB3":   0.25,
    "DTB6":   0.50,
    "DGS1":   1.00,
    "DGS2":   2.00,
    "DGS3":   3.00,
    "DGS5":   5.00,
    "DGS7":   7.00,
    "DGS10":  10.00,
    "DGS20":  20.00,
    "DGS30":  30.00,
}


def _fetch_series(series_id: str, client) -> Optional[float]:
    """
    Fetch the latest valid observation for a FRED series.
    Returns the value in percent (as FRED reports it), or None on failure.
    """
    url = _BASE_URL + series_id
    try:
        resp = client.get(url, timeout=8.0)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("fred_curve: HTTP error fetching %s — %s", series_id, exc)
        return None

    # Parse CSV: DATE,VALUE — scan backward for last non-"." row
    reader = csv.reader(io.StringIO(resp.text))
    rows = list(reader)

    for row in reversed(rows[1:]):   # skip header
        if len(row) >= 2 and row[1].strip() not in (".", "", "VALUE"):
            try:
                return float(row[1])
            except ValueError:
                continue

    log.warning("fred_curve: no valid observation in %s response", series_id)
    return None


def fetch_live_curve() -> dict[float, float]:
    """
    Fetch all FRED series and return a SOFR_OIS-compatible dict.

    Returns a dict of {tenor_years: rate_pct} for all successfully fetched
    series. Any series that fails is omitted — the caller falls back to
    its hardcoded value for that tenor.

    Uses httpx (already a project dependency) for HTTP.
    """
    try:
        import httpx
    except ImportError:
        log.warning("fred_curve: httpx not installed")
        return {}

    live: dict[float, float] = {}

    with httpx.Client(follow_redirects=True) as client:
        for series_id, tenor in _FRED_SERIES.items():
            value = _fetch_series(series_id, client)
            if value is not None and value > 0:
                live[tenor] = round(value, 4)
                log.info(
                    "fred_curve: %s (%.3fY) = %.4f%%",
                    series_id, tenor, value,
                )

    log.info(
        "fred_curve: loaded %d/%d tenors from FRED",
        len(live), len(_FRED_SERIES),
    )
    return live
