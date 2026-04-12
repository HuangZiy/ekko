import { useState, useEffect, Component } from 'react'
import type { Issue } from './stores/boardStore'
import type { ReactNode } from 'react'
import { useBoardStore } from './stores/boardStore'
import { useProjectStore } from './stores/projectStore'
import type { ProjectInfo } from './stores/projectStore'
import { useWebSocket } from './hooks/useWebSocket'
import { useTheme } from './hooks/useTheme'
import { Board } from './components/Board'
import { BoardStats } from './components/BoardStats'
import { IssueDetail } from './components/IssueDetail'
import { ProjectSidebar } from './components/ProjectSidebar'
import { ProjectDetail } from './components/ProjectDetail'
import { RunLogPanel } from './components/RunLogPanel'
import { LayoutDashboard, Plus, Play, Sun, Moon } from 'lucide-react'
import { AnimatePresence } from 'framer-motion'
import './index.css'

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 32, color: 'red', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
          <h2>UI Error</h2>
          <p>{this.state.error.message}</p>
          <pre>{this.state.error.stack}</pre>
          <button onClick={() => this.setState({ error: null })} style={{ marginTop: 16, padding: '8px 16px' }}>
            Dismiss
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function App() {
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null)
  const [selectedProject, setSelectedProject] = useState<ProjectInfo | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newPriority, setNewPriority] = useState('medium')
  const [newLabels, setNewLabels] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [newBlockedBy, setNewBlockedBy] = useState('')

  const { theme, toggleTheme } = useTheme()

  const projectId = useBoardStore(s => s.projectId)
  const setProjectId = useBoardStore(s => s.setProjectId)
  const fetchBoard = useBoardStore(s => s.fetchBoard)
  const fetchIssues = useBoardStore(s => s.fetchIssues)
  const createIssue = useBoardStore(s => s.createIssue)
  const reviewIssue = useBoardStore(s => s.reviewIssue)
  const runAllIssues = useBoardStore(s => s.runAllIssues)
  const runSingleIssue = useBoardStore(s => s.runSingleIssue)
  const deleteIssue = useBoardStore(s => s.deleteIssue)
  const issues = useBoardStore(s => s.issues)

  const fetchProjects = useProjectStore(s => s.fetchProjects)
  const activeProjectId = useProjectStore(s => s.activeProjectId)
  const activeProject = useProjectStore(s => s.projects.find(p => p.id === s.activeProjectId))

  const { sendMessage } = useWebSocket()

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  useEffect(() => {
    if (activeProjectId && activeProjectId !== projectId) {
      setProjectId(activeProjectId)
    }
  }, [activeProjectId, projectId, setProjectId])

  useEffect(() => {
    if (projectId) {
      fetchBoard()
      fetchIssues()
    }
  }, [projectId, fetchBoard, fetchIssues])

  useEffect(() => {
    if (selectedIssue && issues[selectedIssue.id] && issues[selectedIssue.id] !== selectedIssue) {
      setSelectedIssue(issues[selectedIssue.id])
    }
  }, [issues])

  const handleProjectSwitch = (id: string) => {
    setProjectId(id)
    setSelectedIssue(null)
  }

  const handleCreate = async () => {
    if (!newTitle.trim()) return
    const labels = newLabels
      .split(',')
      .map(l => l.trim())
      .filter(Boolean)
    const blockedBy = newBlockedBy
      .split(',')
      .map(b => b.trim())
      .filter(Boolean)
    await createIssue(newTitle.trim(), newPriority, labels, newDescription.trim(), blockedBy)
    resetCreateForm()
  }

  const resetCreateForm = () => {
    setNewTitle('')
    setNewPriority('medium')
    setNewLabels('')
    setNewDescription('')
    setNewBlockedBy('')
    setShowCreateForm(false)
  }

  return (
    <div className="h-screen flex">
      <ProjectSidebar onProjectSwitch={handleProjectSwitch} onProjectDetail={setSelectedProject} />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="flex items-center gap-3 px-6 border-b border-[var(--border)] bg-[var(--header-bg)]" style={{ height: 'var(--header-height)' }}>
          <LayoutDashboard size={20} className="text-[var(--accent)]" />
          <h1 className="text-base font-semibold text-[var(--text-primary)]">
            {activeProject?.name || 'Ekko'}
          </h1>
          {projectId && (
            <span className="text-xs text-gray-400 font-mono">{projectId}</span>
          )}
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={toggleTheme}
              className="p-2 rounded-lg hover:bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
            >
              {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            {projectId && (
              <button
                onClick={() => runAllIssues()}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium"
                title="Run all ready issues"
              >
                <Play size={16} /> Run All
              </button>
            )}
            <button
              onClick={() => setShowCreateForm(true)}
              disabled={!projectId}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Plus size={16} /> New Issue
            </button>
          </div>
        </header>

        {/* Board Stats */}
        {projectId && <BoardStats />}

        {/* Board */}
        <main className="flex-1 overflow-hidden">
          {projectId ? (
            <Board onIssueClick={setSelectedIssue} />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400 text-sm">
              Select a project or create one from the sidebar
            </div>
          )}
        </main>
      </div>

      {/* Issue Detail Slide-over */}
      <AnimatePresence>
        {selectedIssue && (
          <ErrorBoundary>
          <IssueDetail
            issue={selectedIssue}
            onClose={() => setSelectedIssue(null)}
            onApprove={() => {
              reviewIssue(selectedIssue.id, true)
              setSelectedIssue(null)
            }}
            onReject={(comment) => {
              reviewIssue(selectedIssue.id, false, comment)
              setSelectedIssue(null)
            }}
            onRun={() => runSingleIssue(selectedIssue.id)}
            onDelete={() => {
              deleteIssue(selectedIssue.id)
              setSelectedIssue(null)
            }}
          />
          </ErrorBoundary>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {selectedProject && (
          <ProjectDetail
            project={selectedProject}
            onClose={() => setSelectedProject(null)}
          />
        )}
      </AnimatePresence>

      {/* Create Issue Modal */}
      {showCreateForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/30" onClick={resetCreateForm} />
          <div className="relative bg-[var(--bg-card)] rounded-xl shadow-xl p-6 w-full max-w-lg">
            <h2 className="text-lg font-semibold mb-4 text-[var(--text-primary)]">New Issue</h2>

            <div className="space-y-3">
              {/* Title */}
              <div>
                <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">Title</label>
                <input
                  autoFocus
                  value={newTitle}
                  onChange={e => setNewTitle(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleCreate()}
                  placeholder="Issue title..."
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-sm bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                />
              </div>

              {/* Priority */}
              <div>
                <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">Priority</label>
                <select
                  value={newPriority}
                  onChange={e => setNewPriority(e.target.value)}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-sm bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </div>

              {/* Labels */}
              <div>
                <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">Labels (comma-separated)</label>
                <input
                  value={newLabels}
                  onChange={e => setNewLabels(e.target.value)}
                  placeholder="bug, frontend, api"
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-sm bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                />
              </div>

              {/* Description */}
              <div>
                <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">Description (markdown)</label>
                <textarea
                  value={newDescription}
                  onChange={e => setNewDescription(e.target.value)}
                  placeholder="Describe the issue..."
                  rows={4}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-sm bg-[var(--input-bg)] text-[var(--text-primary)] resize-y focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                />
              </div>

              {/* Blocked By */}
              <div>
                <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">Blocked by (comma-separated issue IDs)</label>
                <input
                  value={newBlockedBy}
                  onChange={e => setNewBlockedBy(e.target.value)}
                  placeholder="ISSUE-001, ISSUE-002"
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-sm bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-5">
              <button
                onClick={resetCreateForm}
                className="px-4 py-2 text-sm text-[var(--text-secondary)] hover:text-text-primary)]"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                className="px-4 py-2 bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] text-sm font-medium"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Run Log Panel */}
      <RunLogPanel />
    </div>
  )
}

export default App
