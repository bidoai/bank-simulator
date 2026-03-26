"""
Apex Global Bank — Web API
Serves all 5 dashboard panels + WebSocket streams.
Run: uvicorn api.main:app --reload --port 8000

BANK_LOG=1 enables structured logs to stderr (off by default to keep output clean).
"""
from __future__ import annotations

import asyncio
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

        # Sync callback: mark positions to market on every tick, then broadcast
        def _on_tick(quote) -> None:
            risk_service.position_manager.mark_to_market(quote.ticker, float(quote.mid))
            # Schedule async broadcast without blocking the tick loop
            asyncio.ensure_future(
                trading_broadcaster.broadcast_tick({quote.ticker: float(quote.mid)})
            )

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

    yield

    if _feed is not None:
        await _feed.stop()


app = FastAPI(
    title="Apex Global Bank — Simulation Platform",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# CORS — allow local dev frontends (Vite, live-server, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:8000", "http://localhost:8000"],
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
# ---------------------------------------------------------------------------

try:
    from api import boardroom_routes
    app.include_router(boardroom_routes.router, prefix="/api")
    log.info("boardroom_routes loaded")
except ImportError:
    log.warning("api.boardroom_routes not found — boardroom API endpoints unavailable")

try:
    from api import xva_routes
    app.include_router(xva_routes.router, prefix="/api")
    log.info("xva_routes loaded")
except ImportError:
    log.warning("api.xva_routes not found — XVA API endpoints unavailable")

try:
    from api import models_routes
    app.include_router(models_routes.router, prefix="/api")
    log.info("models_routes loaded")
except ImportError:
    log.warning("api.models_routes not found — model governance API endpoints unavailable")

try:
    from api import scenarios_routes
    app.include_router(scenarios_routes.router, prefix="/api")
    log.info("scenarios_routes loaded")
except ImportError:
    log.warning("api.scenarios_routes not found — scenarios API endpoints unavailable")

# oms_routes MUST be registered before trading_routes — it shadows /blotter, /greeks, /pnl, /ccr
try:
    from api import oms_routes
    app.include_router(oms_routes.router, prefix="/api")
    log.info("oms_routes loaded")
except ImportError:
    log.warning("api.oms_routes not found — OMS endpoints unavailable")

try:
    from api import trading_routes
    app.include_router(trading_routes.router, prefix="/api")
    log.info("trading_routes loaded")
except ImportError:
    log.warning("api.trading_routes not found — trading API endpoints unavailable")

try:
    from api import observer_routes
    app.include_router(observer_routes.router, prefix="/api")
    log.info("observer_routes loaded")
except ImportError:
    log.warning("api.observer_routes not found — Observer Q&A unavailable")

try:
    from api import risk_routes
    app.include_router(risk_routes.router, prefix="/api")
    log.info("risk_routes loaded")
except ImportError:
    log.warning("api.risk_routes not found — risk API endpoints unavailable")

try:
    from api import capital_routes
    app.include_router(capital_routes.router, prefix="/api")
    log.info("capital_routes loaded")
except ImportError:
    log.warning("api.capital_routes not found — regulatory capital API endpoints unavailable")

try:
    from api import treasury_routes
    app.include_router(treasury_routes.router, prefix="/api")
    log.info("treasury_routes loaded")
except ImportError:
    log.warning("api.treasury_routes not found — treasury FTP/ALM API endpoints unavailable")

try:
    from api import credit_routes
    app.include_router(credit_routes.router, prefix="/api")
    log.info("credit_routes loaded")
except ImportError:
    log.warning("api.credit_routes not found — credit ECL API endpoints unavailable")

try:
    from api import compliance_routes
    app.include_router(compliance_routes.router, prefix="/api")
    log.info("compliance_routes loaded")
except ImportError:
    log.warning("api.compliance_routes not found — AML compliance API endpoints unavailable")

try:
    from api import metrics_routes
    app.include_router(metrics_routes.router, prefix="/api")
    log.info("metrics_routes loaded")
except ImportError:
    log.warning("api.metrics_routes not found — metrics API endpoints unavailable")

try:
    from api import collateral_routes
    app.include_router(collateral_routes.router, prefix="/api")
    log.info("collateral_routes loaded")
except ImportError:
    log.warning("api.collateral_routes not found — collateral API endpoints unavailable")

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
