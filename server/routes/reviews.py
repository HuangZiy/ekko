"""Review API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.review import approve_issue, reject_issue
from core.storage import ProjectStorage

router = APIRouter(prefix="/api/projects/{project_id}/issues/{issue_id}/review", tags=["reviews"])


def _get_storage(project_id: str) -> ProjectStorage:
    from server.app import get_project_storage
    return get_project_storage(project_id)


class ReviewRequest(BaseModel):
    approved: bool
    comment: str = ""


@router.post("")
def review_issue(project_id: str, issue_id: str, req: ReviewRequest):
    storage = _get_storage(project_id)

    try:
        if req.approved:
            approve_issue(issue_id, storage)
        else:
            reject_issue(issue_id, storage, comment=req.comment)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(400, str(e))

    # Update board
    from server.routes.board import _get_project_dir
    import json
    project_dir = _get_project_dir(project_id)
    board_file = project_dir / "board.json"
    if board_file.exists():
        data = json.loads(board_file.read_text())
        # Remove from current column
        for col in data["columns"]:
            if issue_id in col["issues"]:
                col["issues"].remove(issue_id)
        # Add to new column
        target_col = "human_done" if req.approved else "todo"
        for col in data["columns"]:
            if col["id"] == target_col:
                col["issues"].append(issue_id)
                break
        board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # WebSocket
    from server.ws import ws_manager
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        event_type = "issue_approved" if req.approved else "issue_rejected"
        loop.create_task(ws_manager.broadcast(project_id, {"type": event_type, "data": {"issue_id": issue_id}}))
    except RuntimeError:
        pass

    return {"ok": True, "action": "approved" if req.approved else "rejected"}
