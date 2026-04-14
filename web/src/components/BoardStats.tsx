import { useTranslation } from 'react-i18next'
import { useBoardStore } from '../stores/boardStore'

const statusColors: Record<string, string> = {
  backlog: 'bg-slate-400',
  todo: 'bg-blue-500',
  in_progress: 'bg-amber-500',
  agent_done: 'bg-violet-500',
  rejected: 'bg-red-500',
  human_done: 'bg-green-500',
}

export function BoardStats() {
  const { t } = useTranslation()
  const issues = useBoardStore(s => s.issues)
  const columns = useBoardStore(s => s.columns)

  const allIssues = Object.values(issues)
  const total = allIssues.length

  if (total === 0) return null

  const statusCounts: Record<string, number> = {}
  for (const col of columns) {
    statusCounts[col.id] = col.issues.length
  }

  const doneCount = statusCounts['human_done'] || 0
  const progressPercent = total > 0 ? Math.round((doneCount / total) * 100) : 0

  const totalCost = allIssues.reduce((sum, issue) => sum + (issue.cost || 0), 0)

  return (
    <div className="px-6 py-3 border-b border-[var(--border)] bg-[var(--bg-card)]">
      <div className="flex items-center gap-4 flex-wrap">
        <span className="text-sm font-medium text-[var(--text-primary)]">
          {t('boardStats.issueCount', { count: total })}
        </span>

        <div className="flex items-center gap-2 flex-wrap">
          {columns.map(col => {
            const count = statusCounts[col.id] || 0
            if (count === 0) return null
            return (
              <span
                key={col.id}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium text-white ${statusColors[col.id] || 'bg-gray-400'}`}
              >
                {t(`status.${col.id}`, col.name)}: {count}
              </span>
            )
          })}
        </div>

        <div className="flex items-center gap-2 ml-auto">
          {totalCost > 0 && (
            <span className="text-xs text-[var(--text-secondary)]">
              {t('boardStats.cost', { amount: totalCost.toFixed(2) })}
            </span>
          )}
          <div className="flex items-center gap-2">
            <div className="w-32 h-2 bg-[var(--bg-secondary)] rounded-full overflow-hidden">
              <div
                className="h-full bg-green-500 rounded-full transition-all duration-500"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <span className="text-xs text-[var(--text-secondary)] whitespace-nowrap">
              {t('boardStats.progress', { done: doneCount, total, pct: progressPercent })}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
