from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime, timezone


class IssueStatus(str, Enum):
    BACKLOG = "backlog"
    PLANNING = "planning"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    AGENT_DONE = "agent_done"
    HUMAN_DONE = "human_done"
    FAILED = "failed"
    REJECTED = "rejected"


VALID_TRANSITIONS = {
    IssueStatus.BACKLOG: {IssueStatus.PLANNING, IssueStatus.TODO},
    IssueStatus.PLANNING: {IssueStatus.TODO, IssueStatus.BACKLOG},
    IssueStatus.TODO: {IssueStatus.IN_PROGRESS, IssueStatus.BACKLOG},
    IssueStatus.IN_PROGRESS: {IssueStatus.AGENT_DONE, IssueStatus.FAILED, IssueStatus.TODO},
    IssueStatus.AGENT_DONE: {IssueStatus.HUMAN_DONE, IssueStatus.REJECTED},
    IssueStatus.FAILED: {IssueStatus.IN_PROGRESS, IssueStatus.TODO},
    IssueStatus.REJECTED: {IssueStatus.TODO},
    IssueStatus.HUMAN_DONE: set(),
}


class IssuePriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Issue:
    id: str
    title: str
    status: IssueStatus = IssueStatus.BACKLOG
    priority: IssuePriority = IssuePriority.MEDIUM
    assignee: str | None = None
    workspace: str = "default"
    blocks: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    spec_ref: str | None = None
    run_ids: list[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    source: str = "human"
    parent_id: str | None = None

    @classmethod
    def create(cls, id: str, title: str, priority: str = "medium", labels: list[str] | None = None) -> Issue:
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=id, title=title,
            priority=IssuePriority(priority),
            labels=labels or [],
            created_at=now, updated_at=now,
        )

    def move_to(self, new_status: IssueStatus) -> None:
        if new_status not in VALID_TRANSITIONS.get(self.status, set()):
            raise ValueError(f"Invalid transition: {self.status} -> {new_status}")
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_blocker(self, issue_id: str) -> None:
        if issue_id not in self.blocked_by:
            self.blocked_by.append(issue_id)

    def remove_blocker(self, issue_id: str) -> None:
        if issue_id in self.blocked_by:
            self.blocked_by.remove(issue_id)

    def is_blocked(self) -> bool:
        return len(self.blocked_by) > 0

    def to_json(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["priority"] = self.priority.value
        return d

    @classmethod
    def from_json(cls, data: dict) -> Issue:
        data = dict(data)
        data["status"] = IssueStatus(data["status"])
        data["priority"] = IssuePriority(data["priority"])
        return cls(**data)


@dataclass
class BoardColumn:
    id: str
    name: str
    issues: list[str] = field(default_factory=list)


# The 6 visible board columns (planning/failed/rejected are hidden states)
BOARD_COLUMNS = [
    ("backlog", "Backlog"),
    ("todo", "Todo"),
    ("in_progress", "In Progress"),
    ("agent_done", "Agent Done"),
    ("rejected", "Rejected"),
    ("human_done", "Human Done"),
]


@dataclass
class Board:
    columns: list[BoardColumn] = field(default_factory=list)

    @classmethod
    def create(cls) -> Board:
        cols = [BoardColumn(id=cid, name=cname) for cid, cname in BOARD_COLUMNS]
        return cls(columns=cols)

    def get_column(self, column_id: str) -> BoardColumn:
        for col in self.columns:
            if col.id == column_id:
                return col
        raise ValueError(f"Column not found: {column_id}")

    def add_issue(self, issue_id: str, column_id: str) -> None:
        col = self.get_column(column_id)
        if issue_id not in col.issues:
            col.issues.append(issue_id)

    def move_issue(self, issue_id: str, to_column_id: str) -> None:
        for col in self.columns:
            if issue_id in col.issues:
                col.issues.remove(issue_id)
                break
        self.get_column(to_column_id).issues.append(issue_id)


@dataclass
class Project:
    id: str
    name: str
    workspaces: list[str] = field(default_factory=list)
    created_at: str = ""
    key: str = "ISS"

    @classmethod
    def create(cls, id: str, name: str, workspace_path: str, key: str = "ISS") -> Project:
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=id,
            name=name,
            workspaces=[workspace_path],
            created_at=now,
            key=key,
        )
