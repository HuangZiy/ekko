"""Tests for executor on_event callback."""
import pytest
from unittest.mock import MagicMock

from core.executor import _message_to_events


def test_assistant_text_block_produces_agent_token():
    from claude_agent_sdk import AssistantMessage, TextBlock
    msg = MagicMock(spec=AssistantMessage)
    msg.content = [MagicMock(spec=TextBlock, text="Hello world")]
    events = _message_to_events("ISS-1", msg)
    assert len(events) == 1
    assert events[0]["type"] == "agent_token"
    assert events[0]["issue_id"] == "ISS-1"
    assert events[0]["data"]["text"] == "Hello world"


def test_assistant_tool_block_produces_agent_tool_call():
    from claude_agent_sdk import AssistantMessage, ToolUseBlock
    tool_block = MagicMock(spec=ToolUseBlock)
    tool_block.name = "Bash"
    tool_block.input = {"command": "ls"}
    msg = MagicMock(spec=AssistantMessage)
    msg.content = [tool_block]
    events = _message_to_events("ISS-1", msg)
    assert len(events) == 1
    assert events[0]["type"] == "agent_tool_call"
    assert events[0]["data"]["tool"] == "Bash"
    assert events[0]["data"]["input"] == {"command": "ls"}


def test_result_message_success_produces_agent_status_done():
    from claude_agent_sdk import ResultMessage
    msg = MagicMock(spec=ResultMessage)
    msg.is_error = False
    msg.total_cost_usd = 0.05
    msg.duration_ms = 3000
    msg.num_turns = 5
    msg.usage = {}
    events = _message_to_events("ISS-1", msg)
    assert len(events) == 1
    assert events[0]["type"] == "agent_status"
    assert events[0]["data"]["status"] == "done"


def test_result_message_error_produces_agent_status_failed():
    from claude_agent_sdk import ResultMessage
    msg = MagicMock(spec=ResultMessage)
    msg.is_error = True
    msg.result = "budget exceeded"
    msg.total_cost_usd = 0.10
    msg.duration_ms = 5000
    msg.num_turns = 10
    msg.usage = {}
    events = _message_to_events("ISS-1", msg)
    assert len(events) == 1
    assert events[0]["type"] == "agent_status"
    assert events[0]["data"]["status"] == "failed"
    assert events[0]["data"]["error"] == "budget exceeded"


def test_mixed_content_produces_multiple_events():
    from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock
    msg = MagicMock(spec=AssistantMessage)
    tool_block = MagicMock(spec=ToolUseBlock)
    tool_block.name = "Read"
    tool_block.input = {"file": "a.py"}
    msg.content = [
        MagicMock(spec=TextBlock, text="Analyzing..."),
        tool_block,
    ]
    events = _message_to_events("ISS-1", msg)
    assert len(events) == 2
    assert events[0]["type"] == "agent_token"
    assert events[1]["type"] == "agent_tool_call"
