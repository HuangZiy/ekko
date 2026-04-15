---
name: harness
description: "Ekko — AI-driven development with kanban issue management. Use this skill when the user wants to: create or manage development tasks/issues, plan features or bug fixes, run automated coding agents, review agent work (approve/reject), manage projects and workspaces, start the kanban Web UI, split issues into sub-issues, or view statistics. Trigger on mentions of: issues, tasks, kanban, board, sprint, backlog, planning, review, approve, reject, harness, ekko, split, sub-issue, or when the user describes work that should be tracked as issues."
---

# Ekko — AI-Driven Development with Kanban

Turn user requirements into tracked issues, execute them with AI agents, and review results on a kanban board.

## When to Use

- User describes a feature, bug fix, or task → create issue(s)
- User wants to plan a complex feature → brainstorm and split into sub-issues
- User wants to see task status → show board or issue list
- User wants to start/stop agent execution → run `ekko run`
- User wants to review agent work → guide through approve/reject flow
- User says "start the board" or "open kanban" → run `ekko serve`
- User wants cost/duration stats → run `ekko stats`

## Core Concepts

Issues flow through a kanban board:

```
Backlog → Planning → Todo → In Progress → Agent Done → Human Done
                               ↑               │
                               └── Failed ─────┘
                          ↑                    │
                          └── Rejected ────────┘
```

- **Agent Done**: Agent finished + evidence collected. Needs human review.
- **Human Done**: Human approved. Terminal state. Unlocks dependent issues.
- **Rejected**: Human rejected with feedback. Goes back to Todo for rework.

Issues can have `blocks` / `blocked_by` dependencies. The scheduler only picks up unblocked Todo issues.

**Parent/Child Issues**: Complex issues can be split into child issues with `parent_id`. Children form a serial dependency chain via `blocked_by`. The parent is blocked until all children complete.

## CLI Reference

All commands use the active project. Set one with `ekko init`, `ekko project create`, or `ekko project switch`.

### Initialize Project

```bash
ekko init                                      # Interactive: prompts for name and key prefix
ekko init --name "my-project" --key PRJ        # Non-interactive
```

Creates `.harness/` structure in the current directory, registers workspace, creates board.

### Project Management

```bash
ekko project create "项目名" ./workspace --key EKO  # Create project + link workspace
ekko project list                                   # List all projects (* = active)
ekko project switch PRJ-abc123                      # Switch active project
ekko project show                                   # Show project details + issue counts
ekko project update --name "新名" --key NEW         # Update project settings
ekko project delete PRJ-abc123                      # Delete a project
```

### Issue Management

```bash
ekko issue create "标题" --label bug --priority high   # Create issue
ekko issue create "子任务" \
  --parent-id EKO-15 \                                 # Set parent issue
  --blocked-by EKO-16 \                                # Set dependency (repeatable)
  --description "详细描述" \                            # Write content.md
  --plan "- [ ] Step 1\n- [ ] Step 2" \                # Write plan.md
  --source agent                                       # Mark as agent-created
ekko issue list                                        # List all issues
ekko issue list --status todo                          # Filter by status
ekko issue show EKO-15                                 # Show issue details + content
ekko issue move EKO-15 todo                            # Move issue status
ekko issue delete EKO-15                               # Delete issue
```

Statuses: `backlog`, `planning`, `todo`, `in_progress`, `agent_done`, `human_done`, `failed`, `rejected`
Priorities: `low`, `medium`, `high`, `urgent`

### Board

```bash
ekko board                        # Kanban overview (issues grouped by column)
ekko board move EKO-15 todo       # Move issue to a board column
```

### Planning

```bash
ekko plan "增加后台管理系统"       # Brainstorm → create issues with dependencies
ekko plan-issue EKO-15            # Run planning agent for a specific issue
```

### Execution

```bash
ekko run                          # Execute all todo + unblocked issues (sequential)
ekko run EKO-15                   # Execute a specific issue
```

Each issue execution: Ralph agent implements → build/test backpressure → git commit → evidence collection → incremental eval.

### Review

```bash
ekko review EKO-15 --approve                          # Approve → Human Done
ekko review EKO-15 --reject --comment "缺少loading"    # Reject → Todo with feedback
```

### Statistics

```bash
ekko stats                        # Project summary (issues, runs, total cost)
ekko stats EKO-15                 # Single issue stats (cost, duration, runs)
```

### Scheduler

```bash
ekko scheduler start              # Auto-dispatch ready issues (foreground, polls)
ekko scheduler status             # Show ready issues and current state
ekko scheduler once               # Run a single poll cycle and exit
```

### Web UI

```bash
ekko serve --dev                  # Dev mode: Vite HMR + FastAPI (localhost:5173 + :8080)
ekko serve                        # Production: serve built assets on :8080
```

### Migration

```bash
ekko migrate                      # Convert fix_plan.md → issues
ekko migrate --fix-plan ./path/to/fix_plan.md
```

## Batch API (for AI-driven splitting)

When splitting a parent issue into multiple child issues, use the batch endpoint:

```
POST /api/projects/{project_id}/issues/batch
```

```json
{
  "parent_id": "EKO-15",
  "issues": [
    {"title": "子任务1", "description": "描述", "plan": "- [ ] Step 1", "priority": "medium"},
    {"title": "子任务2", "description": "描述", "plan": "- [ ] Step 2"},
    {"title": "子任务3", "description": "描述"}
  ],
  "chain_dependencies": true
}
```

Behavior:
- Creates child issues with `parent_id` set, `source=agent`, `labels` inheriting parent + `["planned"]`
- `chain_dependencies=true`: each child `blocked_by` the previous one (serial chain)
- Parent's `blocked_by` set to all children
- All children enter `backlog` column

## Workflow Patterns

### Pattern 1: User describes a single task

```
User: "修复页面布局问题"
→ ekko issue create "修复页面布局问题" --label bug --priority high
→ ekko run EKO-xxx
→ (agent executes, produces evidence)
→ ekko review EKO-xxx --approve
```

### Pattern 2: AI-driven issue splitting (complex feature)

```
User: "增加用户通知系统，支持站内通知和 WebSocket 推送"
→ ekko issue create "增加用户通知系统" --priority high --description "..."
→ (AI brainstorms and splits into sub-issues)
→ ekko issue create "通知数据模型" --parent-id EKO-15 --plan "..." --source agent
→ ekko issue create "通知存储层" --parent-id EKO-15 --blocked-by EKO-16 --plan "..." --source agent
→ ekko issue create "WebSocket 推送" --parent-id EKO-15 --blocked-by EKO-17 --plan "..." --source agent
→ (sub-issues appear on board in backlog, user drags to todo/run as needed)
```

Or use the batch API for efficiency:

```
→ POST /api/projects/{id}/issues/batch with parent_id + issues array + chain_dependencies=true
```

### Pattern 3: User wants to see status

```
User: "现在进度怎么样"
→ ekko board
→ ekko stats
```

### Pattern 4: User rejects agent work

```
User: "登录页缺少loading状态"
→ ekko review EKO-xxx --reject --comment "登录页缺少loading状态，密码框需要显示/隐藏切换"
→ (issue goes back to Todo with feedback appended)
→ ekko run EKO-xxx (re-execute with feedback context)
```

## Important Notes

- Always ensure a project exists before creating issues. Use `ekko init` in the project directory or check with `ekko project list`.
- The `ekko run` command uses Claude Agent SDK internally — it spawns agent subprocesses.
- Evidence (git diff, build output, screenshots) is automatically collected when an issue reaches Agent Done.
- Port 3000 is reserved by the system — never kill processes on that port.
- The `ekko serve --dev` provides drag-drop kanban, issue details, and review panels.
- When splitting issues, the AI decides the decomposition — Ekko only provides atomic operations (create issue, set dependencies).
