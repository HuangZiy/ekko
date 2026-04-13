<p align="center">
  <img src="docs/assets/ekko-banner.svg" alt="Ekko" width="100%" />
</p>

<p align="center">
  <strong>Your next developer never sleeps.</strong>
</p>

<p align="center">
  AI-driven development harness with kanban issue management, multi-agent parallel execution, and human-in-the-loop review.
</p>

<p align="center">
  <a href="https://github.com/HuangZiy/ekko/actions"><img src="https://img.shields.io/github/actions/workflow/status/HuangZiy/ekko/ci.yml?style=for-the-badge&label=CI" alt="CI"></a>
  <a href="https://github.com/HuangZiy/ekko/stargazers"><img src="https://img.shields.io/github/stars/HuangZiy/ekko?style=for-the-badge" alt="Stars"></a>
  <a href="https://github.com/HuangZiy/ekko/blob/main/LICENSE"><img src="https://img.shields.io/github/license/HuangZiy/ekko?style=for-the-badge" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-≥3.11-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
</p>

<p align="center">
  <a href="https://huangziy.github.io/ekko/">Interactive Architecture →</a>
</p>

<p align="center">
  <a href="#what-is-ekko">English</a> · <a href="#什么是-ekko">中文</a>
</p>

---

## What is Ekko?

Ekko is an AI-powered development harness built on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk). Give it a one-line requirement, and it plans, implements, evaluates, and iterates — until a human approves the result.

Inspired by Anthropic's [three-agent architecture](https://www.anthropic.com/engineering/harness-design-long-running-apps) (Planner / Generator / Evaluator), the [Ralph Wiggum technique](https://ghuntley.com/ralph/) for single-task loops with build/test backpressure, and [vibe-kanban](https://g.com/BloopAI/vibe-kanban) for local board UI.

Unlike simple code-generation tools, Ekko manages the full lifecycle: breaking down requirements into dependency-aware issues, dispatching them to parallel agents, collecting evidence (git diff + build output + screenshots), and gating completion on human review.

## Features

| Feature | Description |
|---------|-------------|
| Kanban Board | 6-column board (Backlog → Todo → In Progress → Agent Done → Human Done) with drag-and-drop Web UI |
| Interactive Planning | Brainstorming agent decomposes a requirement into dependency-aware issues automatically |
| Multi-Agent Parallel | Scheduler dispatches unblocked issues to multiple agents running concurrently |
| Build/Test Backpressure | Agents must pass build and tests before marking work complete — no shortcuts |
| Human-in-the-Loop | Agent Done issues require human Approve/Reject with feedback before closing |
| Evidence Collection | Git diff, build output, Playwright screenshots bundled per issue for review |
| Checkpoint Resume | Interrupted tasks resume at the exact step — Ralph done but Eval crashed? Skips Ralph, reruns Eval |
| Real-time Web UI | React + Tailwind dashboard with SSE push, Markdown rendering, and review panels |
| CLI-first | Full CLI for project/issue/review/plan/run — scriptable and composable |

## Architecture

```
Requirement ("Add user auth")
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  Planner Agent                                           │
│  Interactive brainstorming → dependency-aware Issues      │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Kanban Board                                            │
│                                                          │
│  Backlog → Todo → In Progress → Agent Done → Human Done  │
│                     ↑                │                   │
│                     └── Failed ──────┘                   │
│                ↑                     │                   │
│                └── Rejected ─────────┘  (human rejects)  │
│                                                          │
│  Scheduler assigns Todo + unblocked → idle agents        │
│  Multiple agents run in parallel on independent issues   │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Per-Issue Execution                                     │
│                                                          │
│  1. Ralph Agent implements (build/test backpressure)     │
│  2. Incremental eval (verify this change only)           │
│  3. Collect evidence (git diff + build + screenshots)    │
│  4. Agent Done → await human review                      │
│  5. Approve → Human Done → unblock dependents            │
│     Reject  → append feedback → back to Todo             │
└──────────────────────────────────────────────────────────┘
```

> [View the interactive version →](https://huangziy.github.io/ekko/)

## Quick Install

```bash
git clone https://github.com/HuangZiy/ekko.git && cd ekko
uv pip install -e .
cd web && npm install && cd ..
```

After install, the `harness` command is available globally.

**Prerequisites:** Python ≥ 3.11, Node.js ≥ 20, [uv](https://github.com/astral-sh/uv), an `ANTHROPIC_API_KEY` environment variable.

## Getting Started

```bash
# 1. Create a project
harness project create "My App" ./workspace

# 2. Add issues
harness issue create "Implement user login" --label auth --priority high

# 3. Run — agents pick up todo issues automatically
harness run

# 4. Launch the Web UI to review
harness serve --dev    # http://localhost:5173
```

Or go from zero to issues in one shot:

```bash
harness plan "Build a dashboard with auth and analytics"   # brainstorm → issues
harness run                                                 # execute all
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `harness project create <name> <path>` | Create a new project with workspace |
| `harness project list` | List all projects |
| `harness project switch <id>` | Switch active project |
| `harness issue create <title> [--label] [--priority]` | Create an issue |
| `harness issue list [--status todo]` | List issues, optionally filtered |
| `harness issue show <id>` | Show issue details |
| `harness issue move <id> <status>` | Move issue to a status column |
| `harness review <id> --approve` | Approve an Agent Done issue |
| `harness review <id> --reject --comment "..."` | Reject with feedback |
| `harness plan "<requirement>"` | Interactive planning → auto-create issues |
| `harness plan-issue <id>` | Plan a single issue before execution |
| `harness run [<id>]` | Execute all ready issues (or a specific one) |
| `harness serve [--dev]` | Launch Web UI (dev mode with HMR) |
| `harness board` | Print board status to terminal |
| `harness migrate` | Convert fix_plan.md to issues |

## Project Structure

```
ekko/
├── harness.py              # Legacy entry point (backward-compatible)
├── config.py               # Global configuration
├── pyproject.toml
│
├── core/                   # Core domain logic
│   ├── models.py           # Issue / Board / Project data models
│   ├── storage.py          # JSON + Markdown file storage
│   ├── executor.py         # Issue-based Ralph executor
│   ├── ralph_loop.py       # Board-level orchestration + scheduling
│   ├── planner.py          # Planning agent (brainstorm → issues)
│   ├── evidence.py         # Evidence collection (diff, build, screenshots)
│   ├── review.py           # Human review (approve / reject)
│   ├── scheduler.py        # Parallel agent scheduler
│   └── migrate.py          # fix_plan.md → Issue migration
│
├── agents/                 # Claude Agent SDK wrappers
│   ├── planner.py          # Planner agent (interactive brainstorming)
│   ├── ralph_loop.py       # Ralph agent (single-task + backpressure)
│   └── evaluator.py        # Evaluator agent (incremental + full eval)
│
├── cli/                    # CLI entry point
│   └── main.py             # argparse subcommands
│
├── server/                 # FastAPI backend
│   ├── app.py              # App + route registration
│   ├── ws.py               # WebSocket events
│   └── routes/             # Issue / Board / Project / Review APIs
│
├── web/                    # Frontend (Vite + React 19)
│   └── src/
│       ├── App.tsx
│       ├── stores/         # Zustand state management
│       ├── hooks/          # SSE real-time updates
│       └── components/     # Board, Column, IssueCard, IssueDetail
│
├── prompts/                # Agent system prompts
│   ├── planner_system.md
│   ├── planning_prompt.md
│   ├── ralph_prompt.md
│   ├── evaluator_system.md
│   └── eval_criteria.md
│
├── tests/                  # Test suite
└── docs/                   # Documentation + interactive flowchart
```

## Issue Lifecycle

```
Backlog → Planning → Todo → In Progress → Agent Done → Human Done
                      ↑         ↑              │
                      │         └── Failed ─────┘
                      └──────── Rejected ───────┘
```

| Status | Meaning |
|--------|---------|
| Backlog | Created, not yet scheduled |
| Planning | Planner agent is analyzing (optional) |
| Todo | Waiting for an agent to pick up |
| In Progress | Agent is implementing |
| Agent Done | Agent finished — evidence attached, awaiting human review |
| Human Done | Human approved — truly complete |
| Failed | Incremental eval failed — auto-retry |
| Rejected | Human rejected — feedback appended, sent back to Todo |

## Configuration

Edit `config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MODEL` | `claude-opus-4-6` | Claude model to use |
| `MAX_RALPH_LOOPS` | `30` | Maximum execution cycles |
| `MAX_TURNS_PER_LOOP` | `150` | Max agent turns per Ralph cycle |
| `MAX_BUDGET_PER_LOOP` | `5.0` | Max spend per cycle (USD) |
| `EVAL_PASS_THRESHOLD` | `7` | Eval pass threshold (each dimension ≥ X/10) |
| `MAX_PLANNING_TURNS` | `30` | Max turns for planning agent |
| `MAX_PLANNING_BUDGET` | `1.0` | Max spend per planning run (USD) |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Runtime | [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk), Claude claude-opus-4-6 |
| Backend | Python 3.11+, FastAPI, uvicorn, anyio |
| Frontend | React 19, Vite, TailwindCSS 4, Zustand |
| UI Components | Radix UI, @dnd-kit, Framer Motion, Lucide icons |
| Evaluation | Playwright (browser screenshots + interaction testing) |
| Package Manager | uv (Python), npm (Node.js) |

## Contributing

```bash
git clone https://github.com/HuangZiy/ekko.git && cd ekko
uv pip install -e ".[dev]"
cd web && npm install && cd ..

# Run tests
pytest

# Run the web UI in dev mode
cd web && npm run build && cd ..
```

## License

MIT

---

<a id="什么是-ekko"></a>

## 什么是 Ekko？

Ekko 是一个基于 [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk) 的 AI 驱动开发套件。给它一句话需求，它会自动规划、实现、评估、迭代——直到人类审核通过。

灵感来源于 Anthropic 的[三 Agent 架构](https://www.anthropic.com/engineering/harness-design-long-running-apps)（Planner / Generator / Evaluator）、[Ralph Wiggum 技术](https://ghuntley.com/ralph/)的单任务循环与 build/test 反压机制，以及 [vibe-kanban](https://github.com/BloopAI/vibe-kanban) 的本地看板 UI。

与简单的代码生成工具不同，Ekko 管理完整的开发生命周期：将需求拆解为带依赖关系的 Issue，分派给并行 Agent 执行，收集证据（git diff + 构建输出 + 截图），并以人类审核作为完成门控。

## 核心特性

| 特性 | 说明 |
|------|------|
| 看板管理 | 6 列看板（Backlog → Todo → In Progress → Agent Done → Human Done），支持拖拽的 Web UI |
| 交互式规划 | Brainstorming Agent 自动将需求拆解为带依赖关系的 Issue |
| 多 Agent 并行 | 调度器将无阻塞的 Issue 分配给多个 Agent 并发执行 |
| 构建/测试反压 | Agent 必须通过构建和测试才能标记完成——没有捷径 |
| 人类审核闭环 | Agent Done 的 Issue 需要人类 Approve/Reject 才能关闭 |
| 证据收集 | 每个 Issue 附带 git diff、构建输出、Playwright 截图 |
| 断点续传 | 中断的任务精确恢复到步骤级别——Ralph 完成但 Eval 崩了？跳过 Ralph 直接补跑 Eval |
| 实时 Web UI | React + Tailwind 仪表盘，SSE 推送、Markdown 渲染、审核面板 |
| CLI 优先 | 完整的 CLI 支持 project/issue/review/plan/run——可脚本化、可组合 |

## 架构

```
需求 ("增加用户认证系统")
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  Planner Agent                                           │
│  交互式 brainstorming → 产出带依赖关系的 Issue            │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│  看板                                                     │
│                                                          │
│  Backlog → Todo → In Progress → Agent Done → Human Done  │
│                     ↑                │                   │
│                     └── Failed ──────┘                   │
│                ↑                     │                   │
│                └── Rejected ─────────┘ (人类审核不通过)    │
│                                                          │
│  调度器自动将 Todo + 无 blocker 的 Issue 分配给空闲 Agent  │
│  多 Agent 可并行执行无依赖的 Issue                        │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│  每个 Issue 的执行流程                                    │
│                                                          │
│  1. Ralph Agent 实现（单任务 + build/test 反压）          │
│  2. 增量评估（只验证本次变更）                             │
│  3. 收集证据（git diff + 构建输出 + 截图）                │
│  4. Agent Done → 等待人类审核                             │
│  5. Approve → Human Done → 解锁依赖 Issue                │
│     Reject  → 追加反馈 → 打回 Todo                       │
└──────────────────────────────────────────────────────────┘
```

> [查看交互式架构图 →](https://huangziy.github.io/ekko/)

## 快速安装

```bash
git clone https://github.com/HuangZiy/ekko.git && cd ekko
uv pip install -e .
cd web && npm install && cd ..
```

安装后 `harness` 命令全局可用。

**前置条件：** Python ≥ 3.11、Node.js ≥ 20、[uv](https://github.com/astral-sh/uv)、设置 `ANTHROPIC_API_KEY` 环境变量。

## 快速上手

```bash
# 1. 创建项目
harness project create "我的应用" ./workspace

# 2. 添加 Issue
harness issue create "实现用户登录" --label auth --priority high

# 3. 运行 — Agent 自动领取 todo issue
harness run

# 4. 启动 Web UI 审核
harness serve --dev    # http://localhost:5173
```

或者从零开始一步到位：

```bash
harness plan "构建一个带认证和数据分析的后台系统"   # brainstorm → 自动创建 Issue
harness run                                         # 执行全部
```

## CLI 命令速查

| 命令 | 说明 |
|------|------|
| `harness project create <名称> <路径>` | 创建项目 |
| `harness project list` | 列出所有项目 |
| `harness project switch <id>` | 切换活跃项目 |
| `harness issue create <标题> [--label] [--priority]` | 创建 Issue |
| `harness issue list [--status todo]` | 列出 Issue |
| `harness issue show <id>` | 查看 Issue 详情 |
| `harness issue move <id> <状态>` | 移动 Issue 到指定列 |
| `harness review <id> --approve` | 审核通过 |
| `harness review <id> --reject --comment "..."` | 审核拒绝并附反馈 |
| `harness plan "<需求>"` | 交互式规划 → 自动创建 Issue |
| `harness plan-issue <id>` | 对单个 Issue 进行规划 |
| `harness run [<id>]` | 执行所有就绪 Issue（或指定单个） |
| `harness serve [--dev]` | 启动 Web UI |
| `harness board` | 终端打印看板状态 |
| `harness migrate` | 将 fix_plan.md 转为 Issue |

## Issue 生命周期

```
Backlog → Planning → Todo → In Progress → Agent Done → Human Done
                      ↑         ↑              │
                      │         └── Failed ─────┘
                      └──────── Rejected ───────┘
```

| 状态 | 含义 |
|------|------|
| Backlog | 已创建，未排期 |
| Planning | Planner Agent 正在分析（可选） |
| Todo | 等待 Agent 领取 |
| In Progress | Agent 正在实现 |
| Agent Done | Agent 完成，附带证据，等待人类审核 |
| Human Done | 人类审核通过，真正结束 |
| Failed | 增量评估未通过，自动重试 |
| Rejected | 人类审核不通过，追加反馈打回 Todo |

## 配置

编辑 `config.py`：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MODEL` | `claude-opus-4-6` | 使用的 Claude 模型 |
| `MAX_RALPH_LOOPS` | `30` | 最大执行循环次数 |
| `MAX_TURNS_PER_LOOP` | `150` | 每轮 Ralph 最大 agent turns |
| `MAX_BUDGET_PER_LOOP` | `5.0` | 每轮最大花费 (USD) |
| `EVAL_PASS_THRESHOLD` | `7` | 评估通过阈值（每维度 ≥ X/10） |
| `MAX_PLANNING_TURNS` | `30` | 规划 Agent 最大 turns |
| `MAX_PLANNING_BUDGET` | `1.0` | 每次规划最大花费 (USD) |

## 技术栈

| 层级 | 技术 |
|------|------|
| AI 运行时 | [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk)、Claude claude-opus-4-6 |
| 后端 | Python 3.11+、FastAPI、uvicorn、anyio |
| 前端 | React 19、Vite、TailwindCSS 4、Zustand |
| UI 组件 | Radix UI、@dnd-kit、Framer Motion、Lucide icons |
| 评估 | Playwright（浏览器截图 + 交互测试） |
| 包管理 | uv (Python)、npm (Node.js) |

## 参与贡献

```bash
git clone https://github.com/HuangZiy/ekko.git && cd ekko
uv pip install -e ".[dev]"
cd web && npm install && cd ..

# 运行测试
pytest

# 构建前端
cd web && npm run build && cd ..
```

## 许可证

MIT
