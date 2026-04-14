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
