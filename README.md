# Apache Doris PR Monitor

一个轻量级的 Flask Web 服务，帮助 Doris 贡献者集中查看自己（或团队成员）在多个仓库下的开放状态 Pull Request，并提供一键触发常用流水线和 Rebase & Rerun 能力。

## 功能概览

- 从配置的 GitHub 用户/仓库组合中拉取所有开放 PR，展示标题、仓库、更新时间、合并状态。
- 可视化列出失败或 Pending 的流水线，并自动映射到 Doris 社区常用的 `run xxx` 触发词。
- 支持一键按钮触发指定流水线的 rerun，或执行 Update branch 后再提交 `run buildall`。
- 内建 60s 缓存，避免过度调用 GitHub API；POST 路由支持可选 `X-API-Key` 校验。

## 快速开始

1. 安装依赖：

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. 配置 `config.yaml`（已提供示例），或通过环境变量覆盖敏感字段：

   ```bash
   export GITHUB_TOKEN=xxxx
   export PR_MONITOR_API_KEY=optional-shared-secret
   ```

3. 启动服务：

   ```bash
   python main.py
   ```

   默认监听 `config.yaml` 中的 `server.host:server.port`（示例为 `127.0.0.1:8480`）。

4. 浏览器访问 `http://127.0.0.1:8480` 即可查看界面。

## 运行测试

```bash
pytest
```

## 部署提示

- 可直接使用 `gunicorn -w 2 'main:app'` 部署，或容器化后交由 K8s/Nomad 管理。
- GraphQL & REST 请求均使用同一个 PAT，确保具备 `repo` 与 `workflow` 权限。
- 若部署在内网，可通过 `auth.api_key` 配置简单的共享密钥防护；也可以借助反向代理添加 SSO。
