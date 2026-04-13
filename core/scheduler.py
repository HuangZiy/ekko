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
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


def _slog(msg: str) -> None:
    """Scheduler log — always visible via print + logger."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[Scheduler {ts}] {msg}"
    print(line, flush=True)
    logger.info(msg)


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
    # Diagnostics
    poll_count: int = 0
    dispatch_count: int = 0
    last_poll_at: str | None = None
    last_error: str | None = None
    last_dispatch_at: str | None = None


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
            _slog(f"{project_id}: already running, updated settings")
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
        _slog(f"{project_id}: scheduler STARTED (interval={sched.interval}s, max_parallel={sched.max_parallel})")

        # Broadcast scheduler status via WS
        if on_event:
            try:
                await on_event({
                    "type": "scheduler_status",
                    "data": self.status(project_id),
                })
            except Exception:
                pass

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

        _slog(f"{project_id}: scheduler STOPPED")
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
                "poll_count": 0,
                "dispatch_count": 0,
                "last_poll_at": None,
                "last_error": None,
                "last_dispatch_at": None,
                "task_alive": False,
            }
        return {
            "enabled": sched.enabled,
            "interval": sched.interval,
            "max_parallel": sched.max_parallel,
            "running_issues": sorted(sched.running_issues),
            "poll_count": sched.poll_count,
            "dispatch_count": sched.dispatch_count,
            "last_poll_at": sched.last_poll_at,
            "last_error": sched.last_error,
            "last_dispatch_at": sched.last_dispatch_at,
            "task_alive": sched.task is not None and not sched.task.done(),
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
            _slog(f"{project_id}: wake triggered (e.g. after review-approve)")

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

        _slog(f"CLI loop started (interval={sched.interval}s, max_parallel={sched.max_parallel}). Ctrl+C to stop.")

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
            _slog("CLI loop stopped.")

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
        _slog(f"{project_id}: poll loop task RUNNING")

        try:
            while sched.enabled and not sched._stop_event.is_set():
                try:
                    storage, workspace = self._resolve_project(project_id)
                    await self._poll_cycle(project_id, storage, workspace, on_event)
                except Exception as exc:
                    err_msg = f"{type(exc).__name__}: {exc}"
                    sched.last_error = err_msg
                    _slog(f"{project_id}: poll ERROR — {err_msg}")
                    logger.exception("Scheduler poll error for %s", project_id)

                # Interruptible sleep — wakes on stop OR trigger_poll
                should_stop = await self._interruptible_sleep(sched)
                if should_stop:
                    _slog(f"{project_id}: stop event received, exiting loop")
                    break
        except asyncio.CancelledError:
            _slog(f"{project_id}: poll loop CANCELLED")
        except Exception as exc:
            _slog(f"{project_id}: poll loop CRASHED — {exc}")
            logger.exception("Scheduler loop crashed for %s", project_id)
        finally:
            sched.enabled = False
            if sched.task:
                sched.task = None
            _slog(f"{project_id}: poll loop EXITED")

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
        sched.poll_count += 1
        sched.last_poll_at = datetime.now(timezone.utc).isoformat()

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

        _slog(
            f"{project_id}: poll #{sched.poll_count} — "
            f"ready={len(ready)} running={len(already_running)} "
            f"dispatchable={len(dispatchable)} slots={free_slots} "
            f"dispatching={len(to_dispatch)}"
            + (f" → {[i.id for i in to_dispatch]}" if to_dispatch else "")
        )

        # Broadcast poll event
        if on_event:
            try:
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
            except Exception:
                pass

        if not to_dispatch:
            return []

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
        sched.dispatch_count += 1
        sched.last_dispatch_at = datetime.now(timezone.utc).isoformat()

        _slog(f"{project_id}: DISPATCHING {issue_id} ({issue.title})")

        # Broadcast start
        if on_event:
            try:
                await on_event({
                    "type": "agent_started",
                    "data": {"issue_id": issue_id, "title": issue.title, "source": "scheduler"},
                })
            except Exception:
                pass

        # Build per-issue event callback that also persists logs
        async def _issue_event(event: dict) -> None:
            if on_event:
                try:
                    await on_event(event)
                except Exception:
                    pass
            evt_type = event.get("type", "")
            evt_issue_id = event.get("issue_id")
            if evt_issue_id and evt_type.startswith("agent_"):
                try:
                    storage.append_run_log(evt_issue_id, f"run-{run_counter:03d}", event)
                except Exception:
                    pass

        try:
            stats = await run_issue_loop(
                issue, storage, workspace,
                on_event=_issue_event,
                cancel_event=cancel_event,
            )
            run_id = f"run-{run_counter:03d}"
            try:
                storage.save_run_stats(issue_id, run_id, stats)
            except Exception:
                pass

            success_str = "PASSED" if stats.get("success") else "NEEDS REVIEW"
            cost = stats.get("cost_usd", 0)
            _slog(f"{project_id}: {issue_id} DONE — {success_str} (${cost:.2f})")

            if on_event:
                try:
                    await on_event({
                        "type": "agent_done",
                        "data": {
                            "issue_id": issue_id,
                            "success": stats["success"],
                            "cost_usd": stats.get("cost_usd", 0),
                            "source": "scheduler",
                        },
                    })
                except Exception:
                    pass

            return stats

        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            sched.last_error = f"dispatch {issue_id}: {err_msg}"
            _slog(f"{project_id}: {issue_id} DISPATCH ERROR — {err_msg}")
            logger.exception("Scheduler dispatch error for %s", issue_id)
            if on_event:
                try:
                    await on_event({
                        "type": "run_error",
                        "data": {"issue_id": issue_id, "error": str(e), "source": "scheduler"},
                    })
                except Exception:
                    pass
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
