import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Pencil, Save, X, FolderOpen, Hash, Calendar, Tag, BarChart3, FlaskConical } from 'lucide-react'
import type { ProjectInfo } from '../stores/projectStore'
import { useProjectStore } from '../stores/projectStore'
import { useBoardStore } from '../stores/boardStore'

interface ProjectDetailProps {
  project: ProjectInfo
  onClose: () => void
}

const statusColors: Record<string, string> = {
  backlog: 'bg-slate-400',
  todo: 'bg-blue-500',
  in_progress: 'bg-amber-500',
  agent_done: 'bg-violet-500',
  rejected: 'bg-red-500',
  human_done: 'bg-green-500',
}

const statusLabels: Record<string, string> = {
  backlog: 'Backlog',
  todo: 'Todo',
  in_progress: 'In Progress',
  agent_done: 'Agent Done',
  rejected: 'Rejected',
  human_done: 'Human Done',
}

export function ProjectDetail({ project, onClose }: ProjectDetailProps) {
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState(project.name)
  const [editWorkspace, setEditWorkspace] = useState(project.workspaces?.[0] || '')
  const [editKey, setEditKey] = useState(project.key || 'ISS')
  const [saving, setSaving] = useState(false)
  const [projectStats, setProjectStats] = useState<{ total_runs: number; total_cost_usd: number; total_duration_ms: number } | null>(null)

  const updateProject = useProjectStore(s => s.updateProject)
  const issues = useBoardStore(s => s.issues)

  useEffect(() => {
    setEditName(project.name)
    setEditWorkspace(project.workspaces?.[0] || '')
    setEditKey(project.key || 'ISS')
    fetch(`/api/projects/${project.id}`)
      .then(r => r.json())
      .then(data => {
        if (data.run_stats) setProjectStats(data.run_stats)
      })
  }, [project])

  // Compute issue stats from boardStore for live data
  const issueStats: Record<string, number> = {}
  let totalIssues = 0
  for (const issue of Object.values(issues)) {
    issueStats[issue.status] = (issueStats[issue.status] || 0) + 1
    totalIssues++
  }
  // Fallback to project-level counts if board has no issues loaded
  const stats = totalIssues > 0 ? issueStats : (project.issue_counts || {})
  const total = totalIssues > 0 ? totalIssues : (project.total_issues || 0)

  const handleSave = async () => {
    setSaving(true)
    const patch: { name?: string; workspace_path?: string; key?: string } = {}
    if (editName !== project.name) patch.name = editName
    if (editWorkspace !== (project.workspaces?.[0] || '')) patch.workspace_path = editWorkspace
    const normalizedKey = editKey.trim().toUpperCase()
    if (normalizedKey && normalizedKey !== (project.key || 'ISS')) patch.key = normalizedKey
    if (Object.keys(patch).length > 0) {
      await updateProject(project.id, patch)
    }
    setEditing(false)
    setSaving(false)
  }

  const handleCancel = () => {
    setEditing(false)
    setEditName(project.name)
    setEditWorkspace(project.workspaces?.[0] || '')
    setEditKey(project.key || 'ISS')
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <motion.div
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        className="relative ml-auto w-full max-w-lg bg-[var(--bg-card)] h-full overflow-y-auto shadow-xl"
      >
        {/* Header */}
        <div className="sticky top-0 bg-[var(--bg-card)] border-b border-[var(--border)] px-6 py-4 flex items-center gap-3 z-10">
          <span className="text-xs text-gray-400 font-mono">{project.id}</span>
          {editing ? (
            <input
              value={editName}
              onChange={e => setEditName(e.target.value)}
              className="text-lg font-semibold flex-1 px-2 py-1 border border-[var(--border)] rounded-lg bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
            />
          ) : (
            <h2 className="text-lg font-semibold flex-1 truncate text-[var(--text-primary)]">{project.name}</h2>
          )}
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="p-1.5 rounded-lg hover:bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              title="Edit project"
            >
              <Pencil size={16} />
            </button>
          )}
          {editing && (
            <div className="flex gap-1">
              <button
                onClick={handleSave}
                disabled={saving}
                className="p-1.5 rounded-lg hover:bg-green-50 text-green-600 hover:text-green-700 transition-colors disabled:opacity-50"
                title="Save changes"
              >
                <Save size={16} />
              </button>
              <button
                onClick={handleCancel}
                className="p-1.5 rounded-lg hover:bg-red-50 text-red-500 hover:text-red-600 transition-colors"
                title="Cancel"
              >
                <X size={16} />
              </button>
            </div>
          )}
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
        </div>

        <div className="px-6 py-4 space-y-6">
          {/* Basic Info */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm">
              <Hash size={14} className="text-[var(--text-secondary)]" />
              <span className="text-[var(--text-secondary)]">ID:</span>
              <span className="font-mono text-[var(--text-primary)]">{project.id}</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <Calendar size={14} className="text-[var(--text-secondary)]" />
              <span className="text-[var(--text-secondary)]">Created:</span>
              <span className="text-[var(--text-primary)]">
                {project.created_at ? new Date(project.created_at).toLocaleString() : '-'}
              </span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <Tag size={14} className="text-[var(--text-secondary)]" />
              <span className="text-[var(--text-secondary)]">Issue Key:</span>
              {editing ? (
                <input
                  value={editKey}
                  onChange={e => setEditKey(e.target.value.toUpperCase())}
                  className="w-20 px-2 py-0.5 border border-[var(--border)] rounded-md font-mono text-sm bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                  placeholder="ISS"
                  maxLength={10}
                />
              ) : (
                <span className="font-mono text-[var(--text-primary)]">{project.key || 'ISS'}</span>
              )}
            </div>
          </div>

          {/* Workspace */}
          <div>
            <div className="flex items-center gap-1.5 text-sm font-semibold text-[var(--text-primary)] mb-2">
              <FolderOpen size={14} /> Workspace
            </div>
            {editing ? (
              <input
                value={editWorkspace}
                onChange={e => setEditWorkspace(e.target.value)}
                className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-sm font-mono bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                placeholder="/path/to/workspace"
              />
            ) : (
              <div className="px-3 py-2 bg-[var(--bg-secondary)] rounded-lg text-sm font-mono text-[var(--text-primary)] break-all">
                {project.workspaces?.[0] || '-'}
              </div>
            )}
          </div>

          {/* Issue Stats */}
          <div>
            <div className="flex items-center gap-1.5 text-sm font-semibold text-[var(--text-primary)] mb-3">
              <BarChart3 size={14} /> Issue Statistics
              {total > 0 && (
                <span className="ml-auto text-xs font-normal text-[var(--text-secondary)]">{total} total</span>
              )}
            </div>
            {total > 0 ? (
              <div className="space-y-2">
                {/* Progress bar */}
                <div className="flex h-2 rounded-full overflow-hidden bg-[var(--bg-secondary)]">
                  {Object.entries(statusColors).map(([status, color]) => {
                    const count = stats[status] || 0
                    if (count === 0) return null
                    const pct = (count / total) * 100
                    return (
                      <div
                        key={status}
                        className={`${color} transition-all`}
                        style={{ width: `${pct}%` }}
                        title={`${statusLabels[status]}: ${count}`}
                      />
                    )
                  })}
                </div>
                {/* Legend */}
                <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                  {Object.entries(statusColors).map(([status, color]) => {
                    const count = stats[status] || 0
                    if (count === 0) return null
                    return (
                      <div key={status} className="flex items-center gap-1.5 text-xs">
                        <span className={`w-2.5 h-2.5 rounded-full ${color}`} />
                        <span className="text-[var(--text-secondary)]">{statusLabels[status]}</span>
                        <span className="font-medium text-[var(--text-primary)]">{count}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : (
              <div className="text-sm text-[var(--text-secondary)] py-2">No issues yet</div>
            )}
          </div>

          {/* Agent Run Stats */}
          {projectStats && projectStats.total_runs > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-sm font-semibold text-[var(--text-primary)] mb-2">
                <FlaskConical size={14} /> Agent Runs
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div className="px-3 py-2 bg-[var(--bg-secondary)] rounded-lg text-center">
                  <div className="text-lg font-semibold text-[var(--text-primary)]">{projectStats.total_runs}</div>
                  <div className="text-xs text-[var(--text-secondary)]">Runs</div>
                </div>
                <div className="px-3 py-2 bg-[var(--bg-secondary)] rounded-lg text-center">
                  <div className="text-lg font-semibold text-[var(--text-primary)]">${projectStats.total_cost_usd.toFixed(2)}</div>
                  <div className="text-xs text-[var(--text-secondary)]">Cost</div>
                </div>
                <div className="px-3 py-2 bg-[var(--bg-secondary)] rounded-lg text-center">
                  <div className="text-lg font-semibold text-[var(--text-primary)]">{Math.round(projectStats.total_duration_ms / 1000)}s</div>
                  <div className="text-xs text-[var(--text-secondary)]">Duration</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  )
}
