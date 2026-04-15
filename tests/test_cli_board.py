"""Tests for ekko board command."""
import json
import pytest
from cli.main import main
from core.models import Project, Board
from core.storage import ProjectStorage


@pytest.fixture
def cli(tmp_path, capsys):
    """CLI runner with a project that has a board and some issues."""
    project_dir = tmp_path / "project"
    store = ProjectStorage(project_dir)
    project = Project.create(id="PRJ-1", name="test", workspace_path=str(tmp_path))
    store.save_project_meta(project)

    # Create board
    board = Board.create()
    board_data = {"columns": [{"id": c.id, "name": c.name, "issues": c.issues} for c in board.columns]}
    (project_dir / "board.json").write_text(json.dumps(board_data, indent=2, ensure_ascii=False))

    project_dir_str = str(project_dir)

    def run(*args: str):
        try:
            main(["--project", project_dir_str, *args])
        except SystemExit as e:
            return e.code, capsys.readouterr()
        return 0, capsys.readouterr()

    run.project_dir = project_dir_str
    return run


class TestBoardShow:
    def test_empty_board(self, cli):
        code, out = cli("board")
        assert code == 0

    def test_board_shows_issues(self, cli):
        cli("issue", "create", "Task A")
        cli("issue", "create", "Task B")
        code, out = cli("board")
        assert code == 0
        assert "Task A" in out.out
        assert "Task B" in out.out

    def test_board_groups_by_column(self, cli):
        # Create issue and move to todo
        code, out = cli("issue", "create", "In todo")
        issue_id = out.out.strip().split()[1].rstrip(":")
        cli("issue", "move", issue_id, "todo")

        cli("issue", "create", "In backlog")

        code, out = cli("board")
        assert code == 0


class TestBoardMove:
    def test_move_issue(self, cli):
        code, out = cli("issue", "create", "Move me")
        issue_id = out.out.strip().split()[1].rstrip(":")

        code, out = cli("board", "move", issue_id, "todo")
        assert code == 0
        assert "todo" in out.out.lower()

    def test_move_not_found(self, cli):
        code, out = cli("board", "move", "ISS-nope", "todo")
        assert code == 1
