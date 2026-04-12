"""Migrate existing fix_plan.md to Issue-based kanban system."""

from __future__ import annotations
import re
from pathlib import Path

from core.models import Issue, IssueStatus, Board
from core.storage import ProjectStorage


def migrate_fix_plan(fix_plan_path: Path, storage: ProjectStorage) -> list[Issue]:
    """Parse fix_plan.md and create Issues from checklist items.

    Returns list of created Issues.
    """
    if not fix_plan_path.exists():
        return []

    content = fix_plan_path.read_text()
    issues: list[Issue] = []
    current_section = ""

    for line in content.splitlines():
        line = line.strip()

        # Track section headers for labels
        if line.startswith("## "):
            current_section = line.removeprefix("## ").strip()
            continue

        # Parse checklist items
        match_todo = re.match(r"^- \[ \] (.+)$", line)
        match_done = re.match(r"^- \[x\] (.+)$", line)

        if match_todo:
            title = match_todo.group(1).strip()
            # Strip bold markers
            title = re.sub(r"\*\*(.+?)\*\*", r"\1", title)
            # Split on " — " to get title and description
            parts = title.split(" — ", 1)
            issue_title = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else ""

            issue = Issue.create(title=issue_title, priority="medium")
            issue.move_to(IssueStatus.TODO)
            labels = _section_to_labels(current_section)
            issue.labels = labels
            storage.save_issue(issue)

            if description:
                md = f"# {issue.id}: {issue_title}\n\n## 描述\n\n{description}\n"
                storage.save_issue_content(issue.id, md)

            issues.append(issue)

        elif match_done:
            title = match_done.group(1).strip()
            title = re.sub(r"\*\*(.+?)\*\*", r"\1", title)
            parts = title.split(" — ", 1)
            issue_title = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else ""

            issue = Issue.create(title=issue_title, priority="medium")
            issue.move_to(IssueStatus.TODO)
            issue.move_to(IssueStatus.IN_PROGRESS)
            issue.move_to(IssueStatus.AGENT_DONE)
            issue.move_to(IssueStatus.HUMAN_DONE)
            labels = _section_to_labels(current_section)
            issue.labels = labels
            storage.save_issue(issue)

            if description:
                md = f"# {issue.id}: {issue_title}\n\n## 描述\n\n{description}\n"
                storage.save_issue_content(issue.id, md)

            issues.append(issue)

    # Update board
    _update_board(storage, issues)

    return issues


def _update_board(storage: ProjectStorage, issues: list[Issue]) -> None:
    """Create/update board.json with migrated issues in correct columns."""
    board = Board.create()
    for issue in issues:
        col = issue.status.value
        # Map status to board column
        if col in ("backlog", "todo", "in_progress", "agent_done", "rejected", "human_done"):
            board.add_issue(issue.id, col)
        elif col == "planning":
            board.add_issue(issue.id, "backlog")

    import json
    board_file = storage.root / "board.json"
    data = {"columns": [{"id": c.id, "name": c.name, "issues": c.issues} for c in board.columns]}
    board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _section_to_labels(section: str) -> list[str]:
    """Convert fix_plan section header to labels."""
    if not section:
        return []
    section_lower = section.lower()
    if "基础" in section_lower or "infra" in section_lower:
        return ["infra"]
    if "pretext" in section_lower:
        return ["pretext"]
    if "内容" in section_lower or "content" in section_lower:
        return ["content"]
    if "页面" in section_lower or "page" in section_lower:
        return ["frontend"]
    if "搜索" in section_lower or "search" in section_lower:
        return ["search"]
    if "bug" in section_lower or "fix" in section_lower:
        return ["bugfix"]
    if "evaluator" in section_lower or "eval" in section_lower:
        return ["eval-feedback"]
    return [section[:20].lower().replace(" ", "-")]
