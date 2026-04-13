"""FastAPI application — Ekko backend."""

from __future__ import annotations
import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.routes import issues, board, projects, reviews, run, fs, uploads
from server.routes import ws as ws_route

_harness_root: Path | None = None


def get_harness_root() -> Path:
    if _harness_root is None:
        from config import ARTIFACTS_DIR
        return ARTIFACTS_DIR
    return _harness_root


def get_project_storage(project_id: str):
    """Get ProjectStorage for a project via registry. Used by all route handlers."""
    from core.storage import PlatformStorage
    from fastapi import HTTPException
    platform = PlatformStorage(get_harness_root())
    try:
        return platform.get_project_storage(project_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Project {project_id} not found")


def _move_board_column(storage, issue_id: str, target_col: str) -> None:
    board_file = storage.root / "board.json"
    if not board_file.exists():
        return
    data = json.loads(board_file.read_text())
    for col in data["columns"]:
        if issue_id in col["issues"]:
            col["issues"].remove(issue_id)
    for col in data["columns"]:
        if col["id"] == target_col:
            col["issues"].append(issue_id)
            break
    board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _reset_stuck_issues() -> None:
    """Reset any in_progress issues back to todo."""
    try:
        from core.models import IssueStatus
        from core.storage import PlatformStorage
        root = get_harness_root()
        platform = PlatformStorage(root)
        for pid, _ in platform.list_projects():
            storage = platform.get_project_storage(pid)
            for issue in storage.list_issues():
                if issue.status == IssueStatus.IN_PROGRESS:
                    issue.move_to(IssueStatus.TODO)
                    storage.save_issue(issue)
                    _move_board_column(storage, issue.id, "todo")
                elif issue.status == IssueStatus.PLANNING:
                    issue.move_to(IssueStatus.BACKLOG)
                    storage.save_issue(issue)
                    _move_board_column(storage, issue.id, "backlog")
    except Exception:
        pass


def create_app(harness_root: Path | None = None) -> FastAPI:
    global _harness_root
    if harness_root:
        _harness_root = harness_root

    app = FastAPI(title="Ekko", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(projects.router)
    app.include_router(issues.router)
    app.include_router(board.router)
    app.include_router(reviews.router)
    app.include_router(run.router)
    app.include_router(fs.router)
    app.include_router(uploads.router)
    app.include_router(ws_route.router)

    @app.on_event("startup")
    def reset_stuck_issues():
        """Reset any in_progress issues back to todo on server start."""
        _reset_stuck_issues()

    @app.on_event("startup")
    async def start_issue_watchdog():
        """Periodic check for stuck in_progress issues with no active run."""
        async def watchdog():
            while True:
                await asyncio.sleep(30)
                try:
                    from server.routes.run import _cancel_events
                    from server.ws import ws_manager
                    from core.models import IssueStatus
                    from core.storage import PlatformStorage
                    from datetime import datetime, timezone
                    root = get_harness_root()
                    platform = PlatformStorage(root)
                    now = datetime.now(timezone.utc)
                    for pid, _ in platform.list_projects():
                        storage = platform.get_project_storage(pid)
                        for issue in storage.list_issues():
                            if issue.status == IssueStatus.IN_PROGRESS and issue.id not in _cancel_events:
                                # Only reset if stuck for > 60s
                                try:
                                    updated = datetime.fromisoformat(issue.updated_at)
                                    age = (now - updated).total_seconds()
                                except Exception:
                                    age = 999
                                if age < 60:
                                    continue
                                issue.move_to(IssueStatus.TODO)
                                storage.save_issue(issue)
                                _move_board_column(storage, issue.id, "todo")
                                await ws_manager.broadcast(pid, {
                                    "type": "issue_updated", "data": {"issue": issue.to_json()},
                                })
                except Exception:
                    pass
        asyncio.create_task(watchdog())

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


def run_server(host: str = "127.0.0.1", port: int = 8080, harness_root: Path | None = None):
    import uvicorn
    app = create_app(harness_root)
    uvicorn.run(app, host=host, port=port)
