import { create } from 'zustand'

export interface Issue {
  id: string
  title: string
  status: string
  priority: string
  assignee: string | null
  workspace: string
  blocks: string[]
  blocked_by: string[]
  labels: string[]
  created_at: string
  updated_at: string
  retry_count: number
  content?: string
  cost?: number
}

export interface BoardColumn {
  id: string
  name: string
  issues: string[]
}

export interface SSELogEntry {
  id: string
  type: string
  message: string
  timestamp: string
  issueId?: string
}

export interface AgentLogEntry {
  ts: number
  type: string
  data: Record<string, any>
}

interface CreateIssuePayload {
  title: string
  priority?: string
  labels?: string[]
  description?: string
  blocked_by?: string[]
}

interface BoardState {
  columns: BoardColumn[]
  issues: Record<string, Issue>
  projectId: string | null
  loading: boolean
  sseLog: SSELogEntry[]
  agentLogs: Record<string, AgentLogEntry[]>
  wsSend: ((msg: Record<string, unknown>) => void) | null
  setProjectId: (id: string) => void
  fetchBoard: () => Promise<void>
  fetchIssues: () => Promise<void>
  moveIssue: (issueId: string, toColumn: string) => Promise<{ ok: boolean; error?: string }>
  createIssue: (title: string, priority?: string, labels?: string[], description?: string, blockedBy?: string[]) => Promise<void>
  reviewIssue: (issueId: string, approved: boolean, comment?: string) => Promise<void>
  updateIssue: (issueId: string, patch: Partial<Pick<Issue, 'title' | 'priority' | 'labels' | 'blocked_by'>>) => Promise<void>
  updateIssueContent: (issueId: string, content: string) => Promise<void>
  deleteIssue: (issueId: string) => Promise<void>
  runAllIssues: () => Promise<void>
  runSingleIssue: (issueId: string) => Promise<void>
  addSSELog: (entry: SSELogEntry) => void
  clearSSELog: () => void
  appendAgentLog: (issueId: string, entry: AgentLogEntry) => void
  clearAgentLog: (issueId: string) => void
  setWsSend: (fn: ((msg: Record<string, unknown>) => void) | null) => void
  updateIssueFromEvent: (issue: Issue) => void
  moveBoardFromEvent: (issueId: string, toColumn: string) => void
}

let logIdCounter = 0

export const useBoardStore = create<BoardState>((set, get) => ({
  columns: [],
  issues: {},
  projectId: null,
  loading: false,
  sseLog: [],
  agentLogs: {},
  wsSend: null,

  setProjectId: (id) => set({ projectId: id }),

  fetchBoard: async () => {
    const { projectId } = get()
    if (!projectId) return
    set({ loading: true })
    const res = await fetch(`/api/projects/${projectId}/board`)
    const data = await res.json()
    set({ columns: data.columns, loading: false })
  },

  fetchIssues: async () => {
    const { projectId } = get()
    if (!projectId) return
    const res = await fetch(`/api/projects/${projectId}/issues`)
    const list: Issue[] = await res.json()
    const map: Record<string, Issue> = {}
    for (const issue of list) map[issue.id] = issue
    set({ issues: map })
  },

  moveIssue: async (issueId, toColumn) => {
    const { projectId, columns } = get()
    if (!projectId) return { ok: false, error: 'No project selected' }

    // Save snapshot for rollback
    const snapshot = columns.map(col => ({ ...col, issues: [...col.issues] }))

    // Optimistic update
    const newColumns = columns.map(col => ({
      ...col,
      issues: col.issues.filter(id => id !== issueId),
    }))
    const target = newColumns.find(c => c.id === toColumn)
    if (target) target.issues.push(issueId)
    set({ columns: newColumns })

    const res = await fetch(`/api/projects/${projectId}/board/move/${issueId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to_column: toColumn }),
    })

    if (!res.ok) {
      // Rollback
      set({ columns: snapshot })
      const data = await res.json().catch(() => ({}))
      const error = data.detail || `Cannot move to ${toColumn}`
      return { ok: false, error }
    }

    // Refresh issue data to get updated status
    await get().fetchIssues()
    return { ok: true }
  },

  createIssue: async (title, priority = 'medium', labels = [], description = '', blockedBy = []) => {
    const { projectId } = get()
    if (!projectId) return
    const payload: CreateIssuePayload = { title, priority, labels }
    if (description) payload.description = description
    if (blockedBy.length > 0) payload.blocked_by = blockedBy
    await fetch(`/api/projects/${projectId}/issues`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    await get().fetchBoard()
    await get().fetchIssues()
  },

  reviewIssue: async (issueId, approved, comment = '') => {
    const { projectId } = get()
    if (!projectId) return
    await fetch(`/api/projects/${projectId}/issues/${issueId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved, comment }),
    })
    await get().fetchBoard()
    await get().fetchIssues()
  },

  updateIssue: async (issueId, patch) => {
    const { projectId } = get()
    if (!projectId) return
    const res = await fetch(`/api/projects/${projectId}/issues/${issueId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    if (res.ok) {
      const updated: Issue = await res.json()
      set(state => ({ issues: { ...state.issues, [issueId]: updated } }))
    }
  },

  updateIssueContent: async (issueId, content) => {
    const { projectId } = get()
    if (!projectId) return
    await fetch(`/api/projects/${projectId}/issues/${issueId}/content`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    })
  },

  deleteIssue: async (issueId) => {
    const { projectId } = get()
    if (!projectId) return
    await fetch(`/api/projects/${projectId}/issues/${issueId}`, {
      method: 'DELETE',
    })
    await get().fetchBoard()
    await get().fetchIssues()
  },

  runAllIssues: async () => {
    const { projectId } = get()
    if (!projectId) return
    await fetch(`/api/projects/${projectId}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
  },

  runSingleIssue: async (issueId) => {
    const { projectId } = get()
    if (!projectId) return
    await fetch(`/api/projects/${projectId}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ issue_id: issueId }),
    })
  },

  addSSELog: (entry) => {
    set(state => ({
      sseLog: [...state.sseLog.slice(-199), entry],
    }))
  },

  clearSSELog: () => set({ sseLog: [] }),

  appendAgentLog: (issueId, entry) => {
    set(state => {
      const existing = state.agentLogs[issueId] || []
      return {
        agentLogs: {
          ...state.agentLogs,
          [issueId]: [...existing.slice(-499), entry],
        },
      }
    })
  },

  clearAgentLog: (issueId) => {
    set(state => {
      const { [issueId]: _, ...rest } = state.agentLogs
      return { agentLogs: rest }
    })
  },

  setWsSend: (fn) => set({ wsSend: fn }),

  updateIssueFromEvent: (issue) => {
    set(state => ({ issues: { ...state.issues, [issue.id]: issue } }))
  },

  moveBoardFromEvent: (issueId, toColumn) => {
    set(state => {
      const newColumns = state.columns.map(col => ({
        ...col,
        issues: col.issues.filter(id => id !== issueId),
      }))
      const target = newColumns.find(c => c.id === toColumn)
      if (target) target.issues.push(issueId)
      return { columns: newColumns }
    })
  },
}))

export function generateLogId(): string {
  return `log-${Date.now()}-${++logIdCounter}`
}
