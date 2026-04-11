我在等你选择问题的具体表现，这样我才能精准定位修复方向。

从代码分析来看，我已经发现了几个可能导致"文字被压缩"的嫌疑点：

1. `.title` 的 `line-height: 21px` 对应 `LINE_HEIGHT.uiSm = 21`，但 `font-size` 是 `var(--font-size-lg)` = 18px。21px 的行高对于 18px 字体来说偏紧，尤其是中文字符（CJK 字形通常比拉丁字母高）
2. Pretext 用 `FONT_CARD_TITLE = '600 18px Inter'` 测量，但 CSS 里标题字体是 `var(--font-sans)` 包含 `Noto Sans SC`。如果实际渲染用了 Noto Sans SC（中文场景），而 Pretext 用 Inter 测量，高度就会算少
3. 卡片高度是 Pretext 预计算后通过 `style={{ height: cardHeight }}` 硬编码的，如果测量偏小，内容就会被压缩在不够高的容器里

你能告诉我具体是哪种表现吗？或者如果方便的话，截个图给我看看？