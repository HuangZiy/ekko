# ISS-3: PROJECT 的 ISSUE 前缀支持修改

## 现状分析

- `Project` 模型已有 `key` 字段（默认 `"ISS"`），创建时可通过 `--key` 指定
- 但创建后无法修改 `key`
- API 的 `UpdateProjectRequest` 只支持 `name` 和 `workspace_path`，不含 `key`
- CLI 没有 `project update` 子命令
- 前端 `ProjectDetail.tsx` 编辑模式只能改 name 和 workspace，不能改 key

## 实现方案

### 1. CLI: 添加 `project update` 子命令
- 文件: `cli/main.py`
- 添加 `_project_update` 函数，支持 `--key` 和 `--name` 参数
- 在 `build_parser` 中注册 `project update` 子命令
- key 值自动转大写，校验非空

### 2. API: PATCH 端点支持 key
- 文件: `server/routes/projects.py`
- `UpdateProjectRequest` 添加 `key: str | None = None`
- PATCH handler 中处理 key 更新

### 3. 前端 Store: updateProject 支持 key
- 文件: `web/src/stores/projectStore.ts`
- `updateProject` 的 patch 类型添加 `key?: string`

### 4. 前端 UI: ProjectDetail 编辑 key
- 文件: `web/src/components/ProjectDetail.tsx`
- 编辑模式下增加 Issue Key 输入框
- handleSave 中将 key 变更加入 patch

## 注意事项
- 修改 key 只影响后续新建的 issue，已有 issue ID 不变
- key 值强制大写
