构建成功，零错误。

总结一下改了什么：

**根因**：`.tags` 容器设了固定 `height: 28px` + `overflow: hidden`，标签多的时候超出一行的都被裁掉了。同时 Masonry 瀑布流的高度预计算也写死了 `TAGS_HEIGHT = 28`。

**修复**（4 个文件）：

1. `ArticleCard.module.css` — 移除 `.tags` 的固定高度和 `overflow: hidden`，让标签自然换行
2. `ArticleCard.tsx` — 新增 `computeTagsHeight()` 函数，用 Pretext `walkLineRanges()` 测量每个标签文字宽度，模拟 CSS flex-wrap 计算实际行数和高度；`computeCardHeight()` 的第三个参数从 `hasTags: boolean` 改为 `tagsHeight: number`
3. `MasonryGrid.tsx` — 调用 `computeTagsHeight()` 传入实际标签高度，保证瀑布流预计算与 CSS 渲染一致
4. `lib/pretext/fonts.ts` + `index.ts` — 新增 `FONT_TAG` 常量（`12px Inter`），匹配 CSS 中标签的字体