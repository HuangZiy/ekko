"""Projects API routes."""

from __future__ import annotations
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.models import Project, Board
from core.storage import PlatformStorage, ProjectStorage

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get_platform() -> PlatformStorage:
    from server.app import get_harness_root
    return PlatformStorage(get_harness_root())


class CreateProjectRequest(BaseModel):
    name: str
    workspace_path: str


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    workspace_path: str | None = None
    key: str | None = None


class SwitchProjectRequest(BaseModel):
    project_id: str


@router.get("")
def list_projects():
    platform = _get_platform()
    active_id = platform.get_active_project_id()
    projects = platform.list_projects()
    result = []
    for pid, project in projects:
        from dataclasses import asdict
        d = asdict(project)
        d["_active"] = pid == active_id
        # Add issue counts
        store = platform.get_project_storage(pid)
        issues = store.list_issues()
        by_status = {}
        for i in issues:
            by_status[i.status.value] = by_status.get(i.status.value, 0) + 1
        d["issue_counts"] = by_status
        d["total_issues"] = len(issues)
        result.append(d)
    return result


@router.post("")
def create_project(req: CreateProjectRequest):
    platform = _get_platform()
    project, store = platform.create_project(name=req.name, workspace_path=req.workspace_path)
    from dataclasses import asdict
    return asdict(project)


@router.get("/active")
def get_active_project():
    platform = _get_platform()
    active_id = platform.get_active_project_id()
    if not active_id:
        return {"id": None}
    store = platform.get_project_storage(active_id)
    project = store.load_project_meta()
    if not project:
        return {"id": None}
    from dataclasses import asdict
    return asdict(project)


@router.post("/active")
def switch_active_project(req: SwitchProjectRequest):
    platform = _get_platform()
    if platform.switch_project(req.project_id):
        return {"ok": True, "active": req.project_id}
    raise HTTPException(404, f"Project {req.project_id} not found")


@router.get("/{project_id}")
def get_project(project_id: str):
    platform = _get_platform()
    store = platform.get_project_storage(project_id)
    project = store.load_project_meta()
    if not project:
        raise HTTPException(404, f"Project {project_id} not found")
    from dataclasses import asdict
    d = asdict(project)
    issues = store.list_issues()
    by_status = {}
    for i in issues:
        by_status[i.status.value] = by_status.get(i.status.value, 0) + 1
    d["issue_counts"] = by_status
    d["total_issues"] = len(issues)
    # Aggregate run stats across all issues
    total_cost = 0.0
    total_duration = 0
    total_runs = 0
    for i in issues:
        for rs in store.list_all_run_stats(i.id):
            total_runs += 1
            total_cost += rs.get("cost_usd", 0)
            total_duration += rs.get("duration_ms", 0)
    d["run_stats"] = {
        "total_runs": total_runs,
        "total_cost_usd": round(total_cost, 4),
        "total_duration_ms": total_duration,
    }
    return d


@router.delete("/{project_id}")
def delete_project(project_id: str):
    platform = _get_platform()
    project_dir = platform.projects_dir / project_id
    if not project_dir.exists():
        raise HTTPException(404, f"Project {project_id} not found")
    import shutil
    shutil.rmtree(project_dir)
    # If deleted the active project, clear active
    if platform.get_active_project_id() == project_id:
        active_file = platform.root / "active_project"
        if active_file.exists():
            active_file.unlink()
    return {"ok": True}


@router.patch("/{project_id}")
def update_project(project_id: str, req: UpdateProjectRequest):
    platform = _get_platform()
    store = platform.get_project_storage(project_id)
    project = store.load_project_meta()
    if not project:
        raise HTTPException(404, f"Project {project_id} not found")

    if req.name is not None:
        project.name = req.name
    if req.workspace_path is not None:
        project.workspaces = [req.workspace_path]
    if req.key is not None:
        new_key = req.key.strip().upper()
        if not new_key:
            raise HTTPException(400, "Issue key prefix cannot be empty")
        project.key = new_key

    store.save_project_meta(project)
    from dataclasses import asdict
    return asdict(project)
