"""Run API routes — trigger issue execution from the Web UI."""

from __future__ import annotations
import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from core.storage import ProjectStorage

router = APIRouter(prefix="/api/projects/{project_id}/run", tags=["run"])

# Active cancellation events — issue_id → asyncio.Event
_cancel_events: dict[str, asyncio.Event] = {}


def request_cancel(issue_id: str) -> None:
    """Signal cancellation for a running issue. Called from WS route."""
    ev = _cancel_events.get(issue_id)
    if ev:
        ev.set()


def get_cancel_event(issue_id: str) -> asyncio.Event:
    """Get or create a cancel event for an issue run."""
    if issue_id not in _cancel_events:
        _cancel_events[issue_id] = asyncio.Event()
    return _cancel_events[issue_id]


def clear_cancel(issue_id: str) -> None:
    """Clean up cancel event after run completes."""
    _cancel_events.pop(issue_id, None)


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
    from pathlib import Path

    project_dir = get_harness_root() / "projects" / project_id
    storage = ProjectStorage(project_dir)

    # Resolve workspace from project metadata
    project = storage.load_project_meta()
    if not project or not project.workspaces:
        await ws_manager.broadcast(project_id, {
            "type": "run_error", "data": {"error": "Project has no workspace configured"},
        })
        return
    workspace = Path(project.workspaces[0]).resolve()

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

        cancel_event = get_cancel_event(issue_id)
        run_counter = len(storage.list_run_ids(issue_id)) + 1
        await ws_manager.broadcast(project_id, {
            "type": "agent_started", "data": {"issue_id": issue_id, "title": issue.title},
        })
        stats = await run_issue_loop(issue, storage, workspace, on_event=on_event, cancel_event=cancel_event)
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
            cancel_event = get_cancel_event(issue.id)
            run_counter = len(storage.list_run_ids(issue.id)) + 1
            await ws_manager.broadcast(project_id, {
                "type": "agent_started", "data": {"issue_id": issue.id, "title": issue.title},
            })
            stats = await run_issue_loop(issue, storage, workspace, on_event=on_event, cancel_event=cancel_event)
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


class CancelRequest(BaseModel):
    issue_id: str


@router.post("/cancel")
async def cancel_issue(project_id: str, req: CancelRequest):
    storage = _get_storage(project_id)
    issue_id = req.issue_id

    # Signal any active run
    request_cancel(issue_id)

    # If no active run is listening, force the status change directly
    if issue_id not in _cancel_events:
        from core.models import IssueStatus
        try:
            issue = storage.load_issue(issue_id)
            if issue.status == IssueStatus.IN_PROGRESS:
                issue.move_to(IssueStatus.FAILED)
                issue.move_to(IssueStatus.TODO)
                storage.save_issue(issue)
                # Update board: move to todo column
                import json
                board_file = storage.root / "board.json"
                if board_file.exists():
                    data = json.loads(board_file.read_text())
                    for col in data["columns"]:
                        if issue_id in col["issues"]:
                            col["issues"].remove(issue_id)
                    for col in data["columns"]:
                        if col["id"] == "todo":
                            col["issues"].append(issue_id)
                            break
                    board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                # Notify via WS
                from server.ws import ws_manager
                await ws_manager.broadcast(project_id, {
                    "type": "issue_updated", "data": {"issue": issue.to_json()},
                })
        except FileNotFoundError:
            pass

    return {"ok": True, "issue_id": issue_id}
