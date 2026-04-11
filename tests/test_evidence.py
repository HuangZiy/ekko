import subprocess
from unittest.mock import patch, MagicMock
from core.models import Issue, IssueStatus
from core.storage import ProjectStorage
from core.evidence import collect_evidence


def test_collect_evidence_appends_to_content(tmp_path):
    """Evidence should be appended to issue markdown under ## Agent Done 证据."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(title="test task")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task\n\nOriginal content")

    with patch("core.evidence.subprocess.run") as mock_run:
        # Mock git diff
        mock_run.return_value = MagicMock(
            stdout="file.py | 10 ++++\n", returncode=0
        )
        collect_evidence(issue.id, store, ws)

    content = store.load_issue_content(issue.id)
    assert "# Task" in content
    assert "## Agent Done" in content
    assert "file.py" in content


def test_collect_evidence_without_existing_content(tmp_path):
    """Evidence should work even if no prior content exists."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(title="new task")
    store.save_issue(issue)

    with patch("core.evidence.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        collect_evidence(issue.id, store, ws)

    content = store.load_issue_content(issue.id)
    assert "## Agent Done" in content


def test_collect_evidence_includes_build_result(tmp_path):
    """Evidence should include build output when available."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(title="build task")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Build task")

    def mock_run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0)
        if "diff" in cmd:
            result.stdout = "index.ts | 5 +++"
        elif "build" in cmd:
            result.stdout = "Build succeeded"
        elif "log" in cmd:
            result.stdout = "abc1234 feat: add feature"
        else:
            result.stdout = ""
        return result

    with patch("core.evidence.subprocess.run", side_effect=mock_run_side_effect):
        collect_evidence(issue.id, store, ws, run_build=True)

    content = store.load_issue_content(issue.id)
    assert "Build" in content or "build" in content
