import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { motion } from 'framer-motion'
import type { Issue } from '../stores/boardStore'
import { useBoardStore } from '../stores/boardStore'
import { MarkdownEditor } from './MarkdownEditor'
import type { Components } from 'react-markdown'
import {
  Clock, Tag, AlertCircle, CheckCircle2, XCircle, GitBranch,
  Pencil, Save, X, Image, FileCode, FlaskConical, ShieldCheck, Play, ChevronDown, ChevronRight, Trash2, Square, Bot, ArrowUpRight, FilePlus, FileMinus, FileEdit, ClipboardList
} from 'lucide-react'
import { VALID_TRANSITIONS } from '../constants/transitions'
import { AgentLogPanel } from './AgentLogPanel'
import { Lightbox } from './Lightbox'
import { PlanningTerminal } from './PlanningTerminal'

const VIDEO_EXTENSIONS = /\.(mp4|webm)$/i

const markdownComponents: Components = {
  img: ({ src, alt, ...props }) => {
    if (src && VIDEO_EXTENSIONS.test(src)) {
      return (
        <video
          src={src}
          controls
          muted
          loop
          style={{ maxWidth: '100%', borderRadius: '0.5rem' }}
        />
      )
    }
    return (
      <img
        src={src}
        alt={alt || ''}
        loading="lazy"
        style={{ maxWidth: '100%', height: 'auto', borderRadius: '0.5rem', cursor: 'pointer' }}
        onClick={() => src && window.open(src, '_blank')}
        {...props}
      />
    )
  },
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

interface IssueDetailProps {
  issue: Issue
  onClose: () => void
  onApprove: () => void
  onReject: (comment: string) => void
  onRun?: () => void
  onDelete?: () => void
}

interface ScreenshotItem {
  url: string
  type?: 'image' | 'video'  // defaults to 'image' for backward compat
}

interface EvidenceData {
  changeSummary: string
  gitDiff: string
  buildResult: { passed: boolean; output: string } | null
  screenshots: ScreenshotItem[]
  evalSummary: string
  evalItems: { passed: boolean; text: string }[]
  // Structured fields from evidence.json
  filesChanged: number
  commitsCount: number
  diffContent: string
  changedFiles: { filename: string; additions: number; deletions: number; change_type: string }[]
  evalChecks: { criterion: string; passed: boolean; detail: string }[]
  isStructured: boolean
}

function parseStructuredEvidence(data: Record<string, unknown>): EvidenceData {
  const screenshots: ScreenshotItem[] = (data.screenshots as { url: string; type?: string }[] || []).map(s => ({
    url: s.url,
    type: (s.type === 'video' ? 'video' : 'image') as 'image' | 'video',
  }))
  const evalChecks = (data.eval_checks as { criterion: string; passed: boolean; detail: string }[] || [])
  const changedFiles = (data.changed_files as { filename: string; additions: number; deletions: number; change_type: string }[] || [])
  const buildResult = data.build_result as { passed: boolean; status: string; output: string } | null

  return {
    changeSummary: (data.change_summary as string) || '',
    gitDiff: (data.git_diff_stat as string) || '',
    buildResult: buildResult ? { passed: buildResult.passed, output: buildResult.output || '' } : null,
    screenshots,
    evalSummary: (data.eval_summary as string) || '',
    evalItems: evalChecks.map(c => ({ passed: c.passed, text: c.criterion })),
    filesChanged: (data.files_changed as number) || 0,
    commitsCount: (data.commits_count as number) || 0,
    diffContent: (data.git_diff_content as string) || '',
    changedFiles,
    evalChecks,
    isStructured: true,
  }
}

function parseEvidence(content: string): EvidenceData {
  const evidence: EvidenceData = {
    changeSummary: '',
    gitDiff: '',
    buildResult: null,
    screenshots: [],
    evalSummary: '',
    evalItems: [],
    filesChanged: 0,
    commitsCount: 0,
    diffContent: '',
    changedFiles: [],
    evalChecks: [],
    isStructured: false,
  }

  const sectionMatch = content.match(/## Agent Done 证据([\s\S]*?)(?=\n## |$)/)
  if (!sectionMatch) return evidence

  const section = sectionMatch[1]

  // Extract change summary (变更摘要)
  const summaryMatch = section.match(/### 变更摘要\s*\n\s*([\s\S]*?)(?=\n### |$)/)
  if (summaryMatch) {
    evidence.changeSummary = summaryMatch[1].trim()
  }

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

  // Extract screenshots (markdown images) and video links
  const imgRegex = /!\[([^\]]*)\]\(([^)]+)\)/g
  let imgMatch: RegExpExecArray | null
  while ((imgMatch = imgRegex.exec(section)) !== null) {
    const url = imgMatch[2]
    const isVideo = /\.(mp4|webm)$/i.test(url)
    evidence.screenshots.push({ url, type: isVideo ? 'video' : 'image' })
  }
  // Also detect video markdown links: [🎬 name](url.mp4)
  const videoLinkRegex = /\[🎬[^\]]*\]\(([^)]+)\)/g
  let videoMatch: RegExpExecArray | null
  while ((videoMatch = videoLinkRegex.exec(section)) !== null) {
    const url = videoMatch[1]
    // Avoid duplicates if already captured
    if (!evidence.screenshots.some(s => s.url === url)) {
      evidence.screenshots.push({ url, type: 'video' })
    }
  }

  // Extract eval result — supports both new structured format and legacy single-line
  const evalSectionMatch = section.match(/### 评估摘要\s*\n([\s\S]*?)(?=\n### |$)/)
  if (evalSectionMatch) {
    const evalBlock = evalSectionMatch[1]
    // Parse individual ✅/❌ items
    const itemRegex = /- (✅|❌)\s*(.+)/g
    let itemMatch: RegExpExecArray | null
    while ((itemMatch = itemRegex.exec(evalBlock)) !== null) {
      evidence.evalItems.push({
        passed: itemMatch[1] === '✅',
        text: itemMatch[2].trim(),
      })
    }
    // Extract summary line (e.g. "评估结果: 3/4 通过")
    const resultLine = evalBlock.match(/评估结果[:：]\s*([^\n]+)/i)
    if (resultLine) {
      evidence.evalSummary = resultLine[1].trim()
    }
  } else {
    // Legacy: single-line eval match
    const evalMatch = section.match(/(?:eval|评估)[^\n]*[:：]\s*([^\n]+)/i)
    if (evalMatch) {
      evidence.evalSummary = evalMatch[1].trim()
    }
  }

  return evidence
}

export function IssueDetail({ issue, onClose, onApprove, onReject, onRun, onDelete }: IssueDetailProps) {
  const { t } = useTranslation()
  const [rejectComment, setRejectComment] = useState('')
  const [showRejectForm, setShowRejectForm] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [content, setContent] = useState('')
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(issue.title)
  const [editPriority, setEditPriority] = useState(issue.priority)
  const [editLabels, setEditLabels] = useState(issue.labels.join(', '))
  const [editingContent, setEditingContent] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [plan, setPlan] = useState('')
  const [editingPlan, setEditingPlan] = useState(false)
  const [editPlan, setEditPlan] = useState('')
  const [saving, setSaving] = useState(false)
  const [showStatusMenu, setShowStatusMenu] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [children, setChildren] = useState<{ id: string; title: string; status: string }[]>([])
  const [runStats, setRunStats] = useState<{ total_runs: number; total_cost_usd: number; total_duration_ms: number; runs: any[] } | null>(null)
  const [structuredEvidence, setStructuredEvidence] = useState<EvidenceData | null>(null)

  const updateIssue = useBoardStore(s => s.updateIssue)
  const updateIssueContent = useBoardStore(s => s.updateIssueContent)
  const updateIssuePlan = useBoardStore(s => s.updateIssuePlan)
  const isRunning = useBoardStore(s => s.runningIssueIds.includes(issue.id)) || issue.status === 'in_progress'
  const fetchBoard = useBoardStore(s => s.fetchBoard)
  const fetchIssues = useBoardStore(s => s.fetchIssues)

  const allowedTransitions = VALID_TRANSITIONS[issue.status] || []

  const handleStatusChange = async (newStatus: string) => {
    setShowStatusMenu(false)
    setStatusError(null)
    const projectId = useBoardStore.getState().projectId
    if (!projectId) return
    const res = await fetch(`/api/projects/${projectId}/issues/${issue.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      setStatusError(data.detail || t('issueDetail.statusChangeFailed'))
      setTimeout(() => setStatusError(null), 3000)
      return
    }
    await fetchBoard()
    await fetchIssues()
  }

  useEffect(() => {
    const projectId = useBoardStore.getState().projectId
    if (projectId) {
      fetch(`/api/projects/${projectId}/issues/${issue.id}`)
        .then(r => r.json())
        .then(data => {
          setContent(data.content || '')
          setPlan(data.plan || '')
          setChildren(data.children || [])
        })
      fetch(`/api/projects/${projectId}/issues/${issue.id}/stats`)
        .then(r => r.json())
        .then(data => setRunStats(data))
      // Fetch structured evidence data when issue is agent_done
      if (issue.status === 'agent_done') {
        fetch(`/api/projects/${projectId}/issues/${issue.id}/evidence`)
          .then(r => r.json())
          .then(data => {
            if (data && typeof data === 'object' && data.collected_at) {
              setStructuredEvidence(parseStructuredEvidence(data))
            }
          })
          .catch(() => {}) // Fallback to markdown parsing
      }
    }
  }, [issue.id])

  useEffect(() => {
    setEditTitle(issue.title)
    setEditPriority(issue.priority)
    setEditLabels(issue.labels.join(', '))
  }, [issue.title, issue.priority, issue.labels])

  const evidence = useMemo(() => {
    if (issue.status === 'agent_done') {
      // Prefer structured evidence from API, fallback to markdown parsing
      if (structuredEvidence) return structuredEvidence
      return parseEvidence(content)
    }
    return null
  }, [content, issue.status, structuredEvidence])

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

  const handleSavePlan = async () => {
    setSaving(true)
    await updateIssuePlan(issue.id, editPlan)
    setPlan(editPlan)
    setEditingPlan(false)
    setSaving(false)
  }

  const startEditPlan = () => {
    setEditPlan(plan)
    setEditingPlan(true)
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
              title={t('issueDetail.editIssue')}
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
                title={t('issueDetail.saveChanges')}
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
                title={t('issueDetail.cancel')}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {onDelete && (
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="p-1.5 rounded-lg hover:bg-red-50 text-[var(--text-secondary)] hover:text-red-500 transition-colors"
              title={t('issueDetail.deleteIssue')}
            >
              <Trash2 size={16} />
            </button>
          )}
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
        </div>

        <div className="px-6 py-4 space-y-6">
          {/* Status / Priority / Assignee */}
          <div className="flex flex-wrap gap-3 text-sm items-center">
            <div className="relative">
              <button
                onClick={() => allowedTransitions.length > 0 && setShowStatusMenu(!showStatusMenu)}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-white text-xs font-medium ${statusColor(issue.status)} ${allowedTransitions.length > 0 ? 'cursor-pointer hover:opacity-90' : 'cursor-default'}`}
              >
                {t(`status.${issue.status}`, issue.status.replace('_', ' '))}
                {allowedTransitions.length > 0 && <ChevronDown size={12} />}
              </button>
              {showStatusMenu && (
                <div className="absolute top-full left-0 mt-1 bg-[var(--bg-card)] border border-[var(--border)] rounded-lg shadow-lg z-20 min-w-[140px] py-1">
                  {allowedTransitions.map(status => (
                    <button
                      key={status}
                      onClick={() => handleStatusChange(status)}
                      className="w-full text-left px-3 py-1.5 text-xs hover:bg-[var(--bg-secondary)] text-[var(--text-primary)] flex items-center gap-2"
                    >
                      <span className={`w-2 h-2 rounded-full ${statusColor(status)}`} />
                      {t(`status.${status}`, status)}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {statusError && (
              <span className="text-xs text-red-500">{statusError}</span>
            )}
            {editing ? (
              <select
                value={editPriority}
                onChange={e => setEditPriority(e.target.value)}
                className="px-2 py-0.5 rounded text-xs font-medium border border-[var(--border)] bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              >
                <option value="low">{t('issue.create.priority.low')}</option>
                <option value="medium">{t('issue.create.priority.medium')}</option>
                <option value="high">{t('issue.create.priority.high')}</option>
                <option value="urgent">{t('issue.create.priority.urgent')}</option>
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
              <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 block">{t('issueDetail.labelsLabel')}</label>
              <input
                value={editLabels}
                onChange={e => setEditLabels(e.target.value)}
                className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-sm bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                placeholder={t('issueDetail.labelsPlaceholder')}
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
                  <AlertCircle size={14} /> {t('issueDetail.blockedBy')} {issue.blocked_by.join(', ')}
                </div>
              )}
              {issue.blocks.length > 0 && (
                <div className="flex items-center gap-1 text-gray-500">
                  <GitBranch size={14} /> {t('issueDetail.blocks')} {issue.blocks.join(', ')}
                </div>
              )}
            </div>
          )}

          {/* Parent / Children */}
          {issue.parent_id && (
            <div className="flex items-center gap-1.5 text-sm text-violet-600">
              <ArrowUpRight size={14} />
              <span>{t('issueDetail.parentIssue')}</span>
              <span className="font-mono font-medium">{issue.parent_id}</span>
              {issue.source === 'agent' && (
                <span className="inline-flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-full bg-violet-50 text-violet-600">
                  <Bot size={10} /> {t('issueDetail.agent')}
                </span>
              )}
            </div>
          )}
          {children.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-sm font-semibold text-[var(--text-primary)] mb-2">
                <Bot size={14} className="text-violet-500" /> {t('issueDetail.childIssues', { count: children.length })}
              </div>
              <div className="space-y-1.5">
                {children.map(child => (
                  <div key={child.id} className="flex items-center gap-2 text-sm px-3 py-1.5 bg-[var(--bg-secondary)] rounded-lg">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${statusDot(child.status)}`} />
                    <span className="font-mono text-xs text-gray-400">{child.id}</span>
                    <span className="text-[var(--text-primary)] truncate">{child.title}</span>
                    <span className="ml-auto text-xs text-[var(--text-secondary)]">{t(`status.${child.status}`, child.status.replace('_', ' '))}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Run Stats */}
          {runStats && runStats.total_runs > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-sm font-semibold text-[var(--text-primary)] mb-2">
                <FlaskConical size={14} /> {t('issueDetail.agentRuns', { count: runStats.total_runs })}
                <span className="ml-auto text-xs font-normal text-[var(--text-secondary)]">
                  {t('issueDetail.total', { cost: runStats.total_cost_usd.toFixed(2), duration: Math.round(runStats.total_duration_ms / 1000) })}
                </span>
              </div>
              <div className="border border-[var(--border)] rounded-lg overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-[var(--bg-secondary)] text-[var(--text-secondary)]">
                      <th className="px-3 py-1.5 text-left font-medium">{t('issueDetail.run')}</th>
                      <th className="px-3 py-1.5 text-right font-medium">{t('issueDetail.turns')}</th>
                      <th className="px-3 py-1.5 text-right font-medium">{t('issueDetail.tokens')}</th>
                      <th className="px-3 py-1.5 text-right font-medium">{t('issueDetail.cost')}</th>
                      <th className="px-3 py-1.5 text-right font-medium">{t('issueDetail.duration')}</th>
                      <th className="px-3 py-1.5 text-center font-medium">{t('issueDetail.result')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runStats.runs.map((run: any) => (
                      <tr key={run.run_id} className="border-t border-[var(--border)]">
                        <td className="px-3 py-1.5 font-mono text-[var(--text-secondary)]">{run.run_id}</td>
                        <td className="px-3 py-1.5 text-right text-[var(--text-primary)]">{run.turns}</td>
                        <td className="px-3 py-1.5 text-right text-[var(--text-primary)]">
                          {run.tokens_in + run.tokens_out > 0
                          ? `${((run.tokens_in + run.tokens_out) / 1000).toFixed(1)}k`
                            : '-'}
                        </td>
                        <td className="px-3 py-1.5 text-right text-[var(--text-primary)]">${run.cost_usd.toFixed(2)}</td>
                        <td className="px-3 py-1.5 text-right text-[var(--text-primary)]">{Math.round(run.duration_ms / 1000)}s</td>
                        <td className="px-3 py-1.5 text-center">
                          {run.success
                            ? <span className="text-green-600">{t('issueDetail.pass')}</span>
                            : <span className="text-red-500">{t('issueDetail.fail')}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Planning Terminal */}
          {issue.status === 'planning' && (
            <div>
              <PlanningTerminal
                issueId={issue.id}
                projectId={useBoardStore.getState().projectId || ''}
              />
            </div>
          )}

          {/* Run / Stop / Planning Action */}
          {['todo', 'backlog', 'rejected', 'failed', 'planning'].includes(issue.status) && !isRunning && (
            <div className="border-t border-[var(--border)] pt-4 flex items-center gap-2">
              {issue.status === 'backlog' && (
                <button
                  onClick={() => useBoardStore.getState().moveIssue(issue.id, 'planning')}
                  className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 text-sm font-medium"
                >
                  <ClipboardList size={16} /> {t('issueCard.planning')}
                </button>
              )}
              {onRun && (
                <button
                  onClick={onRun}
                  className="flex items-center gap-1.5 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium"
                >
                  <Play size={16} /> {issue.status === 'failed' ? t('issueDetail.resume') : t('issueDetail.runAction')}
                </button>
              )}
            </div>
          )}
          {(isRunning || issue.status === 'in_progress') && (
            <div className="border-t border-[var(--border)] pt-4">
              <button
                onClick={() => useBoardStore.getState().stopIssue(issue.id)}
                className="flex items-center gap-1.5 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium"
              >
                <Square size={16} fill="currentColor" /> {t('issueDetail.stop')}
              </button>
            </div>
          )}

          {/* Agent Log */}
          {['in_progress', 'agent_done'].includes(issue.status) && (
            <AgentLogPanel
              issueId={issue.id}
              onCancel={() => {
                const wsSend = useBoardStore.getState().wsSend
                if (wsSend) {
                  wsSend({ type: 'cancel_agent', issue_id: issue.id })
                }
              }}
            />
          )}

          {/* Evidence Panel (agent_done only) */}
          {issue.status === 'agent_done' && evidence && (
            <EvidencePanel evidence={evidence} />
          )}

          {/* Plan */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">{t('issueDetail.plan')}</h3>
              {!editingPlan ? (
                <button
                  onClick={startEditPlan}
                  className="text-xs text-[var(--accent)] hover:underline flex items-center gap-1"
                >
                  <Pencil size={12} /> {t('issueDetail.edit')}
                </button>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={handleSavePlan}
                    disabled={saving}
                    className="text-xs text-green-600 hover:underline flex items-center gap-1 disabled:opacity-50"
                  >
                    <Save size={12} /> {t('issueDetail.save')}
                  </button>
                  <button
                    onClick={() => setEditingPlan(false)}
                    className="text-xs text-red-500 hover:underline flex items-center gap-1"
                  >
                    <X size={12} /> {t('issueDetail.cancel')}
                  </button>
                </div>
              )}
            </div>
            {editingPlan ? (
              <MarkdownEditor
                value={editPlan}
                onChange={setEditPlan}
                placeholder={t('issueDetail.planPlaceholder')}
                rows={10}
                projectId={useBoardStore.getState().projectId}
                issueId={issue.id}
              />
            ) : (
              <div className="prose prose-sm max-w-none text-[var(--text-primary)]">
                {plan ? (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={markdownComponents}
                  >{plan}</ReactMarkdown>
                ) : (
                  <p className="text-[var(--text-secondary)] text-sm italic">{t('issueDetail.noPlan')}</p>
                )}
              </div>
            )}
          </div>

          {/* Content */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">{t('issueDetail.content')}</h3>
              {!editingContent ? (
                <button
                  onClick={startEditContent}
                  className="text-xs text-[var(--accent)] hover:underline flex items-center gap-1"
                >
                  <Pencil size={12} /> {t('issueDetail.edit')}
                </button>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={handleSaveContent}
                    disabled={saving}
                    className="text-xs text-green-600 hover:underline flex items-center gap-1 disabled:opacity-50"
                  >
                    <Save size={12} /> {t('issueDetail.save')}
                  </button>
                  <button
                    onClick={() => setEditingContent(false)}
                    className="text-xs text-red-500 hover:underline flex items-center gap-1"
                  >
                    <X size={12} /> {t('issueDetail.cancel')}
                  </button>
                </div>
              )}
            </div>
            {editingContent ? (
              <MarkdownEditor
                value={editContent}
                onChange={setEditContent}
                placeholder={t('issueDetail.contentPlaceholder')}
                rows={10}
                projectId={useBoardStore.getState().projectId}
                issueId={issue.id}
              />
            ) : (
              <div className="prose prose-sm max-w-none text-[var(--text-primary)]">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={markdownComponents}
                >{content}</ReactMarkdown>
              </div>
            )}
          </div>

          {/* Human Review */}
          {issue.status === 'agent_done' && (
            <div className="border-t border-[var(--border)] pt-4 space-y-3">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">{t('issueDetail.humanReview')}</h3>
              <div className="flex gap-2">
                <button
                  onClick={onApprove}
                  className="flex items-center gap-1.5 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium"
                >
                  <CheckCircle2 size={16} /> {t('issueDetail.approve')}
                </button>
                <button
                  onClick={() => setShowRejectForm(!showRejectForm)}
                  className="flex items-center gap-1.5 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium"
                >
                  <XCircle size={16} /> {t('issueDetail.reject')}
                </button>
              </div>
              {showRejectForm && (
                <div className="space-y-2">
                  <textarea
                    value={rejectComment}
                    onChange={e => setRejectComment(e.target.value)}
                    placeholder={t('issueDetail.rejectPlaceholder')}
                    className="w-full h-32 p-3 border border-[var(--border)] rounded-lg text-sm resize-none bg-[var(--input-bg)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-red-300"
                  />
                  <button
                    onClick={() => { onReject(rejectComment); setRejectComment(''); setShowRejectForm(false) }}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm"
                  >
                    {t('issueDetail.submitRejection')}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Delete Confirmation */}
        {showDeleteConfirm && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/20">
            <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl shadow-xl p-5 mx-6 max-w-sm">
              <p className="text-sm text-[var(--text-primary)] mb-4">
                {t('issueDetail.deleteConfirm', { id: issue.id })}
              </p>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="px-3 py-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  {t('issueDetail.cancel')}
                </button>
                <button
                  onClick={() => { onDelete?.(); setShowDeleteConfirm(false) }}
                  className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700"
                >
                  {t('issueDetail.delete')}
                </button>
              </div>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  )
}

function EvidencePanel({ evidence }: { evidence: EvidenceData }) {
  const { t } = useTranslation()
  const [galleryIndex, setGalleryIndex] = useState(0)
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const [showFiles, setShowFiles] = useState(false)
  const [showDiff, setShowDiff] = useState(false)
  const [showBuildLog, setShowBuildLog] = useState(false)
  const hasAny = evidence.changeSummary || evidence.gitDiff || evidence.buildResult || evidence.screenshots.length > 0 || evidence.evalSummary || evidence.evalItems.length > 0

  if (!hasAny) return null

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 bg-[var(--bg-secondary)] border-b border-[var(--border)]">
        <h3 className="text-sm font-semibold text-[var(--text-primary)] flex items-center gap-2">
          <ShieldCheck size={16} className="text-violet-500" />
          {t('issueDetail.evidence')}
        </h3>
      </div>
      <div className="p-4 space-y-4">
        {/* Eval Checks — most important, shown first */}
        {(evidence.evalItems.length > 0 || evidence.evalSummary) && (
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)] mb-2">
              <FlaskConical size={14} /> {t('issueDetail.evalResult')}
              {evidence.evalSummary && (
                <span className="ml-auto text-xs text-[var(--text-secondary)]">{evidence.evalSummary}</span>
              )}
            </div>
            {evidence.evalItems.length > 0 && (
              <div className="space-y-1.5 mb-2">
                {evidence.evalItems.map((item, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <span className="shrink-0 mt-0.5">
                      {item.passed
                        ? <CheckCircle2 size={14} className="text-green-500" />
                        : <XCircle size={14} className="text-red-500" />}
                    </span>
                    <span className={`${item.passed ? 'text-[var(--text-primary)]' : 'text-red-600 font-medium'}`}>
                      {item.text}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Screenshots / Recordings with Lightbox */}
        {evidence.screenshots.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)] mb-2">
              <Image size={14} /> {t('issueDetail.screenshots', { count: evidence.screenshots.length })}
            </div>
            <div className="flex gap-2 ovo pb-2">
              {evidence.screenshots.map((item, i) => {
                const isVideo = item.type === 'video' || /\.(mp4|webm)$/i.test(item.url)
                return isVideo ? (
                  <video
                    key={i}
                    src={item.url}
                    muted
                    loop
                    controls
                    className={`h-32 rounded-lg border-2 cursor-pointer transition-all hover:opacity-80 ${i === galleryIndex ? 'border-[var(--accent)]' : 'border-transparent'}`}
                    onClick={() => { setGalleryIndex(i); setLightboxOpen(true) }}
                  />
                ) : (
                  <img
                    key={i}
                    src={item.url}
                    alt={t('issueDetail.screenshot', { index: i + 1 })}
                    className={`h-32 rounded-lg border-2 cursor-pointer transition-all hover:opacity-80 ${i === galleryIndex ? 'border-[var(--accent)]' : 'border-transparent'}`}
                    onClick={() => { setGalleryIndex(i); setLightboxOpen(true) }}
                  />
                )
              })}
            </div>
            {lightboxOpen && (
              <Lightbox
                media={evidence.screenshots.map(s => ({ url: s.url, type: s.type === 'video' || /\.(mp4|webm)$/i.test(s.url) ? 'video' : 'image' }))}
                initialIndex={galleryIndex}
                onClose={() => setLightboxOpen(false)}
              />
            )}
          </div>
        )}

        {/* Change Summary */}
        {evidence.changeSummary && (
          <div className="flex items-center gap-3 px-3 py-2 bg-[var(--bg-secondary)] rounded-lg">
            <GitBranch size={14} className="text-violet-500 shrink-0" />
            <span className="text-sm text-[var(--text-primary)]">{evidence.changeSummary}</span>
            {evidence.isStructured && evidence.commitsCount > 0 && (
              <span className="ml-auto text-xs text-[var(--text-secondary)]">
                {t('issueDetail.commitsCount', { count: evidence.commitsCount })}
              </span>
            )}
          </div>
        )}

        {/* File Changes — collapsible list */}
        {evidence.isStructured && evidence.changedFiles.length > 0 && (
          <div>
            <button
              onClick={() => setShowFiles(!showFiles)}
              className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)] mb-2 hover:text-[var(--text-primary)] transition-colors"
            >
              {showFiles ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <FileCode size={14} />
              {t('issueDetail.filesChanged', { count: evidence.filesChanged })}
            </button>
            {showFiles && (
              <div className="space-y-1 ml-1">
                {evidence.changedFiles.map((f, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs px-2 py-1 rounded bg-[var(--bg-secondary)]">
                    <span className="shrink-0">
                      {f.change_type === 'added' && <FilePlus size={12} className="text-green-500" />}
                      {f.change_type === 'deleted' && <FileMinus size={12} className="text-red-500" />}
                      {f.change_type === 'modified' && <FileEdit size={12} className="text-amber-500" />}
                    </span>
                    <span className="font-mono text-[var(--text-primary)] truncate flex-1">{f.filename}</span>
                    <span className="text-green-600 shrink-0">+{f.additions}</span>
                    <span className="text-red-500 shrink-0">-{f.deletions}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Git Diff — collapsible */}
        {(evidence.gitDiff || evidence.diffContent) && (
          <div>
            <button
              onClick={() => setShowDiff(!showDiff)}
              className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)] mb-2 hover:text-[var(--text-primary)] transition-colors"
            >
              {showDiff ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <FileCode size={14} /> {t('issueDetail.codeChanges')}
            </button>
            {showDiff && (
              <pre className="bg-[#0d1117] text-[#c9d1d9] p-3 rounded-lg text-xs overflow-x-auto max-h-64 overflow-y-auto">
                <code>{evidence.diffContent || evidence.gitDiff}</code>
              </pre>
            )}
          </div>
        )}

        {/* Build Result — collapsible log */}
        {evidence.buildResult && (
          <div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)]">
                <FlaskConical size={14} /> {t('issueDetail.buildResult')}
              </div>
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium text-white ${evidence.buildResult.passed ? 'bg-green-500' : 'bg-red-500'}`}>
                {evidence.buildResult.passed ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                {evidence.buildResult.passed ? t('issueDetail.buildPass') : t('issueDetail.buildFail')}
              </span>
              {evidence.buildResult.output && (
                <button
                  onClick={() => setShowBuildLog(!showBuildLog)}
                  className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors ml-auto"
                >
                  {showBuildLog ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                </button>
              )}
            </div>
            {showBuildLog && evidence.buildResult.output && (
              <pre className="bg-[#0d1117] text-[#c9d1d9] p-3 rounded-lg text-xs overflow-x-auto max-h-48 overflow-y-auto mt-2">
                <code>{evidence.buildResult.output}</code>
              </pre>
            )}
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

function statusDot(status: string): string {
  const map: Record<string, string> = {
    backlog: 'bg-slate-400',
    todo: 'bg-blue-500',
    in_progress: 'bg-amber-500',
    agent_done: 'bg-violet-500',
    rejected: 'bg-red-500',
    human_done: 'bg-green-500',
    failed: 'bg-red-400',
  }
  return map[status] || 'bg-gray-400'
}

export default IssueDetail
