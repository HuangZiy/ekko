import { useState, useEffect, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { motion } from 'framer-motion'
import type { Issue } from '../stores/boardStore'
import { useBoardStore } from '../stores/boardStore'
import {
  Clock, Tag, AlertCircle, CheckCircle2, XCircle, GitBranch,
  Pencil, Save, X, Image, FileCode, FlaskConical, ShieldCheck
} from 'lucide-react'

interface IssueDetailProps {
  issue: Issue
  onClose: () => void
  onApprove: () => void
  onReject: (comment: string) => void
}

interface EvidenceData {
  gitDiff: string
  buildResult: { passed: boolean; output: string } | null
  screenshots: string[]
  evalSummary: string
}

function parseEvidence(content: string): EvidenceData {
  const evidence: EvidenceData = {
    gitDiff: '',
    buildResult: null,
    screenshots: [],
    evalSummary: '',
  }

  const sectionMatch = content.match(/## Agent Done 证据([\s\S]*?)(?=\n## |$)/)
  if (!sectionMatch) return evidence

  const section = sectionMatch[1]

  // Extract git diff from code blocks
  const diffMatch = section.match(/```(?:diff)?\n([\s\S]*?)```/)
  if (diffMatch) {
    evidence.gitDiff = diffMatch[1].trim()
  }

  // Extract build result
  const buildMatch = section.match(/(?:build|构建)[^\n]*?[:：]\s*(pass|fail|passed|failed|成功|失败)/i)
  if (buildMatch) {
    const raw = buildMatch[1].toLowerCase()
    const passed = raw === 'pass' || raw === 'passed' || raw === '成功'
    // Get the full line for output
    const lineMatch = section.match(/(?:build|构建)[^\n]*/i)
    evidence.buildResult = { passed, output: lineMatch ? lineMatch[0].trim() : '' }
  }

  // Extract screenshots (markdown images)
  const imgRegex = /!\[([^\]]*)\]\(([^)]+)\)/g
  let imgMatch: RegExpExecArray | null
  while ((imgMatch = imgRegex.exec(section)) !== null) {
    evidence.screenshots.push(imgMatch[2])
  }

  // Extract eval result
  const evalMatch = section.match(/(?:eval|评估)[^\n]*[:：]\s*([^\n]+)/i)
  if (evalMatch) {
    evidence.evalSummary = evalMatch[1].trim()
  }

  return evidence
}

export function IssueDetail({ issue, onClose, onApprove, onReject }: IssueDetailProps) {
  const [rejectComment, setRejectComment] = useState('')
  const [showRejectForm, setShowRejectForm] = useState(false)
  const [content, setContent] = useState('')
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(issue.title)
  const [editPriority, setEditPriority] = useState(issue.priority)
  const [editLabels, setEditLabels] = useState(issue.labels.join(', '))
  const [editingContent, setEditingContent] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)

  const updateIssue = useBoardStore(s => s.updateIssue)
  const updateIssueContent = useBoardStore(s => s.updateIssueContent)

  useEffect(() => {
    const projectId = useBoardStore.getState().projectId
    if (projectId) {
      fetch(`/api/projects/${projectId}/issues/${issue.id}`)
        .then(r => r.json())
        .then(data => setContent(data.content || ''))
    }
  }, [issue.id])

  useEffect(() => {
    setEditTitle(issue.title)
    setEditPriority(issue.priority)
    setEditLabels(issue.labels.join(', '))
  }, [issue.title, issue.priority, issue.labels])

  const evidence = useMemo(() => {
    if (issue.status === 'agent_done') return parseEvidence(content)
    return null
  }, [content, issue.status])

  const handleSaveFields = async () => {
    setSaving(true)
    const labels = editLabels
      .split(',')
      .map(l => l.trim())
      .filter(Boolean)
    await updateIssue(issue.id, {
      title: editTitle,
      priority: editPriority,
      labels,
    })
    setEditing(false)
    setSaving(false)
  }

  const handleSaveContent = async () => {
    setSaving(true)
    await updateIssueContent(issue.id, editContent)
    setContent(editContent)
    setEditingContent(false)
    setSaving(false)
  }

  const startEditContent = () => {
    setEditContent(content)
    setEditingContent(true)
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <motion.div
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        className="relative ml-auto w-full max-w-2xl bg-[var(--bg-card)] h-full overflow-y-auto shadow-xl"
      >
        {/* Header */}
        <div className="sticky top-0 bg-[var(--bg-card)] border-b border-[var(--border)] px-6 py-4 flex items-center gap-3 z-10">
          <span className="text-xs text-gray-400 font-mono">{issue.id}</span>
          {editing ? (
            <input
              value={editTitle}
              onChange={e => setEditTitle(e.target.value)}
              className="text-lg font-semibold flex-1 px-2 py-1 border border-[var(--border)] rounded-lg bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
            />
          ) : (
            <h2 className="text-lg font-semibold flex-1 truncate text-[var(--text-primary)]">{issue.title}</h2>
          )}
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="p-1.5 rounded-lg hover:bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              title="Edit issue"
            >
              <Pencil size={16} />
            </button>
          )}
          {editing && (
            <div className="flex gap-1">
              <button
                onClick={handleSaveFields}
                disabled={saving}
                className="p-1.5 rounded-lg hover:bg-green-50 text-green-600 hover:text-green-700 transition-colors disabled:opacity-50"
                title="Save changes"
              >
                <Save size={16} />
              </button>
              <button
                onClick={() => {
                  setEditing(false)
                  setEditTitle(issue.title)
                  setEditPriority(issue.priority)
                  setEditLabels(issue.labels.join(', '))
                }}
                className="p-1.5 rounded-lg hover:bg-red-50 text-red-500 hover:text-red-600 transition-colors"
                title="Cancel"
              >
                <X size={16} />
              </button>
            </div>
          )}
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
        </div>

        <div className="px-6 py-4 space-y-6">
          {/* Status / Priority / Assignee */}
          <div className="flex flex-wrap gap-3 text-sm">
            <span className={`px-2 py-0.5 rounded text-white text-xs font-medium ${statusColor(issue.status)}`}>
              {issue.status.replace('_', ' ')}
            </span>
            {editing ? (
              <select
                value={editPriority}
                onChange={e => setEditPriority(e.target.value)}
                className="px-2 py-0.5 rounded text-xs font-medium border border-[var(--border)] bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              >
                <option value="low">low</option>
                <option value="medium">medium</option>
                <option value="high">high</option>
                <option value="urgent">urgent</option>
              </select>
            ) : (
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${priorityBg(issue.priority)}`}>
                {issue.priority}
              </span>
            )}
            {issue.assignee && (
              <span className="flex items-center gap-1 text-gray-500">
                <Clock size={14} /> {issue.assignee}
              </span>
            )}
          </div>

          {/* Labels */}
          {editing ? (
            <div>
              <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">Labels (comma-separated)</label>
              <input
                value={editLabels}
                onChange={e => setEditLabels(e.target.value)}
                className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-sm bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                placeholder="bug, frontend, urgent"
              />
            </div>
          ) : (
            issue.labels.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {issue.labels.map(l => (
                  <span key={l} className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700">
                    <Tag size={10} /> {l}
                  </span>
                ))}
              </div>
            )
          )}

          {/* Dependencies */}
          {(issue.blocked_by.length > 0 || issue.blocks.length > 0) && (
            <div className="space-y-1 text-sm">
              {issue.blocked_by.length > 0 && (
                <div className="flex items-center gap-1 text-orange-600">
                  <AlertCircle size={14} /> Blocked by: {issue.blocked_by.join(', ')}
                </div>
              )}
              {issue.blocks.length > 0 && (
                <div className="flex items-center gap-1 text-gray-500">
                  <GitBranch size={14} /> Blocks: {issue.blocks.join(', ')}
                </div>
              )}
            </div>
          )}

          {/* Evidence Panel (agent_done only) */}
          {issue.status === 'agent_done' && evidence && (
            <EvidencePanel evidence={evidence} />
          )}

          {/* Content */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">Content</h3>
              {!editingContent ? (
                <button
                  onClick={startEditContent}
                  className="text-xs text-[var(--accent)] hover:underline flex items-center gap-1"
                >
                  <Pencil size={12} /> Edit
                </button>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={handleSaveContent}
                    disabled={saving}
                    className="text-xs text-green-600 hover:underline flex items-center gap-1 disabled:opacity-50"
                  >
                    <Save size={12} /> Save
                  </button>
                  <button
                    onClick={() => setEditingContent(false)}
                    className="text-xs text-red-500 hover:underline flex items-center gap-1"
                  >
                    <X size={12} /> Cancel
                  </button>
                </div>
              )}
            </div>
            {editingContent ? (
              <textarea
                value={editContent}
                onChange={e => setEditContent(e.target.value)}
                className="w-full h-64 p-3 border border-[var(--border)] rounded-lg text-sm font-mono resize-y bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                placeholder="Markdown content..."
              />
            ) : (
              <div className="prose prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
              </div>
            )}
          </div>

          {/* Human Review */}
          {issue.status === 'agent_done' && (
            <div className="border-t border-[var(--border)] pt-4 space-y-3">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">Human Review</h3>
              <div className="flex gap-2">
                <button
                  onClick={onApprove}
                  className="flex items-center gap-1.5 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium"
                >
                  <CheckCircle2 size={16} /> Approve
                </button>
                <button
                  onClick={() => setShowRejectForm(!showRejectForm)}
                  className="flex items-center gap-1.5 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium"
                >
                  <XCircle size={16} /> Reject
                </button>
              </div>
              {showRejectForm && (
                <div className="space-y-2">
                  <textarea
                    value={rejectComment}
                    onChange={e => setRejectComment(e.target.value)}
                    placeholder="缺陷描述、优化建议..."
                    className="w-full h-32 p-3 border border-[var(--border)] rounded-lg text-sm resize-none bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-red-300"
                  />
                  <button
                    onClick={() => { onReject(rejectComment); setRejectComment(''); setShowRejectForm(false) }}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm"
                  >
                    Submit Rejection
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </motion.div>
    </div>
  )
}

function EvidencePanel({ evidence }: { evidence: EvidenceData }) {
  const [galleryIndex, setGalleryIndex] = useState(0)
  const hasAny = evidence.gitDiff || evidence.buildResult || evidence.screenshots.length > 0 || evidence.evalSummary

  if (!hasAny) return null

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 bg-[var(--bg-secondary)] border-b border-[var(--border)]">
        <h3 className="text-sm font-semibold text-[var(--text-primary)] flex items-center gap-2">
          <ShieldCheck size={16} className="text-violet-500" />
          Agent Done 证据
        </h3>
      </div>
      <div className="p-4 space-y-4">
        {/* Git Diff */}
        {evidence.gitDiff && (
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)] mb-2">
              <FileCode size={14} /> Git Diff
            </div>
            <pre className="bg-[#0d1117] text-[#c9d1d9] p-3 rounded-lg text-xs overflow-x-auto max-h-48 overflow-y-auto">
              <code>{evidence.gitDiff}</code>
            </pre>
          </div>
        )}

        {/* Build Result */}
        {evidence.buildResult && (
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)] mb-2">
              <FlaskConical size={14} /> Build Result
            </div>
            <div className="flex items-center gap-2">
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium text-white ${evidence.buildResult.passed ? 'bg-green-500' : 'bg-red-500'}`}>
                {evidence.buildResult.passed ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                {evidence.buildResult.passed ? 'PASS' : 'FAIL'}
              </span>
              <span className="text-xs text-[var(--text-secondary)]">{evidence.buildResult.output}</span>
            </div>
          </div>
        )}

        {/* Screenshots */}
        {evidence.screenshots.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)] mb-2">
              <Image size={14} /> Screenshots ({evidence.screenshots.length})
            </div>
            <div className="flex gap-2 overflow-x-auto pb-2">
              {evidence.screenshots.map((src, i) => (
                <img
                  key={i}
                  src={src}
                  alt={`Screenshot ${i + 1}`}
                  className={`h-32 rounded-lg border-2 cursor-pointer transition-all ${i === galleryIndex ? 'border-[var(--accent)]' : 'border-transparent'}`}
                  onClick={() => setGalleryIndex(i)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Eval Summary */}
        {evidence.evalSummary && (
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)] mb-2">
              <FlaskConical size={14} /> Eval Result
            </div>
            <p className="text-sm text-[var(--text-primary)]">{evidence.evalSummary}</p>
          </div>
        )}
      </div>
    </div>
  )
}

function statusColor(status: string): string {
  const map: Record<string, string> = {
    backlog: 'bg-slate-400',
    todo: 'bg-blue-500',
    in_progress: 'bg-amber-500',
    agent_done: 'bg-violet-500',
    rejected: 'bg-red-500',
    human_done: 'bg-green-500',
  }
  return map[status] || 'bg-gray-400'
}

function priorityBg(priority: string): string {
  const map: Record<string, string> = {
    urgent: 'bg-red-100 text-red-700',
    high: 'bg-orange-100 text-orange-700',
    medium: 'bg-blue-100 text-blue-700',
    low: 'bg-gray-100 text-gray-600',
  }
  return map[priority] || 'bg-gray-100 text-gray-600'
}
