# Harness Kanban 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 blog-harness 从 fix_plan.md 扁平 checklist 升级为 Issue 看板系统，支持状态流转、依赖关系、多 agent 并行、人类审核、本地 Web UI。

**Architecture:** Python 后端（FastAPI）+ React 前端（Vite + Radix + dnd-kit）。数据存储用 JSON 索引 + Markdown 内容。执行引擎基于现有 Ralph Loop 升级为并行调度。

**Tech Stack:** Python 3.11+, FastAPI, claude-agent-sdk, Vite, React 18, TanStack Router, Zustand, Radix UI, TailwindCSS, @dnd-kit, Lexical, SSE

---

## Phase 1: 核心数据模型 (Python)

### Task 1: Issue 数据模型

**Files:**
- Create: `core/models.py`
- Create: `core/__init__.py`
- Test: `tests/test_models.py`

**Step 1: Write the failing test**

```python
# tests/test_models.py
import pytest
from core.models import Issue, IssueStatus, IssuePriority

def test_create_issue():
    issue = Issue.create(title="实现登录页", priority="high", labels=["auth"])
    assert issue.id.startswith("ISS-")
    assert issue.status == IssueStatus.BACKLOG
    assert issue.priority == IssuePriority.HIGH
    assert issue.blocks == []
    assert issue.blocked_by == []

def test_issue_status_transition():
    issue = Issue.create(title="test")
    issue.move_to(IssueStatus.TODO)
    assert issue.status == IssueStatus.TODO
    issue.move_to(IssueStatus.IN_PROGRESS)
    assert issue.status == IssueStatus.IN_PROGRESS

def test_issue_invalid_transition():
    issue = Issue.create(title="test")
    with pytest.raises(ValueError):
        issue.move_to(IssueStatus.HUMAN_DONE)  # can't skip to done

def test_issue_dependency():
    a = Issue.create(title="A")
    b = Issue.create(title="B")
    b.add_blocker(a.id)
    assert a.id in b.blocked_by
    assert b.is_blocked()

def test_issue_serialization():
    issue = Issue.create(title="test", labels=["bug"])
    data = issue.to_json()
    loaded = Issue.from_json(data)
    assert loaded.id == issue.id
    assert loaded.title == issue.title
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/cn-edisonhuang01/MyWorks/blog-harness && python -m pytest tests/test_models.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# core/models.py
from __future__ import annotations
import json
import time
import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone


class IssueStatus(str, Enum):
    BACKLOG = "backlog"
    PLANNING = "planning"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    AGENT_DONE = "agent_done"
    HUMAN_DONE = "human_done"
    FAILED = "failed"
    REJECTED = "rejected"

# Valid transitions
VALID_TRANSITIONS = {
    IssueStatus.BACKLOG: {IssueStatus.PLANNING, IssueStatus.TODO},
    IssueStatus.PLANNING: {IssueStatus.TODO, IssueStatus.BACKLOG},
    IssueStatus.TODO: {IssueStatus.IN_PROGRESS, IssueStatus.BACKLOG},
    IssueStatus.IN_PROGRESS: {IssueStatus.AGENT_DONE, IssueStatus.FAILED, IssueStatus.TODO},
    IssueStatus.AGENT_DONE: {IssueStatus.HUMAN_DONE, IssueStatus.REJECTED},
    IssueStatus.FAILED: {IssueStatus.IN_PROGRESS, IssueStatus.TODO},
    IssueStatus.REJECTED: {IssueStatus.TODO},
    IssueStatus.HUMAN_DONE: set(),  # terminal
}


class IssuePriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Issue:
    id: str
    title: str
    status: IssueStatus = IssueStatus.BACKLOG
    priority: IssuePriority = IssuePriority.MEDIUM
    assignee: str | None = None
    workspace: str = "default"
    blocks: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    spec_ref: str | None = None
    run_ids: list[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3

    @classmethod
    def create(cls, title: str, priority: str = "medium", labels: list[str] = None) -> Issue:
        now = datetime.now(timezone.utc).isoformat()
        short_hash = hashlib.md5(f"{title}{time.time()}".encode()).hexdigest()[:6]
        issue_id = f"ISS-{short_hash}"
        return cls(
            id=issue_id, title=title,
            priority=IssuePriority(priority),
            labels=labels or [],
            created_at=now, updated_at=now,
        )

    def move_to(self, new_status: IssueStatus) -> None:
        if new_status not in VALID_TRANSITIONS.get(self.status, set()):
            raise ValueError(f"Invalid transition: {self.status} -> {new_status}")
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_blocker(self, issue_id: str) -> None:
        if issue_id not in self.blocked_by:
            self.blocked_by.append(issue_id)

    def remove_blocker(self, issue_id: str) -> None:
        if issue_id in self.blocked_by:
            self.blocked_by.remove(issue_id)

    def is_blocked(self) -> bool:
        return len(self.blocked_by) > 0

    def to_json(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["priority"] = self.priority.value
        return d

    @classmethod
    def from_json(cls, data: dict) -> Issue:
        data["status"] = IssueStatus(data["status"])
        data["priority"] = IssuePriority(data["priority"])
        return cls(**data)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS

**Step 5: C
```bash
git add core/ tests/test_models.py
git commit -m "feat: add Issue data model with status transitions and dependencies"
```

---

### Task 2: Project 和 Board 数据模型

**Files:**
- Modify: `core/models.py`
- Test: `tests/test_models.py` (append)

**Step 1: Write failing tests**

```python
def test_create_project():
    project = Project.create(name="技术博客", workspace_path="/tmp/workspace")
    assert project.id
    assert project.name == "技术博客"
    assert len(project.workspaces) == 1

def test_board_columns():
    board = Board.create()
    assert len(board.columns) == 6
    assert board.columns[0].id == "backlog"
    assert board.columns[-1].id == "human_done"

def test_board_add_issue():
    board = Board.create()
    board.add_issue("ISS-001", "backlog")
    assert "ISS-001" in board.columns[0].issues

def test_board_move_issue():
    board = Board.create()
    board.add_issue("ISS-001", "backlog")
    board.move_issue("ISS-001", "todo")
    assert "ISS-001" not in board.columns[0].issues
    assert "ISS-001" in board.get_column("todo").issues
```

**Step 2-5:** Implement Project/Board dataclasses, run tests, commit.

---

### Task 3: 文件存储层

**Files:**
- Create: `core/storage.py`
- Test: `tests/t_storage.py`

**Step 1: Write failing tests**

```python
def test_save_and_load_issue(tmp_path):
    store = ProjectStorage(tmp_path / "project")
    issue = Issue.create(title="test issue")
    store.save_issue(issue)
    loaded = store.load_issue(issue.id)
    assert loaded.title == "test issue"

def test_save_issue_markdown(tmp_path):
    store = ProjectStorage(tmp_path / "project")
    issue = Issue.create(title="test")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Description\n\nSome content")
    content = store.load_issue_content(issue.id)
    assert "# Description" in content

def test_list_issues(tmp_path):
    store = ProjectStorage(tmp_path / "project")
    store.save_issue(Issue.create(title="A"))
    store.save_issue(Issue.create(title="B"))
    issues = store.list_issues()
    assert len(issues) == 2
```

**Step 2-5:** Implement JSON read/write + Markdown content, run tests, commit.

---

## Phase 2: 执行引擎

### Task 4: 重构 Ralph 执行为 Issue-based

**Files:**
- Create: `core/executor.py`
- Modify: `agents/ralph_loop.py` — 提取 `run_one_ralph_cycle` 改为接受 Issue 参数
- Test: `tests/test_executor.py`

核心变更：`run_one_ralph_cycle()` 改为 `run_issue_cycle(issue: Issue, project: Projec 的 Markdown 内容构建 prompt 而非从 fix_plan.md。

---

### Task 5: 证据收集模块

**Files:**
- Create: `core/evidence.py`
- Test: `tests/test_evidence.py`

Agent Done 时自动收集：git diff、build 结果、截图，写入 Issue Markdown 的 `## Agent Done 证据` section。

---

### Task 6: 并行调度器

**Files:**
- Create: `core/scheduler.py`
- Test: `tests/test_scheduler.py`

实现 `run_board()` — 找出可执行 Issue（Todo + 无 blocker），分配给空闲 agent，asyncio.create_task 并行执行。

---

### Task 7: Human Review 流程

**Files:**
- Create: `core/review.py`
- Test: `tests/test_review.py`

实现 approve/reject 逻辑：approve → Human Done + 解锁依赖；reject → 追加反馈到 Issue Markdown + 打回 Todo。

---

## Phase 3: CLI

### Task 8: CLI 入口重构

**Files:**
- Create: `cli.py` — 用 argparse 或 click
- Modify: `harness.py` → 保留为向后兼容入口

子命令：`project`, `board`, `issue`, `plan`, `run`, `review`, `serve`

---

### Task 9: Issue CLI 命令

```bash
harness issue create "标题" --label bug --priority high
harness issue list [--status todo]
harness issue show ISS-001
harness issue move ISS-001 todo
```

---

### Task 10: Review CLI 命令

```bash
harness review ISS-001 --approve
harness review ISS-001 --reject --comment "缺少 loading 状态"
```

---

## Phase 4: FastAPI 后端

### Task 11: API 服务器骨架

**Files:**
- Create: `server/__init__.py`
- Create: `server/app.py` — FastAPI app
- Create: `server/routes/issues.py`
- Create: `server/routes/board.py`
- Create: `server/routes/projects.py`
- Create: `server/routes/reviews.py`
- Create: `server/sse.py` — SSE 事件推送

API 端点：
- `GET /api/projects` / `POST /api/projects`
- `GET /api/projects/:id/board`
- `GET /api/projects/:id/issues` / `POST /api/projects/:id/issues`
- `GET /api/projects/:id/issues/:id` / `PATCH /api/projects/:id/issues/:id`
- `POST /api/projects/:id/issues/:id/review`
- `POST /api/projects/:id/issues/:id/move`
- `GET /api/projects/:id/events` (SSE)

---

### Task 12: SSE 实时推送

Agent 执行状态变更时推送事件到前端：issue_updated, agent_started, agent_done, eval_result。

---

## Phase 5: Web UI (Vite + React)

### Task 13: 前端项目脚手架

**Files:**
- Create: `web/` — Vite + React + TailwindCSS + Radix 项目
- `web/package.json`, `web/vite.config.ts`, `web/tailwind.config.ts`
- `web/src/main.tsx`, `web/src/App.tsx`

```bash
cd web && npm create vite@latest . -- --template react-ts
npm install @radix-ui/react-dialog @radix-ui/react-dropdown-menu @dnd-kit/core @dnd-kit/sortable zustand lucide-react tailwindcss framer-motion
```

---

### Task 14: Board 看板视图

**Files:**
- Create: `web/src/components/Board.tsx`
- Create: `web/src/components/Column.tsx`
- Create: `web/src/components/IssueCard.tsx`
- Create: `web/src/stores/boardStore.ts`

6 列看板，@dnd-kit 拖拽 Issue 在列之间移动，拖拽完成时调 `PATCH /api/.../move`。

---

### Task 15: Issue 详情面板

**Files:**
- Create: `web/src/components/IssueDetail.tsx`
- Create: `web/src/components/MarkdownViewer.tsx`
- Create: `web/src/components/EvidencePanel.tsx`

Markdown 渲染（Issue 内容）、图片展示、agent 日志、diff 查看。

---

### Task 16: 审核面板

**Files:**
- Create: `web/src/components/ReviewPanel.tsx`

Approve / Reject 按钮 + 反馈文本框 + 截图上传。调 `POST /api/.../revie

### Task 17: 实时更新 (SSE)

**Files:**
- Create: `web/src/hooks/useSSE.ts`
- Modify: `web/src/stores/boardStore.ts`

监听 `/api/projects/:id/events`，实时更新看板状态。

---

## Phase 6: 集成与迁移

### Task 18: `harness serve` 命令

启动 FastAPI 后端 + Vite dev server（开发模式）或 serve 构建产物（生产模式）。

---

### Task 19: 迁移工具

**Files:**
- Create: `core/migrate.py`

将现有 `fix_plan.md` 的 `- [ ]` / `- [x]` 项转为 Issue，保留历史。

---

### Task 20: Planning 集成

将现有 Planner agent 改为产出 Issue（带 blocks/blocked_by），而非写 fix_plan.md。

---

## 执行顺序

```
Phase 1 (Task 1-3)  → 核心数据模型，可独立测试
Phase 2 (Task 4-7)  → 执行引擎，依赖 Phase 1
Phase 3 (Task 8-10) → CLI，依赖 Phase 1-2
Phase 4 (Task 11-12)→ API 后端，依赖 Phase 1-2
Phase 5 (Task 13-17)→ Web UI，依赖 Phase 4
Phase 6 (Task 18-20)→ 集成，依赖全部
```

Phase 1-3 是后端核心，可以先做完再开始前端。Phase 4 和 Phase 5 可以部分并行（API 骨架 + 前端骨架同时搭）。
