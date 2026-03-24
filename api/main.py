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
    """Initialise the meeting store database at server startup."""
    from api.meeting_store import store as _store
    try:
        _store.initialize()
        log.info("meeting_store.ready")
    except Exception as exc:
        log.error("meeting_store.startup_failed", error=str(exc))
    yield


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
