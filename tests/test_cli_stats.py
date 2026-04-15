"""Tests for ekko stats command."""
import json
import pytest
from cli.main import main
from core.models import Project
from core.storage import ProjectStorage


@pytest.fixture
def cli(tmp_path, capsys):
    project_dir = tmp_path / "project"
    store = ProjectStorage(project_dir)
    project = Project.create(id="PRJ-1", name="test", workspace_path=str(tmp_path))
    store.save_project_meta(project)
    project_dir_str = str(project_dir)

    def run(*args: str):
        try:
            main(["--project", project_dir_str, *args])
        except SystemExit as e:
            return e.code, capsys.readouterr()
        return 0, capsys.readouterr()

    run.project_dir = project_dir_str
    run.store = store
    return run


class TestStats:
    def test_stats_no_runs(self, cli):
        code, out = cli("issue", "create", "No runs yet")
        issue_id = out.out.strip().split()[1].rstrip(":")
        code, out = cli("stats", issue_id)
        assert code == 0
        assert "0 runs" in out.out.lower() or "no runs" in out.out.lower()

    def test_stats_with_run_data(self, cli):
        code, out = cli("issue", "create", "Has stats")
        issue_id = out.out.strip().split()[1].rstrip(":")

        # Write fake stats
        stats_dir = cli.store.issues_dir / issue_id / "stats"
        stats_dir.mkdir(parents=True)
        (stats_dir / "run-001.json").write_text(json.dumps({
            "success": True,
            "cost_usd": 0.42,
            "duration_ms": 15000,
            "attempts": 2,
            "details": [{"num_turns": 5, "usage": {"input_tokens": 1000, "output_tokens": 500}}],
        }))

        code, out = cli("stats", issue_id)
        assert code == 0
        assert "$0.42" in out.out or "0.42" in out.out

    def test_stats_project_summary(self, cli):
        cli("issue", "create", "Issue A")
        cli("issue", "create", "Issue B")
        code, out = cli("stats")
        assert code == 0
        assert "2" in out.out

    def test_stats_not_found(self, cli):
        code, out = cli("stats", "ISS-nope")
        assert code == 1
