"""Issues API routes."""

from __future__ import annotations
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.models import Issue, IssuePriority, IssueStatus
from core.storage import ProjectStorage

router = APIRouter(prefix="/api/projects/{project_id}/issues", tags=["issues"])


def _get_storage(project_id: str) -> ProjectStorage:
    from server.app import get_project_storage
    return get_project_storage(project_id)


class CreateIssueRequest(BaseModel):
    title: str
    priority: str = "medium"
    labels: list[str] = []
    description: str = ""
    blocked_by: list[str] = []
    workspace: str = "default"
    parent_id: str | None = None
    plan: str = ""
    source: str = "human"


class ChildIssueRequest(BaseModel):
    title: str
    description: str = ""
    plan: str = ""
    priority: str = "medium"
    labels: list[str] = []


class BatchCreateRequest(BaseModel):
    parent_id: str
    issues: list[ChildIssueRequest]
    chain_dependencies: bool = True


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
    project = storage.load_project_meta()
    prefix = project.key if project else "ISS"
    issue_id = storage.next_issue_id(prefix)
    issue = Issue.create(id=issue_id, title=req.title, priority=req.priority, labels=req.labels)
    issue.workspace = req.workspace
    issue.source = req.source
    if req.parent_id:
        issue.parent_id = req.parent_id
    for blocker_id in req.blocked_by:
        issue.add_blocker(blocker_id)
    storage.save_issue(issue)

    if req.description:
        content = f"# {issue.id}: {issue.title}\n\n## 描述\n\n{req.description}\n"
        storage.save_issue_content(issue.id, content)

    if req.plan:
        storage.save_issue_plan(issue.id, req.plan)

    # Add to board backlog
    _add_to_board(project_id, issue.id, "backlog")

    _publish(project_id, "issue_created", {"issue": issue.to_json()})

    return issue.to_json()


@router.post("/batch")
def batch_create_issues(project_id: str, req: BatchCreateRequest):
    storage = _get_storage(project_id)

    # Validate parent exists
    try:
        parent = storage.load_issue(req.parent_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Parent issue {req.parent_id} not found")

    project = storage.load_project_meta()
    prefix = project.key if project else "ISS"

    created = []
    prev_id: str | None = None

    for child_req in req.issues:
        issue_id = storage.next_issue_id(prefix)
        issue = Issue.create(
            id=issue_id,
            title=child_req.title,
            priority=child_req.priority,
            labels=child_req.labels + (parent.labels or []) + ["planned"],
        )
        issue.parent_id = req.parent_id
        issue.source = "agent"

        if req.chain_dependencies and prev_id:
            issue.add_blocker(prev_id)

        storage.save_issue(issue)

        if child_req.description:
            content = f"# {issue.id}: {issue.title}\n\n## 描述\n\n{child_req.description}\n"
            storage.save_issue_content(issue.id, content)

        if child_req.plan:
            storage.save_issue_plan(issue.id, child_req.plan)

        _add_to_board(project_id, issue.id, "backlog")
        _publish(project_id, "issue_created", {"issue": issue.to_json()})

        created.append({"id": issue.id, "title": issue.title})
        prev_id = issue_id

    # Update parent: blocked_by all children
    for item in created:
        if item["id"] not in parent.blocked_by:
            parent.blocked_by.append(item["id"])
    storage.save_issue(parent)

    return {"created": created, "parent_id": req.parent_id}


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
    result["plan"] = storage.load_issue_plan(issue_id)

    # Attach children (issues whose parent_id == this issue)
    all_issues = storage.list_issues()
    result["children"] = [
        {"id": i.id, "title": i.title, "status": i.status.value}
        for i in all_issues if i.parent_id == issue_id
    ]

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
        try:
            issue.priority = IssuePriority(req.priority)
        except ValueError:
            raise HTTPException(400, f"Invalid priority: {req.priority}")
    if req.labels is not None:
        issue.labels = req.labels
    if req.assignee is not None:
        issue.assignee = req.assignee
    if req.status is not None:
        new_status = IssueStatus(req.status)
        try:
            issue.move_to(new_status)
        except ValueError as e:
            raise HTTPException(400, str(e))

    storage.save_issue(issue)

    # Sync board if status changed
    if req.status is not None:
        _sync_board_column(project_id, issue_id, req.status)

    _publish(project_id, "issue_updated", {"issue": issue.to_json()})
    return issue.to_json()


@router.get("/{issue_id}/evidence")
def get_issue_evidence(project_id: str, issue_id: str):
    storage = _get_storage(project_id)
    evidence = storage.load_evidence(issue_id)
    return evidence


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


@router.get("/{issue_id}/plan")
def get_issue_plan(project_id: str, issue_id: str):
    storage = _get_storage(project_id)
    return {"plan": storage.load_issue_plan(issue_id)}


@router.put("/{issue_id}/plan")
def update_issue_plan(project_id: str, issue_id: str, body: dict):
    storage = _get_storage(project_id)
    storage.save_issue_plan(issue_id, body.get("plan", ""))
    return {"ok": True}


@router.delete("/{issue_id}")
def delete_issue(project_id: str, issue_id: str):
    storage = _get_storage(project_id)
    issue_dir = storage.issues_dir / issue_id
    if not issue_dir.exists():
        raise HTTPException(404, f"Issue {issue_id} not found")

    import shutil
    shutil.rmtree(issue_dir)

    # Remove from board
    _remove_from_board(project_id, issue_id)

    _publish(project_id, "issue_deleted", {"issue_id": issue_id})
    return {"ok": True}


# --- Run log endpoints ---

@router.get("/{issue_id}/logs")
def list_issue_logs(project_id: str, issue_id: str):
    storage = _get_storage(project_id)
    return {"runs": storage.list_run_ids(issue_id)}


@router.get("/{issue_id}/logs/{run_id}")
def get_issue_log(project_id: str, issue_id: str, run_id: str):
    storage = _get_storage(project_id)
    entries = storage.load_run_log(issue_id, run_id)
    return {"run_id": run_id, "entries": entries}


@router.get("/{issue_id}/stats")
def get_issue_stats(project_id: str, issue_id: str):
    storage = _get_storage(project_id)
    runs = storage.list_all_run_stats(issue_id)
    total_cost = sum(r.get("cost_usd", 0) for r in runs)
    total_duration = sum(r.get("duration_ms", 0) for r in runs)
    total_turns = sum(r.get("details", [{}])[0].get("num_turns", 0) if r.get("details") else 0 for r in runs)
    # Build per-run summary
    per_run = []
    for i, r in enumerate(runs):
        details = r.get("details", [])
        run_turns = sum(d.get("num_turns", 0) for d in details)
        run_tokens_in = sum(d.get("usage", {}).get("input_tokens", 0) for d in details)
        run_tokens_out = sum(d.get("usage", {}).get("output_tokens", 0) for d in details)
        per_run.append({
            "run_id": f"run-{i+1:03d}",
            "success": r.get("success", False),
            "attempts": r.get("attempts", 0),
            "cost_usd": r.get("cost_usd", 0),
            "duration_ms": r.get("duration_ms", 0),
            "turns": run_turns,
            "tokens_in": run_tokens_in,
            "tokens_out": run_tokens_out,
        })
    return {
        "total_runs": len(runs),
        "total_cost_usd": total_cost,
        "total_duration_ms": total_duration,
        "runs": per_run,
    }


# --- Board helpers ---

def _add_to_board(project_id: str, issue_id: str, column: str):
    from server.app import get_project_storage
    storage = get_project_storage(project_id)
    board_file = storage.root / "board.json"
    if board_file.exists():
        data = json.loads(board_file.read_text())
        for col in data["columns"]:
            if col["id"] == column:
                if issue_id not in col["issues"]:
                    col["issues"].append(issue_id)
                break
        board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _remove_from_board(project_id: str, issue_id: str):
    from server.app import get_project_storage
    storage = get_project_storage(project_id)
    board_file = storage.root / "board.json"
    if not board_file.exists():
        return
    data = json.loads(board_file.read_text())
    for col in data["columns"]:
        if issue_id in col["issues"]:
            col["issues"].remove(issue_id)
    board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _sync_board_column(project_id: str, issue_id: str, status: str):
    """Move issue to the board column matching its new status."""
    from server.app import get_project_storage
    storage = get_project_storage(project_id)
    board_file = storage.root / "board.json"
    if not board_file.exists():
        return
    data = json.loads(board_file.read_text())
    # Remove from all columns
    for col in data["columns"]:
        if issue_id in col["issues"]:
            col["issues"].remove(issue_id)
    # Add to target column
    for col in data["columns"]:
        if col["id"] == status:
            col["issues"].append(issue_id)
            break
    board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _publish(project_id: str, event_type: str, data: dict):
    from server.ws import ws_manager
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(ws_manager.broadcast(project_id, {"type": event_type, "data": data}))
    except RuntimeError:
        pass
