# AI 驱动 Issue 拆分 + CLI 增强需求设计

## 背景

当前 superpowers brainstorming 产出的 impl-plan 走 CLI subagent 执行，与 Ekko 的 issue-driven 看板开发流程脱节。需要将 brainstorming 的产出桥接到 Ekko 看板，让 plan 中的 tasks 变成看板上的子 issue，走 Ekko 的标准执行流程。

Ekko 已有较完整的 CLI（入口 `harness`，定义在 `cli/main.py`），需要更名为 `ekko` 并补齐缺失能力。

---

## 一、AI 驱动 Issue 拆分

### 核心原则

- **拆分决策由 AI 完成**，Ekko 只提供原子操作（创建 issue、设依赖等）
- **父 issue 的 brainstorming 统一拆好所有子 issue**（title + description + plan），保持一致性
- **子 issue 创建后进入 backlog 列**，用户自行决定何时推进

### 流程

```
brainstorming → 产出 plan（含 tasks）
    ↓
AI 解析 plan 中的 tasks
    ↓
逐个调用 Ekko 工具：
  - 创建子 issue（title + description + plan）
  - 设 parent_id 指向父 issue
  - 设 blocked_by 串行依赖链（每个子 issue blocked_by 前一个）
    ↓
子 issue 出现在 Ekko 看板 backlog 列
    ↓
用户按需拖动到 planning / todo → run 执行
```

### 子 issue 规格

| 字段 | 来源 |
|------|------|
| title | 父 issue brainstorming 拆分产出 |
| description (content.md) | 父 issue brainstorming 拆分产出 |
| plan (plan.md) | 父 issue brainstorming 拆分产出 |
| parent_id | 指向父 issue |
| blocked_by | 串行链：第 N 个子 issue blocked_by 第 N-1 个 |
| source | `"agent"` |
| labels | 继承父 issue labels + `["planned"]` |
| 初始列 | backlog |

### 父 issue 状态

子 issue 全部创建后，父 issue 的 `blocked_by` 设为所有子 issue ID。父 issue 等待所有子 issue 完成后才可推进。

---

## 二、CLI 更名与增强

### 2.1 更名：`harness` → `ekko`

- `pyproject.toml` 的 `[project.scripts]` 入口从 `harness` 改为 `ekko`
- `cli/main.py` 中 `build_parser()` 的 `prog="harness"` 改为 `prog="ekko"`
- 所有帮助文本、错误提示中的 `harness` 引用更新为 `ekko`

### 2.2 现有命令（已实现，无需改动）

```
ekko project create/list/switch/show/update/delete
ekko issue create/list/show/move/delete
ekko review --approve/--reject
ekko plan <prompt>
ekko plan-issue <issue_id>
ekko run [issue_id]
ekko scheduler start/status/once
ekko serve [--dev] [--port]
ekko migrate [--fix-plan]
```

### 2.3 需要增强的命令

#### `ekko issue create` — 新增参数

现有 `issue create` 只支持 `title`、`--label`、`--priority`。AI 驱动拆分需要以下新参数：

```
ekko issue create "title" \
  --parent-id EKO-15 \          # 设置父 issue
  --blocked-by EKO-16 \         # 设置依赖（可重复）
  --description "详细描述" \     # 写入 content.md
  --plan "执行计划内容" \        # 写入 plan.md（新增）
  --source agent \               # 标记来源（默认 human）
```

对应 `CreateIssueRequest` 变更：
- 新增 `plan: str = ""` 字段
- 新增 `source: str = "human"` 字段
- 现有 `parent_id`、`blocked_by`、`description` 已在 API model 中，CLI 需要暴露

#### `ekko init` — 新增命令

从当前目录初始化项目，简化 `ekko project create`：

```
ekko init                        # 交互式：提示输入项目名和 key prefix
ekko init --name "my-project" --key PRJ  # 非交互式
```

行为：
- 在当前目录创建 `.harness/` 结构
- 自动将当前目录注册为 workspace
- 注册到 registry
- 等价于 `ekko project create "name" $(pwd) --key PRJ`

#### `ekko board` — 新增命令

```
ekko board                       # 看板概览（按列分组显示 issue）
ekko board move EKO-15 todo      # 移动 issue 到指定列
```

`ekko board` 输出示例：
```
backlog (3)
  EKO-[medium]  实现用户登录
  EKO-16  [high]    修复支付bug
  EKO-17  [low]     优化首页性能

todo (1)
  EKO-12  [medium]  添加日志模块

in_progress (1)
  EKO-10  [high]    重构数据库层

agent_done (2)
  EKO-8   [medium]  添加单元测试
  EKO-9   [medium]  更新API文档
```

注：`ekko board move` 与现有 `ekko issue move` 的区别是 board move 操作看板列，issue move 操作 issue 状态。当前两者等价（列 = 状态），但语义上 board move 更直观。

#### `ekko stats` — 新增命令

```
ekko stats EKO-15                # 单个 issue 的 cost/duration/turns 统计
ekko stats                       # 项目级汇总统计
```

### 2.4 API 变更

#### `POST /api/projects/{id}/issues` — CreateIssueRequest 新增字段

```python
class CreateIssueRequest(BaseModel):
    title: str
    priority: str = "medium"
    labels: list[str] = []
    description: str = ""
    blocked_by: list[str] = []
    workspace: str = "default"
    parent_id: str | None = None
    plan: str = ""          # 新增：写入 plan.md
    source: str = "human"   # 新增：标记来源
```

创建逻辑变更：
- 如果 `plan` 非空，创建后调用 `storage.save_issue_plan(issue_id, plan)`
- 如果 `source` 为 `"agent"`，设置 `issue.source = "agent"`

#### `POST /api/projects/{id}/issues/batch` — 新增批量创建端点（P1）

```python
class BatchCreateRequest(BaseModel):
    parent_id: str                    # 父 issue ID
    issues: list[ChildIssueRequest]   # 子 issue 列表（按顺序）
    chain_dependencies: bool = True   # 自动串行依赖链

class ChildIssueRequest(BaseModel):
    title: str
    description: str = ""
    plan: str = ""
    priority: str = "medium"
    labels: list[str] = []
```

行为：
- 按顺序创建子 issue，自动设 `parent_id`
- `chain_dependencies=True` 时自动设串行 `blocked_by`
- 父 issue 的 `blocked_by` 设为所有子 issue
- 所有子 issue 进入 backlog 列
- 返回创建的子 issue 列表

---

## 三、harness skill / MCP tool 对齐

确保 AI 可用的 harness skill 工具覆盖以下能力：

| 操作 | 需要的参数 | 现状 |
|------|-----------|------|
| 创建 issue | title, description, plan, parent_id, blocked_by, source | 缺 plan、source |
| 批量创建子 issue | parent_id, issues[], chain_dependencies | 不存在 |
| 查看 issue 详情 | issue_id | 已有 |
| 查看看板 | — | 已有 |

harness skill 的 create issue 能力需要与 API 保持一致，新增 `plan` 和 `source` 参数支持。
