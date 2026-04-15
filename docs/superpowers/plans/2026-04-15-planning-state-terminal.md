# Planning State + Embedded Terminal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Activate the PLANNING kanban state as a real human workflow with an embedded xterm.js terminal running a restricted Claude Code subprocess for issue refinement.

**Architecture:** Backend spawns a PTY-based Claude Code process per planning session, streams I/O over the existing WebSocket. Frontend renders output in xterm.js inside IssueDetail. Auto-sync detects content/child-issue changes when the session ends.

**Tech Stack:** Python asyncio + pty (backend), xterm.js + @xterm/addon-fit (frontend), existing FastAPI WebSocket infrastructure

**Spec:** `docs/superpowers/specs/2026-04-15-planning-state-terminal-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `core/models.py` | Modify | Add `IN_PROGRESS` to PLANNING transitions |
| `server/app.py` | Modify | Remove PLANNING→BACKLOG reset; register planning router |
| `server/routes/board.py` | Modify | Add `planning` to status_map |
| `server/routes/planning.py` | **Create** | PTY session management, start/stop/input/resize endpoints, auto-sync |
| `server/routes/ws.py` | Modify | Handle `planning_input` and `planning_resize` WS messages |
| `web/src/constants/transitions.ts` | Modify | Add `in_progress` to planning transitions |
| `web/src/components/IssueCard.tsx` | Modify | Add Planning button, update canRun |
| `web/src/components/IssueDetail.tsx` | Modify | Embed PlanningTerminal, update Run button for planning status |
| `web/src/components/PlanningTerminal.tsx` | **Create** | xterm.js terminal component |
| `web/src/stores/boardStore.ts` | Mod planning session state + actions |
| `web/src/hooks/useWebSocket.ts` | Modify | Handle planning_started/output/ended events |
| `web/src/i18n/locales/en/translation.json` | Modify | Add planning i18n keys |
| `web/src/i18n/locales/zh/translation.json` | Modify | Add planning i18n keys |
| `web/package.json` | Modify | Add @xterm/xterm, @xterm/addon-fit deps |

---

### Task 1: Update State Transitions (Backend + Frontend)

**Files:**
- Modify: `core/models.py:19-28`
- Modify: `web/src/constants/transitions.ts:1-10`
- Modify: `server/routes/board.py:113-120`

- [ ] **Step 1: Update backend VALID_TRANSITIONS**

In `core/models.py`, add `IssueStatus.IN_PROGRESS` to the PLANNING transition set:

```python
VALID_TRANSITIONS = {
    IssueStatus.BACKLOG: {IssueStatus.PLANNING, IssueStatus.TODO},
    IssueStatus.PLANNING: {IssueStatus.TODO, IssueStatus.BACKLOG, IssueStatus.IN_PROGRESS},
    IssueStatus.TODO: {IssueStatus.IN_PROGRESS, IssueStatus.BACKLOG},
    IssueStatus.IN_PROGRESS: {IssueStatus.AGENT_DONE, IssueStatus.FAILED, IssueStatus.TODO},
    IssueStatus.AGENT_DONE: {IssueStatus.HUMAN_DONE, IssueStatus.REJECTED},
    IssueStatus.FAILED: {IssueStatus.IN_PROGRESS, IssueStatus.TODO},
    IssueStatus.REJECTED: {IssueStatus.TODO},
    IssueStatus.HUMAN_DONE: set(),
}
```

- [ ] **Step 2: Add `planning` to board.py status_map**

In `server/routes/board.py`, the `status_map` dict (line ~113) is missing `planning`. Add it so drag-to-planning works:

```python
        status_map = {
            "backlog": IssueStatus.BACKLOG,
            "planning": IssueStatus.PLANNING,
            "todo": IssueStatus.TODO,
            "in_progress": IssueStatus.IN_PROGRESS,
            "agent_done": IssueStatus.AGENT_DONE,
            "rejected": IssueStatus.REJECTED,
            "human_done": IssueStatus.HUMAN_DONE,
        }
```

- [ ] **Step 3: Update frontend transitions.ts**

Replace the full content of `web/src/constants/transitions.ts`:

```ts
export const VALID_TRANSITIONS: Record<string, string[]> = {
  backlog: ['planning', 'todo'],
  planning: ['todo', 'backlog', 'in_progress'],
  todo: ['in_progress', 'backlog'],
  in_progress: ['agent_done', 'failed', 'todo'],
  agent_done: ['human_done', 'rejected'],
  failed: ['in_progress', 'todo'],
  rejected: ['todo'],
  human_done: [],
}
```

- [ ] **Step 4: Verify transitions work**

Start the server and test:
1. Create an issue (lands in backlog)
2. Drag it to the Planning column — should succeed
3. From Planning, the status dropdown should show: Todo, Backlog, In Progress
4. Drag from Planning to In Progress — should succeed (if no other issue running)

- [ ] **Step 5: Commit**

```bash
git add core/models.py server/routes/board.py web/src/constants/transitions.ts
git commit -m "feat: activate PLANNING state transitions — add planning→in_progress, fix board status_map"
```

---

### Task 2: Remove Startup PLANNING Reset

**Files:**
- Modify: `server/app.py:51-70`

- [ ] **Step 1: Remove the PLANNING→BACKLOG reset branch**

In `server/app.py`, function `_reset_stuck_issues()`, remove lines 65-68 (the `elif issue.status == IssueStatus.PLANNING` block):

Before:
```python
def _reset_stuck_issues() -> None:
    """Reset any in_progress issues to failed (not todo) to avoid retry loops."""
    try:
        from core.models import IssueStatus
        from core.storage import PlatformStorage
        root = get_harness_root()
        platform = PlatformStorage(root)
        for pid, _ in platform.list_projects():
            storage = platform.get_project_storage(pid)
            for issue in storage.list_issues():
                if issue.status == IssueStatus.IN_PROGRESS:
                    issue.move_to(IssueStatus.FAILED)
                    storage.save_issue(issue)
                    _move_board_column(storage, issue.id, "todo")
                elif issue.status == IssueStatus.PLANNING:
                    issue.move_to(IssueStatus.BACKLOG)
                    storage.save_issue(issue)
                    _move_board_column(storage, issue.id, "backlog")
    except Exception:
        pass
```

After:
```python
def _reset_stuck_issues() -> None:
    """Reset any in_progress issues to failed (not todo) to avoid retry loops."""
    try:
        from core.models import IssueStatus
        from core.storage import PlatformStorage
        root = get_harness_root()
        platform = PlatformStorage(root)
        for pid, _ in platform.list_projects():
            storage = platform.get_project_storage(pid)
            for issue in storage.list_issues():
                if issue.status == IssueStatus.IN_PROGRESS:
                    issue.move_to(IssueStatus.FAILED)
                    storage.save_issue(issue)
                    _move_board_column(storage, issue.id, "todo")
    except Exception:
        pass
```

- [ ] **Step 2: Verify server starts without resetting planning issues**

1. Manually set an issue to `planning` status (drag it there via UI)
2. Restart the server
3. Confirm the issue is still in the Planning column (not reset to Backlog)

- [ ] **Step 3: Commit**

```bash
git add server/app.py
git commit -m "fix: stop resetting PLANNING issues to BACKLOG on server startup"
```

---

### Task 3: IssueCard Planning Button + i18n + IssueDetail Run from Planning

**Files:**
- Modify: `web/src/components/IssueCard.tsx`
- Modify: `web/src/components/IssueDetail.tsx:571-581`
- Modify: `web/src/i18n/locales/en/translation.json`
- Modify: `web/src/i18n/locales/zh/translation.json`

- [ ] **Step 1: Add i18n keys for planning**

In `web/src/i18n/locales/en/translation.json`, add to the `issueCard` section:

```json
  "issueCard": {
    "stopTitle": "Stop this issue",
    "stop": "Stop",
    "runTitle": "Run this issue",
    "blockedBy": "Blocked by {{count}}",
    "planningTitle": "Start planning this issue",
    "planning": "Plan"
  },
```

And add to the `issueDetail` section (after `"buildLog": "Build Log"`):

```json
    "buildLog": "Build Log",
    "startPlanning": "Start Planning",
    "stopPlanning": "Stop Planning",
    "planningTerminal": "Planning Terminal",
    "planningActive": "Planning session active",
    "planningEnded": "Planning session ended"
```

In `web/src/i18n/locales/zh/translation.json`, add to the `issueCard` section:

```json
  "issueCard": {
    "stopTitle": "停止此问题",
    "stop": "停止",
    "runTitle": "运行此问题",
    "blockedBy": "被 {{count}} 个问题阻塞",
    "planningTitle": "开始规划此问题",
    "planning": "规划"
  },
```

And add to the `issueDetail` section (after `"buildLog": "构建日志"`):

```json
    "buildLog": "构建日志",
    "startPlanning": "开始规划",
    "stopPlanning": "停止规划",
    "planningTerminal": "规划终端",
    "planningActive": "规划会话进行中",
    "planningEnded": "规划会话已结束"
```

- [ ] **Step 2: Add Planning button to IssueCard**

In `web/src/components/IssueCard.tsx`:

1. Add `ClipboardList` to the lucide-react import:

```ts
import { GripVertical, AlertCircle, Clock, Tag, Play, Square, Bot, ClipboardList } from 'lucide-react'
```

2. Add `moveIssue` from the store and a `canPlan` flag after the existing `canRun` line:

```ts
  const moveIssue = useBoardStore(s => s.moveIssue)
  const canPlan = issue.status === 'backlog'
```

3. Update `canRun` to include `planning`:

```ts
  const canRun = !hasOtherRunning && (issue.status === 'todo' || issue.status === 'rejected' || issue.status === 'backlog' || issue.status === 'failed' || issue.status === 'planning')
```

4. Add a `handlePlan` handler after `handleStop`:

```ts
  const handlePlan = (e: React.MouseEvent) => {
    e.stopPropagation()
    moveIssue(issue.id, 'planning')
  }
```

5. Add the Planning button right before the existing Run button (inside the `{canRun && !isRunning ...}` block area). Insert this block after the stop button block and before the run button block:

```tsx
            {canPlan && !isRunning && (
              <button
                onClick={handlePlan}
                className="p-1 rounded hover:bg-violet-50 text-violet-600 hover:text-violet-700 transition-colors"
                title={t('issueCard.planningTitle')}
              >
                <ClipboardList size={12} />
              </button>
            )}
```

The final button area (lines ~65-84) should look like:

```tsx
            {(isRunning || issue.status === 'in_progress') && (
              <button
                onClick={handleStop}
                className="ml-auto flex items-center gap-1 p-1 rounded hover:bg-red-50 text-red-500 hover:text-red-600 transition-colors"
                title={t('issueCard.stopTitle')}
              >
                <Square size={10} fill="currentColor" />
                <span className="text-xs">{t('issueCard.stop')}</span>
              </button>
            )}
            {canPlan && !isRunning && issue.status !== 'in_progress' && (
              <button
                onClick={handlePlan}
                className="ml-auto p-1 rounded hover:bg-violet-50 text-violet-600 hover:text-violet-700 transition-colors"
                title={t('issueCard.planningTitle')}
              >
                <ClipboardList size={12} />
              </button>
            )}
            {canRun && !isRunning && issue.status !== 'in_progress' && (
              <button
                onClick={handleRun}
                className="ml-auto p-1 rounded hover:bg-green-50 text-green-600 hover:text-green-700 transition-colors"
                title={t('issueCard.runTitle')}
              >
                <Play size={12} />
              </button>
            )}
```

Note: For backlog issues, both Planning and Run buttons show. `ml-auto` only applies to the first visible button — since both show for backlog, remove `ml-auto` from the Planning button and keep it only on the first visible button in the group. A cleaner approach: wrap the buttons in a flex container:

```tsx
            {!isRunning && issue.status !== 'in_progress' && (canPlan || canRun) && (
              <div className="ml-auto flex items-center gap-0.5">
                {canPlan && (
                  <button
                    onClick={handlePlan}
                    className="p-1 rounded hover:bg-violet-50 text-violet-600 hover:text-violet-700 transition-colors"
                    title={t('issueCard.planningTitle')}
                  >
                    <ClipboardList size={12} />
                  </button>
                )}
                {canRun && (
                  <button
                    onClick={handleRun}
                    className="p-1 rounded hover:bg-green-50 text-green-600 hover:text-green-700 transition-colors"
                    title={t('issueCard.runTitle')}
                  >
                    <Play size={12} />
                  </button>
                )}
              </div>
            )}
```

This replaces the original `{canRun && !isRunning && issue.status !== 'in_progress' && (...)}` block.

- [ ] **Step 3: Update IssueDetail Run button to include planning status**

In `web/src/components/IssueDetail.tsx`, line 572, the Run button condition currently is:

```tsx
{onRun && ['todo', 'backlog', 'rejected', 'failed'].includes(issue.status) && !isRunning && (
```

Add `'planning'` to the array:

```tsx
{onRun && ['todo', 'backlog', 'rejected', 'failed', 'planning'].includes(issue.status) && !isRunning && (
```

- [ ] **Step 4: Verify buttons work**

1. Create an issue — it lands in Backlog
2. The card should show both a violet Planning (ClipboardList) icon and a green Run (Play) icon
3. Click Planning — issue moves to Planning column
4. In Planning column, the card should show only the Run (Play) icon (canPlan is false for planning status)
5. Open the issue detail from Planning — the Run button should appear

- [ ] **Step 5: Commit**

```bash
git add web/src/components/IssueCard.tsx web/src/components/IssueDetail.tsx web/src/i18n/locales/en/translation.json web/src/i18n/locales/zh/translation.json
git commit -m "feat: add Planning button to IssueCard, update Run to support planning status"
```

---

### Task 4: Backend Planning Terminal Session Management

**Files:**
- Create: `server/routes/planning.py`
- Modify: `server/routes/ws.py`
- Modify: `server/app.py`

- [ ] **Step 1: Create `server/routes/planning.py`**

```python
"""Planning terminal session management — PTY-based Claude Code subprocess."""

from __future__ import annotations

import asyncio
import os
import pty
import signal
import struct
import fcntl
import termios
from dataclasses import dataclass, field
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


# Global session registry: issue_id → session
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
    result = {"content_changed": False, "new_children": []}

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
        raise HTTPException(400, f"Issue must be in planning status, got {issue.status.value}")

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
```

- [ ] **Step 2: Register planning router in app.py**

In `server/app.py`, add the import and router registration.

Add to imports (after `from server.routes import ... run ...`):

```python
from server.routes import issues, board, projects, reviews, run, fs, uploads
from server.routes import planning as planning_route
```

Add the router in `create_app()` (after `app.include_router(run.router)`):

```python
    app.include_router(planning_route.router)
```

- [ ] **Step 3: Add WS message handlers for planning_input and planning_resize**

In `server/routes/ws.py`, add two new `elif` branches inside the message handling loop (after the `cancel_agent` handler):

```python
            elif msg_type == "cancel_agent":
                issue_id = data.get("issue_id")
                if issue_id:
                    from server.routes.run import request_cancel
                    request_cancel(issue_id)
            elif msg_type == "planning_input":
                issue_id = data.get("issue_id")
                if issue_id:
                    from server.routes.planning import handle_planning_input
                    await handle_planning_input(issue_id, data.get("data", ""))
            elif msg_type == "planning_resize":
                issue_id = data.get("issue_id")
                if issue_id:
                    from server.routes.planning import handle_planning_resize
                    await handle_planning_resize(
                        issue_id,
                        data.get("cols", 80),
                        data.get("rows", 24),
                    )
```

- [ ] **Step 4: Verify backend starts without errors**

Start the server and confirm no import errors. Test the `/planning/start` endpoint manually:

```bash
curl -X POST http://localhost:8080/api/projects/<project_id>/planning/start \
  -H 'Content-Type: application/json' \
  -d '{"issue_id": "<issue_in_planning>", "cols": 80, "rows": 24}'
```

Should return `{"ok": true, "session_id": "..."}` if the issue is in planning status.

- [ ] **Step 5: Commit**

```bash
git add server/routes/planning.py server/routes/ws.py server/app.py
git commit -m "feat: add backend planning terminal session management with PTY"
```

---

### Task 5: Install xterm.js Dependencies + Extend boardStore + useWebSocket

**Files:**
- Modify: `web/package.json` (via npm install)
- Modify: `web/src/stores/boardStore.ts`
- Modify: `web/src/hooks/useWebSocket.ts`

- [ ] **Step 1: Install xterm.js packages**

```bash
cd web && npm install @xterm/xterm @xterm/addon-fit
```

- [ ] **Step 2: Extend boardStore with planning session state**

In `web/src/stores/boardStore.ts`:

1. Add to the `BoardState` interface (after `wsSend` line 59):

```ts
  planningActive: Record<string, boolean>
  setPlanningActive: (issueId: string, active: boolean) => void
  startPlanning: (issueId: string, cols?: number, rows?: number) => Promise<void>
  stopPlanning: (issueId: string) => Promise<void>
```

2. Add initial state in the `create<BoardState>` call (after `wsSend: null,`):

```ts
  planningActive: {},
```

3. Add the action implementations (after the `setWsSend` implementation):

```ts
  setPlanningActive: (issueId, active) => set(state => ({
    planningActive: { ...state.planningActive, [issueId]: active },
  })),

  startPlanning: async (issueId, cols = 80, rows = 24) => {
    const { projectId } = get()
    if (!projectId) return
    const res = await fetch(`/api/projects/${projectId}/planning/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ issue_id: issueId, cols, rows }),
    })
    if (res.ok) {
      set(state => ({
        planningActive: { ...state.planningActive, [issueId]: true },
      }))
    }
  },

  stopPlanning: async (issueId) => {
    const { projectId } = get()
    if (!projectId) return
    await fetch(`/api/projects/${projectId}/planning/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ issue_id: issueId }),
    })
    set(state => ({
      planningActive: { ...state.planningActive, [issueId]: false },
    }))
  },
```

- [ ] **Step 3: Extend useWebSocket with planning events**

In `web/src/hooks/useWebSocket.ts`:

1. Add `setPlanningActive` to the store selectors at the top of the hook (after `removeRunningIssue`):

```ts
  const setPlanningActive = useBoardStore(s => s.setPlanningActive)
```

2. Add it to the `useEffect` dependency array at the bottom (line 196).

3. Add three new cases inside the `switch (type)` block, before the `default` / closing brace (after the `run_error` case):

```ts
          case 'planning_started':
            if (payload?.issue_id) {
              setPlanningActive(payload.issue_id, true)
              logEvent('planning_started', `Planning started for ${payload.issue_id}`, payload.issue_id)
            }
            break

          case 'planning_output':
            // Dispatch as CustomEvent — PlanningTerminal listens for this
            window.dispatchEvent(new CustomEvent('planning_output', {
              detail: { issue_id: data.issue_id, data: data.data },
            }))
            break

          case 'planning_ended':
            if (payload?.issue_id) {
              setPlanningActive(payload.issue_id, false)
              logEvent('planning_ended', `Planning ended for ${payload.issue_id}`, payload.issue_id)
              fetchBoard()
              fetchIssues()
            }
            break
```

- [ ] **Step 4: Verify the store and WS changes compile**

```bash
cd web && npx tsc --noEmit
```

Should pass with no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/package.json web/package-lock.json web/src/stores/boardStore.ts web/src/hooks/useWebSocket.ts
git commit -m "feat: add xterm.js deps, extend boardStore and useWebSocket for planning sessions"
```

---

### Task 6: Create PlanningTerminal Component + Integrate in IssueDetail

**Files:**
- Create: `web/src/components/PlanningTerminal.tsx`
- Modify: `web/src/components/IssueDetail.tsx`

- [ ] **Step 1: Create `web/src/components/PlanningTerminal.tsx`**

```tsx
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { useBoardStore } from '../stores/boardStore'
import { Play, Square } from 'lucide-react'

interface PlanningTerminalProps {
  issueId: string
  projectId: string
}

export function PlanningTerminal({ issueId, projectId }: PlanningTerminalProps) {
  const { t } = useTranslation()
  const termRef = useRef<HTMLDivElement>(null)
  const terminalRef = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const [started, setStarted] = useState(false)

  const isActive = useBoardStore(s => s.planningActive[issueId] ?? false)
  const startPlanning = useBoardStore(s => s.startPlanning)
  const stopPlanning = useBoardStore(s => s.stopPlanning)
  const wsSend = useBoardStore(s => s.wsSend)

  // Initialize xterm.js
  useEffect(() => {
    if (!termRef.current) return

    const terminal = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      theme: {
        background: '#1a1b26',
        foreground: '#a9b1d6',
        cursor: '#c0caf5',
        selectionBackground: '#33467c',
      },
      convertEol: true,
      scrollback: 5000,
    })

    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.open(termRef.current)
    fitAddon.fit()

    terminalRef.current = terminal
    fitAddonRef.current = fitAddon

    // Handle user input → send via WS
    terminal.onData((data) => {
      if (wsSend) {
        wsSend({ type: 'planning_input', issue_id: issueId, data })
      }
    })

    // Handle resize
    const resizeObserver = new ResizeObserver(() => {
      fitAddon.fit()
      if (wsSend) {
        wsSend({
          type: 'planning_resize',
          issue_id: issueId,
          cols: terminal.cols,
          rows: terminal.rows,
        })
      }
    })
    resizeObserver.observe(termRef.current)

    return () => {
      resizeObserver.disconnect()
      terminal.dispose()
      terminalRef.current = null
      fitAddonRef.current = null
    }
  }, [issueId, wsSend])

  // Listen for planning_output CustomEvents
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (detail?.issue_id === issueId && detail?.data && terminalRef.current) {
        terminalRef.current.write(detail.data)
      }
    }
    window.addEventListener('planning_output', handler)
    return () => window.removeEventListener('planning_output', handler)
  }, [issueId])

  // Sync started state from store
  useEffect(() => {
    setStarted(isActive)
  }, [isActive])

  const handleStart = async () => {
    const terminal = terminalRef.current
    const cols = terminal?.cols ?? 80
    const rows = terminal?.rows ?? 24
    await startPlanning(issueId, cols, rows)
    setStarted(true)
  }

  const handleStop = async () => {
    await stopPlanning(issueId)
    setStarted(false)
  }

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 bg-[var(--bg-secondary)] border-b border-[var(--border)]">
        <span className="text-xs font-medium text-[var(--text-secondary)]">
          {t('issueDetail.planningTerminal')}
        </span>
        <div className="flex items-center gap-2">
          {!started ? (
            <button
              onClick={handleStart}
              className="flex items-center gap-1 px-2 py-1 text-xs bg-violet-600 text-white rounded hover:bg-violet-700 transition-colors"
            >
              <Play size={12} /> {t('issueDetail.startPlanning')}
            </button>
          ) : (
            <button
              onClick={handleStop}
              className="flex items-center gap-1 px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
            >
              <Square size={12} fill="currentColor" /> {t('issueDetail.stopPlanning')}
            </button>
          )}
        </div>
      </div>
      <div
        ref={termRef}
        style={{ height: '400px', padding: '4px' }}
      />
    </div>
  )
}
```

- [ ] **Step 2: Integrate PlanningTerminal in IssueDetail**

In `web/src/components/IssueDetail.tsx`:

1. Add the import at the top (after the `Lightbox` import):

```ts
import { PlanningTerminal } from './PlanningTerminal'
```

2. Insert the PlanningTerminal section right before the `{/* Run / Stop Action */}` comment (line ~571). Add this block:

```tsx
          {/* Planning Terminal */}
          {issue.status === 'planning' && (
            <div>
              <PlanningTerminal
                issueId={issue.id}
                projectId={useBoardStore.getState().projectId || ''}
              />
            </div>
          )}
```

- [ ] **Step 3: Verify the component renders**

1. Start the dev server (`cd web && npm run dev`)
2. Move an issue to Planning status
3. Open the issue detail panel
4. The PlanningTerminal component should render with a dark terminal area and a "Start Planning" button
5. Click "Start Planning" — the terminal should connect and show Claude Code's interactive UI
6. Type in the terminal — input should be sent and output should appear

- [ ] **Step 4: Commit**

```bash
git add web/src/components/PlanningTerminal.tsx web/src/components/IssueDetail.tsx
git commit -m "feat: add PlanningTerminal xterm.js component, integrate in IssueDetail"
```

---

### Task 7: End-to-End Verification

**Files:** None (verification only)

- [ ] **Step 1: Full state transition flow**

1. Create a new issue — lands in Backlog
2. On the card, confirm both Planning (violet ClipboardList) and Run (green Play) icons appear
3. Click the Planning icon — issue moves to Planning column
4. Open the issue detail — confirm PlanningTerminal renders with "Start Planning" button
5. From the status dropdown in detail, confirm options: Todo, Backlog, In Progress
6. Click "Start Planning" — terminal should show Claude Code interactive UI
7. Type a message in the terminal — confirm output appears
8. Click "Stop Planning" — terminal session ends, `planning_ended` event fires
9. Click Run (from detail or card) — issue should move to In Progress

- [ ] **Step 2: Drag-and-drop flow**

1. Create an issue in Backlog
2. Drag it to the Planning column — should succeed, status updates to `planning`
3. Drag it back to Backlog — should succeed
4. Drag it to Planning again, then drag to In Progress — should succeed (if no other running)

- [ ] **Step 3: Auto-sync verification**

1. Move an issue to Planning, open detail, start a planning session
2. In the Claude Code terminal, use the harness skill to update the issue description (e.g., edit content.md)
3. Stop the planning session
4. Confirm the issue detail refreshes with the updated content
5. If sub-issues were created during planning, confirm they appear on the board

- [ ] **Step 4: Server restart persistence**

1. Move an issue to Planning status
2. Restart the server (`Ctrl+C` and restart)
3. Confirm the issue is still in the Planning column (not reset to Backlog)

- [ ] **Step 5: Concurrent session guard**

1. Move an issue to Planning, start a planning session
2. Try to start another planning session for the same issue (via curl or UI)
3. Should get a 409 error: "Planning session already active"

- [ ] **Step 6: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address issues found during e2e verification"
```
