"""Ekko — Unified loop orchestrator with task isolation and resume.

Each harness run creates an isolated task under artifacts/tasks/<task_id>/ with:
  - state.json     — resumable checkpoint
  - fix_plan.md    — task-specific TODO list (copied to workspace during run)
  - eval_*.md      — evaluation reports
  - screenshots/   — Playwright screenshots
  - stats.json     — final cost/token statistics
  - summary.txt    — human-readable summary

On startup, if interrupted tasks exist, the user chooses: resume / new / quit.
"""

import json
import re
import sys
import time
import hashlib
import io
from datetime import datetime
from pathlib import Path

import anyio

from agents.planner import run_planner
from agents.ralph_loop import run_one_ralph_cycle, has_remaining_work
from agents.evaluator import run_incremental_eval, run_full_eval
from config import WORKSPACE_DIR, ARTIFACTS_DIR, TASKS_DIR, MAX_RALPH_LOOPS, EVAL_PASS_THRESHOLD


# ANSI colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_CYAN = "\033[36m"
C_RED = "\033[31m"
C_DIM = "\033[2m"

# Strip ANSI codes for log file
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

# Global log file handle — set per task
_log_file: io.TextIOWrapper | None = None


def _tee(msg: str) -> None:
    """Print to terminal AND append to log file."""
    print(msg, flush=True)  # _tee internal
    if _log_file:
        _log_file.write(_ANSI_RE.sub("", msg) + "\n")
        _log_file.flush()


# ---------------------------------------------------------------------------
# Task directory management
# ---------------------------------------------------------------------------

def _generate_task_id(prompt: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_hash = hashlib.md5(prompt.encode()).hexdigest()[:6]
    return f"{ts}_{short_hash}"


def _get_task_dir(task_id: str) -> Path:
    return TASKS_DIR / task_id


def _find_interrupted_tasks() -> list[dict]:
    """Find all tasks with state.json that are not completed."""
    interrupted = []
    if not TASKS_DIR.exists():
        return interrupted
    for task_dir in sorted(TASKS_DIR.iterdir(), reverse=True):
        state_file = task_dir / "state.json"
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                if state.get("status") != "completed":
                    interrupted.append(state)
            except (json.JSONDecodeError, KeyError):
                pass
    return interrupted


def _summarize_task(task: dict) -> str:
    """Generate a short summary from task state — check fix_plan for actual work."""
    task_dir = _get_task_dir(task["task_id"])
    fix_plan = task_dir / "fix_plan.md"
    if fix_plan.exists():
        content = fix_plan.read_text()
        done = content.count("- [x]")
        todo = content.count("- [ ]")
        # Extract first few task descriptions for context
        tasks = []
        for line in content.splitlines():
            if "- [x]" in line or "- [ ]" in line:
                desc = line.strip().removeprefix("- [x]").removeprefix("- [ ]").strip()
                if desc and len(tasks) < 3:
                    tasks.append(desc[:40])
        summary = f"{done} done / {todo} todo"
        if tasks:
            summary += f" | {'; '.join(tasks)}"
        return summary
    return task.get("user_prompt", "")[:50]


def _prompt_task_selection(interrupted: list[dict]) -> str | None:
    """Ask user to choose: resume an interrupted task, start new, or quit."""
    _tee(f"\n{C_BOLD}Found interrupted task(s):{C_RESET}\n")
    for i, task in enumerate(interrupted):
        task_id = task["task_id"]
        phase = task["phase"]
        cycle = task["loop_count"]
        step = task.get("step", "ralph")
        ts = datetime.fromtimestamp(task["timestamp"]).strftime("%Y-%m-%d %H:%M")
        summary = _summarize_task(task)
        _tee(f"  {C_GREEN}{i + 1}.{C_RESET} [{task_id}]")
        _tee(f"     {C_CYAN}{summary}{C_RESET}")
        _tee(f"     phase={phase} step={step} cycle=#{cycle} last={ts}")

    _tee(f"\n  {C_GREEN}N.{C_RESET} Start a new task")
    _tee(f"  {C_GREEN}Q.{C_RESET} Quit")

    choice = input(f"\n  {C_YELLOW}>{C_RESET} ").strip().upper()

    if choice == "Q":
        return "__quit__"
    if choice == "N":
        return None  # new task
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(interrupted):
            return interrupted[idx]["task_id"]
    return None


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def _save_state(task_dir: Path, task_id: str, phase: str, loop_count: int,
                cycle_stats: list[dict], user_prompt: str, harness_start: float,
                planner_session_id: str | None = None, step: str = "ralph") -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "task_id": task_id,
        "status": "running",
        "phase": phase,
        "step": step,  # "ralph" or "eval" within a cycle
        "loop_count": loop_count,
        "cycle_stats": cycle_stats,
        "user_prompt": user_prompt,
        "harness_start": harness_start,
        "timestamp": time.time(),
    }
    if planner_session_id:
        state["planner_session_id"] = planner_session_id
    (task_dir / "state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _mark_completed(task_dir: Path) -> None:
    state_file = task_dir / "state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        state["status"] = "completed"
        state["timestamp"] = time.time()
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _load_state(task_dir: Path) -> dict | None:
    state_file = task_dir / "state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except (json.JSONDecodeError, KeyError):
            return None
    return None


# ---------------------------------------------------------------------------
# fix_plan sync: task_dir/fix_plan.md <-> workspace/fix_plan.md
# ---------------------------------------------------------------------------

def _sync_fix_plan_to_workspace(task_dir: Path) -> None:
    """Copy task's fix_plan.md to workspace for Ralph to work on."""
    src = task_dir / "fix_plan.md"
    dst = WORKSPACE_DIR / "fix_plan.md"
    if src.exists():
        dst.write_text(src.read_text())


def _sync_fix_plan_from_workspace(task_dir: Path) -> None:
    """Copy workspace fix_plan.md back to task dir after Ralph modifies it."""
    src = WORKSPACE_DIR / "fix_plan.md"
    dst = task_dir / "fix_plan.md"
    if src.exists():
        dst.write_text(src.read_text())


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

def save_task_artifact(task_dir: Path, name: str, content: str) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / name).write_text(content)


# ---------------------------------------------------------------------------
# Eval feedback
# ---------------------------------------------------------------------------

def all_criteria_pass(report: str) -> bool:
    scores = re.findall(r"(\d+)/10", report)
    if not scores:
        return False
    return all(int(s) >= EVAL_PASS_THRESHOLD for s in scores)


def append_eval_feedback_to_fix_plan(report: str) -> None:
    """Extract FAIL items from evaluator report and append as new tasks. Keep all history."""
    fix_plan = WORKSPACE_DIR / "fix_plan.md"
    current = fix_plan.read_text() if fix_plan.exists() else "# 任务计划\n"
    fail_items = []
    for line in report.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [FAIL]"):
            desc = stripped.removeprefix("- [FAIL]").strip()
            fail_items.append(f"- [ ] {desc}")
    if fail_items:
        fix_plan.write_text(current + "\n" + "\n".join(fail_items) + "\n")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _fmt_duration(ms: int) -> str:
    s = ms // 1000
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s}s"
    h, m = divmod(m, 60)
    return f"{h}h{m}m{s}s"


def _print_summary(task_dir: Path, cycle_stats: list[dict], harness_start: float) -> None:
    total_cost = 0.0
    total_duration = 0
    total_input = 0
    total_output = 0

    lines = []
    lines.append("")
    lines.append(f"{C_BOLD}{'='*80}{C_RESET}")
    lines.append(f"{C_BOLD}  Harness Summary{C_RESET}")
    lines.append(f"{C_BOLD}{'='*80}{C_RESET}")
    lines.append("")
    lines.append(f"  {'Cycle':<8} {'Phase':<12} {'Task':<40} {'Cost':>8} {'Duration':>10} {'Turns':>6} {'Tokens':>20}")
    lines.append(f"  {'─'*8} {'─'*12} {'─'*40} {'─'*8} {'─'*10} {'─'*6} {'─'*20}")

    for entry in cycle_stats:
        cycle = entry["cycle"]
        phase = entry["phase"]
        task = entry.get("task", "—")
        if task and len(task) > 38:
            task = task[:35] + "..."
        cost = entry.get("cost_usd", 0)
        duration = entry.get("duration_ms", 0)
        turns = entry.get("num_turns", 0)
        usage = entry.get("usage", {})
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)

        total_cost += cost
        total_duration += duration
        total_input += inp
        total_output += out

        color = C_CYAN if phase == "Ralph" else C_YELLOW
        lines.append(
            f"  {color}#{cycle:<7}{C_RESET} {phase:<12} {task:<40} "
            f"${cost:>7.2f} {_fmt_duration(duration):>10} {turns:>6} {f'in={inp:,} out={out:,}':>20}"
        )

    lines.append(f"  {'─'*8} {'─'*12} {'─'*40} {'─'*8} {'─'*10} {'─'*6} {'─'*20}")

    wall_time = time.time() - harness_start
    lines.append("")
    lines.append(f"  {C_BOLD}Total cost:{C_RESET}     ${total_cost:.2f}")
    lines.append(f"  {C_BOLD}Total API time:{C_RESET} {_fmt_duration(total_duration)}")
    lines.append(f"  {C_BOLD}Wall time:{C_RESET}      {_fmt_duration(int(wall_time * 1000))}")
    lines.append(f"  {C_BOLD}Total tokens:{C_RESET}   in={total_input:,}  out={total_output:,}")
    lines.append(f"  {C_BOLD}Cycles:{C_RESET}         {len([e for e in cycle_stats if e['phase'] == 'Ralph'])}")
    lines.append("")

    summary_text = "\n".join(lines)
    _tee(summary_text)

    plain = re.sub(r"\033\[[0-9;]*m", "", summary_text)
    save_task_artifact(task_dir, "summary.txt", plain)
    save_task_artifact(task_dir, "stats.json", json.dumps({
        "cycles": cycle_stats,
        "totals": {
            "cost_usd": round(total_cost, 2),
            "api_duration_ms": total_duration,
            "wall_time_ms": int(wall_time * 1000),
            "input_tokens": total_input,
            "output_tokens": total_output,
            "num_cycles": len([e for e in cycle_stats if e["phase"] == "Ralph"]),
        }
    }, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# README generation
# ---------------------------------------------------------------------------

async def _generate_readme() -> None:
    from agents.ralph_loop import _log, C_CYAN as RC, _log_message
    from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage
    from config import MODEL

    _log("README", RC, "Generating README.md for the blog project...")

    specs_content = ""
    specs_dir = WORKSPACE_DIR / "specs"
    if specs_dir.exists():
        for spec_file in sorted(specs_dir.glob("*.md")):
            specs_content += f"\n\n### {spec_file.name}\n{spec_file.read_text()}"

    agent_md = (WORKSPACE_DIR / "AGENT.md").read_text() if (WORKSPACE_DIR / "AGENT.md").exists() else ""

    prompt = f"""为当前 Blog 项目编写一份 README.md，保存到项目根目录。

要求：
- 项目名称和一句话描述
- 技术栈列表（从 package.json 和源码中提取实际使用的技术）
- 功能特性列表（从 specs 和实际代码中总结）
- 快速开始（安装、开发、构建命令）
- 项目结构概览（主要目录和文件的用途）
- 内容写作指南（如何添加新文章，frontmatter 格式）
- 致谢（Pretext 等核心依赖）

先阅读项目的 package.json、目录结构和关键源码，确保 README 内容准确反映实际实现。
不要编造不存在的功能。用中文撰写。

## 项目构建指南 (AGENT.md)
{agent_md}

## 功能规格 (specs/)
{specs_content}
"""

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            model=MODEL,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
            cwd=str(WORKSPACE_DIR),
            max_turns=30,
            permission_mode="bypassPermissions",
        ),
    ):
        _log_message(message)
        if isinstance(message, ResultMessage):
            cost = f"${message.total_cost_usd:.2f}" if message.total_cost_usd else "?"
            _log("README", RC, f"Done. cost={cost} duration={message.duration_ms // 1000}s")


# ---------------------------------------------------------------------------
# Main harness
# ---------------------------------------------------------------------------

async def run_harness(user_prompt: str) -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)

    # Check for interrupted tasks
    interrupted = _find_interrupted_tasks()
    task_id = None
    task_dir = None
    phase = "planner"
    loop_count = 0
    cycle_stats: list[dict] = []
    harness_start = time.time()
    resume_step = "ralph"  # within a cycle: "ralph" or "eval"

    if interrupted:
        choice = _prompt_task_selection(interrupted)
        if choice == "__quit__":
            _tee("Bye.")
            return
        if choice is not None:
            # Resume existing task
            task_id = choice
            task_dir = _get_task_dir(task_id)
            saved = _load_state(task_dir)
            if saved:
                phase = saved["phase"]
                loop_count = saved["loop_count"]
                cycle_stats = saved["cycle_stats"]
                harness_start = saved["harness_start"]
                resume_step = saved.get("step", "ralph")
                _sync_fix_plan_to_workspace(task_dir)
                _tee(f"\n{C_CYAN}Resuming task {task_id}: phase={phase}, cycle=#{loop_count}, step={resume_step}{C_RESET}")

    # New task
    if task_id is None:
        task_id = _generate_task_id(user_prompt)
        task_dir = _get_task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        _tee(f"\n{C_CYAN}New task: {task_id}{C_RESET}")

    # Open log file for this task
    global _log_file
    _log_file = open(task_dir / "harness.log", "a", encoding="utf-8")
    _log_file.write(f"\n{'='*60}\nHarness started: {datetime.now().isoformat()}\nPrompt: {user_prompt}\nTask: {task_id}\n{'='*60}\n")
    _log_file.flush()

    try:
        # Phase 1: Planner
        if phase == "planner":
            _tee("=" * 60)
            _tee("Phase 1: Planning")
            _tee("=" * 60)
            _save_state(task_dir, task_id, "planner", 0, cycle_stats, user_prompt, harness_start)

            # Check if we have a saved planner session to resume
            saved_state = _load_state(task_dir)
            planner_session = saved_state.get("planner_session_id") if saved_state else None

            result, session_id = await run_planner(user_prompt, resume_session_id=planner_session)

            # Save planner session_id for potential resume
            if session_id:
                _save_state(task_dir, task_id, "planner", 0, cycle_stats, user_prompt, harness_start, planner_session_id=session_id)

            if result:
                save_task_artifact(task_dir, "planner_output.md", result)

            fix_plan = WORKSPACE_DIR / "fix_plan.md"
            if not fix_plan.exists() or "- [ ]" not in fix_plan.read_text():
                _tee("WARNING: Planner did not create fix_plan.md with tasks. Aborting.")
                return

            _sync_fix_plan_from_workspace(task_dir)
            phase = "loop"

        # Phase 2: Migrate fix_plan → Issues, then run Issue-based Ralph Loop
        if phase == "loop":
            _tee("=" * 60)
            _tee("Phase 2: Issue-based Ralph Loop")
            _tee("=" * 60)

            # Migrate fix_plan.md to Issues
            fix_plan = WORKSPACE_DIR / "fix_plan.md"
            if fix_plan.exists() and "- [ ]" in fix_plan.read_text():
                from core.migrate import migrate_fix_plan
                from core.storage import PlatformStorage
                platform = PlatformStorage(ARTIFACTS_DIR)
                active_id = platform.get_active_project_id()
                if not active_id:
                    # Create a default project
                    project, store = platform.create_project(name=user_prompt[:30], workspace_path=str(WORKSPACE_DIR))
                    active_id = project.id
                    _tee(f"  Created project {active_id}")
                store = platform.get_project_storage(active_id)
                issues = migrate_fix_plan(fix_plan, store)
                _tee(f"  Migrated {len(issues)} issues from fix_plan.md")

            # Run all ready issues via Issue-based Ralph Loop
            from core.ralph_loop import run_board
            from core.storage import PlatformStorage
            platform = PlatformStorage(ARTIFACTS_DIR)
            active_id = platform.get_active_project_id()
            if active_id:
                store = platform.get_project_storage(active_id)
                all_stats = await run_board(store, WORKSPACE_DIR)
                for s in all_stats:
                    cycle_stats.append({
                        "cycle": loop_count,
                        "phase": "Ralph",
                        "task": s.get("title", "—"),
                        "cost_usd": s.get("cost_usd", 0),
                        "duration_ms": s.get("duration_ms", 0),
                        "num_turns": s.get("attempts", 0),
                        "usage": {},
                    })
                    loop_count += 1

            phase = "readme"

        # Summary
        _print_summary(task_dir, cycle_stats, harness_start)

        # Phase 3: README
        if phase == "readme":
            _tee("=" * 60)
            _tee("Phase 3: Generate README")
            _tee("=" * 60)
            _save_state(task_dir, task_id, "readme", loop_count, cycle_stats, user_prompt, harness_start)
            await _generate_readme()

        _mark_completed(task_dir)
        _sync_fix_plan_from_workspace(task_dir)
        _tee(f"\n{C_GREEN}Harness complete. Task: {task_id}{C_RESET}")

    finally:
        if _log_file:
            _log_file.close()
            _log_file = None


_CLI_SUBCOMMANDS = {"issue", "review", "project", "board", "plan", "plan-issue", "run", "serve"}

if __name__ == "__main__":
    # Delegate to new CLI if a known subcommand is used
    if len(sys.argv) > 1 and sys.argv[1] in _CLI_SUBCOMMANDS:
        from cli.main import main as cli_main
        cli_main(sys.argv[1:])
    else:
        prompt = sys.argv[1] if len(sys.argv) > 1 else "创建一个极简风格的技术博客"
        anyio.run(run_harness, prompt)
