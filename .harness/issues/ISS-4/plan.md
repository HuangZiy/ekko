# ISS-4: harness 增加 planning agent

## 概述

在 harness 的 Generator (Ralph) 前增加一个 Planning Agent 步骤。Planning Agent 分析 issue 的复杂度，生成结构化的执行计划（带 checklist），并在必要时将复杂 issue 拆分为子 issue。

## 变更清单

### 1. 新增 Planning Agent 系统提示词
- [x] 创建 `prompts/planning_prompt.md`
- Planning Agent 的职责：分析 issue、生成 plan.md、判断是否需要拆分
- 输出格式：结构化的 checklist plan + 可选的 `[SPLIT]` 指令

### 2. 新增 Planning Agent 模块
- [x] 创建 `core/planner.py`
- `run_issue_planning(issue, storage, workspace)` — 核心函数
- 使用 `claude_agent_sdk.query()` 调用 LLM
- 工具集：Read, Glob, Grep（只读分析）+ Write（仅写 plan.md）
- 解析输出：提取 plan 写入 `plan.md`，解析 `[SPLIT]` 创建子 issue
- 返回 stats dict（cost, duration, 是否拆分等）

### 3. 集成到 ralph_loop.py
- [x] 在 `run_issue_loop()` 的 Generator 循环前插入 Planning 步骤
- 状态流转：backlog/todo → planning → todo → in_progress
- Planning 完成后 issue 状态从 planning → todo
- 如果 planning 产生了子 issue，当前 issue 设置 blocked_by 子 issue
- 子 issue 创建时设置 `parent_id`

### 4. 更新数据模型和看板
- [x] `models.py`: 在 BOARD_COLUMNS 中添加 "planning" 列
- [x] `ralph_loop.py`: `_sync_board()` 的 `status_to_col` 映射添加 planning

### 5. 更新配置
- [x] `config.py`: 添加 `MAX_PLANNING_TURNS` 和 `MAX_PLANNING_BUDGET` 常量

### 6. Evaluator plan 追加支持
- [x] 在 evaluator 结果处理中增加 `[PLAN_APPEND]` 标记支持，追加到 plan.md

### 7. CLI 支持
- [x] `cli/main.py`: 添加 `plan-issue` 子命令，可单独对某个 issue 运行 planning

## 关键设计决策

1. **Planning Agent 是只读的**：它只分析代码库和 issue 内容，不修改源码。唯一的写操作是 plan.md。
2. **拆分阈值**：Planning Agent 根据任务描述中的信号（多个独立关注点、跨层变更、描述过长、涉及新建超过5个文件）决定是否拆分。
3. **父子关系**：拆分出的子 issue 通过 `parent_id` 关联父 issue，父 issue 的 blocked_by 设置为子 issue。
4. **plan.md 格式**：使用 `- [ ]` / `- [x]` checklist，Generator 完成一项就勾选一项。
