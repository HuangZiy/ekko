import { create } from 'zustand'

export interface ProjectInfo {
  id: string
  name: string
  workspaces: string[]
  created_at: string
  _active?: boolean
  issue_counts?: Record<string, number>
  total_issues?: number
}

interface ProjectState {
  projects: ProjectInfo[]
  activeProjectId: string | null
  loading: boolean
  fetchProjects: () => Promise<void>
  createProject: (name: string, workspacePath: string) => Promise<void>
  switchProject: (projectId: string) => Promise<void>
  deleteProject: (projectId: string) => Promise<void>
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  activeProjectId: null,
  loading: false,

  fetchProjects: async () => {
    set({ loading: true })
    const res = await fetch('/api/projects')
    const projects: ProjectInfo[] = await res.json()
    const active = projects.find(p => p._active)
    set({
      projects,
      activeProjectId: active?.id || (projects[0]?.id ?? null),
      loading: false,
    })
  },

  createProject: async (name, workspacePath) => {
    await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, workspace_path: workspacePath }),
    })
    await get().fetchProjects()
  },

  switchProject: async (projectId) => {
    await fetch('/api/projects/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId }),
    })
    set({ activeProjectId: projectId })
    await get().fetchProjects()
  },

  deleteProject: async (projectId) => {
    await fetch(`/api/projects/${projectId}`, { method: 'DELETE' })
    await get().fetchProjects()
  },
}))
