"""Run API routes — trigger issue execution from the Web UI."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from core.storage import ProjectStorage

router = APIRouter(prefix="/api/projects/{project_id}/run", tags=["run"])


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
    from server.sse import event_bus
    from core.ralph_loop import run_issue_loop, run_board, find_ready_issues
    from config import WORKSPACE_DIR

    project_dir = get_harness_root() / "projects" / project_id
    storage = ProjectStorage(project_dir)

    async def _publish(event_type: str, data: dict) -> None:
        await event_bus.publish(event_type, data)

    if issue_id:
        try:
            issue = storage.load_issue(issue_id)
        except FileNotFoundError:
            await _publish("run_error", {"issue_id": issue_id, "error": "Issue not found"})
            return

        await _publish("agent_started", {"issue_id": issue_id, "title": issue.title})
        stats = await run_issue_loop(issue, storage, WORKSPACE_DIR)
        await _publish("agent_done", {"issue_id": issue_id, "success": stats["success"], "cost_usd": stats.get("cost_usd", 0)})
    else:
        ready = find_ready_issues(storage)
        if not ready:
            await _publish("run_error", {"error": "No actionable issues"})
            return

        for issue in ready:
            await _publish("agent_started", {"issue_id": issue.id, "title": issue.title})
            stats = await run_issue_loop(issue, storage, WORKSPACE_DIR)
            await _publish("agent_done", {"issue_id": issue.id, "success": stats["success"], "cost_usd": stats.get("cost_usd", 0)})


@router.post("")
async def run_issues(project_id: str, req: RunRequest, background_tasks: BackgroundTasks):
    _get_storage(project_id)  # validate project exists
    background_tasks.add_task(_run_in_background, project_id, req.issue_id)
    return {"ok": True, "issue_id": req.issue_id}
