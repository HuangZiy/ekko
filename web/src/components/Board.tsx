import { useState, useCallback } from 'react'
import { DndContext, closestCorners, PointerSensor, useSensor, useSensors, DragOverlay } from '@dnd-kit/core'
import type { DragEndEvent, DragStartEvent } from '@dnd-kit/core'
import type { Issue } from '../stores/boardStore'
import { useBoardStore } from '../stores/boardStore'
import { Column } from './Column'
import { IssueCard } from './IssueCard'

interface BoardProps {
  onIssueClick: (issue: Issue) => void
}

export function Board({ onIssueClick }: BoardProps) {
  const columns = useBoardStore(s => s.columns)
  const issues = useBoardStore(s => s.issues)
  const moveIssue = useBoardStore(s => s.moveIssue)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  )

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveId(event.active.id as string)
  }, [])

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    setActiveId(null)
    const { active, over } = event
    if (!over) return

    const issueId = active.id as string
    const targetColumnId = over.id as string

    const isColumn = columns.some(c => c.id === targetColumnId)
    if (isColumn) {
      const result = await moveIssue(issueId, targetColumnId)
      if (result && !result.ok) {
        setToast(result.error || 'Move failed')
        setTimeout(() => setToast(null), 3000)
      }
    }
  }, [columns, moveIssue])

  const activeIssue = activeId ? issues[activeId] : null

  return (
    <>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <div className="flex gap-4 overflow-x-auto p-4 h-full">
          {columns.map(column => {
            const columnIssues = column.issues
              .map(id => issues[id])
              .filter(Boolean)

            return (
              <Column
                key={column.id}
                column={column}
                issues={columnIssues}
                onIssueClick={onIssueClick}
              />
            )
          })}
        </div>

        <DragOverlay>
          {activeIssue ? (
            <div className="rotate-3 opacity-90">
              <IssueCard issue={activeIssue} onClick={() => {}} />
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>

      {toast && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50 px-4 py-2 bg-red-600 text-white text-sm rounded-lg shadow-lg animate-fade-in">
          {toast}
        </div>
      )}
    </>
  )
}
