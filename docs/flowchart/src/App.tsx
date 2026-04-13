import { useCallback, useState, useRef } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeChange,
  type EdgeChange,
  type NodeTypes,
  applyNodeChanges,
  applyEdgeChanges,
  MarkerType,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './App.css';

// --- Types ---

interface StepDef {
  id: string;
  title: string;
  titleZh: string;
  description: string;
  descriptionZh: string;
  detail: string;
  detailZh: string;
  icon: string;
  phase: Phase;
  codeFiles?: string[];
}

interface NoteDef {
  id: string;
  text: string;
  textZh: string;
  appearsWithStep: number;
  phase: Phase;
}

type Phase = 'input' | 'planning' | 'kanban' | 'execution' | 'review' | 'done';
type Lang = 'en' | 'zh';

// --- Theme ---

const phaseColors: Record<Phase, { bg: string; border: string; text: string }> = {
  input:     { bg: '#1a1a2e', border: '#60a5fa', text: '#93c5fd' },
  planning:  { bg: '#1a2e1a', border: '#4ade80', text: '#86efac' },
  kanban:    { bg: '#2e1a2e', border: '#c084fc', text: '#d8b4fe' },
  execution: { bg: '#2e2a1a', border: '#fbbf24', text: '#fde68a' },
  review:    { bg: '#2e1a1a', border: '#f87171', text: '#fca5a5' },
  done:      { bg: '#0a2a2a', border: '#2dd4bf', text: '#99f6e4' },
};

const phaseLabels: Record<Lang, Record<Phase, string>> = {
  en: { input: 'Input', planning: 'Planning', kanban: 'Kanban', execution: 'Execution', review: 'Review', done: 'Done' },
  zh: { input: '输入', planning: '规划', kanban: '看板', execution: '执行', review: '审核', done: '完成' },
};

// --- Steps ---

const allSteps: StepDef[] = [
  {
    id: 'requirement',
    title: 'User Requirement',
    titleZh: '用户需求',
    description: '"Add user authentication"',
    descriptionZh: '"增加用户认证系统"',
    detail: 'A single natural-language requirement is the only input Ekko needs. It can be a one-liner like "Add user authentication" or a detailed paragraph. The planner will decompose it into actionable issues.',
    detailZh: 'Ekko 只需要一句自然语言需求作为输入。可以是简单的一句话如"增加用户认证系统"，也可以是详细的段落描述。规划器会将其拆解为可执行的 Issue。',
    icon: '💬',
    phase: 'input',
    codeFiles: ['cli/main.py → plan command'],
  },
  {
    id: 'planner',
    title: 'Planner Agent',
    titleZh: 'Planner Agent',
    description: 'Brainstorm → specs + dependency-aware Issues',
    descriptionZh: '交互式 brainstorming → specs + 带依赖的 Issue',
    detail: 'The Planner Agent uses interactive brainstorming to analyze the requirement. It generates functional specs, creates dependency-aware issues with blocked_by relationships, and can split complex issues into children. Uses AskUserQuestion for clarification.',
    detailZh: 'Planner Agent 通过交互式 brainstorming 分析需求。它生成功能规格文档，创建带 blocked_by 依赖关系的 Issue，并可将复杂 Issue 拆分为子 Issue。支持通过 AskUserQuestion 向用户确认细节。',
    icon: '🧠',
    phase: 'planning',
    codeFiles: ['agents/planner.py', 'core/planner.py', 'prompts/planner_system.md'],
  },
  {
    id: 'kanban',
    title: 'Kanban Board',
    titleZh: '看板',
    description: 'Backlog → Planning → Todo → In Progress → Done',
    descriptionZh: 'Backlog → Planning → Todo → In Progress → Done',
    detail: 'A 7-column kanban board tracks every issue through its lifecycle. The Web UI supports drag-and-drop, real-time SSE updates, and an issue detail panel with live agent output. State transitions are strictly enforced by the state machine in models.py.',
    detailZh: '7 列看板追踪每个 Issue 的完整生命周期。Web UI 支持拖拽操作、SSE 实时更新和 Issue 详情面板（含实时 Agent 输出）。状态转换由 models.py 中的状态机严格控制。',
    icon: '📋',
    phase: 'kanban',
    codeFiles: ['core/models.py', 'web/src/components/Board.tsx'],
  },
  {
    id: 'scheduler',
    title: 'Scheduler',
    titleZh: '调度器',
    description: 'Assign unblocked issues to idle agents',
    descriptionZh: '将无阻塞 Issue 分配给空闲 Agent',
    detail: 'The scheduler polls for TODO issues where all blocked_by dependencies are human_done. It dispatches them to concurrent agents via asyncio.Semaphore, sorted by priority (urgent > high > medium > low). Configurable interval and max parallelism.',
    detailZh: '调度器轮询所有 blocked_by 依赖已完成（human_done）的 TODO Issue，按优先级排序（urgent > high > medium > low），通过 asyncio.Semaphore 分派给并发 Agent。支持配置轮询间隔和最大并行数。',
    icon: '⚡',
    phase: 'kanban',
    codeFiles: ['core/scheduler.py', 'core/ralph_loop.py → find_ready_issues()'],
  },
  {
    id: 'ralph',
    title: 'Ralph Agent',
    titleZh: 'Ralph Agent',
    description: 'Implement with build/test backpressure',
    descriptionZh: '实现代码 + build/test 反压',
    detail: 'Ralph is the generator agent. It receives the issue content + plan.md + AGENT.md + specs, then implements the solution using Read/Write/Edit/Bash/Glob/Grep tools. Runs in bypassPermissions mode. Build and tests must pass before proceeding — this is the backpressure mechanism.',
    detailZh: 'Ralph 是代码生成 Agent。它接收 Issue 内容 + plan.md + AGENT.md + specs，然后使用 Read/Write/Edit/Bash/Glob/Grep 工具实现方案。以 bypassPermissions 模式运行。构建和测试必须通过才能继续——这就是反压机制。',
    icon: '🔨',
    phase: 'execution',
    codeFiles: ['core/executor.py', 'agents/ralph_loop.py', 'prompts/ralph_prompt.md'],
  },
  {
    id: 'eval',
    title: 'Evaluator',
    titleZh: '评估器',
    description: 'Playwright + incremental code review',
    descriptionZh: 'Playwright + 增量代码审查',
    detail: 'The Evaluator starts a dev server, then uses Playwright via MCP to browse the running app. It outputs structured markers: [PASS] for met criteria, [FAIL] for issues (triggers Ralph retry), [NEW_ISSUE] for unrelated problems, and [PLAN_APPEND] for plan updates.',
    detailZh: '评估器启动开发服务器，通过 MCP 使用 Playwright 浏览运行中的应用。输出结构化标记：[PASS] 表示通过、[FAIL] 表示问题（触发 Ralph 重试）、[NEW_ISSUE] 表示无关问题、[PLAN_APPEND] 表示计划更新。',
    icon: '🔍',
    phase: 'execution',
    codeFiles: ['agents/evaluator.py', 'prompts/evaluator_system.md'],
  },
  {
    id: 'evidence',
    title: 'Evidence Collection',
    titleZh: '证据收集',
    description: 'Git diff + build output + screenshots',
    descriptionZh: 'Git diff + 构建输出 + 截图',
    detail: 'After the agent completes work, evidence is automatically collected: git diff HEAD~1 --stat, git log -1 --oneline, npm run build output, and Playwright screenshots. All evidence is appended to the issue\'s content.md as a structured Markdown block.',
    detailZh: 'Agent 完成工作后，自动收集证据：git diff HEAD~1 --stat、git log -1 --oneline、npm run build 输出和 Playwright 截图。所有证据以结构化 Markdown 块追加到 Issue 的 content.md 中。',
    icon: '📸',
    phase: 'execution',
    codeFiles: ['core/evidence.py'],
  },
  {
    id: 'agent-done',
    title: 'Agent Done',
    titleZh: 'Agent Done',
    description: 'Awaiting human review',
    descriptionZh: '等待人类审核',
    detail: 'The issue moves to agent_done status with all evidence attached. The Web UI shows the complete diff, build output, screenshots, and agent conversation log. The issue is now waiting for a human to review and approve or reject.',
    detailZh: 'Issue 进入 agent_done 状态，附带所有证据。Web UI 展示完整的 diff、构建输出、截图和 Agent 对话日志。Issue 现在等待人类审核通过或拒绝。',
    icon: '✅',
    phase: 'review',
    codeFiles: ['core/ralph_loop.py → run_issue_loop()'],
  },
  {
    id: 'human-review',
    title: 'Human Review',
    titleZh: '人类审核',
    description: 'Approve or Reject with feedback',
    descriptionZh: 'Approve 或 Reject 并附反馈',
    detail: 'The human reviews the evidence and either approves (→ human_done, unblocks dependents) or rejects with feedback (→ todo, feedback appended to content.md for the agent\'s next attempt). This is the quality gate — no issue closes without human sign-off.',
    detailZh: '人类审核证据后，可以通过（→ human_done，解锁依赖 Issue）或拒绝并附反馈（→ todo，反馈追加到 content.md 供 Agent 下次参考）。这是质量门控——没有人类签字，Issue 不会关闭。',
    icon: '👤',
    phase: 'review',
    codeFiles: ['core/review.py', 'server/routes/reviews.py'],
  },
  {
    id: 'human-done',
    title: 'Human Done',
    titleZh: 'Human Done',
    description: 'Complete — unblock dependents',
    descriptionZh: '完成 — 解锁依赖 Issue',
    detail: 'Terminal state. The issue is complete and all issues that had this issue in their blocked_by list are now unblocked. The scheduler will automatically pick them up in the next poll cycle if they have no remaining blockers.',
    detailZh: '终态。Issue 完成，所有在 blocked_by 中依赖此 Issue 的 Issue 现在被解锁。如果没有其他阻塞项，调度器会在下一个轮询周期自动领取它们。',
    icon: '🎉',
    phase: 'done',
    codeFiles: ['core/models.py → VALID_TRANSITIONS'],
  },
];

// --- Notes ---

const notes: NoteDef[] = [
  {
    id: 'note-parallel',
    text: 'Multiple agents run in\nparallel on independent\nissues — no waiting.',
    textZh: '多个 Agent 可并行执行\n无依赖的 Issue\n无需等待',
    appearsWithStep: 4,
    phase: 'kanban',
  },
  {
    id: 'note-backpressure',
    text: 'Build/test must pass\nbefore moving forward.\nFailed → auto-retry.',
    textZh: '构建/测试必须通过\n才能继续推进\n失败 → 自动重试',
    appearsWithStep: 5,
    phase: 'execution',
  },
  {
    id: 'note-reject',
    text: 'Rejected issues return\nto Todo with feedback\nappended — agents retry.',
    textZh: '被拒绝的 Issue 带着反馈\n打回 Todo\nAgent 重新执行',
    appearsWithStep: 9,
    phase: 'review',
  },
];

// --- Positions (branching layout) ---

const positions: Record<string, { x: number; y: number }> = {
  'requirement':   { x: 400, y: 0 },
  'planner':       { x: 400, y: 130 },
  'kanban':        { x: 400, y: 270 },
  'scheduler':     { x: 400, y: 400 },
  'ralph':         { x: 520, y: 530 },
  'eval':          { x: 520, y: 660 },
  'evidence':      { x: 520, y: 790 },
  'agent-done':    { x: 400, y: 920 },
  'human-review':  { x: 400, y: 1050 },
  'human-done':    { x: 400, y: 1180 },
  'note-parallel':    { x: 730, y: 370 },
  'note-backpressure':{ x: 180, y: 580 },
  'note-reject':      { x: 100, y: 1020 },
};

// --- Edges ---

const edgeDefs: { source: string; target: string; label?: string; labelZh?: string; animated?: boolean; style?: React.CSSProperties; type?: string }[] = [
  { source: 'requirement', target: 'planner' },
  { source: 'planner', target: 'kanban', label: 'Issues created', labelZh: '创建 Issue' },
  { source: 'kanban', target: 'scheduler' },
  { source: 'scheduler', target: 'ralph', label: 'Dispatch', labelZh: '分派' },
  { source: 'ralph', target: 'eval', label: 'Build passes', labelZh: '构建通过', animated: true },
  { source: 'eval', target: 'evidence' },
  { source: 'evidence', target: 'agent-done' },
  { source: 'agent-done', target: 'human-review' },
  { source: 'human-review', target: 'human-done', label: 'Approve', labelZh: '通过', style: { stroke: '#4ade80' } },
  { source: 'human-review', target: 'kanban', label: 'Reject', labelZh: '拒绝', style: { stroke: '#f87171' }, type: 'reject' },
];

// --- Custom Node Components ---

interface CustomNodeData {
  title: string;
  description: string;
  icon: string;
  phase: Phase;
  selected?: boolean;
  [key: string]: unknown;
}

function CustomNode({ data }: { data: CustomNodeData }) {
  const colors = phaseColors[data.phase];
  return (
    <div
      className={`custom-node ${data.selected ? 'node-selected' : ''}`}
      style={{
        background: colors.bg,
        border: `1.5px solid ${data.selected ? '#fff' : colors.border}`,
      }}
    >
      <Handle type="target" position={Position.Top} id="top" style={{ background: colors.border, border: `1.5px solid ${colors.border}` }} />
      <Handle type="target" position={Position.Left} id="left" style={{ background: colors.border, border: `1.5px solid ${colors.border}` }} />
      <div className="node-content">
        <div className="node-icon">{data.icon}</div>
        <div className="node-title" style={{ color: data.selected ? '#fff' : colors.text }}>{data.title}</div>
        <div className="node-description">{data.description}</div>
      </div>
      <Handle type="source" position={Position.Bottom} id="bottom" style={{ background: colors.border, border: `1.5px solid ${colors.border}` }} />
      <Handle type="source" position={Position.Right} id="right" style={{ background: colors.border, border: `1.5px solid ${colors.border}` }} />
    </div>
  );
}

interface NoteNodeData {
  text: string;
  phase: Phase;
  [key: string]: unknown;
}

function NoteNode({ data }: { data: NoteNodeData }) {
  const colors = phaseColors[data.phase];
  return (
    <div className="note-node" style={{ borderColor: colors.border + '66' }}>
      <pre>{data.text}</pre>
    </div>
  );
}

const nodeTypes: NodeTypes = {
  custom: CustomNode,
  note: NoteNode,
};

// --- Detail Panel ---

function DetailPanel({ step, lang, onClose }: { step: StepDef; lang: Lang; onClose: () => void }) {
  const colors = phaseColors[step.phase];
  const title = lang === 'zh' ? step.titleZh : step.title;
  const detail = lang === 'zh' ? step.detailZh : step.detail;

  return (
    <div className="detail-panel" style={{ borderColor: colors.border }}>
      <div className="detail-header">
        <div className="detail-title-row">
          <span className="detail-icon">{step.icon}</span>
          <span className="detail-title" style={{ color: colors.text }}>{title}</span>
          <span className="detail-phase-badge" style={{ background: colors.border + '22', color: colors.text, borderColor: colors.border }}>
            {phaseLabels[lang][step.phase]}
          </span>
        </div>
        <button className="detail-close" onClick={onClose} aria-label="Close">×</button>
      </div>
      <div className="detail-body">
        <p className="detail-text">{detail}</p>
        {step.codeFiles && step.codeFiles.length > 0 && (
          <div className="detail-files">
            <div className="detail-files-label">{lang === 'zh' ? '相关代码' : 'Source files'}</div>
            {step.codeFiles.map((f, i) => (
              <code key={i} className="detail-file">{f}</code>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// --- Helpers ---

function createNode(step: StepDef, index: number, visibleCount: number, lang: Lang, selectedId: string | null): Node {
  const visible = index < visibleCount;
  const pos = positions[step.id];
  return {
    id: step.id,
    type: 'custom',
    position: pos,
    data: {
      title: lang === 'zh' ? step.titleZh : step.title,
      description: lang === 'zh' ? step.descriptionZh : step.description,
      icon: step.icon,
      phase: step.phase,
      selected: step.id === selectedId,
    },
    style: {
      opacity: visible ? 1 : 0,
      transition: 'opacity 0.5s ease-in-out',
      pointerEvents: visible ? 'all' as const : 'none' as const,
      cursor: visible ? 'pointer' : 'default',
    },
    draggable: true,
    selectable: visible,
  };
}

function createNoteNode(note: NoteDef, visibleCount: number, lang: Lang): Node {
  const visible = visibleCount > note.appearsWithStep;
  const pos = positions[note.id];
  return {
    id: note.id,
    type: 'note',
    position: pos,
    data: {
      text: lang === 'zh' ? note.textZh : note.text,
      phase: note.phase,
    },
    style: {
      opacity: visible ? 1 : 0,
      transition: 'opacity 0.5s ease-in-out',
      pointerEvents: visible ? 'all' as const : 'none' as const,
    },
    draggable: true,
    selectable: false,
    connectable: false,
  };
}

function createEdge(def: typeof edgeDefs[0], visibleCount: number, lang: Lang): Edge {
  const sourceIdx = allSteps.findIndex(s => s.id === def.source);
  const targetIdx = allSteps.findIndex(s => s.id === def.target);
  const visible = sourceIdx < visibleCount && targetIdx < visibleCount;

  const isRejectEdge = def.type === 'reject';
  const label = lang === 'zh' ? (def.labelZh || def.label) : def.label;

  return {
    id: `${def.source}-${def.target}`,
    source: def.source,
    target: def.target,
    sourceHandle: isRejectEdge ? 'right' : 'bottom',
    targetHandle: isRejectEdge ? 'left' : 'top',
    type: 'smoothstep',
    animated: def.animated && visible,
    label: visible ? label : undefined,
    labelStyle: { fill: '#888', fontSize: 12, fontWeight: 500 },
    labelBgStyle: { fill: '#0a0a0a', fillOpacity: 0.9 },
    labelBgPadding: [6, 4] as [number, number],
    labelBgBorderRadius: 4,
    markerEnd: { type: MarkerType.ArrowClosed, color: def.style?.stroke || '#444' },
    style: {
      stroke: def.style?.stroke || '#444',
      strokeWidth: 2,
      opacity: visible ? 1 : 0,
      transition: 'opacity 0.5s ease-in-out',
    },
  };
}

// --- App ---

export default function App() {
  const [visibleCount, setVisibleCount] = useState(1);
  const [lang, setLang] = useState<Lang>('en');
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const nodePositionsRef = useRef<Record<string, { x: number; y: number }>>({});

  const selectedStep = selectedStepId ? allSteps.find(s => s.id === selectedStepId) ?? null : null;

  const getNodes = useCallback((count: number): Node[] => {
    const stepNodes = allSteps.map((step, i) => {
      const node = createNode(step, i, count, lang, selectedStepId);
      if (nodePositionsRef.current[step.id]) {
        node.position = nodePositionsRef.current[step.id];
      }
      return node;
    });
    const noteNodes = notes.map(note => {
      const node = createNoteNode(note, count, lang);
      if (nodePositionsRef.current[note.id]) {
        node.position = nodePositionsRef.current[note.id];
      }
      return node;
    });
    return [...stepNodes, ...noteNodes];
  }, [lang, selectedStepId]);

  const getEdges = useCallback((count: number): Edge[] => {
    return edgeDefs.map(def => createEdge(def, count, lang));
  }, [lang]);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    for (const change of changes) {
      if (change.type === 'position' && change.position) {
        nodePositionsRef.current[change.id] = change.position;
      }
    }
    setVisibleCount(c => c);
    void applyNodeChanges;
  }, []);

  const onEdgesChange = useCallback((_changes: EdgeChange[]) => {
    void applyEdgeChanges;
  }, []);

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    // Only handle step nodes, not note nodes
    const step = allSteps.find(s => s.id === node.id);
    if (step) {
      setSelectedStepId(prev => prev === node.id ? null : node.id);
    }
  }, []);

  const handleNext = () => setVisibleCount(c => Math.min(c + 1, allSteps.length));
  const handlePrev = () => setVisibleCount(c => Math.max(c - 1, 1));
  const handleReset = () => {
    setVisibleCount(1);
    setSelectedStepId(null);
    nodePositionsRef.current = {};
  };
  const handleShowAll = () => setVisibleCount(allSteps.length);

  const nodes = getNodes(visibleCount);
  const edges = getEdges(visibleCount);

  const titles = {
    en: { h1: 'How ', brand: 'Ekko', h1end: ' Works', subtitle: 'Step through the architecture — click any node for details' },
    zh: { h1: '', brand: 'Ekko', h1end: ' 工作原理', subtitle: '逐步展示架构 — 点击任意节点查看详情' },
  };

  const t = titles[lang];

  const currentStep = visibleCount > 0 ? allSteps[Math.min(visibleCount - 1, allSteps.length - 1)] : null;
  const currentPhase = currentStep?.phase;

  return (
    <div className="app-container">
      <a href="https://github.com/HuangZiy/ekko" className="github-link" target="_blank" rel="noopener noreferrer">
        GitHub ↗
      </a>

      <div className="header">
        <h1>{t.h1}<span>{t.brand}</span>{t.h1end}</h1>
        <p>{t.subtitle}</p>
        <div className="lang-toggle">
          <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
          <button className={lang === 'zh' ? 'active' : ''} onClick={() => setLang('zh')}>中文</button>
        </div>
      </div>

      <div className="main-area">
        <div className="flow-container">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            minZoom={0.3}
            maxZoom={1.5}
            defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1a1a1a" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>

        {selectedStep && (
          <DetailPanel
            step={selectedStep}
            lang={lang}
            onClose={() => setSelectedStepId(null)}
          />
        )}
      </div>

      {/* Phase Legend */}
      <div className="phase-legend">
        {(Object.keys(phaseColors) as Phase[]).map(phase => (
          <div
            key={phase}
            className={`phase-item ${currentPhase === phase ? 'active' : ''}`}
            style={{ borderColor: phaseColors[phase].border }}
          >
            <span className="phase-dot" style={{ background: phaseColors[phase].border }} />
            <span className="phase-label">{phaseLabels[lang][phase]}</span>
          </div>
        ))}
      </div>

      <div className="controls">
        <button onClick={handlePrev} disabled={visibleCount <= 1}>
          ← Previous
        </button>
        <span className="step-counter">
          {visibleCount} / {allSteps.length}
        </span>
        <button onClick={handleNext} disabled={visibleCount >= allSteps.length}>
          Next →
        </button>
        <button className="secondary-btn" onClick={handleShowAll} disabled={visibleCount >= allSteps.length}>
          Show All
        </button>
        <button className="secondary-btn" onClick={handleReset} disabled={visibleCount === 1 && !selectedStepId}>
          Reset
        </button>
      </div>
    </div>
  );
}
