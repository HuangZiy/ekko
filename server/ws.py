"""WebSocket connection manager for real-time updates."""

from __future__ import annotations
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """Per-project WebSocket connection registry."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, project_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[project_id].append(ws)

    def disconnect(self, project_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(project_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, project_id: str, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(project_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(project_id, ws)


ws_manager = ConnectionManager()
