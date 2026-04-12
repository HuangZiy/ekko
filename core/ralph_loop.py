"""Ralph Loop — Issue-based execution loop.

Takes one Issue, runs Generator + Evaluator in a loop until the Issue passes.
Harness owns all state transitions. Generator only writes code. Evaluator only verifies.

Flow:
  harness: Issue → In Progress
  loop:
    Generator (Ralph): write code + build + commit
    Evaluator: verify THIS Issue only
      - passed → break
      - failed → continue loop (Generator fixes)
      - found other problems → create new Issues on the board
  harness: collect evidence → Issue → Agent Done
"""

from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from core.models import Issue, IssueStatus, Board
from core.storage import ProjectStorage
from core.evidence import collect_evidence


C_RESET = "\033[0m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"


def _log(prefix: str, color: str, msg: str) -> None:
    try:
        from harness import _tee
        _tee(f"{color}[{prefix}]{C_RESET} {msg}")
    except ImportError:
        print(f"[{prefix}] {msg}", flush=True)


async def run_issue_loop(
    issue: Issue,
    storage: ProjectStorage,
    workspace: Path,
    max_retries: int = 3,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
) -> dict:
    """Ralph Loop for a single Issue.

    Returns stats dict with success, cost, duration, etc.
    on_event: optional async callback for streaming events to WebSocket.
    """
    all_stats: list[dict] = []

    # === 1. State: → In Progress ===
    if issue.status == IssueStatus.BACKLOG:
        issue.move_to(IssueStatus.TODO)
        storage.save_issue(issue)
    if issue.status == IssueStatus.REJECTED:
        issue.move_to(IssueStatus.TODO)
        storage.save_issue(issue)
    if issue.status in (IssueStatus.TODO, IssueStatus.FAILED):
        issue.move_to(IssueStatus.IN_PROGRESS)
        storage.save_issue(issue)
        _log("State", C_CYAN, f"{issue.id}: → in_progress")
        await _sync_board(issue, storage, on_event)

    # === 2. Generator + Evaluator Loop ===
    passed = False
    for attempt in range(1, max_retries + 1):
        _log("Loop", C_CYAN, f"{issue.id} attempt #{attempt}/{max_retries}")

        # --- Generator: Ralph writes code ---
        _log("Generator", C_CYAN, f"Starting: {issue.title}")
        gen_stats = await _run_generator(issue, storage, workspace, on_event)
        all_stats.append({"phase": "generator", "attempt": attempt, **gen_stats})

        if not gen_stats.get("success"):
            _log("Generator", C_RED, f"Generator failed on attempt #{attempt}")
            _append_log(issue, storage, "Generator Failed", f"Attempt #{attempt}")
            continue

        # --- Evaluator: verify THIS Issue only ---
        _log("Evaluator", C_MAGENTA, f"Verifying: {issue.title}")
        eval_result = await _run_evaluator(issue, storage, workspace)
        all_stats.append({"phase": "evaluator", "attempt": attempt, **eval_result.get("stats", {})})

        if eval_result["passed"]:
            _log("Evaluator", C_GREEN, f"Issue {issue.id} PASSED")
            passed = True
            break

        # Evaluator found problems with current Issue → continue loop
        _log("Evaluator", C_YELLOW, f"Issue {issue.id} not passed, feedback appended")
        _append_log(issue, storage, f"Eval Feedback (attempt #{attempt})", eval_result.get("feedback", ""))

        # Evaluator found OTHER problems → create new Issues
        for new_title in eval_result.get("new_issues", []):
            _create_side_issue(new_title, storage)

    # === 3. Collect evidence ===
    _log("Evidence", C_CYAN, f"Collecting evidence for {issue.id}")
    collect_evidence(issue.id, storage, workspace, run_build=True)

    # === 4. State: → Agent Done ===
    issue = storage.load_issue(issue.id)
    if issue.status == IssueStatus.IN_PROGRESS:
        issue.move_to(IssueStatus.AGENT_DONE)
        storage.save_issue(issue)
        await _sync_board(issue, storage, on_event)
        if passed:
            _log("State", C_GREEN, f"{issue.id}: → agent_done (PASSED, awaiting human review)")
        else:
            _log("State", C_YELLOW, f"{issue.id}: → agent_done (max retries, needs human review)")

    # Aggregate stats
    total_cost = sum(s.get("cost_usd", 0) for s in all_stats)
    total_duration = sum(s.get("duration_ms", 0) for s in all_stats)
    return {
        "success": passed,
        "issue_id": issue.id,
        "title": issue.title,
        "attempts": len([s for s in all_stats if s["phase"] == "generator"]),
        "cost_usd": total_cost,
        "duration_ms": total_duration,
        "details": all_stats,
    }


# ---------------------------------------------------------------------------
# Generator (Ralph)
# ---------------------------------------------------------------------------

async def _run_generator(
    issue: Issue,
    storage: ProjectStorage,
    workspace: Path,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
) -> dict:
    """Call Ralph to implement the Issue. Returns stats dict."""
    from core.executor import execute_issue
    return await execute_issue(issue, storage, workspace, on_event=on_event)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

async def _run_evaluator(issue: Issue, storage: ProjectStorage, workspace: Path) -> dict:
    """Run Evaluator to verify THIS Issue. Returns {passed, feedback, new_issues, stats}."""
    from agents.evaluator import run_issue_eval

    try:
        content = storage.load_issue_content(issue.id)
    except FileNotFoundError:
        content = ""

    screenshots_dir = storage.root / "runs" / issue.id / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        report, stats = await run_issue_eval(
            issue_id=issue.id,
            issue_title=issue.title,
            issue_content=content,
            screenshots_dir=screenshots_dir,
        )
    except Exception as e:
        _log("Evaluator", C_RED, f"Eval error: {e}")
        return {"passed": True, "feedback": "", "new_issues": [], "stats": {}}

    passed = True
    feedback_lines = []
    new_issues = []

    if report:
        for line in report.splitlines():
            stripped = line.strip()
            if stripped.startswith("- [FAIL]"):
                passed = False
                feedback_lines.append(stripped)
            elif stripped.startswith("- [NEW_ISSUE]"):
                title = stripped.removeprefix("- [NEW_ISSUE]").strip()
                if title:
                    new_issues.append(title)

    return {
        "passed": passed,
        "feedback": "\n".join(feedback_lines),
        "new_issues": new_issues,
        "stats": stats,
        "report": report,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_side_issue(title: str, storage: ProjectStorage) -> None:
    """Create a new Issue from Evaluator findings and add to board."""
    project = storage.load_project_meta()
    prefix = project.key if project else "ISS"
    issue_id = storage.next_issue_id(prefix)
    new_issue = Issue.create(id=issue_id, title=title, labels=["eval-finding"])
    new_issue.move_to(IssueStatus.TODO)
    storage.save_issue(new_issue)

    # Add to board
    board_file = storage.root / "board.json"
    if board_file.exists():
        data = json.loads(board_file.read_text())
        for col in data["columns"]:
            if col["id"] == "todo":
                col["issues"].append(new_issue.id)
                break
        board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    _log("NewIssue", C_CYAN, f"Created {new_issue.id}: {title}")


def _append_log(issue: Issue, storage: ProjectStorage, title: str, content: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        existing = storage.load_issue_content(issue.id)
    except FileNotFoundError:
        existing = ""
    entry = f"\n\n## {title} ({now})\n\n{content}\n"
    storage.save_issue_content(issue.id, existing + entry)


async def _sync_board(
    issue: Issue,
    storage: ProjectStorage,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
) -> None:
    board_file = storage.root / "board.json"
    if not board_file.exists():
        return
    data = json.loads(board_file.read_text())
    for col in data["columns"]:
        if issue.id in col["issues"]:
            col["issues"].remove(issue.id)
    status_to_col = {
        "backlog": "backlog", "todo": "todo", "in_progress": "in_progress",
        "agent_done": "agent_done", "rejected": "rejected", "human_done": "human_done",
    }
    target = status_to_col.get(issue.status.value)
    if target:
        for col in data["columns"]:
            if col["id"] == target:
                col["issues"].append(issue.id)
                break
    board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    if on_event:
        await on_event({"type": "issue_updated", "data": {"issue": issue.to_json()}})


# ---------------------------------------------------------------------------
# Board-level runner
# ---------------------------------------------------------------------------

def find_ready_issues(storage: ProjectStorage) -> list[Issue]:
    """Find issues that are TODO and have no unresolved blockers."""
    all_issues = storage.list_issues()
    done_ids = {i.id for i in all_issues if i.status == IssueStatus.HUMAN_DONE}
    return [
        i for i in all_issues
        if i.status == IssueStatus.TODO
        and all(b in done_ids for b in i.blocked_by)
    ]


async def run_board(
    storage: ProjectStorage,
    workspace: Path,
    max_parallel: int = 1,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
) -> list[dict]:
    """Run all ready issues. Supports parallel execution when max_parallel > 1."""
    all_stats = []
    ready = find_ready_issues(storage)

    if not ready:
        _log("Board", C_GREEN, "No actionable issues.")
        return all_stats

    _log("Board", C_CYAN, f"{len(ready)} ready issues (max_parallel={max_parallel})")

    if max_parallel <= 1:
        # Sequential
        for issue in ready:
            stats = await run_issue_loop(issue, storage, workspace, on_event=on_event)
            all_stats.append(stats)
            status = "PASSED" if stats["success"] else "NEEDS REVIEW"
            _log("Board", C_GREEN if stats["success"] else C_YELLOW,
                 f"{issue.id}: {status} (${stats['cost_usd']:.2f}, {stats['attempts']} attempts)")
    else:
        # Parallel with semaphore
        semaphore = asyncio.Semaphore(max_parallel)

        async def _run_one(issue: Issue) -> dict:
            async with semaphore:
                return await run_issue_loop(issue, storage, workspace, on_event=on_event)

        tasks = [asyncio.create_task(_run_one(issue)) for issue in ready]
        for coro in asyncio.as_completed(tasks):
            stats = await coro
            all_stats.append(stats)
            status = "PASSED" if stats["success"] else "NEEDS REVIEW"
            _log("Board", C_GREEN if stats["success"] else C_YELLOW,
                 f"{stats['issue_id']}: {status} (${stats['cost_usd']:.2f}, {stats['attempts']} attempts)")

    return all_stats
