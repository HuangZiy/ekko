import pytest
from core.models import Issue, IssueStatus
from core.storage import ProjectStorage
from core.review import approve_issue, reject_issue


def _make_agent_done_issue(store, title, blocked_by=None):
    """Helper: create an issue in AGENT_DONE state."""
    issue = Issue.create(title=title)
    issue.move_to(IssueStatus.TODO)
    issue.move_to(IssueStatus.IN_PROGRESS)
    issue.move_to(IssueStatus.AGENT_DONE)
    if blocked_by:
        for bid in blocked_by:
            issue.add_blocker(bid)
    store.save_issue(issue)
    store.save_issue_content(issue.id, f"# {title}\n\nOriginal content")
    return issue


def test_approve_moves_to_human_done(tmp_path):
    """Approve should transition issue to HUMAN_DONE."""
    store = ProjectStorage(tmp_path / "project")
    issue = _make_agent_done_issue(store, "Feature A")

    approve_issue(issue.id, store)

    reloaded = store.load_issue(issue.id)
    assert reloaded.status == IssueStatus.HUMAN_DONE


def test_approve_unlocks_dependents(tmp_path):
    """Approve should remove the approved issue from dependents' blocked_by."""
    store = ProjectStorage(tmp_path / "project")
    a = _make_agent_done_issue(store, "Blocker A")

    # Create a dependent issue that's blocked by A
    dep = Issue.create(title="Dependent")
    dep.add_blocker(a.id)
    dep.move_to(IssueStatus.TODO)
    store.save_issue(dep)

    approve_issue(a.id, store)

    reloaded_dep = store.load_issue(dep.id)
    assert a.id not in reloaded_dep.blocked_by
    assert not reloaded_dep.is_blocked()


def test_reject_moves_to_todo(tmp_path):
    """Reject should transition issue back to TODO via REJECTED."""
    store = ProjectStorage(tmp_path / "project")
    issue = _make_agent_done_issue(store, "Feature B")

    reject_issue(issue.id, store, comment="缺少 loading 状态")

    reloaded = store.load_issue(issue.id)
    assert reloaded.status == IssueStatus.TODO


def test_reject_appends_feedback(tmp_path):
    """Reject should append reviewer feedback to issue markdown."""
    store = ProjectStorage(tmp_path / "project")
    issue = _make_agent_done_issue(store, "Feature C")

    reject_issue(issue.id, store, comment="需要添加错误处理")

    content = store.load_issue_content(issue.id)
    assert "需要添加错误处理" in content
    assert "## Review Feedback" in content


def test_reject_increments_retry(tmp_path):
    """Reject should increment the issue's retry count."""
    store = ProjectStorage(tmp_path / "project")
    issue = _make_agent_done_issue(store, "Feature D")
    assert issue.retry_count == 0

    reject_issue(issue.id, store, comment="try again")

    reloaded = store.load_issue(issue.id)
    assert reloaded.retry_count == 1
