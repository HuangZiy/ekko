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


class TestBatchCreate:
    def test_batch_create_with_chain(self, client):
        c, pid, store = client
        # Create parent issue first
        resp = c.post(f"/api/projects/{pid}/issues", json={"title": "Parent"})
        parent_id = resp.json()["id"]

        resp = c.post(f"/api/projects/{pid}/issues/batch", json={
            "parent_id": parent_id,
            "issues": [
                {"title": "Child 1", "description": "First task", "plan": "- [ ] Do A"},
                {"title": "Child 2", "description": "Second task", "plan": "- [ ] Do B"},
                {"title": "Child 3", "description": "Third task"},
            ],
            "chain_dependencies": True,
        })
        assert resp.status_code == 200
        children = resp.json()["created"]
        assert len(children) == 3

        # Verify serial chain: child 2 blocked by child 1, child 3 blocked by child 2
        child1 = store.load_issue(children[0]["id"])
        child2 = store.load_issue(children[1]["id"])
        child3 = store.load_issue(children[2]["id"])

        assert child1.blocked_by == []
        assert children[0]["id"] in child2.blocked_by
        assert children[1]["id"] in child3.blocked_by

        # All children have parent_id set
        assert child1.parent_id == parent_id
        assert child2.parent_id == parent_id
        assert child3.parent_id == parent_id

        # All children are source=agent
        assert child1.source == "agent"

        # Parent is blocked by all children
        parent = store.load_issue(parent_id)
        for ch in children:
            assert ch["id"] in parent.blocked_by

        # Plans saved
        assert "Do A" in store.load_issue_plan(children[0]["id"])
        assert "Do B" in store.load_issue_plan(children[1]["id"])

    def test_batch_create_no_chain(self, client):
        c, pid, store = client
        resp = c.post(f"/api/projects/{pid}/issues", json={"title": "Parent2"})
        parent_id = resp.json()["id"]

        resp = c.post(f"/api/projects/{pid}/issues/batch", json={
            "parent_id": parent_id,
            "issues": [
                {"title": "Independent 1"},
                {"title": "Independent 2"},
            ],
            "chain_dependencies": False,
        })
        assert resp.status_code == 200
        children = resp.json()["created"]

        child1 = store.load_issue(children[0]["id"])
        child2 = store.load_issue(children[1]["id"])
        assert child1.blocked_by == []
        assert child2.blocked_by == []

    def test_batch_create_parent_not_found(self, client):
        c, pid, store = client
        resp = c.post(f"/api/projects/{pid}/issues/batch", json={
            "parent_id": "NONEXISTENT-99",
            "issues": [{"title": "Orphan"}],
        })
        assert resp.status_code == 404
