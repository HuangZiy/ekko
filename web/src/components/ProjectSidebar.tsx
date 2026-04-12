import { useState } from 'react'
import { FolderKanban, FolderOpen, Plus, Check, Trash2, ChevronDown, Info } from 'lucide-react'
import { useProjectStore } from '../stores/projectStore'
import type { ProjectInfo } from '../stores/projectStore'
import { DirectoryPicker } from './DirectoryPicker'
import { EkkoLogo } from './EkkoLogo'

interface ProjectSidebarProps {
  onProjectSwitch: (projectId: string) => void
  onProjectDetail: (project: ProjectInfo) => void
}

export function ProjectSidebar({ onProjectSwitch, onProjectDetail }: ProjectSidebarProps) {
  const projects = useProjectStore(s => s.projects)
  const activeProjectId = useProjectStore(s => s.activeProjectId)
  const switchProject = useProjectStore(s => s.switchProject)
  const createProject = useProjectStore(s => s.createProject)
  const deleteProject = useProjectStore(s => s.deleteProject)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newPath, setNewPath] = useState('')
  const [showPicker, setShowPicker] = useState(false)
  const [expanded, setExpanded] = useState(true)

  const handleCreate = async () => {
    if (!newName.trim() || !newPath.trim()) return
    await createProject(newName.trim(), newPath.trim())
    setNewName('')
    setNewPath('')
    setShowCreate(false)
  }

  const handleSwitch = async (id: string) => {
    await switchProject(id)
    onProjectSwitch(id)
  }

  return (
    <div className="w-64 border-r border-[var(--border)] bg-white flex flex-col h-full">
      {/* Logo — matches right header height */}
      <div className="flex items-center px-4 border-b border-[var(--border)]" style={{ height: 'var(--header-height)' }}>
        <EkkoLogo size={24} />
      </div>

      {/* Projects header */}
      <div
        className="flex items-center gap-2 px-4 py-2.5 cursor-pointer hover:bg-gray-50"
        onClick={() => setExpanded(!expanded)}
      >
        <FolderKanban size={14} className="text-[var(--text-secondary)]" />
        <span className="text-xs font-semibold flex-1 text-[var(--text-secondary)] uppercase tracking-wider">Projects</span>
        <ChevronDown size={14} className={`text-gray-400 transition-transform ${expanded ? '' : '-rotate-90'}`} />
      </div>

      {expanded && (
        <div className="flex-1 overflow-y-auto">
          {projects.map(project => (
            <ProjectItem
              key={project.id}
              project={project}
              isActive={project.id === activeProjectId}
              onSwitch={() => handleSwitch(project.id)}
              onDelete={() => deleteProject(project.id)}
              onDetail={() => onProjectDetail(project)}
            />
          ))}

          {projects.length === 0 && (
            <div className="px-4 py-6 text-xs text-gray-400 text-center">
              No projects yet
            </div>
          )}
        </div>
      )}

      <div className="border-t border-[var(--border)] p-2">
        {showCreate ? (
          <div className="space-y-2 p-2">
            <input
              autoFocus
              value={newName}
              onChange={e => setNewName(e.target.value)}
              placeholder="Project name"
              className="w-full px-2 py-1.5 text-xs border border-[var(--border)] rounded focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
            />
            <div className="flex gap-1">
              <input
                value={newPath}
                onChange={e => setNewPath(e.target.value)}
                placeholder="Workspace path"
                className="flex-1 min-w-0 px-2 py-1.5 text-xs border border-[var(--border)] rounded focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
              />
              <button
                onClick={() => setShowPicker(true)}
                className="px-2 py-1.5 border border-[var(--border)] rounded hover:bg-blue-50 text-gray-500 hover:text-[var(--accent)]"
                title="Browse directories"
              >
                <FolderOpen size={14} />
              </button>
            </div>
            <div className="flex gap-1">
              <button
                onClick={handleCreate}
                className="flex-1 px-2 py-1 text-xs bg-[var(--accent)] text-white rounded hover:bg-[var(--accent-hover)]"
              >
                Create
              </button>
              <button
                onClick={() => setShowCreate(false)}
                className="px-2 py-1 text-xs text-gray-500 hover:text-gray-700"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowCreate(true)}
            className="w-full flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 hover:text-[var(--accent)] hover:bg-blue-50 rounded"
          >
            <Plus size={14} /> New Project
          </button>
        )}
      </div>
      <DirectoryPicker
        open={showPicker}
        onSelect={(path) => { setNewPath(path); setShowPicker(false) }}
        onClose={() => setShowPicker(false)}
      />
    </div>
  )
}

function ProjectItem({
  project,
  isActive,
  onSwitch,
  onDelete,
  onDetail,
}: {
  project: ProjectInfo
  isActive: boolean
  onSwitch: () => void
  onDelete: () => void
  onDetail: () => void
}) {
  const [showActions, setShowActions] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const total = project.total_issues || 0
  const done = project.issue_counts?.human_done || 0

  return (
    <div
      className={`group flex items-center gap-2 px-4 py-2.5 cursor-pointer border-l-2 transition-colors ${
        isActive
          ? 'border-l-[var(--accent)] bg-blue-50'
          : 'border-l-transparent hover:bg-gray-50'
      }`}
      onClick={onSwitch}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          {isActive && <Check size={12} className="text-[var(--accent)] shrink-0" />}
          <span className={`text-sm truncate ${isActive ? 'font-medium text-[var(--accent)]' : 'text-[var(--text-primary)]'}`}>
            {project.name}
          </span>
        </div>
        {total > 0 && (
          <div className="text-xs text-gray-400 mt-0.5 ml-5">
            {done}/{total} done
          </div>
        )}
      </div>
      {showActions && (
        <div className="flex gap-0.5 shrink-0">
          <button
            onClick={e => { e.stopPropagation(); onDetail() }}
            className="text-gray-300 hover:text-[var(--accent)] shrink-0"
            title="Project details"
          >
            <Info size={14} />
          </button>
          {!isActive && (
            <button
              onClick={e => { e.stopPropagation(); setShowDeleteConfirm(true) }}
              className="text-gray-300 hover:text-red-500 shrink-0"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      )}
      {showDeleteConfirm && (
        <div className="flex items-center gap-1 shrink-0" onClick={e => e.stopPropagation()}>
          <span className="text-xs text-red-500">Delete?</span>
          <button
            onClick={() => { onDelete(); setShowDeleteConfirm(false) }}
            className="text-xs px-1.5 py-0.5 bg-red-500 text-white rounded hover:bg-red-600"
          >
            Yes
          </button>
          <button
            onClick={() => setShowDeleteConfirm(false)}
            className="text-xs px-1.5 py-0.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            No
          </button>
        </div>
      )}
    </div>
  )
}
