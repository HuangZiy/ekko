import { useEffect, useRef, useCallback } from 'react'
import { useBoardStore, generateLogId } from '../stores/boardStore'
import { useProjectStore } from '../stores/projectStore'

const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000

export function useWebSocket() {
  const projectId = useBoardStore(s => s.projectId)
  const updateIssueFromEvent = useBoardStore(s => s.updateIssueFromEvent)
  const moveBoardFromEvent = useBoardStore(s => s.moveBoardFromEvent)
  const fetchBoard = useBoardStore(s => s.fetchBoard)
  const fetchIssues = useBoardStore(s => s.fetchIssues)
  const addSSELog = useBoardStore(s => s.addSSELog)
  const appendAgentLog = useBoardStore(s => s.appendAgentLog)
  const setWsSend = useBoardStore(s => s.setWsSend)
  const removeRunningIssue = useBoardStore(s => s.removeRunningIssue)
  const setPlanningActive = useBoardStore(s => s.setPlanningActive)
  const fetchProjects = useProjectStore(s => s.fetchProjects)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttempt = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const sendMessage = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  useEffect(() => {
    if (!projectId) return

    let disposed = false

    function connect() {
      if (disposed) return

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/api/projects/${projectId}/ws`)
      wsRef.current = ws

      const logEvent = (type: string, message: string, issueId?: string) => {
        addSSELog({
          id: generateLogId(),
          type,
          message,
          timestamp: new Date().toISOString(),
          issueId,
        })
      }

      ws.onopen = () => {
        reconnectAttempt.current = 0
        setWsSend(sendMessage)
      }

      ws.onmessage = (event) => {
        let data: Record<string, any>
        try {
          data = JSON.parse(event.data)
        } catch {
          return
        }

        const type = data.type as string
        const payload = data.data as Record<string, any> | undefined

        switch (type) {
          case 'ping':
            sendMessage({ type: 'pong' })
            break

          case 'issue_updated':
            if (payload?.issue) {
              updateIssueFromEvent(payload.issue)
              logEvent('issue_updated', `Issue ${payload.issue.id} updated: ${payload.issue.title}`, payload.issue.id)
              fetchProjects()
            }
            break

          case 'issue_created':
            logEvent('issue_created', `Issue created: ${payload?.issue?.title || payload?.issue_id || 'unknown'}`, payload?.issue_id)
            fetchBoard()
            fetchIssues()
            fetchProjects()
            break

          case 'issue_moved':
            if (payload) {
              moveBoardFromEvent(payload.issue_id, payload.to_column)
              logEvent('issue_moved', `Issue ${payload.issue_id} moved to ${payload.to_column}`, payload.issue_id)
            }
            break

          case 'issue_approved':
            logEvent('issue_approved', `Issue ${payload?.issue_id || 'unknown'} approved`, payload?.issue_id)
            fetchBoard()
            fetchIssues()
            fetchProjects()
            break

          case 'issue_rejected':
            logEvent('issue_rejected', `Issue ${payload?.issue_id || 'unknown'} rejected`, payload?.issue_id)
            fetchBoard()
            fetchIssues()
            fetchProjects()
            break

          case 'issue_deleted':
            logEvent('issue_deleted', `Issue ${payload?.issue_id || 'unknown'} deleted`, payload?.issue_id)
            fetchBoard()
            fetchIssues()
            fetchProjects()
            break

          case 'agent_started':
            logEvent('agent_started', `Agent started on ${payload?.issue_id || 'unknown'}`, payload?.issue_id)
            if (payload?.issue_id) removeRunningIssue(payload.issue_id)
            fetchBoard()
            fetchIssues()
            break

          case 'agent_done':
            logEvent('agent_done', `Agent completed ${payload?.issue_id || 'unknown'}`, payload?.issue_id)
            if (payload?.issue_id) removeRunningIssue(payload.issue_id)
            fetchBoard()
            fetchIssues()
            fetchProjects()
            break

          case 'agent_token':
            if (data.issue_id) {
              appendAgentLog(data.issue_id, {
                ts: data.ts, type: 'agent_token', data: data.data,
              })
            }
            break

          case 'agent_tool_call':
            if (data.issue_id) {
              appendAgentLog(data.issue_id, {
                ts: data.ts, type: 'agent_tool_call', data: data.data,
              })
            }
            break

          case 'agent_status':
            if (data.issue_id) {
              appendAgentLog(data.issue_id, {
                ts: data.ts, type: 'agent_status', data: data.data,
              })
            }
            break

          case 'harness_log':
            if (data.issue_id) {
              appendAgentLog(data.issue_id, {
                ts: data.ts, type: 'harness_log', data: data.data,
              })
            }
            break

          case 'run_error':
            logEvent('run_error', payload?.issue_id ? `${payload.issue_id}: ${payload.error}` : (payload?.error || 'Run failed'), payload?.issue_id)
            if (payload?.issue_id) removeRunningIssue(payload.issue_id)
            break

          case 'planning_started':
            if (payload?.issue_id) {
              setPlanningActive(payload.issue_id, true)
              logEvent('planning_started', `Planning started for ${payload.issue_id}`, payload.issue_id)
            }
            break

          case 'planning_output':
            window.dispatchEvent(new CustomEvent('planning_output', {
              detail: { issue_id: data.issue_id, data: data.data },
            }))
            break

          case 'planning_ended':
            if (payload?.issue_id) {
              setPlanningActive(payload.issue_id, false)
              logEvent('planning_ended', `Planning ended for ${payload.issue_id}`, payload.issue_id)
              fetchBoard()
              fetchIssues()
            }
            break
        }
      }

      ws.onclose = () => {
        wsRef.current = null
        setWsSend(null)
        if (!disposed) {
          const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt.current), RECONNECT_MAX_MS)
          reconnectAttempt.current++
          reconnectTimer.current = setTimeout(connect, delay)
        }
      }

      ws.onerror = () => {
        // onclose will fire after onerror, reconnect handled there
      }
    }

    connect()

    return () => {
      disposed = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      setWsSend(null)
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [projectId, updateIssueFromEvent, moveBoardFromEvent, fetchBoard, fetchIssues, addSSELog, appendAgentLog, setWsSend, removeRunningIssue, setPlanningActive, fetchProjects, sendMessage])

  return { sendMessage }
}
