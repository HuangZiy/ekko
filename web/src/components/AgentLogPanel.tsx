import { useRef, useEffect, useState } from 'react'
import { useBoardStore } from '../stores/boardStore'
import type { AgentLogEntry } from '../stores/boardStore'
import { Terminal, Square, History } from 'lucide-react'

interface AgentLogPanelProps {
  issueId: string
  onCancel?: () => void
}

function formatEntry(entry: AgentLogEntry): { label: string; color: string; text: string } {
  switch (entry.type) {
    case 'agent_token':
      return { label: 'LLM', color: 'text-cyan-500', text: entry.data.text || '' }
    case 'agent_tool_call':
      return {
        label: 'Tool',
        color: 'text-yellow-500',
        text: `${entry.data.tool}(${JSON.stringify(entry.data.input).slice(0, 120)})`,
      }
    case 'agent_status': {
      const s = entry.data.status
      const color = s === 'done' ? 'text-green-500' : s === 'failed' ? 'text-red-500' : 'text-blue-500'
      const text = s === 'failed' ? `${s}: ${entry.data.error || ''}` : s
      return { label: 'Status', color, text }
    }
    case 'harness_log': {
      const level = entry.data.level || 'info'
      const phase = entry.data.phase || ''
      const colorMap: Record<string, string> = {
        info: 'text-violet-500', success: 'text-green-500',
        warning: 'text-amber-500', error: 'text-red-500',
      }
      const phaseLabel: Record<string, string> = {
        state: 'State', loop: 'Loop', generator: 'Gen',
        evaluator: 'Eval', evidence: 'Evidence', new_issue: 'NewIssue',
      }
      return {
        label: phaseLabel[phase] || 'Harness',
        color: colorMap[level] || 'text-violet-500',
        text: entry.data.msg || '',
      }
    }
    default:
      return { label: entry.type, color: 'text-gray-400', text: JSON.stringify(entry.data) }
  }
}

export function AgentLogPanel({ issueId, onCancel }: AgentLogPanelProps) {
  const agentLogs = useBoardStore(s => s.agentLogs[issueId] || [])
  const [historyRuns, setHistoryRuns] = useState<string[]>([])
  const [selectedRun, setSelectedRun] = useState<string | null>(null)
  const [historyEntries, setHistoryEntries] = useState<AgentLogEntry[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const projectId = useBoardStore(s => s.projectId)

  useEffect(() => {
    if (!showHistory && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [agentLogs, showHistory])

  useEffect(() => {
    if (!projectId) return
    fetch(`/api/projects/${projectId}/issues/${issueId}/logs`)
      .then(r => r.json())
      .then(data => setHistoryRuns(data.runs || []))
      .catch(() => {})
  }, [projectId, issueId])

  useEffect(() => {
    if (!projectId || !selectedRun) return
    fetch(`/api/projects/${projectId}/issues/${issueId}/logs/${selectedRun}`)
      .then(r => r.json())
      .then(data => setHistoryEntries(data.entries || []))
      .catch(() => {})
  }, [projectId, issueId, selectedRun])

  const entries = showHistory ? historyEntries : agentLogs
  const isRunning = agentLogs.length > 0 && agentLogs[agentLogs.length - 1]?.data?.status !== 'done' && agentLogs[agentLogs.length - 1]?.data?.status !== 'failed'

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 bg-[var(--bg-secondary)] border-b border-[var(--border)] flex items-center gap-2">
        <Terminal size={16} className="text-cyan-500" />
        <h3 className="text-sm font-semibold text-[var(--text-primary)] flex-1">Agent Log</h3>

        {historyRuns.length > 0 && (
          <button
            onClick={() => {
              setShowHistory(!showHistory)
              if (!showHistory && historyRuns.length > 0 && !selectedRun) {
                setSelectedRun(historyRuns[historyRuns.length - 1])
              }
            }}
            className={`flex items-center gap-1 text-xs px-2 py-1 rounded ${showHistory ? 'bg-[var(--accent)] text-white' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}`}
          >
            <History size={12} /> History
          </button>
        )}

        {isRunning && onCancel && (
          <button
            onClick={onCancel}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-red-600 text-white hover:bg-red-700"
          >
            <Square size={12} /> Cancel
          </button>
        )}
      </div>

      {showHistory && historyRuns.length > 0 && (
        <div className="px-4 py-2 border-b border-[var(--border)] flex gap-1 overflow-x-auto">
          {historyRuns.map(run => (
            <button
              key={run}
              onClick={() => setSelectedRun(run)}
              className={`text-xs px-2 py-0.5 rounded ${selectedRun === run ? 'bg-[var(--accent)] text-white' : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}`}
            >
              {run}
            </button>
          ))}
        </div>
      )}

      <div ref={scrollRef} className="h-[240px] overflow-y-auto px-4 py-2 font-mono text-xs space-y-0.5">
        {entries.length === 0 && (
          <div className="text-[var(--text-secondary)] py-8 text-center">
            {showHistory ? 'No entries in this run.' : 'No agent activity yet. Run the issue to see live output.'}
          </div>
        )}
        {entries.map((entry, i) => {
          const { label, color, text } = formatEntry(entry)
          return (
            <div key={i} className="flex gap-2">
              <span className={`shrink-0 ${color}`}>[{label}]</span>
              <span className="text-[var(--text-primary)] whitespace-pre-wrap break-all">{text}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
