# WebSocket Agent Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace SSE with WebSocket for real-time bidirectional agent streaming, add per-issue JSONL run logs, and build an agent log panel in the frontend.

**Architecture:** FastAPI native WebSocket endpoint replaces `sse-starlette`. A `ConnectionManager` manages per-project connections. The executor streams events via an `on_event` callback threaded through `ralph_loop`. JSONL logs persist each run to disk. Frontend uses a reconnecting WebSocket hook that dispatches events to Zustand stores.

**Tech Stack:** FastAPI WebSocket, Zustand, React, JSONL file storage

---

## File Structure

| Operation | File | Responsibility |
|-----------|------|----------------|
| Create | `server/ws.py` | `ConnectionManager` — per-project WebSocket connection registry + broadcast |
| Create | `server/routes/ws.py` | WebSocket endpoint, heartbeat, client message dispatch |
| Create | `web/src/hooks/useWebSocket.ts` | WebSocket hook with auto-reconnect, heartbeat, event dispatch |
| Create | `web/src/components/AgentLogPanel.tsx` | Per-issue real-time agent log viewer with history |
| Modify | `core/storage.py` | Add `append_run_log`, `load_run_log`, `list_run_ids` methods |
| Modify | `core/executor.py` | Add `on_event` callback, emit `agent_token`/`agent_tool_call`/`agent_status` |
| Modify | `core/ralph_loop.py` | Thread `on_event` through loop, replace `event_bus` with callback |
| Modify | `server/routes/run.py` | Wire `on_event` to `ws_manager.broadcast`, handle cancellation |
| Modify | `server/routes/issues.py` | Add log REST endpoints, replace `event_bus` with `ws_manager` |
| Modify | `server/app.py` | Remove SSE endpoint, register WS route, remove `sse-starlette` import |
| Modify | `web/src/stores/boardStore.ts` | Add `agentLogs` state, `appendAgentLog`/`clearAgentLog` actions |
| Modify | `web/src/App.tsx` | Replace `useSSE()` with `useWebSocket()` |
| Modify | `web/src/components/IssueDetail.tsx` | Embed `AgentLogPanel` tab |
| Modify | `web/src/components/RunLogPanel.tsx` | Rename "SSE Events" label, use same data source |
| Delete | `server/sse.py` | Replaced by `server/ws.py` |
| Delete | `web/src/hooks/useSSE.ts` | Replaced by `useWebSocket.ts` |

---

### Task 1: Storage — Run Log Methods

**Files:**
- Modify: `core/storage.py:9-84` (ProjectStorage class)
- Test: `tests/core/test_storage_logs.py`

- [ ] **Step 1: Write failing tests for run log storage**

```python
# tests/core/test_storage_logs.py
"""Tests for JSONL run log storage."""
import json
import pytest
from pathlib import Path
from core.storage import ProjectStorage


@pytest.fixture
def storage(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "issues").mkdir()
    return ProjectStorage(root)


def test_append_and_load_run_log(storage):
    entry1 = {"ts": 1713000000, "type": "agent_status", "data": {"status": "thinking"}}
    entry2 = {"ts": 1713000001, "type": "agent_token", "data": {"text": "hello"}}
    storage.append_run_log("ISS-1", "run-001", entry1)
    storage.append_run_log("ISS-1", "run-001", entry2)
    logs = storage.load_run_log("ISS-1", "run-001")
    assert len(logs) == 2
    assert logs[0]["type"] == "agent_status"
    assert logs[1]["data"]["text"] == "hello"


def test_list_run_ids_empty(storage):
    assert storage.list_run_ids("ISS-1") == []


def test_list_run_ids(storage):
    storage.append_run_log("ISS-1", "run-001", {"ts": 1, "type": "x", "data": {}})
    storage.append_run_log("ISS-1", "run-002", {"ts": 2, "type": "y", "data": {}})
    ids = storage.list_run_ids("ISS-1")
    assert ids == ["run-001", "run-002"]


def test_load_run_log_not_found(storage):
    assert storage.load_run_log("ISS-1", "run-999") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && python -m pytest tests/core/test_storage_logs.py -v`
Expected: FAIL — `AttributeError: 'ProjectStorage' object has no attribute 'append_run_log'`

- [ ] **Step 3: Implement run log methods in ProjectStorage**

Add these methods to `core/storage.py` inside the `ProjectStorage` class, after `load_issue_content`:

```python
    def append_run_log(self, issue_id: str, run_id: str, entry: dict) -> None:
        logs_dir = self.issues_dir / issue_id / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        with open(logs_dir / f"{run_id}.jsonl", "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_run_log(self, issue_id: str, run_id: str) -> list[dict]:
        log_file = self.issues_dir / issue_id / "logs" / f"{run_id}.jsonl"
        if not log_file.exists():
            return []
        entries = []
        for line in log_file.read_text().splitlines():
            if line.strip():
                entries.append(json.loads(line))
        return entries

    def list_run_ids(self, issue_id: str) -> list[str]:
        logs_dir = self.issues_dir / issue_id / "logs"
        if not logs_dir.exists():
            return []
        return sorted(f.stem for f in logs_dir.glob("*.jsonl"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && python -m pytest tests/core/test_storage_logs.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/storage.py tests/core/test_storage_logs.py
git commit -m "feat: add JSONL run log storage methods to ProjectStorage"
```

---

### Task 2: WebSocket Connection Manager

**Files:**
- Create: `server/ws.py`
- Test: `tests/server/test_ws_manager.py`

- [ ] **Step 1: Write failing tests for ConnectionManager**

```python
# tests/server/test_ws_manager.py
"""Tests for WebSocket ConnectionManager."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from server.ws import ConnectionManager


@pytest.fixture
def manager():
    return ConnectionManager()


@pytest.mark.asyncio
async def test_connect_and_disconnect(manager):
    ws = AsyncMock()
    await manager.connect("PRJ-1", ws)
    assert ws in manager._connections["PRJ-1"]
    manager.disconnect("PRJ-1", ws)
    assert ws not in manager._connections["PRJ-1"]


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_project_connections(manager):
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    ws_other = AsyncMock()
    await manager.connect("PRJ-1", ws1)
    await manager.connect("PRJ-1", ws2)
    await manager.connect("PRJ-2", ws_other)

    await manager.broadcast("PRJ-1", {"type": "ping"})

    ws1.send_json.assert_called_once_with({"type": "ping"})
    ws2.send_json.assert_called_once_with({"type": "ping"})
    ws_other.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_removes_dead_connections(manager):
    ws_alive = AsyncMock()
    ws_dead = AsyncMock()
    ws_dead.send_json.side_effect = Exception("connection closed")
    await manager.connect("PRJ-1", ws_alive)
    await manager.connect("PRJ-1", ws_dead)

    await manager.broadcast("PRJ-1", {"type": "test"})

    assert ws_dead not in manager._connections["PRJ-1"]
    assert ws_alive in manager._connections["PRJ-1"]


@pytest.mark.asyncio
async def test_disconnect_nonexistent_is_noop(manager):
    ws = AsyncMock()
    manager.disconnect("PRJ-1", ws)  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && python -m pytest tests/server/test_ws_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.ws'`

- [ ] **Step 3: Implement ConnectionManager**

```python
# server/ws.py
"""WebSocket connection manager for real-time updates."""

from __future__ import annotations
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """Per-project WebSocket connection registry."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, project_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[project_id].append(ws)

    def disconnect(self, project_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(project_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, project_id: str, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(project_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(project_id, ws)


ws_manager = ConnectionManager()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && python -m pytest tests/server/test_ws_manager.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add server/ws.py tests/server/test_ws_manager.py
git commit -m "feat: add WebSocket ConnectionManager with per-project broadcast"
```

---

### Task 3: WebSocket Route Endpoint

**Files:**
- Create: `server/routes/ws.py`
- Modify: `server/app.py:1-75`

- [ ] **Step 1: Create WebSocket route**

```python
# server/routes/ws.py
"""WebSocket endpoint for real-time project events."""

from __future__ import annotations
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.ws import ws_manager

router = APIRouter()

HEARTBEAT_INTERVAL = 20  # seconds


@router.websocket("/api/projects/{project_id}/ws")
async def project_websocket(project_id: str, ws: WebSocket):
    await ws_manager.connect(project_id, ws)

    # Heartbeat task
    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await ws.send_json({"type": "ping"})
        except Exception:
            pass

    hb_task = asyncio.create_task(heartbeat())

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")
            if msg_type == "pong":
                pass  # heartbeat response, no action needed
            elif msg_type == "cancel_agent":
                issue_id = data.get("issue_id")
                if issue_id:
                    from server.routes.run import cancel_agent
                    cancel_agent(issue_id)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hb_task.cancel()
        ws_manager.disconnect(project_id, ws)
```

- [ ] **Step 2: Register WS route in app.py — replace SSE endpoint**

Replace the full content of `server/app.py` with:

```python
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

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    app.include_router(projects.router)
    app.include_router(issues.router)
    app.include_router(board.router)
    app.include_router(reviews.router)
    app.include_router(run.router)
    app.include_router(fs.router)
    app.include_router(ws_route.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


def run_server(host: str = "127.0.0.1", port: int = 8080, harness_root: Path | None = None):
    import uvicorn
    app = create_app(harness_root)
    uvicorn.run(app, host=host, port=port)
```

- [ ] **Step 3: Verify server starts without import errors**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && python -c "from server.app import create_app; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add server/routes/ws.py server/app.py
git commit -m "feat: add WebSocket endpoint, remove SSE endpoint from app"
```

---

### Task 4: Executor — Stream Events via on_event Callback

**Files:**
- Modify: `core/executor.py:96-127`
- Test: `tests/core/test_executor_events.py`

- [ ] **Step 1: Write failing test for on_event streaming**

```python
# tests/core/test_executor_events.py
"""Tests for executor on_event callback."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.executor import _message_to_events


def _make_text_block(text):
    block = MagicMock()
    block.text = text
    block.__class__.__name__ = "TextBlock"
    return block


def _make_tool_block(name, input_data):
    block = MagicMock()
    block.name = name
    block.input = input_data
    block.__class__.__name__ = "ToolUseBlock"
    return bn

def test_assistant_text_block_produces_agent_token():
    from claude_agent_sdk import AssistantMessage, TextBlock
    msg = MagicMock(spec=AssistantMessage)
    msg.content = [MagicMock(spec=TextBlock, text="Hello world")]
    events = _message_to_events("ISS-1", msg)
    assert len(events) == 1
    assert events[0]["type"] == "agent_token"
    assert events[0]["issue_id"] == "ISS-1"
    assert events[0]["data"]["text"] == "Hello world"


def test_assistant_tool_block_produces_agent_tool_call():
    from claude_agent_sdk import AssistantMessage, ToolUseBlock
    msg = MagicMock(spec=AssistantMessage)
    msg.content = [MagicMock(spec=ToolUseBlock, name="Bash", input={"command": "ls"})]
    events = _message_to_events("ISS-1", msg)
    assert len(events) == 1
    assert events[0]["type"] == "agent_tool_call"
    assert events[0]["data"]["tool"] == "Bash"
    assert events[0]["data"]["input"] == {"command": "ls"}


def test_result_message_success_produces_agent_status_done():
    from claude_agent_sdk import ResultMessage
    msg = MagicMock(spec=ResultMessage)
    msg.is_error = False
    msg.total_cost_usd = 0.05
    msg.duration_ms = 3000
    msg.num_turns = 5
    msg.usage = {}
    events = _message_to_events("ISS-1", msg)
    assert len(events) == 1
    assert events[0]["type"] == "agent_status"
    assert events[0]["data"]["status"] == "done"


def test_result_message_error_produces_agent_status_failed():
    from claude_agent_sdk import ResultMessage
    msg = MagicMock(spec=ResultMessage)
    msg.is_error = True
    msg.result = "budget exceeded"
    msg.total_cost_usd = 0.10
    msg.duration_ms = 5000
    msg.num_turns = 10
    msg.usage = {}
    events = _message_to_events("ISS-1", msg)
    assert len(events) == 1
    assert events[0]["type"] == "agent_status"
    assert events[0]["data"]["status"] == "failed"
    assert events[0]["data"]["error"] == "budget exceeded"


def test_mixed_content_produces_multiple_events():
    from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock
    msg = MagicMock(spec=AssistantMessage)
    msg.content = [
        MagicMock(spec=TextBlock, text="Analyzing..."),
        MagicMock(spec=ToolUseBlock, name="Read", input={"file": "a.py"}),
    ]
    events = _message_to_events("ISS-1", msg)
    assert len(events) == 2
    assert events[0]["type"] == "agent_token"
    assert events[1]["type"] == "agent_tool_call"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && python -m pytest tests/core/test_executor_events.py -v`
Expected: FAIL — `ImportError: cannot import name '_message_to_events' from 'core.executor'`

- [ ] **Step 3: Implement _message_to_events and update execute_issue**

Replace `core/executor.py` with:

```python
"""Issue executor — takes one Issue, runs Ralph, returns result.

Does NOT manage state transitions. That's the scheduler's job.
"""

from __future__ import annotations
import time
from pathlib import Path
from typing import Awaitable, Callable

from claude_agent_sdk import (
    query, ClaudeAgentOptions, ResultMessage,
    AssistantMessage, SystemMessage, TextBlock, ToolUseBlock, ToolResultBlock,
)
from config import MODEL, MAX_TURNS_PER_LOOP, MAX_BUDGET_PER_LOOP
from core.models import Issue
from core.storage import ProjectStorage


C_RESET = "\033[0m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_DIM = "\033[2m"


def _log(prefix: str, color: str, msg: str) -> None:
    try:
        from harness import _tee
        _tee(f"{color}[{prefix}]{C_RESET} {msg}")
    except ImportError:
        print(f"[{prefix}] {msg}", flush=True)


def _log_message(message) -> None:
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                text = block.text[:300] + "..." if len(block.text) > 300 else block.text
                _log("Ralph", C_CYAN, text)
            elif isinstance(block, ToolUseBlock):
                inp = str(block.input)[:120]
                _log("Tool", C_YELLOW, f"{block.name}({inp})")
    elif isinstance(message, ResultMessage):
        cost = f"${message.total_cost_usd:.2f}" if message.total_cost_usd else "?"
        _log("Done", C_GREEN, f"turns={message.num_turns} cost={cost} duration={message.duration_ms // 1000}s")
        if message.is_error:
            _log("Done", C_RED, f"ERROR: {message.result}")


def _message_to_events(issue_id: str, message) -> list[dict]:
    """Convert a SDK message to a list of WebSocket event dicts."""
    ts = int(time.time())
    events: list[dict] = []

    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                events.append({
                    "ts": ts, "type": "agent_token", "issue_id": issue_id,
                    "data": {"text": block.text},
                })
            elif isinstance(block, ToolUseBlock):
                events.append({
                    "ts": ts, "type": "agent_tool_call", "issue_id": issue_id,
                    "data": {"tool": block.name, "input": block.input},
                })
    elif isinstance(message, ResultMessage):
        status = "failed" if message.is_error else "done"
        data: dict = {"status": status}
        if message.is_error:
            data["error"] = message.result
        events.append({
            "ts": ts, "type": "agent_status", "issue_id": issue_id,
            "data": data,
        })

    return events


def build_issue_prompt(issue: Issue, storage: ProjectStorage, workspace: Path) -> str:
    """Build Ralph prompt from Issue content + project context."""
    try:
        content = storage.load_issue_content(issue.id)
    except FileNotFoundError:
        content = ""

    agent_md_path = workspace / "AGENT.md"
    agent_md = agent_md_path.read_text() if agent_md_path.exists() else ""

    specs_content = ""
    for specs_dir in [workspace / ".harness" / "specs", storage.root / "specs"]:
        if specs_dir.exists():
            for f in sorted(specs_dir.glob("*.md")):
                specs_content += f"\n\n### {f.name}\n{f.read_text()}"

    base_prompt = ""
    ralph_prompt_path = Path("prompts") / "ralph_prompt.md"
    if ralph_prompt_path.exists():
        base_prompt = ralph_prompt_path.read_text()

    return f"""{base_prompt}

## 任务: {issue.title}

ID: {issue.id}
优先级: {issue.priority.value}
标签: {', '.join(issue.labels) if issue.labels else '无'}

## 任务详情

{content if content else '（无详细描述，请根据标题完成任务）'}

## 项目构建指南 (AGENT.md)
{agent_md}

## 功能规格 (specs/)
{specs_content}

## 本轮任务（只做这一项，不要做其他任务）

请只实现上面这一项任务。完成后 git commit，然后停止。
"""


async def execute_issue(
    issue: Issue,
    storage: ProjectStorage,
    workspace: Path,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
) -> dict:
    """Execute a single Issue via Ralph. Returns stats dict.

    Does NOT change issue status — caller (scheduler) handles that.
    on_event: optional async callback for streaming events to WebSocket/logs.
    """
    _log("Task", C_CYAN, f"{issue.id}: {issue.title}")

    prompt = build_issue_prompt(issue, storage, workspace)
    stats: dict = {"success": False, "issue_id": issue.id, "title": issue.title}

    # Emit thinking status
    if on_event:
        await on_event({
            "ts": int(time.time()), "type": "agent_status", "issue_id": issue.id,
            "data": {"status": "thinking"},
        })

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            model=MODEL,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent"],
            cwd=str(workspace),
            max_turns=MAX_TURNS_PER_LOOP,
            max_budget_usd=MAX_BUDGET_PER_LOOP,
            permission_mode="bypassPermissions",
        ),
    ):
        _log_message(message)

        if on_event:
            for event in _message_to_events(issue.id, message):
                await on_event(event)

        if isinstance(message, ResultMessage):
            stats.update({
                "success": not message.is_error,
                "cost_usd": message.total_cost_usd or 0,
                "duration_ms": message.duration_ms,
                "num_turns": message.num_turns,
                "usage": message.usage or {},
            })

    return stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && python -m pytest tests/core/test_executor_events.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/executor.py tests/core/test_executor_events.py
git commit -m "feat: add on_event callback and _message_to_events to executor"
```

---

### Task 5: Ralph Loop — Thread on_event, Replace event_bus

**Files:**
- Modify: `core/ralph_loop.py:44-251`

- [ ] **Step 1: Update run_issue_loop signature to accept on_event**

Replace `core/ralph_loop.py` with the following. Key changes:
- `run_issue_loop` accepts `on_event` callback
- `_run_generator` passes `on_event` to `execute_issue`
- `_sync_board` uses `on_event` instead of `event_bus`
- `run_board` and `find_ready_issues` pass `on_event` through

```python
"""Ralph Loop — Issue-based execution loop.

Takes one Issue, runs Generator + Evaluator in a loop until the Issue passes.
Harness owns all state transitions. Generator only writes code. Evaluator only verifies.

Flow:
  harness: Issue → In Progress
  loop:
    Generator (Ralph): write code + build + commit
    Evaluator: verify THIS Issue only
      - passed → break
      - failed → continue loop (Generator fixes)
      - found other problems → create new Issues on the board
  harness: collect evidence → Issue → Agent Done
"""

from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from core.models import Issue, IssueStatus, Board
from core.storage import ProjectStorage
from core.evidence import collect_evidence


C_RESET = "\033[0m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"


def _log(prefix: str, color: str, msg: str) -> None:
    try:
        from harness import _tee
        _tee(f"{color}[{prefix}]{C_RESET} {msg}")
    except ImportError:
        print(f"[{prefix}] {msg}", flush=True)


async def run_issue_loop(
    issue: Issue,
    storage: ProjectStorage,
    workspace: Path,
    max_retries: int = 3,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
) -> dict:
    """Ralph Loop for a single Issue.

    Returns stats dict with success, cost, duration, etc.
    on_event: optional async callback for streaming events to WebSocket.
    """
    all_stats: list[dict] = []

    # === 1. State: → In Progress ===
    if issue.status in (IssueStatus.TODO, IssueStatus.FAILED, IssueStatus.REJECTED):
        if issue.status == IssueStatus.REJECTED:
            issue.move_to(IssueStatus.TODO)
            storage.save_issue(issue)
        issue.move_to(IssueStatus.IN_PROGRESS)
        storage.save_issue(issue)
        _log("State", C_CYAN, f"{issue.id}: → in_progress")
        await _sync_board(issue, storage, on_event)

    # === 2. Generator + Evaluator Loop ===
    passed = False
    for attempt in range(1, max_retries + 1):
        _log("Loop", C_CYAN, f"{issue.id} attempt #{attempt}/{max_retries}")

        # --- Generator: Ralph writes code ---
        _log("Generator", C_CYAN, f"Starting: {issue.title}")
        gen_stats = await _run_generator(issue, storage, workspace, on_event)
        all_stats.append({"phase": "generator", "attempt": attempt, **gen_stats})

        if not gen_stats.get("success"):
            _log("Generator", C_RED, f"Generator failed on attempt #{attempt}")
            _append_log(issue, storage, "Generator Failed", f"Attempt #{attempt}")
            continue

        # --- Evaluator: verify THIS Issue only ---
        _log("Evaluator", C_MAGENTA, f"Verifying: {issue.title}")
        eval_result = await _run_evaluator(issue, storage, workspace)
        all_stats.append({"phase": "evaluator", "attempt": attempt, **eval_result.get("stats", {})})

        if eval_result["passed"]:
            _log("Evaluator", C_GREEN, f"Issue {issue.id} PASSED")
            passed = True
            break

        # Evaluator found problems with current Issue → continue loop
        _log("Evaluator", C_YELLOW, f"Issue {issue.id} not passed, feedback appended")
        _append_log(issue, storage, f"Eval Feedback (attempt #{attempt})", eval_result.get("feedback", ""))

        # Evaluator found OTHER problems → create new Issues
        for new_title in eval_result.get("new_issues", []):
            _create_side_issue(new_title, storage)

    # === 3. Collect evidence ===
    _log("Evidence", C_CYAN, f"Collecting evidence for {issue.id}")
    collect_evidence(issue.id, storage, workspace, run_build=True)

    # === 4. State: → Agent Done ===
    issue = storage.load_issue(issue.id)
    if issue.status == IssueStatus.IN_PROGRESS:
        issue.move_to(IssueStatus.AGENT_DONE)
        storage.save_issue(issue)
        await _sync_board(issue, storage, on_event)
        if passed:
            _log("State", C_GREEN, f"{issue.id}: → agent_done (PASSED, awaiting human review)")
        else:
            _log("State", C_YELLOW, f"{issue.id}: → agent_done (max retries, needs human review)")

    # Aggregate stats
    total_cost = sum(s.get("cost_usd", 0) for s in all_stats)
    total_duration = sum(s.get("duration_ms", 0) for s in all_stats)
    return {
        "success": passed,
        "issue_id": issue.id,
        "title": issue.title,
        "attempts": len([s for s in all_stats if s["phase"] == "generator"]),
        "cost_usd": total_cost,
        "duration_ms": total_duration,
        "details": all_stats,
    }


# ---------------------------------------------------------------------------
# Generator (Ralph)
# ---------------------------------------------------------------------------

async def _run_generator(
    issue: Issue,
    storage: ProjectStorage,
    workspace: Path,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
) -> dict:
    """Call Ralph to implement the Issue. Returns stats dict."""
    from core.executor import execute_issue
    return await execute_issue(issue, storage, workspace, on_event=on_event)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

async def _run_evaluator(issue: Issue, storage: ProjectStorage, workspace: Path) -> dict:
    """Run Evaluator to verify THIS Issue. Returns {passed, feedback, new_issues, stats}."""
    from agents.evaluator import run_issue_eval

    try:
        content = storage.load_issue_content(issue.id)
    except FileNotFoundError:
        content = ""

    screenshots_dir = storage.root / "runs" / issue.id / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        report, stats = await run_issue_eval(
            issue_id=issue.id,
            issue_title=issue.title,
            issue_content=content,
            screenshots_dir=screenshots_dir,
        )
    except Exception as e:
        _log("Evaluator", C_RED, f"Eval error: {e}")
        return {"passed": True, "feedback": "", "new_issues": [], "stats": {}}

    passed = True
    feedback_lines = []
    new_issues = []

    if report:
        for line in report.splitlines():
            stripped = line.strip()
            if stripped.startswith("- [FAIL]"):
                passed = False
                feedback_lines.append(stripped)
            elif stripped.startswith("- [NEW_ISSUE]"):
                title = stripped.removeprefix("- [NEW_ISSUE]").strip()
                if title:
                    new_issues.append(title)

    return {
        "passed": passed,
        "feedback": "\n".join(feedback_lines),
        "new_issues": new_issues,
        "stats": stats,
        "report": report,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_side_issue(title: str, storage: ProjectStorage) -> None:
    """Create a new Issue from Evaluator findings and add to board."""
    project = storage.load_project_meta()
    prefix = project.key if project else "ISS"
    issue_id = storage.next_issue_id(prefix)
    new_issue = Issue.create(id=issue_id, title=title, labels=["eval-finding"])
    new_issue.move_to(IssueStatus.TODO)
    storage.save_issue(new_issue)

    # Add to board
    board_file = storage.root / "board.json"
    if board_file.exists():
        data = json.loads(board_file.read_text())
        for col in data["columns"]:
            if col["id"] == "todo":
                col["issues"].append(new_issue.id)
                break
        board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    _log("NewIssue", C_CYAN, f"Created {new_issue.id}: {title}")


def _append_log(issue: Issue, storage: ProjectStorage, title: str, content: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        existing = storage.load_issue_content(issue.id)
    except FileNotFoundError:
        existing = ""
    entry = f"\n\n## {title} ({now})\n\n{content}\n"
    storage.save_issue_content(issue.id, existing + entry)


async def _sync_board(
    issue: Issue,
    storage: ProjectStorage,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
) -> None:
    board_file = storage.root / "board.json"
    if not board_file.exists():
        return
    data = json.loads(board_file.read_text())
    for col in data["columns"]:
        if issue.id in col["issues"]:
            col["issues"].remove(issue.id)
    status_to_col = {
        "backlog": "backlog", "todo": "todo", "in_progress": "in_progress",
        "agent_done": "agent_done", "rejected": "rejected", "human_done": "human_done",
    }
    target = status_to_col.get(issue.status.value)
    if target:
        for col in data["columns"]:
            if col["id"] == target:
                col["issues"].append(issue.id)
                break
    board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    if on_event:
        await on_event({"type": "issue_updated", "data": {"issue": issue.to_json()}})


# ---------------------------------------------------------------------------
# Board-level runner
# ---------------------------------------------------------------------------

def find_ready_issues(storage: ProjectStorage) -> list[Issue]:
    """Find issues that are TODO and have no unresolved blockers."""
    all_issues = storage.list_issues()
    done_ids = {i.id for i in all_issues if i.status == IssueStatus.HUMAN_DONE}
    return [
        i for i in all_issues
        if i.status == IssueStatus.TODO
        and all(b in done_ids for b in i.blocked_by)
    ]


async def run_board(
    storage: ProjectStorage,
    workspace: Path,
    max_parallel: int = 1,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
) -> list[dict]:
    """Run all ready issues. Supports parallel execution when max_parallel > 1."""
    all_stats = []
    ready = find_ready_issues(storage)

    if not ready:
        _log("Board", C_GREEN, "No actionable issues.")
        return all_stats

    _log("Board", C_CYAN, f"{len(ready)} ready issues (max_parallel={max_parallel})")

    if max_parallel <= 1:
        for issue in ready:
            stats = await run_issue_loop(issue, storage, workspace, on_event=on_event)
            all_stats.append(stats)
            status = "PASSED" if stats["success"] else "NEEDS REVIEW"
            _log("Board", C_GREEN if stats["success"] else C_YELLOW,
                 f"{issue.id}: {status} (${stats['cost_usd']:.2f}, {stats['attempts']} attempts)")
    else:
        semaphore = asyncio.Semaphore(max_parallel)

        async def _run_one(issue: Issue) -> dict:
            async with semaphore:
                return await run_issue_loop(issue, storage, workspace, on_event=on_event)

        tasks = [asyncio.create_task(_run_one(issue)) for issue in ready]
        for coro in asyncio.as_completed(tasks):
            stats = await coro
            all_stats.append(stats)
            status = "PASSED" if stats["success"] else "NEEDS REVIEW"
            _log("Board", C_GREEN if stats["success"] else C_YELLOW,
                 f"{stats['issue_id']}: {status} (${stats['cost_usd']:.2f}, {stats['attempts']} attempts)")

    return all_stats
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && python -m pytest tests/ -v --timeout=30 -x`
Expected: All existing tests PASS (ralph_loop signature is backward-compatible via `on_event=None` default)

- [ ] **Step 3: Commit**

```bash
git add core/ralph_loop.py
git commit -m "feat: thread on_event callback through ralph_loop, replace event_bus in _sync_board"
```

---

### Task 6: Run Route — Wire on_event to WebSocket Manager + Cancellation

**Files:**
- Modify: `server/routes/run.py:1-64`

- [ ] **Step 1: Replace server/routes/run.py with WebSocket-based version**

Replace the full content of `server/routes/run.py`:

```python
"""Run API routes — trigger issue execution from the Web UI."""

from __future__ import annotations
import asyncio
from typing import Set

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from core.storage import ProjectStorage

router = APIRouter(prefix="/api/projects/{project_id}/run", tags=["run"])

# Active cancellation flags — issue_ids that should be cancelled
_cancel_flags: Set[str] = set()


def cancel_agent(issue_id: str) -> None:
    """Set cancellation flag for an issue. Called from WS route."""
    _cancel_flags.add(issue_id)


def is_cancelled(issue_id: str) -> bool:
    """Check if an issue has been cancelled."""
    return issue_id in _cancel_flags


def clear_cancel(issue_id: str) -> None:
    """Clear cancellation flag after run completes."""
    _cancel_flags.discard(issue_id)


def _get_storage(project_id: str) -> ProjectStorage:
    from server.app import get_harness_root
    project_dir = get_harness_root() / "projects" / project_id
    if not project_dir.exists():
        raise HTTPException(404, f"Project {project_id} not found")
    return ProjectStorage(project_dir)


class RunRequest(BaseModel):
    issue_id: str | None = None


async def _run_in_background(project_id: str, issue_id: str | None) -> None:
    from server.app import get_harness_root
    from server.ws import ws_manager
    from core.ralph_loop import run_issue_loop, find_ready_issues
    from config import WORKSPACE_DIR
    import time

    project_dir = get_harness_root() / "projects" / project_id
    storage = ProjectStorage(project_dir)

    run_counter = 0

    async def on_event(event: dict) -> None:
        """Broadcast event via WebSocket and persist to JSONL log."""
        await ws_manager.broadcast(project_id, event)
        # Persist agent events to run log
        evt_type = event.get("type", "")
        evt_issue_id = event.get("issue_id")
        if evt_issue_id and evt_type.startswith("agent_"):
            storage.append_run_log(evt_issue_id, f"run-{run_counter:03d}", event)

    if issue_id:
        try:
            issue = storage.load_issue(issue_id)
        except FileNotFoundError:
            await ws_manager.broadcast(project_id, {
                "type": "run_error", "data": {"issue_id": issue_id, "error": "Issue not found"},
            })
            return

        run_counter = len(storage.list_run_ids(issue_id)) + 1
        await ws_manager.broadcast(project_id, {
            "type": "agent_started", "data": {"issue_id": issue_id, "title": issue.title},
        })
        stats = await run_issue_loop(issue, storage, WORKSPACE_DIR, on_event=on_event)
        clear_cancel(issue_id)
        await ws_manager.broadcast(project_id, {
            "type": "agent_done", "data": {
                "issue_id": issue_id, "success": stats["success"],
                "cost_usd": stats.get("cost_usd", 0),
            },
        })
    else:
        ready = find_ready_issues(storage)
        if not ready:
            await ws_manager.broadcast(project_id, {
                "type": "run_error", "data": {"error": "No actionable issues"},
            })
            return

        for issue in ready:
            run_counter = len(storage.list_run_ids(issue.id)) + 1
            await ws_manager.broadcast(project_id, {
                "type": "agent_started", "data": {"issue_id": issue.id, "title": issue.title},
            })
            stats = await run_issue_loop(issue, storage, WORKSPACE_DIR, on_event=on_event)
            clear_cancel(issue.id)
            await ws_manager.broadcast(project_id, {
                "type": "agent_done", "data": {
                    "issue_id": issue.id, "success": stats["success"],
                    "cost_usd": stats.get("cost_usd", 0),
                },
            })


@router.post("")
async def run_issues(project_id: str, req: RunRequest, background_tasks: BackgroundTasks):
    _get_storage(project_id)  # validate project exists
    background_tasks.add_task(_run_in_background, project_id, req.issue_id)
    return {"ok": True, "issue_id": req.issue_id}
```

- [ ] **Step 2: Verify import works**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && python -c "from server.routes.run import cancel_agent, is_cancelled; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add server/routes/run.py
git commit -m "feat: wire run route to WebSocket manager, add cancellation support"
```

---

### Task 7: Issues Route — Replace event_bus with ws_manager + Add Log Endpoints

**Files:**
- Modify: `server/routes/issues.py:201-209` (replace `_publish`)
- Add: log REST endpoints at end of file

- [ ] **Step 1: Replace _publish helper to use ws_manager**

In `server/routes/issues.py`, replace the `_publish` function (lines 201-208) with:

```python
def _publish(event_type: str, data: dict):
    from server.ws import ws_manager
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        # Extract project_id from the data if available, or broadcast to all
        # Issues routes always have project_id in scope via the caller
        # We use a fire-and-forget pattern here since these are sync route handlers
        loop.create_task(ws_manager.broadcast(_current_project_id.get(), {"type": event_type, "data": data}))
    except RuntimeError:
        pass
```

Wait — the issue is that `_publish` doesn't know the `project_id`. The current code has the same problem (global EventBus). We need to thread `project_id` through. The cleanest approach: change `_publish` to accept `project_id`.

Replace the `_publish` function and update all call sites. Full replacement of `server/routes/issues.py`:

```python
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
    project = storage.load_project_meta()
    prefix = project.key if project else "ISS"
    issue_id = storage.next_issue_id(prefix)
    issue = Issue.create(id=issue_id, title=req.title, priority=req.priority, labels=req.labels)
    issue.workspace = req.workspace
    for blocker_id in req.blocked_by:
        issue.add_blocker(blocker_id)
    storage.save_issue(issue)

    if req.description:
        content = f"# {issue.id}: {issue.title}\n\n## 描述\n\n{req.description}\n"
        storage.save_issue_content(issue.id, content)

    _add_to_board(project_id, issue.id, "backlog")
    _publish(project_id, "issue_created", {"issue": issue.to_json()})
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
        try:
            issue.move_to(new_status)
        except ValueError as e:
            raise HTTPException(400, str(e))

    storage.save_issue(issue)

    if req.status is not None:
        _sync_board_column(project_id, issue_id, req.status)

    _publish(project_id, "issue_updated", {"issue": issue.to_json()})
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


@router.delete("/{issue_id}")
def delete_issue(project_id: str, issue_id: str):
    storage = _get_storage(project_id)
    issue_dir = storage.issues_dir / issue_id
    if not issue_dir.exists():
        raise HTTPException(404, f"Issue {issue_id} not found")

    import shutil
    shutil.rmtree(issue_dir)

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


# --- Board helpers ---

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


def _remove_from_board(project_id: str, issue_id: str):
    from server.app import get_harness_root
    board_file = get_harness_root() / "projects" / project_id / "board.json"
    if not board_file.exists():
        return
    data = json.loads(board_file.read_text())
    for col in data["columns"]:
        if issue_id in col["issues"]:
            col["issues"].remove(issue_id)
    board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _sync_board_column(project_id: str, issue_id: str, status: str):
    """Move issue to the board column matching its new status."""
    from server.app import get_harness_root
    board_file = get_harness_root() / "projects" / project_id / "board.json"
    if not board_file.exists():
        return
    data = json.loads(board_file.read_text())
    for col in data["columns"]:
        if issue_id in col["issues"]:
            col["issues"].remove(issue_id)
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
```

- [ ] **Step 2: Verify import works**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && python -c "from server.routes.issues import router; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add server/routes/issues.py
git commit -m "feat: replace event_bus with ws_manager in issues route, add log REST endpoints"
```

---

### Task 8: Frontend — useWebSocket Hook

**Files:**
- Create: `web/src/hooks/useWebSocket.ts`

- [ ] **Step 1: Create useWebSocket hook**

```typescript
// web/src/hooks/useWebSocket.ts
import { useEffect, useRef, useCallback } from 'react'
import { useBoardStore, generateLogId } from '../stores/boardStore'
import { useProjectStore } from '../stores/projectStore'

const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000

export function useWebSocket() {
  const projectId = useBoardStore(s => s.projectId)
  const updateIssueFromEvent = useBoardStore(s => s.updateIssueFromEvent)
  const moveBoardFromEvent = useBoardStore(s => s.moveBoardFromEvent)
  const fetchBoard = useBoardStore(s => s.fetchBoard)
  const fetchIssues = useBoardStore(s => s.fetchIssues)
  const addSSELog = useBoardStore(s => s.addSSELog)
  const appendAgentLog = useBoardStore(s => s.appendAgentLog)
  const fetchProjects = useProjectStore(s => s.fetchProjects)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttempt = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const sendMessage = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  useEffect(() => {
    if (!projectId) return

    let disposed = false

    function connect() {
      if (disposed) return

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/api/projects/${projectId}/ws`)
      wsRef.current = ws

      const logEvent = (type: string, message: string, issueId?: string) => {
        addSSELog({
          id: generateLogId(),
          type,
          message,
          timestamp: new Date().toISOString(),
          issueId,
        })
      }

      ws.onopen = () => {
        reconnectAttempt.current = 0
      }

      ws.onmessage = (event) => {
        let data: Record<string, any>
        try {
          data = JSON.parse(event.data)
        } catch {
          return
        }

        const type = data.type as string
        const payload = data.data as Record<string, any> | undefined

        switch (type) {
          case 'ping':
            sendMessage({ type: 'pong' })
            break

          // --- Board events (same as old SSE) ---
          case 'issue_updated':
            if (payload?.issue) {
              updateIssueFromEvent(payload.issue)
              logEvent('issue_updated', `Issue ${payload.issue.id} updated: ${payload.issue.title}`, payload.issue.id)
              fetchProjects()
            }
            break

          case 'issue_created':
            logEvent('issue_created', `Issue created: ${payload?.issue?.title || payload?.issue_id || 'unknown'}`, payload?.issue_id)
            fetchBoard()
            fetchIssues()
            fetchProjects()
            break

          case 'issue_moved':
            if (payload) {
              moveBoardFromEvent(payload.issue_id, payload.to_column)
              logEvent('issue_moved', `Issue ${payload.issue_id} moved to ${payload.to_column}`, payload.issue_id)
            }
            break

          case 'issue_approved':
            logEvent('issue_approved', `Issue ${payload?.issue_id || 'unknown'} approved`, payload?.issue_id)
            fetchBoard()
            fetchIssues()
            fetchProjects()
            break

          case 'issue_rejected':
            logEvent('issue_rejected', `Issue ${payload?.issue_id || 'unknown'} rejected`, payload?.issue_id)
            fetchBoard()
            fetchIssues()
            fetchProjects()
            break

          case 'issue_deleted':
            logEvent('issue_deleted', `Issue ${payload?.issue_id || 'unknown'} deleted`, payload?.issue_id)
            fetchBoard()
            fetchIssues()
            fetchProjects()
            break

          // --- Agent streaming events ---
          case 'agent_started':
            logEvent('agent_started', `Agent started on ${payload?.issue_id || 'unknown'}`, payload?.issue_id)
            fetchBoard()
            fetchIssues()
            break

          case 'agent_done':
            logEvent('agent_done', `Agent completed ${payload?.issue_id || 'unknown'}`, payload?.issue_id)
            fetchBoard()
            fetchIssues()
            fetchProjects()
            break

          case 'agent_token':
            if (data.issue_id) {
              appendAgentLog(data.issue_id, {
                ts: data.ts, type: 'agent_token', data: data.data,
              })
            }
            break

          case 'agent_tool_call':
            if (data.issue_id) {
              appendAgentLog(data.issue_id, {
                ts: data.ts, type: 'agent_tool_call', data: data.data,
              })
            }
            break

          case 'agent_status':
            if (data.issue_id) {
              appendAgentLog(data.issue_id, {
                ts: data.ts, type: 'agent_status', data: data.data,
              })
            }
            break

          case 'run_error':
            logEvent('run_error', payload?.issue_id ? `${payload.issue_id}: ${payload.error}` : (payload?.error || 'Run failed'), payload?.issue_id)
            break
        }
      }

      ws.onclose = () => {
        wsRef.current = null
        if (!disposed) {
          const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt.current), RECONNECT_MAX_MS)
          reconnectAttempt.current++
          reconnectTimer.current = setTimeout(connect, delay)
        }
      }

      ws.onerror = () => {
        // onclose will fire after onerror, reconnect handled there
      }
    }

    connect()

    return () => {
      disposed = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [projectId, updateIssueFromEvent, moveBoardFromEvent, fetchBoard, fetchIssues, addSSELog, appendAgentLog, fetchProjects, sendMessage])

  return { sendMessage }
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/hooks/useWebSocket.ts
git commit -m "feat: add useWebSocket hook with auto-reconnect and agent event dispatch"
```

---

### Task 9: Frontend — boardStore Agent Log State

**Files:**
- Modify: `web/src/stores/boardStore.ts`

- [ ] **Step 1: Add AgentLogEntry interface and agentLogs state**

In `web/src/stores/boardStore.ts`, add the `AgentLogEntry` interface after the `SSELogEntry` interface (after line 32):

```typescript
export interface AgentLogEntry {
  ts: number
  type: string
  data: Record<string, any>
}
```

- [ ] **Step 2: Add agentLogs to BoardState interface**

In the `BoardState` interface, add after the `sseLog` line (after line 47):

```typescript
  agentLogs: Record<string, AgentLogEntry[]>
```

And add the action signatures after `clearSSELog` (after line 60):

```typescript
  appendAgentLog: (issueId: string, entry: AgentLogEntry) => void
  clearAgentLog: (issueId: string) => void
```

- [ ] **Step 3: Add initial state and action implementations**

In the store creation, add after `sseLog: [],` (after line 72):

```typescript
  agentLogs: {},
```

Add the action implementations after the `clearSSELog` action (after line 216):

```typescript
  appendAgentLog: (issueId, entry) => {
    set(state => {
      const existing = state.agentLogs[issueId] || []
      return {
        agentLogs: {
          ...state.agentLogs,
          [issueId]: [...existing.slice(-499), entry],
        },
      }
    })
  },

  clearAgentLog: (issueId) => {
    set(state => {
      const { [issueId]: _, ...rest } = state.agentLogs
      return { agentLogs: rest }
    })
  },
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko/web && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors related to boardStore

- [ ] **Step 5: Commit**

```bash
git add web/src/stores/boardStore.ts
git commit -m "feat: add agentLogs state and actions to boardStore"
```

---

### Task 10: Frontend — AgentLogPanel Component

**Files:**
- Create: `web/src/components/AgentLogPanel.tsx`

- [ ] **Step 1: Create AgentLogPanel component**

```tsx
// web/src/components/AgentLogPanel.tsx
import { useRef, useEffect, useState } from 'react'
import { useBoardStore } from '../stores/boardStore'
import type { AgentLogEntry } from '../stores/boardStore'
import { Terminal, Square, ChevronDown, History } from 'lucide-react'

interface AgentLogPanelProps {
  issueId: string
  onCancel?: () => void
}

function formatEntry(entry: AgentLogEntry): { label: string; color: string; text: string } {
  switch (entry.type) {
    case 'agent_token':
      return { label: 'LLM', color: 'text-cyan-500', text: entry.data.text || '' }
    case 'agent_tool_call':
      return {
        label: 'Tool',
        color: 'text-yellow-500',
        text: `${entry.data.tool}(${JSON.stringify(entry.data.input).slice(0, 120)})`,
      }
    case 'agent_status': {
      const s = entry.data.status
      const color = s === 'done' ? 'text-green-500' : s === 'failed' ? 'text-red-500' : 'text-blue-500'
      const text = s === 'failed' ? `${s}: ${entry.data.error || ''}` : s
      return { label: 'Status', color, text }
    }
    default:
      return { label: entry.type, color: 'text-gray-400', text: JSON.stringify(entry.data) }
  }
}

export function AgentLogPanel({ issueId, onCancel }: AgentLogPanelProps) {
  const agentLogs = useBoardStore(s => s.agentLogs[issueId] || [])
  const [historyRuns, setHistoryRuns] = useState<string[]>([])
  const [selectedRun, setSelectedRun] = useState<string | null>(null)
  const [historyEntries, setHistoryEntries] = useState<AgentLogEntry[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const projectId = useBoardStore(s => s.projectId)

  // Auto-scroll to bottom on new entries
  useEffect(() => {
    if (!showHistory && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [agentLogs, showHistory])

  // Fetch history runs list
  useEffect(() => {
    if (!projectId) return
    fetch(`/api/projects/${projectId}/issues/${issueId}/logs`)
      .then(r => r.json())
      .then(data => setHistoryRuns(data.runs || []))
      .catch(() => {})
  }, [projectId, issueId])

  // Fetch selected history run
  useEffect(() => {
    if (!projectId || !selectedRun) return
    fetch(`/api/projects/${projectId}/issues/${issueId}/logs/${selectedRun}`)
      .then(r => r.json())
      .then(data => setHistoryEntries(data.entries || []))
      .catch(() => {})
  }, [projectId, issueId, selectedRun])

  const entries = showHistory ? historyEntries : agentLogs
  const isRunning = agentLogs.length > 0 && agentLogs[agentLogs.length - 1]?.data?.status !== 'done' && agentLogs[agentLogs.length - 1]?.data?.status !== 'failed'

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 bg-[var(--bg-secondary)] border-b border-[var(--border)] flex items-center gap-2">
        <Terminal size={16} className="text-cyan-500" />
        <h3 className="text-sm font-semibold text-[var(--text-primary)] flex-1">Agent Log</h3>

        {historyRuns.length > 0 && (
          <button
            onClick={() => {
              setShowHistory(!showHistory)
              if (!showHistory && historyRuns.length > 0 && !selectedRun) {
                setSelectedRun(historyRuns[historyRuns.length - 1])
              }
            }}
            className={`flex items-center gap-1 text-xs px-2 py-1 rounded ${showHistory ? 'bg-[var(--accent)] text-white' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}`}
          >
            <History size={12} /> History
          </button>
        )}

        {isRunning && onCancel && (
          <button
            onClick={onCancel}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-red-600 text-white hover:bg-red-700"
          >
            <Square size={12} /> Cancel
          </button>
        )}
      </div>

      {showHistory && historyRuns.length > 0 && (
        <div className="px-4 py-2 border-b border-[var(--border)] flex gap-1 overflow-x-auto">
          {historyRuns.map(run => (
            <button
              key={run}
              onClick={() => setSelectedRun(run)}
              className={`text-xs px-2 py-0.5 rounded ${selectedRun === run ? 'bg-[var(--accent)] text-white' : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}`}
            >
              {run}
            </button>
          ))}
        </div>
      )}

      <div ref={scrollRef} className="h-[240px] overflow-y-auto px-4 py-2 font-mono text-xs space-y-0.5">
        {entries.length === 0 && (
          <div className="text-[var(--text-secondary)] py-8 text-center">
            {showHistory ? 'No entries in this run.' : 'No agent activity yet. Run the issue to see live output.'}
          </div>
        )}
        {entries.map((entry, i) => {
          const { label, color, text } = formatEntry(entry)
          return (
            <div key={i} className="flex gap-2">
              <span className={`shrink-0 ${color}`}>[{label}]</span>
              <span className="text-[var(--text-primary)] whitespace-pre-wrap break-all">{text}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/AgentLogPanel.tsx
git commit -m "feat: add AgentLogPanel component with live streaming and history"
```

---

### Task 11: Frontend — Wire Up App.tsx, IssueDetail, RunLogPanel

**Files:**
- Modify: `web/src/App.tsx:6,45`
- Modify: `web/src/components/IssueDetail.tsx`
- Modify: `web/src/components/RunLogPanel.tsx:61`

- [ ] **Step 1: Replace useSSE with useWebSocket in App.tsx**

In `web/src/App.tsx`, change the import (line 6):

```typescript
// OLD:
import { useSSE } from './hooks/useSSE'
// NEW:
import { useWebSocket } from './hooks/useWebSocket'
```

And change the hook call (line 45):

```typescript
// OLD:
useSSE()
// NEW:
const { sendMessage } = useWebSocket()
```

- [ ] **Step 2: Add AgentLogPanel to IssueDetail**

In `web/src/components/IssueDetail.tsx`, add the import at the top (after the existing imports):

```typescript
import { AgentLogPanel } from './AgentLogPanel'
```

Then add the AgentLogPanel section in the component body, right before the `{/* Content */}` section (before line 339 in the original). Insert between the Run Action section and the Evidence Panel:

```tsx
          {/* Agent Log */}
          {['in_progress', 'agent_done'].includes(issue.status) && (
            <AgentLogPanel
              issueId={issue.id}
              onCancel={() => {
                const projectId = useBoardStore.getState().projectId
                if (!projectId) return
                // Send cancel via WebSocket — we need access to sendMessage
                // For now, use a REST fallback or direct WS access
                // The simplest approach: post to a cancel endpoint
                fetch(`/api/projects/${projectId}/issues/${issue.id}/cancel`, { method: 'POST' }).catch(() => {})
              }}
            />
          )}
```

Wait — the cancel should go through WebSocket. But `IssueDetail` doesn't have access to `sendMessage`. The cleanest approach: expose `sendMessage` via a store or pass it as prop. Since the cancel is a rare action, let's add a simple REST endpoint as a thin wrapper. Actually, simpler: store the `sendMessage` function in the board store.

Revised approach — add `wsSend` to boardStore:

In `web/src/stores/boardStore.ts`, add to the interface (after `clearAgentLog`):

```typescript
  wsSend: ((msg: Record<string, unknown>) => void) | null
  setWsSend: (fn: ((msg: Record<string, unknown>) => void) | null) => void
```

Add to the store creation (after `agentLogs: {}`):

```typescript
  wsSend: null,
  setWsSend: (fn) => set({ wsSend: fn }),
```

In `web/src/hooks/useWebSocket.ts`, add at the end of the `ws.onopen` handler:

```typescript
      ws.onopen = () => {
        reconnectAttempt.current = 0
        useBoardStore.getState().setWsSend(sendMessage)
      }
```

And in the cleanup:

```typescript
      useBoardStore.getState().setWsSend(null)
```

Now in `IssueDetail.tsx`, the cancel handler becomes:

```tsx
          {/* Agent Log */}
          {['in_progress', 'agent_done'].includes(issue.status) && (
            <AgentLogPanel
              issueId={issue.id}
              onCancel={() => {
                const wsSend = useBoardStore.getState().wsSend
                if (wsSend) {
                  wsSend({ type: 'cancel_agent', issue_id: issue.id })
                }
              }}
            />
          )}
```

- [ ] **Step 3: Update RunLogPanel label**

In `web/src/components/RunLogPanel.tsx`, change the label (line 61):

```typescript
// OLD:
<span className="text-xs font-medium text-[var(--text-secondary)]">SSE Events</span>
// NEW:
<span className="text-xs font-medium text-[var(--text-secondary)]">Events</span>
```

Also update the empty state message (line 73):

```typescript
// OLD:
No events yet. Events will appear here as they arrive via SSE.
// NEW:
No events yet. Events will appear here as they arrive.
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko/web && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add web/src/App.tsx web/src/components/IssueDetail.tsx web/src/components/RunLogPanel.tsx web/src/stores/boardStore.ts web/src/hooks/useWebSocket.ts
git commit -m "feat: wire useWebSocket into App, add AgentLogPanel to IssueDetail, update RunLogPanel"
```

---

### Task 12: Cleanup — Delete SSE Files

**Files:**
- Delete: `server/sse.py`
- Delete: `web/src/hooks/useSSE.ts`

- [ ] **Step 1: Delete SSE files**

```bash
rm server/sse.py
rm web/src/hooks/useSSE.ts
```

- [ ] **Step 2: Verify no remaining imports of deleted modules**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && grep -r "from server.sse" --include="*.py" .`
Expected: No matches

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && grep -r "useSSE\|from.*hooks/useSSE" --include="*.ts" --include="*.tsx" web/`
Expected: No matches

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && grep -r "sse_starlette\|sse-starlette" --include="*.py" --include="*.txt" --include="*.toml" .`
Expected: No matches (or only in requirements — remove from there too if found)

- [ ] **Step 3: Remove sse-starlette from dependencies if present**

Check `requirements.txt` or `pyproject.toml` for `sse-starlette` and remove it.

- [ ] **Step 4: Final verification — server starts clean**

Run: `cd /Users/cn-edisonhuang01/MyWorks/ekko && python -c "from server.app import create_app; app = create_app(); print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove SSE files and sse-starlette dependency"
```

---

## Verification Checklist

After all tasks are complete, run through these checks:

1. `python -m pytest tests/ -v` — all tests pass
2. `cd web && npx tsc --noEmit` — no TypeScript errors
3. Start server: `harness serve --dev`, open browser to kanban board
4. Create an issue and run it — verify WebSocket connection in browser DevTools (Network → WS tab)
5. During agent execution, open IssueDetail — verify live token stream and tool calls in AgentLogPanel
6. Click Cancel button during execution — verify agent stops
7. After completion, switch to History tab in AgentLogPanel — verify past runs are listed and viewable
8. Drag issues on board, create/delete issues — verify board events still work via WebSocket
9. Kill server and restart — verify WebSocket auto-reconnects in browser
10. Open two browser tabs — verify both receive events independently
