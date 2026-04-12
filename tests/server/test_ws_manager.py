"""Tests for WebSocket ConnectionManager."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from server.ws import ConnectionManager


@pytest.fixture
def manager():
    return ConnectionManager()


@pytest.mark.asyncio
async def test_connect_and_disconnect(manager):
    ws = AsyncMock()
    await manager.connect("PRJ-1", ws)
    assert ws in manager._connections["PRJ-1"]
    manager.disconnect("PRJ-1", ws)
    assert ws not in manager._connections["PRJ-1"]


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_project_connections(manager):
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    ws_other = AsyncMock()
    await manager.connect("PRJ-1", ws1)
    await manager.connect("PRJ-1", ws2)
    await manager.connect("PRJ-2", ws_other)

    await manager.broadcast("PRJ-1", {"type": "ping"})

    ws1.send_json.assert_called_once_with({"type": "ping"})
    ws2.send_json.assert_called_once_with({"type": "ping"})
    ws_other.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_removes_dead_connections(manager):
    ws_alive = AsyncMock()
    ws_dead = AsyncMock()
    ws_dead.send_json.side_effect = Exception("connection closed")
    await manager.connect("PRJ-1", ws_alive)
    await manager.connect("PRJ-1", ws_dead)

    await manager.broadcast("PRJ-1", {"type": "test"})

    assert ws_dead not in manager._connections["PRJ-1"]
    assert ws_alive in manager._connections["PRJ-1"]


@pytest.mark.asyncio
async def test_disconnect_nonexistent_is_noop(manager):
    ws = AsyncMock()
    manager.disconnect("PRJ-1", ws)  # should not raise
