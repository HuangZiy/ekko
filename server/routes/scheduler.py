"""Scheduler API routes — start/stop/configure auto-dispatch per project."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/projects/{project_id}/scheduler", tags=["scheduler"])


class SchedulerStartRequest(BaseModel):
    interval: int | None = None
    max_parallel: int | None = None


class SchedulerUpdateRequest(BaseModel):
    interval: int | None = None
    max_parallel: int | None = None


def _get_storage(project_id: str):
    from server.app import get_project_storage
    return get_project_storage(project_id)


@router.get("")
async def get_scheduler_status(project_id: str):
    """Get current scheduler status for a project."""
    _get_storage(project_id)  # validate project exists
    from core.scheduler import scheduler
    return scheduler.status(project_id)


@router.post("/start")
async def start_scheduler(project_id: str, req: SchedulerStartRequest | None = None):
    """Start auto-dispatch polling for a project."""
    _get_storage(project_id)  # validate project exists

    from core.scheduler import scheduler
    from server.ws import ws_manager

    async def on_event(event: dict) -> None:
        await ws_manager.broadcast(project_id, event)

    body = req or SchedulerStartRequest()
    status = await scheduler.start(
        project_id,
        interval=body.interval,
        max_parallel=body.max_parallel,
        on_event=on_event,
    )

    # Broadcast scheduler status change
    await ws_manager.broadcast(project_id, {
        "type": "scheduler_status",
        "data": status,
    })

    return status


@router.post("/stop")
async def stop_scheduler(project_id: str):
    """Stop auto-dispatch polling for a project."""
    _get_storage(project_id)  # validate project exists

    from core.scheduler import scheduler
    from server.ws import ws_manager

    status = await scheduler.stop(project_id)

    await ws_manager.broadcast(project_id, {
        "type": "scheduler_status",
        "data": status,
    })

    return status


@router.patch("")
async def update_scheduler(project_id: str, req: SchedulerUpdateRequest):
    """Update scheduler parameters (interval, max_parallel) without starting/stopping."""
    _get_storage(project_id)  # validate project exists

    from core.scheduler import scheduler
    from server.ws import ws_manager

    status = scheduler.update_settings(
        project_id,
        interval=req.interval,
        max_parallel=req.max_parallel,
    )

    await ws_manager.broadcast(project_id, {
        "type": "scheduler_status",
        "data": status,
    })

    return status
