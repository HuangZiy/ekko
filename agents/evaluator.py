"""Evaluator agent — verifies Issue completion via Playwright + code review.

Two modes:
- run_issue_eval(): Issue-aware incremental eval. Receives Issue object, verifies against
  acceptance criteria, outputs [FAIL] for current issue problems and [NEW_ISSUE] for other findings.
- run_full_eval(): Four-dimension full scoring (legacy, used for final quality gate).
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Awaitable, Callable

from claude_agent_sdk import (
    query, ClaudeAgentOptions, ResultMessage,
    AssistantMessage, SystemMessage, TextBlock, ToolUseBlock, ToolResultBlock,
)
from config import MODEL


PROMPTS_DIR = Path("prompts")

C_RESET = "\033[0m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"
C_DIM = "\033[2m"


def _log(prefix: str, color: str, msg: str) -> None:
    try:
        from harness import _tee
        _tee(f"{color}[{prefix}]{C_RESET} {msg}")
    except ImportError:
        print(f"[{prefix}] {msg}", flush=True)


def _log_message(message, issue_id: str = "") -> None:
    tag = f"{issue_id} " if issue_id else ""
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                text = block.text[:300] + "..." if len(block.text) > 300 else block.text
                _log("Evaluator", C_MAGENTA, f"{tag}{text}")
            elif isinstance(block, ToolUseBlock):
                inp = str(block.input)[:120]
                _log("Tool", C_YELLOW, f"{tag}{block.name}({inp})")
    elif isinstance(message, ResultMessage):
        cost = f"${message.total_cost_usd:.2f}" if message.total_cost_usd else "?"
        _log("Done", C_GREEN, f"{tag}turns={message.num_turns} cost={cost} duration={message.duration_ms // 1000}s")
        if message.is_error:
            _log("Done", C_RED, f"{tag}ERROR: {message.result}")


def _get_git_diff(workspace: Path) -> str:
    try:
        stat = subprocess.run(["git", "diff", "HEAD~1", "--stat"], cwd=str(workspace),
                              capture_output=True, text=True, timeout=10).stdout.strip()
        log = subprocess.run(["git", "log", "-1", "--oneline"], cwd=str(workspace),
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return f"Commit: {log}\n\nChanged files:\n{stat}"
    except Exception:
        return "(unable to get git diff)"


def _find_free_port() -> int:
    """Find an available port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_dev_server(workspace: Path) -> tuple:
    """Start dev server on a free port. Returns (process, port)."""
    port = _find_free_port()
    env = {**os.environ, "PORT": str(port)}
    server = subprocess.Popen(
        ["npm", "run", "dev", "--", "-p", str(port)],
        cwd=str(workspace), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(10)
    return server, port


def _stop_dev_server(server):
    server.terminate()
    server.wait()


async def _run_eval_query(
    prompt: str, ss_dir: Path, workspace: Path, max_turns: int = 40,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
    issue_id: str = "",
) -> tuple[str, dict]:
    system_prompt_path = PROMPTS_DIR / "evaluator_system.md"
    system_prompt = system_prompt_path.read_text() if system_prompt_path.exists() else ""

    result = "Evaluation failed — no result returned"
    stats = {"cost_usd": 0, "duration_ms": 0, "num_turns": 0, "usage": {}}

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            model=MODEL,
            system_prompt=system_prompt,
            allowed_tools=["Read", "Glob", "Grep", "Bash"],
            permission_mode="bypassPermissions",
            mcp_servers={
                "playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}
            },
            cwd=str(workspace),
            max_turns=max_turns,
            max_buffer_size=10 * 1024 * 1024,
        ),
    ):
        _log_message(message, issue_id)

        if on_event and issue_id:
            from core.executor import _message_to_events
            for event in _message_to_events(issue_id, message):
                await on_event(event)

        if isinstance(message, ResultMessage):
            result = message.result
            stats = {
                "cost_usd": message.total_cost_usd or 0,
                "duration_ms": message.duration_ms,
                "num_turns": message.num_turns,
                "usage": message.usage or {},
            }

    return result or "Evaluation returned no result", stats


# ---------------------------------------------------------------------------
# Issue-aware eval (used by core/ralph_loop.py)
# ---------------------------------------------------------------------------

async def run_issue_eval(
    issue_id: str,
    issue_title: str,
    issue_content: str,
    screenshots_dir: Path | None = None,
    workspace: Path | None = None,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
) -> tuple[str, dict]:
    """Evaluate a specific Issue's completion. Returns (report, stats).

    The report uses these markers:
    - [PASS] item — verification passed
    - [FAIL] item — current Issue has this problem (Ralph should fix)
    - [NEW_ISSUE] title — unrelated problem found (harness creates a new Issue)
    """
    from config import SCREENSHOTS_DIR as DEFAULT_SCREENSHOTS_DIR
    ws = workspace
    if not ws:
        raise ValueError("workspace is required for run_issue_eval")
    ss_dir = screenshots_dir or DEFAULT_SCREENSHOTS_DIR
    ss_dir.mkdir(parents=True, exist_ok=True)

    _log("Eval", C_MAGENTA, f"Issue eval: {issue_title[:60]}")

    git_diff = _get_git_diff(ws)

    server, port = _start_dev_server(ws)
    try:
        prompt = f"""增量评估：验证以下 Issue 是否正确完成。

## Issue: {issue_id}

### 标题
{issue_title}

### 详细内容与验收标准
{issue_content if issue_content else '（无详细描述，根据标题判断）'}

### 本次代码变更
{git_diff}

## 评估要求

1. 用 Playwright 打开 http://localhost:{port}，验证与此 Issue 相关的页面和功能
2. 对照 Issue 的验收标准逐项检查
3. 运行 `npm run build` 确认构建通过
4. 只关注此 Issue 的完成情况，不做全量评估

## 输出格式（严格遵守）

对此 Issue 的每个验收标准：
- [PASS] 标准描述 — 验证通过的说明
- [FAIL] 标准描述 — 未通过的原因和修复建议

如果在验证过程中发现了与此 Issue 无关的其他问题，用以下格式单独列出：
- [NEW_ISSUE] 问题标题 — 简要描述

截图规则：
- 截图前 browser_resize 设为 1920x1080
- 格式 JPEG quality 50
- 保存到 {ss_dir}"""

        return await _run_eval_query(prompt, ss_dir, ws, max_turns=30, on_event=on_event, issue_id=issue_id)
    finally:
        _stop_dev_server(server)


# ---------------------------------------------------------------------------
# Legacy: string-based incremental eval (backward compat for harness.py)
# ---------------------------------------------------------------------------

async def run_incremental_eval(
    task_description: str,
    screenshots_dir: Path | None = None,
) -> tuple[str, dict]:
    """Legacy incremental eval — accepts a string task description."""
    return await run_issue_eval(
        issue_id="(legacy)",
        issue_title=task_description,
        issue_content="",
        screenshots_dir=screenshots_dir,
    )


# ---------------------------------------------------------------------------
# Full eval (quality gate)
# ---------------------------------------------------------------------------

async def run_full_eval(screenshots_dir: Path | None = None, workspace: Path | None = None) -> tuple[str, dict]:
    """Full four-dimension evaluation with Playwright."""
    from config import SCREENSHOTS_DIR as DEFAULT_SCREENSHOTS_DIR
    ws = workspace
    if not ws:
        raise ValueError("workspace is required for run_issue_eval")
    ss_dir = screenshots_dir or DEFAULT_SCREENSHOTS_DIR
    ss_dir.mkdir(parents=True, exist_ok=True)

    _log("Eval", C_MAGENTA, "Full evaluation starting...")

    eval_criteria_path = PROMPTS_DIR / "eval_criteria.md"
    eval_criteria = eval_criteria_path.read_text() if eval_criteria_path.exists() else ""

    server, port = _start_dev_server(ws)
    try:
        prompt = f"""全量评估当前运行在 http://localhost:{port} 的应用。

{eval_criteria}

使用 Playwright 实际浏览页面：导航每个页面、点击交互元素、测试暗色模式切换、
检查响应式布局、验证文章渲染。
对每个维度给出 X/10 分数和详细发现。
对未达标项给出精确的问题描述和修复建议。

截图规则：
- 允许使用 fullPage: true
- 截图前 browser_resize 设为 1920x1080
- 格式 JPEG quality 50
- 保存到 {ss_dir}"""

        return await _run_eval_query(prompt, ss_dir, ws, max_turns=80)
    finally:
        _stop_dev_server(server)
