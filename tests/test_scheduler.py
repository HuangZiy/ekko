"""Unit tests for the Issue Scheduler (core/scheduler.py)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.models import Issue, IssueStatus, IssuePriority
from core.storage import ProjectStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_issue(
    id: str,
    title: str = "test",
    status: str = "todo",
    priority: str = "medium",
    blocked_by: list[str] | None = None,
) -> Issue:
    issue = Issue.create(id=id, title=title, priority=priority)
    issue.status = IssueStatus(status)
    if blocked_by:
        issue.blocked_by = blocked_by
    return issue


def _setup_storage(tmp_path: Path, issues: list[Issue]) -> ProjectStorage:
    """Create a ProjectStorage with pre-populated issues."""
    store = ProjectStorage(tmp_path / "project")
    for issue in issues:
        store.save_issue(issue)
    return store


# ---------------------------------------------------------------------------
# find_ready_issues — priority sorting
# ---------------------------------------------------------------------------

class TestFindReadyIssuesPriority:
    """Verify that find_ready_issues returns results sorted by priority."""

    def test_sorted_by_priority(self, tmp_path):
        from core.ralph_loop import find_ready_issues

        issues = [
            _make_issue("ISS-1", "low task", priority="low"),
            _make_issue("ISS-2", "urgent task", priority="urgent"),
            _make_issue("ISS-3", "high task", priority="high"),
            _make_issue("ISS-4", "medium task", priority="medium"),
        ]
        store = _setup_storage(tmp_path, issues)
        ready = find_ready_issues(store)

        assert len(ready) == 4
        assert ready[0].id == "ISS-2"  # urgent
        assert ready[1].id == "ISS-3"  # high
        assert ready[2].id == "ISS-4"  # medium
        assert ready[3].id == "ISS-1"  # low

    def test_blocked_issues_excluded(self, tmp_path):
        from core.ralph_loop import find_ready_issues

        issues = [
            _make_issue("ISS-1", "done", status="human_done"),
            _make_issue("ISS-2", "ready", blocked_by=["ISS-1"]),  # unblocked (ISS-1 is done)
            _make_issue("ISS-3", "blocked", blocked_by=["ISS-99"]),  # blocked (ISS-99 not done)
        ]
        store = _setup_storage(tmp_path, issues)
        ready = find_ready_issues(store)

        assert len(ready) == 1
        assert ready[0].id == "ISS-2"

    def test_only_todo_and_backlog(self, tmp_path):
        from core.ralph_loop import find_ready_issues

        issues = [
            _make_issue("ISS-1", status="todo"),
            _make_issue("ISS-2", status="backlog"),
            _make_issue("ISS-3", status="in_progress"),
            _make_issue("ISS-4", status="agent_done"),
            _make_issue("ISS-5", status="human_done"),
        ]
        store = _setup_storage(tmp_path, issues)
        ready = find_ready_issues(store)

        ids = {i.id for i in ready}
        assert ids == {"ISS-1", "ISS-2"}


# ---------------------------------------------------------------------------
# IssueScheduler — unit tests
# ---------------------------------------------------------------------------

class TestIssueScheduler:
    """Test the IssueScheduler class."""

    def test_status_default(self):
        from core.scheduler import IssueScheduler

        sched = IssueScheduler()
        status = sched.status("PRJ-1")
        assert status["enabled"] is False
        assert status["running_issues"] == []
        assert "interval" in status
        assert "max_parallel" in status

    def test_update_settings(self):
        from core.scheduler import IssueScheduler

        sched = IssueScheduler()
        status = sched.update_settings("PRJ-1", interval=30, max_parallel=3)
        assert status["interval"] == 30
        assert status["max_parallel"] == 3

    def test_update_settings_floor(self):
        from core.scheduler import IssueScheduler

        sched = IssueScheduler()
        # interval should be floored at 5s
        status = sched.update_settings("PRJ-1", interval=2)
        assert status["interval"] == 5

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self):
        from core.scheduler import IssueScheduler

        sched = IssueScheduler()

        # Mock _resolve_project to avoid needing real storage
        with patch.object(sched, "_resolve_project") as mock_resolve:
            mock_storage = MagicMock()
            mock_storage.list_issues.return_value = []
            mock_resolve.return_value = (mock_storage, Path("/tmp/ws"))

            status = await sched.start("PRJ-1", interval=5)
            assert status["enabled"] is True

            # Give the loop a moment to start
            await asyncio.sleep(0.05)

            status = await sched.stop("PRJ-1")
            assert status["enabled"] is False

    @pytest.mark.asyncio
    async def test_no_duplicate_dispatch(self, tmp_path):
        """Scheduler should not dispatch issues already in running_issues."""
        from core.scheduler import IssueScheduler

        issues = [
            _make_issue("ISS-1", "task A", priority="urgent"),
            _make_issue("ISS-2", "task B", priority="high"),
        ]
        store = _setup_storage(tmp_path, issues)

        sched = IssueScheduler()
        # Pretend ISS-1 is already running
        proj_sched = sched._ensure("PRJ-1")
        proj_sched.running_issues.add("ISS-1")
        proj_sched.max_parallel = 10  # no slot limit

        dispatched_ids = []
        original_dispatch = sched._dispatch_one

        async def mock_dispatch(project_id, issue, storage, workspace, on_event=None):
            dispatched_ids.append(issue.id)
            return {"success": True, "issue_id": issue.id, "title": issue.title,
                    "attempts": 1, "cost_usd": 0, "duration_ms": 0, "details": []}

        with patch.object(sched, "_dispatch_one", side_effect=mock_dispatch):
            await sched._poll_cycle("PRJ-1", store, Path("/tmp/ws"))

        # ISS-1 should NOT be dispatched (already running)
        assert "ISS-1" not in dispatched_ids
        assert "ISS-2" in dispatched_ids

    @pytest.mark.asyncio
    async def test_respects_max_parallel(self, tmp_path):
        """Scheduler should only dispatch up to max_parallel issues."""
        from core.scheduler import IssueScheduler

        issues = [
            _make_issue("ISS-1", priority="urgent"),
            _make_issue("ISS-2", priority="high"),
            _make_issue("ISS-3", priority="medium"),
        ]
        store = _setup_storage(tmp_path, issues)

        sched = IssueScheduler()
        proj_sched = sched._ensure("PRJ-1")
        proj_sched.max_parallel = 1  # only 1 slot

        dispatched_ids = []

        async def mock_dispatch(project_id, issue, storage, workspace, on_event=None):
            dispatched_ids.append(issue.id)
            return {"success": True, "issue_id": issue.id, "title": issue.title,
                    "attempts": 1, "cost_usd": 0, "duration_ms": 0, "details": []}

        with patch.object(sched, "_dispatch_one", side_effect=mock_dispatch):
            await sched._poll_cycle("PRJ-1", store, Path("/tmp/ws"))

        # Only 1 issue should be dispatched (max_parallel=1)
        assert len(dispatched_ids) == 1
        # And it should be the highest priority one
        assert dispatched_ids[0] == "ISS-1"

    @pytest.mark.asyncio
    async def test_blocked_issues_not_dispatched(self, tmp_path):
        """Scheduler should not dispatch issues whose blockers aren't done."""
        from core.scheduler import IssueScheduler

        issues = [
            _make_issue("ISS-1", "parent", status="todo"),
            _make_issue("ISS-2", "child", status="todo", blocked_by=["ISS-1"]),
        ]
        store = _setup_storage(tmp_path, issues)

        sched = IssueScheduler()
        proj_sched = sched._ensure("PRJ-1")
        proj_sched.max_parallel = 10

        dispatched_ids = []

        async def mock_dispatch(project_id, issue, storage, workspace, on_event=None):
            dispatched_ids.append(issue.id)
            return {"success": True, "issue_id": issue.id, "title": issue.title,
                    "attempts": 1, "cost_usd": 0, "duration_ms": 0, "details": []}

        with patch.object(sched, "_dispatch_one", side_effect=mock_dispatch):
            await sched._poll_cycle("PRJ-1", store, Path("/tmp/ws"))

        # Only ISS-1 should be dispatched; ISS-2 is blocked
        assert "ISS-1" in dispatched_ids
        assert "ISS-2" not in dispatched_ids

    @pytest.mark.asyncio
    async def test_dispatch_broadcasts_events(self, tmp_path):
        """Scheduler should broadcast agent_started and agent_done events."""
        from core.scheduler import IssueScheduler

        issues = [_make_issue("ISS-1", "task")]
        store = _setup_storage(tmp_path, issues)

        sched = IssueScheduler()
        proj_sched = sched._ensure("PRJ-1")
        proj_sched.max_parallel = 1

        events = []

        async def capture_event(event):
            events.append(event)

        mock_stats = {
            "success": True, "issue_id": "ISS-1", "title": "task",
            "attempts": 1, "cost_usd": 0.5, "duration_ms": 1000, "details": [],
        }

        with patch("core.ralph_loop.run_issue_loop", new_callable=AsyncMock, return_value=mock_stats):
            await sched._poll_cycle("PRJ-1", store, Path("/tmp/ws"), on_event=capture_event)

        event_types = [e["type"] for e in events]
        assert "scheduler_poll" in event_types
        assert "agent_started" in event_types
        assert "agent_done" in event_types

    @pytest.mark.asyncio
    async def test_run_once(self, tmp_path):
        """run_once should execute a single poll cycle."""
        from core.scheduler import IssueScheduler

        issues = [_make_issue("ISS-1", "task", priority="urgent")]
        store = _setup_storage(tmp_path, issues)

        sched = IssueScheduler()

        mock_stats = {
            "success": True, "issue_id": "ISS-1", "title": "task",
            "attempts": 1, "cost_usd": 0.1, "duration_ms": 500, "details": [],
        }

        with patch("core.ralph_loop.run_issue_loop", new_callable=AsyncMock, return_value=mock_stats):
            results = await sched.run_once("PRJ-1", store, Path("/tmp/ws"))

        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["issue_id"] == "ISS-1"
