"""SSE event bus for real-time updates to the Web UI."""

from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone


class EventBus:
    """Simple pub/sub for SSE events. One global instance per server."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def publish(self, event_type: str, data: dict) -> None:
        payload = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass  # drop if consumer is too slow


# Global singleton
event_bus = EventBus()
