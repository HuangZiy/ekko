import { useRef, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Terminal, ChevronDown, ChevronUp, Trash2 } from 'lucide-react'
import { useBoardStore } from '../stores/boardStore'
import type { SSELogEntry } from '../stores/boardStore'

const typeColors: Record<string, string> = {
  agent_started: 'text-amber-500',
  agent_done: 'text-violet-500',
  issue_created: 'text-blue-500',
  issue_updated: 'text-cyan-500',
  issue_moved: 'text-green-500',
  issue_approved: 'text-green-600',
  issue_rejected: 'text-red-500',
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function RunLogPanel() {
  const [open, setOpen] = useState(false)
  const sseLog = useBoardStore(s => s.sseLog)
  const clearSSELog = useBoardStore(s => s.clearSSELog)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [sseLog, open])

  return (
    <div className="fixed bottom-0 left-64 right-0 z-40">
      {/* Toggle bar */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-4 py-1.5 bg-[var(--bg-card)] border-t border-x border-[var(--border)] rounded-t-lg ml-4 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
      >
        <Terminal size={14} />
        <span>Event Log</span>
        {sseLog.length > 0 && (
          <span className="px-1.5 py-0.5 text-xs rounded-full bg-[var(--accent)] text-white">
            {sseLog.length}
          </span>
        )}
        {open ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 220 }}
            exit={{ height: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="overflow-hidden bg-[var(--bg-card)] border-t border-[var(--border)]"
          >
            <div className="flex items-center justify-between px-4 py-1.5 border-b border-[var(--border)]">
              <span className="text-xs font-medium text-[var(--text-secondary)]">SSE Events</span>
              <button
                onClick={clearSSELog}
                className="text-xs text-[var(--text-secondary)] hover:text-[var(--danger)] flex items-center gap-1"
              >
                <Trash2 size={12} /> Clear
              </button>
            </div>
            <div ref={scrollRef} className="h-[180px] overflow-y-auto px-4 py-2 font-mono text-xs space-y-0.5">
              {sseLog.length === 0 && (
                <div className="text-[var(--text-secondary)] py-4 text-center">
                  No events yet. Events will appear here as they arrive via SSE.
                </div>
              )}
              {sseLog.map((entry: SSELogEntry) => (
                <div key={entry.id} className="flex gap-2">
                  <span className="text-[var(--text-secondary)] shrink-0">{formatTime(entry.timestamp)}</span>
                  <span className={`shrink-0 ${typeColors[entry.type] || 'text-[var(--text-secondary)]'}`}>
                    [{entry.type}]
                  </span>
                  <span className="text-[var(--text-primary)] truncate">{entry.message}</span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
