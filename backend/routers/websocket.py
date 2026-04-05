"""
backend/routers/websocket.py
WebSocket endpoint that broadcasts every new shot to all connected clients.

The ConnectionManager keeps a registry of active WebSocket connections and
fans out messages. The ShotService calls broadcast() after persisting each shot.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


# ─── Connection manager ───────────────────────────────────────────────────────

class ConnectionManager:
    """Thread-safe registry for active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        logger.info("WS client connected. Total: %d", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections = [c for c in self._connections if c is not ws]
        logger.info("WS client disconnected. Total: %d", len(self._connections))

    async def broadcast(self, message: dict) -> None:
        """
        Send a JSON message to all connected clients.
        Dead connections are removed silently.
        """
        payload = json.dumps(message, default=str)
        dead    = []

        async with self._lock:
            targets = list(self._connections)

        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self.disconnect(ws)

    @property
    def client_count(self) -> int:
        return len(self._connections)


# Module-level singleton — imported by shot_service to call broadcast()
manager = ConnectionManager()


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.websocket("/ws/shots")
async def websocket_shots(ws: WebSocket) -> None:
    """
    Real-time shot feed.
    Clients connect and receive a JSON object for every new shot.
    A heartbeat ping is sent every 20 s to keep the connection alive.
    """
    await manager.connect(ws)
    try:
        # Send initial heartbeat to confirm connection
        await ws.send_json({"type": "connected", "clients": manager.client_count})

        # Keep connection alive; actual shot data comes via broadcast()
        while True:
            try:
                # Wait for client pong or idle; timeout triggers our own ping
                await asyncio.wait_for(ws.receive_text(), timeout=20.0)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping", "ts": datetime.utcnow().isoformat()})

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)