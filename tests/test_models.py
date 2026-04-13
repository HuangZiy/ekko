import pytest
from core.models import Issue, IssueStatus, IssuePriority, Project, Board


def test_create_issue():
    issue = Issue.create(id="ISS-1", title="实现登录页", priority="high", labels=["auth"])
    assert issue.id == "ISS-1"
    assert issue.status == IssueStatus.BACKLOG
    assert issue.priority == IssuePriority.HIGH
    assert issue.blocks == []
    assert issue.blocked_by == []


def test_issue_status_transition():
    issue = Issue.create(id="ISS-1", title="test")
    issue.move_to(IssueStatus.TODO)
    assert issue.status == IssueStatus.TODO
    issue.move_to(IssueStatus.IN_PROGRESS)
    assert issue.status == IssueStatus.IN_PROGRESS


def test_issue_invalid_transition():
    issue = Issue.create(id="ISS-1", title="test")
    with pytest.raises(ValueError):
        issue.move_to(IssueStatus.HUMAN_DONE)  # can't skip to done


def test_issue_dependency():
    a = Issue.create(id="ISS-1", title="A")
    b = Issue.create(id="ISS-2", title="B")
    b.add_blocker(a.id)
    assert a.id in b.blocked_by
    assert b.is_blocked()


def test_issue_serialization():
    issue = Issue.create(id="ISS-1", title="test", labels=["bug"])
    data = issue.to_json()
    loaded = Issue.from_json(data)
    assert loaded.id == issue.id
    assert loaded.title == issue.title


# --- Project tests ---

def test_create_project():
    project = Project.create(id="PRJ-1", name="技术博客", workspace_path="/tmp/workspace")
    assert project.id == "PRJ-1"
    assert project.name == "技术博客"
    assert len(project.workspaces) == 1


# --- Explicit ID tests ---

def test_issue_create_with_explicit_id():
    issue = Issue.create(id="ISS-1", title="Fix login")
    assert issue.id == "ISS-1"

def test_project_create_with_key():
    project = Project.create(id="PRJ-1", name="Blog", workspace_path="/tmp/ws", key="BLOG")
    assert project.id == "PRJ-1"
    assert project.key == "BLOG"

def test_project_create_default_key():
    project = Project.create(id="PRJ-2", name="My Project", workspace_path="/tmp/ws")
    assert project.key == "ISS"  # default prefix


# --- Board tests ---

def test_board_columns():
    board = Board.create()
    assert len(board.columns) == 7
    assert board.columns[0].id == "backlog"
    assert board.columns[-1].id == "human_done"


def test_board_add_issue():
    board = Board.create()
    board.add_issue("ISS-001", "backlog")
    assert "ISS-001" in board.columns[0].issues


def test_board_move_issue():
    board = Board.create()
    board.add_issue("ISS-001", "backlog")
    board.move_issue("ISS-001", "todo")
    assert "ISS-001" not in board.columns[0].issues
    assert "ISS-001" in board.get_column("todo").issues
