from __future__ import annotations
import json
from pathlib import Path

from core.models import Issue


class ProjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.issues_dir = self.root / "issues"

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
