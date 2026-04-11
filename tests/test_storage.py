from core.models import Issue
from core.storage import ProjectStorage


def test_save_and_load_issue(tmp_path):
    store = ProjectStorage(tmp_path / "project")
    issue = Issue.create(title="test issue")
    store.save_issue(issue)
    loaded = store.load_issue(issue.id)
    assert loaded.title == "test issue"


def test_save_issue_markdown(tmp_path):
    store = ProjectStorage(tmp_path / "project")
    issue = Issue.create(title="test")
    store.save_issue(issue)
    store.save_issue_content(issue.id, "# Description\n\nSome content")
    content = store.load_issue_content(issue.id)
    assert "# Description" in content


def test_list_issues(tmp_path):
    store = ProjectStorage(tmp_path / "project")
    store.save_issue(Issue.create(title="A"))
    store.save_issue(Issue.create(title="B"))
    issues = store.list_issues()
    assert len(issues) == 2
