"""FastAPI application — Ekko backend."""

from __future__ import annotations
import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from server.sse import event_bus
from server.routes import issues, board, projects, reviews, run, fs

# Harness root — configurable, defaults to workspace/.harness
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

    @app.get("/api/projects/{project_id}/events")
    async def sse_events(project_id: str):
        queue = event_bus.subscribe()

        async def stream():
            try:
                while True:
                    event = await queue.get()
                    yield {"event": event["type"], "data": json.dumps(event["data"])}
            except asyncio.CancelledError:
                pass
            finally:
                event_bus.unsubscribe(queue)

        return EventSourceResponse(stream())

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


def run_server(host: str = "127.0.0.1", port: int = 8080, harness_root: Path | None = None):
    import uvicorn
    app = create_app(harness_root)
    uvicorn.run(app, host=host, port=port)
