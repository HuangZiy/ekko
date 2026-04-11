# Harness Kanban 系统设计

> 将 fix_plan.md 扁平 checklist 升级为带状态流转、依赖关系、多 agent 并行的 Issue 看板系统。

## 背景

当前 harness 用 `fix_plan.md` 管理任务，存在以下限制：
- 扁平列表，无依赖关系，无法表达 "A 完成后才能做 B"
- 单 agent 串行，无法并行执行无依赖的任务
- 无人类审核环节，agent 说 done 就 done
- 无可视化，只能看 markdown 文件
- 任务状态只有两种（`- [ ]` / `- [x]`），无法表达 planning / review / rejected

## 参考项目

- **vibe-kanban** — 本地 Web UI 看板，管理 coding agent 的工作。Vite + React + Radix + dnd-kit + Zustand
- **multica** — 多 agent 平台，Issue 分配给 agent 自动执行。Next.js + Go + PostgreSQL
- **Linear** — 产品级 Issue 管理，状态流转 + 依赖关系 + 优先级

## 核心概念

```
Platform
├── Project (博客项目、后台系统...)
│   ├── Workspace[] (workspace/、admin-workspace/...)
│   ├── Board (看板)
│   │   ├── Column: Backlog → Planning → Todo → In Progress → Agent Done → Human Done
│   │   └── Issue[] (带依赖关系的任务卡片)
│   └── Agent Pool[] (可并行执行的 agent 实例)
```

### 从当前架构的映射

| 当前 | 新系统 |
|------|--------|
| `fix_plan.md` 的 `- [ ]` | Issue (Backlog / Todo) |
| `fix_plan.md` 的 `- [x]` | Issue (Human Done) |
| Planner agent | Planning 阶段（可选，产出一批 Issue） |
| Ralph Loop 单次循环 | Agent 领取一个 Issue 执行 |
| Evaluator | Review（Issue 完成后自动触发增量评估） |
| `state.json` | Issue 状态 + Board 状态 |
| `workspace/` | Workspace 实例 |

## 状态流转

```
Backlog → Planning → Todo → In Progress → Agent Done → Human Done
                      ↑         ↑              │
                      │         └── Failed ─────┘
                      └──────── Rejected ───────┘
```

| 状态 | 含义 | 触发条件 |
|------|------|----------|
| **Backlog** | 用户创建或 Planner 产出，未排期 | 手动创建 / `harness plan` 产出 |
| **Planning** | Planner agent 正在分析细化 | 可选步骤，`harness plan` 触发 |
| **Todo** | 已排期，等待 agent 领取 | Planning 完成 / 手动移入 / 直接创建 |
| **In Progress** | Agent 正在实现 | 空闲 agent 自动领取 |
| **Agent Done** | Agent 完成，附带证据等待人类审核 | Ralph 完成 + 增量评估通过 |
| **Human Done** | 人类审核通过，真正结束 | 人类在 Web UI 或 CLI 批准 |
| **Failed** | 增量评估未通过，自动回到 In Progress 重试 | Evaluator 发现 FAIL 项 |
| **Rejected** | 人类审核不通过，追加反馈打回 Todo | 人类在 Web UI 或 CLI 打回 |

## 数据模型

### 目录结构

```
.harness/
├── config.json                    ← 全局配置（模型、并行数、阈值）
├── projects/
│   └── <project-id>/
│       ├── project.json           ← 项目元数据（名称、workspace 列表）
│       ├── board.json             ← 看板状态（列定义、Issue 排序）
│       ├── issues/
│       │   ├── <issue-id>.json    ← 索引：状态、依赖、assignee、优先级
│       │   └── <issue-id>.md      ← 内容：描述、验收标准、agent 日志、审核反馈
│       ├── specs/                 ← Planner 产出的功能规格
│       │   └── *.md
│       ├── workspaces/
│       │   ├── default.json       ← workspace 配置（路径、git 分支）
│       │   └── admin.json
│       ├── agents/
│       │   └── <agent-id>.json    ← agent 状态（idle/busy、当前任务）
│       └── runs/
│           └── <run-id>/          ← 每次执行的日志、截图、统计
│               ├── harness.log
│               ├── screenshots/
│               ├── diff.patch
│               └── stats.json
```

### Issue JSON (`issues/<id>.json`)

```json
{
  "id": "ISS-001",
  "title": "实现权限认证系统",
  "status": "in_progress",
  "priority": "high",
  "assignee": "agent-1",
  "workspace": "default",
  "blocks": ["ISS-003", "ISS-004"],
  "blocked_by": [],
  "labels": ["auth", "backend"],
  "created_at": "2026-04-11T10:00:00Z",
  "updated_at": "2026-04-11T12:30:00Z",
  "spec_ref": "specs/auth.md",
  "run_ids": ["run-001", "run-002"],
  "retry_count": 0,
  "max_retries": 3
}
```

### Issue Markdown (`issues/<id>.md`)

```markdown
# ISS-001: 实现权限认证系统

## 描述

JWT + bcrypt 单用户认证，Middleware 路由保护。
参考规格：`specs/auth.md`

## 验收标准

- 登录页面可用
- JWT token 正确签发和验证
- 未认证请求重定向到登录页

## Agent 日志

### Run run-001 (agent-1, 2026-04-11 12:30)

实现了 /api/auth/login 路由，JWT 签发和验证中间件。

![login-page](../runs/run-001/screenshots/login-page.jpeg)

### Agent Done 证据 (2026-04-11 14:30)

**Git Diff:**
```
+ app/admin/login/page.tsx (new)
+ lib/auth/jwt.ts (new)
M middleware.ts
```

**Build:** ✅ npm run build — 0 errors

**截图:**
![login](../runs/run-002/screenshots/login.jpeg)
![dashboard](../runs/run-002/screenshots/dashboard.jpeg)

**增量评估:** PASS

## Human Review

### Review #1 (2026-04-11 15:00) — REJECTED

**缺陷:**
- 登录页没有 loading 状态
- 密码输入框没有显示/隐藏切换

**优化点:**
- 登录失败的错误提示太模糊，应该区分"密码错误"和"用户不存在"

**附件:**
![feedback](../runs/run-002/reviews/feedback-001.png)

### Review #2 (2026-04-11 17:00) — APPROVED

LGTM
```

### Project JSON (`project.json`)

```json
{
  "id": "blog-project",
  "name": "技术博客",
  "workspaces": [
    {"id": "default", "path": "/.../workspace", "branch": "main"},
    {"id": "admin", "path": "/Users/.../admin-workspace", "branch": "feature/admin"}
  ],
  "agents": [
    {"id": "agent-1", "model": "claude-opus-4-6", "max_turns": 150, "max_budget": 5.0},
    {"id": "agent-2", "model": "claude-opus-4-6", "max_turns": 150, "max_budget": 5.0}
  ],
  "settings": {
    "max_parallel_agents": 2,
    "eval_threshold": 7,
    "max_retries": 3,
    "auto_eval": true
  }
}
```

### Board JSON (`board.json`)

```json
{
  "columns": [
    {"id": "backlog", "name": "Backlog", "issues": ["ISS-005", "ISS-006"]},
    {"id": "planning", "name": "Planning", "issues": []},
    {"id": "todo", "name": "Todo", "issues": ["ISS-003", "ISS-004"]},
    {"id": "in_progress", "name": "In Progress", "issues": ["ISS-001"]},
    {"id": "agent_done", "name": "Agent Done", "issues": ["ISS-002"]},
    {"id": "human_done", "name": "Human Done", "issues": []}
  ]
}
```

## 执行引擎

### 并行 Agent 调度

```python
async def run_board(project: Project):
    """主循环：持续调度可执行的 Issue 给空闲 Agent"""
    while True:
        # 找出所有可执行的 Issue（Todo 状态 + 无 blocker）
        ready = [i for i in project.issues
                 if i.status == "todo"
                 and all(dep.status == "human_done" for dep in i.blocked_by)]

        # 分配给空闲 agent
        for issue in ready:
            agent = project.get_idle_agent()
            if not agent:
                break
            asyncio.create_task(run_issue(agent, issue, project))

        # 检查是否全部完成
        if all(i.status == "human_done" for i in project.issues):
            break
        await asyncio.sleep(5)  # 轮询间隔
```

### 单 Issue 执行流程

```python
async def run_issue(agent: Agent, issue: Issue, project: Project):
    issue.status = "in_progress"
    issue.assignee = agent.id
    run = create_run(issue, agent)

    try:
        # Ralph cycle（当前 run_one_ralph_cycle 的升级版）
        result = await ralph_execute(agent, issue, project)
        run.save_result(result)

        # 收集 Agent Done 证据
        evidence = await collect_evidence(issue, project)
        issue.append_evidence(evidence)

        # 增量评估
        eval_result = await incremental_eval(issue, project)
        run.save_eval(eval_result)

        if eval_result.passed:
            issue.status = "agent_done"  # 等待人类审核
            notify_human(issue)
        else:
            issue.retry_count += 1
            if issue.retry_count < issue.max_retries:
                issue.status = "in_progress"  # 自动重试
                issue.append_comment(eval_result.feedback)
            else:
                issue.status = "agent_done"  # 超过重试次数，交给人类判断
                issue.append_comment("超过最大重试次数，请人工审核")

    except Exception as e:
        issue.status = "todo"  # 异常回到队列
        issue.append_comment(f"执行异常: {e}")
        agent.status = "idle"
```

### Agent Done 证据收集

```python
async def collect_evidence(issue: Issue, project: Project) -> Evidence:
    workspace = project.get_workspace(issue.workspace)

    # Git diff
    diff = run_command(f"git diff HEAD~1 --stat", cwd=workspace.path)
    diff_patch = run_command(f"git diff HEAD~1", cwd=workspace.path)

    # Build 结果
    build = run_command("npm run build 2>&1 | tail -20", cwd=workspace.path)

    # 截图（启动 dev server + Playwright）
    screenshots = await take_screenshots(workspace, issue)

    # 增量评估报告
    eval_report = await run_incremental_eval(issue)
return Evidence(
        diff_stat=diff,
        diff_patch=diff_patch,
        build_output=build,
        screenshots=screenshots,
        eval_report=eval_report,
        timestamp=now(),
    )
```

### Human Review 流程

```python
# Web UI 或 CLI 触发
async def human_review(issue: Issue, approved: bool, feedback: str = None, attachments: list = None):
    review = Review(
        timestamp=now(),
        approved=approved,
        feedback=feedback,
        attachments=attachments,
    )
    issue.append_review(review)

    if approved:
        issue.status = "human_done"
        # 解锁被 block 的 issue
        for blocked_id in issue.blocks:
            blocked = get_issue(blocked_id)
            blocked.blocked_by.remove(issue.id)
            if not blocked.blocked_by and blocked.status == "backlog":
                blocked.status = "todo"  # 自动进入待办
    else:
        issue.status = "todo"  # 打回
        issue.retry_count = 0  # 重置重试计数
```

## Planning 流程（可选）

```bash
# 交互式 brainstorming → 产出一批带依赖关系的 Issue
harness plan "增加后台管理系统"

# 或者直接创建 Issue
harness issue create "修复首页文字压缩" --label bug --priority high\nPlanning 产出的 Issue 自动设置 `blocks` / `blocked_by` 依赖关系：

```
ISS-001: 权限认证系统
ISS-002: 后台 API 路由        ← blocked_by: [ISS-001]
ISS-003: 文章编辑器           ← blocked_by: [ISS-001, ISS-002]
ISS-004: 移动端适配           ← blocked_by: [ISS-003]
```

调度器自动按依赖顺序执行：ISS-001 先做，完成后 ISS-002 解锁，以此类推。无依赖的 Issue 可以并行。

## 前端技术栈

参考 vibe-kanban 选型：

| 层 | 选型 | 理由 |
|---|---|---|
| 构建 | Vite | 快速 HMR，vibe-kanban 同款 |
| 框架 | React 18 | 生态成熟，vibe-kanban 同款 |
| 路由 | TanStack Router | 类型安全，vibe-kanban 同款 |
| 状态 | Zustand | 轻量，vibe-kanban 同款 |
| UI 组件 | Radix UI | 无样式原语，vibe-kanban 同款 |
| 样式 | TailwindCSS | 原子 CSS，vibe-kanban 同款 |
| 拖拽 | @dnd-kit | 看板拖拽，vibe-kanban 同款 |
| 图标 | Lucide React | vibe-kanban 同款 |
| Markdown 编辑 | Lexical | 富文本编辑 Issue 内容，vibe-kanban 同款 |
| Diff 查看 | @git-diff-view/react | 代码变更审查，vibe-kanban 同款 |
| 动画 | Framer Motion | 拖拽/过渡动画 |
| 实时更新 | SSE | agent 执行状态推送 |
| 后端 | FastAPI (Python) | 跟 harness 同语言 |

### Web UI 页面

1. **Board 视图** — 看板拖拽，列：Backlog / Planning / Todo / In Progress / Agent Done / Human Done
2. **Issue 详情** — Markdown 渲染、图片、agent 日志、diff 查看、审核面板
3. **审核面板** — Approve / Reject 按钮 + 富文本反馈编辑器 + 截图上传
4. **Project 设置** — workspace 管理、agent 配置、阈值设置
5. **运行监控** — 实时 agent 执行日志、cost 统计

## CLI 命令

```bash
# 项目管理
harness project create "技术博客"
harness project list
harness project switch <id>

# 看板
harness board                          # CLI 看板视图
harness serve                          # 启动 Web UI (localhost:8080)

# Issue 管理
harness issue create "标题" --label bug --priority high
harness issue list [--status todo]
harness issue show ISS-001
harness issue move ISS-001 todo        # 手动移动状态

# Planning（可选）
harness plan "需求描述"                 # 交互式 brainstorming → 产出 Issues

# 执行
harness run                            # 自动调度所有
harness run ISS-001                    # 手动触发单个 Issue

# 审核
harness review ISS-001 --approve
harness review ISS-001 --reject --comment "缺少 loading 状态"

# Workspace
harness workspace add ./admin-workspace --name admin
harness workspace list
```

## 全量评估

在所有 Issue 进入 Agent Done / Human Done 后，可选触发一次全量评估：

```bash
harness eval --full                    # 四维度全量评估
```

全量评估发现的问题自动创建新 Issue 进入 Backlog。

## 迁移路径

从当前 harness 迁移：

1. `fix_plan.md` 的每个 `- [ ]` → 一个 Issue (Todo)
2. `fix_plan.md` 的每个 `- [x]` → 一个 Issue (Human Done)
3. `state.json` → Board 状态
4. `workspace/` → 默认 Workspace
5. `prompts/` → 保留，Ralph/Evaluator 的系统提示词不变
6. `harness.py` → 拆分为 `engine.py`（调度）+ `server.py`（Web UI）+ `cli.py`（命令行）
