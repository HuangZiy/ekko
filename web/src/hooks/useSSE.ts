import { useEffect, useRef } from 'react'
import { useBoardStore, generateLogId } from '../stores/boardStore'

export function useSSE() {
  const projectId = useBoardStore(s => s.projectId)
  const updateIssueFromEvent = useBoardStore(s => s.updateIssueFromEvent)
  const moveBoardFromEvent = useBoardStore(s => s.moveBoardFromEvent)
  const fetchBoard = useBoardStore(s => s.fetchBoard)
  const fetchIssues = useBoardStore(s => s.fetchIssues)
  const addSSELog = useBoardStore(s => s.addSSELog)
  const sourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!projectId) return

    const source = new EventSource(`/api/projects/${projectId}/events`)
    sourceRef.current = source

    const logEvent = (type: string, message: string, issueId?: string) => {
      addSSELog({
        id: generateLogId(),
        type,
        message,
        timestamp: new Date().toISOString(),
        issueId,
      })
    }

    source.addEventListener('issue_updated', (e) => {
      const data = JSON.parse(e.data)
      if (data.issue) {
        updateIssueFromEvent(data.issue)
        logEvent('issue_updated', `Issue ${data.issue.id} updated: ${data.issue.title}`, data.issue.id)
      }
    })

    source.addEventListener('issue_created', (e) => {
      const data = JSON.parse(e.data)
      logEvent('issue_created', `Issue created: ${data.issue?.title || data.issue_id || 'unknown'}`, data.issue_id)
      fetchBoard()
      fetchIssues()
    })

    source.addEventListener('issue_moved', (e) => {
      const data = JSON.parse(e.data)
      moveBoardFromEvent(data.issue_id, data.to_column)
      logEvent('issue_moved', `Issue ${data.issue_id} moved to ${data.to_column}`, data.issue_id)
    })

    source.addEventListener('issue_approved', (e) => {
      const data = JSON.parse(e.data)
      logEvent('issue_approved', `Issue ${data.issue_id || 'unknown'} approved`, data.issue_id)
      fetchBoard()
      fetchIssues()
    })

    source.addEventListener('issue_rejected', (e) => {
      const data = JSON.parse(e.data)
      logEvent('issue_rejected', `Issue ${data.issue_id || 'unknown'} rejected`, data.issue_id)
      fetchBoard()
      fetchIssues()
    })

    source.addEventListener('agent_started', (e) => {
      const data = JSON.parse(e.data)
      logEvent('agent_started', `Agent started on issue ${data.issue_id || 'unknown'}`, data.issue_id)
      fetchBoard()
      fetchIssues()
    })

    source.addEventListener('agent_done', (e) => {
      const data = JSON.parse(e.data)
      logEvent('agent_done', `Agent completed issue ${data.issue_id || 'unknown'}`, data.issue_id)
      fetchBoard()
      fetchIssues()
    })

    source.onerror = () => {
      setTimeout(() => {
        source.close()
      }, 3000)
    }

    return () => {
      source.close()
      sourceRef.current = null
    }
  }, [projectId, updateIssueFromEvent, moveBoardFromEvent, fetchBoard, fetchIssues, addSSELog])
}
