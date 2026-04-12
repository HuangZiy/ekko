"""Functional tests for review CLI commands."""
import pytest
from cli.main import main
from core.models import Issue, IssueStatus
from core.storage import ProjectStorage


@pytest.fixture
def cli(tmp_path, capsys):
    from core.models import Project
    project_dir = tmp_path / "project"
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
    run.store = ProjectStorage(tmp_path / "project")
    return run


def _create_agent_done_issue(cli) -> str:
    """Helper: create an issue and move it to agent_done."""
    code, out = cli("issue", "create", "Review me")
    issue_id = out.out.strip().split()[1].rstrip(":")
    cli("issue", "move", issue_id, "todo")
    cli("issue", "move", issue_id, "in_progress")
    cli("issue", "move", issue_id, "agent_done")
    return issue_id


class TestReviewApprove:
    def test_approve(self, cli):
        issue_id = _create_agent_done_issue(cli)
        code, out = cli("review", issue_id, "--approve")
        assert code == 0
        assert "Approved" in out.out
        assert "human_done" in out.out

    def test_approve_unlocks_dependents(self, cli):
        blocker_id = _create_agent_done_issue(cli)
        # Create a dependent issue and add blocker
        code, out = cli("issue", "create", "Dependent task")
        dep_id = out.out.strip().split()[1].rstrip(":")
        # Manually add blocker via storage
        dep = cli.store.load_issue(dep_id)
        dep.add_blocker(blocker_id)
        cli.store.save_issue(dep)

        code, out = cli("review", blocker_id, "--approve")
        assert code == 0
        assert "Unblocked" in out.out
        assert dep_id in out.out

        # Verify blocker was actually removed
        dep = cli.store.load_issue(dep_id)
        assert not dep.is_blocked()


class TestReviewReject:
    def test_reject(self, cli):
        issue_id = _create_agent_done_issue(cli)
        code, out = cli("review", issue_id, "--reject")
        assert code == 0
        assert "Rejected" in out.out
        assert "todo" in out.out

    def test_reject_with_comment(self, cli):
        issue_id = _create_agent_done_issue(cli)
        code, out = cli("review", issue_id, "--reject", "--comment", "Missing loading state")
        assert code == 0
        assert "Missing loading state" in out.out
        # Verify feedback was written to content
        content = cli.store.load_issue_content(issue_id)
        assert "Missing loading state" in content
        assert "Review Feedback" in content

    def test_reject_moves_to_todo(self, cli):
        issue_id = _create_agent_done_issue(cli)
        cli("review", issue_id, "--reject")
        issue = cli.store.load_issue(issue_id)
        assert issue.status == IssueStatus.TODO


class TestReviewErrors:
    def test_not_agent_done(self, cli):
        code, out = cli("issue", "create", "Not ready")
        issue_id = out.out.strip().split()[1].rstrip(":")
        code, out = cli("review", issue_id, "--approve")
        assert code == 1
        assert "agent_done" in out.err

    def test_not_found(self, cli):
        code, out = cli("review", "ISS-nope", "--approve")
        assert code == 1
        assert "not found" in out.err.lower()

    def test_no_flag(self, cli):
        issue_id = _create_agent_done_issue(cli)
        code, out = cli("review", issue_id)
        assert code == 1
        assert "approve" in out.err.lower() or "reject" in out.err.lower()
