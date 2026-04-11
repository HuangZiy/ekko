import os
import subprocess
import time
from pathlib import Path

from claude_agent_sdk import (
    query, ClaudeAgentOptions, ResultMessage,
    AssistantMessage, SystemMessage, TextBlock, ToolUseBlock, ToolResultBlock,
)
from config import MODEL, WORKSPACE_DIR


PROMPTS_DIR = Path("prompts")
EVAL_PORT = 3001

# ANSI colors
C_RESET = "\033[0m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"
C_DIM = "\033[2m"


def _log(prefix: str, color: str, msg: str) -> None:
    from harness import _tee
    _tee(f"{color}[{prefix}]{C_RESET} {msg}")


def _log_message(message) -> None:
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                text = block.text
                if len(text) > 300:
                    text = text[:300] + "..."
                _log("Evaluator", C_MAGENTA, text)
            elif isinstance(block, ToolUseBlock):
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


def _get_git_diff() -> str:
    """Get the git diff of the last commit (what Ralph just changed)."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--stat"],
            cwd=str(WORKSPACE_DIR),
            capture_output=True, text=True, timeout=10,
        )
        diff_stat = result.stdout.strip()

        result2 = subprocess.run(
            ["git", "log", "-1", "--oneline"],
            cwd=str(WORKSPACE_DIR),
            capture_output=True, text=True, timeout=10,
        )
        commit_msg = result2.stdout.strip()

        return f"Commit: {commit_msg}\n\nChanged files:\n{diff_stat}"
    except Exception:
        return "(unable to get git diff)"


def _start_dev_server():
    """Start Next.js dev server, return process handle."""
    env = {**os.environ, "PORT": str(EVAL_PORT)}
    server = subprocess.Popen(
        ["npm", "run", "dev", "--", "-p", str(EVAL_PORT)],
        cwd=str(WORKSPACE_DIR),
        env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(10)
    return server


def _stop_dev_server(server):
    server.terminate()
    server.wait()


async def _run_eval_query(prompt: str, ss_dir: Path, max_turns: int = 40) -> tuple[str, dict]:
    """Run a single evaluator query and return (report, stats)."""
    system_prompt = (PROMPTS_DIR / "evaluator_system.md").read_text()

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
                "playwright": {
                    "command": "npx",
                    "args": ["@playwright/mcp@latest"],
                }
            },
            cwd=str(WORKSPACE_DIR),
            max_turns=max_turns,
            max_buffer_size=10 * 1024 * 1024,
        ),
    ):
        _log_message(message)
        if isinstance(message, ResultMessage):
            result = message.result
            stats = {
                "cost_usd": message.total_cost_usd or 0,
                "duration_ms": message.duration_ms,
                "num_turns": message.num_turns,
                "usage": message.usage or {},
            }

    return result or "Evaluation returned no result", stats


async def run_incremental_eval(task_description: str, screenshots_dir: Path | None = None) -> tuple[str, dict]:
    """Incremental evaluation — only verify what Ralph just changed.

    Cheaper and faster than full eval. Checks the specific change + build.
    """
    from config import SCREENSHOTS_DIR as DEFAULT_SCREENSHOTS_DIR
    ss_dir = screenshots_dir or DEFAULT_SCREENSHOTS_DIR
    ss_dir.mkdir(parents=True, exist_ok=True)

    _log("Eval", C_MAGENTA, f"Incremental eval: {task_description[:60]}")

    git_diff = _get_git_diff()

    server = _start_dev_server()
    try:
        prompt = f"""增量评估：验证 Ralph 刚完成的这项修改是否正确。

## 本轮修改

任务：{task_description}

{git_diff}

## 评估要求

1. 用 Playwright 打开 http://localhost:{EVAL_PORT}，只验证与本次修改相关的页面和功能
2. 检查修改涉及的源码文件，确认实现正确
3. 运行 `npm run build` 确认构建通过
4. 不需要全量评估所有页面，只关注本次变更

## 输出格式

```
## 增量评估

### 变更验证: PASS/FAIL
- 具体发现...

### 构建检查: PASS/FAIL

### 发现的问题
- [FAIL] 问题描述（如果有）
```

截图规则：
- 只截取与本次修改相关的页面
- 截图前 browser_resize 设为 1920x1080
- 格式 JPEG quality 50
- 保存到 {ss_dir}"""

        return await _run_eval_query(prompt, ss_dir, max_turns=30)
    finally:
        _stop_dev_server(server)


async def run_full_eval(screenshots_dir: Path | None = None) -> tuple[str, dict]:
    """Full evaluation — four-dimension scoring with Playwright.

    Used at the end of the loop when all tasks are done, or periodically.
    """
    from config import SCREENSHOTS_DIR as DEFAULT_SCREENSHOTS_DIR
    ss_dir = screenshots_dir or DEFAULT_SCREENSHOTS_DIR
    ss_dir.mkdir(parents=True, exist_ok=True)

    _log("Eval", C_MAGENTA, f"Full evaluation on port {EVAL_PORT}...")

    eval_criteria = (PROMPTS_DIR / "eval_criteria.md").read_text()

    server = _start_dev_server()
    try:
        prompt = f"""全量评估当前运行在 http://localhost:{EVAL_PORT} 的 Blog 应用。

{eval_criteria}

使用 Playwright 实际浏览页面：导航每个页面、点击交互元素、测试暗色模式切换、
检查响应式布局、验证文章渲染、验证 Pretext 排版效果。
对每个维度给出 X/10 分数和详细发现。
对未达标项给出精确的问题描述和修复建议。

截图规则：
- 允许使用 fullPage: true
- 截图前 browser_resize 设为 1920x1080
- 格式 JPEG quality 50
- 保存到 {ss_dir}"""

        return await _run_eval_query(prompt, ss_dir, max_turns=80)
    finally:
        _stop_dev_server(server)
