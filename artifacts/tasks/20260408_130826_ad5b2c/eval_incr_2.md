两张卡片的 `scrollHeight === clientHeight`，overflow 为 0，说明 Pretext 预测量的高度与实际渲染完全一致。现在验证常量计算的正确性。

让我做最后的数学验证和截图：

**CSS 实际值（从 DOM 测量确认）：**
- `box-sizing: border-box` → height 包含 border
- `padding: 4px 12px` → 垂直 4px×2 = 8px，水平 12px×2 = 24px
- `border: 1px solid` → 垂直 1px×2 = 2px，水平 1px×2 = 2px
- `font-size: 12px`, `line-height: 1` (= 12px)
- 实际渲染高度：**22px** ✓ (12 + 8 + 2)
- 实际水平 padding+border：**26px** ✓ (24 + 2)

**JS 常量（ArticleCard.tsx 第 43-44 行）：**
- `TAG_PILL_HEIGHT = 22` ✓
- `TAG_H_PADDING = 26` ✓

完全匹配。下面输出评估报告：

---

## 增量评估

### 变更验证: PASS

- `TAG_PILL_HEIGHT` 已从 16 更新为 22，与 CSS 实际渲染高度完全一致（DOM 测量确认所有 tag pill 高度均为 22px）
- `TAG_H_PADDING` 已从 20 更新为 26，与 CSS `padding: 4px 12px` + `border: 1px solid`（box-sizing: border-box）的水平总和一致
- 常量注释 `// 12px font × line-height:1 + 4px×2 padding + 1px×2 border` 准确描述了计算过程
- 两张带 tags 的卡片 overflow 均为 0（scrollHeight === clientHeight = 130px），Pretext 预测量与实际渲染完全对齐，无内容溢出或截断
- `computeTagsHeight()` 和 `computeCardHeight()` 逻辑正确引用了更新后的常量
- `MasonryGrid.tsx` 的改动仅为 import 调整（新增 `CARD_PADDING` / `CARD_PADDING_MOBILE` 导入），与本次常量修复配合正确
- `lib/pretext/fonts.ts` 和 `lib/pretext/index.ts` 的改动为 barrel export 补充，无功能影响

### 构建检查: PASS

- `npm run build` 成功，TypeScript 编译通过，33 个静态页面全部生成，无 warning 或 error

### 发现的问题

无。本次修改精准地将 Pretext 高度常量与 CSS 实际渲染值对齐，修复了之前因未计入 border 导致的 ~6px 高度偏差。