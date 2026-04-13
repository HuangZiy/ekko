# ISS-3: PROJECT 的 ISSUE 前缀支持修改

## 描述

支持自定义 PROJECT 的 ISSUE 前缀


## Agent Done 证据

收集时间: 2026-04-13 17:36 UTC

### Git Diff

```
cli/main.py                          | 38 ++++++++++++++++++++++++++++++++++++
 config.py                            |  4 ++++
 core/models.py                       |  3 ++-
 server/routes/projects.py            |  6 ++++++
 web/src/components/ProjectDetail.tsx | 19 ++++++++++++++++--
 web/src/stores/projectStore.ts       |  2 +-
 6 files changed, 68 insertions(+), 4 deletions(-)
```

### Latest Commit

`c614d98 feat: 支持修改项目的 Issue 前缀 (ISS-3)`

### Build: UNKNOWN

```
(no output)
```


## Agent Done 证据

收集时间: 2026-04-13 17:38 UTC

### Git Diff

```
cli/main.py                          |  43 ++++++++++++++
 config.py                            |   4 ++
 core/models.py                       |   3 +-
 core/ralph_loop.py                   | 107 +++++++++++++++++++++++++++++++++--
 server/routes/projects.py            |   6 ++
 web/src/components/ProjectDetail.tsx |  19 ++++++-
 web/src/stores/projectStore.ts       |   2 +-
 7 files changed, 175 insertions(+), 9 deletions(-)
```

### Latest Commit

`c614d98 feat: 支持修改项目的 Issue 前缀 (ISS-3)`

### Build: UNKNOWN

```
(no output)
```
