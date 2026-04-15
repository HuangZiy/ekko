# AI 驱动 Issue 拆分 + CLI 增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 CLI 从 `harness` 更名为 `ekko`，增强 issue create 支持 plan/parent_id/blocked_by/source，新增 init/board/stats 命令，新增批量创建 API 端点，使 AI 驱动的 issue 拆分流程可以落地。

**Architecture:** 改动集中在 4 层：pyproject.toml 入口更名 → CLI argparse 增强（cli/main.py）→ API model 扩展（server/routes/issues.py）→ 新增批量端点。所有改动向后兼容，不影响现有 issue 数据。

**Tech Stack:** Python 3.11+, argparse, FastAPI/Pydantic, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `pyproject.toml` | 更名 entry point `harness` → `ekko` |
| Modify | `cli/main.py` | 更名 prog、帮助文本；新增 `--parent-id/--blocked-by/--description/--plan/--source` 参数；新增 `init/board/stats` 子命令 |
| Modify | `harness.py` | 更名日志/函数中的 harness 引用 |
| Modify | `server/routes/issues.py` | `CreateIssueRequest` 新增 `plan`、`source` 字段；新增 `POST /batch` 端点 |
| Modify | `tests/test_cli_issue.py` | 新增 issue create 增强参数测试 |
| Create | `tests/test_cli_init.py` | `ekko init` 命令测试 |
| Create | `tests/test_cli_board.py` | `ekko board` 命令测试 |
| Create | `tests/test_cli_stats.py` | `ekko stats` 命令测试 |
| Create | `tests/test_api_batch.py` | 批量创建 API 端点测试 |

---

### Task 1: CLI 更名 `harness` → `ekko`

**Files:**
- Modify: `pyproject.toml:18`
- Modify: `cli/main.py:25,49,646`
- Modify: `harness.py:1,259,378,420,421,510,518`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 更新 pyproject.toml entry point**

```toml
[project.scripts]
ekko = "cli.main:main"
```

- [ ] **Step 2: 更新 cli/main.py 中所有 harness 引用**

`build_parser()` 中：
```python
parser = argparse.ArgumentParser(
    prog="ekko",
    description="Ekko — AI-driven development with kanban issue management",
)
```

`_get_storage()` 中的错误提示：
```python
print("No active project. Create one with: ekko project create \"name\" /path/to/workspace", file=sys.stderr)
```

`_project_list()` 中的提示：
```python
print("No projects. Create one with: ekko project create \"name\" /path/to/workspace")
```

- [ ] **Step 3: 更新 harness.py 中的引用**

函数名 `run_harness` → `run_ekko`，日志文本中的 "Harness" → "Ekko"：

```python
# Line 259
lines.append(f"{C_BOLD}  Ekko Summary{C_RESET}")

# Line 378
async def run_ekko(user_prompt: str) -> None:

# Line 420
_log_file = open(task_dir / "ekko.log", "a", encoding="utf-8")

# Line 421
_log_file.write(f"\n{'='*60}\nEkko started: {datetime.now().isoformat()}\nPrompt: {user_prompt}\nTask: {task_id}\n{'='*60}\n")

# Line 510
_tee(f"\n{C_GREEN}Ekko complete. Task: {task_id}{C_RESET}")

# Line 526 (main block)
anyio.run(run_ekko, prompt)
```

docstring (line 1):
```python
"""Ekko — Unified loop orchestrator with task isolation and resume.
```

- [ ] **Step 4: 运行现有测试确认不破坏**

Run: `pytest tests/test_cli.py tests/test_cli_issue.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml cli/main.py harness.py
git commit -m "refactor: rename CLI entry point from harness to ekko"
```

---

### Task 2: 增强 `ekko issue create` 参数

**Files:**
- Modify: `cli/main.py:147-177` (`_issue_create` 函数)
- Modify: `cli/main.py:689-694` (argparse setup)
- Test: `tests/test_cli_issue.py`

- [ ] **Step 1: 写失败测试 — issue create 带 parent-id 和 blocked-by**

在 `tests/test_cli_issue.py` 的 `TestIssueCreate` 类中新增：

```python
def test_with_parent_id(self, cli):
    # Create parent first
    code, out = cli("issue", "create", "Parent issue")
    parent_id = out.out.strip().split()[1].rstrip(":")

    code, out = cli("issue", "create", "Child issue", "--parent-id", parent_id)
    assert code == 0
    child_id = out.out.strip().split()[1].rstrip(":")

    code, out = cli("issue", "show", child_id)
    assert parent_id in out.out

def test_with_blocked_by(self, cli):
    code, out = cli("issue", "create", "Blocker")
    blocker_id = out.out.strip().split()[1].rstrip(":")

    code, out = cli("issue", "create", "Blocked", "--blocked-by", blocker_id)
    assert code == 0
    child_id = out.out.strip().split()[1].rstrip(":")

    code, out = cli("issue", "show", child_id)
    assert blocker_id in out.out
    assert "BLOCKED" in out.out or blocker_id in out.out

def test_with_description(self, cli):
    code, out = cli("issue", "create", "With desc", "--description", "Detailed description here")
    assert code == 0
    issue_id = out.out.strip().split()[1].rstrip(":")

    code, out = cli("issue", "show", issue_id)
    assert "Detailed description here" in out.out

def test_with_plan(self, cli):
    code, out = cli("issue", "create", "With plan", "--plan", "- [ ] Step 1\n- [ ] Step 2")
    assert code == 0
    issue_id = out.out.strip().split()[1].rstrip(":")

    # Verify plan was saved by checking the plan file directly
    from core.storage import ProjectStorage
    store = ProjectStorage(cli.project_dir)
    plan = store.load_issue_plan(issue_id)
    assert "Step 1" in plan

def test_with_source(self, cli):
    code, out = cli("issue", "create", "Agent created", "--source", "agent")
    assert code == 0
    issue_id = out.out.strip().split()[1].rstrip(":")

    from core.storage import ProjectStorage
    store = ProjectStorage(cli.project_dir)
    issue = store.load_issue(issue_id)
    assert issue.source == "agent"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_cli_issue.py::TestIssueCreate::test_with_parent_id -v`
Expected: FAIL (argparse 不认识 `--parent-id`)

- [ ] **Step 3: 新增 argparse 参数**

在 `cli/main.py` 的 `build_parser()` 中，`issue create` 子命令部分新增：

```python
# issue create
p = issue_sub.add_parser("create", help="Create a new issue")
p.add_argument("title", help="Issue title")
p.add_argument("--label", action="append", help="Add label (repeatable)")
p.add_argument("--priority", default="medium", choices=["low", "medium", "high", "urgent"])
p.add_argument("--parent-id", default=None, help="Parent issue ID")
p.add_argument("--blocked-by", action="append", help="Blocker issue ID (repeatable)")
p.add_argument("--description", default="", help="Issue description (saved as content.md)")
p.add_argument("--plan", default="", help="Execution plan (saved as plan.md)")
p.add_argument("--source", default="human", choices=["human", "agent"], help="Issue source")
p.set_defaults(func=_issue_create)
```

- [ ] **Step 4: 更新 `_issue_create` 函数**

```python
def _issue_create(args: argparse.Namespace) -> None:
    from core.models import Issue
    import json
    store = _get_storage(args)

    project = store.load_project_meta()
    if project is None:
        print("Error: project metadata not found in storage directory.", file=sys.stderr)
        sys.exit(1)
    issue_id = store.next_issue_id(project.key)

    issue = Issue.create(
        id=issue_id,
        title=args.title,
        priority=args.priority,
        labels=args.label or [],
    )

    # Set optional fields
    if args.parent_id:
        issue.parent_id = args.parent_id
    if args.source:
        issue.source = args.source
    if args.blocked_by:
        for blocker_id in args.blocked_by:
            issue.add_blocker(blocker_id)

    store.save_issue(issue)

    # Save description as content.md
    if args.description:
        content = f"# {issue.id}: {issue.title}\n\n## 描述\n\n{args.description}\n"
        store.save_issue_content(issue.id, content)

    # Save plan as plan.md
    if args.plan:
        store.save_issue_plan(issue.id, args.plan)

    # Add to board backlog
    board_file = store.root / "board.json"
    if board_file.exists():
        data = json.loads(board_file.read_text())
        for col in data["columns"]:
            if col["id"] == "backlog":
                col["issues"].append(issue.id)
                break
        board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    print(f"Created {issue.id}: {issue.title}")
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_cli_issue.py::TestIssueCreate -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add cli/main.py tests/test_cli_issue.py
git commit -m "feat: enhance issue create with parent-id, blocked-by, description, plan, source"
```

---

### Task 3: API `CreateIssueRequest` 新增 `plan` 和 `source` 字段

**Files:**
- Modify: `server/routes/issues.py:21-28` (CreateIssueRequest)
- Modify: `server/routes/issues.py:48-72` (create_issue endpoint)
- Test: `tests/test_api_batch.py` (新建，先测单个创建增强)

- [ ] **Step 1: 写失败测试**

创建 `tests/test_api_batch.py`：

```python
"""Tests for enhanced issue creation API."""
import pytest
from fastapi.testclient import TestClient
from core.models import Project
from core.storage import ProjectStorage


@pytest.fixture
def app(tmp_path):
    """Create a FastAPI test app with a tmp project."""
    from server.app import create_app
    harness_root = tmp_path / "harness"
    harness_root.mkdir()

    app = create_app(harness_root=harness_root)

    # Create a project
    from core.storage import PlatformStorage
    platform = PlatformStorage(harness_root)
    project, store = platform.create_project(
        name="test", workspace_path=str(tmp_path), key="TST"
    )

    return app, project.id, store


@pytest.fixture
def client(app):
    app_instance, project_id, store = app
    return TestClient(app_instance), project_id, store


class TestCreateIssueWithPlan:
    def test_create_with_plan(self, client):
        c, pid, store = client
        resp = c.post(f"/api/projects/{pid}/issues", json={
            "title": "Test issue",
            "plan": "- [ ] Step 1\n- [ ] Step 2",
        })
        assert resp.status_code == 200
        issue_id = resp.json()["id"]

        plan = store.load_issue_plan(issue_id)
        assert "Step 1" in plan
        assert "Step 2" in plan

    def test_create_with_source_agent(self, client):
        c, pid, store = client
        resp = c.post(f"/api/projects/{pid}/issues", json={
            "title": "Agent issue",
            "source": "agent",
        })
        assert resp.status_code == 200
        issue_id = resp.json()["id"]

        issue = store.load_issue(issue_id)
        assert issue.source == "agent"

    def test_create_without_plan_no_plan_file(self, client):
        c, pid, store = client
        resp = c.post(f"/api/projects/{pid}/issues", json={
            "title": "No plan issue",
        })
        assert resp.status_code == 200
        issue_id = resp.json()["id"]

        plan = store.load_issue_plan(issue_id)
        assert plan is None or plan == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api_batch.py::TestCreateIssueWithPlan::test_create_with_plan -v`
Expected: FAIL (CreateIssueRequest 没有 `plan` 字段，请求中的 `plan` 被忽略)

- [ ] **Step 3: 更新 CreateIssueRequest**

在 `server/routes/issues.py` 中：

```python
class CreateIssueRequest(BaseModel):
    title: str
    priority: str = "medium"
    labels: list[str] = []
    description: str = ""
    blocked_by: list[str] = []
    workspace: str = "default"
    parent_id: str | None = None
    plan: str = ""          # 新增
    source: str = "human"   # 新增
```

- [ ] **Step 4: 更新 create_issue 端点逻辑**

```python
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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_api_batch.py::TestCreateIssueWithPlan -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add server/routes/issues.py tests/test_api_batch.py
git commit -m "feat: add plan and source fields to CreateIssueRequest"
```

---

### Task 4: 批量创建子 issue API 端点

**Files:**
- Modify: `server/routes/issues.py` (新增 BatchCreateRequest model + batch endpoint)
- Test: `tests/test_api_batch.py` (新增 TestBatchCreate 类)

- [ ] **Step 1: 写失败测试**

在 `tests/test_api_batch.py` 中新增：

```python
class TestBatchCreate:
    def test_batch_create_with_chain(self, client):
        c, pid, store = client
        # Create parent issue first
        resp = c.post(f"/api/projects/{pid}/issues", json={"title": "Parent"})
        parent_id = resp.json()["id"]

        resp = c.post(f"/api/projects/{pid}/issues/batch", json={
            "parent_id": parent_id,
            "issues": [
                {"title": "Child 1", "description": "First task", "plan": "- [ ] Do A"},
                {"title": "Child 2", "description": "Second task", "plan": "- [ ] Do B"},
                {"title": "Child 3", "description": "Third task"},
            ],
            "chain_dependencies": True,
        })
        assert resp.status_code == 200
        children = resp.json()["created"]
        assert len(children) == 3

        # Verify serial chain: child 2 blocked by child 1, child 3 blocked by child 2
        child1 = store.load_issue(children[0]["id"])
        child2 = store.load_issue(children[1]["id"])
        child3 = store.load_issue(children[2]["id"])

        assert child1.blocked_by == []
        assert children[0]["id"] in child2.blocked_by
        assert children[1]["id"] in child3.blocked_by

        # All children have parent_id set
        assert child1.parent_id == parent_id
        assert child2.parent_id == parent_id
        assert child3.parent_id == parent_id

        # All children are source=agent
        assert child1.source == "agent"

        # Parent is blocked by all children
        parent = store.load_issue(parent_id)
        for ch in children:
            assert ch["id"] in parent.blocked_by

        # Plans saved
        assert "Do A" in store.load_issue_plan(children[0]["id"])
        assert "Do B" in store.load_issue_plan(children[1]["id"])

    def test_batch_create_no_chain(self, client):
        c, pid, store = client
        resp = c.post(f"/api/projects/{pid}/issues", json={"title": "Parent2"})
        parent_id = resp.json()["id"]

        resp = c.post(f"/api/projects/{pid}/issues/batch", json={
            "parent_id": parent_id,
            "issues": [
                {"title": "Independent 1"},
                {"title": "Independent 2"},
            ],
            "chain_dependencies": False,
        })
        assert resp.status_code == 200
        children = resp.json()["created"]

        child1 = store.load_issue(children[0]["id"])
        child2 = store.load_issue(children[1]["id"])
        assert child1.blocked_by == []
        assert child2.blocked_by == []

    def test_batch_create_parent_not_found(self, client):
        c, pid, store = client
        resp = c.post(f"/api/projects/{pid}/issues/batch", json={
            "parent_id": "NONEXISTENT-99",
            "issues": [{"title": "Orphan"}],
        })
        assert resp.status_code == 404
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api_batch.py::TestBatchCreate::test_batch_create_with_chain -v`
Expected: FAIL (404, endpoint 不存在)

- [ ] **Step 3: 新增 Pydantic models**

在 `server/routes/issues.py` 中新增：

```python
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
```

- [ ] **Step 4: 实现批量创建端点**

在 `server/routes/issues.py` 中新增：

```python
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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_api_batch.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add server/routes/issues.py tests/test_api_batch.py
git commit -m "feat: add batch create endpoint for child issues"
```

---

### Task 5: `ekko init` 命令

**Files:**
- Modify: `cli/main.py` (新增 `_init` 函数 + argparse setup)
- Modify: `harness.py:518` (新增 "init" 到 `_CLI_SUBCOMMANDS`)
- Create: `tests/test_cli_init.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_cli_init.py`：

```python
"""Tests for ekko init command."""
import json
import os
import pytest
from cli.main import main


@pytest.fixture
def workspace(tmp_path, capsys, monkeypatch):
    """Provide a tmp workspace dir and a CLI runner."""
    work_dir = tmp_path / "my-project"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)

    # Point ARTIFACTS_DIR to tmp so we don't pollute real storage
    monkeypatch.setattr("config.ARTIFACTS_DIR", tmp_path / "artifacts")

    def run(*args: str):
        try:
            main(list(args))
        except SystemExit as e:
            return e.code, capsys.readouterr()
        return 0, capsys.readouterr()

    run.work_dir = work_dir
    return run


class TestInit:
    def test_init_creates_harness_dir(self, workspace):
        code, out = workspace("init", "--name", "test-project", "--key", "TST")
        assert code == 0
        assert (workspace.work_dir / ".harness").is_dir()
        assert (workspace.work_dir / ".harness" / "project.json").exists()

    def test_init_sets_project_name_and_key(self, workspace):
        workspace("init", "--name", "my-app", "--key", "APP")
        project_file = workspace.work_dir / ".harness" / "project.json"
        data = json.loads(project_file.read_text())
        assert data["name"] == "my-app"
        assert data["key"] == "APP"

    def test_init_registers_workspace(self, workspace):
        workspace("init", "--name", "ws-test", "--key", "WS")
        project_file = workspace.work_dir / ".harness" / "project.json"
        data = json.loads(project_file.read_text())
        assert str(workspace.work_dir) in data["workspaces"]

    def test_init_creates_board(self, workspace):
        workspace("init", "--name", "board-test", "--key", "BRD")
        board_file = workspace.work_dir / ".harness" / "board.json"
        assert board_file.exists()
        data = json.loads(board_file.read_text())
        col_ids = [c["id"] for c in data["columns"]]
        assert "backlog" in col_ids
        assert "todo" in col_ids

    def test_init_already_initialized(self, workspace):
        workspace("init", "--name", "first", "--key", "F")
        code, out = workspace("init", "--name", "second", "--key", "S")
        assert code != 0
        assert "already initialized" in out.err.lower()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_cli_init.py::TestInit::test_init_creates_harness_dir -v`
Expected: FAIL (argparse 不认识 `init` 子命令)

- [ ] **Step 3: 实现 `_init` 函数**

在 `cli/main.py` 中新增：

```python
def _init(args: argparse.Namespace) -> None:
    """Initialize a new Ekko project in the current directory."""
    import json
    from core.models import Project, Board
    from core.storage import ProjectStorage

    cwd = Path.cwd()
    harness_dir = cwd / ".harness"

    if harness_dir.exists():
        print("Error: project already initialized in this directory.", file=sys.stderr)
        sys.exit(1)

    # Interactive prompts if name/key not provided
    name = args.name
    if not name:
        name = input("Project name: ").strip()
        if not name:
            print("Error: project name is required.", file=sys.stderr)
            sys.exit(1)

    key = args.key
    if not key:
        default_key = name[:3].upper()
        key = input(f"Issue prefix [{default_key}]: ").strip().upper() or default_key

    # Create .harness structure
    store = ProjectStorage(harness_dir)
    project = Project.create(
        id=f"prj-{name.lower().replace(' ', '-')}",
        name=name,
        workspace_path=str(cwd),
        key=key.upper(),
    )
    store.save_project_meta(project)

    # Create board.json
    board = Board.create()
    board_data = {"columns": [{"id": c.id, "name": c.name, "issues": c.issues} for c in board.columns]}
    (harness_dir / "board.json").write_text(json.dumps(board_data, indent=2, ensure_ascii=False))

    # Create issues dir
    (harness_dir / "issues").mkdir(exist_ok=True)

    # Register to platform
    platform = _get_platform()
    registry_file = platform.root / "registry.json"
    registry = {}
    if registry_file.exists():
        registry = json.loads(registry_file.read_text())
    registry[project.id] = str(harness_dir)
    platform.root.mkdir(parents=True, exist_ok=True)
    registry_file.write_text(json.dumps(registry, indent=2, ensure_ascii=False))

    print(f"Initialized project '{name}' (prefix: {key})")
    print(f"  Storage: {harness_dir}")
```

- [ ] **Step 4: 注册 argparse 子命令**

在 `cli/main.py` 的 `build_parser()` 中，在 `project_parser` 之前新增：

```python
# -- init --
init_parser = sub.add_parser("init", help="Initialize Ekko project in current directory")
init_parser.add_argument("--name", default=None, help="Project name (interactive if omitted)")
init_parser.add_argument("--key", default=None, help="Issue ID prefix, e.g. EKO (interactive if omitted)")
init_parser.set_defaults(func=_init)
```

- [ ] **Step 5: 更新 harness.py 的 _CLI_SUBCOMMANDS**

```python
_CLI_SUBCOMMANDS = {"init", "issue", "review", "project", "board", "plan", "plan-issue", "run", "serve"}
```

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/test_cli_init.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add cli/main.py harness.py tests/test_cli_init.py
git commit -m "feat: add ekko init command for project initialization"
```

---

### Task 6: `ekko board` 命令

**Files:**
- Modify: `cli/main.py` (新增 `_board_show` 和 `_board_move` 函数 + argparse setup)
- Create: `tests/test_cli_board.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_cli_board.py`：

```python
"""Tests for ekko board command."""
import json
import pytest
from cli.main import main
from core.models import Project, Board
from core.storage import ProjectStorage


@pytest.fixture
def cli(tmp_path, capsys):
    """CLI runner with a project that has a board and some issues."""
    project_dir = tmp_path / "project"
    store = ProjectStorage(project_dir)
    project = Project.create(id="PRJ-1", name="test", workspace_path=str(tmp_path))
    store.save_project_meta(project)

    # Create board
    board = Board.create()
    board_data = {"columns": [{"id": c.id, "name": c.name, "issues": c.issues} for c in board.columns]}
    (project_dir / "board.json").write_text(json.dumps(board_data, indent=2, ensure_ascii=False))

    project_dir_str = str(project_dir)

    def run(*args: str):
        try:
            main(["--project", project_dir_str, *args])
        except SystemExit as e:
            return e.code, capsys.readouterr()
        return 0, capsys.readouterr()

    run.project_dir = project_dir_str
    return run


class TestBoardShow:
    def test_empty_board(self, cli):
        code, out = cli("board")
        assert code == 0
        assert "backlog" in out.out.lower()

    def test_board_shows_issues(self, cli):
        cli("issue", "create", "Task A")
        cli("issue", "create", "Task B")
        code, out = cli("board")
        assert code == 0
        assert "Task A" in out.out
        assert "Task B" in out.out
        assert "backlog" in out.out.lower()

    def test_board_groups_by_column(self, cli):
        # Create issue and move to todo
        code, out = cli("issue", "create", "In todo")
        issue_id = out.out.strip().split()[1].rstrip(":")
        cli("issue", "move", issue_id, "todo")

        cli("issue", "create", "In backlog")

        code, out = cli("board")
        assert code == 0
        # Both columns should appear
        assert "backlog" in out.out.lower()
        assert "todo" in out.out.lower()


class TestBoardMove:
    def test_move_issue(self, cli):
        code, out = cli("issue", "create", "Move me")
        issue_id = out.out.strip().split()[1].rstrip(":")

        code, out = cli("board", "move", issue_id, "todo")
        assert code == 0
        assert "todo" in out.out.lower()

    def test_move_not_found(self, cli):
        code, out = cli("board", "move", "ISS-nope", "todo")
        assert code == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_cli_board.py::TestBoardShow::test_empty_board -v`
Expected: FAIL (argparse 不认识 `board` 子命令，或没有 `_board_show` 函数)

- [ ] **Step 3: 实现 `_board_show` 函数**

在 `cli/main.py` 中新增：

```python
def _board_show(args: argparse.Namespace) -> None:
    """Show kanban board overview grouped by column."""
    import json
    store = _get_storage(args)
    board_file = store.root / "board.json"

    if not board_file.exists():
        print("No board found. Create issues first.")
        return

    data = json.loads(board_file.read_text())
    issues_map = {}
    for issue in store.list_issues():
        issues_map[issue.id] = issue

    for col in data["columns"]:
        issue_ids = col["issues"]
        if not issue_ids:
            continue
        print(f"\n{col['name']} ({len(issue_ids)})")
        for iid in issue_ids:
            issue = issues_map.get(iid)
            if issue:
                blocked = " [BLOCKED]" if issue.is_blocked() else ""
                print(f"  {issue.id}  [{issue.priority.value:<6}]  {issue.title}{blocked}")
            else:
                print(f"  {iid}  (not found)")
    print()
```

- [ ] **Step 4: 实现 `_board_move` 函数**

```python
def _board_move(args: argparse.Namespace) -> None:
    """Move an issue to a different board column."""
    import json
    from core.models import IssueStatus
    store = _get_storage(args)

    try:
        issue = store.load_issue(args.issue_id)
    except FileNotFoundError:
        print(f"Issue not found: {args.issue_id}", file=sys.stderr)
        sys.exit(1)

    # Update issue status to match target column
    status_map = {
        "backlog": IssueStatus.BACKLOG,
        "planning": IssueStatus.PLANNING,
        "todo": IssueStatus.TODO,
        "in_progress": IssueStatus.IN_PROGRESS,
        "agent_done": IssueStatus.AGENT_DONE,
        "rejected": IssueStatus.REJECTED,
        "human_done": IssueStatus.HUMAN_DONE,
    }
    new_status = status_map.get(args.column)
    if not new_status:
        print(f"Invalid column: {args.column}", file=sys.stderr)
        sys.exit(1)

    old = issue.status.value
    try:
        issue.move_to(new_status)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    store.save_issue(issue)

    # Update board.json
    board_file = store.root / "board.json"
    if board_file.exists():
        data = json.loads(board_file.read_text())
        for col in data["columns"]:
            if args.issue_id in col["issues"]:
                col["issues"].remove(args.issue_id)
        for col in data["columns"]:
            if col["id"] == args.column:
                col["issues"].append(args.issue_id)
                break
        board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    print(f"Moved {args.issue_id}: {old} -> {args.column}")
```

- [ ] **Step 5: 注册 argparse 子命令**

在 `cli/main.py` 的 `build_parser()` 中新增：

```python
# -- board --
board_parser = sub.add_parser("board", help="Kanban board overview")
board_sub = board_parser.add_subparsers(dest="board_command")

board_parser.set_defaults(func=_board_show)  # `ekko board` with no subcommand shows board

p = board_sub.add_parser("move", help="Move issue to a board column")
p.add_argument("issue_id", help="Issue ID")
p.add_argument("column", help="Target column (backlog, planning, todo, in_progress, ...)")
p.set_defaults(func=_board_move)
```

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/test_cli_board.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add cli/main.py tests/test_cli_board.py
git commit -m "feat: add ekko board command for kanban overview and move"
```

---

### Task 7: `ekko stats` 命令

**Files:**
- Modify: `cli/main.py` (新增 `_stats` 函数 + argparse setup)
- Create: `tests/test_cli_stats.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_cli_stats.py`：

```python
"""Tests for ekko stats command."""
import json
import pytest
from cli.main import main
from core.models import Project
from core.storage import ProjectStorage


@pytest.fixture
def cli(tmp_path, capsys):
    project_dir = tmp_path / "project"
    store = ProjectStorage(project_dir)
    project = Project.create(id="PRJ-1", name="test", workspace_path=str(tmp_path))
    store.save_project_meta(project)
    project_dir_str = str(project_dir)

    def run(*args: str):
        try:
            main(["--project", project_dir_str, *args])
        except SystemExit as e:
            return e.code, capsys.readouterr()
        return 0, capsys.readouterr()

    run.project_dir = project_dir_str
    run.store = store
    return run


class TestStats:
    def test_stats_no_runs(self, cli):
        code, out = cli("issue", "create", "No runs yet")
        issue_id = out.out.strip().split()[1].rstrip(":")
        code, out = cli("stats", issue_id)
        assert code == 0
        assert "0 runs" in out.out.lower() or "no runs" in out.out.lower()

    def test_stats_with_run_data(self, cli):
        code, out = cli("issue", "create", "Has stats")
        issue_id = out.out.strip().split()[1].rstrip(":")

        # Write fake stats
        stats_dir = cli.store.issues_dir / issue_id / "stats"
        stats_dir.mkdir(parents=True)
        (stats_dir / "run-001.json").write_text(json.dumps({
            "success": True,
            "cost_usd": 0.42,
            "duration_ms": 15000,
            "attempts": 2,
            "details": [{"num_turns": 5, "usage": {"input_tokens": 1000, "output_tokens": 500}}],
        }))

        code, out = cli("stats", issue_id)
        assert code == 0
        assert "$0.42" in out.out or "0.42" in out.out

    def test_stats_project_summary(self, cli):
        cli("issue", "create", "Issue A")
        cli("issue", "create", "Issue B")
        code, out = cli("stats")
        assert code == 0
        assert "2" in out.out  # 2 issues

    def test_stats_not_found(self, cli):
        code, out = cli("stats", "ISS-nope")
        assert code == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_cli_stats.py::TestStats::test_stats_no_runs -v`
Expected: FAIL (argparse 不认识 `stats` 子命令)

- [ ] **Step 3: 实现 `_stats` 函数**

在 `cli/main.py` 中新增：

```python
def _stats(args: argparse.Namespace) -> None:
    """Show cost/duration/turns statistics."""
    store = _get_storage(args)
    issue_id = getattr(args, "issue_id", None)

    if issue_id:
        # Single issue stats
        try:
            issue = store.load_issue(issue_id)
        except FileNotFoundError:
            print(f"Issue not found: {issue_id}", file=sys.stderr)
            sys.exit(1)

        runs = store.list_all_run_stats(issue_id)
        if not runs:
            print(f"{issue_id}: {issue.title}")
            print(f"  0 runs")
            return

        total_cost = sum(r.get("cost_usd", 0) for r in runs)
        total_duration = sum(r.get("duration_ms", 0) for r in runs)
        total_attempts = sum(r.get("attempts", 0) for r in runs)

        print(f"{issue_id}: {issue.title}")
        print(f"  Runs:     {len(runs)}")
        print(f"  Cost:     ${total_cost:.2f}")
        print(f"  Duration: {total_duration // 1000}s")
        print(f"  Attempts: {total_attempts}")

        for i, r in enumerate(runs):
            status = "PASS" if r.get("success") else "FAIL"
            cost = r.get("cost_usd", 0)
            dur = r.get("duration_ms", 0) // 1000
            print(f"    run-{i+1:03d}: {status}  ${cost:.2f}  {dur}s")
    else:
        # Project summary
        issues = store.list_issues()
        total_cost = 0.0
        total_runs = 0
        by_status = {}

        for issue in issues:
            by_status.setdefault(issue.status.value, []).append(issue)
            runs = store.list_all_run_stats(issue.id)
            total_runs += len(runs)
            total_cost += sum(r.get("cost_usd", 0) for r in runs)

        print(f"Project: {len(issues)} issues, {total_runs} runs, ${total_cost:.2f} total cost")
        for status, items in sorted(by_status.items()):
            print(f"  {status:<15} {len(items)}")
```

- [ ] **Step 4: 注册 argparse 子命令**

在 `cli/main.py` 的 `build_parser()` 中新增：

```python
# -- stats --
stats_parser = sub.add_parser("stats", help="Show cost/duration statistics")
stats_parser.add_argument("issue_id", nargs="?", default=None, help="Issue ID (omit for project summary)")
stats_parser.set_defaults(func=_stats)
```

- [ ] **Step 5: 更新 harness.py 的 _CLI_SUBCOMMANDS**

```python
_CLI_SUBCOMMANDS = {"init", "issue", "review", "project", "board", "plan", "plan-issue", "run", "serve", "stats"}
```

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/test_cli_stats.py -v`
Expected: ALL PASS

- [ ] **Step 7: 运行全部测试确认无回归**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add cli/main.py harness.py tests/test_cli_stats.py
git commit -m "feat: add ekko stats command for cost and duration statistics"
```
