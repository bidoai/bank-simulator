"""
DFAST / CCAR 2025 Official Scenario Parameters.

Source: Federal Reserve Board — 2025 Supervisory Scenarios (February 5, 2025).
https://www.federalreserve.gov/supervisionreg/dfast-economic-scenarios.htm

The Fed publishes three scenarios annually:
  - Baseline:          GDP grows ~2%, unemployment stable
  - Adverse:           Mild recession, +2.5pp unemployment, equity -15%
  - Severely Adverse:  Severe recession, +6pp unemployment, equity -55%

Parameters are expressed as cumulative changes over the 9-quarter horizon.

Live calibration:
  fetch_macro_starting_point() pulls the current UNRATE, GDP growth, and
  S&P 500 from FRED so scenarios are expressed relative to where we actually
  are today, not the Fed's Feb 2025 starting conditions.
"""
from __future__ import annotations

import csv
import io
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Official 2025 Fed DFAST Scenario Parameters
# These are the CUMULATIVE changes over the full 9-quarter horizon.
# Source: Board of Governors, February 5, 2025.
# ---------------------------------------------------------------------------

# Unemployment rate PEAKS (absolute level, %) per scenario
_UNRATE_PEAK: dict[str, float] = {
    "baseline":         4.1,
    "adverse":          6.4,
    "severely_adverse": 10.0,
}

# Cumulative real GDP change (fraction) over 9 quarters
_GDP_CUMULATIVE: dict[str, float] = {
    "baseline":         +0.050,   # ~+2% per year
    "adverse":          -0.019,   # mild recession
    "severely_adverse": -0.082,   # severe contraction
}

# Peak-to-trough equity price change (fraction) — DJIA proxy
_EQUITY_SHOCK: dict[str, float] = {
    "baseline":         +0.03,
    "adverse":          -0.15,
    "severely_adverse": -0.55,
}

# Change in 3M Treasury rate over 9 quarters (bps)
# Severely adverse: near-zero policy rates (rates drop sharply)
# Adverse: moderate easing
# Baseline: gradual normalization
_RATE_DELTA_BPS_3M: dict[str, float] = {
    "baseline":         -30,
    "adverse":          -280,
    "severely_adverse": -350,
}

# Historical typical starting UNRATE used in official scenarios (Feb 2025 publication)
_FED_BASELINE_UNRATE = 4.0


# ---------------------------------------------------------------------------
# Live macro starting point
# ---------------------------------------------------------------------------

def fetch_macro_starting_point() -> dict:
    """
    Fetch current macro conditions from FRED to anchor the DFAST starting point.

    Returns:
        unrate_pct:     Current unemployment rate (%)
        gdp_growth_pct: Most recent quarterly GDP growth, annualized (%)
        sp500_level:    Current S&P 500 index level
        rate_3m_pct:    Current 3-month T-bill yield (%)

    Falls back to historical typical values on any failure.
    """
    defaults = {
        "unrate_pct":     _FED_BASELINE_UNRATE,
        "gdp_growth_pct": 2.0,
        "sp500_level":    5_500.0,
        "rate_3m_pct":    4.30,
    }

    try:
        import httpx
    except ImportError:
        log.warning("dfast_scenarios: httpx not installed")
        return defaults

    def _fred_last(series_id: str) -> float | None:
        try:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
            resp = httpx.get(url, timeout=8.0, follow_redirects=True)
            resp.raise_for_status()
            for row in reversed(list(csv.reader(io.StringIO(resp.text)))[1:]):
                if len(row) >= 2 and row[1].strip() not in (".", ""):
                    return float(row[1])
        except Exception as exc:
            log.warning("dfast_scenarios: FRED fetch %s failed — %s", series_id, exc)
        return None

    result = dict(defaults)

    unrate = _fred_last("UNRATE")
    if unrate is not None:
        result["unrate_pct"] = unrate
        log.info("dfast_scenarios: UNRATE = %.2f%%", unrate)

    gdp_q = _fred_last("A191RL1Q225SBEA")   # quarterly real GDP growth, annualized
    if gdp_q is not None:
        result["gdp_growth_pct"] = gdp_q
        log.info("dfast_scenarios: GDP QoQ ann = %.2f%%", gdp_q)

    sp500 = _fred_last("SP500")
    if sp500 is not None:
        result["sp500_level"] = sp500
        log.info("dfast_scenarios: S&P 500 = %.0f", sp500)

    rate_3m = _fred_last("DTB3")
    if rate_3m is not None:
        result["rate_3m_pct"] = rate_3m
        log.info("dfast_scenarios: 3M T-bill = %.2f%%", rate_3m)

    return result


def build_scenarios(macro: dict | None = None) -> dict[str, dict]:
    """
    Build DFAST scenario parameter dicts calibrated to a live macro starting point.

    The official scenario defines ABSOLUTE unemployment peaks and cumulative
    asset changes.  We re-express them relative to where the economy is today.

    Returns a dict in the same format as dfast_engine.SCENARIOS:
        {
            "baseline": {
                "gdp":              annual rate (fraction),
                "ur_delta":         unemployment change (pp),
                "eq_shock":         equity price shock (fraction),
                "rate_bps":         interest rate shock (bps),
                "equity_shock_pct": same as eq_shock (alias),
                "source":           "DFAST 2025 Official",
                "starting_unrate":  float,
            },
            ...
        }
    """
    if macro is None:
        macro = fetch_macro_starting_point()

    current_unrate = macro["unrate_pct"]
    current_rate_3m = macro["rate_3m_pct"]

    scenarios: dict[str, dict] = {}
    for name in ("baseline", "adverse", "severely_adverse"):
        # ur_delta = how much unemployment rises FROM today's level
        ur_delta = max(0.0, _UNRATE_PEAK[name] - current_unrate)

        # rate_bps = change relative to today's 3M rate
        # Cap at floor of 0.1% (zero lower bound approximation)
        new_rate_3m = max(0.10, current_rate_3m + _RATE_DELTA_BPS_3M[name] / 100.0)
        rate_bps = round((new_rate_3m - current_rate_3m) * 100)

        # GDP: convert cumulative 9Q to annualised rate (÷ 2.25 years)
        gdp_annual = _GDP_CUMULATIVE[name] / 2.25

        eq_shock = _EQUITY_SHOCK[name]

        scenarios[name] = {
            "gdp":              round(gdp_annual, 4),
            "ur_delta":         round(ur_delta, 2),
            "eq_shock":         eq_shock,
            "rate_bps":         rate_bps,
            "equity_shock_pct": eq_shock,
            "source":           "DFAST 2025 Official / FRED",
            "starting_unrate":  round(current_unrate, 2),
            "starting_rate_3m": round(current_rate_3m, 2),
            "unrate_peak":      _UNRATE_PEAK[name],
        }
        log.info(
            "dfast_scenarios: %s — gdp=%.2f%% ur_delta=%.1fpp eq=%.0f%% rate=%+dbps",
            name, gdp_annual * 100, ur_delta, eq_shock * 100, rate_bps,
        )

    return scenarios
