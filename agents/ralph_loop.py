import re
import sys
from pathlib import Path

from claude_agent_sdk import (
    query, ClaudeAgentOptions, ResultMessage,
    AssistantMessage, SystemMessage, TextBlock, ToolUseBlock, ToolResultBlock,
)
from config import MODEL, WORKSPACE_DIR, MAX_TURNS_PER_LOOP, MAX_BUDGET_PER_LOOP


PROMPTS_DIR = Path("prompts")

# ANSI colors for log readability
C_RESET = "\033[0m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_DIM = "\033[2m"


def _log(prefix: str, color: str, msg: str) -> None:
    from harness import _tee
    _tee(f"{color}[{prefix}]{C_RESET} {msg}")


def _read_workspace_file(name: str) -> str:
    p = WORKSPACE_DIR / name
    return p.read_text() if p.exists() else ""


def has_remaining_work() -> bool:
    """Check if fix_plan.md still has unchecked items."""
    content = _read_workspace_file("fix_plan.md")
    return "- [ ]" in content


def _extract_next_task() -> str | None:
    """Extract the first unchecked task from fix_plan.md."""
    content = _read_workspace_file("fix_plan.md")
    for line in content.splitlines():
        if re.match(r"^\s*- \[ \]", line):
            return line.strip()
    return None


def _read_pending_tasks() -> str:
    """Read only pending tasks from fix_plan.md (strip completed items and old headers)."""
    content = _read_workspace_file("fix_plan.md")
    pending = []
    for line in content.splitlines():
        if re.match(r"^\s*- \[ \]", line):
            pending.append(line)
    return "\n".join(pending) if pending else ""


def build_ralph_prompt() -> str:
    """Assemble the prompt for one Ralph cycle.

    Key Ralph principles:
    - Deterministically allocate the same stack every loop (specs + fix_plan + AGENT.md)
    - Only ONE task per cycle
    - fix_plan only shows pending tasks (completed items stripped to save context)
    """
    base_prompt = (PROMPTS_DIR / "ralph_prompt.md").read_text()

    next_task = _extract_next_task()
    if not next_task:
        return ""

    # Collect all specs
    specs_content = ""
    specs_dir = WORKSPACE_DIR / ".harness" / "specs"
    if specs_dir.exists():
        for spec_file in sorted(specs_dir.glob("*.md")):
            specs_content += f"\n\n### {spec_file.name}\n{spec_file.read_text()}"

    pending_tasks = _read_pending_tasks()
    agent_md = _read_workspace_file("AGENT.md")

    return f"""{base_prompt}

## 项目构建指南 (AGENT.md)
{agent_md}

## 待办任务 (fix_plan.md — 仅剩余项)
{pending_tasks}

## 本轮任务（只做这一项，不要做其他任务）

{next_task}

请只实现上面这一项任务。完成后将其标记为 `- [x]`，然后停止。

## 功能规格 (specs/)
{specs_content}
"""


def _log_message(message, agent_name: str = "Ralph") -> None:
    """Log SDK messages in a human-readable format."""
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                # Truncate long text output
                text = block.text
                if len(text) > 300:
                    text = text[:300] + "..."
                _log(agent_name, C_CYAN, text)
            elif isinstance(block, ToolUseBlock):
                # Show tool name + abbreviated input
                inp = str(block.input)
                if len(inp) > 120:
                    inp = inp[:120] + "..."
                _log("Tool", C_YELLOW, f"{block.name}({inp})")
            elif isinstance(block, ToolResultBlock):
                status = "ERROR" if block.is_error else "OK"
                content = str(block.content or "")
                if len(content) > 200:
                    content = content[:200] + "..."
                _log("Result", C_GREEN if status == "OK" else C_RED, f"[{status}] {content}")
    elif isinstance(message, ResultMessage):
        cost = f"${message.total_cost_usd:.2f}" if message.total_cost_usd else "?"
        _log("Done", C_GREEN, f"turns={message.num_turns} cost={cost} duration={message.duration_ms // 1000}s")
        if message.is_error:
            _log("Done", C_RED, f"ERROR: {message.result}")
    elif isinstance(message, SystemMessage):
        _log("System", C_DIM, f"{message.subtype}: {message.data}")


async def run_one_ralph_cycle() -> dict:
    """Execute a single Ralph cycle for ONE task. Returns stats dict."""
    prompt = build_ralph_prompt()
    if not prompt:
        return {"success": False}

    task = _extract_next_task()
    _log("Task", C_CYAN, task or "(none)")

    stats = {"success": False, "task": task}
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            model=MODEL,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent"],
            cwd=str(WORKSPACE_DIR),
            max_turns=MAX_TURNS_PER_LOOP,
            max_budget_usd=MAX_BUDGET_PER_LOOP,
            permission_mode="bypassPermissions",
        ),
    ):
        _log_message(message)
        if isinstance(message, ResultMessage):
            stats.update({
                "success": not message.is_error,
                "cost_usd": message.total_cost_usd or 0,
                "duration_ms": message.duration_ms,
                "num_turns": message.num_turns,
                "usage": message.usage or {},
            })

    return stats
