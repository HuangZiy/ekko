export const VALID_TRANSITIONS: Record<string, string[]> = {
  backlog: ['planning', 'todo'],
  planning: ['todo', 'backlog'],
  todo: ['in_progress', 'backlog'],
  in_progress: ['agent_done', 'failed', 'todo'],
  agent_done: ['human_done', 'rejected'],
  failed: ['in_progress', 'todo'],
  rejected: ['todo'],
  human_done: [],
}

export const STATUS_LABELS: Record<string, string> = {
  backlog: 'Backlog',
  planning: 'Planning',
  todo: 'Todo',
  in_progress: 'In Progress',
  agent_done: 'Agent Done',
  failed: 'Failed',
  rejected: 'Rejected',
  human_done: 'Human Done',
}
