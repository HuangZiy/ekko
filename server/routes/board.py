"""Board API routes."""

from __future__ import annotations
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.models import Board
from core.storage import ProjectStorage

router = APIRouter(prefix="/api/projects/{project_id}/board", tags=["board"])


def _get_project_dir(project_id: str) -> Path:
    from server.app import get_harness_root
    d = get_harness_root() / "projects" / project_id
    if not d.exists():
        raise HTTPException(404, f"Project {project_id} not found")
    return d


@router.get("")
def get_board(project_id: str):
    project_dir = _get_project_dir(project_id)
    board_file = project_dir / "board.json"
    if not board_file.exists():
        board = Board.create()
        data = {"columns": [{"id": c.id, "name": c.name, "issues": c.issues} for c in board.columns]}
    else:
        data = json.loads(board_file.read_text())

    # Auto-heal: ensure every issue appears on the board
    storage = ProjectStorage(project_dir)
    all_issues = storage.list_issues()
    on_board = set()
    for col in data["columns"]:
        on_board.update(col["issues"])

    dirty = False
    for issue in all_issues:
        if issue.id not in on_board:
            # Place in column matching its status
            target_col = issue.status.value
            for col in data["columns"]:
                if col["id"] == target_col:
                    col["issues"].append(issue.id)
                    dirty = True
                    break

    if dirty:
        board_file.parent.mkdir(parents=True, exist_ok=True)
        board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    return data


class MoveIssueRequest(BaseModel):
    to_column: str


@router.post("/move/{issue_id}")
def move_issue_on_board(project_id: str, issue_id: str, req: MoveIssueRequest):
    project_dir = _get_project_dir(project_id)
    board_file = project_dir / "board.json"

    board_data = json.loads(board_file.read_text()) if board_file.exists() else {"columns": []}

    # Remove from current column
    for col in board_data["columns"]:
        if issue_id in col["issues"]:
            col["issues"].remove(issue_id)

    # Add to target column
    target = next((c for c in board_data["columns"] if c["id"] == req.to_column), None)
    if not target:
        raise HTTPException(400, f"Column {req.to_column} not found")
    target["issues"].append(issue_id)

    board_file.write_text(json.dumps(board_data, indent=2, ensure_ascii=False))

    # Also update issue status to match column
    storage = ProjectStorage(project_dir)
    try:
        issue = storage.load_issue(issue_id)
        from core.models import IssueStatus
        status_map = {
            "backlog": IssueStatus.BACKLOG,
            "todo": IssueStatus.TODO,
            "in_progress": IssueStatus.IN_PROGRESS,
            "agent_done": IssueStatus.AGENT_DONE,
            "rejected": IssueStatus.REJECTED,
            "human_done": IssueStatus.HUMAN_DONE,
        }
        new_status = status_map.get(req.to_column)
        if new_status and issue.status != new_status:
            issue.move_to(new_status)
            storage.save_issue(issue)
    except FileNotFoundError:
        pass  # issue meta might not exist yet
    except ValueError as e:
        # Revert board.json — put issue back in source column
        board_data2 = json.loads(board_file.read_text()) if board_file.exists() else board_data
        for col in board_data2["columns"]:
            if issue_id in col["issues"]:
                col["issues"].remove(issue_id)
        # Find the column matching the issue's actual status
        actual_col = {v.value: k for k, v in status_map.items()}.get(issue.status.value)
        if actual_col:
            for col in board_data2["columns"]:
                if col["id"] == actual_col:
                    if issue_id not in col["issues"]:
                        col["issues"].append(issue_id)
                    break
        board_file.write_text(json.dumps(board_data2, indent=2, ensure_ascii=False))
        raise HTTPException(400, str(e))

    # Publish WebSocket event
    from server.ws import ws_manager
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(ws_manager.broadcast(project_id, {"type": "issue_moved", "data": {"issue_id": issue_id, "to_column": req.to_column}}))
    except RuntimeError:
        pass

    return {"ok": True}
