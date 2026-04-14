import { useState, useEffect, Component, lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import type { Issue } from './stores/boardStore'
import type { ReactNode } from 'react'
import { useBoardStore } from './stores/boardStore'
import { useProjectStore } from './stores/projectStore'
import type { ProjectInfo } from './stores/projectStore'
import { useWebSocket } from './hooks/useWebSocket'
import { useTheme } from './hooks/useTheme'
import { useLanguage } from './hooks/useLanguage'
import { Board } from './components/Board'
import { BoardStats } from './components/BoardStats'
import { ProjectSidebar } from './components/ProjectSidebar'
import { LayoutDashboard, Plus, Play, Sun, Moon, Languages } from 'lucide-react'
import { AnimatePresence } from 'framer-motion'
import i18n from './i18n'
import './index.css'

// Lazy-loaded components for code-splitting
const IssueDetail = lazy(() => import('./components/IssueDetail'))
const ProjectDetail = lazy(() => import('./components/ProjectDetail'))
const MarkdownEditor = lazy(() => import('./components/MarkdownEditor'))
const RunLogPanel = lazy(() => import('./components/RunLogPanel'))

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 32, color: 'red', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
          <h2>{i18n.t('error.uiError')}</h2>
          <p>{this.state.error.message}</p>
          <pre>{this.state.error.stack}</pre>
          <button onClick={() => this.setState({ error: null })} style={{ marginTop: 16, padding: '8px 16px' }}>
            {i18n.t('error.dismiss')}
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function App() {
  const { t } = useTranslation()
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null)
  const [selectedProject, setSelectedProject] = useState<ProjectInfo | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newPriority, setNewPriority] = useState('medium')
  const [newLabels, setNewLabels] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [newBlockedBy, setNewBlockedBy] = useState('')

  const { theme, toggleTheme } = useTheme()
  const { language, toggleLanguage } = useLanguage()

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

  useWebSocket()

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
              onClick={toggleLanguage}
              className="p-2 rounded-lg hover:bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors flex items-center gap-1"
              title={language === 'en' ? t('header.switchToZh') : t('header.switchToEn')}
            >
              <Languages size={18} />
              <span className="text-xs font-medium">{language === 'en' ? 'EN' : '中'}</span>
            </button>
            <button
              onClick={toggleTheme}
              className="p-2 rounded-lg hover:bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              title={theme === 'light' ? t('header.switchToDark') : t('header.switchToLight')}
            >
              {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            {projectId && (
              <button
                onClick={() => runAllIssues()}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium"
                title={t('header.runAllTitle')}
              >
                <Play size={16} /> {t('header.runAll')}
              </button>
            )}
            <button
              onClick={() => setShowCreateForm(true)}
              disabled={!projectId}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Plus size={16} /> {t('header.newIssue')}
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
              {t('board.selectProject')}
            </div>
          )}
        </main>
      </div>

      {/* Issue Detail Slide-over */}
      <AnimatePresence>
        {selectedIssue && (
          <Suspense fallback={null}>
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
          </Suspense>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {selectedProject && (
          <Suspense fallback={null}>
            <ProjectDetail
              project={selectedProject}
              onClose={() => setSelectedProject(null)}
            />
          </Suspense>
        )}
      </AnimatePresence>

      {/* Create Issue Modal */}
      {showCreateForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/30" onClick={resetCreateForm} />
          <div className="relative bg-[var(--bg-card)] rounded-xl shadow-xl p-6 w-full max-w-lg">
            <h2 className="text-lg font-semibold mb-4 text-[var(--text-primary)]">{t('issue.create.title')}</h2>

            <div className="space-y-3">
              {/* Title */}
              <div>
                <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">{t('issue.create.titleLabel')}</label>
                <input
                  autoFocus
                  value={newTitle}
                  onChange={e => setNewTitle(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleCreate()}
                  placeholder={t('issue.create.titlePlaceholder')}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-sm bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                />
              </div>

              {/* Priority */}
              <div>
                <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">{t('issue.create.priorityLabel')}</label>
                <select
                  value={newPriority}
                  onChange={e => setNewPriority(e.target.value)}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-sm bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                >
                  <option value="low">{t('issue.create.priority.low')}</option>
                  <option value="medium">{t('issue.create.priority.medium')}</option>
                  <option value="high">{t('issue.create.priority.high')}</option>
                  <option value="urgent">{t('issue.create.priority.urgent')}</option>
                </select>
              </div>

              {/* Labels */}
              <div>
                <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">{t('issue.create.labelsLabel')}</label>
                <input
                  value={newLabels}
                  onChange={e => setNewLabels(e.target.value)}
                  placeholder={t('issue.create.labelsPlaceholder')}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-sm bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                />
              </div>

              {/* Description */}
              <div>
                <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">{t('issue.create.descriptionLabel')}</label>
                <Suspense fallback={null}>
                  <MarkdownEditor
                    value={newDescription}
                    onChange={setNewDescription}
                    placeholder={t('issue.create.descriptionPlaceholder')}
                    rows={6}
                    uploadUrl={projectId ? `/api/projects/${projectId}/uploads` : null}
                  />
                </Suspense>
              </div>

              {/* Blocked By */}
              <div>
                <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">{t('issue.create.blockedByLabel')}</label>
                <input
                  value={newBlockedBy}
                  onChange={e => setNewBlockedBy(e.target.value)}
                  placeholder={t('issue.create.blockedByPlaceholder')}
                  className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-sm bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-5">
              <button
                onClick={resetCreateForm}
                className="px-4 py-2 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                {t('issue.create.cancel')}
              </button>
              <button
                onClick={handleCreate}
                className="px-4 py-2 bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] text-sm font-medium"
              >
                {t('issue.create.submit')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Run Log Panel */}
      <Suspense fallback={null}>
        <RunLogPanel />
      </Suspense>
    </div>
  )
}

export default App
