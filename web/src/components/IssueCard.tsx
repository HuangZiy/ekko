import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, AlertCircle, Clock, Tag, Play, Square, Bot, ClipboardList } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Issue } from '../stores/boardStore'
import { useBoardStore } from '../stores/boardStore'

const priorityColors: Record<string, string> = {
  urgent: 'border-l-red-500',
  high: 'border-l-orange-500',
  medium: 'border-l-blue-500',
  low: 'border-l-gray-400',
}

interface IssueCardProps {
  issue: Issue
  onClick: () => void
}

export function IssueCard({ issue, onClick }: IssueCardProps) {
  const { t } = useTranslation()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: issue.id,
  })
  const runSingleIssue = useBoardStore(s => s.runSingleIssue)
  const stopIssue = useBoardStore(s => s.stopIssue)
  const moveIssue = useBoardStore(s => s.moveIssue)
  const isRunning = useBoardStore(s => s.runningIssueIds.includes(issue.id)) || issue.status === 'in_progress'
  const hasOtherRunning = useBoardStore(s => Object.values(s.issues).some(i => i.status === 'in_progress' && i.id !== issue.id))

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  const canRun = !hasOtherRunning && (issue.status === 'todo' || issue.status === 'rejected' || issue.status === 'backlog' || issue.status === 'failed' || issue.status === 'planning')
  const canPlan = issue.status === 'backlog'

  const handleRun = (e: React.MouseEvent) => {
    e.stopPropagation()
    runSingleIssue(issue.id)
  }

  const handleStop = (e: React.MouseEvent) => {
    e.stopPropagation()
    stopIssue(issue.id)
  }

  const handlePlan = (e: React.MouseEvent) => {
    e.stopPropagation()
    moveIssue(issue.id, 'planning')
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      onClick={onClick}
      className={`bg-[var(--bg-card)] rounded-lg border border-[var(--border)] p-3 cursor-pointer hover:shadow-md transition-shadow border-l-4 ${priorityColors[issue.priority] || 'border-l-gray-300'}`}
    >
      <div className="flex items-start gap-2">
        <button {...attributes} {...listeners} className="mt-0.5 text-gray-400 hover:text-gray-600 cursor-grab">
          <GripVertical size={14} />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1">
            <span className="text-xs text-gray-400 mb-1">{issue.id}</span>
            {issue.source === 'agent' && (
              <Bot size={12} className="text-violet-500 mb-1" />
            )}
            {(isRunning || issue.status === 'in_progress') && (
              <button
                onClick={handleStop}
                className="ml-auto flex items-center gap-1 p-1 rounded hover:bg-red-50 text-red-500 hover:text-red-600 transition-colors"
                title={t('issueCard.stopTitle')}
              >
                <Square size={10} fill="currentColor" />
                <span className="text-xs">{t('issueCard.stop')}</span>
              </button>
            )}
            {!isRunning && issue.status !== 'in_progress' && (canPlan || canRun) && (
              <div className="ml-auto flex items-center gap-0.5">
                {canPlan && (
                  <button
                    onClick={handlePlan}
                    className="p-1 rounded hover:bg-violet-50 text-violet-600 hover:text-violet-700 transition-colors"
                    title={t('issueCard.planningTitle')}
                  >
                    <ClipboardList size={12} />
                  </button>
                )}
                {canRun && (
                  <button
                    onClick={handleRun}
                    className="p-1 rounded hover:bg-green-50 text-green-600 hover:text-green-700 transition-colors"
                    title={t('issueCard.runTitle')}
                  >
                    <Play size={12} />
                  </button>
                )}
              </div>
            )}
          </div>
          <div className="text-sm font-medium text-[var(--text-primary)] truncate">{issue.title}</div>
          {issue.labels.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {issue.labels.map(label => (
                <span key={label} className="inline-flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-700">
                  <Tag size={10} />
                  {label}
                </span>
              ))}
            </div>
          )}
          {issue.blocked_by.length > 0 && (
            <div className="flex items-center gap-1 mt-1.5 text-xs text-orange-600">
              <AlertCircle size={12} />
              {t('issueCard.blockedBy', { count: issue.blocked_by.length })}
            </div>
          )}
          {issue.assignee && (
            <div className="flex items-center gap-1 mt-1.5 text-xs text-gray-500">
              <Clock size={12} />
              {issue.assignee}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
