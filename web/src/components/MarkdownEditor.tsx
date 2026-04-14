import { useState, useRef, useCallback, type DragEvent, type ClipboardEvent, type ChangeEvent } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Bold, Italic, Heading1, Heading2, Heading3, Code, Link, List, ListOrdered,
  Quote, ImageIcon, Eye, Pencil, Upload, Loader2
} from 'lucide-react'

interface MarkdownEditorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  rows?: number
  /** project + issue context for image uploads */
  projectId?: string | null
  issueId?: string | null
  /** custom upload URL — overrides the default projectId/issueId-based URL */
  uploadUrl?: string | null
  className?: string
  /** auto-focus the textarea */
  autoFocus?: boolean
}

type ToolbarAction = {
  icon: typeof Bold
  labelKey: string
  action: (text: string, selStart: number, selEnd: number) => { text: string; cursor: number }
}

const toolbarActions: ToolbarAction[] = [
  {
    icon: Bold,
    labelKey: 'markdownEditor.bold',
    action: (text, s, e) => {
      const selected = text.slice(s, e)
      const replacement = `**${selected || 'bold text'}**`
      return { text: text.slice(0, s) + replacement + text.slice(e), cursor: selected ? s + replacement.length : s + 2 }
    },
  },
  {
    icon: Italic,
    labelKey: 'markdownEditor.italic',
    action: (text, s, e) => {
      const selected = text.slice(s, e)
      const replacement = `*${selected || 'italic text'}*`
      return { text: text.slice(0, s) + replacement + text.slice(e), cursor: selected ? s + replacement.length : s + 1 }
    },
  },
  {
    icon: Heading1,
    labelKey: 'markdownEditor.heading1',
    action: (text, s, e) => {
      const lineStart = text.lastIndexOf('\n', s - 1) + 1
      const selected = text.slice(s, e) || 'Heading'
      const before = text.slice(0, lineStart)
      const after = text.slice(e)
      const replacement = `# ${selected}`
      return { text: before + replacement + after, cursor: before.length + replacement.length }
    },
  },
  {
    icon: Heading2,
    labelKey: 'markdownEditor.heading2',
    action: (text, s, e) => {
      const lineStart = text.lastIndexOf('\n', s - 1) + 1
      const selected = text.slice(s, e) || 'Heading'
      const before = text.slice(0, lineStart)
      const after = text.slice(e)
      const replacement = `## ${selected}`
      return { text: before + replacement + after, cursor: before.length + replacement.length }
    },
  },
  {
    icon: Heading3,
    labelKey: 'markdownEditor.heading3',
    action: (text, s, e) => {
      const lineStart = text.lastIndexOf('\n', s - 1) + 1
      const selected = text.slice(s, e) || 'Heading'
      const before = text.slice(0, lineStart)
      const after = text.slice(e)
      const replacement = `### ${selected}`
      return { text: before + replacement + after, cursor: before.length + replacement.length }
    },
  },
  {
    icon: Code,
    labelKey: 'markdownEditor.code',
    action: (text, s, e) => {
      const selected = text.slice(s, e)
      if (selected.includes('\n')) {
        const replacement = `\`\`\`\n${selected}\n\`\`\``
        return { text: text.slice(0, s) + replacement + text.slice(e), cursor: s + replacement.length }
      }
      const replacement = `\`${selected || 'code'}\``
      return { text: text.slice(0, s) + replacement + text.slice(e), cursor: selected ? s + replacement.length : s + 1 }
    },
  },
  {
    icon: Link,
    labelKey: 'markdownEditor.link',
    action: (text, s, e) => {
      const selected = text.slice(s, e) || 'link text'
      const replacement = `[${selected}](url)`
      return { text: text.slice(0, s) + replacement + text.slice(e), cursor: s + selected.length + 3 }
    },
  },
  {
    icon: List,
    labelKey: 'markdownEditor.bulletList',
    action: (text, s, e) => {
      const selected = text.slice(s, e)
      if (selected) {
        const lines = selected.split('\n').map(l => `- ${l}`).join('\n')
        return { text: text.slice(0, s) + lines + text.slice(e), cursor: s + lines.length }
      }
      const replacement = '- '
      return { text: text.slice(0, s) + replacement + text.slice(e), cursor: s + 2 }
    },
  },
  {
    icon: ListOrdered,
    labelKey: 'markdownEditor.numberedList',
    action: (text, s, e) => {
      const selected = text.slice(s, e)
      if (selected) {
        const lines = selected.split('\n').map((l, i) => `${i + 1}. ${l}`).join('\n')
        return { text: text.slice(0, s) + lines + text.slice(e), cursor: s + lines.length }
      }
      const replacement = '1. '
      return { text: text.slice(0, s) + replacement + text.slice(e), cursor: s + 3 }
    },
  },
  {
    icon: Quote,
    labelKey: 'markdownEditor.quote',
    action: (text, s, e) => {
      const selected = text.slice(s, e)
      if (selected) {
        const lines = selected.split('\n').map(l => `> ${l}`).join('\n')
        return { text: text.slice(0, s) + lines + text.slice(e), cursor: s + lines.length }
      }
      const replacement = '> '
      return { text: text.slice(0, s) + replacement + text.slice(e), cursor: s + 2 }
    },
  },
]

const previewComponents: Components = {
  img: ({ src, alt, ...props }) => (
    <img
      src={src}
      alt={alt || ''}
      loading="lazy"
      style={{ maxWidth: '100%', height: 'auto', borderRadius: '0.5rem', cursor: 'pointer' }}
      onClick={() => src && window.open(src, '_blank')}
      {...props}
    />
  ),
  a: ({ href, children, ...props }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
      {children}
    </a>
  ),
  pre: ({ children, ...props }) => (
    <pre style={{ overflow: 'auto', maxHeight: '400px' }} {...props}>
      {children}
    </pre>
  ),
}

export function MarkdownEditor({
  value,
  onChange,
  placeholder: placeholderProp,
  rows = 8,
  projectId,
  issueId,
  uploadUrl: uploadUrlProp,
  className = '',
  autoFocus = false,
}: MarkdownEditorProps) {
  const { t } = useTranslation()
  const placeholder = placeholderProp ?? t('markdownEditor.placeholder')
  const [mode, setMode] = useState<'write' | 'preview'>('write')
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Resolve the upload URL: explicit prop takes priority, then projeueId combo
  const resolvedUploadUrl = uploadUrlProp
    || (projectId && issueId ? `/api/projects/${projectId}/issues/${issueId}/uploads` : null)
  const canUpload = !!resolvedUploadUrl

  const insertTextAtCursor = useCallback((insertion: string) => {
    const ta = textareaRef.current
    if (!ta) {
      onChange(value + insertion)
      return
    }
    const start = ta.selectionStart
    const end = ta.selectionEnd
    const newText = value.slice(0, start) + insertion + value.slice(end)
    onChange(newText)
    requestAnimationFrame(() => {
      ta.selectionStart = ta.selectionEnd = start + insertion.length
      ta.focus()
    })
  }, [value, onChange])

  const uploadImage = useCallback(async (file: File) => {
    if (!resolvedUploadUrl) return
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch(resolvedUploadUrl, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        console.error('Upload failed:', err)
        return
      }
      const data = await res.json()
      const isVideo = file.type.startsWith('video/')
      const mdMarkup = isVideo
        ? `[🎬 ${file.name}](${data.url})\n`
        : `![${file.name}](${data.url})\n`
      insertTextAtCursor(mdMarkup)
    } catch (err) {
      console.error('Upload error:', err)
    } finally {
      setUploading(false)
    }
  }, [resolvedUploadUrl, insertTextAtCursor])

  const handlePaste = useCallback((e: ClipboardEvent<HTMLTextAreaElement>) => {
    if (!canUpload) return
    const items = e.clipboardData?.items
    if (!items) return
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/') || item.type.startsWith('video/')) {
        e.preventDefault()
        const file = item.getAsFile()
        if (file) uploadImage(file)
        return
      }
    }
  }, [canUpload, uploadImage])

  const handleDrop = useCallback((e: DragEvent<HTMLTextAreaElement>) => {
    e.preventDefault()
    setDragOver(false)
    if (!canUpload) return
    const files = e.dataTransfer?.files
    if (!files) return
    for (const file of Array.from(files)) {
      if (file.type.startsWith('image/') || file.type.startsWith('video/')) {
        uploadImage(file)
        return
      }
    }
  }, [canUpload, uploadImage])

  const handleDragOver = useCallback((e: DragEvent<HTMLTextAreaElement>) => {
    e.preventDefault()
    if (canUpload) setDragOver(true)
  }, [canUpload])

  const handleDragLeave = useCallback(() => {
    setDragOver(false)
  }, [])

  const handleFileSelect = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && (file.type.startsWith('image/') || file.type.startsWith('video/'))) {
      uploadImage(file)
    }
    // Reset input so same file can be selected again
    e.target.value = ''
  }, [uploadImage])

  const handleToolbarAction = useCallback((action: ToolbarAction['action']) => {
    const ta = textareaRef.current
    if (!ta) return
    const { text, cursor } = action(value, ta.selectionStart, ta.selectionEnd)
    onChange(text)
    requestAnimationFrame(() => {
      ta.selectionStart = ta.selectionEnd = cursor
      ta.focus()
    })
  }, [value, onChange])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Tab inserts 2 spaces
    if (e.key === 'Tab') {
      e.preventDefault()
      insertTextAtCursor('  ')
    }
  }, [insertTextAtCursor])

  return (
    <div className={`border border-[var(--border)] rounded-lg overflow-hidden ${className}`}>
      {/* Toolbar */}
      <div className="flex items-center gap-0.5 px-2 py-1.5 bg-[var(--bg-secondary)] border-b border-[var(--border)] flex-wrap">
        {/* Mode tabs */}
        <button
          onClick={() => setMode('write')}
          className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
            mode === 'write'
              ? 'bg-[var(--bg-card)] text-[var(--text-primary)] shadow-sm'
              : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
        >
          <Pencil size={12} /> {t('markdownEditor.write')}
        </button>
        <button
          onClick={() => setMode('preview')}
          className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
            mode === 'preview'
          ? 'bg-[var(--bg-card)] text-[var(--text-primary)] shadow-sm'
              : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
        >
          <Eye size={12} /> {t('markdownEditor.preview')}
        </button>

        {mode === 'write' && (
          <>
            <div className="w-px h-4 bg-[var(--border)] mx-1" />
            {toolbarActions.map((item, i) => (
              <button
                key={i}
                onClick={() => handleToolbarAction(item.action)}
                className="p-1 rounded hover:bg-[var(--bg-card)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                title={t(item.labelKey)}
              >
                <item.icon size={14} />
              </button>
            ))}
            {canUpload && (
              <>
                <div className="w-px h-4 bg-[var(--border)] mx-1" />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="p-1 rounded hover:bg-[var(--bg-card)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors disabled:opacity-50"
                  title={t('markdownEditor.uploadImage')}
                >
                  {uploading ? <Loader2 size={14} className="animate-spin" /> : <ImageIcon size={14} />}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*,video/mp4,video/webm"
                  className="hidden"
                  onChange={handleFileSelect}
                />
              </>
            )}
          </>
        )}

        {uploading && (
          <span className="ml-auto text-xs text-[var(--text-secondary)] flex items-center gap-1">
            <Loader2 size={12} className="animate-spin" /> {t('markdownEditor.uploading')}
          </span>
        )}
      </div>

      {/* Content area */}
      {mode === 'write' ? (
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={e => onChange(e.target.value)}
            onPaste={handlePaste}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={rows}
            autoFocus={autoFocus}
            className={`w-full p-3 text-sm font-mono resize-y bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none border-0 ${
              dragOver ? 'bg-blue-50/50' : ''
            }`}
            style={{ minHeight: `${rows * 1.5}rem` }}
          />
          {dragOver && (
            <div className="absolute inset-0 flex items-center justify-center bg-blue-50/80 dark:bg-blue-900/30 pointer-events-none rounded-b-lg">
              <div className="flex items-center gap-2 text-blue-600 text-sm font-medium">
                <Upload size={20} /> {t('markdownEditor.dropImage')}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="p-3 prose prose-sm max-w-none min-h-[8rem] text-[var(--text-primary)]" style={{ minHeight: `${rows * 1.5}rem` }}>
          {value ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={previewComponents}>{value}</ReactMarkdown>
          ) : (
            <p className="text-[var(--text-secondary)] italic">{t('markdownEditor.nothingToPreview')}</p>
          )}
        </div>
      )}

      {/* Footer hint */}
      {mode === 'write' && (
        <div className="px-3 py-1.5 bg-[var(--bg-secondary)] border-t border-[var(--border)] text-[10px] text-[var(--text-secondary)]">
          {canUpload ? t('markdownEditor.footerHintUpload') : t('markdownEditor.footerHint')}
        </div>
      )}
    </div>
  )
}

export default MarkdownEditor
