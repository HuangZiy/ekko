import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { Unicode11Addon } from '@xterm/addon-unicode11'
import '@xterm/xterm/css/xterm.css'
import { useBoardStore } from '../stores/boardStore'
import { Play, Square } from 'lucide-react'

interface PlanningTerminalProps {
  issueId: string
  projectId: string
}

export function PlanningTerminal({ issueId, projectId }: PlanningTerminalProps) {
  const { t } = useTranslation()
  const termRef = useRef<HTMLDivElement>(null)
  const terminalRef = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const wsSendRef = useRef<((msg: Record<string, unknown>) => void) | null>(null)
  const [started, setStarted] = useState(false)

  const isActive = useBoardStore(s => s.planningActive[issueId] ?? false)
  const startPlanning = useBoardStore(s => s.startPlanning)
  const stopPlanning = useBoardStore(s => s.stopPlanning)
  const replayPlanningOutput = useBoardStore(s => s.replayPlanningOutput)
  const wsSend = useBoardStore(s => s.wsSend)

  // Keep wsSend ref in sync without triggering terminal re-init
  useEffect(() => {
    wsSendRef.current = wsSend
  }, [wsSend])

  // Initialize xterm.js — only depends on issueId
  useEffect(() => {
    if (!termRef.current) return

    const terminal = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      theme: {
        background: '#1a1b26',
        foreground: '#a9b1d6',
        cursor: '#c0caf5',
        selectionBackground: '#33467c',
      },
      scrollback: 5000,
      allowProposedApi: true,
    })

    const fitAddon = new FitAddon()
    const unicodeAddon = new Unicode11Addon()
    terminal.loadAddon(fitAddon)
    terminal.loadAddon(unicodeAddon)
    terminal.unicode.activeVersion = '11'
    terminal.open(termRef.current)
    fitAddon.fit()

    terminalRef.current = terminal
    fitAddonRef.current = fitAddon

    // Handle user input -> send via WS ref
    terminal.onData((data) => {
      wsSendRef.current?.({ type: 'planning_input', issue_id: issueId, data })
    })

    // Handle resize
    const resizeObserver = new ResizeObserver(() => {
      fitAddon.fit()
      wsSendRef.current?.({
        type: 'planning_resize',
        issue_id: issueId,
        cols: terminal.cols,
        rows: terminal.rows,
      })
    })
    resizeObserver.observe(termRef.current)

    return () => {
      resizeObserver.disconnect()
      terminal.dispose()
      terminalRef.current = null
      fitAddonRef.current = null
    }
  }, [issueId])

  // Listen for planning_output CustomEvents
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (detail?.issue_id === issueId && detail?.data && terminalRef.current) {
        terminalRef.current.write(detail.data)
      }
    }
    window.addEventListener('planning_output', handler)
    return () => window.removeEventListener('planning_output', handler)
  }, [issueId])

  // Sync started state from store + replay on reconnect
  useEffect(() => {
    setStarted(isActive)
    if (isActive && terminalRef.current) {
      replayPlanningOutput(issueId).then(data => {
        if (data && terminalRef.current) {
          terminalRef.current.write(data)
        }
      })
    }
  }, [isActive, issueId, replayPlanningOutput])

  const handleStart = async () => {
    const terminal = terminalRef.current
    const cols = terminal?.cols ?? 80
    const rows = terminal?.rows ?? 24
    await startPlanning(issueId, cols, rows)
    setStarted(true)
    // Delayed resize to force Claude CLI to redraw with correct dimensions
    setTimeout(() => {
      fitAddonRef.current?.fit()
      const t = terminalRef.current
      if (t) {
        wsSendRef.current?.({
          type: 'planning_resize',
          issue_id: issueId,
          cols: t.cols,
          rows: t.rows,
        })
      }
    }, 1000)
  }

  const handleStop = async () => {
    await stopPlanning(issueId)
    setStarted(false)
  }

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 bg-[var(--bg-secondary)] border-b border-[var(--border)]">
        <span className="text-xs font-medium text-[var(--text-secondary)]">
          {t('issueDetail.planningTerminal')}
        </span>
        <div className="flex items-center gap-2">
          {!started ? (
            <button
              onClick={handleStart}
              className="flex items-center gap-1 px-2 py-1 text-xs bg-violet-600 text-white rounded hover:bg-violet-700 transition-colors"
            >
              <Play size={12} /> {t('issueDetail.startPlanning')}
            </button>
          ) : (
            <button
              onClick={handleStop}
              className="flex items-center gap-1 px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
            >
              <Square size={12} fill="currentColor" /> {t('issueDetail.stopPlanning')}
            </button>
          )}
        </div>
      </div>
      <div
        ref={termRef}
        style={{ height: '500px' }}
      />
    </div>
  )
}
