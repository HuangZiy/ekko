## 评估报告

---

### 设计质量: 7/10

- [PASS] 配色体系：使用 CSS custom properties 定义完整的 design tokens（`tokens.css`），light/dark 两套配色，色彩克制——暖灰底色 `#FAFAF8`、深色 `#141414`，没有紫色渐变等 AI 生成典型模式
- [PASS] 排版系统：完整的 type scale（xs→4xl），三套字体族（sans/serif/mono），包含中文字体 Noto Sans SC / Noto Serif SC，间距系统 4px 递增
- [PASS] 暗色模式：切换流畅，按钮标签正确更新（"切换到亮色模式" ↔ "切换到暗色模式"），`body` 上有 `transition: color 0.2s, background-color 0.2s`，无闪烁（anti-flash inline script）
- [PASS] 动画有意义：Framer Motion 页面过渡、卡片入场渐显、手风琴展开，全部尊重 `prefers-reduced-motion`（`useReducedMotion` hook + CSS media query）
- [MINOR] 整体设计偏保守——干净但缺少强烈的视觉个性。卡片、页面布局都是标准博客模式，没有特别突出的原创设计决策
- [MINOR] 首页 hero 区域仅有标题 + 副标题，视觉层次略单薄

---

### Pretext 排版质量: 8/10

- [PASS] 文章页文字环绕：`PretextFloatClient.tsx` 使用 `prepareWithSegments()` + `layoutNextLine()` 实现逐行布局，`getWidthAtY()` 根据图片区域动态缩窄行宽，文字真正环绕图片流动
- [PASS] 首页 masonry 瀑布流：`MasonryGrid.tsx` 直接调用 `prepare()` + `layout()` 和 `prepareWithSegments()` + `walkLineRanges()` 预测量每张卡片高度，绝对定位实现零布局抖动的瀑布流
- [PASS] 摘要卡片 shrink-wrap：`ArticleCard.tsx` 使用 `useShrinkWrap()` hook（内部调用 `walkLineRanges()`）计算标题最小宽度，`maxWidth` 设为 shrunk width
- [PASS] 归档手风琴预测量：`ArchiveClient.tsx` 使用 `useTextLayout()` hook（`prepare()` + `layout()`）预测量展开内容高度，传给 Framer Motion `animate={{ height: estimatedHeight }}`，实现流畅展开动画
- [PASS] 代码内联混合字体：`useRichInline.ts` 实现了完整的 Canvas 2D fallback（因 `prepareRichInline` 在 v0.0.4 中尚不可用），包含 tokenization、baseline alignment、greedy line-breaking
- [PASS] 无 DOM 测量：`grep getBoundingClientRect|offsetHeight` 在整个源码中零匹配，所有文字测量通过 Pretext 或 Canvas 2D 完成
- [PASS] resize 时只调 `layout()` 不调 `prepare()`：hooks 中 `prepared` 通过 `useMemo` 缓存在 `[text, font, cacheGeneration]` 上，layout 单独 memo 在 `[prepared, width]` 上
- [PASS] `PretextProvider` 在 `document.fonts.ready` 后调用 `clearCache()` 并 bump `cacheGeneration`，触发所有 hooks 重新测量
- [MINOR] `useRichInline` 是 Canvas 2D fallback 而非真正的 Pretext API 调用——这是 v0.0.4 的限制，代码中有明确注释说明，设计合理但严格来说不算"使用 Pretext API"

---

### 功能完整性: 7/10

- [PASS] 文章列表：首页 masonry grid 展示所有文章，带 "Load More" 分页
- [PASS] 文章详情页：标题、日期、分类、阅读时间、MDX 渲染、标签、上/下篇导航
- [PASS] 分类页：分类索引（显示计数）+ 分类详情（文章列表 + 返回链接）
- [PASS] 标签页：标签索引（5 个标签，显示计数）+ 标签详情页
- [PASS] 归档页：按年分组手风琴，默认展开最新年份，日期 + 标题 + 分类链接
- [PASS] 搜索：全屏 modal，200ms debounce，MiniSearch + CJK tokenizer，`<mark>` 高亮，↑↓/Enter/Esc 键盘导航，ARIA combobox/listbox 模式
- [PASS] i18n：中/英双语，URL 路由 `/zh/...` `/en/...`，locale 切换链接正确指向对应语言页面
- [PASS] MDX 渲染：代码高亮（rehype-pretty-code，双主题）、Callout 组件、FloatImage 组件、行号
- [PASS] RSS feed：`/feed.xml` 路由存在
- [PASS] SEO：`robots.ts` + `sitemap.ts` 生成
- [FAIL] 控制台 hydration 错误：文章页 `PretextFloat` 组件产生 `<p>` 嵌套 `<p>` 的 hydration error（3 个错误）→ **修复建议**：`PretextFloat.tsx` 第 98 行和第 120 行的 `<p className={styles.fallbackText}>{children}</p>` 中，`children` 来自 MDX 可能包含 `<p>` 标签。应改为 `<div>` 避免嵌套 `<p>`

---

### 交互体验 + 代码质量: 8/10

- [PASS] 导航流畅：页面间跳转有 Framer Motion 过渡动画，`template.tsx` 包裹页面级动画
- [PASS] 响应式布局：375px 移动端有 hamburger 菜单（dialog 模式 + 关闭按钮），768px 平板适配，1280px 桌面三栏 masonry。断点设计合理（640/960）
- [PASS] 可访问性：skip-to-content 链接、ARIA landmarks（nav/main/contentinfo）、`aria-expanded` 手风琴、combobox 搜索、focus trap（`useFocusTrap`）、`aria-hidden` 装饰性 SVG、`prefers-reduced-motion` 全面支持
- [PASS] TypeScript 类型严格：所有组件有明确的 interface 定义，Zod schema 验证 frontmatter，无 `any` 类型
- [PASS] 组件结构合理：清晰的目录分层（components/article、card、layout、mdx、search、ui），lib 层分离（pretext、content、i18n、search）
- [PASS] `npm run build` 零错误通过：TypeScript 编译通过，33 个静态页面成功生成，prebuild 脚本生成搜索索引
- [PASS] SSR/CSR 分离得当：Pretext 组件用 `next/dynamic` + `ssr: false`，SSR 有 CSS grid/float fallback
- [FAIL] 控制台有 hydration 错误（2 error + 1 warning on article page）→ 同上，`<p>` 嵌套问题
- [MINOR] build 有一个 Next.js workspace root warning（多 lockfile 检测），非阻塞但应清理

---

### 总结

**通过** — 加权总分 7.5/10，四个维度均达到 ≥7 阈值。

关键修复项：
1. `PretextFloat.tsx` 的 SSR fallback 和 mobile fallback 中 `<p className={styles.fallbackText}>{children}</p>` 导致 `<p>` 嵌套 hydration error — 改为 `<div>` 即可修复

整体评价：这是一个架构扎实的博客应用。Pretext 集成是真实的、深度的——5 个自定义 hooks 覆盖了 prepare/layout/walkLineRanges/layoutNextLine 全套 API，零 DOM 测量，resize 时正确地只重新 layout。代码质量高，可访问性考虑周全，i18n 完整。主要扣分点在于设计原创性偏保守和 hydration 错误。