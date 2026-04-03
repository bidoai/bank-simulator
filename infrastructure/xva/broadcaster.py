"""XVABroadcaster — fans out XVA refresh results to /ws/xva clients."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from fastapi import WebSocket
import structlog
log = structlog.get_logger(__name__)

class XVABroadcaster:
    def __init__(self) -> None:
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.append(ws)
        log.info("xva_broadcaster.connected", total=len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        self._clients = [c for c in self._clients if c is not ws]

    async def broadcast_refresh(self, result: dict) -> None:
        msg = {
            "type": "xva_refresh",
            "data": result,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        }
        dead = []
        for client in self._clients:
            try:
                await client.send_json(msg)
            except Exception:
                dead.append(client)
        for d in dead:
            self.disconnect(d)

xva_broadcaster = XVABroadcaster()
