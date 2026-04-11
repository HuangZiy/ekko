# Blog Harness

基于 Claude Agent SDK 的三阶段自动化博客构建套件。结合 Anthropic 三 Agent 架构（Planner → Generator → Evaluator）和 Ralph Wiggum 循环技术，从一句话需求自动生成完整的 Next.js + MDX + Pretext 技术博客。

## 灵感来源

- [Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps) — Anthropic 三 Agent 架构（Planner / Generator / Evaluator）
- [Ralph Wiggum technique](https://ghuntley.com/ralph/) — `while :; do cat PROMPT.md | claude ; done` 单任务循环、fix_plan 状态传递、build/test backpressure
- [Superpowers Brainstorming](https://github.com/obra/superpowers) — Planner 的结构化头脑风暴流程
- [@chenglou/pretext](https://github.com/chenglou/pretext) — 纯 JS 文本测量与布局引擎，博客的核心排版能力

## 架构

```
User Prompt ("创建一个极简技术博客")
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 1: Planner                                        │
│   brainstorming → specs/*.md + fix_plan.md + AGENT.md   │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 2: Build + Evaluate Loop                          │
│                                                         │
│   while has_work() and loop < MAX:                      │
│     1. Ralph: 从 fix_plan.md 取 1 项 → 实现 → build →  │
│              test → git commit                          │
│     2. Evaluator: Playwright 浏览页面 → 四维度打分       │
│     3. 全部 ≥7/10 → break                              │
│     4. 否则 → FAIL 项追加到 fix_plan.md → 继续          │
│                                                         │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 3: README                                         │
│   读取实际代码生成项目 README.md                          │
└──────────────────────────┬──────────────────────────────┘
                           ▼
                    Summary 统计汇总
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行（一句话描述你想要的博客）
python harness.py "创建一个极简风格的技术博客，支持中英文"
```

生成的博客源码在 `workspace/`，评估报告和截图在 `artifacts/`。

## 项目结构

```
blog-harness/
├── harness.py                 # 主入口 — 三阶段编排 + 统计汇总
├── config.py                  # 全局配置（模型、循环次数、预算、阈值）
├── requirements.txt           # claude-agent-sdk, anyio
│
├── agents/                    # Agent 模块
│   ├── planner.py             # Phase 1: Brainstorming → specs + fix_plan
│   ├── ralph_loop.py          # Phase 2: Ralph Loop（每轮 1 任务 + backpressure）
│   └── evaluator.py           # Phase 2: Playwright QA 四维度评估
│
├── prompts/                   # 系统提示词（可独立调优）
│   ├── planner_system.md      # Planner 角色 + Brainstorming 流程 + Pretext API 速查
│   ├── ralph_prompt.md        # Ralph 每轮 prompt（技术栈 + Pretext 指南 + 规则）
│   ├── evaluator_system.md    # Evaluator 角色 + 评估流程 + Pretext 验证
│   └── eval_criteria.md       # 四维度评估标准（设计/Pretext排版/功能/交互）
│
├── workspace/                 # 生成的 Blog 源码（Ralph 的工作目录）
│   ├── app/                   # Next.js App Router 页面
│   ├── components/            # React 组件
│   ├── lib/                   # Pretext hooks、内容 API 等
│   ├── content/               # MDX 文章
│   ├── styles/                # CSS Modules
│   ├── specs/                 # Planner 生成的功能规格
│   ├── fix_plan.md            # Ralph 的 TODO 列表（只保留待办项）
│   └── AGENT.md               # Ralph 自维护的构建指南
│
└── artifacts/                 # Harness 产出物（不混入项目源码）
    ├── screenshots/           # Evaluator 的 Playwright 截图
    ├── eval_cycle_*.md        # 每轮评估报告
    ├── harness_summary.txt    # 运行汇总（纯文本）
    ├── harness_stats.json     # 运行统计（机器可读）
    └── planner_output.md      # Planner 输出摘要
```

## 配置

编辑 `config.py`：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MODEL` | `claude-opus-4-6` | Claude 模型 |
| `MAX_RALPH_LOOPS` | `30` | 最大循环次数 |
| `MAX_TURNS_PER_LOOP` | `150` | 每轮 Ralph 最大 agent turns |
| `MAX_BUDGET_PER_LOOP` | `5.0` | 每轮 Ralph 最大花费 (USD) |
| `EVAL_PASS_THRESHOLD` | `7` | 评估通过阈值（每维度 ≥ X/10） |
| `MAX_PLANNER_TURNS` | `50` | Planner 最大 turns |

## 评估标准

Evaluator 使用 Playwright MCP 实际浏览页面，按四个维度打分：

| 维度 | 权重 | 评估内容 |
|------|------|----------|
| 设计质量 | 25% | 视觉一致性、暗色模式、动画、原创性 |
| Pretext 排版质量 | 25% | 文字环绕、masonry 预测量、shrink-wrap、手风琴、rich-inline |
| 功能完整性 | 25% | 对照 specs 逐项验证，功能必须可用非 stub |
| 交互体验 + 代码质量 | 25% | 响应式、可访问性、TypeScript 严格、build 通过 |

所有维度 ≥ 7/10 才算通过。未通过的 FAIL 项自动追加到 fix_plan.md 触发下一轮修复。

## Ralph Loop 核心机制

每轮循环遵循 Ralph Wiggum 技术：

1. **Context Reset** — 每轮全新 context window，不用 compaction
2. **确定性栈分配** — 每轮加载相同的 specs + fix_plan + AGENT.md
3. **单任务** — 每轮只从 fix_plan.md 取第一个 `- [ ]` 项
4. **Backpressure** — `npm run build` 必须通过才能 commit
5. **自我改进** — Ralph 更新 AGENT.md 记录构建经验
6. **fix_plan 只保留待办** — 已完成项自动清理，评估反馈只提取 FAIL 项

## 运行日志

Harness 输出彩色日志：

```
[Task]      当前处理的任务（青色）
[Ralph]     Ralph agent 的文本输出（青色）
[Evaluator] Evaluator agent 的文本输出（紫色）
[Tool]      工具调用 — 名称 + 缩略参数（黄色）
[Result]    工具执行结果（绿色/红色）
[Done]      完成摘要 — turns、cost、duration（绿色）
[Eval]      Evaluator 状态（dev server 启停）
```

运行结束后输出统计汇总表：

```
======================================================================
  SUMMARY
======================================================================
  #1  Ralph       添加分类归档页                    $2.96    7m6s  turns=58
  #1  Evaluator                                     $4.91   10m53s  turns=113
  #2  Ralph       SSR masonry CLS 修复              $1.42    4m13s  turns=30
  #2  Evaluator                                     $4.45    9m52s  turns=98
  --------------------------------------------------------------------
  Total cost: $18.39  API time: 44m3s  Wall: 44m52s  Tokens: in=2,861,615 out=107,851
```

## 调优提示词

所有系统提示词在 `prompts/` 目录下，可独立编辑调优：

- **Planner 不够有野心？** → 编辑 `planner_system.md` 的功能范围描述
- **Ralph 做了占位符实现？** → 强化 `ralph_prompt.md` 底部的 "DO NOT IMPLEMENT PLACEHOLDER" 规则
- **Evaluator 太宽容？** → 调高 `eval_criteria.md` 的阈值或增加扣分项
- **Evaluator 太严格？** → 降低 `config.py` 的 `EVAL_PASS_THRESHOLD`

## 已知限制

- Evaluator 每轮花费约 $4-5（启动 Playwright 浏览所有页面 + 读全部源码），占总成本 ~75%
- `@chenglou/pretext` v0.0.4 缺少 `prepareRichInline` API，内联代码排版使用 Canvas 2D fallback
