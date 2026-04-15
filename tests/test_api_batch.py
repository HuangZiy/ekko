"""Tests for enhanced issue creation API."""
import pytest
from fastapi.testclient import TestClient
from core.models import Project
from core.storage import ProjectStorage


@pytest.fixture
def app(tmp_path):
    """Create a FastAPI test app with a tmp project."""
    from server.app import create_app
    harness_root = tmp_path / "harness"
    harness_root.mkdir()

    app = create_app(harness_root=harness_root)

    # Create a project
    from core.storage import PlatformStorage
    platform = PlatformStorage(harness_root)
    project, store = platform.create_project(
        name="test", workspace_path=str(tmp_path), key="TST"
    )

    return app, project.id, store


@pytest.fixture
def client(app):
    app_instance, project_id, store = app
    return TestClient(app_instance), project_id, store


class TestCreateIssueWithPlan:
    def test_create_with_plan(self, client):
        c, pid, store = client
        resp = c.post(f"/api/projects/{pid}/issues", json={
            "title": "Test issue",
            "plan": "- [ ] Step 1\n- [ ] Step 2",
        })
        assert resp.status_code == 200
        issue_id = resp.json()["id"]

        plan = store.load_issue_plan(issue_id)
        assert "Step 1" in plan
        assert "Step 2" in plan

    def test_create_with_source_agent(self, client):
        c, pid, store = client
        resp = c.post(f"/api/projects/{pid}/issues", json={
            "title": "Agent issue",
            "source": "agent",
        })
        assert resp.status_code == 200
        issue_id = resp.json()["id"]

        issue = store.load_issue(issue_id)
        assert issue.source == "agent"

    def test_create_without_plan_no_plan_file(self, client):
        c, pid, store = client
        resp = c.post(f"/api/projects/{pid}/issues", json={
            "title": "No plan issue",
        })
        assert resp.status_code == 200
        issue_id = resp.json()["id"]

        plan = store.load_issue_plan(issue_id)
        assert plan is None or plan == ""
