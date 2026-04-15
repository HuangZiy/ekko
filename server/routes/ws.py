"""WebSocket endpoint for real-time project events."""

from __future__ import annotations
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.ws import ws_manager

router = APIRouter()

HEARTBEAT_INTERVAL = 20  # seconds


@router.websocket("/api/projects/{project_id}/ws")
async def project_websocket(project_id: str, ws: WebSocket):
    await ws_manager.connect(project_id, ws)

    # Heartbeat task
    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await ws.send_json({"type": "ping"})
        except Exception:
            pass

    hb_task = asyncio.create_task(heartbeat())

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")
            if msg_type == "pong":
                pass  # heartbeat response, no action needed
            elif msg_type == "cancel_agent":
                issue_id = data.get("issue_id")
                if issue_id:
                    from server.routes.run import request_cancel
                    request_cancel(issue_id)
            elif msg_type == "planning_input":
                issue_id = data.get("issue_id")
                if issue_id:
                    from server.routes.planning import handle_planning_input
                    await handle_planning_input(issue_id, data.get("data", ""))
            elif msg_type == "planning_resize":
                issue_id = data.get("issue_id")
                if issue_id:
                    from server.routes.planning import handle_planning_resize
                    await handle_planning_resize(
                        issue_id,
                        data.get("cols", 80),
                        data.get("rows", 24),
                    )
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hb_task.cancel()
        ws_manager.disconnect(project_id, ws)
