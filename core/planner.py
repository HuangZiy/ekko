"""Planning Agent — analyzes an Issue and generates an execution plan.

Runs BEFORE the Generator (Ralph). Reads the codebase, produces a structured
plan.md with checklist items, and optionally splits complex issues into
child issues.

Does NOT modify source code. Only writes plan.md.
"""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Awaitable, Callable

from claude_agent_sdk import (
    query, ClaudeAgentOptions, ResultMessage,
    AssistantMessage, TextBlock, ToolUseBlock,
)
from claude_agent_sdk.types import StreamEvent
from config import MODEL, MAX_PLANNING_TURNS, MAX_PLANNING_BUDGET
from core.models import Issue, IssueStatus
from core.storage import ProjectStorage


PROMPTS_DIR = Path("prompts")

C_RESET = "\033[0m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"
C_BLUE = "\033[34m"


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
                _log("Planner", C_BLUE, text)
            elif isinstance(block, ToolUseBlock):
                inp = str(block.input)[:120]
                _log("Tool", C_YELLOW, f"{block.name}({inp})")
    elif isinstance(message, ResultMessage):
        cost = f"${message.total_cost_usd:.2f}" if message.total_cost_usd else "?"
        _log("Planner", C_GREEN, f"Done. turns={message.num_turns} cost={cost} duration={message.duration_ms // 1000}s")
        if message.is_error:
            _log("Planner", C_RED, f"ERROR: {message.result}")


def _message_to_events(issue_id: str, message) -> list[dict]:
    """Convert a SDK message to WebSocket event dicts for the planning phase."""
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
                        "ts": ts, "type": "planning_token", "issue_id": issue_id,
                        "data": {"text": text},
                    })
    elif isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                events.append({
                    "ts": ts, "type": "planning_token", "issue_id": issue_id,
                    "data": {"text": block.text},
                })
            elif isinstance(block, ToolUseBlock):
                events.append({
                    "ts": ts, "type": "planning_tool_call", "issue_id": issue_id,
                    "data": {"tool": block.name, "input": block.input},
                })
    elif isinstance(message, ResultMessage):
        status = "failed" if message.is_error else "done"
        data: dict = {"status": status, "phase": "planning"}
        if message.total_cost_usd:
            data["cost_usd"] = message.total_cost_usd
        if message.duration_ms:
            data["duration_ms"] = message.duration_ms
        if message.num_turns:
            data["num_turns"] = message.num_turns
        events.append({
            "ts": ts, "type": "planning_status", "issue_id": issue_id,
            "data": data,
        })

    return events


def build_planning_prompt(issue: Issue, storage: ProjectStorage, workspace: Path) -> str:
    """Build the prompt for the Planning Agent."""
    try:
        content = storage.load_issue_content(issue.id)
    except FileNotFoundError:
        content = ""

    existing_plan = storage.load_issue_plan(issue.id)
    plan_path = storage.issues_dir / issue.id / "plan.md"

    agent_md_path = workspace / "AGENT.md"
    agent_md = agent_md_path.read_text() if agent_md_path.exists() else ""

    specs_content = ""
    for specs_dir in [workspace / ".harness" / "specs", storage.root / "specs"]:
        if specs_dir.exists():
            for f in sorted(specs_dir.glob("*.md")):
                specs_content += f"\n\n### {f.name}\n{f.read_text()}"

    # Gather info about child/parent issues for context
    all_issues = storage.list_issues()
    related_context = ""
    if issue.parent_id:
        try:
            parent = storage.load_issue(issue.parent_id)
            parent_content = ""
            try:
                parent_content = storage.load_issue_content(parent.id)
            except FileNotFoundError:
                pass
            related_context += f"\n### 父 Issue: {parent.id} — {parent.title}\n{parent_content}\n"
        except FileNotFoundError:
            pass

    children = [i for i in all_issues if i.parent_id == issue.id]
    if children:
        related_context += "\n### 已有子 Issue:\n"
        for child in children:
            related_context += f"- {child.id}: {child.title} [{child.status.value}]\n"

    return f"""请为以下 Issue 制定执行计划。

## Issue 信息

ID: {issue.id}
标题: {issue.title}
优先级: {issue.priority.value}
标签: {', '.join(issue.labels) if issue.labels else '无'}

## 任务详情

{content if content else '（无详细描述，请根据标题分析）'}

## 已有计划

{existing_plan if existing_plan else '（尚无计划）'}

## 项目构建指南 (AGENT.md)
{agent_md}

## 功能规格 (specs/)
{specs_content}

## 相关 Issue
{related_context if related_context else '（无相关 issue）'}

## 输出要求

1. 探索代码库，理解现有架构
2. 将执行计划写入: {plan_path}
3. 如果任务需要拆分，在输出末尾使用 [SPLIT] 标记

注意：你只能写 plan.md，不能修改任何源码文件。
"""


def parse_split_directives(result_text: str) -> list[dict]:
    """Parse [SPLIT] directives from the planning agent's output.

    Format: [SPLIT] title | description
    Returns list of {title, description} dicts.
    """
    splits: list[dict] = []
    if not result_text:
        return splits

    for line in result_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[SPLIT]"):
            rest = stripped.removeprefix("[SPLIT]").strip()
            if "|" in rest:
                title, desc = rest.split("|", 1)
                splits.append({"title": title.strip(), "description": desc.strip()})
            elif rest:
                splits.append({"title": rest, "description": ""})

    return splits


def parse_plan_appends(result_text: str) -> list[str]:
    """Parse [PLAN_APPEND] directives from evaluator output.

    Format: [PLAN_APPEND] text to append  OR  - [PLAN_APPEND] text to append
    Returns list of text strings to append.
    """
    appends: list[str] = []
    if not result_text:
        return appends

    for line in result_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [PLAN_APPEND]"):
            rest = stripped.removeprefix("- [PLAN_APPEND]").strip()
            if rest:
                appends.append(rest)
        elif stripped.startswith("[PLAN_APPEND]"):
            rest = stripped.removeprefix("[PLAN_APPEND]").strip()
            if rest:
                appends.append(rest)

    return appends


async def run_issue_planning(
    issue: Issue,
    storage: ProjectStorage,
    workspace: Path,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
    cancel_event=None,
) -> dict:
    """Run the Planning Agent for a single Issue.

    Returns stats dict with:
      - success: bool
      - cost_usd: float
      - duration_ms: int
      - split_issues: list of created child issue IDs
      - plan_generated: bool
    """
    _log("Planning", C_BLUE, f"Analyzing: {issue.id} — {issue.title}")

    system_prompt_path = PROMPTS_DIR / "planning_prompt.md"
    system_prompt = system_prompt_path.read_text() if system_prompt_path.exists() else ""

    prompt = build_planning_prompt(issue, storage, workspace)
    plan_path = storage.issues_dir / issue.id / "plan.md"

    stats: dict = {
        "success": False,
        "issue_id": issue.id,
        "cost_usd": 0,
        "duration_ms": 0,
        "split_issues": [],
        "plan_generated": False,
    }

    if on_event:
        await on_event({
            "ts": int(time.time()), "type": "planning_status", "issue_id": issue.id,
            "data": {"status": "thinking", "phase": "planning"},
        })

    result_text = ""

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            model=MODEL,
            system_prompt=system_prompt,
            allowed_tools=["Read", "Write", "Glob", "Grep", "Bash"],
            cwd=str(workspace),
            max_turns=MAX_PLANNING_TURNS,
            max_budget_usd=MAX_PLANNING_BUDGET,
            permission_mode="bypassPermissions",
        ),
    ):
        _log_message(message)

        if on_event:
            for event in _message_to_events(issue.id, message):
                await on_event(event)

        if isinstance(message, ResultMessage):
            result_text = message.result or ""
            stats.update({
                "success": not message.is_error,
                "cost_usd": message.total_cost_usd or 0,
                "duration_ms": message.duration_ms or 0,
                "num_turns": message.num_turns or 0,
                "usage": message.usage or {},
            })

        # Check cancellation
        if cancel_event and cancel_event.is_set():
            _log("Planning", C_YELLOW, f"{issue.id}: cancelled")
            stats["cancelled"] = True
            break

    # Check if plan was generated (the agent writes it directly via Write tool)
    plan_content = storage.load_issue_plan(issue.id)
    stats["plan_generated"] = bool(plan_content)

    if stats["plan_generated"]:
        _log("Planning", C_GREEN, f"Plan generated for {issue.id}")
    else:
        _log("Planning", C_YELLOW, f"No plan generated for {issue.id}")

    # Parse [SPLIT] directives from the result
    splits = parse_split_directives(result_text)
    # Also check plan.md itself for [SPLIT] directives
    if plan_content:
        splits.extend(parse_split_directives(plan_content))

    if splits:
        _log("Planning", C_BLUE, f"Splitting {issue.id} into {len(splits)} child issues")
        created_ids = _create_child_issues(issue, splits, storage)
        stats["split_issues"] = created_ids

        if on_event:
            await on_event({
                "ts": int(time.time()), "type": "planning_split", "issue_id": issue.id,
                "data": {"child_issues": created_ids, "count": len(created_ids)},
            })

    return stats


def _create_child_issues(
    parent: Issue,
    splits: list[dict],
    storage: ProjectStorage,
) -> list[str]:
    """Create child issues from [SPLIT] directives.

    Sets parent_id on children. Adds children to board TODO column.
    Returns list of created issue IDs.
    """
    project = storage.load_project_meta()
    prefix = project.key if project else "ISS"

    created_ids: list[str] = []
    prev_id: str | None = None

    for split in splits:
        issue_id = storage.next_issue_id(prefix)
        child = Issue.create(
            id=issue_id,
            title=split["title"],
            priority=parent.priority.value,
            labels=parent.labels + ["planned"],
        )
        child.source = "agent"
        child.parent_id = parent.id

        # Chain dependencies: each child depends on the previous one
        # (since splits are ordered by dependency)
        if prev_id:
            child.blocked_by.append(prev_id)

        child.move_to(IssueStatus.TODO)
        storage.save_issue(child)

        # Save child issue content if description provided
        if split.get("description"):
            storage.save_issue_content(issue_id, split["description"])

        # Add to board TODO column
        board_file = storage.root / "board.json"
        if board_file.exists():
            data = json.loads(board_file.read_text())
            for col in data["columns"]:
                if col["id"] == "todo":
                    col["issues"].append(issue_id)
                    break
            board_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

        _log("Planning", C_CYAN, f"Created child {issue_id}: {split['title']}")
        created_ids.append(issue_id)
        prev_id = issue_id

    # Update parent: set blocked_by to all children
    # Parent won't proceed until all children are done
    if created_ids:
        for cid in created_ids:
            if cid not in parent.blocked_by:
                parent.blocked_by.append(cid)
        storage.save_issue(parent)

    return created_ids
