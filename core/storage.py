from __future__ import annotations
import json
from pathlib import Path
from dataclasses import asdict

from core.models import Issue, Board, Project


class ProjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.issues_dir = self.root / "issues"

    def _next_id(self, prefix: str) -> str:
        counter_file = self.root / "counter.json"
        counters: dict[str, int] = {}
        if counter_file.exists():
            counters = json.loads(counter_file.read_text())
        n = counters.get(prefix, 0) + 1
        counters[prefix] = n
        self.root.mkdir(parents=True, exist_ok=True)
        counter_file.write_text(json.dumps(counters))
        return f"{prefix}-{n}"

    def next_issue_id(self, prefix: str = "ISS") -> str:
        return self._next_id(prefix)

    def save_issue(self, issue: Issue) -> None:
        issue_dir = self.issues_dir / issue.id
        issue_dir.mkdir(parents=True, exist_ok=True)
        (issue_dir / "meta.json").write_text(
            json.dumps(issue.to_json(), indent=2, ensure_ascii=False)
        )

    def load_issue(self, issue_id: str) -> Issue:
        meta_file = self.issues_dir / issue_id / "meta.json"
        data = json.loads(meta_file.read_text())
        return Issue.from_json(data)

    def save_issue_content(self, issue_id: str, content: str) -> None:
        issue_dir = self.issues_dir / issue_id
        issue_dir.mkdir(parents=True, exist_ok=True)
        (issue_dir / "content.md").write_text(content)

    def load_issue_content(self, issue_id: str) -> str:
        return (self.issues_dir / issue_id / "content.md").read_text()

    def save_issue_plan(self, issue_id: str, plan: str) -> None:
        issue_dir = self.issues_dir / issue_id
        issue_dir.mkdir(parents=True, exist_ok=True)
        (issue_dir / "plan.md").write_text(plan)

    def load_issue_plan(self, issue_id: str) -> str:
        f = self.issues_dir / issue_id / "plan.md"
        return f.read_text() if f.exists() else ""

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

    def save_run_stats(self, issue_id: str, run_id: str, stats: dict) -> None:
        stats_dir = self.issues_dir / issue_id / "stats"
        stats_dir.mkdir(parents=True, exist_ok=True)
        (stats_dir / f"{run_id}.json").write_text(
            json.dumps(stats, indent=2, ensure_ascii=False)
        )

    def load_run_stats(self, issue_id: str, run_id: str) -> dict | None:
        f = self.issues_dir / issue_id / "stats" / f"{run_id}.json"
        return json.loads(f.read_text()) if f.exists() else None

    def list_all_run_stats(self, issue_id: str) -> list[dict]:
        stats_dir = self.issues_dir / issue_id / "stats"
        if not stats_dir.exists():
            return []
        result = []
        for f in sorted(stats_dir.glob("*.json")):
            result.append(json.loads(f.read_text()))
        return result

    def list_issues(self) -> list[Issue]:
        if not self.issues_dir.exists():
            return []
        issues = []
        for issue_dir in sorted(self.issues_dir.iterdir()):
            meta = issue_dir / "meta.json"
            if meta.exists():
                issues.append(Issue.from_json(json.loads(meta.read_text())))
        return issues

    def save_board(self, board: Board) -> None:
        data = {"columns": [{"id": c.id, "name": c.name, "issues": c.issues} for c in board.columns]}
        (self.root / "board.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def load_board(self) -> Board | None:
        board_file = self.root / "board.json"
        if not board_file.exists():
            return None
        data = json.loads(board_file.read_text())
        from core.models import BoardColumn
        board = Board()
        board.columns = [BoardColumn(id=c["id"], name=c["name"], issues=c.get("issues", [])) for c in data["columns"]]
        return board

    def save_project_meta(self, project: Project) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "project.json").write_text(
            json.dumps(asdict(project), indent=2, ensure_ascii=False)
        )

    def load_project_meta(self) -> Project | None:
        meta = self.root / "project.json"
        if not meta.exists():
            return None
        data = json.loads(meta.read_text())
        return Project(**data)


class PlatformStorage:
    """Manages multiple projects. Central registry at harness_root, project data in workspace/.harness/."""

    def __init__(self, harness_root: Path) -> None:
        self.root = harness_root
        self._registry_file = self.root / "registry.json"

    def _load_registry(self) -> dict[str, str]:
        """Load project_id → workspace_path mapping."""
        if self._registry_file.exists():
            return json.loads(self._registry_file.read_text())
        return {}

    def _save_registry(self, registry: dict[str, str]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._registry_file.write_text(json.dumps(registry, indent=2, ensure_ascii=False))

    def _next_id(self, prefix: str) -> str:
        counter_file = self.root / "counter.json"
        counters: dict[str, int] = {}
        if counter_file.exists():
            counters = json.loads(counter_file.read_text())
        n = counters.get(prefix, 0) + 1
        counters[prefix] = n
        self.root.mkdir(parents=True, exist_ok=True)
        counter_file.write_text(json.dumps(counters))
        return f"{prefix}-{n}"

    def next_project_id(self) -> str:
        return self._next_id("PRJ")

    def create_project(self, name: str, workspace_path: str, key: str = "ISS") -> tuple[Project, ProjectStorage]:
        project_id = self.next_project_id()
        project = Project.create(id=project_id, name=name, workspace_path=workspace_path, key=key)
        # Store project data in workspace/.harness/
        project_root = Path(workspace_path) / ".harness"
        store = ProjectStorage(project_root)
        store.save_project_meta(project)
        (project_root / "issues").mkdir(parents=True, exist_ok=True)
        (project_root / "specs").mkdir(exist_ok=True)
        (project_root / "runs").mkdir(exist_ok=True)
        board = Board.create()
        store.save_board(board)
        # Register in central registry
        registry = self._load_registry()
        registry[project_id] = workspace_path
        self._save_registry(registry)
        self._set_active(project_id)
        return project, store

    def list_projects(self) -> list[tuple[str, Project]]:
        registry = self._load_registry()
        result = []
        for pid, ws_path in sorted(registry.items()):
            project_root = Path(ws_path) / ".harness"
            meta = project_root / "project.json"
            if meta.exists():
                data = json.loads(meta.read_text())
                result.append((pid, Project(**data)))
        return result

    def get_project_storage(self, project_id: str) -> ProjectStorage:
        registry = self._load_registry()
        ws_path = registry.get(project_id)
        if not ws_path:
            raise FileNotFoundError(f"Project {project_id} not in registry")
        return ProjectStorage(Path(ws_path) / ".harness")

    def get_active_project_id(self) -> str | None:
        active_file = self.root / "active_project"
        if active_file.exists():
            return active_file.read_text().strip()
        projects = self.list_projects()
        return projects[0][0] if projects else None

    def _set_active(self, project_id: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "active_project").write_text(project_id)

    def switch_project(self, project_id: str) -> bool:
        registry = self._load_registry()
        if project_id in registry:
            self._set_active(project_id)
            return True
        return False

