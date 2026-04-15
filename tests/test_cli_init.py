"""Tests for ekko init command."""
import json
import os
import pytest
from cli.main import main


@pytest.fixture
def workspace(tmp_path, capsys, monkeypatch):
    """Provide a tmp workspace dir and a CLI runner."""
    work_dir = tmp_path / "my-project"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)

    # Point ARTIFACTS_DIR to tmp so we don't pollute real storage
    monkeypatch.setattr("config.ARTIFACTS_DIR", tmp_path / "artifacts")

    def run(*args: str):
        try:
            main(list(args))
        except SystemExit as e:
            return e.code, capsys.readouterr()
        return 0, capsys.readouterr()

    run.work_dir = work_dir
    return run


class TestInit:
    def test_init_creates_harness_dir(self, workspace):
        code, out = workspace("init", "--name", "test-project", "--key", "TST")
        assert code == 0
        assert (workspace.work_dir / ".harness").is_dir()
        assert (workspace.work_dir / ".harness" / "project.json").exists()

    def test_init_sets_project_name_and_key(self, workspace):
        workspace("init", "--name", "my-app", "--key", "APP")
        project_file = workspace.work_dir / ".harness" / "project.json"
        data = json.loads(project_file.read_text())
        assert data["name"] == "my-app"
        assert data["key"] == "APP"

    def test_init_registers_workspace(self, workspace):
        workspace("init", "--name", "ws-test", "--key", "WS")
        project_file = workspace.work_dir / ".harness" / "project.json"
        data = json.loads(project_file.read_text())
        assert str(workspace.work_dir) in data["workspaces"]

    def test_init_creates_board(self, workspace):
        workspace("init", "--name", "board-test", "--key", "BRD")
        board_file = workspace.work_dir / ".harness" / "board.json"
        assert board_file.exists()
        data = json.loads(board_file.read_text())
        col_ids = [c["id"] for c in data["columns"]]
        assert "backlog" in col_ids
        assert "todo" in col_ids

    def test_init_already_initialized(self, workspace):
        workspace("init", "--name", "first", "--key", "F")
        code, out = workspace("init", "--name", "second", "--key", "S")
        assert code != 0
        assert "already initialized" in out.err.lower()
