# Ekko

Master of Time for Long-Running Harness

基于 Claude Agent SDK 的 AI 驱动开发套件，集成看板式任务管理、多 Agent 并行执行、人类审核流程和本地 Web UI。

从一句话需求出发，自动规划、实现、评估、迭代，直到人类审核通过。适用于任何 Web 应用项目。

## 灵感来源

- [Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps) — Anthropic 三 Agent 架构（Planner / Generator / Evaluator）
- [Ralph Wiggum technique](https://ghuntley.com/ralph/) — 单任务循环、fix_plan 状态传递、build/test backpressure
- [vibe-kanban](https://github.com/BloopAI/vibe-kanban) — 本地看板 UI，管理 coding agent 工作
- [multica](https://github.com/multica-ai/multica) — 多 agent 平台，Issue 分配给 agent 自动执行

## 架构

```
用户需求 ("增加用户认证系统")
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Planning（可选）                                             │
│   交互式 brainstorming → 产出一批带依赖关系的 Issue           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Kanban Board                                                │
│                                                             │
│  Backlog → Todo → In Progress → Agent Done → Human Done     │
│                       ↑              │                      │
│                       └── Failed ────┘                      │
│                  ↑                   │                      │
│                  └── Rejected ───────┘ (人类审核不通过)       │
│                                                             │
│  调度器自动将 Todo + 无 blocker 的 Issue 分配给空闲 Agent     │
│  多 Agent 可并行执行无依赖的 Issue                           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ 每个 Issue 的执行流程                                        │
│                                                             │
│  1. Ralph Agent 实现（单任务 + build/test backpressure）     │
│  2. 增量评估（只验证本次变更）                                │
│  3. 收集证据（git diff + build + 截图）                      │
│  4. Agent Done → 等待人类审核                                │
│  5. 人类 Approve → Human Done → 解锁依赖 Issue              │
│     人类 Reject → 追加反馈 → 打回 Todo                       │
└─────────────────────────────────────────────────────────────┘
```

## 安装

```bash
# One-line 安装（需要 uv）
uv pip install -e git+https://github.com/your-repo/ekko.git#egg=ekko

# 或者本地安装
git clone <repo-url> && cd ekko
uv pip install -e .

# 安装前端依赖（Web UI）
cd web && npm install && cd ..
```

安装后 `harness` 命令全局可用。

## 快速开始

```bash
# 方式 1: 看板模式（推荐）
harness project create "我的项目" ./workspace
harness issue create "实现用户登录" --label auth --priority high
harness run                              # 自动执行所有 todo issue
harness serve --dev                      # 启动 Web UI 看板

# 方式 2: Planning 模式（从需求到 Issue）
harness plan "增加后台管理系统"           # 交互式规划 → 自动创建 Issue
harness run                              # 执行

# 方式 3: 传统模式（fix_plan.md 驱动，向后兼容）
python harness.py "创建一个全栈 Web 应用"
```

## CLI 命令

```bash
# 项目管理
harness project create "项目名" ./workspace
harness project list
harness project switch PRJ-abc123
harness project show

# Issue 管理
harness issue create "标题" --label bug --priority high
harness issue list [--status todo]
harness issue show ISS-001
harness issue move ISS-001 todo

# 审核
harness review ISS-001 --approve
harness review ISS-001 --reject --comment "缺少 loading 状态"

# Planning（可选）
harness plan "增加后台管理系统"

# 执行
harness run                              # 执行所有 todo + unblocked issue
harness run ISS-001                      # 执行单个 issue

# Web UI
harness serve --dev                      # 开发模式（Vite HMR + FastAPI）
harness serve                            # 生产模式（serve 构建产物）

# 迁移
harness migrate                          # 将 fix_plan.md 转为 Issue
harness migrate --fix-plan ./path/to/fix_plan.md
```

## 项目结构

```
ekko/
├── harness.py                 # 传统模式入口（向后兼容）
├── config.py                  # 全局配置
├── requirements.txt
│
├── core/                      # 核心数据模型与业务逻辑
│   ├── models.py              # Issue / Board / Project 数据模型
│   ├── storage.py             # JSON + Markdown 文件存储
│   ├── executor.py            # Issue-based Ralph 执行器
│   ├── evidence.py            # Agent Done 证据收集
│   ├── scheduler.py           # 并行 Agent 调度器
│   ├── review.py              # 人类审核（approve / reject）
│   └── migrate.py             # fix_plan.md → Issue 迁移
│
├── agents/                    # Claude Agent SDK 封装
│   ├── planner.py             # Planner Agent（交互式 brainstorming）
│   ├── ralph_loop.py          # Ralph Agent（单任务实现 + backpressure）
│   └── evaluator.py           # Evaluator Agent（增量 + 全量评估）
│
├── cli/                       # CLI 入口
│   └── main.py                # argparse 子命令（issue/review/plan/run/serve/migrate）
│
├── server/                    # FastAPI 后端
│   ├── app.py                 # FastAPI 应用 + 路由注册
│   ├── sse.py                 # SSE 事件总线（实时推送）
│   └── routes/
│       ├── issues.py          # Issue CRUD API
│       ├── board.py           # 看板 API（拖拽移动）
│       ├── projects.py        # 项目管理 API
│       └── reviews.py         # 审核 API
│
├── web/                       # 前端（Vite + React）
│   └── src/
│       ├── App.tsx             # 主应用
│       ├── stores/
│       │   └── boardStore.ts  # Zustand 状态管理
│       ├── hooks/
│       │   └── useSSE.ts      # SSE 实时更新
│       └── components/
│           ├── Board.tsx       # 看板视图（dnd-kit 拖拽）
│           ├── Column.tsx      # 看板列
│           ├── IssueCard.tsx   # Issue 卡片
│           └── IssueDetail.tsx # Issue 详情 + 审核面板
│
├── prompts/                   # Agent 系统提示词
│   ├── planner_system.md
│   ├── ralph_prompt.md
│   ├── evaluator_system.md
│   └── eval_criteria.md
│
├── workspace/                 # 生成的项目源码
│   └── .harness/              # Harness 运行时数据
│       ├── projects/          # 项目数据
│       │   └── <project-id>/
│       │       ├── board.json
│       │       ├── issues/
│       │       │   ├── <id>/meta.json
│       │       │   └── <id>/content.md
│       │       └── runs/
│       ├── tasks/             # 传统模式的任务记录
│       └── specs/             # Planner 产出的功能规格
│
├── tests/                     # 测试
└── docs/plans/                # 设计文档（历史）
```

## Issue 状态流转

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

## Agent Done 证据

Issue 进入 Agent Done 时自动收集：

- Git diff（变更文件列表 + patch）
- Build 结果（构建输出）
- Playwright 截图
- 增量评估报告

证据写入 Issue 的 Markdown 内容，在 Web UI 中可查看。

## 人类审核

Agent Done 的 Issue 需要人类审核才能进入 Human Done：

- **Approve** → Human Done，自动解锁被此 Issue block 的其他 Issue
- **Reject** → 追加反馈（缺陷描述 + 优化建议 + 截图）→ 打回 Todo 重新执行

审核方式：
- Web UI：Issue 详情面板的 Approve / Reject 按钮
- CLI：`harness review ISS-001 --approve` 或 `--reject --comment "..."`

## 依赖关系

Issue 支持 `blocks` / `blocked_by` 依赖：

```
ISS-001: 权限认证
ISS-002: 后台 API        ← blocked_by: [ISS-001]
ISS-003: 前端页面        ← blocked_by: [ISS-001, ISS-002]
```

调度器自动按依赖顺序执行。无依赖的 Issue 可并行分配给多个 Agent。

## Web UI

```bash
harness serve --dev    # http://localhost:5173（前端）+ :8080（API）
```

- 看板视图：6 列拖拽，实时更新
- Issue 详情：Markdown 渲染、证据查看、依赖关系
- 审核面板：Approve / Reject + 反馈编辑
- SSE 实时推送：Agent 执行状态变更即时反映

技术栈：Vite + React 18 + TailwindCSS + Radix UI + @dnd-kit + Zustand + Framer Motion

## 配置

编辑 `config.py`：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MODEL` | `claude-opus-4-6` | Claude 模型 |
| `MAX_RALPH_LOOPS` | `30` | 最大循环次数 |
| `MAX_TURNS_PER_LOOP` | `150` | 每轮 Ralph 最大 agent turns |
| `MAX_BUDGET_PER_LOOP` | `5.0` | 每轮最大花费 (USD) |
| `EVAL_PASS_THRESHOLD` | `7` | 评估通过阈值（每维度 >= X/10） |

## 评估标准

Evaluator 使用 Playwright 实际浏览页面，按四个维度打分：

| 维度 | 权重 | 评估内容 |
|------|------|----------|
| 设计质量 | 25% | 视觉一致性、暗色模式、动画、原创性 |
| 功能完整性 | 25% | 对照 specs 逐项验证 |
| 交互体验 | 25% | 响应式、可访问性、导航流畅度 |
| 代码质量 | 25% | TypeScript、构建通过、组件结构 |

循环内用增量评估（只验证本次变更，~$1），循环结束用全量评估（四维度打分，~$4）。

## 断点续传

每个任务独立存储在 `.harness/tasks/<task_id>/`，中断后重启自动恢复：

```bash
python harness.py "..."    # 中断（Ctrl+C / 崩溃）
python harness.py           # 重启 → 显示中断任务列表 → 选择恢复
```

精确到步骤级别：Ralph 完成后 Eval 崩了 → 恢复时跳过 Ralph 直接补跑 Eval。

## 运行日志

终端彩色输出 + 文件日志（`.harness/tasks/<id>/harness.log`）：

```
[Task]      当前任务（青色）
[Ralph]     Agent 输出（青色）
[Evaluator] 评估输出（紫色）
[Tool]      工具调用（黄色）
[Done]      完成摘要 — turns、cost、duration（绿色）
```

运行结束输出统计汇总，保存到 `harness_summary.txt` + `harness_stats.json`。

## 从 fix_plan.md 迁移

```bash
harness migrate    # 将 workspace/fix_plan.md 的 checklist 转为 Issue
```

`- [ ]` → Issue (Todo)，`- [x]` → Issue (Human Done)，自动设置标签和看板位置。
