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
  icon: string;
  phase: Phase;
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
    icon: '💬',
    phase: 'input',
  },
  {
    id: 'planner',
    title: 'Planner Agent',
    titleZh: 'Planner Agent',
    description: 'Brainstorm → specs + dependency-aware Issues',
    descriptionZh: '交互式 brainstorming → specs + 带依赖的 Issue',
    icon: '🧠',
    phase: 'planning',
  },
  {
    id: 'kanban',
    title: 'Kanban Board',
    titleZh: '看板',
    description: 'Backlog → Planning → Todo → In Progress → Done',
    descriptionZh: 'Backlog → Planning → Todo → In Progress → Done',
    icon: '📋',
    phase: 'kanban',
  },
  {
    id: 'scheduler',
    title: 'Scheduler',
    titleZh: '调度器',
    description: 'Assign unblocked issues to idle agents',
    descriptionZh: '将无阻塞 Issue 分配给空闲 Agent',
    icon: '⚡',
    phase: 'kanban',
  },
  {
    id: 'ralph',
    title: 'Ralph Agent',
    titleZh: 'Ralph Agent',
    description: 'Implement with build/test backpressure',
    descriptionZh: '实现代码 + build/test 反压',
    icon: '🔨',
    phase: 'execution',
  },
  {
    id: 'eval',
    title: 'Evaluator',
    titleZh: '评估器',
    description: 'Playwright + incremental code review',
    descriptionZh: 'Playwright + 增量代码审查',
    icon: '🔍',
    phase: 'execution',
  },
  {
    id: 'evidence',
    title: 'Evidence Collection',
    titleZh: '证据收集',
    description: 'Git diff + build output + screenshots',
    descriptionZh: 'Git diff + 构建输出 + 截图',
    icon: '📸',
    phase: 'execution',
  },
  {
    id: 'agent-done',
    title: 'Agent Done',
    titleZh: 'Agent Done',
    description: 'Awaiting human review',
    descriptionZh: '等待人类审核',
    icon: '✅',
    phase: 'review',
  },
  {
    id: 'human-review',
    title: 'Human Review',
    titleZh: '人类审核',
    description: 'Approve or Reject with feedback',
    descriptionZh: 'Approve 或 Reject 并附反馈',
    icon: '👤',
    phase: 'review',
  },
  {
    id: 'human-done',
    title: 'Human Done',
    titleZh: 'Human Done',
    description: 'Complete — unblock dependents',
    descriptionZh: '完成 — 解锁依赖 Issue',
    icon: '🎉',
    phase: 'done',
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
  // Main flow — slight zigzag for visual interest
  'requirement':   { x: 400, y: 0 },
  'planner':       { x: 400, y: 130 },
  'kanban':        { x: 400, y: 270 },
  'scheduler':     { x: 400, y: 400 },
  // Execution branch — shifts right
  'ralph':         { x: 520, y: 530 },
  'eval':          { x: 520, y: 660 },
  'evidence':      { x: 520, y: 790 },
  // Review branch — shifts left
  'agent-done':    { x: 400, y: 920 },
  'human-review':  { x: 400, y: 1050 },
  'human-done':    { x: 400, y: 1180 },
  // Notes
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
  [key: string]: unknown;
}

function CustomNode({ data }: { data: CustomNodeData }) {
  const colors = phaseColors[data.phase];
  return (
    <div
      className="custom-node"
      style={{
        background: colors.bg,
        border: `1.5px solid ${colors.border}`,
      }}
    >
      <Handle type="target" position={Position.Top} id="top" style={{ background: colors.border, border: `1.5px solid ${colors.border}` }} />
      <Handle type="target" position={Position.Left} id="left" style={{ background: colors.border, border: `1.5px solid ${colors.border}` }} />
      <div className="node-content">
        <div className="node-icon">{data.icon}</div>
        <div className="node-title" style={{ color: colors.text }}>{data.title}</div>
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

// --- Helpers ---

function createNode(step: StepDef, index: number, visibleCount: number, lang: Lang): Node {
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
    },
    style: {
      opacity: visible ? 1 : 0,
      transition: 'opacity 0.5s ease-in-out',
      pointerEvents: visible ? 'all' as const : 'none' as const,
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
  const nodePositionsRef = useRef<Record<string, { x: number; y: number }>>({});

  const getNodes = useCallback((count: number): Node[] => {
    const stepNodes = allSteps.map((step, i) => {
      const node = createNode(step, i, count, lang);
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
  }, [lang]);

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

  const handleNext = () => setVisibleCount(c => Math.min(c + 1, allSteps.length));
  const handlePrev = () => setVisibleCount(c => Math.max(c - 1, 1));
  const handleReset = () => {
    setVisibleCount(1);
    nodePositionsRef.current = {};
  };
  const handleShowAll = () => setVisibleCount(allSteps.length);

  const nodes = getNodes(visibleCount);
  const edges = getEdges(visibleCount);

  const titles = {
    en: { h1: 'How ', brand: 'Ekko', h1end: ' Works', subtitle: 'Step through the architecture — click Next to reveal each stage' },
    zh: { h1: '', brand: 'Ekko', h1end: ' 工作原理', subtitle: '逐步展示架构 — 点击 Next 查看每个阶段' },
  };

  const t = titles[lang];

  // Determine current phase for the legend highlight
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

      <div className="flow-container">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
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
        <button className="secondary-btn" onClick={handleReset} disabled={visibleCount === 1}>
          Reset
        </button>
      </div>
    </div>
  );
}
