import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from claude_agent_sdk import ResultMessage
from core.models import Issue, IssueStatus
from core.storage import ProjectStorage
from core.executor import execute_issue, build_issue_prompt


def test_build_issue_prompt_basic(tmp_path):
    """Prompt should include issue title and markdown content."""
    store = ProjectStorage(tmp_path / "project")
    issue = Issue.create(id="ISS-1", title="实现登录页", labels=["auth"])
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# 实现登录页\n\n需要用户名密码表单")

    prompt = build_issue_prompt(issue, store, tmp_path / "ws")
    assert "实现登录页" in prompt
    assert "用户名密码表单" in prompt


def test_build_issue_prompt_without_content(tmp_path):
    """Prompt should work even if no markdown content exists."""
    store = ProjectStorage(tmp_path / "project")
    issue = Issue.create(id="ISS-1", title="修复 bug")
    store.save_issue(issue)

    prompt = build_issue_prompt(issue, store, tmp_path / "ws")
    assert "修复 bug" in prompt


@pytest.mark.asyncio
async def test_execute_issue_success(tmp_path):
    """Successful execution should return success=True. Does NOT change status."""
    store = ProjectStorage(tmp_path / "project")
    issue = Issue.create(id="ISS-1", title="test task")
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

    async def mock_receive():
        yield mock_result

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.receive_messages = mock_receive

    with patch("core.executor.ClaudeSDKClient", return_value=mock_client):
        stats = await execute_issue(issue, store, tmp_path / "ws")

    assert stats["success"] is True
    assert stats["cost_usd"] == 0.05
    # Executor does NOT change status — that's the scheduler's job
    reloaded = store.load_issue(issue.id)
    assert reloaded.status == IssueStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_execute_issue_failure(tmp_path):
    """Failed execution should return success=False. Does NOT change status."""
    store = ProjectStorage(tmp_path / "project")
    issue = Issue.create(id="ISS-1", title="failing task")
    issue.move_to(IssueStatus.TODO)
    issue.move_to(IssueStatus.IN_PROGRESS)
    store.save_issue(issue)

    mock_result = MagicMock(spec=ResultMessage)
    mock_result.is_error = True
    mock_result.total_cost_usd = 0.02
    mock_result.duration_ms = 1000
    mock_result.num_turns = 2
    mock_result.usage = {}
    mock_result.result = "Error occurred"

    async def mock_receive():
        yield mock_result

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.receive_messages = mock_receive

    with patch("core.executor.ClaudeSDKClient", return_value=mock_client):
        stats = await execute_issue(issue, store, tmp_path / "ws")

    assert stats["success"] is False
    # Status unchanged — executor doesn't touch it
    reloaded = store.load_issue(issue.id)
    assert reloaded.status == IssueStatus.IN_PROGRESS
