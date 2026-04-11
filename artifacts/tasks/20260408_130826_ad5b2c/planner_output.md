分析完成。卡片标签的问题定位到 4 个根因：垂直 padding 太小（2px）、背景色几乎透明（accent 8%）、缺少边框、与 `/tags` 页面标签风格不一致。

已创建/更新以下文件：

- `specs/card-tag-style-fix.md` — 完整的修复规格，包含根因分析、4 个修复方案、验收标准、Pretext 常量同步说明和目标 CSS 参考
- `fix_plan.md` — 按依赖排序的 6 步实现计划（CSS 改动 → Pretext 常量同步 → 4 项验证）
- `AGENT.md` — 新增了 `card-tag-style-fix.md` 和 `homepage-text-fix.md` 的规格索引条目

核心改动很聚焦：只需改 `ArticleCard.module.css`（padding/background/border）和 `ArticleCard.tsx`（`TAG_PILL_HEIGHT` 16→22, `TAG_H_PADDING` 20→26），masonry 布局逻辑无需修改。