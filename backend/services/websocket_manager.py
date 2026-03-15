"""WebSocket connection manager: track clients and broadcast events to all."""
import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Maintains active WebSocket connections and broadcasts JSON messages to all."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the main event loop so broadcast_sync can schedule from threads."""
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
        logger.info("WebSocket connected; total connections: %s", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("WebSocket disconnected; total connections: %s", len(self._connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected clients. message must include 'type'."""
        if "type" not in message:
            logger.warning("WebSocket broadcast message missing 'type'")
        text = json.dumps(message, default=str)
        async with self._lock:
            connections = list(self._connections)
        dead = []
        for ws in connections:
            try:
                await ws.send_text(text)
            except Exception as e:
                logger.warning("WebSocket send failed: %s", e)
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    def broadcast_sync(self, message: dict[str, Any]) -> None:
        """Thread-safe: schedule broadcast on the main event loop. Call from sync tools."""
        if self._loop is None:
            logger.warning("WebSocket manager loop not set; broadcast_sync dropped")
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)
            future.result(timeout=5.0)
        except Exception as e:
            logger.warning("WebSocket broadcast_sync failed: %s", e)
            return
