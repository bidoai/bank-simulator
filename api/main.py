"""
Apex Global Bank — Web API
Serves all 5 dashboard panels + WebSocket streams.
Run: uvicorn api.main:app --reload --port 8000

BANK_LOG=1 enables structured logs to stderr (off by default to keep output clean).
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import structlog

# ── Optional structured logging (BANK_LOG=1 to enable) ───────────────────────

if os.environ.get("BANK_LOG"):
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Initialise services at server startup."""
    from api.meeting_store import store as _store
    try:
        _store.initialize()
        log.info("meeting_store.ready")
    except Exception as exc:
        log.error("meeting_store.startup_failed", error=str(exc))

    # Ensure data/ directory exists for OMS + new infrastructure SQLite files
    Path(__file__).parent.parent.joinpath("data").mkdir(exist_ok=True)

    # Initialise event log
    try:
        from infrastructure.events.event_log import event_log as _event_log  # noqa: F841
        log.info("event_log.ready")
    except Exception as exc:
        log.error("event_log.startup_failed", error=str(exc))

    # Initialise instrument master and seed defaults
    try:
        from infrastructure.reference.instrument_master import instrument_master as _im
        _im.seed_defaults()
        log.info("instrument_master.ready")
    except Exception as exc:
        log.error("instrument_master.startup_failed", error=str(exc))

    # Start market data feed and wire into OMS + position mark-to-market
    try:
        from infrastructure.market_data.feed_handler import MarketDataFeed
        from infrastructure.trading.oms import oms
        from infrastructure.risk.risk_service import risk_service
        from api.trading_broadcaster import trading_broadcaster

        _feed = MarketDataFeed()

        from infrastructure.events.bus import event_bus, TickEvent

        # Sync callback: mark positions to market on every tick, then broadcast
        def _on_tick(quote) -> None:
            risk_service.position_manager.mark_to_market(quote.ticker, float(quote.mid))
            # Schedule async broadcast without blocking the tick loop
            asyncio.ensure_future(
                trading_broadcaster.broadcast_tick({quote.ticker: float(quote.mid)})
            )
            # Publish TickEvent onto the event bus (non-blocking)
            event_bus.publish_sync(TickEvent(ticker=quote.ticker, price=float(quote.mid)))

        for ticker in _feed.get_all_quotes():
            _feed.subscribe(ticker, _on_tick)

        oms.set_feed(_feed)

        # Initialise OMS SQLite table
        from api.oms_routes import _init_db
        await _init_db()

        # Start feed as background task
        asyncio.ensure_future(_feed.start())
        log.info("market_data.feed_started")
    except Exception as exc:
        log.error("market_data.startup_failed", error=str(exc))
        _feed = None

    # Start intraday risk cycle (15s risk re-compute loop)
    try:
        from infrastructure.risk.intraday_cycle import intraday_cycle
        intraday_cycle.start()
        log.info("intraday_cycle.started")
    except Exception as exc:
        log.error("intraday_cycle.startup_failed", error=str(exc))

    # SOD P&L explain snapshot (taken after feed is seeded with live prices)
    try:
        from infrastructure.trading.pnl_explain import pnl_explain_engine
        from infrastructure.risk.risk_service import risk_service as _rs
        _sod_positions = _rs.position_manager.get_all_positions()
        _sod_prices = {t: float(q.mid) for t, q in _feed.get_all_quotes().items()} if _feed else {}
        pnl_explain_engine.take_sod_snapshot(_sod_positions, _sod_prices)
        log.info("pnl_explain.sod_snapshot_taken")
    except Exception as exc:
        log.error("pnl_explain.startup_failed", error=str(exc))

    # Initialise VaR backtest store (seeds 252 days of demo history)
    try:
        from infrastructure.risk.var_backtest_store import backtest_store
        backtest_store.initialize()
        log.info("var_backtest_store.ready")
    except Exception as exc:
        log.error("var_backtest_store.startup_failed", error=str(exc))

    # Initialise model governance registry
    try:
        from infrastructure.governance.model_registry import model_registry
        model_registry.initialize()
        log.info("model_registry.ready")
    except Exception as exc:
        log.error("model_registry.startup_failed", error=str(exc))

    yield

    if _feed is not None:
        await _feed.stop()

    try:
        from infrastructure.risk.intraday_cycle import intraday_cycle
        await intraday_cycle.stop()
    except Exception:
        pass


app = FastAPI(
    title="Apex Global Bank — Simulation Platform",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# CORS — allow local dev frontends (Vite, live-server, etc.)
from config.settings import ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static files (dashboard HTML, CSS, JS)
# ---------------------------------------------------------------------------

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"

if DASHBOARD_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")
else:
    log.warning("dashboard/ directory not found — static files will not be served")

# ---------------------------------------------------------------------------
# Route file imports (graceful degradation if not yet created)
# oms_routes MUST precede trading_routes — it shadows /blotter, /greeks, /pnl, /ccr
# ---------------------------------------------------------------------------

_ROUTE_MODULES = [
    "boardroom_routes",
    "xva_routes",
    "models_routes",
    "scenarios_routes",
    "oms_routes",               # must be before trading_routes
    "trading_routes",
    "observer_routes",
    "risk_routes",
    "capital_routes",
    "treasury_routes",
    "credit_routes",
    "compliance_routes",
    "metrics_routes",
    "collateral_routes",
    "stress_routes",
    "securities_finance_routes",
    "securitized_routes",
    "liquidity_routes",
]

for _mod in _ROUTE_MODULES:
    try:
        _module = importlib.import_module(f"api.{_mod}")
        app.include_router(_module.router, prefix="/api")
        log.info(f"{_mod} loaded")
    except ImportError:
        log.warning(f"api.{_mod} not found — endpoints unavailable")

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "bank": "Apex Global Bank"})

# ---------------------------------------------------------------------------
# HTML panel routes
# ---------------------------------------------------------------------------

def _html(name: str) -> FileResponse:
    path = DASHBOARD_DIR / name
    if not path.exists():
        return JSONResponse({"error": f"{name} not found"}, status_code=404)
    return FileResponse(str(path))


@app.get("/")
async def index() -> FileResponse:
    return _html("index.html")


@app.get("/boardroom")
async def boardroom() -> FileResponse:
    return _html("boardroom.html")


@app.get("/trading")
async def trading() -> FileResponse:
    return _html("trading.html")


@app.get("/xva")
async def xva() -> FileResponse:
    return _html("xva.html")


@app.get("/models")
async def models() -> FileResponse:
    return _html("models.html")


@app.get("/scenarios")
async def scenarios() -> FileResponse:
    return _html("scenarios.html")


@app.get("/risk")
async def risk() -> FileResponse:
    return _html("risk.html")


@app.get("/securities-finance")
async def securities_finance() -> FileResponse:
    return _html("securities_finance.html")


@app.get("/securitized")
async def securitized() -> FileResponse:
    return _html("securitized.html")


@app.get("/capital")
async def capital() -> FileResponse:
    return _html("capital.html")


@app.get("/treasury")
async def treasury() -> FileResponse:
    return _html("treasury.html")


@app.get("/liquidity")
async def liquidity() -> FileResponse:
    return _html("liquidity.html")

# ---------------------------------------------------------------------------
# WebSocket: Boardroom live stream
# ---------------------------------------------------------------------------

@app.websocket("/ws/boardroom")
async def ws_boardroom(websocket: WebSocket) -> None:
    """
    Live boardroom agent conversation stream.

    Delegates entirely to the BoardroomBroadcaster singleton:
    - on connect: replays history, adds client to broadcast set
    - keepalive: browser pings every 25 s; we reply with pong
    - on disconnect: removes client from broadcast set
    """
    try:
        from api.boardroom_broadcaster import broadcaster as _br
    except ImportError:
        await websocket.accept()
        await websocket.send_text(json.dumps({"type": "error", "message": "broadcaster unavailable"}))
        return

    await _br.connect(websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=60.0)
                if isinstance(data, dict) and data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "pong"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await _br.disconnect(websocket)


@app.websocket("/ws/trading")
async def ws_trading(websocket: WebSocket) -> None:
    """
    Live trading data stream — pushes fills and price ticks to the dashboard.
    Message types: fill, tick, positions.
    """
    try:
        from api.trading_broadcaster import trading_broadcaster as _tbr
    except ImportError:
        await websocket.accept()
        await websocket.send_text(json.dumps({"type": "error", "message": "trading broadcaster unavailable"}))
        return

    await _tbr.connect(websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=60.0)
                if isinstance(data, dict) and data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "pong"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await _tbr.disconnect(websocket)


async def broadcast_boardroom_message(message: dict) -> None:
    """
    Compatibility shim — delegates to the broadcaster singleton.
    Kept so any existing callers continue to work.
    """
    try:
        from api.boardroom_broadcaster import broadcaster as _br
        await _br._broadcast(message)
    except Exception:
        pass
