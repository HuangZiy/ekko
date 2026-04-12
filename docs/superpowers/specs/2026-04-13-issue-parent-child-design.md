# Issue 父子关系与来源标识

## Context

Agent 在 loop 中通过 Evaluator 发现问题时会创建新 issue（`_create_side_issue`），但目前这些 issue 和触发它们的父 issue 没有任何关联，也无法区分是人类还是 Agent 创建的。

## 设计

### 数据模型

Issue dataclass 新增两个字段：
- `source: str = "human"` — `"human"` 或 `"agent"`
- `parent_id: str | None = None` — Agent 创建的子 issue 指向父 issue ID

不加 `children` 字段，通过查询 `parent_id` 反向获取子 issue 列表。

### 后端

- `core/models.py` — Issue 加 `source`、`parent_id` 字段，`to_json`/`from_json` 兼容
- `core/ralph_loop.py` — `_create_side_issue` 接收 `parent_issue_id`，设置 `source="agent"` 和 `parent_id`
- `server/routes/issues.py`:
  - `CreateIssueRequest` 加可选 `parent_id`
  - `GET /issues/{id}` 额外查询 children（id + title + status）附在响应里
  - `POST /issues` 创建时 source 默认 `"human"`
- `cli/main.py` — 不改，CLI 创建的 issue 默认 `source="human"`

### 前端

- `web/src/stores/boardStore.ts` — Issue 接口加 `source`、`parent_id`
- `web/src/components/IssueCard.tsx` — agent 创建的 issue 显示机器人小图标
- `web/src/components/IssueDetail.tsx`:
  - 有 `parent_id` 时显示"来源于 {parent_id}"（可点击）
  - 底部新增"子 Issue"区块，列出 children 的 id、title、status

### 调度关系

子 issue 独立流转，仅展示关系，不影响父 issue 状态。

## 涉及文件

- `core/models.py`
- `core/ralph_loop.py`
- `server/routes/issues.py`
- `web/src/stores/boardStore.ts`
- `web/src/components/IssueCard.tsx`
- `web/src/components/IssueDetail.tsx`

## 验证

1. `python -m pytest tests/ -x -q`
2. `cd web && npx tsc --noEmit`
3. Agent 创建的 side issue 有 `source=agent` 和正确的 `parent_id`
4. 父 issue 详情页能看到子 issue 列表
5. IssueCard 上 agent 创建的 issue 有机器人图标
