"""FastAPI application — Ekko backend."""

from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.routes import issues, board, projects, reviews, run, fs
from server.routes import ws as ws_route

_harness_root: Path | None = None


def get_harness_root() -> Path:
    if _harness_root is None:
        from config import ARTIFACTS_DIR
        return ARTIFACTS_DIR
    return _harness_root


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
    app.include_router(ws_route.router)

    @app.on_event("startup")
    def reset_stuck_issues():
        """Reset any in_progress issues back to todo on server start."""
        try:
            from core.models import IssueStatus
            from core.storage import PlatformStorage
            import json
            root = get_harness_root()
            platform = PlatformStorage(root)
            for pid, _ in platform.list_projects():
                storage = platform.get_project_storage(pid)
                for issue in storage.list_issues():
                    if issue.status == IssueStatus.IN_PROGRESS:
                        issue.move_to(IssueStatus.TODO)
                        storage.save_issue(issue)
                        # Fix board column
                        board_file = storage.root / "board.json"
                        if board_file.exists():
                            data = json.loads(board_file.read_text())
                            for col in data["columns"]:
                                if issue.id in col["issues"]:
                                    col["issues"].remove(issue.id)
                            for col in data["columns"]:
                                if col["id"] == "todo":
                                    col["issues"].append(issue.id)
                                    break
                            board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception:
            pass  # best-effort on startup

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


def run_server(host: str = "127.0.0.1", port: int = 8080, harness_root: Path | None = None):
    import uvicorn
    app = create_app(harness_root)
    uvicorn.run(app, host=host, port=port)
