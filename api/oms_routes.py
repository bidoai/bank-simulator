"""
OMS API routes — live replacements for the mock trading endpoints.

Routes registered here MUST be added to main.py BEFORE trading_routes so they
shadow the mock /blotter, /greeks, /pnl, and /ccr endpoints.

New endpoint:
  POST /api/trading/orders   — submit a market order, returns TradeConfirmation

Shadowed (now live):
  GET /api/trading/blotter   — live OMS blotter
  GET /api/trading/greeks    — computed from real positions via GreeksCalculator
  GET /api/trading/pnl       — from PositionManager.get_firm_report()
  GET /api/trading/ccr       — from CounterpartyRegistry (already real data)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.trading_broadcaster import trading_broadcaster
from infrastructure.risk.counterparty_registry import counterparty_registry
from infrastructure.risk.risk_service import risk_service
from infrastructure.trading.greeks import GreeksCalculator
from infrastructure.trading.oms import oms

log = structlog.get_logger(__name__)

router = APIRouter()

_DB_PATH = str(Path(__file__).parent.parent / "data" / "oms_trades.db")

# Serialise concurrent order submissions — prevents PositionManager data corruption
# under concurrent requests. Single-user demo: contention never occurs in practice.
_ORDER_LOCK = asyncio.Lock()

# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class OrderRequest(BaseModel):
    desk: str
    book_id: str
    ticker: str
    side: str       # "buy"/"sell" for equity/bond/fx/commodity; "payer"/"receiver" for IRS; "protection_buy"/"protection_sell" for CDS
    qty: float      # shares/lots for equity/commodity; notional for derivatives
    # Optional derivative enrichment — ignored for plain equity/bond trades
    notional: Optional[float] = None
    counterparty_id: Optional[str] = None
    fixed_rate: Optional[float] = None      # IRS fixed rate as decimal (e.g. 0.0425 for 4.25%)
    tenor_years: Optional[float] = None     # IRS/CDS tenor
    currency: Optional[str] = "USD"
    strike: Optional[float] = None          # option strike
    expiry_date: Optional[str] = None       # ISO date string
    product_subtype: Optional[str] = None   # "irs","cds","fwd","option","gov_bond","spot","future"
    spread_bps: Optional[float] = None      # CDS spread at booking
    override_raroc: bool = False            # P6: bypass RAROC gate (use when desk is below-hurdle but trade is strategically necessary)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _init_db() -> None:
    """Create oms_trades table if it doesn't exist, and migrate existing tables."""
    import os
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS oms_trades (
                trade_id        TEXT PRIMARY KEY,
                ticker          TEXT,
                side            TEXT,
                quantity        REAL,
                fill_price      REAL,
                notional        REAL,
                desk            TEXT,
                book_id         TEXT,
                trader_id       TEXT,
                executed_at     TEXT,
                greeks_json     TEXT,
                var_before      REAL,
                var_after       REAL,
                limit_status    TEXT,
                counterparty_id TEXT,
                product_subtype TEXT,
                product_details TEXT,
                pre_trade_message TEXT,
                limit_headroom_pct REAL
            )
        """)
        # Migrate existing tables — SQLite ignores duplicate column errors
        for col in (
            "counterparty_id TEXT",
            "product_subtype TEXT",
            "product_details TEXT",
            "pre_trade_message TEXT",
            "limit_headroom_pct REAL",
        ):
            try:
                await db.execute(f"ALTER TABLE oms_trades ADD COLUMN {col}")
            except Exception:
                pass
        await db.commit()


async def _persist_trade(conf_dict: dict) -> None:
    """Write-through to SQLite (fire-and-forget via create_task)."""
    import json
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            await db.execute(
                """INSERT OR REPLACE INTO oms_trades VALUES
                   (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    conf_dict["trade_id"],
                    conf_dict["ticker"],
                    conf_dict["side"],
                    conf_dict["quantity"],
                    conf_dict["fill_price"],
                    conf_dict["notional"],
                    conf_dict["desk"],
                    conf_dict["book_id"],
                    "system",
                    conf_dict["executed_at"],
                    json.dumps(conf_dict["greeks"]),
                    conf_dict["var_before"],
                    conf_dict["var_after"],
                    conf_dict["limit_status"],
                    conf_dict.get("counterparty_id"),
                    conf_dict.get("product_subtype"),
                    json.dumps(conf_dict["product_details"]) if conf_dict.get("product_details") else None,
                    conf_dict.get("pre_trade_message"),
                    conf_dict.get("limit_headroom_pct"),
                ),
            )
            await db.commit()
    except Exception as exc:
        log.error("oms.persist_failed", error=str(exc))


def _safe_parse_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _matches_history_filters(
    trade: dict,
    *,
    trade_id: str | None = None,
    book: str | None = None,
    instrument: str | None = None,
) -> bool:
    if trade_id and not (trade.get("trade_id", "").startswith(trade_id)):
        return False
    if book and trade.get("book_id") != book:
        return False
    if instrument and instrument.lower() not in (trade.get("instrument") or "").lower():
        return False
    return True


def _format_trade_record(record: dict) -> dict:
    executed_at = record.get("executed_at")
    time_value = record.get("time")
    if executed_at and not time_value:
        try:
            time_value = datetime.fromisoformat(executed_at.replace("Z", "+00:00")).strftime("%H:%M:%S")
        except Exception:
            time_value = executed_at

    trade_id = record.get("trade_id") or record.get("id")
    instrument = record.get("instrument") or record.get("ticker")
    quantity = record.get("qty", record.get("quantity"))
    price = record.get("price", record.get("fill_price"))
    book = record.get("book") or record.get("book_id")

    return {
        "id": trade_id,
        "trade_id": trade_id,
        "time": time_value,
        "executed_at": executed_at,
        "book": book,
        "book_id": book,
        "desk": record.get("desk"),
        "instrument": instrument,
        "ticker": instrument,
        "side": record.get("side"),
        "qty": quantity,
        "quantity": quantity,
        "price": price,
        "fill_price": price,
        "notional": record.get("notional"),
        "status": record.get("status", "FILLED"),
        "limit_status": record.get("limit_status"),
        "counterparty_id": record.get("counterparty_id"),
        "product_subtype": record.get("product_subtype"),
        "product_details": record.get("product_details") if isinstance(record.get("product_details"), dict) else _safe_parse_json(record.get("product_details")),
        "greeks": record.get("greeks") if isinstance(record.get("greeks"), dict) else _safe_parse_json(record.get("greeks_json")),
        "var_before": record.get("var_before"),
        "var_after": record.get("var_after"),
        "pre_trade_message": record.get("pre_trade_message"),
        "limit_headroom_pct": record.get("limit_headroom_pct"),
    }


async def _query_trade_history(
    *,
    trade_id: str | None = None,
    book: str | None = None,
    instrument: str | None = None,
    limit: int = 50,
    offset: int = 0,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> list[dict]:
    if not Path(_DB_PATH).exists():
        return []

    clauses = []
    params: list[object] = []

    if trade_id:
        clauses.append("trade_id LIKE ?")
        params.append(trade_id if "%" in trade_id else trade_id + "%")
    if book:
        clauses.append("book_id = ?")
        params.append(book)
    if instrument:
        clauses.append("ticker LIKE ?")
        params.append(instrument if "%" in instrument else "%" + instrument + "%")
    if from_ts:
        clauses.append("executed_at >= ?")
        params.append(from_ts)
    if to_ts:
        clauses.append("executed_at <= ?")
        params.append(to_ts)

    sql = """
        SELECT trade_id, ticker, side, quantity, fill_price, notional, desk, book_id,
               executed_at, greeks_json, var_before, var_after, limit_status,
               counterparty_id, product_subtype, product_details,
               pre_trade_message, limit_headroom_pct
        FROM oms_trades
    """
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY executed_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()

    return [_format_trade_record(dict(row)) for row in rows]


def _get_prices() -> dict[str, float]:
    """Return current mid prices from the feed, falling back gracefully."""
    if oms._feed is None:
        return {}
    return {t: float(q.mid) for t, q in oms._feed.get_all_quotes().items()}


# ---------------------------------------------------------------------------
# POST /api/trading/orders — execute a market order
# ---------------------------------------------------------------------------

@router.post("/trading/orders")
async def submit_order(order: OrderRequest) -> dict:
    if order.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be positive")

    # Normalise side aliases so PositionManager always sees "buy" or "sell"
    _SIDE_ALIASES = {
        "payer": "buy", "receiver": "sell",
        "protection_buy": "buy", "protection_sell": "sell",
    }
    normalised_side = _SIDE_ALIASES.get(order.side.lower(), order.side.lower())
    if normalised_side not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail=f"Unknown side: {order.side!r}")

    # Build product_details dict for derivatives
    product_details: dict | None = None
    if order.product_subtype:
        product_details = {k: v for k, v in {
            "fixed_rate":   order.fixed_rate,
            "tenor_years":  order.tenor_years,
            "spread_bps":   order.spread_bps,
            "strike":       order.strike,
            "expiry_date":  order.expiry_date,
            "currency":     order.currency,
            "original_side": order.side,       # preserve "payer"/"receiver" etc.
        }.items() if v is not None}

    async with _ORDER_LOCK:
        try:
            conf = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: oms.submit_order(
                    desk=order.desk.upper(),
                    book_id=order.book_id,
                    ticker=order.ticker,
                    side=normalised_side,
                    qty=order.qty,
                    counterparty_id=order.counterparty_id,
                    product_subtype=order.product_subtype,
                    product_details=product_details,
                    override_raroc=order.override_raroc,
                ),
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    conf_dict = conf.model_dump(mode="json")

    # Persist synchronously — trade record must survive; await so errors surface
    await _persist_trade(conf_dict)

    # Broadcast and XVA refresh are non-critical; fire-and-forget is fine here
    asyncio.create_task(trading_broadcaster.broadcast_fill(conf_dict))
    from infrastructure.xva.service import xva_service
    asyncio.create_task(xva_service.refresh())

    return conf_dict


# ---------------------------------------------------------------------------
# GET /api/trading/blotter — live blotter (shadows mock)
# ---------------------------------------------------------------------------

@router.get("/trading/blotter")
async def get_blotter(
    trade_id: str | None = Query(default=None),
    book: str | None = Query(default=None),
    instrument: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
) -> dict:
    trades = await _query_trade_history(
        trade_id=trade_id,
        book=book,
        instrument=instrument,
        limit=limit,
        offset=offset,
        from_ts=from_ts,
        to_ts=to_ts,
    )

    # Fall back to in-memory blotter for live/demo use if persistence is empty.
    if not trades:
        memory_trades = [_format_trade_record(t) for t in oms.get_blotter(limit=1000)]
        trades = [
            t for t in memory_trades
            if _matches_history_filters(t, trade_id=trade_id, book=book, instrument=instrument)
        ]
        trades = trades[offset:offset + limit]

    return {
        "trades": trades,
        "count": len(trades),
        "filters": {
            "trade_id": trade_id,
            "book": book,
            "instrument": instrument,
            "limit": limit,
            "offset": offset,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
    }


@router.get("/trading/trades/{trade_id}")
async def get_trade_detail(trade_id: str) -> dict:
    trades = await _query_trade_history(trade_id=trade_id, limit=50)
    for trade in trades:
        if trade["trade_id"] == trade_id:
            return trade

    for trade in oms.get_blotter(limit=1000):
        formatted = _format_trade_record(trade)
        if formatted["trade_id"] == trade_id:
            return formatted

    raise HTTPException(status_code=404, detail=f"Trade not found: {trade_id}")


# ---------------------------------------------------------------------------
# GET /api/trading/greeks — computed from real positions (shadows mock)
# ---------------------------------------------------------------------------

@router.get("/trading/greeks")
def get_greeks() -> dict:
    positions = risk_service.position_manager.get_all_positions()
    prices = _get_prices()

    agg = GreeksCalculator.aggregate(positions, prices)
    portfolio = agg["portfolio"]
    by_book = agg["by_book"]

    # Build the books list in the same shape the dashboard expects
    books = []
    for book_id, g in sorted(by_book.items()):
        desk = g.get("desk", "")
        delta_abs = abs(g["delta"])
        # Approximate delta limit from LimitManager if available
        try:
            lim = risk_service.limit_manager.get_limit("EQUITY_DELTA")
            delta_limit = lim.hard_limit
        except (KeyError, AttributeError):
            delta_limit = 500_000_000

        try:
            veg_lim = risk_service.limit_manager.get_limit("VEGA_FIRM")
            vega_limit = veg_lim.hard_limit
        except (KeyError, AttributeError):
            vega_limit = 50_000_000

        books.append({
            "book_id":        book_id,
            "name":           book_id,
            "desk":           desk,
            "trader":         desk,
            "delta":          round(g["delta"], 0),
            "gamma":          round(g["gamma"], 2),
            "vega":           round(g["vega"], 2),
            "theta":          round(g["theta"], 2),
            "rho":            round(g["rho"], 2),
            "dv01":           round(g["dv01"], 2),
            "delta_limit":    delta_limit,
            "vega_limit":     vega_limit,
            "delta_util_pct": round(delta_abs / max(delta_limit, 1) * 100, 1),
            "vega_util_pct":  round(abs(g["vega"]) / max(vega_limit, 1) * 100, 1),
        })

    return {
        "portfolio": {k: round(v, 2) for k, v in portfolio.items()},
        "books":     books,
    }


# ---------------------------------------------------------------------------
# GET /api/trading/pnl — from PositionManager (shadows mock)
# ---------------------------------------------------------------------------

@router.get("/trading/pnl")
def get_pnl() -> dict:
    firm = risk_service.position_manager.get_firm_report()

    # Build desk-level rows
    desks = []
    books = []
    for desk_name, desk_data in firm.get("by_desk", {}).items():
        if "error" in desk_data:
            continue
        total_pnl = desk_data.get("total_pnl", 0.0)
        desks.append({
            "desk":  desk_name,
            "daily": round(desk_data.get("unrealised_pnl", 0.0), 2),
            "mtd":   round(desk_data.get("realised_pnl", 0.0), 2),
            "ytd":   round(total_pnl, 2),
        })
        for book_dict in desk_data.get("books", []):
            books.append({
                "book_id": book_dict["book_id"],
                "name":    book_dict["book_id"],
                "desk":    desk_name,
                "daily":   round(book_dict.get("unrealised_pnl", 0.0), 2),
                "mtd":     round(book_dict.get("realised_pnl", 0.0), 2),
                "ytd":     round(book_dict.get("total_pnl", 0.0), 2),
            })

    total = {
        "daily": round(firm.get("unrealised_pnl", 0.0), 2),
        "mtd":   round(firm.get("realised_pnl", 0.0), 2),
        "ytd":   round(firm.get("total_pnl", 0.0), 2),
    }

    return {"total": total, "desks": desks, "books": books}


# ---------------------------------------------------------------------------
# GET /api/trading/ccr — live from CounterpartyRegistry (shadows mock)
# ---------------------------------------------------------------------------

@router.get("/trading/ccr")
def get_ccr() -> dict:
    report = counterparty_registry.get_report()
    summary = counterparty_registry.get_summary()

    total_ead = sum(cp["current_ead"] for cp in report)
    total_limit = sum(cp["pfe_limit"] for cp in report)
    total_util = round(total_ead / max(total_limit, 1) * 100, 1)

    counterparties = [
        {
            "counterparty": cp["name"],
            "id":           cp["id"],
            "rating":       cp["rating"],
            "ead_mm":       round(cp["current_ead"] / 1_000_000, 1),
            "limit_mm":     round(cp["pfe_limit"]   / 1_000_000, 0),
            "utilization":  round(cp["pfe_utilization_pct"], 1),
            "status":       cp["limit_status"],
            "headroom_mm":  round((cp["pfe_limit"] - cp["current_ead"]) / 1_000_000, 1),
        }
        for cp in report
    ]

    return {
        "total_ead_mm":   round(total_ead   / 1_000_000, 2),
        "total_limit_mm": round(total_limit / 1_000_000, 0),
        "total_util_pct": total_util,
        "breaches":       summary["breach"] + summary["red"],
        "warnings":       summary["yellow"] + summary["orange"],
        "counterparties": counterparties,
    }


@router.get("/trading/pnl-explain")
def get_pnl_explain():
    """
    P&L attribution by Greek bucket — per desk and firm-wide.
    Decomposes actual P&L into delta, gamma, theta, vega, and unexplained residual.
    """
    from infrastructure.trading.pnl_explain import pnl_explain_engine
    from infrastructure.market_data.feed_handler import MarketDataFeed

    positions = risk_service.position_manager.get_all_positions()
    try:
        _prices = {t: float(q.mid) for t, q in oms._feed.get_all_quotes().items()} if oms._feed else {}
    except Exception:
        _prices = {}

    return pnl_explain_engine.explain(positions, _prices)


@router.post("/trading/pnl-explain/reset-sod")
def reset_sod_snapshot():
    """Reset the SOD baseline to current prices and positions (for demo use)."""
    from infrastructure.trading.pnl_explain import pnl_explain_engine

    positions = risk_service.position_manager.get_all_positions()
    try:
        _prices = {t: float(q.mid) for t, q in oms._feed.get_all_quotes().items()} if oms._feed else {}
    except Exception:
        _prices = {}

    pnl_explain_engine.take_sod_snapshot(positions, _prices)
    return {"status": "ok", "positions_snapshotted": len(positions), "prices_snapshotted": len(_prices)}


# ---------------------------------------------------------------------------
# GET /api/trading/prices — current mid prices (used by booking ticket)
# ---------------------------------------------------------------------------

@router.get("/trading/prices")
def get_prices_snapshot() -> dict:
    """Return current mid prices for all instruments in the feed."""
    return _get_prices()


# ---------------------------------------------------------------------------
# Initialise DB on import
# ---------------------------------------------------------------------------

async def _ensure_db() -> None:
    await _init_db()
