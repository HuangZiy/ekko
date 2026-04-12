"""Issues API routes."""

from __future__ import annotations
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.models import Issue, IssueStatus
from core.storage import ProjectStorage

router = APIRouter(prefix="/api/projects/{project_id}/issues", tags=["issues"])


def _get_storage(project_id: str) -> ProjectStorage:
    from server.app import get_harness_root
    project_dir = get_harness_root() / "projects" / project_id
    if not project_dir.exists():
        raise HTTPException(404, f"Project {project_id} not found")
    return ProjectStorage(project_dir)


class CreateIssueRequest(BaseModel):
    title: str
    priority: str = "medium"
    labels: list[str] = []
    description: str = ""
    blocked_by: list[str] = []
    workspace: str = "default"


class UpdateIssueRequest(BaseModel):
    title: str | None = None
    priority: str | None = None
    labels: list[str] | None = None
    status: str | None = None
    assignee: str | None = None


@router.get("")
def list_issues(project_id: str, status: str | None = None):
    storage = _get_storage(project_id)
    issues = storage.list_issues()
    if status:
        issues = [i for i in issues if i.status.value == status]
    return [i.to_json() for i in issues]


@router.post("")
def create_issue(project_id: str, req: CreateIssueRequest):
    storage = _get_storage(project_id)
    issue = Issue.create(title=req.title, priority=req.priority, labels=req.labels)
    issue.workspace = req.workspace
    for blocker_id in req.blocked_by:
        issue.add_blocker(blocker_id)
    storage.save_issue(issue)

    if req.description:
        content = f"# {issue.id}: {issue.title}\n\n## 描述\n\n{req.description}\n"
        storage.save_issue_content(issue.id, content)

    # Add to board backlog
    _add_to_board(project_id, issue.id, "backlog")

    # SSE
    _publish("issue_created", {"issue": issue.to_json()})

    return issue.to_json()


@router.get("/{issue_id}")
def get_issue(project_id: str, issue_id: str):
    storage = _get_storage(project_id)
    try:
        issue = storage.load_issue(issue_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Issue {issue_id} not found")

    result = issue.to_json()
    try:
        result["content"] = storage.load_issue_content(issue_id)
    except FileNotFoundError:
        result["content"] = ""
    return result


@router.patch("/{issue_id}")
def update_issue(project_id: str, issue_id: str, req: UpdateIssueRequest):
    storage = _get_storage(project_id)
    try:
        issue = storage.load_issue(issue_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Issue {issue_id} not found")

    if req.title is not None:
        issue.title = req.title
    if req.priority is not None:
        issue.priority = req.priority
    if req.labels is not None:
        issue.labels = req.labels
    if req.assignee is not None:
        issue.assignee = req.assignee
    if req.status is not None:
        new_status = IssueStatus(req.status)
        issue.move_to(new_status)

    storage.save_issue(issue)
    _publish("issue_updated", {"issue": issue.to_json()})
    return issue.to_json()


@router.get("/{issue_id}/content")
def get_issue_content(project_id: str, issue_id: str):
    storage = _get_storage(project_id)
    try:
        return {"content": storage.load_issue_content(issue_id)}
    except FileNotFoundError:
        return {"content": ""}


@router.put("/{issue_id}/content")
def update_issue_content(project_id: str, issue_id: str, body: dict):
    storage = _get_storage(project_id)
    storage.save_issue_content(issue_id, body.get("content", ""))
    return {"ok": True}


def _add_to_board(project_id: str, issue_id: str, column: str):
    from server.app import get_harness_root
    board_file = get_harness_root() / "projects" / project_id / "board.json"
    if board_file.exists():
        data = json.loads(board_file.read_text())
        for col in data["columns"]:
            if col["id"] == column:
                if issue_id not in col["issues"]:
                    col["issues"].append(issue_id)
                break
        board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _publish(event_type: str, data: dict):
    from server.sse import event_bus
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(event_bus.publish(event_type, data))
    except RuntimeError:
        pass
