---
name: harness
description: "Ekko — AI-driven development with kanban issue management. Use this skill when the user wants to: create or manage development tasks/issues, plan features or bug fixes, run automated coding agents, review agent work (approve/reject), manage projects and workspaces, start the kanban Web UI, or migrate from fix_plan.md. Trigger on mentions of: issues, tasks, kanban, board, sprint, backlog, planning, review, approve, reject, harness, ekko, or when the user describes work that should be tracked as issues."
---

# Ekko — AI-Driven Development with Kanban

Turn user requirements into tracked issues, execute them with AI agents, and review results on a kanban board.

## When to Use

- User describes a feature, bug fix, or task → create issue(s)
- User wants to plan a complex feature → run `harness plan` to brainstorm and create issues with dependencies
- User wants to see task status → show board or issue list
- User wants to start/stop agent execution → run `harness run`
- User wants to review agent work → guide through approve/reject flow
- User says "start the board" or "open kanban" → run `harness serve`

## Core Concepts

Issues flow through a kanban board:

```
Backlog → Todo → In Progress → Agent Done → Human Done
                    ↑               │
                    └── Failed ─────┘
               ↑                    │
               └── Rejected ────────┘
```

- **Agent Done**: Agent finished + evidence collected. Needs human review.
- **Human Done**: Human approved. Terminal state. Unlocks dependent issues.
- **Rejected**: Human rejected with feedback. Goes back to Todo for rework.

Issues can have `blocks` / `blocked_by` dependencies. The scheduler only picks up unblocked Todo issues.

## CLI Reference

All commands use the active project. Set one with `harness project create` or `harness project switch`.

### Project Management

```bash
harness project create "项目名" ./workspace    # Create project + link workspace
harness project list                           # List all projects (* = active)
harness project switch PRJ-abc123              # Switch active project
harness project show                           # Show project details + issue counts
```

### Issue Management

```bash
harness issue create "标题" --label bug --priority high   # Create issue
harness issue list                                        # List all issues
harness issue list --status todo                          # Filter by status
harness issue show ISS-abc123                             # Show issue details + content
harness issue move ISS-abc123 todo                        # Move issue status
```

Statuses: `backlog`, `todo`, `in_progress`, `agent_done`, `human_done`, `failed`, `rejected`
Priorities: `low`, `medium`, `high`, `urgent`

### Planning (Interactive)

```bash
harness plan "增加后台管理系统"    # Brainstorm → create issues with dependencies
```

The planner agent will analyze the requirement, create specs, and produce a batch of issues with `blocks`/`blocked_by` relationships.

### Execution

```bash
harness run           # Execute all todo + unblocked issues (sequential)
harness run ISS-abc123         # Execute a specific issue
```

Each issue execution: Ralph agent implements → build/test backpressure → git commit → evidence collection → incremental eval.

### Review

```bash
harness review ISS-abc123 --approve                          # Approve → Human Done
harness review ISS-abc123 --reject --comment "缺少loading"    # Reject → Todo with feedback
```

### Web UI

```bash
harness serve --dev            # Dev mode: Vite HMR + FastAPI (localhost:5173 + :8080)
harness serve                  # Production: serve built assets on :8080
```

### Migration

```bash
harness migrate                # Convert fix_plan.md → issues
harness migrate --fix-plan ./path/to/fix_plan.md
```

## Workflow Patterns

### Pattern 1: User describes a single task

```
User: "修复页面布局问题"
→ harness issue create "修复页面布局问题" --label bug --priority high
→ harness run ISS-xxx
→ (agent executes, produces evidence)
→ harness review ISS-xxx --approve
```

### Pattern 2: User describes a complex feature

```
User: "增加后台管理系统，支持用户管理和权限认证"
→ harness plan "增加后台管理系统，支持用户管理和权限认证"
→ (planner creates multiple issues with dependencies)
→ harness run
→ (agent executes issues in dependency order)
→ harness review ISS-xxx --approve (for each)
```

### Pattern 3: User wants to see status

```
User: "现在进度怎么样"
→ harness issue list
→ harness project show
```

### Pattern 4: User rejects agent work

```
User: "登录页缺少loading状态"
→ harness review ISS-xxx --reject --comment "登录页缺少loading状态，密码框需要显示/隐藏切换"
→ (issue goes back to Todo with feedback appended)
→ harness run ISS-xxx (re-execute with feedback context)
```

## Important Notes

- Always ensure a project exists before creating issues. Check with `harness project list`.
- The `harness run` command uses Claude Agent SDK internally — it spawns agent subprocesses.
- Evidence (git diff, build output, screenshots) is automatically collected when an issue reaches Agent Done.
- Port 3000 is reserved by the system — never kill processes on that port.
- The `harness serve --dev` provides drag-drop kanban, issue details, and review panels.
