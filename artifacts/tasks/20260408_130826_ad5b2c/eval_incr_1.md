

## 增量评估

### 变更验证: FAIL

**CSS 样式 (ArticleCard.module.css `.tag`) — PASS**

4 项 CSS 变更全部正确落地，浏览器计算样式确认：

| 属性 | 要求值 | 实际渲染值 | 状态 |
|---|---|---|---|
| padding | `4px 12px` | `4px 12px` | ✅ |
| background | `color-mix(in srgb, var(--accent) 12%, transparent)` | `color(srgb 0.376 0.647 0.980 / 0.12)` | ✅ |
| border | `1px solid color-mix(in srgb, var(--accent) 20%, transparent)` | `1px solid color(srgb 0.376 0.647 0.980 / 0.2)` | ✅ |
| border-radius | `9999px` | `9999px` | ✅ |

**JS 高度常量同步 — FAIL**

`ArticleCard.tsx` 中用于 Pretext masonry 预测量的常量未随 CSS 更新：

- `TAG_PILL_HEIGHT = 16` — 旧值基于 `12px font × line-height:1 + 2px×2 padding = 16px`。新 CSS 下实际 pill 高度 = 12 + 4×2 (padding) + 1×2 (border) = **22px**。差值 **6px**。
- `TAG_H_PADDING = 20` — 旧值基于 `10px × 2 = 20px`。新 CSS 下实际水平占用 = 12×2 (padding) + 1×2 (border) = **26px**。差值 **6px**。

**实测溢出证据：** 两张卡片均出现 `scrollHeight(127) > clientHeight(124)`，内容底部超出卡片边界 3px。当前因为只有单行 tags 且 `HEIGHT_SAFETY_MARGIN = 4` 部分吸收了误差，溢出仅 3px 不太明显。但如果 tags 多到需要换行，误差会成倍放大导致严重截断。

### 构建检查: PASS

`npm run build` 编译成功，TypeScript 无报错，33 个页面全部静态生成。

### 发现的问题

- [FAIL] `ArticleCard.tsx` 第 43-44 行常量未同步更新。`TAG_PILL_HEIGHT` 应从 `16` 改为 `22`（12px font + 4px×2 padding + 1px×2 border），`TAG_H_PADDING` 应从 `20` 改为 `26`（12px×2 padding + 1px×2 border）。这导致 Pretext masonry 预测量的卡片高度偏小，所有带 tags 的卡片内容溢出 3px。tags 越多、换行越多，溢出越严重。