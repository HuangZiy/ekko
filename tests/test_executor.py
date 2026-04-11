import pytest
from unittest.mock import patch, MagicMock
from claude_agent_sdk import ResultMessage
from core.models import Issue, IssueStatus
from core.storage import ProjectStorage
from core.executor import IssueExecutor, build_issue_prompt


def test_build_issue_prompt_basic(tmp_path):
    """Prompt should include issue title and markdown content."""
    store = ProjectStorage(tmp_path / "project")
    issue = Issue.create(title="实现登录页", labels=["auth"])
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# 实现登录页\n\n需要用户名密码表单")

    prompt = build_issue_prompt(issue, store)
    assert "实现登录页" in prompt
    assert "用户名密码表单" in prompt


def test_build_issue_prompt_without_content(tmp_path):
    """Prompt should work even if no markdown content exists."""
    store = ProjectStorage(tmp_path / "project")
    issue = Issue.create(title="修复 bug")
    store.save_issue(issue)

    prompt = build_issue_prompt(issue, store)
    assert "修复 bug" in prompt


def test_executor_init(tmp_path):
    """Executor should initialize with storage and workspace."""
    store = ProjectStorage(tmp_path / "project")
    executor = IssueExecutor(store, workspace=tmp_path / "ws")
    assert executor.storage is store


@pytest.mark.asyncio
async def test_executor_run_success(tmp_path):
    """Successful execution should move issue to AGENT_DONE and return stats."""
    store = ProjectStorage(tmp_path / "project")
    issue = Issue.create(title="test task")
    issue.move_to(IssueStatus.TODO)
    issue.move_to(IssueStatus.IN_PROGRESS)
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task\nDo something")

    mock_result = MagicMock(spec=ResultMessage)
    mock_result.is_error = False
    mock_result.total_cost_usd = 0.05
    mock_result.duration_ms = 3000
    mock_result.num_turns = 5
    mock_result.usage = {"input_tokens": 100, "output_tokens": 50}
    mock_result.result = "Done"

    async def mock_query(*args, **kwargs):
        yield mock_result

    executor = IssueExecutor(store, workspace=tmp_path / "ws")
    with patch("core.executor.query", mock_query):
        stats = await executor.run(issue)

    assert stats["success"] is True
    assert stats["cost_usd"] == 0.05
    reloaded = store.load_issue(issue.id)
    assert reloaded.status == IssueStatus.AGENT_DONE


@pytest.mark.asyncio
async def test_executor_run_failure(tmp_path):
    """Failed execution should move issue to FAILED."""
    store = ProjectStorage(tmp_path / "project")
    issue = Issue.create(title="failing task")
    issue.move_to(IssueStatus.TODO)
    issue.move_to(IssueStatus.IN_PROGRESS)
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task\nThis will fail")

    mock_result = MagicMock(spec=ResultMessage)
    mock_result.is_error = True
    mock_result.total_cost_usd = 0.02
    mock_result.duration_ms = 1000
    mock_result.num_turns = 2
    mock_result.usage = {}
    mock_result.result = "Error occurred"

    async def mock_query(*args, **kwargs):
        yield mock_result

    executor = IssueExecutor(store, workspace=tmp_path / "ws")
    with patch("core.executor.query", mock_query):
        stats = await executor.run(issue)

    assert stats["success"] is False
    reloaded = store.load_issue(issue.id)
    assert reloaded.status == IssueStatus.FAILED
