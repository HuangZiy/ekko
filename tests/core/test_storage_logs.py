"""Tests for JSONL run log storage."""
import json
import pytest
from pathlib import Path
from core.storage import ProjectStorage


@pytest.fixture
def storage(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "issues").mkdir()
    return ProjectStorage(root)


def test_append_and_load_run_log(storage):
    entry1 = {"ts": 1713000000, "type": "agent_status", "data": {"status": "thinking"}}
    entry2 = {"ts": 1713000001, "type": "agent_token", "data": {"text": "hello"}}
    storage.append_run_log("ISS-1", "run-001", entry1)
    storage.append_run_log("ISS-1", "run-001", entry2)
    logs = storage.load_run_log("ISS-1", "run-001")
    assert len(logs) == 2
    assert logs[0]["type"] == "agent_status"
    assert logs[1]["data"]["text"] == "hello"


def test_list_run_ids_empty(storage):
    assert storage.list_run_ids("ISS-1") == []


def test_list_run_ids(storage):
    storage.append_run_log("ISS-1", "run-001", {"ts": 1, "type": "x", "data": {}})
    storage.append_run_log("ISS-1", "run-002", {"ts": 2, "type": "y", "data": {}})
    ids = storage.list_run_ids("ISS-1")
    assert ids == ["run-001", "run-002"]


def test_load_run_log_not_found(storage):
    assert storage.load_run_log("ISS-1", "run-999") == []
