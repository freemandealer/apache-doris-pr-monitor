## 项目背景

Apache Doris 代码库的活跃贡献者需要频繁地查看自己或团队成员的开放状态 Pull Request，了解流水线失败原因，并在必要时重新触发流水线或执行 rebase。手工在 GitHub 页面逐个查找、点击、重新运行流水线既耗时又容易遗漏。本设计旨在交付一个基于 Python 的轻量化 Web 工具，集中展示特定用户的 Open 状态 PR，提供失败流水线的可视化以及一键 rerun/rebase 能力，减少上下文切换并提升响应效率。

## 目标与非目标

**目标**

1. 拉取特定 GitHub 用户的所有开放 PR，显示核心元数据（标题、编号、仓库、更新时间、评审状态、是否冲突）。
2. 表格化展示每个 PR 下失败或待处理(pending)的流水线，附带原始详情链接。
3. 为每条失败流水线提供一键 rerun 功能，通过在 PR 下评论指定触发词完成。触发词映射如下：
   - `run compile`
   - `run feut`
   - `run beut`
   - `run p0`
   - `run p1`
   - `run cloud_p0`
   - `run performance`
   - `run external`
   - `run nonConcurrent`
4. 提供「Rebase & Rerun」复合操作：自动点击 GitHub PR 页的 **Update branch**（若可用），随后在评论中提交 `run buildall`。
5. 支持使用配置文件存储目标用户名、访问令牌、GitHub Enterprise 地址等凭据。

**非目标**

1. 不实现流水线结果的抓取/解析，直接使用 GitHub Checks API/Status API 返回的数据和原生详情链接。
2. 不负责权限管理（假设部署环境仅限可信内部用户）。
3. 不处理非 GitHub 平台（例如 GitLab、Gerrit）。

## 高层架构

为了保证实现和部署都足够简单，采用「单体 Python Web 服务」架构：

```
┌────────────────────────────────────────────────┐
│              Flask + Jinja Web 服务             │
│                                                │
│  • 路由层：/ -> 渲染表格；/rerun, /rebase -> POST │
│  • GitHub Client：封装 GraphQL/REST 调用        │
│  • 配置管理：加载多用户+项目组合                │
│  • 缓存：内存级（per target 60s）               │
└────────────────────────────────────────────────┘
         ▲
         │ PAT、API Base、targets
        ┌────────┴────────┐
        │  config.yaml    │
        └─────────────────┘
         ▲
         │
        GitHub APIs
```

关键点：

1. 所有页面均由 Flask（或 FastAPI 的 Jinja 模式）在服务端渲染，避免额外的前后端分离工程成本。
2. 交互表单使用最基础的 HTML form + fetch，POST 请求直接命中同一个 Python 服务路由。
3. 静态资源仅包含一个轻量 CSS（可使用 Pico.css / simple.css），不依赖构建工具。
4. 服务可运行在单进程 Gunicorn/Waitress，部署简单。

## 核心模块设计

### 1. 配置管理模块

- **配置文件**：`config.yaml`（优先）或 `.env`。为满足「多个用户 + 项目组合」，改为 targets 列表：
  ```yaml
  github:
    token: ${GITHUB_TOKEN}
    api_base: "https://api.github.com"
    web_base: "https://github.com"
  targets:
    - label: "Freeman @ apache/doris"
      user: "freemandealer"
      repos:
        - "apache/doris"
        - "apache/doris-expr"
    - label: "Team Bot"
      user: "team-ci"
      repos:
        - "my-org/playground"
  polling:
    interval_seconds: 300
  server:
    host: 0.0.0.0
    port: 8080
  auth:
    api_key: "optional-shared-key"
  ```
- 启动时加载并做 schema 校验（pydantic / voluptuous），确保 `targets` 至少包含一个配置，`repos` 为空时默认全局搜索。
- 支持环境变量覆盖敏感字段（如 token、api_key）。
- 在 UI 中通过下拉框/URL query 选择 target，服务端根据 target 决定 author + repo 过滤条件。

### 2. GitHub 数据服务

- **PR 列表查询**：使用 GraphQL API 以减少请求量，过滤条件为 `author`, `is:open`, `is:pr`。
- **冲突检测**：`mergeableState` 字段；若为 `CONFLICTING` 则标记红色状态。
- **Update branch 判断**：当 `mergeable=true` 且 `mergeable_state` 为 `unstable`（如 PR [#58845](https://github.com/apache/doris/pull/58845) 的实时状态），GitHub UI 会展示 `Update branch` 按钮；`mergeable_state=clean` 则按钮消失。后台需要读取这两个字段，以便在表格中显示「可更新」提示并启用「Rebase & Rerun」按钮。
- **流水线状态**：
  - GraphQL `checkSuites` / REST `check-runs` 获取；
  - 仅保留状态为 `failure`, `cancelled`, `timed_out`, `action_required` 等非成功条目；
  - 提供 `html_url` 作为详情链接。
- **真实数据示例**：PR #58845 的 commit `976a2b3` 返回的 `statuses` 中，`performance (Doris Performance)` 项 `state=failure`、`description="TeamCity build failed"`、`target_url=http://43.132.222.7:8111/...`；`P0 Regression` 则可能处于 `pending`。界面需原样显示 `context`、`description`、`target_url`，方便一眼定位出错流水线。
- **流水线 ↔ run 命令映射**：结合 #58845 的状态列表与 Doris 社区约定，整理以下对应关系供 UI 渲染及后端校验（若某条流水线名称匹配 `context`，即自动填充该触发词）：

  | 状态 `context` 示例                     | 推荐显示名称         | 触发命令          | 备注 |
  | -------------------------------------- | -------------------- | ----------------- | ---- |
  | `COMPILE (DORIS_COMPILE)`              | Compile              | `run compile`     | #58845 中成功记录，仍允许重跑 |
  | `FE UT (Doris FE UT)`                  | FE UT                | `run feut`        | TeamCity FE 单测 |
  | `BE UT (Doris BE UT)`                  | BE UT                | `run beut`        | TeamCity BE 单测 |
  | `P0 Regression (Doris Regression)`     | P0 Regression        | `run p0`          | #58845 中处于 pending |
  | `vault_p0 (Doris Cloud Regression)`    | Cloud P0             | `run cloud_p0`    | 云端 P0 套件 |
  | `NonConcurrent Regression`             | Non-Concurrent Reg   | `run nonConcurrent` | 名称保持驼峰以匹配命令 |
  | `performance (Doris Performance)`      | Performance          | `run performance` | #58845 中 state=failure，需要 rerun |
  | `External Regression`                  | External Regression  | `run external`    | 第三方回归 |
  | `vault_p1 / p1` or `P1 Regression`     | P1 Regression        | `run p1`          | 某些 PR 中 context=Vault_P1 |
  | `Coverage`（如 `check_coverage`）       | Coverage             | `run coverage`    | 若需专门命令，可扩展映射 |

  - 后端实现上维护一个 `context -> command` 字典，默认命中列表即可；若 `context` 未知，则回退到按钮下拉让用户自行选择命令。
  - 示例 PR #58845 的 `performance` 失败，可在行内直接展示 `run performance` 按钮，避免人工选择。
- **Update branch 操作**：调用 `PUT /repos/{owner}/{repo}/pulls/{pull_number}/update-branch`（需权限）。
- **Comment 触发**：`POST /repos/{owner}/{repo}/pulls/{pull_number}/comments`，payload 为触发词。
- 考虑 GitHub API 速率限制：
  - 使用 `If-None-Match` ETag 缓存 PR 列表；
  - 对 rerun 及 rebase 操作使用短暂队列，避免突发风暴。

### 3. Web 服务路由层

实现建议：Flask + Jinja（也可用 FastAPI 但依旧采用同步模板渲染模式）。核心路由：

- `GET /`：参数 `target=label`，渲染表格。服务器端准备好 `targets` 列表以供切换。
- `POST /rerun`：Form 参数 `{ "target": "label", "pr": 123, "pipeline": "compile" }`。返回 JSON，前端用 `<form hx-post>` 或 fetch 更新按钮状态。
- `POST /rebase-rerun`：Form 参数 `{ "target": "label", "pr": 123 }`，顺序执行 Update branch + buildall 评论。

由于所有交互都回到同一个服务，错误消息可通过 Flash message 或 JSON 响应注入模板，无需独立 API 层。

### 4. Web UI

- 模板：单个 `index.html`，使用原生 HTML + Pico.css（或自定义 200 行以内 CSS）。
- 布局：
  - 顶部工具栏：`<select name="target">` 用于切换用户/项目组合，旁边是刷新按钮（提交 GET 请求）。
  - 主表格列：PR #、标题、所属仓库、最新更新时间、冲突状态（图标+文字）、流水线状态。
  - 流水线单元格内列出失败项：名称、状态徽章、详情链接，以及一个 `<form method="post">` 的 Rerun 按钮。
  - 行尾的 `Rebase & Rerun` 按钮同样是 form，点击后禁用并显示“处理中”。
  - `Update branch` 提示：若某 PR 的 `mergeable_state` 为 `unstable`（实测来自 #58845），在表格中显示「需要 Update branch」徽章，并在 `Rebase & Rerun` 气泡提示中说明该按钮会先点击 GitHub 上相同操作，再触发 `run buildall`。
- 动效：使用 HTMX 或 `fetch` 仅刷新按钮位置即可；若需要极简，可直接让 form 提交后重定向回首页并通过 Flash 展示“成功/失败”。
- 友好空态：根据选择的 target 给出“没有 open PR”的提示以及最近刷新时间。

## 工作流与时序

1. 用户访问 `/`，若未指定 target，则使用配置中的第一个 target。服务端根据 target 组合出 GraphQL 查询，渲染首屏表格。
2. 60 秒缓存：若同一 target 在 TTL 内已有数据则直接使用，否则实时拉取 GitHub 数据并落入缓存。
3. 用户通过下拉选择其他 target 后提交 GET 请求，服务端重复步骤 1-2 并渲染相应结果。
4. 用户点击 Rerun：
  1. `<form method="post" action="/rerun">` 携带 target、PR 编号、流水线名称。
  2. 服务器校验流水线是否存在于映射表，随后调用评论 API 发送 `run <pipeline>`。
  3. 返回 JSON（含状态/提示），前端可通过 HTMX 局部刷新按钮或直接刷新整页。
5. 用户点击 `Rebase & Rerun`：
  1. 提交至 `/rebase-rerun`，服务端先调用 Update branch（若接口返回 202 表示正在进行）。
  2. 待 Update branch 请求返回后，再调用评论 API 写入 `run buildall`。
  3. 将两个操作的结果合并后返回给前端进行展示。

## 错误处理与重试

- **GitHub API 速率限制**：读取到 `403` + `X-RateLimit-Remaining=0` 时，记录解冻时间并在前端提示“稍后刷新”。
- **Update branch 不可用**：若 PR 已 up-to-date，会返回 422，前端提示“无需 Update，已直接触发 buildall”。
- **重复点击 rerun**：后端去重（同一 pipeline 在 2 分钟内仅执行一次）并在响应中返回 `already_triggered=true`。
- **网络错误**：使用 exponential backoff 最多重试 3 次。

## 安全与权限

- 仅需提供具备 `repo` + `workflow` scope 的 GitHub PAT，保存在本地 `config.yaml` 或环境变量中。
- 服务默认部署在内网或 VPN 中，Python 服务本身只监本地回环地址。

## 部署方案

1. 以 `uvicorn main:app` 运行，或使用 `gunicorn -k uvicorn.workers.UvicornWorker`。
2. 打包方式：
   - `poetry` / `pip-tools` 管理依赖。
   - 提供 `Dockerfile`（基础镜像 `python:3.11-slim`）。
3. 使用 systemd/容器编排（K8s CronJob + Deployment）负责进程守护与日志。
