"""Planning terminal session management — PTY-based Claude Code subprocess."""

from __future__ import annotations

import asyncio
import os
import pty
import signal
import struct
import fcntl
import termios
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.models import IssueStatus
from core.storage import ProjectStorage
from server.ws import ws_manager

router = APIRouter(prefix="/api/projects/{project_id}/planning", tags=["planning"])


@dataclass
class PlanningSession:
    issue_id: str
    project_id: str
    process: asyncio.subprocess.Process
    master_fd: int
    read_task: asyncio.Task | None = None
    started_at: str = ""
    content_snapshot: str = ""


# Global session registry: issue_id -> session
_sessions: dict[str, PlanningSession] = {}


def _get_storage(project_id: str) -> ProjectStorage:
    from server.app import get_project_storage
    return get_project_storage(project_id)


async def _read_pty_loop(session: PlanningSession) -> None:
    """Read PTY master fd in a thread and broadcast output via WebSocket."""
    loop = asyncio.get_event_loop()
    try:
        while True:
            try:
                data = await loop.run_in_executor(
                    None, os.read, session.master_fd, 4096
                )
            except OSError:
                break
            if not data:
                break
            await ws_manager.broadcast(session.project_id, {
                "type": "planning_output",
                "issue_id": session.issue_id,
                "data": data.decode("utf-8", errors="replace"),
            })
    except asyncio.CancelledError:
        pass
    finally:
        # Process ended or was cancelled — run cleanup
        await _cleanup_session(session.issue_id)


async def _sync_after_planning(session: PlanningSession) -> dict:
    """Detect content/child-issue changes and broadcast updates."""
    storage = _get_storage(session.project_id)
    result: dict = {"content_changed": False, "new_children": []}

    # 1. Check content changes
    try:
        current_content = storage.load_issue_content(session.issue_id)
        if current_content != session.content_snapshot:
            result["content_changed"] = True
    except FileNotFoundError:
        pass

    # 2. Check for new child issues
    try:
        all_issues = storage.list_issues()
        new_children = [
            i for i in all_issues
            if i.parent_id == session.issue_id
            and i.created_at > session.started_at
        ]
        result["new_children"] = [c.id for c in new_children]
    except Exception:
        pass

    # 3. Broadcast updates
    if result["content_changed"]:
        try:
            issue = storage.load_issue(session.issue_id)
            await ws_manager.broadcast(session.project_id, {
                "type": "issue_updated",
                "data": {"issue": issue.to_json()},
            })
        except Exception:
            pass

    for child_id in result["new_children"]:
        try:
            child = storage.load_issue(child_id)
            await ws_manager.broadcast(session.project_id, {
                "type": "issue_created",
                "data": {"issue": child.to_json()},
            })
        except Exception:
            pass

    return result


async def _cleanup_session(issue_id: str) -> dict | None:
    """Clean up a session: terminate process, close fd, sync, broadcast ended."""
    session = _sessions.pop(issue_id, None)
    if not session:
        return None

    # Terminate process if still running
    if session.process.returncode is None:
        try:
            os.killpg(os.getpgid(session.process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
        try:
            await asyncio.wait_for(session.process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            session.process.kill()

    # Close PTY master fd
    try:
        os.close(session.master_fd)
    except OSError:
        pass

    # Auto-sync
    sync_result = await _sync_after_planning(session)

    # Broadcast session ended
    await ws_manager.broadcast(session.project_id, {
        "type": "planning_ended",
        "data": {
            "issue_id": issue_id,
            "sync_result": sync_result,
        },
    })

    return sync_result


# --- WS message handlers (called from ws.py) ---

async def handle_planning_input(issue_id: str, data: str) -> None:
    """Write user input to the PTY."""
    session = _sessions.get(issue_id)
    if not session:
        return
    try:
        os.write(session.master_fd, data.encode("utf-8"))
    except OSError:
        pass


async def handle_planning_resize(issue_id: str, cols: int, rows: int) -> None:
    """Resize the PTY terminal."""
    session = _sessions.get(issue_id)
    if not session:
        return
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(session.master_fd, termios.TIOCSWINSZ, winsize)
    except OSError:
        pass


# --- REST endpoints ---

class StartRequest(BaseModel):
    issue_id: str
    cols: int = 80
    rows: int = 24


class InputRequest(BaseModel):
    issue_id: str
    data: str


class ResizeRequest(BaseModel):
    issue_id: str
    cols: int
    rows: int


class StopRequest(BaseModel):
    issue_id: str


@router.post("/start")
async def start_planning(project_id: str, req: StartRequest):
    storage = _get_storage(project_id)

    # Validate issue exists and is in planning status
    try:
        issue = storage.load_issue(req.issue_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Issue {req.issue_id} not found")

    if issue.status != IssueStatus.PLANNING:
        raise HTTPException(
            400, f"Issue must be in planning status, got {issue.status.value}"
        )

    # Only one session per issue
    if req.issue_id in _sessions:
        raise HTTPException(409, f"Planning session already active for {req.issue_id}")

    # Snapshot content.md
    try:
        content_snapshot = storage.load_issue_content(req.issue_id)
    except FileNotFoundError:
        content_snapshot = ""

    # Resolve workspace
    project = storage.load_project_meta()
    if not project or not project.workspaces:
        raise HTTPException(400, "Project has no workspace configured")
    workspace = project.workspaces[0]

    # Create PTY
    master_fd, slave_fd = pty.openpty()
    winsize = struct.pack("HHHH", req.rows, req.cols, 0, 0)
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

    # Spawn claude process
    env = {**os.environ, "TERM": "xterm-256color"}
    process = await asyncio.create_subprocess_exec(
        "claude",
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=workspace,
        env=env,
        preexec_fn=os.setsid,
    )
    os.close(slave_fd)

    now = datetime.now(timezone.utc).isoformat()
    session = PlanningSession(
        issue_id=req.issue_id,
        project_id=project_id,
        process=process,
        master_fd=master_fd,
        started_at=now,
        content_snapshot=content_snapshot,
    )
    _sessions[req.issue_id] = session

    # Start reading PTY output
    session.read_task = asyncio.create_task(_read_pty_loop(session))

    # Broadcast started
    await ws_manager.broadcast(project_id, {
        "type": "planning_started",
        "data": {"issue_id": req.issue_id},
    })

    return {"ok": True, "session_id": req.issue_id}


@router.post("/input")
async def planning_input(project_id: str, req: InputRequest):
    await handle_planning_input(req.issue_id, req.data)
    return {"ok": True}


@router.post("/resize")
async def planning_resize(project_id: str, req: ResizeRequest):
    await handle_planning_resize(req.issue_id, req.cols, req.rows)
    return {"ok": True}


@router.post("/stop")
async def stop_planning(project_id: str, req: StopRequest):
    if req.issue_id not in _sessions:
        raise HTTPException(404, f"No active planning session for {req.issue_id}")

    session = _sessions[req.issue_id]

    # Cancel the read task first
    if session.read_task:
        session.read_task.cancel()
        try:
            await session.read_task
        except asyncio.CancelledError:
            pass

    sync_result = await _cleanup_session(req.issue_id)
    return {"ok": True, "sync_result": sync_result}
