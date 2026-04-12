import { useState, useEffect, useCallback } from 'react'
import { Folder, ArrowLeft, FolderOpen } from 'lucide-react'

interface DirectoryPickerProps {
  open: boolean
  onSelect: (path: string) => void
  onClose: () => void
}

interface BrowseResponse {
  current: string
  parent: string | null
  entries: { name: string; type: string }[]
}

export function DirectoryPicker({ open, onSelect, onClose }: DirectoryPickerProps) {
  const [data, setData] = useState<BrowseResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const browse = useCallback(async (path?: string) => {
    setLoading(true)
    setError(null)
    try {
      const url = path ? `/api/fs/browse?path=${encodeURIComponent(path)}` : '/api/fs/browse'
      const res = await fetch(url)
      if (!res.ok) {
        const err = await res.json()
        setError(err.detail || 'Failed to browse directory')
        return
      }
      setData(await res.json())
    } catch {
      setError('Failed to connect to server')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) browse()
  }, [open, browse])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative bg-[var(--bg-card)] rounded-xl shadow-xl w-full max-w-lg flex flex-col" style={{ maxHeight: '70vh' }}>
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border)]">
          <FolderOpen size={16} className="text-[var(--accent)] shrink-0" />
          <span className="text-sm font-semibold">Select Directory</span>
        </div>

        {/* Current path + back */}
        {data && (
          <div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--border)] bg-gray-50">
            {data.parent && (
              <button
                onClick={() => browse(data.parent!)}
                className="p-1 rounded hover:bg-gray-200 text-gray-500 shrink-0"
              >
                <ArrowLeft size={14} />
              </button>
            )}
            <span className="text-xs text-gray-600 truncate font-mono">{data.current}</span>
          </div>
        )}

        {/* Directory list */}
        <div className="flex-1 overflow-y-auto px-2 py-1">
          {loading && (
            <div className="text-xs text-gray-400 text-center py-8">Loading...</div>
          )}
          {error && (
            <div className="text-xs text-red-500 text-center py-8">{error}</div>
          )}
          {data && !loading && data.entries.length === 0 && (
            <div className="text-xs text-gray-400 text-center py-8">No subdirectories</div>
          )}
          {data && !loading && data.entries.map(entry => (
            <button
              key={entry.name}
              onClick={() => browse(`${data.current}/${entry.name}`)}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left rounded hover:bg-blue-50 transition-colors"
            >
              <Folder size={14} className="text-[var(--accent)] shrink-0" />
              <span className="truncate">{entry.name}</span>
            </button>
          ))}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-[var(--border)]">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700 rounded"
          >
            Cancel
          </button>
          <button
            onClick={() => data && onSelect(data.current)}
            disabled={!data}
            className="px-3 py-1.5 text-xs bg-[var(--accent)] text-white rounded hover:bg-[var(--accent-hover)] disabled:opacity-50"
          >
            Select this directory
          </button>
        </div>
      </div>
    </div>
  )
}
