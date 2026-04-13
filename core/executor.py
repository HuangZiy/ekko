"""Issue executor — takes one Issue, runs Ralph, returns result.

Does NOT manage state transitions. That's the scheduler's job.
"""

from __future__ import annotations
import asyncio
import time
from pathlib import Path
from typing import Awaitable, Callable

from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions, ResultMessage,
    AssistantMessage, SystemMessage, TextBlock, ToolUseBlock, ToolResultBlock,
    query,
)
from claude_agent_sdk.types import StreamEvent
from config import MODEL, MAX_TURNS_PER_LOOP, MAX_BUDGET_PER_LOOP
from core.models import Issue
from core.storage import ProjectStorage


C_RESET = "\033[0m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_DIM = "\033[2m"


def _log(prefix: str, color: str, msg: str) -> None:
    try:
        from harness import _tee
        _tee(f"{color}[{prefix}]{C_RESET} {msg}")
    except ImportError:
        print(f"[{prefix}] {msg}", flush=True)


def _log_message(message) -> None:
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                text = block.text[:300] + "..." if len(block.text) > 300 else block.text
                _log("Ralph", C_CYAN, text)
            elif isinstance(block, ToolUseBlock):
                inp = str(block.input)[:120]
                _log("Tool", C_YELLOW, f"{block.name}({inp})")
    elif isinstance(message, ResultMessage):
        cost = f"${message.total_cost_usd:.2f}" if message.total_cost_usd else "?"
        _log("Done", C_GREEN, f"turns={message.num_turns} cost={cost} duration={message.duration_ms // 1000}s")
        if message.is_error:
            _log("Done", C_RED, f"ERROR: {message.result}")


def _message_to_events(issue_id: str, message) -> list[dict]:
    """Convert a SDK message to a list of WebSocket event dicts."""
    ts = int(time.time())
    events: list[dict] = []

    if isinstance(message, StreamEvent):
        evt = message.event
        evt_type = evt.get("type", "")
        if evt_type == "content_block_delta":
            delta = evt.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                if text:
                    events.append({
                        "ts": ts, "type": "agent_token", "issue_id": issue_id,
                        "data": {"text": text},
                    })
            elif delta.get("type") == "input_json_delta":
                # Partial tool input — skip to avoid noise
                pass
        elif evt_type == "content_block_start":
            cb = evt.get("content_block", {})
            if cb.get("type") == "tool_use":
                events.append({
                    "ts": ts, "type": "agent_tool_call", "issue_id": issue_id,
                    "data": {"tool": cb.get("name", ""), "input": cb.get("input", {})},
                })
    elif isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                events.append({
                    "ts": ts, "type": "agent_token", "issue_id": issue_id,
                    "data": {"text": block.text},
                })
            elif isinstance(block, ToolUseBlock):
                events.append({
                    "ts": ts, "type": "agent_tool_call", "issue_id": issue_id,
                    "data": {"tool": block.name, "input": block.input},
                })
    elif isinstance(message, ResultMessage):
        status = "failed" if message.is_error else "done"
        data: dict = {"status": status}
        if message.is_error:
            data["error"] = message.result
        if message.total_cost_usd:
            data["cost_usd"] = message.total_cost_usd
        if message.duration_ms:
            data["duration_ms"] = message.duration_ms
        if message.num_turns:
            data["num_turns"] = message.num_turns
        if message.usage:
            data["usage"] = message.usage
        events.append({
            "ts": ts, "type": "agent_status", "issue_id": issue_id,
            "data": data,
        })

    return events


def build_issue_prompt(issue: Issue, storage: ProjectStorage, workspace: Path) -> str:
    """Build Ralph prompt from Issue content + project context."""
    try:
        content = storage.load_issue_content(issue.id)
    except FileNotFoundError:
        content = ""

    plan = storage.load_issue_plan(issue.id)
    plan_path = storage.issues_dir / issue.id / "plan.md"

    agent_md_path = workspace / "AGENT.md"
    agent_md = agent_md_path.read_text() if agent_md_path.exists() else ""

    specs_content = ""
    for specs_dir in [workspace / ".harness" / "specs", storage.root / "specs"]:
        if specs_dir.exists():
            for f in sorted(specs_dir.glob("*.md")):
                specs_content += f"\n\n### {f.name}\n{f.read_text()}"

    base_prompt = ""
    ralph_prompt_path = Path("prompts") / "ralph_prompt.md"
    if ralph_prompt_path.exists():
        base_prompt = ralph_prompt_path.read_text()

    return f"""{base_prompt}

## 任务: {issue.title}

ID: {issue.id}
优先级: {issue.priority.value}
标签: {', '.join(issue.labels) if issue.labels else '无'}

## 任务详情

{content if content else '（无详细描述，请根据标题完成任务）'}

## 执行计划 (plan.md)
路径: {plan_path}

{plan if plan else '（尚无计划，请先制定计划再实现）'}

如需更新计划，直接 Write/Edit 上述路径。

## 项目构建指南 (AGENT.md)
{agent_md}

## 功能规格 (specs/)
{specs_content}

## 本轮任务（只做这一项，不要做其他任务）

请只实现上面这一项任务。完成后 git commit，然后停止。
"""


async def execute_issue(
    issue: Issue,
    storage: ProjectStorage,
    workspace: Path,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
    cancel_event: asyncio.Event | None = None,
) -> dict:
    """Execute a single Issue via Ralph. Returns stats dict.

    Uses query() for streaming messages. Cancel is checked between messages.
    """
    _log("Task", C_CYAN, f"{issue.id}: {issue.title}")

    prompt = build_issue_prompt(issue, storage, workspace)
    stats: dict = {"success": False, "issue_id": issue.id, "title": issue.title}

    # Emit thinking status
    if on_event:
        await on_event({
            "ts": int(time.time()), "type": "agent_status", "issue_id": issue.id,
            "data": {"status": "thinking"},
        })

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            model=MODEL,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent"],
            cwd=str(workspace),
            max_turns=MAX_TURNS_PER_LOOP,
            max_budget_usd=MAX_BUDGET_PER_LOOP,
            permission_mode="bypassPermissions",
        ),
    ):
        _log_message(message)

        if on_event:
            for event in _message_to_events(issue.id, message):
                await on_event(event)

        if isinstance(message, ResultMessage):
            stats.update({
                "success": not message.is_error,
                "cost_usd": message.total_cost_usd or 0,
                "duration_ms": message.duration_ms,
                "num_turns": message.num_turns,
                "usage": message.usage or {},
            })

        # Check cancellation between messages
        if cancel_event and cancel_event.is_set():
            _log("Cancel", C_YELLOW, f"{issue.id}: cancelled by user")
            stats["cancelled"] = True
            if on_event:
                await on_event({
                    "ts": int(time.time()), "type": "agent_status", "issue_id": issue.id,
                    "data": {"status": "cancelled"},
                })
            break

    return stats
