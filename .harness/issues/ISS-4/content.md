# ISS-4: harness 增加 planning agent

## 描述

在 harness 的 generator 前增加一个 planning 的 agent 流程，planning 的 agent 会生成一个 针对此issue 的 plan，放置于 issue详情的 plan字段内，后续 generator 在完成时 会依次进行 [X] ，然后 planning 和 evaluator 都可以创建和追加 pla，也都可以创建 issue。当然创建 issue，是需要取决于遇到问题的复杂度的，比如：

```
根据我观察 ekko 跑 ISS-1 的情况（52 turns，$3.07，578s），加上 Claude
  Agent SDK 的特性，分享一下经验判断：

  Agent 能比较好完成的粒度：

  单个 issue 最好控制在一个"可独立验证的变更"范围内。具体来说：

  - 改动集中在 3-5 个文件以内
  - 一次 git commit 能说清楚做了什么
  - 有明确的验收标准（能用 build/test/截图验证）
  - 不需要跨多个子系统做协调性修改

  需要拆分的信号：

  - issue 标题里有"和"、"并且"、"同时" — 多个独立关注点
  - 需要同时改前端 + 后端 + 数据模型 — 跨层变更容易顾此失彼
  - 描述超过 3 段 — 说明复杂度高
  - 涉及新建超过 5 个文件 — agent 容易丢失上下文
  - 有隐含的先后依赖 — 比如"加数据库表然后写 API 然后写 UI"

  实际例子：

  ISS-1（markdown 编辑器）其实偏大了 — 它同时做了组件、后端上传
  API、集成到多个页面。更好的拆法：
  1. ISS-1: 创建 MarkdownEditor 组件（纯前端）
  2. ISS-2: 图片上传 API（纯后端）
  3. ISS-3: 集成到 Issue 创建和编辑流程（接线）

  每个 15-25 turns，$1 以内，成功率更高。

  经验法则：如果你觉得需要给 agent 写超过 5 行的描述才能说清楚，就该拆了。
```

当然 Issue也会有父子依赖关系，根据某个issue A分拆出来的issue  都是属于 issue A 的子 Issue
