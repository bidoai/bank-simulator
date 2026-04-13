"""
Live market data seeding — fetches real prices from Yahoo Finance at startup.

Maps Yahoo Finance symbols to internal simulation tickers. Bond yields are
converted to approximate clean prices using a first-order DV01 model.
Falls back silently to static SEED_PRICES for any ticker that fails.

Called once from MarketDataFeed.__init__ so every session starts anchored
to real market levels.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Yahoo Finance symbol → internal simulation ticker
_YF_DIRECT: dict[str, str] = {
    "AAPL":     "AAPL",
    "MSFT":     "MSFT",
    "SPY":      "SPY",
    "NVDA":     "NVDA",
    "GOOGL":    "GOOGL",
    "GC=F":     "XAUUSD",   # Gold futures
    "NG=F":     "NG1",      # Natural gas futures
    "CL=F":     "CL1",
    "EURUSD=X": "EURUSD",
    "GBPUSD=X": "GBPUSD",
}

# Yield indices — fetched separately and converted to bond prices
_YF_YIELDS: dict[str, str] = {
    "^TNX": "US10Y",   # 10-year treasury yield (%)
    "^IRX": "_3M",     # 13-week bill yield (%) — used to derive US2Y
}


def _yield_to_price(yield_pct: float, maturity_years: float, coupon_pct: float) -> float:
    """
    First-order bond price approximation.

    Uses modified duration from par-coupon bond:
        P ≈ 100 - ModDur × (y - c) × 100
    where ModDur ≈ maturity / (1 + c/200) for semi-annual coupon.
    Accurate to ~0.5 points for small yield deviations (<200bps from coupon).
    """
    mod_dur = maturity_years / (1.0 + coupon_pct / 200.0)
    price = 100.0 - mod_dur * (yield_pct - coupon_pct)
    return round(max(50.0, min(150.0, price)), 4)


def fetch_live_seeds() -> dict[str, float]:
    """
    Fetch live prices from Yahoo Finance.

    Returns a dict of simulation-ticker → current price for whichever
    tickers succeed. Any missing tickers fall back to static SEED_PRICES
    in the caller.

    Never raises — all errors are logged as warnings.
    """
    try:
        import yfinance as yf
    except ImportError:
        log.warning("live_seed: yfinance not installed — pip install yfinance")
        return {}

    live: dict[str, float] = {}

    # ── Direct equity / FX / commodity prices ────────────────────────────
    for yf_sym, sim_ticker in _YF_DIRECT.items():
        try:
            info = yf.Ticker(yf_sym).fast_info
            price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
            if price and float(price) > 0:
                live[sim_ticker] = round(float(price), 6)
                log.info("live_seed: %s = %.4f", sim_ticker, live[sim_ticker])
        except Exception as exc:
            log.warning("live_seed: failed to fetch %s — %s", yf_sym, exc)

    # ── Treasury yields → bond prices ────────────────────────────────────
    yield_cache: dict[str, float] = {}
    for yf_sym, label in _YF_YIELDS.items():
        try:
            info = yf.Ticker(yf_sym).fast_info
            y = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
            if y and float(y) > 0:
                yield_cache[label] = float(y)
        except Exception as exc:
            log.warning("live_seed: failed to fetch %s — %s", yf_sym, exc)

    if "US10Y" in yield_cache:
        y10 = yield_cache["US10Y"]
        # 10Y note: coupon ~4%, maturity 10Y, modified duration ~8.5Y
        live["US10Y"] = _yield_to_price(y10, maturity_years=10.0, coupon_pct=4.0)
        log.info("live_seed: US10Y yield=%.3f%% → price=%.4f", y10, live["US10Y"])

    if "_3M" in yield_cache:
        y3m = yield_cache["_3M"]
        # 2Y note: coupon ~4%, maturity 2Y, modified duration ~1.9Y
        # 2Y yield typically trades ~3M bill + 5-20bps in current regime
        y2 = y3m * 1.06
        live["US2Y"] = _yield_to_price(y2, maturity_years=2.0, coupon_pct=4.0)
        log.info("live_seed: US2Y est_yield=%.3f%% → price=%.4f", y2, live["US2Y"])

    # ── AAPL option: price from live AAPL spot ────────────────────────────
    # AAPL_CALL_200 is a 200-strike call. With AAPL above 200 it's deep ITM;
    # price ≈ intrinsic + small time-value premium (~0.5% of spot).
    if "AAPL" in live:
        aapl_spot = live["AAPL"]
        intrinsic = max(0.0, aapl_spot - 200.0)
        time_val = max(1.0, aapl_spot * 0.005)
        live["AAPL_CALL_200"] = round(intrinsic + time_val, 2)
        log.info(
            "live_seed: AAPL_CALL_200 intrinsic=%.2f + tv=%.2f → %.2f",
            intrinsic, time_val, live["AAPL_CALL_200"],
        )

    # USD_IRS_5Y stays at 100.0 (par swap — no direct Yahoo Finance quote)

    log.info("live_seed: seeded %d tickers from Yahoo Finance", len(live))
    return live
