"""Functional tests for issue CLI commands."""
import pytest
from cli.main import main, build_parser, _get_storage
from core.models import Issue, IssueStatus
from core.storage import ProjectStorage


@pytest.fixture
def store(tmp_path):
    return ProjectStorage(tmp_path / "project")


@pytest.fixture
def cli(tmp_path, capsys):
    """Return a helper that runs CLI commands against a tmp project."""
    from core.models import Project
    project_dir = tmp_path / "project"
    # Create project metadata so _issue_create can read the key
    store = ProjectStorage(project_dir)
    project = Project.create(id="PRJ-1", name="test", workspace_path=str(tmp_path))
    store.save_project_meta(project)
    project_dir = str(project_dir)

    def run(*args: str):
        try:
            main(["--project", project_dir, *args])
        except SystemExit as e:
            return e.code, capsys.readouterr()
        return 0, capsys.readouterr()

    run.project_dir = project_dir
    return run


class TestIssueCreate:
    def test_basic(self, cli):
        code, out = cli("issue", "create", "Fix login bug")
        assert code == 0
        assert "Created ISS-" in out.out
        assert "Fix login bug" in out.out

    def test_with_labels_and_priority(self, cli):
        code, out = cli("issue", "create", "Add auth", "--label", "auth", "--label", "security", "--priority", "high")
        assert code == 0
        assert "Created ISS-" in out.out

    def test_created_issue_persists(self, cli):
        cli("issue", "create", "Persistent issue")
        code, out = cli("issue", "list")
        assert code == 0
        assert "Persistent issue" in out.out


class TestIssueList:
    def test_empty(self, cli):
        code, out = cli("issue", "list")
        assert code == 0
        assert "No issues found" in out.out

    def test_lists_created_issues(self, cli):
        cli("issue", "create", "Issue A")
        cli("issue", "create", "Issue B")
        code, out = cli("issue", "list")
        assert code == 0
        assert "Issue A" in out.out
        assert "Issue B" in out.out

    def test_filter_by_status(self, cli):
        cli("issue", "create", "Backlog item")
        code, out = cli("issue", "list", "--status", "todo")
        assert code == 0
        assert "No issues found" in out.out

        code, out = cli("issue", "list", "--status", "backlog")
        assert code == 0
        assert "Backlog item" in out.out


class TestIssueShow:
    def test_show_existing(self, cli):
        code, out = cli("issue", "create", "Show me")
        issue_id = out.out.strip().split()[1].rstrip(":")
        code, out = cli("issue", "show", issue_id)
        assert code == 0
        assert "Show me" in out.out
        assert "backlog" in out.out

    def test_show_not_found(self, cli):
        code, out = cli("issue", "show", "ISS-nonexistent")
        assert code == 1
        assert "not found" in out.err.lower()


class TestIssueMove:
    def test_move_to_todo(self, cli):
        code, out = cli("issue", "create", "Move me")
        issue_id = out.out.strip().split()[1].rstrip(":")
        code, out = cli("issue", "move", issue_id, "todo")
        assert code == 0
        assert "todo" in out.out

    def test_invalid_transition(self, cli):
        code, out = cli("issue", "create", "Bad move")
        issue_id = out.out.strip().split()[1].rstrip(":")
        # backlog -> human_done is invalid
        code, _ = cli("issue", "move", issue_id, "human_done")
        assert code != 0

    def test_move_not_found(self, cli):
        code, out = cli("issue", "move", "ISS-nope", "todo")
        assert code == 1
