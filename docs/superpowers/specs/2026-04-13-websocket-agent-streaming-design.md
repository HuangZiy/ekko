# WebSocket Agent Streaming — 设计文档

## 背景

Ekko 当前使用 SSE 做服务端推送，仅支持 issue 状态变更等粗粒度事件。Agent 执行过程（tool calls、LLM token、命令输出）无法实时展示，且前端无法向 agent 发送指令（取消）。

已知问题：当前 `EventBus` 是全局单例，未按 project_id 过滤，所有客户端收到所有项目的事件。

本设计将 SSE 全面替换为 WebSocket，实现 agent 执行的实时流式输出和双向通信，同时修复事件的项目隔离问题。

## WebSocket 协议

连接地址：`ws://host/api/projects/{project_id}/ws`

### 服务端 → 客户端

```jsonc
// Agent 执行相关
{ "type": "agent_token",       "issue_id": "ISS-1", "data": { "text": "..." } }
{ "type": "agent_tool_call",   "issue_id": "ISS-1", "data": { "tool": "Bash", "input": "npm test" } }
{ "type": "agent_tool_result", "issue_id": "ISS-1", "data": { "tool": "Bash", "output": "..." } }
{ "type": "agent_status",      "issue_id": "ISS-1", "data": { "status": "thinking" | "tool_calling" | "done" | "failed" } }

// 看板相关（替代现有 SSE 事件）
{ "type": "issue_updated", "data": { "issue": {...} } }
{ "type": "issue_moved",   "data": { "issue_id": "ISS-1", "column": "agent_done" } }
{ "type": "issue_created", "data": { "issue": {...} } }

// 心跳
{ "type": "ping" }
```

### 客户端 → 服务端

```jsonc
{ "type": "cancel_agent",   "issue_id": "ISS-1" }
{ "type": "pong" }
// Future (v2): { "type": "user_intervene", "issue_id": "ISS-1", "data": { "message": "..." } }
```

> `user_intervene` 暂不实现。Claude Agent SDK 的 `query()` 是 async generator，中途注入用户消息需要重构执行模型，留作 v2。

心跳：服务端每 20s 发 ping，客户端回 pong。选择 20s 而非 30s，避免部分代理/负载均衡器的 idle timeout（通常 30-60s）。

## Issue Log 存储

每个 issue 目录下新增 `logs/` 子目录，每次 agent 执行生成独立的 JSONL 日志文件：

```
issues/ISS-1/
  meta.json
  content.md
  logs/
    run-001.jsonl
    run-002.jsonl
```

JSONL 格式，每行一个 JSON，与 WebSocket 消息格式一致：

```jsonl
{"ts": 1713000000, "type": "agent_status", "data": {"status": "thinking"}}
{"ts": 1713000001, "type": "agent_token", "data": {"text": "Let me analyze..."}}
{"ts": 1713000002, "type": "agent_tool_call", "data": {"tool": "Bash", "input": "npm test"}}
```

## 后端改动

### 新建 `server/ws.py` — WebSocket 连接管理器

`ConnectionManager` 类：
- `dict[str, list[WebSocket]]`（project_id → 连接列表）
- `connect(project_id, ws)` / `disconnect(project_id, ws)`
- `broadcast(project_id, message: dict)` — 向项目所有连接广播
- 替代现有 `server/sse.py` 的 `EventBus`

### 新建 `server/routes/ws.py` — WebSocket 端点

- `@router.websocket("/api/projects/{project_id}/ws")`
- 接收连接 → 注册到 manager → 循环读取客户端消息 → 断开时清理
- 心跳：后台 task 每 20s 发 ping

### 修改 `core/executor.py` — agent 消息流式推送

- `execute_issue()` 新增 `on_event: Callable[[dict], Awaitable[None]]` 回调参数
- 遍历 `query()` async generator 时，将每条 message 转为事件调用 `on_event`
- 消息类型映射（基于 `claude_agent_sdk` 实际类型）：
  - `AssistantMessage` → 遍历 `.content` blocks：
    - `TextBlock` → `agent_token`（`.text`）
    - `ToolUseBlock` → `agent_tool_call`（`.name`, `.input`）
  - `ResultMessage` → `agent_status(done)` 或 `agent_status(failed)`（检查 `.is_error`）
  - `ToolResultBlock` 目前未在 generator 中直接 yield，tool 结果通过下一轮 `AssistantMessage` 体现；如后续 SDK 支持，映射为 `agent_tool_result`
- 同时写入 JSONL 日志文件

### 修改 `core/ralph_loop.py` — 透传 on_event 回调

- `run_issue_loop()` 新增 `on_event` 参数
- 传递给 `_run_generator()` → `execute_issue()`
- 在 issue 状态变更时也通过 `on_event` 发送 `agent_status` 事件（替代当前直接调用 `event_bus.publish`）
- 移除对 `server.sse.event_bus` 的直接依赖

### 修改 `server/routes/run.py` — 对接 WebSocket manager

- `_run_in_background` 中构造 `on_event` 回调，调用 `ws_manager.broadcast(project_id, event)`
- 将 `on_event` 传递给 `ralph_loop.run_issue_loop()`
- 处理 `cancel_agent` 消息：设置 cancellation flag，executor 检查后中断

### 修改 `core/storage.py` — 新增日志方法

- `append_issue_log(issue_id, run_id, entry: dict)`
- `load_issue_logs(issue_id, run_id) -> list[dict]`
- `list_issue_runs(issue_id) -> list[str]`

### 新增 REST API — 历史日志查询（放在 `server/routes/issues.py`）

- `GET /api/projects/{pid}/issues/{iid}/logs` — 列出所有 run
- `GET /api/projects/{pid}/issues/{iid}/logs/{run_id}` — 获取指定 run 的日志

> 日志是 issue 的子资源，放在 issues 路由中，不新建路由文件。

### 删除

- `server/sse.py`
- `server/app.py` 中的 SSE 端点 `/api/projects/{project_id}/events`
- `sse-starlette` 依赖

## 前端改动

### 新建 `web/src/hooks/useWebSocket.ts` — 替代 `useSSE.ts`

- 连接 `ws://host/api/projects/{project_id}/ws`
- 自动重连（指数退避，最大 30s）
- 心跳响应（收到 ping 回 pong）
- 暴露 `send(message)` 方法
- 按 `type` 分发事件到 store

### 修改 `web/src/stores/boardStore.ts`

- SSE 事件处理逻辑不变，数据来源切换到 WebSocket
- 新增 `agentLogs: Record<string, AgentLogEntry[]>`（按 issue_id 存储实时日志）
- 新增 `appendAgentLog(issueId, entry)` / `clearAgentLog(issueId)`

### 新建 `web/src/components/AgentLogPanel.tsx`

- 嵌入 `IssueDetail.tsx` 详情页，作为 tab 或折叠区域
- 实时显示 token 流、tool calls、命令输出
- 支持查看历史 run 日志（REST API）
- 取消按钮：`ws.send({ type: "cancel_agent", issue_id })`

### 删除 `web/src/hooks/useSSE.ts`

- `App.tsx` 中 `useSSE` 调用替换为 `useWebSocket`

### 修改 `web/src/components/RunLogPanel.tsx`

- 从 `sseLog` 切换到 `agentLogs` 数据源

## 关键文件清单

| 操作 | 文件 |
|------|------|
| 新建 | `server/ws.py` |
| 新建 | `server/routes/ws.py` |
| 新建 | `web/src/hooks/useWebSocket.ts` |
| 新建 | `web/src/components/AgentLogPanel.tsx` |
| 修改 | `core/executor.py` |
| 修改 | `core/ralph_loop.py` |
| 修改 | `core/storage.py` |
| 修改 | `server/routes/run.py` |
| 修改 | `server/routes/issues.py` |
| 修改 | `server/app.py` |
| 修改 | `web/src/stores/boardStore.ts` |
| 修改 | `web/src/App.tsx` |
| 修改 | `web/src/components/IssueDetail.tsx` |
| 修改 | `web/src/components/RunLogPanel.tsx` |
| 删除 | `server/sse.py` |
| 删除 | `web/src/hooks/useSSE.ts` |

## 验证

1. `harness serve --dev` 启动，浏览器打开看板
2. 创建 issue 并执行 `harness run`，观察 WebSocket 连接建立
3. Agent 执行过程中，IssueDetail 面板实时显示 token 流和 tool calls
4. 点击取消按钮，agent 中断执行
5. 执行完成后，查看历史日志（切换 run tab）
6. 看板拖拽、issue 状态变更等现有功能正常工作
7. 断开网络后重连，WebSocket 自动恢复
