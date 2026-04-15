# Planning 状态优化 — 嵌入式终端 + Issue 精炼工作流

**日期**: 2026-04-15
**状态**: Draft

## 背景

Ekko 的 kanban 中 `PLANNING` 状态已存在于枚举和看板列中，但从未被执行引擎使用——启动时甚至会将 PLANNING 状态的 Issue 重置回 BACKLOG。

用户需要一个 **人类驱动的 Planning 阶段**：在 Issue 创建后、Agent 执行前，人类可以借助 superpowers brainstorming 来拆分 Issue 粒度、完善描述内容。这与 Agent 内部的 `plan.md`（实现计划）是完全不同的概念——Planning 是人的流程，Plan 是 Agent 的步骤。

## 目标

1. 激活 `PLANNING` 为真实的工作流状态
2. Issue 创建后，用户可选择 "Run"（直接执行）或 "Planning"（进入人类精炼流程）
3. Planning 状态下，Issue 详情页嵌入 xterm.js 终端，运行受限的 Claude Code 子进程
4. 用户通过终端使用 superpowers brainstorming 辅助拆分和完善 Issue
5. brainstorming 产出（更新的描述、新建的子 Issue）自动同步回 Issue 系统

## 设计

### 1. 状态流转变更

**文件**: `core/models.py`, `web/src/constants/transitions.ts`

当前 PLANNING 的转换：
```
planning → todo, backlog
```

新增 `planning → in_progress`，支持从 Planning 直接 RUN：
```python
VALID_TRANSITIONS = {
    IssueStatus.BACKLOG:     {IssueStatus.PLANNING, IssueStatus.TODO},
    IssueStatus.PLANNING:    {IssueStatus.TODO, IssueStatus.BACKLOG, IssueStatus.IN_PROGRESS},  # 新增 IN_PROGRESS
    IssueStatus.TODO:        {IssueStatus.IN_PROGRESS, IssueStatus.BACKLOG},
    # ... 其余不变
}
```

前端 `transitions.ts` 同步更新：
```ts
planning: ['todo', 'backlog', 'in_progress'],
```

**移除启动重置逻辑**: `server/app.py` 中 `_reset_stuck_issues()` 的 `PLANNING → BACKLOG` 分支删除。Planning 是合法的持久状态，服务器重启不应干扰。

### 2. IssueCard 按钮增强

**文件**: `web/src/components/IssueCard.tsx`

在 Backlog 列的卡片上，现有 Run (Play) 按钮旁增加 "Planning" 按钮（使用 `ClipboardList` 或 `FileSearch` 图标）。

逻辑：
- `canPlan`: `issue.status === 'backlog'`（只有 Backlog 状态可进入 Planning）
- 点击后调用 `boardStore.moveIssue(issue.id, 'planning')`
- Planning 列的卡片显示 Run 按钮（因为 `planning → in_progress` 现在合法）

更新 `canRun` 条件，增加 `planning` 状态：
```ts
const canRun = !hasOtherRunning && ['todo', 'rejected', 'backlog', 'failed', 'planning'].includes(issue.status)
```

### 3. 后端 Planning Terminal 会话管理

**新文件**: `server/routes/planning.py`

#### 3.1 会话数据结构

```python
@dataclass
class PlanningSession:
    issue_id: str
    project_id: str
    process: asyncio.subprocess.Process
    master_fd: int          # PTY master file descriptor
    started_at: str
    content_snapshot: str   # 会话开始时的 content.md 快照，用于 diff

# 全局会话注册表
_sessions: dict[str, PlanningSession] = {}  # issue_id → session
```

#### 3.2 PTY 子进程管理

使用 PTY（伪终端）启动 Claude Code 交互模式，这样 Claude Code 认为自己运行在真实终端中，会渲染完整的 TUI（颜色、进度条、工具调用展示），xterm.js 直接显示原始终端输出。

```python
import pty, os, asyncio, struct, fcntl, termios

master_fd, slave_fd = pty.openpty()
# 设置初始终端大小（前端 xterm.js 的 cols/rows）
winsize = struct.pack('HHHH', rows, cols, 0, 0)
fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

process = await asyncio.create_subprocess_exec(
    'claude',  # 交互模式，不加 --print
    stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
    cwd=str(workspace_path),
    env={**os.environ, 'TERM': 'xterm-256color'},
    preexec_fn=os.setsid,
)
os.close(slave_fd)  # 父进程只用 master_fd

# 异步读取 master_fd（在线程池中执行 os.read）
async def _read_loop():
    loop = asyncio.get_event_loop()
    while True:
        data = await loop.run_in_executor(None, os.read, master_fd, 4096)
        if not data:
            break
        await ws_manager.broadcast(project_id, {
            "type": "planning_output",
            "issue_id": issue_id,
            "data": data.decode('utf-8', errors='replace'),
        })
```

#### 3.3 API 端点

**`POST /api/projects/{pid}/planning/start`**
- Body: `{ issue_id: str, cols: int, rows: int }`
- 验证 Issue 状态为 `planning`
- 快照当前 `content.md`
- 通过 PTY 启动 Claude Code 交互式子进程（见 3.2）
- 注册到 `_sessions`
- 启动异步读取任务，广播 `planning_output` WS 事件
- 广播 `planning_started` 事件
- 返回 `{ ok: true, session_id: issue_id }`

**`POST /api/projects/{pid}/planning/input`**
- Body: `{ issue_id: str, data: str }`
- 查找对应 session，写入 `os.write(master_fd, data.encode())`
- 返回 `{ ok: true }`

**`POST /api/projects/{pid}/planning/resize`**
- Body: `{ issue_id: str, cols: int, rows: int }`
- 通过 `ioctl(master_fd, TIOCSWINSZ, ...)` 更新终端大小
- 返回 `{ ok: true }`

**`POST /api/projects/{pid}/planning/stop`**
- Body: `{ issue_id: str }`
- 终止子进程（`process.terminate()`，超时后 `process.kill()`）
- 关闭 master_fd
- 触发 auto-sync（见第 5 节）
- 清理 session
- 广播 `planning_ended` 事件
- 返回 `{ ok: true, sync_result: {...} }`

#### 3.4 WS 事件处理

在现有 WS 路由（`server/routes/ws.py`）中增加对 `planning_input` 和 `planning_resize` 消息类型的处理：

```python
elif msg_type == "planning_input":
    from server.routes.planning import handle_planning_input
    await handle_planning_input(msg.get("issue_id"), msg.get("data", ""))
elif msg_type == "planning_resize":
    from server.routes.planning import handle_planning_resize
    await handle_planning_resize(msg.get("issue_id"), msg.get("cols", 80), msg.get("rows", 24))
```

这样前端可以通过已有的 WS 连接发送终端输入和窗口大小变更，无需额外连接。

#### 3.5 子进程管理细节

- 使用 PTY + `asyncio.create_subprocess_exec` 启动交互式 Claude Code
- 命令白名单：只允许启动 `claude` 可执行文件，不暴露完整 shell
- PTY master_fd 读取在线程池中执行（`loop.run_in_executor`），避免阻塞事件循环
- 终端大小变更通过 `ioctl(TIOCSWINSZ)` 传递给子进程
- 进程异常退出时自动触发 cleanup + sync + 关闭 master_fd
- 单 Issue 同一时间只允许一个 planning session

### 4. 前端 PlanningTerminal 组件

**新文件**: `web/src/components/PlanningTerminal.tsx`

#### 4.1 依赖

```
npm install @xterm/xterm @xterm/addon-fit
```

#### 4.2 组件设计

```tsx
interface PlanningTerminalProps {
  issueId: string
  projectId: string
}
```

核心逻辑：
- 挂载时初始化 xterm.js Terminal 实例 + FitAddon
- 监听 WS 的 `planning_output` 事件（通过 boardStore 新增的 slice），写入 terminal
- 用户键入时通过 `wsSend({ type: 'planning_input', issue_id, data })` 发送
- 提供 "Start Planning" 按钮调用 `POST /planning/start`
- 提供 "Stop Planning" 按钮调用 `POST /planning/stop`
- 组件卸载时如果 session 仍在运行，提示用户是否停止

#### 4.3 在 IssueDetail 中集成

**文件**: `web/src/components/IssueDetail.tsx`

在 `issue.status === 'planning'` 时渲染 `PlanningTerminal`：

```tsx
{/* Planning Terminal */}
{issue.status === 'planning' && (
  <PlanningTerminal issueId={issue.id} projectId={projectId} />
)}
```

位置：放在 Status/Priority 区域之后、Plan 编辑器之前。

#### 4.4 boardStore 扩展

**文件**: `web/src/stores/boardStore.ts`

新增状态 slice：
```ts
planningSessionActive: Record<string, boolean>  // issue_id → active
setPlanningSessionActive: (issueId: string, active: boolean) => void
startPlanning: (issueId: string) => Promise<void>  // POST /planning/start
stopPlanning: (issueId: string) => Promise<void>   // POST /planning/stop
```

#### 4.5 useWebSocket 扩展

**文件**: `web/src/hooks/useWebSocket.ts`

新增事件处理：
```ts
case 'planning_started':
  setPlanningSessionActive(data.issue_id, true)
  break
case 'planning_output':
  // 通过自定义事件分发给 PlanningTerminal 组件
  window.dispatchEvent(new CustomEvent('planning_output', { detail: data }))
  break
case 'planning_ended':
  setPlanningSessionActive(data.issue_id, false)
  fetchIssues()  // 刷新以获取 sync 后的数据
  break
```

`planning_output` 使用 CustomEvent 分发而非存入 store，因为终端数据量大且是流式的，不适合放在 Zustand 状态中。

### 5. Auto-Sync 机制

**位置**: `server/routes/planning.py` 中的 `_sync_after_planning()` 函数

Planning 会话结束时（用户点 Stop 或进程自然退出）触发：

1. **Content diff**: 重新读取 `content.md`，与会话开始时的快照对比。如果有变更，广播 `issue_updated`
2. **子 Issue 扫描**: 列出当前 Issue 的 children（通过 `parent_id` 关联），与会话开始时对比。新增的子 Issue 广播 `issue_created`
3. **Board 刷新**: 如果有新子 Issue，它们应该已经在 board 的 backlog 列中（由 harness CLI 创建时自动添加）

```python
async def _sync_after_planning(session: PlanningSession, storage: ProjectStorage) -> dict:
    # 1. Check content changes
    current_content = storage.load_issue_content(session.issue_id)
    content_changed = current_content != session.content_snapshot
    
    # 2. Check for new child issues
    issue = storage.load_issue(session.issue_id)
    all_issues = storage.list_issues()
    new_children = [i for i in all_issues if i.parent_id == session.issue_id and i.created_at > session.started_at]
    
    # 3. Broadcast updates
    if content_changed:
        await ws_manager.broadcast(session.project_id, {
            "type": "issue_updated", "data": {"issue": issue.to_json()}
        })
    for child in new_children:
        await ws_manager.broadcast(session.project_id, {
            "type": "issue_created", "data": {"issue": child.to_json()}
        })
    
    return {
        "content_changed": content_changed,
        "new_children": [c.id for c in new_children],
    }
```

### 6. i18n

**文件**: `web/src/i18n/locales/en.json`, `zh.json`

新增键：
- `issueCard.planning` / `issueCard.planningTitle`
- `issueDetail.planningTerminal` / `issueDetail.startPlanning` / `issueDetail.stopPlanning`
- `issueDetail.planningActive` / `issueDetail.planningEnded`
- `issueDetail.syncResult`

## 涉及文件清单

| 文件 | 变更类型 |
|------|----------|
| `core/models.py` | 修改 VALID_TRANSITIONS |
| `server/app.py` | 移除 PLANNING 重置逻辑 |
| `server/routes/planning.py` | **新建** — Planning 会话管理 |
| `server/routes/ws.py` (路由文件) | 增加 planning_input 消息处理 |
| `server/app.py` | 注册 planning router |
| `web/src/constants/transitions.ts` | 同步转换规则 |
| `web/src/components/IssueCard.tsx` | 增加 Planning 按钮 |
| `web/src/components/IssueDetail.tsx` | 集成 PlanningTerminal |
| `web/src/components/PlanningTerminal.tsx` | **新建** — xterm.js 终端组件 |
| `web/src/stores/boardStore.ts` | 新增 planning session 状态 |
| `web/src/hooks/useWebSocket.ts` | 新增 planning 事件处理 |
| `web/src/i18n/locales/*.json` | 新增 i18n 键 |
| `web/package.json` | 新增 @xterm/xterm, @xterm/addon-fit 依赖 |

## 验证方案

1. **状态流转**: 创建 Issue → 点击 Planning 按钮 → 确认 Issue 移到 Planning 列 → 点击 Run → 确认进入 In Progress
2. **拖拽**: 从 Backlog 拖到 Planning 列 → 确认状态变更
3. **终端启动**: 打开 Planning 状态的 Issue 详情 → 点击 Start Planning → 确认 xterm.js 终端出现并可交互
4. **终端输入输出**: 在终端中输入命令 → 确认输出正确显示
5. **Auto-Sync**: 在终端中通过 harness CLI 修改 Issue 描述或创建子 Issue → 停止 Planning → 确认 Web UI 自动刷新
6. **服务器重启**: Planning 状态的 Issue 在重启后仍保持 Planning 状态（不被重置）
7. **并发**: 同一 Issue 不能同时开启两个 planning session
