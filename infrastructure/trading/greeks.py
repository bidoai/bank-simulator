"""
Greeks Calculator — computes option/bond/FX sensitivities per position.

Dispatch logic:
  - Equities (AAPL, MSFT, SPY, NVDA, CL1):  delta = qty * price
  - Bonds (US10Y, US2Y):                      DV01  = notional * duration * 0.0001
  - FX (EURUSD, GBPUSD):                      delta = qty * rate (USD notional)
  - Equity options (*_CALL_*, *_PUT_*):        full Black-Scholes via scipy
  - IRS (USD_IRS_5Y):                          DV01  = qty * 0.0004
"""
from __future__ import annotations
import math
from typing import Optional

_ZERO = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0, "dv01": 0.0}

# Modified duration (years) for each bond ticker
_BOND_DURATIONS: dict[str, float] = {
    "US10Y": 8.5,
    "US2Y":  1.9,
}

_FX_TICKERS: frozenset[str] = frozenset({"EURUSD", "GBPUSD"})
_IRS_TICKERS: frozenset[str] = frozenset({"USD_IRS_5Y"})


def _parse_option(ticker: str) -> tuple[str, str, float]:
    """'AAPL_CALL_200' → ('AAPL', 'call', 200.0)"""
    parts = ticker.split("_")
    for i, p in enumerate(parts):
        if p in ("CALL", "PUT"):
            underlying = "_".join(parts[:i])
            opt_type = p.lower()
            try:
                strike = float(parts[i + 1])
            except (IndexError, ValueError):
                strike = 100.0
            return underlying, opt_type, strike
    return ticker, "call", 100.0


def _bsm(S: float, K: float, T: float, r: float, sigma: float,
         opt_type: str, qty: float) -> dict:
    """Black-Scholes greeks. Contract multiplier = 100."""
    try:
        from scipy.stats import norm
    except ImportError:
        # Fallback: delta-only (no scipy)
        intrinsic = max(0.0, S - K) if opt_type == "call" else max(0.0, K - S)
        delta = qty * 100 * (intrinsic / max(S, 1e-9))
        return {**_ZERO, "delta": delta}

    if T <= 0 or S <= 0 or K <= 0 or sigma <= 0:
        return dict(_ZERO)

    sqT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqT)
    d2 = d1 - sigma * sqT
    m = qty * 100  # contract multiplier

    if opt_type == "call":
        delta = m * norm.cdf(d1)
        rho   = m * K * T * math.exp(-r * T) * norm.cdf(d2) / 100.0
    else:
        delta = m * (norm.cdf(d1) - 1.0)
        rho   = -m * K * T * math.exp(-r * T) * norm.cdf(-d2) / 100.0

    gamma = m * norm.pdf(d1) / max(S * sigma * sqT, 1e-9)
    vega  = m * S * norm.pdf(d1) * sqT / 100.0
    theta = m * (
        -(S * norm.pdf(d1) * sigma) / max(2.0 * sqT, 1e-9)
        - r * K * math.exp(-r * T) * (norm.cdf(d2) if opt_type == "call" else norm.cdf(-d2))
    ) / 365.0

    return {"delta": delta, "gamma": gamma, "vega": vega,
            "theta": theta, "rho": rho, "dv01": 0.0}


class GreeksCalculator:

    @classmethod
    def compute(
        cls,
        ticker: str,
        qty: float,
        price: float,
        prices: Optional[dict[str, float]] = None,
    ) -> dict:
        """
        Return {delta, gamma, vega, theta, rho, dv01} in USD for one position.
        prices: current market prices dict (used for option underlying lookup).
        """
        prices = prices or {}

        if ticker in _IRS_TICKERS:
            return {**_ZERO, "dv01": qty * 0.0004}

        if ticker in _BOND_DURATIONS:
            duration = _BOND_DURATIONS[ticker]
            # Face value: qty contracts * $1,000 face * (price / 100 clean price)
            face_value = abs(qty) * 1000.0 * (price / 100.0)
            dv01 = face_value * duration * 0.0001
            dv01 = dv01 if qty >= 0 else -dv01
            return {**_ZERO, "dv01": dv01}

        if ticker in _FX_TICKERS:
            # qty in base currency, price = spot rate → USD notional
            return {**_ZERO, "delta": qty * price}

        if "_CALL_" in ticker or "_PUT_" in ticker:
            underlying, opt_type, strike = _parse_option(ticker)
            S = prices.get(underlying, price)
            return _bsm(S, strike, 0.25, 0.045, 0.30, opt_type, qty)

        # Default: equity / commodity delta-1
        return {**_ZERO, "delta": qty * price}

    @classmethod
    def aggregate(
        cls,
        positions: list[dict],
        prices: Optional[dict[str, float]] = None,
    ) -> dict:
        """
        Aggregate Greeks across all positions.

        positions: list of BookPosition.to_dict() dicts — fields:
            book_id, desk, instrument, quantity, last_price, avg_cost, ...
        Returns:
            {
              "portfolio": {delta, gamma, vega, theta, rho, dv01},
              "by_book": {book_id: {book_id, desk, delta, gamma, vega, theta, rho, dv01}},
            }
        """
        prices = prices or {}
        keys = ("delta", "gamma", "vega", "theta", "rho", "dv01")
        portfolio: dict[str, float] = {k: 0.0 for k in keys}
        by_book: dict[str, dict] = {}

        for pos in positions:
            ticker  = pos.get("instrument", "")
            qty     = float(pos.get("quantity", 0.0))
            price   = float(pos.get("last_price") or pos.get("avg_cost") or prices.get(ticker, 0.0))
            book_id = pos.get("book_id", "default")
            desk    = pos.get("desk", "")

            if qty == 0.0:
                continue

            g = cls.compute(ticker, qty, price, prices)

            for k in keys:
                portfolio[k] += g[k]

            if book_id not in by_book:
                by_book[book_id] = {"book_id": book_id, "desk": desk, **{k: 0.0 for k in keys}}
            for k in keys:
                by_book[book_id][k] += g[k]

        return {"portfolio": portfolio, "by_book": by_book}
