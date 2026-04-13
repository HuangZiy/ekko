<p align="center">
  <img src="docs/assets/ekko-banner.svg" alt="Ekko" width="100%" />
</p>

<p align="center">
  <strong>Your next developer never sleeps.</strong><br/>
  One requirement in. Planned, implemented, evaluated, and iterated — until you approve.
</p>

<p align="center">
  <a href="https://github.com/HuangZiy/ekko/stargazers"><img src="https://img.shields.io/github/stars/HuangZiy/ekko?style=for-the-badge" alt="Stars"></a>&nbsp;
  <a href="https://github.com/HuangZiy/ekko/blob/main/LICENSE"><img src="https://img.shields.io/github/license/HuangZiy/ekko?style=for-the-badge" alt="License"></a>&nbsp;
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-≥3.11-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>&nbsp;
  <a href="https://github.com/anthropics/claude-agent-sdk"><img src="https://img.shields.io/badge/Claude_Agent_SDK-black?style=for-the-badge&logo=anthropic&logoColor=white" alt="Claude Agent SDK"></a>
</p>

<p align="center">
  <a href="https://huangziy.github.io/ekko/">Interactive Architecture →</a>
</p>

<p align="center">
  <a href="#what-is-ekko">English</a> · <a href="#什么是-ekko">中文</a>
</p>

---

## What is Ekko?

Ekko is an AI-powered development harness built on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk). It turns a single requirement into a fully managed development pipeline — planning, implementation, evaluation, and human review — all orchestrated through a kanban board.

Unlike simple code-generation tools, Ekko manages the **full lifecycle**: decomposing requirements into dependency-aware issues, dispatching them to parallel agents, collecting evidence (git diff + build output + Playwright screenshots), and gating completion on human approval.

Inspired by:
- Anthropic's [three-agent architecture](https://www.anthropic.com/engineering/harness-design-long-running-apps) — Planner / Generator / Evaluator
- The [Ralph Wiggum technique](https://ghuntley.com/ralph/) — single-task loops with build/test backpressure
- [vibe-kanban](https://github.com/BloopAI/vibe-kanban) — local board UI for AI-driven development

## Features

| Feature | Description |
|---|---|
| **Kanban Board** | 7-column board with drag-and-drop Web UI — Backlog through Human Done |
| **Interactive Planning** | Planner agent decomposes requirements into dependency-aware issues with specs |
| **Multi-Agent Parallel** | Scheduler dispatches unblocked issues to concurrent agents via async semaphore |
| **Build/Test Backpressure** | Agents must pass build and tests before marking work complete |
| **Human-in-the-Loop** | Every issue requires explicit Approve / Reject before closing |
| **Evidence Collection** | Git diff, build output, Playwright screenshots bundled per issue |
| **Issue Splitting** | Planning agent can split complex issues into children with dependency tracking |
| **Checkpoint Resume** | Interrupted tasks resume at the exact step — no wasted work |
| **Real-time Web UI** | React + Tailwind dashboard with SSE streaming and review panels |
| **CLI-first** | Full CLI for project / issue / review / plan / run — scriptable and composable |

## Architecture

```
"Add user authentication"
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Planner Agent                                              │
│  Brainstorm → specs + dependency-aware Issues               │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Kanban Board                                               │
│                                                             │
│  Backlog → Planning → Todo → In Progress → Agent Done       │
│                        ↑          ↑             │           │
│                        │          └── Failed ───┘           │
│                        └──── Rejected ──────────┘           │
│                                                             │
│  Scheduler: Todo + unblocked → idle agents (parallel)       │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Per-Issue Execution Loop                                   │
│                                                             │
│  1. Planning Agent writes plan.md (can split into children) │
│  2. Ralph Agent implements (build/test backpressure)        │
│  3. Evaluator verifies (Playwright + incremental review)    │
│  4. Evidence collected (git diff + build + screenshots)     │
│  5. Agent Done → human review                               │
│     Approve → Human Done → unblock dependents               │
│     Reject  → feedback → back to Todo                       │
└─────────────────────────────────────────────────────────────┘
```

> [View the interactive version →](https://huangziy.github.io/ekko/)

## Quick Install

Prerequisites: Python ≥ 3.11, Node.js ≥ 20, [uv](https://github.com/astral-sh/uv)

```bash
git clone https://github.com/HuangZiy/ekko.git && cd ekko
uv pip install -e .
cd web && npm install && cd ..
```

Set your API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

The `harness` command is now available globally.

## Getting Started

```bash
# 1. Create a project
harness project create "My App" ./my-app

# 2. Plan — one sentence in, dependency-aware issues out
harness plan "Build a dashboard with auth and analytics"

# 3. Run — agents pick up issues automatically
harness run

# 4. Review in the Web UI
harness serve --dev    # → http://localhost:5173
```

Or manage issues manually:

```bash
harness issue create "Implement login page" --label auth --priority high
harness run ISS-1
harness review ISS-1 --approve
```

## CLI Reference

| Command | Description |
|---|---|
| `harness project create <name> <path>` | Create a new project |
| `harness project list` | List all projects |
| `harness project switch <id>` | Switch active project |
| `harness project show [id]` | Show project details and issue counts |
| `harness project update [id] [--name] [--key]` | Update project settings |
| `harness project delete <id> [-y]` | Delete a project |
| `harness issue create <title> [--label] [--priority]` | Create an issue |
| `harness issue list [--status STATUS]` | List issues, optionally filtered |
| `harness issue show <id>` | Show issue details |
| `harness issue move <id> <status>` | Move issue to a status |
| `harness issue delete <id> [-y]` | Delete an issue |
| `harness review <id> --approve` | Approve an Agent Done issue |
| `harness review <id> --reject --comment "..."` | Reject with feedback |
| `harness plan "<requirement>"` | Interactive planning → auto-create issues |
| `harness plan-issue <id>` | Plan a single issue |
| `harness run [<id>]` | Execute all ready issues or a specific one |
| `harness serve [--port N] [--dev]` | Launch Web UI |
| `harness board` | Print board to terminal |
| `harness migrate` | Convert fix_plan.md → issues |

## Issue Lifecycle

```
Backlog ──→ Planning ──→ Todo ──→ In Progress ──→ Agent Done ──→ Human Done
                          ↑           ↑                │
                          │           └── Failed ──────┘
                          └──────── Rejected ──────────┘
```

| Status | Description |
|---|---|
| `backlog` | Created, not yet scheduled |
| `planning` | Planner agent is analyzing |
| `todo` | Ready for an agent to pick up |
| `in_progress` | Agent is implementing |
| `agent_done` | Agent finished — evidence attached, awaiting human review |
| `human_done` | Human approved — complete, unblocks dependents |
| `failed` | Eval failed — auto-retried |
| `rejected` | Human rejected — feedback appended, back to todo |

## Project Structure

```
ekko/
├── config.py               # Global configuration constants
├── pyproject.toml           # Package definition → `harness` CLI
│
├── core/                   # Domain logic
│   ├── models.py           # Issue / Board / Project dataclasses + state machine
│   ├── storage.py          # JSON + Markdown persistence (no database)
│   ├── executor.py         # Single-issue Ralph executor (Claude Agent SDK)
│   ├── ralph_loop.py       # Board-level orchestration + parallel scheduling
│   ├── planner.py          # Per-issue planning agent (writes plan.md, can split)
│   ├── evidence.py         # Evidence collection (git diff, build, screenshots)
│   ├── review.py           # Human review logic (approve / reject)
│   └── migrate.py          # fix_plan.md → issues migration
│
├── agents/                 # Claude Agent SDK wrappers
│   ├── planner.py          # Interactive brainstorming planner
│   ├── ralph_loop.py       # Ralph agent (single-task + backpressure)
│   └── evaluator.py        # Evaluator (Playwright + code review)
│
├── cli/main.py             # argparse CLI — all subcommands
│
├── server/                 # FastAPI backend
│   ├── app.py              # App factory + startup hooks + watchdog
│   ├── ws.py               # WebSocket manager
│   └── routes/             # REST + WebSocket endpoints
│
├── web/                    # Frontend (Vite + React 19 + TailwindCSS 4)
│   └── src/
│       ├── stores/         # Zustand state management
│       ├── hooks/          # SSE real-time hooks
│       └── components/     # Board, Column, IssueCard, IssueDetail
│
├── prompts/                # Agent system prompts (Markdown)
│   ├── planner_system.md
│   ├── ralph_prompt.md
│   └── evaluator_system.md
│
├── docs/
│   ├── assets/             # Banner SVG
│   └── flowchart/          # Interactive architecture (Vite + React + @xyflow/react)
│
└── .harness/               # Runtime data store (auto-created)
    ├── registry.json       # project_id → workspace mapping
    ├── active_project      # Currently active project ID
    └── <workspace>/.harness/
        ├── project.json    # Project metadata
        ├── board.json      # Kanban board state
        ├── issues/ISS-*/   # meta.json + content.md + plan.md + logs/ + stats/
        └── specs/          # Functional specs from planner
```

## Configuration

Edit `config.py`:

| Parameter | Default | Description |
|---|---|---|
| `MODEL` | `claude-opus-4-6` | Claude model for all agents |
| `MAX_RALPH_LOOPS` | `30` | Max execution cycles per issue |
| `MAX_TURNS_PER_LOOP` | `150` | Max agent turns per cycle |
| `MAX_BUDGET_PER_LOOP` | `5.0` | Max spend per cycle (USD) |
| `EVAL_PASS_THRESHOLD` | `7` | Eval pass threshold (each dimension ≥ X/10) |
| `MAX_PLANNING_TURNS` | `30` | Max turns for planning agent |
| `MAX_PLANNING_BUDGET` | `1.0` | Max spend per planning run (USD) |
| `SCHEDULER_MAX_PARALLEL` | `1` | Max concurrent issue runs per project |

## Tech Stack

| Layer | Technology |
|---|---|
| AI Runtime | [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk), Claude Opus |
| Backend | Python 3.11+, FastAPI, uvicorn, anyio |
| Frontend | React 19, Vite, TailwindCSS 4, Zustand |
| UI Components | Radix UI, @dnd-kit, Framer Motion, Lucide |
| Evaluation | Playwright via MCP server |
| Storage | JSON + Markdown files (no database) |
| Package Managers | uv (Python), npm (Node.js) |
| Build | hatchling |

## Contributing

```bash
git clone https://github.com/HuangZiy/ekko.git && cd ekko
uv pip install -e ".[dev]"
cd web && npm install && cd ..

# Run tests
pytest

# Build frontend
cd web && npm run build && cd ..
```

## License

[MIT](https://github.com/HuangZiy/ekko/blob/main/LICENSE)

---

<a id="什么是-ekko"></a>

## 什么是 Ekko？

Ekko 是一个基于 [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk) 的 AI 驱动开发套件。给它一句话需求，它会自动规划、实现、评估、迭代——直到你审核通过。

与简单的代码生成工具不同，Ekko 管理**完整的开发生命周期**：将需求拆解为带依赖关系的 Issue，分派给并行 Agent 执行，收集证据（git diff + 构建输出 + Playwright 截图），并以人类审核作为完成门控。

灵感来源：
- Anthropic 的[三 Agent 架构](https://www.anthropic.com/engineering/harness-design-long-running-apps) — Planner / Generator / Evaluator
- [Ralph Wiggum 技术](https://ghuntley.com/ralph/) — 单任务循环 + build/test 反压
- [vibe-kanban](https://github.com/BloopAI/vibe-kanban) — AI 驱动开发的本地看板 UI

## 核心特性

| 特性 | 说明 |
|---|---|
| **看板管理** | 7 列看板 + 拖拽 Web UI — 从 Backlog 到 Human Done |
| **交互式规划** | Planner Agent 自动将需求拆解为带依赖关系的 Issue 和功能规格 |
| **多 Agent 并行** | 调度器将无阻塞 Issue 分配给多个 Agent 并发执行 |
| **构建/测试反压** | Agent 必须通过构建和测试才能标记完成 |
| **人类审核闭环** | 每个 Issue 都需要人类明确 Approve / Reject 才能关闭 |
| **证据收集** | 每个 Issue 附带 git diff、构建输出、Playwright 截图 |
| **Issue 拆分** | 规划 Agent 可将复杂 Issue 拆分为带依赖的子 Issue |
| **断点续传** | 中断的任务精确恢复到步骤级别 — 不浪费已完成的工作 |
| **实时 Web UI** | React + Tailwind 仪表盘，SSE 推送 + 审核面板 |
| **CLI 优先** | 完整 CLI 支持 project / issue / review / plan / run — 可脚本化 |

## 架构

```
"增加用户认证系统"
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Planner Agent                                              │
│  交互式 brainstorming → specs + 带依赖关系的 Issue           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  看板                                                       │
│                                                             │
│  Backlog → Planning → Todo → In Progress → Agent Done       │
│                        ↑          ↑             │           │
│                        │          └── Failed ───┘           │
│                        └──── Rejected ──────────┘           │
│                                                             │
│  调度器：Todo + 无 blocker → 空闲 Agent（并行执行）           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  每个 Issue 的执行循环                                       │
│                                                             │
│  1. Planning Agent 编写 plan.md（可拆分为子 Issue）          │
│  2. Ralph Agent 实现代码（build/test 反压）                  │
│  3. Evaluator 验证（Playwright + 增量审查）                  │
│  4. 收集证据（git diff + 构建输出 + 截图）                   │
│  5. Agent Done → 人类审核                                    │
│     Approve → Human Done → 解锁依赖 Issue                   │
│     Reject  → 追加反馈 → 打回 Todo                          │
└─────────────────────────────────────────────────────────────┘
```

> [查看交互式架构图 →](https://huangziy.github.io/ekko/)

## 快速安装

前置条件：Python ≥ 3.11、Node.js ≥ 20、[uv](https://github.com/astral-sh/uv)

```bash
git clone https://github.com/HuangZiy/ekko.git && cd ekko
uv pip install -e .
cd web && npm install && cd ..
```

设置 API Key：

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

安装后 `harness` 命令全局可用。

## 快速上手

```bash
# 1. 创建项目
harness project create "我的应用" ./my-app

# 2. 规划 — 一句话输入，带依赖的 Issue 输出
harness plan "构建一个带认证和数据分析的后台系统"

# 3. 运行 — Agent 自动领取 Issue
harness run

# 4. 在 Web UI 中审核
harness serve --dev    # → http://localhost:5173
```

或手动管理 Issue：

```bash
harness issue create "实现登录页面" --label auth --priority high
harness run ISS-1
harness review ISS-1 --approve
```

## CLI 命令速查

| 命令 | 说明 |
|---|---|
| `harness project create <名称> <路径>` | 创建项目 |
| `harness project list` | 列出所有项目 |
| `harness project switch <id>` | 切换活跃项目 |
| `harness project show [id]` | 查看项目详情和 Issue 统计 |
| `harness project update [id] [--name] [--key]` | 更新项目设置 |
| `harness project delete <id> [-y]` | 删除项目 |
| `harness issue create <标题> [--label] [--priority]` | 创建 Issue |
| `harness issue list [--status STATUS]` | 列出 Issue |
| `harness issue show <id>` | 查看 Issue 详情 |
| `harness issue move <id> <状态>` | 移动 Issue |
| `harness issue delete <id> [-y]` | 删除 Issue |
| `harness review <id> --approve` | 审核通过 |
| `harness review <id> --reject --comment "..."` | 审核拒绝并附反馈 |
| `harness plan "<需求>"` | 交互式规划 → 自动创建 Issue |
| `harness plan-issue <id>` | 对单个 Issue 进行规划 |
| `harness run [<id>]` | 执行所有就绪 Issue（或指定单个） |
| `harness serve [--port N] [--dev]` | 启动 Web UI |
| `harness board` | 终端打印看板 |
| `harness migrate` | 将 fix_plan.md 转为 Issue |

## Issue 生命周期

```
Backlog ──→ Planning ──→ Todo ──→ In Progress ──→ Agent Done ──→ Human Done
                          ↑           ↑                │
                          │           └── Failed ──────┘
                          └──────── Rejected ──────────┘
```

| 状态 | 说明 |
|---|---|
| `backlog` | 已创建，未排期 |
| `planning` | Planner Agent 正在分析 |
| `todo` | 等待 Agent 领取 |
| `in_progress` | Agent 正在实现 |
| `agent_done` | Agent 完成，附带证据，等待人类审核 |
| `human_done` | 人类审核通过，解锁依赖 Issue |
| `failed` | 评估未通过，自动重试 |
| `rejected` | 人类审核不通过，追加反馈打回 Todo |

## 项目结构

```
ekko/
├── config.py               # 全局配置常量
├── pyproject.toml           # 包定义 → `harness` CLI
│
├── core/                   # 核心领域逻辑
│   ├── models.py           # Issue / Board / Project 数据模型 + 状态机
│   ├── storage.py          # JSON + Markdown 持久化（无数据库）
│   ├── executor.py         # 单 Issue Ralph 执行器（Claude Agent SDK）
│   ├── ralph_loop.py       # 看板级编排 + 并行调度
│   ├── planner.py          # 单 Issue 规划 Agent（写 plan.md，可拆分）
│   ├── evidence.py         # 证据收集（git diff、构建、截图）
│   ├── review.py           # 人类审核逻辑（approve / reject）
│   └── migrate.py          # fix_plan.md → issues 迁移
│
├── agents/                 # Claude Agent SDK 封装
│   ├── planner.py          # 交互式 brainstorming 规划器
│   ├── ralph_loop.py       # Ralph Agent（单任务 + 反压）
│   └── evaluator.py        # 评估器（Playwright + 代码审查）
│
├── cli/main.py             # argparse CLI — 所有子命令
│
├── server/                 # FastAPI 后端
│   ├── app.py              # 应用工厂 + 启动钩子 + 看门狗
│   ├── ws.py               # WebSocket 管理器
│   └── routes/             # REST + WebSocket 端点
│
├── web/                    # 前端（Vite + React 19 + TailwindCSS 4）
│   └── src/
│       ├── stores/         # Zustand 状态管理
│       ├── hooks/          # SSE 实时 hooks
│       └── components/     # Board, Column, IssueCard, IssueDetail
│
├── prompts/                # Agent 系统提示词（Markdown）
│
├── docs/
│   ├── assets/             # Banner SVG
│   └── flowchart/          # 交互式架构图（Vite + React + @xyflow/react）
│
└── .harness/               # 运行时数据（自动创建）
    ├── registry.json       # project_id → workspace 映射
    ├── active_project      # 当前活跃项目 ID
    └── <workspace>/.harness/
        ├── project.json    # 项目元数据
        ├── board.json      # 看板状态
        ├── issues/ISS-*/   # meta.json + content.md + plan.md + logs/ + stats/
        └── specs/          # 规划器产出的功能规格
```

## 配置

编辑 `config.py`：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `MODEL` | `claude-opus-4-6` | 所有 Agent 使用的 Claude 模型 |
| `MAX_RALPH_LOOPS` | `30` | 每个 Issue 最大执行循环次数 |
| `MAX_TURNS_PER_LOOP` | `150` | 每轮 Ralph 最大 turns |
| `MAX_BUDGET_PER_LOOP` | `5.0` | 每轮最大花费 (USD) |
| `EVAL_PASS_THRESHOLD` | `7` | 评估通过阈值（每维度 ≥ X/10） |
| `MAX_PLANNING_TURNS` | `30` | 规划 Agent 最大 turns |
| `MAX_PLANNING_BUDGET` | `1.0` | 每次规划最大花费 (USD) |
| `SCHEDULER_MAX_PARALLEL` | `1` | 每个项目最大并行 Issue 数 |

## 技术栈

| 层级 | 技术 |
|---|---|
| AI 运行时 | [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk)、Claude Opus |
| 后端 | Python 3.11+、FastAPI、uvicorn、anyio |
| 前端 | React 19、Vite、TailwindCSS 4、Zustand |
| UI 组件 | Radix UI、@dnd-kit、Framer Motion、Lucide |
| 评估 | Playwright（MCP 服务器） |
| 存储 | JSON + Markdown（无数据库） |
| 包管理 | uv (Python)、npm (Node.js) |
| 构建 | hatchling |

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

[MIT](https://github.com/HuangZiy/ekko/blob/main/LICENSE)
