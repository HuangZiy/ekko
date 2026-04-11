from __future__ import annotations
import asyncio
from core.models import Issue, IssueStatus
from core.storage import ProjectStorage


def find_ready_issues(storage: ProjectStorage) -> list[Issue]:
    """Find issues that are TODO and have no unresolved blockers."""
    all_issues = storage.list_issues()
    # Build set of completed issue IDs for blocker resolution
    done_ids = {i.id for i in all_issues if i.status == IssueStatus.HUMAN_DONE}
    ready = []
    for issue in all_issues:
        if issue.status != IssueStatus.TODO:
            continue
        # Check if all blockers are resolved
        unresolved = [b for b in issue.blocked_by if b not in done_ids]
        if not unresolved:
            ready.append(issue)
    return ready


class Scheduler:
    """Runs ready issues in parallel via an executor, respecting concurrency limits."""

    def __init__(self, storage: ProjectStorage, executor, max_parallel: int = 3) -> None:
        self.storage = storage
        self.executor = executor
        self.max_parallel = max_parallel

    async def run_batch(self) -> list[dict]:
        """Find ready issues and execute them in parallel. Returns list of stats dicts."""
        ready = find_ready_issues(self.storage)
        if not ready:
            return []

        semaphore = asyncio.Semaphore(self.max_parallel)
        results: list[dict] = []

        async def _run_one(issue: Issue) -> dict:
            async with semaphore:
                issue.move_to(IssueStatus.IN_PROGRESS)
                self.storage.save_issue(issue)
                return await self.executor.run(issue)

        tasks = [asyncio.create_task(_run_one(issue)) for issue in ready]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)

        return results
