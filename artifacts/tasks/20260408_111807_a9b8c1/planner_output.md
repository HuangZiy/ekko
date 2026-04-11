已完成分析和规格文件创建。总结一下：

**根因定位**：卡片标题的 `line-height: 21px` 配 `font-size: 18px`，行高比只有 1.17，对中文多行标题来说太紧凑。再加上卡片用固定高度 + `overflow: hidden`，Pretext 测量的任何偏差都会导致文字被裁切。

**已创建的文件**：
- `specs/homepage-text-fix.md` — 详细的修复规格，包含 3 个修复点和验收标准
- `fix_plan.md` — 已更新，按依赖顺序列出修复步骤

**修复方案（3 步）**：
1. `fonts.ts` 新增 `LINE_HEIGHT.cardTitle = 25`，同步更新 CSS 和组件计算
2. `computeCardHeight()` 增加 +4px 安全余量
3. `.card` 的 `overflow: hidden` 仅保留在 `.summary` 上

`AGENT.md` 的更新因权限问题未写入，需要你授权后重试。要我现在继续更新 AGENT.md 吗？