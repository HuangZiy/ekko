# JIRA-Style Auto-Increment IDs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hash-based Issue and Project IDs with JIRA-style auto-incrementing numeric IDs (e.g. ISS-1, ISS-2, PRJ-1, BLOG-1).

**Architecture:** A `counter.json` file per project directory tracks per-prefix counters. `PlatformStorage` manages a global counter for project IDs. `Issue.create()` and `Project.create()` no longer generate IDs internally — callers pass the next ID from the counter. The `Project` model gains an optional `key` field (the prefix, e.g. "BLOG") used for issue IDs within that project.

**Tech Stack:** Python 3.11+, stdlib only (json, pathlib). No new dependencies.

---

## File Map

| File | Change |
|------|--------|
| `core/models.py` | Add `key` field to `Project`; change `Issue.create()` and `Project.create()` to accept an explicit `id` parameter |
| `core/storage.py` | Add `_next_id()` helper to `ProjectStorage` (issue counter) and `PlatformStorage` (project counter); update `create_project` to pass ID; update `save_issue` callers |
| `cli/main.py` | Pass next issue ID when calling `Issue.create()` |
| `tests/test_models.py` | Update tests to pass explicit IDs |
| `tests/test_storage.py` | Add counter tests |
| `tests/test_cli_issue.py` | Update expected ID format |

---

### Task 1: Add `key` to `Project` model and make IDs explicit

**Files:**
- Modify: `core/models.py`

- [ ] **Step 1: Write the failing tests**

```python
# In tests/test_models.py — add these tests

def test_issue_create_with_explicit_id():
    issue = Issue.create(id="ISS-1", title="Fix login")
    assert issue.id == "ISS-1"

def test_project_create_with_key():
    project = Project.create(id="PRJ-1", name="Blog", workspace_path="/tmp/ws", key="BLOG")
    assert project.id == "PRJ-1"
    assert project.key == "BLOG"

def test_project_create_default_key():
    project = Project.create(id="PRJ-2", name="My Project", workspace_path="/tmp/ws")
    assert project.key == "ISS"  # default prefix
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/cn-edisonhuang01/MyWorks/ekko
python -m pytest tests/test_models.py::test_issue_create_with_explicit_id tests/test_models.py::test_project_create_with_key tests/test_models.py::test_project_create_default_key -v
```

Expected: FAIL — `Issue.create()` doesn't accept `id`, `Project` has no `key` field.

- [ ] **Step 3: Update `core/models.py`**

Replace the `Issue.create()` classmethod (lines 58-68):

```python
@classmethod
def create(cls, id: str, title: str, priority: str = "medium", labels: list[str] | None = None) -> Issue:
    now = datetime.now(timezone.utc).isoformat()
    return cls(
        id=id, title=title,
        priority=IssuePriority(priority),
        labels=labels or [],
        created_at=now, updated_at=now,
    )
```

Add `key: str = "ISS"` field to `Project` dataclass (after `created_at`):

```python
@dataclass
class Project:
    id: str
    name: str
    workspaces: list[str] = field(default_factory=list)
    created_at: str = ""
    key: str = "ISS"
```

Replace `Project.create()` classmethod (lines 155-163):

```python
@classmethod
def create(cls, id: str, name: str, workspace_path: str, key: str = "ISS") -> Project:
    now = datetime.now(timezone.utc).isoformat()
    return cls(
        id=id,
        name=name,
        workspaces=[workspace_path],
        created_at=now,
        key=key,
    )
```

Also remove the `import hashlib` and `import time` lines at the top since they're no longer needed.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_models.py::test_issue_create_with_explicit_id tests/test_models.py::test_project_create_with_key tests/test_models.py::test_project_create_default_key -v
```

Expected: PASS

- [ ] **Step 5: Fix existing model tests that use old `Issue.create()` / `Project.create()` signatures**

In `tests/test_models.py`, update all existing calls:

```python
def test_create_issue():
    issue = Issue.create(id="ISS-1", title="实现登录页", priority="high", labels=["auth"])
    assert issue.id == "ISS-1"
    assert issue.status == IssueStatus.BACKLOG
    assert issue.priority == IssuePriority.HIGH
    assert issue.blocks == []
    assert issue.blocked_by == []

def test_issue_status_transition():
    issue = Issue.create(id="ISS-1", title="test")
    issue.move_to(IssueStatus.TODO)
    assert issue.status == IssueStatus.TODO
    issue.move_to(IssueStatus.IN_PROGRESS)
    assert issue.status == IssueStatus.IN_PROGRESS

def test_issue_invalid_transition():
    issue = Issue.create(id="ISS-1", title="test")
    with pytest.raises(ValueError):
        issue.move_to(IssueStatus.HUMAN_DONE)

def test_issue_dependency():
    a = Issue.create(id="ISS-1", title="A")
    b = Issue.create(id="ISS-2", title="B")
    b.add_blocker(a.id)
    assert a.id in b.blocked_by
    assert b.is_blocked()

def test_issue_serialization():
    issue = Issue.create(id="ISS-1", title="test", labels=["bug"])
    data = issue.to_json()
    loaded = Issue.from_json(data)
    assert loaded.id == issue.id
    assert loaded.title == issue.title

def test_create_project():
    project = Project.create(id="PRJ-1", name="技术博客", workspace_path="/tmp/workspace")
    assert project.id == "PRJ-1"
    assert project.name == "技术博客"
    assert len(project.workspaces) == 1
```

- [ ] **Step 6: Run all model tests**

```bash
python -m pytest tests/test_models.py -v
```

Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add core/models.py tests/test_models.py
git commit -m "feat: make Issue/Project IDs explicit, add Project.key prefix field"
```

---

### Task 2: Add counter logic to `ProjectStorage` and `PlatformStorage`

**Files:**
- Modify: `core/storage.py`
- Modify: `tests/test_storage.py`

The counter is stored in `counter.json` at the root of each project directory (for issues) and at the harness root (for projects). Format: `{"ISS": 3, "BLOG": 7}` — a dict of prefix → last used number.

- [ ] **Step 1: Write failing tests for the counter**

Add to `tests/test_storage.py`:

```python
import tempfile
from pathlib import Path
from core.storage import ProjectStorage, PlatformStorage
from core.models import Issue, Project


def test_project_storage_next_issue_id(tmp_path):
    store = ProjectStorage(tmp_path)
    assert store.next_issue_id("ISS") == "ISS-1"
    assert store.next_issue_id("ISS") == "ISS-2"
    assert store.next_issue_id("BLOG") == "BLOG-1"
    assert store.next_issue_id("ISS") == "ISS-3"


def test_platform_storage_next_project_id(tmp_path):
    platform = PlatformStorage(tmp_path)
    assert platform.next_project_id() == "PRJ-1"
    assert platform.next_project_id() == "PRJ-2"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_storage.py::test_project_storage_next_issue_id tests/test_storage.py::test_platform_storage_next_project_id -v
```

Expected: FAIL — `next_issue_id` and `next_project_id` don't exist.

- [ ] **Step 3: Add `next_issue_id()` to `ProjectStorage`**

Add this method to the `ProjectStorage` class in `core/storage.py` (after `__init__`):

```python
def next_issue_id(self, prefix: str = "ISS") -> str:
    counter_file = self.root / "counter.json"
    counters: dict[str, int] = {}
    if counter_file.exists():
        counters = json.loads(counter_file.read_text())
    n = counters.get(prefix, 0) + 1
    counters[prefix] = n
    self.root.mkdir(parents=True, exist_ok=True)
    counter_file.write_text(json.dumps(counters))
    return f"{prefix}-{n}"
```

- [ ] **Step 4: Add `next_project_id()` to `PlatformStorage`**

Add this method to the `PlatformStorage` class in `core/storage.py` (after `__init__`):

```python
def next_project_id(self) -> str:
    counter_file = self.root / "counter.json"
    counters: dict[str, int] = {}
    if counter_file.exists():
        counters = json.loads(counter_file.read_text())
    n = counters.get("PRJ", 0) + 1
    counters["PRJ"] = n
    self.root.mkdir(parents=True, exist_ok=True)
    counter_file.write_text(json.dumps(counters))
    return f"PRJ-{n}"
```

- [ ] **Step 5: Run counter tests**

```bash
python -m pytest tests/test_storage.py::test_project_storage_next_issue_id tests/test_storage.py::test_platform_storage_next_project_id -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/storage.py tests/test_storage.py
git commit -m "feat: add auto-increment ID counters to ProjectStorage and PlatformStorage"
```

---

### Task 3: Wire counters into `PlatformStorage.create_project()` and `cli/main.py`

**Files:**
- Modify: `core/storage.py` — `create_project()`
- Modify: `cli/main.py` — `_issue_create()`

- [ ] **Step 1: Write failing integration test**

Add to `tests/test_storage.py`:

```python
def test_create_project_gets_incremental_id(tmp_path):
    platform = PlatformStorage(tmp_path)
    p1, _ = platform.create_project(name="Alpha", workspace_path="/tmp/alpha")
    p2, _ = platform.create_project(name="Beta", workspace_path="/tmp/beta")
    assert p1.id == "PRJ-1"
    assert p2.id == "PRJ-2"


def test_create_project_with_custom_key(tmp_path):
    platform = PlatformStorage(tmp_path)
    p, store = platform.create_project(name="Blog", workspace_path="/tmp/blog", key="BLOG")
    assert p.key == "BLOG"
    issue_id = store.next_issue_id(p.key)
    assert issue_id == "BLOG-1"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_storage.py::test_create_project_gets_incremental_id tests/test_storage.py::test_create_project_with_custom_key -v
```

Expected: FAIL — `create_project` still uses old hash-based ID.

- [ ] **Step 3: Update `PlatformStorage.create_project()` in `core/storage.py`**

Replace the existing `create_project` method:

```python
def create_project(self, name: str, workspace_path: str, key: str = "ISS") -> tuple[Project, ProjectStorage]:
    project_id = self.next_project_id()
    project = Project.create(id=project_id, name=name, workspace_path=workspace_path, key=key)
    project_dir = self.projects_dir / project.id
    store = ProjectStorage(project_dir)
    store.save_project_meta(project)
    (project_dir / "issues").mkdir(parents=True, exist_ok=True)
    (project_dir / "specs").mkdir(exist_ok=True)
    (project_dir / "runs").mkdir(exist_ok=True)
    board = Board.create()
    store.save_board(board)
    self._set_active(project.id)
    return project, store
```

- [ ] **Step 4: Run integration tests**

```bash
python -m pytest tests/test_storage.py::test_create_project_gets_incremental_id tests/test_storage.py::test_create_project_with_custom_key -v
```

Expected: PASS

- [ ] **Step 5: Update `_issue_create()` in `cli/main.py`**

Replace the `Issue.create(...)` call in `_issue_create` (around line 96):

```python
def _issue_create(args: argparse.Namespace) -> None:
    from core.models import Issue
    import json
    store = _get_storage(args)

    # Determine issue prefix from project key
    project = store.load_project_meta()
    prefix = project.key if project else "ISS"
    issue_id = store.next_issue_id(prefix)

    issue = Issue.create(
        id=issue_id,
        title=args.title,
        priority=args.priority,
        labels=args.label or [],
    )
    store.save_issue(issue)

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

- [ ] **Step 6: Update `_project_create()` in `cli/main.py` to accept `--key`**

Replace `_project_create` and its parser registration:

```python
def _project_create(args: argparse.Namespace) -> None:
    platform = _get_platform()
    workspace_path = str(Path(args.workspace_path).resolve())
    key = (args.key or "ISS").upper()
    project, store = platform.create_project(name=args.name, workspace_path=workspace_path, key=key)
    print(f"Created project {project.id}: {project.name}  (issue prefix: {project.key})")
    print(f"  Workspace: {workspace_path}")
    print(f"  Storage:   {store.root}")
```

In `build_parser()`, find the `project create` subparser block and add the `--key` argument:

```python
p = project_sub.add_parser("create", help="Create a new project")
p.add_argument("name", help="Project name")
p.add_argument("workspace_path", help="Path to workspace directory")
p.add_argument("--key", default="ISS", help="Issue ID prefix (e.g. BLOG → BLOG-1, BLOG-2). Default: ISS")
p.set_defaults(func=_project_create)
```

- [ ] **Step 7: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: All PASS (fix any remaining failures from old hash-based ID assumptions in other test files)

- [ ] **Step 8: Commit**

```bash
git add core/storage.py cli/main.py tests/test_storage.py
git commit -m "feat: wire JIRA-style auto-increment IDs into project creation and issue creation"
```

---

### Task 4: Fix remaining test files that reference old ID format

**Files:**
- Modify: `tests/test_cli_issue.py`
- Modify: `tests/test_cli.py` (if needed)

- [ ] **Step 1: Run the full test suite and capture failures**

```bash
python -m pytest tests/ -v 2>&1 | grep -E "FAILED|ERROR"
```

- [ ] **Step 2: For each failing test, update ID assertions**

Any test that does `assert issue.id.startswith("ISS-")` and then checks the hash format should be updated. The new IDs are `ISS-1`, `ISS-2`, etc. Tests that just check `startswith("ISS-")` will still pass. Tests that check the full ID value need to use the counter.

Example pattern — if a test creates an issue and checks its ID:

```python
# Old (hash-based):
assert re.match(r"ISS-[a-f0-9]{6}", issue.id)

# New (numeric):
assert re.match(r"ISS-\d+", issue.id)
```

- [ ] **Step 3: Run full test suite again**

```bash
python -m pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: update test assertions for JIRA-style numeric IDs"
```

---

### Task 5: Update `core/migrate.py` to use counter when creating issues

**Files:**
- Modify: `core/migrate.py`

- [ ] **Step 1: Read the migrate file**

```bash
cat core/migrate.py
```

- [ ] **Step 2: Find all `Issue.create()` calls and update them**

Each call like:
```python
issue = Issue.create(title=title, ...)
```

Must become:
```python
issue_id = store.next_issue_id(prefix)
issue = Issue.create(id=issue_id, title=title, ...)
```

Where `prefix` comes from `store.load_project_meta().key` (default `"ISS"` if no project meta).

The `migrate_fix_plan` function signature should accept `store: ProjectStorage` (it already does based on `cli/main.py` usage). Add prefix resolution at the top of the function:

```python
def migrate_fix_plan(fix_plan_path: Path, store: ProjectStorage) -> list[Issue]:
    project = store.load_project_meta()
    prefix = project.key if project else "ISS"
    # ... rest of function, use store.next_issue_id(prefix) for each issue
```

- [ ] **Step 3: Run migrate-related tests**

```bash
python -m pytest tests/ -k "migrate" -v
```

Expected: PASS (or no migrate tests — that's fine too)

- [ ] **Step 4: Run full suite**

```bash
python -m pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add core/migrate.py
git commit -m "feat: use counter-based IDs in migrate_fix_plan"
```
