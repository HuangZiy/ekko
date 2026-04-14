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


def test_collect_evidence_no_agent_commits_but_head_moved(tmp_path):
    """When agent produced no commits but HEAD moved (external commits),
    evidence should NOT misattribute the diff to the agent."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="empty agent run")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    def mock_run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0)
        cmd_str = " ".join(cmd)
        if "rev-parse" in cmd_str:
            # HEAD has moved from base_sha (external commit pushed HEAD forward)
            result.stdout = "def5678"
        elif "diff" in cmd_str:
            # There IS a diff between base and HEAD, but it's from external commits
            result.stdout = "core/ralph_loop.py | 66 ++++++\n"
        elif "log" in cmd_str:
            result.stdout = "a27e66e fix: some other agent commit (EKO-3)"
        else:
            result.stdout = ""
        return result

    with patch("core.evidence.subprocess.run", side_effect=mock_run_side_effect):
        # agent_commits=[] means agent tracked commits and produced none
        collect_evidence(issue.id, store, ws, base_sha="abc1234", agent_commits=[])

    content = store.load_issue_content(issue.id)
    # Should NOT contain the external diff
    assert "ralph_loop.py" not in content
    assert "a27e66e" not in content
    # Should clearly state no agent commits
    assert "No file changes by this agent" in content
    assert "No commits by this agent" in content
    # Should NOT use legacy header
    assert "### Latest Commit" not in content


def test_collect_evidence_with_agent_commits_list(tmp_path):
    """When agent has explicit commit list, evidence should show range diff normally."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="agent with commits")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    def mock_run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0)
        cmd_str = " ".join(cmd)
        if "rev-parse" in cmd_str:
            result.stdout = "def5678"
        elif "diff" in cmd_str and "abc1234..HEAD" in cmd_str:
            result.stdout = "core/evidence.py | 20 ++++++\n"
        elif "log" in cmd_str and "abc1234..HEAD" in cmd_str:
            result.stdout = "def5678 fix: actual agent commit (ISS-1)"
        else:
            result.stdout = ""
        return result

    with patch("core.evidence.subprocess.run", side_effect=mock_run_side_effect):
        # agent_commits has actual SHAs — agent did produce commits
        collect_evidence(issue.id, store, ws, base_sha="abc1234", agent_commits=["def5678"])

    content = store.load_issue_content(issue.id)
    assert "core/evidence.py" in content
    assert "def5678" in content
    assert "### Commits" in content
    assert "### Latest Commit" not in content


def test_collect_evidence_agent_commits_none_backward_compat(tmp_path):
    """When agent_commits is None (old callers), behavior should match pre-fix range diff."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="backward compat")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    def mock_run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0)
        cmd_str = " ".join(cmd)
        if "rev-parse" in cmd_str:
            result.stdout = "def5678"  # HEAD differs from base
        elif "diff" in cmd_str and "abc1234..HEAD" in cmd_str:
            result.stdout = "some_file.py | 10 +++\n"
        elif "log" in cmd_str and "abc1234..HEAD" in cmd_str:
            result.stdout = "def5678 feat: some commit"
        else:
            result.stdout = ""
        return result

    with patch("core.evidence.subprocess.run", side_effect=mock_run_side_effect):
        # agent_commits=None — backward compatible, no filtering
        collect_evidence(issue.id, store, ws, base_sha="abc1234", agent_commits=None)

    content = store.load_issue_content(issue.id)
    # Should show the diff and commits as before (no filtering)
    assert "some_file.py" in content
    assert "def5678" in content
    assert "### Commits" in content
    assert "No file changes by this agent" not in content
    assert "No commits by this agent" not in content


def test_collect_evidence_rev_parse_returns_empty(tmp_path):
    """When git rev-parse HEAD returns empty (git failure), evidence should
    output an error message instead of running unpredictable git commands."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="rev-parse fails")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    call_log: list[str] = []

    def mock_run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=1)
        cmd_str = " ".join(cmd)
        call_log.append(cmd_str)
        if "rev-parse" in cmd_str:
            # Simulate git rev-parse HEAD failing (returns empty)
            result.stdout = ""
        else:
            result.stdout = ""
        return result

    with patch("core.evidence.subprocess.run", side_effect=mock_run_side_effect):
        collect_evidence(issue.id, store, ws, base_sha="abc1234")

    content = store.load_issue_content(issue.id)
    # Should contain error message
    assert "unable to determine HEAD" in content
    # Should NOT have attempted git diff or git log with empty current_head
    diff_calls = [c for c in call_log if "diff" in c]
    log_calls = [c for c in call_log if "log" in c and "rev-parse" not in c]
    assert len(diff_calls) == 0, f"Should not run git diff when rev-parse fails, but got: {diff_calls}"
    assert len(log_calls) == 0, f"Should not run git log when rev-parse fails, but got: {log_calls}"


def test_collect_evidence_includes_screenshots_with_project_id(tmp_path):
    """When screenshots exist and project_id is provided, evidence should contain markdown image links."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="screenshot task")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    # Create fake screenshot files
    screenshots_dir = store.root / "runs" / issue.id / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    (screenshots_dir / "step1.png").write_bytes(b"fake png")
    (screenshots_dir / "step2.jpg").write_bytes(b"fake jpg")

    with patch("core.evidence.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="file.py | 10 ++++\n", returncode=0)
        collect_evidence(issue.id, store, ws, project_id="proj-123")

    content = store.load_issue_content(issue.id)
    assert "### 截图/录屏" in content
    assert "![step1](/api/projects/proj-123/issues/ISS-1/screenshots/step1.png)" in content
    assert "![step2](/api/projects/proj-123/issues/ISS-1/screenshots/step2.jpg)" in content


def test_collect_evidence_screenshots_without_project_id(tmp_path):
    """When screenshots exist but no projecdence should use relative paths."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="screenshot no pid")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    # Create fake screenshot
    screenshots_dir = store.root / "runs" / issue.id / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    (screenshots_dir / "capture.png").write_bytes(b"fake png")

    with patch("core.evidence.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="file.py | 10 ++++\n", returncode=0)
        collect_evidence(issue.id, store, ws)

    content = store.load_issue_content(issue.id)
    assert "### 截图/录屏" in content
    assert "![capture](screenshots/capture.png)" in content


def test_collect_evidence_no_screenshots_dir(tmp_path):
    """When no screenshots directory exists, evidence should not contain screenshot section."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="no screenshots")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    with patch("core.evidence.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="file.py | 10 ++++\n", returncode=0)
        collect_evidence(issue.id, store, ws, project_id="proj-123")

    content = store.load_issue_content(issue.id)
    assert "### 截图/录屏" not in content


def test_collect_evidence_empty_screenshots_dir(tmp_path):
    """When screenshots directory exists but is empty, evidence should not contain screenshot section."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="empty screenshots")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    # Create empty screenshots dir
    screenshots_dir = store.root / "runs" / issue.id / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    with patch("core.evidence.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="file.py | 10 ++++\n", returncode=0)
        collect_evidence(issue.id, store, ws, project_id="proj-123")

    content = store.load_issue_content(issue.id)
    assert "### 截图/录屏" not in content


def test_collect_evidence_includes_change_summary(tmp_path):
    """Evidence should include a 变更摘要 section with shortstat output."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="change summary task")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    def mock_run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0)
        cmd_str = " ".join(cmd)
        if "rev-parse" in cmd_str:
            result.stdout = "def5678"
        elif "--shortstat" in cmd_str:
            result.stdout = " 3 files changed, 45 insertions(+), 12 deletions(-)"
        elif "diff" in cmd_str and "--stat" in cmd_str and "abc1234..HEAD" in cmd_str:
            result.stdout = "file.py | 10 ++++\n"
        elif "diff" in cmd_str and "--name-only" in cmd_str:
            result.stdout = "file.py\n"
        elif "diff" in cmd_str and "-- file.py" in cmd_str:
            result.stdout = "+added line\n-removed line\n"
        elif "log" in cmd_str and "abc1234..HEAD" in cmd_str:
            result.stdout = "def5678 feat: add feature"
        else:
            result.stdout = ""
        return result

    with patch("core.evidence.subprocess.run", side_effect=mock_run_side_effect):
        collect_evidence(issue.id, store, ws, base_sha="abc1234")

    content = store.load_issue_content(issue.id)
    assert "### 变更摘要" in content
    assert "3 files changed" in content
    assert "45 insertions" in content


def test_collect_evidence_includes_file_diff_details(tmp_path):
    """Evidence should include 修改文件详情 section with per-file diffs."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="file diff details")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    def mock_run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0)
        cmd_str = " ".join(cmd)
        if "rev-parse" in cmd_str:
            result.stdout = "def5678"
        elif "--shortstat" in cmd_str:
            result.stdout = " 1 file changed, 5 insertions(+)"
        elif "diff" in cmd_str and "--stat" in cmd_str:
            result.stdout = "core/evidence.py | 5 +++++"
        elif "diff" in cmd_str and "--name-only" in cmd_str:
            result.stdout = "core/evidence.py\n"
        elif "diff" in cmd_str and "-- core/evidence.py" in cmd_str:
            result.stdout = "diff --git a/core/evidence.py b/core/evidence.py\n+new line 1\n+new line 2"
        elif "log" in cmd_str:
            result.stdout = "def5678 feat: update evidence"
        else:
            result.stdout = ""
        return result

    with patch("core.evidence.subprocess.run", side_effect=mock_run_side_effect):
        collect_evidence(issue.id, store, ws, base_sha="abc1234")

    content = store.load_issue_content(issue.id)
    assert "### 修改文件详情" in content
    assert "#### core/evidence.py" in content
    assert "+new line 1" in content


def test_collect_evidence_video_files_collected(tmp_path):
    """Video files (.mp4, .webm) should be collected alongside images."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="video task")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    # Create fake media files (images + videos)
    screenshots_dir = store.root / "runs" / issue.id / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    (screenshots_dir / "step1.png").write_bytes(b"fake png")
    (screenshots_dir / "recording.mp4").write_bytes(b"fake mp4")
    (screenshots_dir / "demo.webm").write_bytes(b"fake webm")

    with patch("core.evidence.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="file.py | 10 ++++\n", returncode=0)
        collect_evidence(issue.id, store, ws, project_id="proj-123")

    content = store.load_issue_content(issue.id)
    assert "### 截图/录屏" in content
    # Image uses markdown image syntax
    assert "![step1](/api/projects/proj-123/issues/ISS-1/screenshots/step1.png)" in content
    # Videos use markdown link syntax with 🎬 prefix
    assert "[🎬 recording](/api/projects/proj-123/issues/ISS-1/screenshots/recording.mp4)" in content
    assert "[🎬 demo](/api/projects/proj-123/issues/ISS-1/screenshots/demo.webm)" in content


def test_collect_evidence_video_type_field_in_evidence_data(tmp_path):
    """Evidence data should include type='video' for video files and type='image' for images."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="video type field")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    screenshots_dir = store.root / "runs" / issue.id / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    (screenshots_dir / "capture.png").write_bytes(b"fake png")
    (screenshots_dir / "screen.mp4").write_bytes(b"fake mp4")
    (screenshots_dir / "clip.webm").write_bytes(b"fake webm")

    with patch("core.evidence.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="file.py | 10 ++++\n", returncode=0)
        collect_evidence(issue.id, store, ws, project_id="proj-123")

    # Read the evidence.json to check type fields
    import json
    evidence_path = store.issues_dir / issue.id / "evidence.json"
    assert evidence_path.exists(), "evidence.json should be created"
    evidence_data = json.loads(evidence_path.read_text())

    screenshots = evidence_data["screenshots"]
    assert len(screenshots) == 3

    # Find each by filename
    by_name = {s["filename"]: s for s in screenshots}
    assert by_name["capture.png"]["type"] == "image"
    assert by_name["screen.mp4"]["type"] == "video"
    assert by_name["clip.webm"]["type"] == "video"


def test_collect_evidence_only_videos_no_images(tmp_path):
    """When only video files exist (no images), they should still be collected."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="only videos")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    screenshots_dir = store.root / "runs" / issue.id / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    (screenshots_dir / "recording.mp4").write_bytes(b"fake mp4")

    with patch("core.evidence.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        collect_evidence(issue.id, store, ws, project_id="proj-123")

    content = store.load_issue_content(issue.id)
    assert "### 截图/录屏" in content
    assert "[🎬 recording](/api/projects/proj-123/issues/ISS-1/screenshots/recording.mp4)" in content


def test_collect_evidence_unsupported_files_ignored(tmp_path):
    """Non-image, non-video files in screenshots dir should be ignored."""
    store = ProjectStorage(tmp_path / "project")
    ws = tmp_path / "workspace"
    ws.mkdir()

    issue = Issue.create(id="ISS-1", title="unsupported files")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Task")

    screenshots_dir = store.root / "runs" / issue.id / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    (screenshots_dir / "notes.txt").write_text("some notes")
    (screenshots_dir / "data.json").write_text("{}")

    with patch("core.evidence.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        collect_evidence(issue.id, store, ws, project_id="proj-123")

    content = store.load_issue_content(issue.id)
    assert "### 截图/录屏" not in content
