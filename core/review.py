from __future__ import annotations
from datetime import datetime, timezone

from core.models import Issue, IssueStatus
from core.storage import ProjectStorage


def approve_issue(issue_id: str, storage: ProjectStorage) -> None:
    """Approve an AGENT_DONE issue: move to HUMAN_DONE and unlock dependents."""
    issue = storage.load_issue(issue_id)
    issue.move_to(IssueStatus.HUMAN_DONE)
    storage.save_issue(issue)

    # Unlock any issues blocked by this one
    for other in storage.list_issues():
        if issue_id in other.blocked_by:
            other.remove_blocker(issue_id)
            storage.save_issue(other)


def reject_issue(issue_id: str, storage: ProjectStorage, comment: str = "") -> None:
    """Reject an AGENT_DONE issue: append feedback, move back to TODO."""
    issue = storage.load_issue(issue_id)

    # Append feedback to markdown
    if comment:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        feedback = f"\n\n## Review Feedback ({now})\n\n{comment}\n"
        try:
            existing = storage.load_issue_content(issue_id)
        except FileNotFoundError:
            existing = ""
        storage.save_issue_content(issue_id, existing + feedback)

    # AGENT_DONE → REJECTED → TODO
    issue.move_to(IssueStatus.REJECTED)
    issue.move_to(IssueStatus.TODO)
    issue.retry_count += 1
    storage.save_issue(issue)
