import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.models import Issue, IssueStatus, Board
from core.storage import ProjectStorage
from core.scheduler import Scheduler, find_ready_issues


def _make_issue(store, title, status=IssueStatus.TODO, blocked_by=None):
    """Helper to create and persist an issue at a given status."""
    issue = Issue.create(title=title)
    # Walk through transitions to reach target status
    if status in (IssueStatus.TODO, IssueStatus.IN_PROGRESS):
        issue.move_to(IssueStatus.TODO)
    if status == IssueStatus.IN_PROGRESS:
        issue.move_to(IssueStatus.IN_PROGRESS)
    if blocked_by:
        for bid in blocked_by:
            issue.add_blocker(bid)
    store.save_issue(issue)
    return issue


def test_find_ready_issues_basic(tmp_path):
    """Should find TODO issues with no blockers."""
    store = ProjectStorage(tmp_path / "project")
    a = _make_issue(store, "A", IssueStatus.TODO)
    b = _make_issue(store, "B", IssueStatus.TODO)

    ready = find_ready_issues(store)
    ids = [i.id for i in ready]
    assert a.id in ids
    assert b.id in ids


def test_find_ready_issues_skips_blocked(tmp_path):
    """Should skip issues that have unresolved blockers."""
    store = ProjectStorage(tmp_path / "project")
    a = _make_issue(store, "A", IssueStatus.TODO)
    b = _make_issue(store, "B", IssueStatus.TODO, blocked_by=[a.id])

    ready = find_ready_issues(store)
    ids = [i.id for i in ready]
    assert a.id in ids
    assert b.id not in ids


def test_find_ready_issues_skips_non_todo(tmp_path):
    """Should only return TODO issues, not BACKLOG or IN_PROGRESS."""
    store = ProjectStorage(tmp_path / "project")
    _make_issue(store, "backlog", IssueStatus.BACKLOG)
    _make_issue(store, "in_progress", IssueStatus.IN_PROGRESS)
    todo = _make_issue(store, "todo", IssueStatus.TODO)

    ready = find_ready_issues(store)
    ids = [i.id for i in ready]
    assert todo.id in ids
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_scheduler_runs_ready_issues(tmp_path):
    """Scheduler should pick up ready issues and run them via executor."""
    store = ProjectStorage(tmp_path / "project")
    a = _make_issue(store, "Task A", IssueStatus.TODO)
    b = _make_issue(store, "Task B", IssueStatus.TODO)

    run_log = []

    async def mock_executor_run(issue):
        run_log.append(issue.id)
        # Scheduler already moved to IN_PROGRESS, executor moves to AGENT_DONE
        issue.move_to(IssueStatus.AGENT_DONE)
        store.save_issue(issue)
        return {"success": True, "issue_id": issue.id}

    mock_executor = MagicMock()
    mock_executor.run = mock_executor_run

    scheduler = Scheduler(store, mock_executor, max_parallel=2)
    results = await scheduler.run_batch()

    assert len(run_log) == 2
    assert a.id in run_log
    assert b.id in run_log
    assert all(r["success"] for r in results)


@pytest.mark.asyncio
async def test_scheduler_respects_max_parallel(tmp_path):
    """Scheduler should not exceed max_parallel concurrent tasks."""
    store = ProjectStorage(tmp_path / "project")
    for i in range(5):
        _make_issue(store, f"Task {i}", IssueStatus.TODO)

    concurrent_count = 0
    max_concurrent = 0
    lock = asyncio.Lock()

    async def mock_executor_run(issue):
        nonlocal concurrent_count, max_concurrent
        async with lock:
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
        await asyncio.sleep(0.05)
        async with lock:
            concurrent_count -= 1
        # Scheduler already moved to IN_PROGRESS
        issue.move_to(IssueStatus.AGENT_DONE)
        store.save_issue(issue)
        return {"success": True, "issue_id": issue.id}

    mock_executor = MagicMock()
    mock_executor.run = mock_executor_run

    scheduler = Scheduler(store, mock_executor, max_parallel=2)
    await scheduler.run_batch()

    assert max_concurrent <= 2
