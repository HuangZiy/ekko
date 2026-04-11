from __future__ import annotations
from pathlib import Path

from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage
from config import MODEL, MAX_TURNS_PER_LOOP, MAX_BUDGET_PER_LOOP
from core.models import Issue, IssueStatus
from core.storage import ProjectStorage


def build_issue_prompt(issue: Issue, storage: ProjectStorage) -> str:
    """Build an agent prompt from Issue metadata and markdown content."""
    try:
        content = storage.load_issue_content(issue.id)
    except FileNotFoundError:
        content = ""

    return f"""你是一个高级全栈工程师。请完成以下任务。

## 任务: {issue.title}

ID: {issue.id}
优先级: {issue.priority.value}
标签: {', '.join(issue.labels) if issue.labels else '无'}

## 任务详情

{content if content else '（无详细描述，请根据标题完成任务）'}

## 工作方式

1. 阅读任务详情，理解需求
2. 修改代码前先搜索代码库确认现状
3. 完整实现功能，不要占位符
4. 运行构建和测试验证
5. 构建通过后 git commit

## 关键规则

- 只做这一项任务，做好做完
- 构建/测试不通过就不提交
- 禁止执行 kill、pkill 等杀进程命令
- 禁止操作 3000 端口
"""


class IssueExecutor:
    """Executes a single Issue via claude-agent-sdk."""

    def __init__(self, storage: ProjectStorage, workspace: Path) -> None:
        self.storage = storage
        self.workspace = workspace

    async def run(self, issue: Issue) -> dict:
        """Execute an issue. Updates issue status and returns stats."""
        prompt = build_issue_prompt(issue, self.storage)
        stats: dict = {"success": False, "issue_id": issue.id}

        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                model=MODEL,
                allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent"],
                cwd=str(self.workspace),
                max_turns=MAX_TURNS_PER_LOOP,
                max_budget_usd=MAX_BUDGET_PER_LOOP,
                permission_mode="bypassPermissions",
            ),
        ):
            if isinstance(message, ResultMessage):
                success = not message.is_error
                stats.update({
                    "success": success,
                    "cost_usd": message.total_cost_usd or 0,
                    "duration_ms": message.duration_ms,
                    "num_turns": message.num_turns,
                    "usage": message.usage or {},
                })

                if success:
                    issue.move_to(IssueStatus.AGENT_DONE)
                else:
                    issue.move_to(IssueStatus.FAILED)
                    issue.retry_count += 1
                self.storage.save_issue(issue)

        return stats
