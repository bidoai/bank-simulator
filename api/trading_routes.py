"""
FastAPI routes for the Trading Floor dashboard — static fallback layer.

NOTE ON SHADOW ROUTING: api/main.py registers oms_routes BEFORE these
trading_routes. FastAPI resolves the first matching route, so the live
endpoints at /api/trading/blotter, /greeks, /pnl, and /ccr are served
by oms_routes (backed by the live OMS and PositionManager). The static
routes in this file are never reached in a running server; they exist
only for offline testing and as documentation of the expected schemas.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(prefix="/trading", tags=["trading"])

# ---------------------------------------------------------------------------
# Mock data — Trading books at Apex Global Bank
# ---------------------------------------------------------------------------

_BOOKS = {
    "IR_RATES":     {"name": "IR Rates",       "trader": "James Park",      "desk": "Rates"},
    "IR_CREDIT":    {"name": "IR Credit",      "trader": "Sofia Reyes",     "desk": "Rates"},
    "EQ_DERIV":     {"name": "Equity Derivs",  "trader": "Marcus Chen",     "desk": "Equities"},
    "EQ_DELTA1":    {"name": "Delta-One",      "trader": "Priya Mehta",     "desk": "Equities"},
    "FX_OPTIONS":   {"name": "FX Options",     "trader": "Kai Tanaka",      "desk": "FX"},
    "FX_SPOT":      {"name": "FX Spot/Fwd",   "trader": "Nina Volkov",     "desk": "FX"},
    "CREDIT_CORP":  {"name": "Corp Credit",    "trader": "Leo Santos",      "desk": "Credit"},
    "CREDIT_STRUC": {"name": "Structured Cdt", "trader": "Rachel Kim",      "desk": "Credit"},
}

# Greeks per book (delta=DV01 in USD, gamma/vega/theta/rho in $k per unit)
_BOOK_GREEKS = {
    "IR_RATES":     {"delta": -182_000, "gamma":   4_200, "vega":      0, "theta":  -1_840, "rho":   9_200, "dv01": -182_000},
    "IR_CREDIT":    {"delta":   94_000, "gamma":   1_100, "vega":      0, "theta":    -620, "rho":   4_100, "dv01":   94_000},
    "EQ_DERIV":     {"delta":  312_000, "gamma":  18_400, "vega":  92_300, "theta": -12_100, "rho":   6_800, "dv01":       0},
    "EQ_DELTA1":    {"delta":  780_000, "gamma":       0, "vega":      0, "theta":       0, "rho":       0, "dv01":       0},
    "FX_OPTIONS":   {"delta":  -48_000, "gamma":   3_100, "vega":  31_200, "theta":  -4_300, "rho":  -1_200, "dv01":       0},
    "FX_SPOT":      {"delta":  120_000, "gamma":       0, "vega":      0, "theta":       0, "rho":       0, "dv01":       0},
    "CREDIT_CORP":  {"delta":   62_000, "gamma":     800, "vega":      0, "theta":    -420, "rho":   2_800, "dv01":   62_000},
    "CREDIT_STRUC": {"delta":   38_000, "gamma":   2_200, "vega":   4_100, "theta":    -890, "rho":   1_600, "dv01":   38_000},
}

# Limits per book
_BOOK_LIMITS = {
    "IR_RATES":     {"delta_limit": 500_000, "vega_limit": 50_000, "var_limit": 2_500_000},
    "IR_CREDIT":    {"delta_limit": 300_000, "vega_limit": 30_000, "var_limit": 1_500_000},
    "EQ_DERIV":     {"delta_limit": 600_000, "vega_limit": 200_000, "var_limit": 5_000_000},
    "EQ_DELTA1":    {"delta_limit": 2_000_000, "vega_limit": 100_000, "var_limit": 8_000_000},
    "FX_OPTIONS":   {"delta_limit": 200_000, "vega_limit": 80_000, "var_limit": 2_000_000},
    "FX_SPOT":      {"delta_limit": 500_000, "vega_limit": 20_000, "var_limit": 1_000_000},
    "CREDIT_CORP":  {"delta_limit": 250_000, "vega_limit": 20_000, "var_limit": 1_200_000},
    "CREDIT_STRUC": {"delta_limit": 150_000, "vega_limit": 50_000, "var_limit": 900_000},
}

# Daily P&L per book (USD)
_BOOK_PNL = {
    "IR_RATES":     {"daily": -124_000, "ytd":  3_820_000, "mtd":   -340_000},
    "IR_CREDIT":    {"daily":   82_000, "ytd":  2_140_000, "mtd":    210_000},
    "EQ_DERIV":     {"daily":  318_000, "ytd":  9_640_000, "mtd":    870_000},
    "EQ_DELTA1":    {"daily":  -64_000, "ytd": 12_100_000, "mtd":   -280_000},
    "FX_OPTIONS":   {"daily":   47_000, "ytd":  1_890_000, "mtd":    140_000},
    "FX_SPOT":      {"daily":   21_000, "ytd":    780_000, "mtd":     60_000},
    "CREDIT_CORP":  {"daily":  -18_000, "ytd":  1_230_000, "mtd":    -90_000},
    "CREDIT_STRUC": {"daily":   93_000, "ytd":  4_580_000, "mtd":    320_000},
}

# CCR limits per counterparty
_CCR = {
    "Goldman_Sachs":  {"ead": 8.4,  "limit": 15.0, "rating": "AA-"},
    "JPMorgan_Chase": {"ead": 11.2, "limit": 20.0, "rating": "A+"},
    "Deutsche_Bank":  {"ead": 8.52, "limit": 10.0, "rating": "BBB+"},
    "BNP_Paribas":    {"ead": 5.3,  "limit": 12.0, "rating": "A"},
    "HSBC":           {"ead": 6.0,  "limit": 18.0, "rating": "AA-"},
    "Morgan_Stanley": {"ead": 3.8,  "limit": 10.0, "rating": "A"},
    "Citigroup":      {"ead": 7.1,  "limit": 14.0, "rating": "A-"},
}

# Recent trades blotter (static sample)
_BLOTTER = [
    {"id": "TRD-0041", "time": "14:32:01", "book": "EQ_DERIV",  "instrument": "SPX Dec 5000 Call",   "side": "BUY",  "qty": 500,  "price": 48.20, "status": "FILLED"},
    {"id": "TRD-0040", "time": "14:28:44", "book": "IR_RATES",  "instrument": "USD IRS 10Y Pay Fix",  "side": "PAY",  "qty": 50_000_000, "price": 4.472, "status": "FILLED"},
    {"id": "TRD-0039", "time": "14:21:17", "book": "FX_OPTIONS","instrument": "EUR/USD 3M 1.09 Call", "side": "BUY",  "qty": 10_000_000, "price": 0.0082, "status": "FILLED"},
    {"id": "TRD-0038", "time": "14:15:03", "book": "EQ_DELTA1", "instrument": "AAPL",                 "side": "SELL", "qty": 5_000, "price": 214.67, "status": "FILLED"},
    {"id": "TRD-0037", "time": "14:02:55", "book": "CREDIT_CORP","instrument": "AAPL 5Y CDS",         "side": "BUY",  "qty": 5_000_000, "price": 42.5, "status": "FILLED"},
    {"id": "TRD-0036", "time": "13:58:29", "book": "IR_CREDIT", "instrument": "CDX.IG 5Y",            "side": "SELL", "qty": 25_000_000, "price": 68.2, "status": "FILLED"},
    {"id": "TRD-0035", "time": "13:44:12", "book": "FX_SPOT",   "instrument": "USD/JPY",              "side": "BUY",  "qty": 20_000_000, "price": 149.82, "status": "FILLED"},
    {"id": "TRD-0034", "time": "13:31:08", "book": "EQ_DERIV",  "instrument": "SPX Dec 4800 Put",    "side": "SELL", "qty": 300,  "price": 32.10, "status": "FILLED"},
]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/greeks")
def get_greeks():
    """Portfolio Greeks — portfolio totals and per-book breakdown."""
    books = []
    for book_id, g in _BOOK_GREEKS.items():
        book_info = _BOOKS[book_id]
        limits = _BOOK_LIMITS[book_id]
        delta_util = round(abs(g["delta"]) / limits["delta_limit"] * 100, 1)
        vega_util  = round(abs(g["vega"])  / limits["vega_limit"]  * 100, 1) if limits["vega_limit"] else 0.0
        books.append({
            "book_id":    book_id,
            "name":       book_info["name"],
            "desk":       book_info["desk"],
            "trader":     book_info["trader"],
            "delta":      g["delta"],
            "gamma":      g["gamma"],
            "vega":       g["vega"],
            "theta":      g["theta"],
            "rho":        g["rho"],
            "dv01":       g["dv01"],
            "delta_limit":    limits["delta_limit"],
            "vega_limit":     limits["vega_limit"],
            "delta_util_pct": delta_util,
            "vega_util_pct":  vega_util,
        })

    # Portfolio totals
    portfolio = {
        "delta": sum(g["delta"] for g in _BOOK_GREEKS.values()),
        "gamma": sum(g["gamma"] for g in _BOOK_GREEKS.values()),
        "vega":  sum(g["vega"]  for g in _BOOK_GREEKS.values()),
        "theta": sum(g["theta"] for g in _BOOK_GREEKS.values()),
        "rho":   sum(g["rho"]   for g in _BOOK_GREEKS.values()),
        "dv01":  sum(g["dv01"]  for g in _BOOK_GREEKS.values()),
    }

    return {"portfolio": portfolio, "books": books}


@router.get("/pnl")
def get_pnl():
    """P&L attribution — daily and YTD by book and desk."""
    books = []
    for book_id, pnl in _BOOK_PNL.items():
        book_info = _BOOKS[book_id]
        books.append({
            "book_id": book_id,
            "name":    book_info["name"],
            "desk":    book_info["desk"],
            "trader":  book_info["trader"],
            "daily":   pnl["daily"],
            "mtd":     pnl["mtd"],
            "ytd":     pnl["ytd"],
        })

    # Desk roll-ups
    desk_map: dict = {}
    for b in books:
        d = b["desk"]
        if d not in desk_map:
            desk_map[d] = {"daily": 0, "mtd": 0, "ytd": 0}
        desk_map[d]["daily"] += b["daily"]
        desk_map[d]["mtd"]   += b["mtd"]
        desk_map[d]["ytd"]   += b["ytd"]

    total_daily = sum(pnl["daily"] for pnl in _BOOK_PNL.values())
    total_mtd   = sum(pnl["mtd"]   for pnl in _BOOK_PNL.values())
    total_ytd   = sum(pnl["ytd"]   for pnl in _BOOK_PNL.values())

    return {
        "total": {"daily": total_daily, "mtd": total_mtd, "ytd": total_ytd},
        "desks": [{"desk": k, **v} for k, v in desk_map.items()],
        "books": books,
    }


@router.get("/ccr")
def get_ccr():
    """CCR limit utilisation per counterparty."""
    result = []
    for cp, data in _CCR.items():
        util = round(data["ead"] / data["limit"] * 100, 1)
        status = "BREACH" if util > 100 else ("WARN" if util > 80 else "OK")
        result.append({
            "counterparty": cp.replace("_", " "),
            "id":           cp,
            "rating":       data["rating"],
            "ead_mm":       data["ead"],
            "limit_mm":     data["limit"],
            "utilization":  util,
            "status":       status,
            "headroom_mm":  round(max(0.0, data["limit"] - data["ead"]), 2),
        })

    # Sort by utilisation descending
    result.sort(key=lambda x: x["utilization"], reverse=True)

    total_ead   = sum(d["ead"]   for d in _CCR.values())
    total_limit = sum(d["limit"] for d in _CCR.values())

    return {
        "total_ead_mm":   round(total_ead, 2),
        "total_limit_mm": round(total_limit, 2),
        "total_util_pct": round(total_ead / total_limit * 100, 1),
        "breaches":       sum(1 for x in result if x["status"] == "BREACH"),
        "warnings":       sum(1 for x in result if x["status"] == "WARN"),
        "counterparties": result,
    }


@router.get("/blotter")
def get_blotter():
    """Recent trade blotter."""
    return {"trades": _BLOTTER, "count": len(_BLOTTER)}


@router.get("/circuit-breaker")
def get_circuit_breaker():
    """Circuit breaker state across all desks."""
    desks = [
        {"desk": "Rates",     "state": "CLOSED", "trigger": None,      "daily_loss": -42_000,    "limit": -5_000_000},
        {"desk": "Equities",  "state": "CLOSED", "trigger": None,      "daily_loss":  254_000,   "limit": -5_000_000},
        {"desk": "FX",        "state": "CLOSED", "trigger": None,      "daily_loss":   68_000,   "limit": -3_000_000},
        {"desk": "Credit",    "state": "CLOSED", "trigger": None,      "daily_loss":   75_000,   "limit": -2_000_000},
    ]
    return {
        "system_state": "CLOSED",  # CLOSED = normal (no breaker tripped)
        "last_checked":  datetime.now(timezone.utc).isoformat(),
        "desks": desks,
    }
