"""Issue Scheduler — periodic polling and auto-dispatch of ready issues.

The scheduler runs as an asyncio background task, polling each enabled project
for ready issues and dispatching them via run_issue_loop(). It integrates with
the existing cancel-event system to avoid double-dispatching and supports
WebSocket event broadcasting for real-time UI updates.

Design:
  - Per-project scheduling state (enabled, interval, max_parallel)
  - Module-level singleton ``scheduler``
  - Reuses find_ready_issues() + run_issue_loop() from core.ralph_loop
  - Reuses _cancel_events from server.routes.run for "is running" tracking
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from config import (
    SCHEDULER_POLL_INTERVAL,
    SCHEDULER_MAX_PARALLEL,
    SCHEDULER_ENABLED_DEFAULT,
)
from core.models import IssuePriority

logger = logging.getLogger("ekko.scheduler")

# Priority sort order — lower value = higher priority
_PRIORITY_ORDER = {
    IssuePriority.URGENT: 0,
    IssuePriority.HIGH: 1,
    IssuePriority.MEDIUM: 2,
    IssuePriority.LOW: 3,
}


@dataclass
class _ProjectSchedule:
    """Mutable scheduling state for one project."""

    enabled: bool = False
    interval: int = SCHEDULER_POLL_INTERVAL
    max_parallel: int = SCHEDULER_MAX_PARALLEL
    task: asyncio.Task | None = field(default=None, repr=False)
    running_issues: set[str] = field(default_factory=set)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _wake_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


class IssueScheduler:
    """Manages per-project auto-dispatch loops.

    Usage (server mode)::

        from core.scheduler import scheduler
        await scheduler.start("PRJ-1")          # begin polling
        status = scheduler.status("PRJ-1")      # inspect
        await scheduler.stop("PRJ-1")           # halt

    Usage (CLI mode)::

        await scheduler.run_once("PRJ-1", storage, workspace)
        # or
        await scheduler.run_loop("PRJ-1", storage, workspace)
    """

    def __init__(self) -> None:
        self._schedules: dict[str, _ProjectSchedule] = {}

    # ------------------------------------------------------------------
    # Public — lifecycle
    # ------------------------------------------------------------------

    async def start(
        self,
        project_id: str,
        interval: int | None = None,
        max_parallel: int | None = None,
        on_event: Callable[[dict], Awaitable[None]] | None = None,
    ) -> dict:
        """Start the polling loop for *project_id* inside the running event loop.

        Returns the current scheduler status dict.
        """
        sched = self._ensure(project_id)

        if sched.enabled and sched.task and not sched.task.done():
            # Already running — just update settings if provided
            if interval is not None:
                sched.interval = interval
            if max_parallel is not None:
                sched.max_parallel = max_parallel
            return self.status(project_id)

        if interval is not None:
            sched.interval = interval
        if max_parallel is not None:
            sched.max_parallel = max_parallel

        sched.enabled = True
        sched._stop_event.clear()
        sched.task = asyncio.create_task(
            self._poll_loop_server(project_id, on_event),
            name=f"scheduler-{project_id}",
        )
        logger.info("Scheduler started for %s (interval=%ds, max_parallel=%d)",
                     project_id, sched.interval, sched.max_parallel)
        return self.status(project_id)

    async def stop(self, project_id: str) -> dict:
        """Stop the polling loop for *project_id*."""
        sched = self._schedules.get(project_id)
        if not sched:
            return self.status(project_id)

        sched.enabled = False
        sched._stop_event.set()

        if sched.task and not sched.task.done():
            sched.task.cancel()
            try:
                await sched.task
            except (asyncio.CancelledError, Exception):
                pass
            sched.task = None

        logger.info("Scheduler stopped for %s", project_id)
        return self.status(project_id)

    async def stop_all(self) -> None:
        """Stop all active scheduling loops (called on server shutdown)."""
        for pid in list(self._schedules):
            await self.stop(pid)

    def status(self, project_id: str) -> dict:
        """Return a JSON-serialisable status dict."""
        sched = self._schedules.get(project_id)
        if not sched:
            return {
                "enabled": False,
                "interval": SCHEDULER_POLL_INTERVAL,
                "max_parallel": SCHEDULER_MAX_PARALLEL,
                "running_issues": [],
            }
        return {
            "enabled": sched.enabled,
            "interval": sched.interval,
            "max_parallel": sched.max_parallel,
            "running_issues": sorted(sched.running_issues),
        }

    def update_settings(
        self,
        project_id: str,
        interval: int | None = None,
        max_parallel: int | None = None,
    ) -> dict:
        """Update scheduling parameters without starting/stopping."""
        sched = self._ensure(project_id)
        if interval is not None:
            sched.interval = max(5, interval)  # floor at 5s
        if max_parallel is not None:
            sched.max_parallel = max(1, max_parallel)
        return self.status(project_id)

    def trigger_poll(self, project_id: str) -> None:
        """Wake the scheduler loop immediately for *project_id*.

        Use after review-approve or any event that unblocks issues so the
        next poll cycle happens right away instead of waiting for the interval.
        No-op if the scheduler is not running for this project.
        """
        sched = self._schedules.get(project_id)
        if sched and sched.enabled and sched.task and not sched.task.done():
            sched._wake_event.set()
            logger.info("Scheduler wake triggered for %s", project_id)

    # ------------------------------------------------------------------
    # Public — CLI mode (no server, no WS)
    # ------------------------------------------------------------------

    async def run_once(
        self,
        project_id: str,
        storage,
        workspace: Path,
        max_parallel: int | None = None,
        on_event: Callable[[dict], Awaitable[None]] | None = None,
    ) -> list[dict]:
        """Single poll cycle: find ready issues, dispatch, return stats."""
        sched = self._ensure(project_id)
        if max_parallel is not None:
            sched.max_parallel = max_parallel
        return await self._poll_cycle(project_id, storage, workspace, on_event)

    async def run_loop(
        self,
        project_id: str,
        storage,
        workspace: Path,
        interval: int | None = None,
        max_parallel: int | None = None,
        on_event: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        """Blocking loop for CLI usage. Runs until interrupted."""
        sched = self._ensure(project_id)
        if interval is not None:
            sched.interval = interval
        if max_parallel is not None:
            sched.max_parallel = max_parallel
        sched.enabled = True
        sched._stop_event.clear()

        logger.info("Scheduler loop started (interval=%ds, max_parallel=%d)",
                     sched.interval, sched.max_parallel)
        print(f"[Scheduler] Polling every {sched.interval}s (max_parallel={sched.max_parallel}). Ctrl+C to stop.",
              flush=True)

        try:
            while sched.enabled and not sched._stop_event.is_set():
                await self._poll_cycle(project_id, storage, workspace, on_event)
                # Interruptible sleep — wakes on stop OR trigger_poll
                should_stop = await self._interruptible_sleep(sched)
                if should_stop:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            sched.enabled = False
            print("[Scheduler] Stopped.", flush=True)

    # ------------------------------------------------------------------
    # Internal — server poll loop
    # ------------------------------------------------------------------

    async def _poll_loop_server(
        self,
        project_id: str,
        on_event: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        """Background task for server mode. Resolves storage/workspace each cycle."""
        sched = self._schedules[project_id]

        try:
            while sched.enabled and not sched._stop_event.is_set():
                try:
                    storage, workspace = self._resolve_project(project_id)
                    await self._poll_cycle(project_id, storage, workspace, on_event)
                except Exception:
                    logger.exception("Scheduler poll error for %s", project_id)

                # Interruptible sleep — wakes on stop OR trigger_poll
                should_stop = await self._interruptible_sleep(sched)
                if should_stop:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            sched.enabled = False
            if sched.task:
                sched.task = None

    # ------------------------------------------------------------------
    # Internal — single poll cycle
    # ------------------------------------------------------------------

    async def _poll_cycle(
        self,
        project_id: str,
        storage,
        workspace: Path,
        on_event: Callable[[dict], Awaitable[None]] | None = None,
    ) -> list[dict]:
        """One poll iteration: find ready → filter running → sort → dispatch."""
        from core.ralph_loop import find_ready_issues, run_issue_loop

        sched = self._ensure(project_id)
        ready = find_ready_issues(storage)

        # Filter out issues already being run (by scheduler or manual trigger)
        already_running = self._get_globally_running_issues()
        dispatchable = [i for i in ready if i.id not in already_running]

        # Sort by priority (urgent first)
        dispatchable.sort(key=lambda i: _PRIORITY_ORDER.get(i.priority, 99))

        # Respect max_parallel — how many slots are free?
        current_count = len(sched.running_issues)
        free_slots = max(0, sched.max_parallel - current_count)
        to_dispatch = dispatchable[:free_slots]

        # Broadcast poll event
        if on_event:
            await on_event({
                "type": "scheduler_poll",
                "data": {
                    "project_id": project_id,
                    "found_ready": len(ready),
                    "already_running": len(ready) - len(dispatchable),
                    "dispatching": len(to_dispatch),
                    "ts": int(time.time()),
                },
            })

        if not to_dispatch:
            return []

        logger.info("Dispatching %d issues for %s: %s",
                     len(to_dispatch), project_id,
                     [i.id for i in to_dispatch])

        # Dispatch
        all_stats: list[dict] = []
        if sched.max_parallel <= 1:
            for issue in to_dispatch:
                stats = await self._dispatch_one(project_id, issue, storage, workspace, on_event)
                all_stats.append(stats)
        else:
            semaphore = asyncio.Semaphore(sched.max_parallel)
            tasks = []
            for issue in to_dispatch:
                async def _run(iss=issue):
                    async with semaphore:
                        return await self._dispatch_one(project_id, iss, storage, workspace, on_event)
                tasks.append(asyncio.create_task(_run()))
            for coro in asyncio.as_completed(tasks):
                stats = await coro
                all_stats.append(stats)

        return all_stats

    async def _dispatch_one(
        self,
        project_id: str,
        issue,
        storage,
        workspace: Path,
        on_event: Callable[[dict], Awaitable[None]] | None = None,
    ) -> dict:
        """Run a single issue with proper bookkeeping."""
        from core.ralph_loop import run_issue_loop

        sched = self._ensure(project_id)
        issue_id = issue.id

        # Register as running
        cancel_event = self._register_running(issue_id, sched)

        run_counter = len(storage.list_run_ids(issue_id)) + 1

        # Broadcast start
        if on_event:
            await on_event({
                "type": "agent_started",
                "data": {"issue_id": issue_id, "title": issue.title, "source": "scheduler"},
            })

        # Build per-issue event callback that also persists logs
        async def _issue_event(event: dict) -> None:
            if on_event:
                await on_event(event)
            evt_type = event.get("type", "")
            evt_issue_id = event.get("issue_id")
            if evt_issue_id and evt_type.startswith("agent_"):
                storage.append_run_log(evt_issue_id, f"run-{run_counter:03d}", event)

        try:
            stats = await run_issue_loop(
                issue, storage, workspace,
                on_event=_issue_event,
                cancel_event=cancel_event,
            )
            run_id = f"run-{run_counter:03d}"
            storage.save_run_stats(issue_id, run_id, stats)

            if on_event:
                await on_event({
                    "type": "agent_done",
                    "data": {
                        "issue_id": issue_id,
                        "success": stats["success"],
                        "cost_usd": stats.get("cost_usd", 0),
                        "source": "scheduler",
                    },
                })
            return stats

        except Exception as e:
            logger.exception("Scheduler dispatch error for %s", issue_id)
            if on_event:
                await on_event({
                    "type": "run_error",
                    "data": {"issue_id": issue_id, "error": str(e), "source": "scheduler"},
                })
            return {
                "success": False, "issue_id": issue_id, "title": issue.title,
                "attempts": 0, "cost_usd": 0, "duration_ms": 0, "details": [],
                "error": str(e),
            }
        finally:
            self._unregister_running(issue_id, sched)

    async def _interruptible_sleep(self, sched: _ProjectSchedule) -> bool:
        """Sleep for *interval* seconds, interruptible by stop or wake events.

        Returns ``True`` if the loop should stop (stop_event was set),
        ``False`` if the sleep was interrupted by wake or timed out normally.
        """
        stop_task = asyncio.ensure_future(sched._stop_event.wait())
        wake_task = asyncio.ensure_future(sched._wake_event.wait())
        try:
            _done, pending = await asyncio.wait(
                {stop_task, wake_task},
                timeout=sched.interval,
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            stop_task.cancel()
            wake_task.cancel()
            raise

        for t in (stop_task, wake_task):
            if not t.done():
                t.cancel()

        # Reset wake so it can be triggered again next cycle
        sched._wake_event.clear()

        return sched._stop_event.is_set()

    # ------------------------------------------------------------------
    # Internal — running-issue tracking
    # ------------------------------------------------------------------

    def _register_running(self, issue_id: str, sched: _ProjectSchedule) -> asyncio.Event:
        """Mark issue as running in both scheduler and the global _cancel_events."""
        sched.running_issues.add(issue_id)
        # Also register in server.routes.run._cancel_events for watchdog compat
        try:
            from server.routes.run import get_cancel_event
            return get_cancel_event(issue_id)
        except ImportError:
            # CLI mode — no server module
            cancel = asyncio.Event()
            return cancel

    def _unregister_running(self, issue_id: str, sched: _ProjectSchedule) -> None:
        """Remove issue from running sets."""
        sched.running_issues.discard(issue_id)
        try:
            from server.routes.run import clear_cancel
            clear_cancel(issue_id)
        except ImportError:
            pass

    def _get_globally_running_issues(self) -> set[str]:
        """Collect all issue IDs currently running across scheduler + manual runs."""
        running = set()
        # From scheduler state
        for sched in self._schedules.values():
            running |= sched.running_issues
        # From server.routes.run._cancel_events (manual runs)
        try:
            from server.routes.run import _cancel_events
            running |= set(_cancel_events.keys())
        except ImportError:
            pass
        return running

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    def _ensure(self, project_id: str) -> _ProjectSchedule:
        if project_id not in self._schedules:
            self._schedules[project_id] = _ProjectSchedule(
                enabled=SCHEDULER_ENABLED_DEFAULT,
                interval=SCHEDULER_POLL_INTERVAL,
                max_parallel=SCHEDULER_MAX_PARALLEL,
            )
        return self._schedules[project_id]

    @staticmethod
    def _resolve_project(project_id: str):
        """Resolve storage + workspace for a project (server mode)."""
        from server.app import get_project_storage
        storage = get_project_storage(project_id)
        project = storage.load_project_meta()
        if not project or not project.workspaces:
            raise ValueError(f"Project {project_id} has no workspace configured")
        workspace = Path(project.workspaces[0]).resolve()
        return storage, workspace


# Module-level singleton
scheduler = IssueScheduler()
