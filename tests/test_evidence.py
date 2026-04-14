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

    issue = Issue.create(id="ISS-1", title="test task")
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

    issue = Issue.create(id="ISS-1", title="new task")
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

    issue = Issue.create(id="ISS-1", title="build task")
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


def test_collect_evidence_with_base_sha_range_diff(tmp_path):
    """When base_sha is provided, evidence should use range diff (base_sha..HEAD)."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="range diff task")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    def mock_run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0)
        cmd_str = " ".join(cmd)
        if "rev-parse" in cmd_str:
            result.stdout = "def5678"  # current HEAD differs from base
        elif "diff" in cmd_str and "abc1234..HEAD" in cmd_str:
            result.stdout = "IssueDetail.tsx | 15 +++++++"
        elif "log" in cmd_str and "abc1234..HEAD" in cmd_str:
            result.stdout = "d03696f feat: replace hardcoded text\n0a0a529 fix(i18n): remaining text"
        else:
            result.stdout = ""
        return result

    with patch("core.evidence.subprocess.run", side_effect=mock_run_side_effect):
        collect_evidence(issue.id, store, ws, base_sha="abc1234")

    content = store.load_issue_content(issue.id)
    assert "IssueDetail.tsx" in content
    assert "d03696f" in content
    assert "0a0a529" in content
    assert "### Commits" in content
    # Should NOT use legacy "Latest Commit" header
    assert "### Latest Commit" not in content


def test_collect_evidence_base_sha_equals_head(tmp_path):
    """When base_sha == HEAD (no commits during run), evidence should say so."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="no commits task")
    store.save_issue(issue)

    def mock_run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0)
        cmd_str = " ".join(cmd)
        if "rev-parse" in cmd_str:
            result.stdout = "abc1234"  # same as base_sha
        else:
            result.stdout = ""
        return result

    with patch("core.evidence.subprocess.run", side_effect=mock_run_side_effect):
        collect_evidence(issue.id, store, ws, base_sha="abc1234")

    content = store.load_issue_content(issue.id)
    assert "No commits during this run" in content


def test_collect_evidence_no_base_sha_legacy(tmp_path):
    """Without base_sha, evidence should use legacy HEAD~1 behavior."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="legacy task")
    store.save_issue(issue)

    def mock_run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0)
        cmd_str = " ".join(cmd)
        if "diff" in cmd_str and "HEAD~1" in cmd_str:
            result.stdout = "file.py | 3 +++"
        elif "log" in cmd_str and "-1" in cmd:
            result.stdout = "abc1234 feat: legacy commit"
        else:
            result.stdout = ""
        return result

    with patch("core.evidence.subprocess.run", side_effect=mock_run_side_effect):
        collect_evidence(issue.id, store, ws)

    content = store.load_issue_content(issue.id)
    assert "### Latest Commit" in content
    assert "abc1234" in content
    # Should NOT have range-based headers
    assert "### Commits" not in content
