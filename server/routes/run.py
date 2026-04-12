"""Run API routes — trigger issue execution from the Web UI."""

from __future__ import annotations
from typing import Set

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from core.storage import ProjectStorage

router = APIRouter(prefix="/api/projects/{project_id}/run", tags=["run"])

# Active cancellation flags — issue_ids that should be cancelled
_cancel_flags: Set[str] = set()


def cancel_agent(issue_id: str) -> None:
    """Set cancellation flag for an issue. Called from WS route."""
    _cancel_flags.add(issue_id)


def is_cancelled(issue_id: str) -> bool:
    """Check if an issue has been cancelled."""
    return issue_id in _cancel_flags


def clear_cancel(issue_id: str) -> None:
    """Clear cancellation flag after run completes."""
    _cancel_flags.discard(issue_id)


def _get_storage(project_id: str) -> ProjectStorage:
    from server.app import get_harness_root
    project_dir = get_harness_root() / "projects" / project_id
    if not project_dir.exists():
        raise HTTPException(404, f"Project {project_id} not found")
    return ProjectStorage(project_dir)


class RunRequest(BaseModel):
    issue_id: str | None = None


async def _run_in_background(project_id: str, issue_id: str | None) -> None:
    from server.app import get_harness_root
    from server.ws import ws_manager
    from core.ralph_loop import run_issue_loop, find_ready_issues
    from config import WORKSPACE_DIR

    project_dir = get_harness_root() / "projects" / project_id
    storage = ProjectStorage(project_dir)

    run_counter = 0

    async def on_event(event: dict) -> None:
        """Broadcast event via WebSocket and persist to JSONL log."""
        await ws_manager.broadcast(project_id, event)
        # Persist agent events to run log
        evt_type = event.get("type", "")
        evt_issue_id = event.get("issue_id")
        if evt_issue_id and evt_type.startswith("agent_"):
            storage.append_run_log(evt_issue_id, f"run-{run_counter:03d}", event)

    if issue_id:
        try:
            issue = storage.load_issue(issue_id)
        except FileNotFoundError:
            await ws_manager.broadcast(project_id, {
                "type": "run_error", "data": {"issue_id": issue_id, "error": "Issue not found"},
            })
            return

        run_counter = len(storage.list_run_ids(issue_id)) + 1
        await ws_manager.broadcast(project_id, {
            "type": "agent_started", "data": {"issue_id": issue_id, "title": issue.title},
        })
        stats = await run_issue_loop(issue, storage, WORKSPACE_DIR, on_event=on_event)
        clear_cancel(issue_id)
        await ws_manager.broadcast(project_id, {
            "type": "agent_done", "data": {
                "issue_id": issue_id, "success": stats["success"],
                "cost_usd": stats.get("cost_usd", 0),
            },
        })
    else:
        ready = find_ready_issues(storage)
        if not ready:
            await ws_manager.broadcast(project_id, {
                "type": "run_error", "data": {"error": "No actionable issues"},
            })
            return

        for issue in ready:
            run_counter = len(storage.list_run_ids(issue.id)) + 1
            await ws_manager.broadcast(project_id, {
                "type": "agent_started", "data": {"issue_id": issue.id, "title": issue.title},
            })
            stats = await run_issue_loop(issue, storage, WORKSPACE_DIR, on_event=on_event)
            clear_cancel(issue.id)
            await ws_manager.broadcast(project_id, {
                "type": "agent_done", "data": {
                    "issue_id": issue.id, "success": stats["success"],
                    "cost_usd": stats.get("cost_usd", 0),
                },
            })


@router.post("")
async def run_issues(project_id: str, req: RunRequest, background_tasks: BackgroundTasks):
    _get_storage(project_id)  # validate project exists
    background_tasks.add_task(_run_in_background, project_id, req.issue_id)
    return {"ok": True, "issue_id": req.issue_id}
