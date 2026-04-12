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
    """Manages multiple projects under .harness/projects/."""

    def __init__(self, harness_root: Path) -> None:
        self.root = harness_root
        self.projects_dir = self.root / "projects"

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
        project_dir = self.projects_dir / project.id
        store = ProjectStorage(project_dir)
        store.save_project_meta(project)
        (project_dir / "issues").mkdir(parents=True, exist_ok=True)
        (project_dir / "specs").mkdir(exist_ok=True)
        (project_dir / "runs").mkdir(exist_ok=True)
        board = Board.create()
        store.save_board(board)
        # Save active project marker
        self._set_active(project.id)
        return project, store

    def list_projects(self) -> list[tuple[str, Project]]:
        if not self.projects_dir.exists():
            return []
        result = []
        for d in sorted(self.projects_dir.iterdir()):
            meta = d / "project.json"
            if meta.exists():
                data = json.loads(meta.read_text())
                result.append((d.name, Project(**data)))
        return result

    def get_project_storage(self, project_id: str) -> ProjectStorage:
        return ProjectStorage(self.projects_dir / project_id)

    def get_active_project_id(self) -> str | None:
        active_file = self.root / "active_project"
        if active_file.exists():
            return active_file.read_text().strip()
        # Fallback: return first project
        projects = self.list_projects()
        return projects[0][0] if projects else None

    def _set_active(self, project_id: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "active_project").write_text(project_id)

    def switch_project(self, project_id: str) -> bool:
        if (self.projects_dir / project_id).exists():
            self._set_active(project_id)
            return True
        return False

