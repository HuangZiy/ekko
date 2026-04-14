import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { useTranslation } from 'react-i18next'
import type { BoardColumn as BoardColumnType, Issue } from '../stores/boardStore'
import { IssueCard } from './IssueCard'

const columnColors: Record<string, string> = {
  backlog: 'bg-slate-400',
  todo: 'bg-blue-500',
  in_progress: 'bg-amber-500',
  agent_done: 'bg-violet-500',
  rejected: 'bg-red-500',
  human_done: 'bg-green-500',
}

interface ColumnProps {
  column: BoardColumnType
  issues: Issue[]
  onIssueClick: (issue: Issue) => void
}

export function Column({ column, issues, onIssueClick }: ColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: column.id })
  const { t } = useTranslation()

  return (
    <div className="flex flex-col w-72 min-w-[288px] shrink-0">
      <div className="flex items-center gap-2 px-3 py-2 mb-2">
        <div className={`w-2.5 h-2.5 rounded-full ${columnColors[column.id] || 'bg-gray-400'}`} />
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{column.name}</h3>
        <span className="text-xs text-gray-400 ml-auto">{issues.length}</span>
      </div>

      <div
        ref={setNodeRef}
        className={`flex-1 flex flex-col gap-2 p-2 rounded-lg min-h-[200px] transition-colors ${
          isOver ? 'bg-blue-50 border-2 border-dashed border-blue-300' : 'bg-[var(--bg-secondary)]'
        }`}
      >
        <SortableContext items={issues.map(i => i.id)} strategy={verticalListSortingStrategy}>
          {issues.map(issue => (
            <IssueCard key={issue.id} issue={issue} onClick={() => onIssueClick(issue)} />
          ))}
        </SortableContext>

        {issues.length === 0 && (
          <div className="flex-1 flex items-center justify-center text-xs text-gray-400">
            {t('column.dropHere')}
          </div>
        )}
      </div>
    </div>
  )
}
