# VPS 模式一键部署 Review 与执行计划

日期：2026-05-15

## 背景

当前 `oc remote bootstrap-vps --apply` 已经能生成 secret、配置本机 daemon、
安装 systemd/Caddy，并通过 Vercel 部署 Dashboard BFF。但实际部署中暴露出一个
产品级问题：部署成功仍需要操作者继续判断端口、动态域名、Vercel preview URL 与
production URL、Vercel Deployment Protection、登录密码路径和端到端验证结果。

VPS 模式的目标不是“提供若干脚本片段”，而是在 Codex 已运行于目标 VPS 且
`VERCEL_TOKEN` 已配置的前提下，用一个命令完成部署并返回可访问的 Dashboard。

## Review 结论

当前流程可用但不够自动化，主要风险如下。

1. **最终 URL 语义不清**
   Vercel CLI 返回的 deployment URL 可能是 preview/generated URL，不一定是最终用户
   应访问的 production alias。preview URL 可能被 Vercel Deployment Protection 拦截。

2. **VPS 入口选择依赖人工判断**
   443 被占用、`sslip.io` 证书限流、需要改用 `nip.io:8443` 这类情况目前靠人工补救。
   脚本应自动选择可用 HTTPS 入口并验证。

3. **Vercel 配置缺少部署后验证**
   当前只执行 link/env/deploy，没有验证 production alias 的 `/api/session` 是否返回
   Open Composer 应用 JSON，也没有验证登录后 BFF 能否通过 HMAC 调用 daemon。

4. **密码状态不够明确**
   首次部署生成密码时有 owner-only 文件；二次部署复用已有 hash 时可能没有原始密码。
   输出必须说明是否有可用 password path，以及何时需要 `--rotate-secrets`。

5. **失败信息不够面向自动化**
   命令失败时缺少 stage 化的 verify 结果，不利于下一次自动重试或用户快速定位。

## 本次执行范围

本次改造优先保证一键部署闭环，而不是一次性替换所有 Vercel CLI 调用为 REST API。

必须完成：

- `bootstrap-vps --apply` 默认执行部署后验证。
- 增加 `dashboard_url`，将最终可访问 URL 与 Vercel deployment URL 分离。
- 自动选择 daemon URL：无 `--daemon-url` 时根据公网 IPv4 生成候选 URL。
- 允许自动回退到 `:8443`，并优先使用 `nip.io`，降低 `sslip.io` 限流风险。
- Caddy 写入前自动检测 443 是否可用。
- Caddy restart 后验证 daemon `/health`。
- Vercel 部署后验证 production alias `/api/session`。
- 若本次有可用原始密码，自动登录并验证 `/api/dashboard/catalog`。
- 输出和报告中记录 verify 步骤、最终 URL、密码文件路径，不泄露 secret/token。
- 增加 `--no-verify` 作为调试逃生口。

后续增强：

- 使用 Vercel REST API 做 project/env upsert，减少 CLI 交互面。
- 使用 Vercel REST API 管理 Deployment Protection，并在 token 权限不足时给出明确诊断。
- 增加 `--json` 输出，方便 agent 或 CI 读取。

## 目标命令

```bash
VERCEL_TOKEN=<token> uv run oc remote bootstrap-vps --apply
```

高级参数仍保留：

```bash
uv run oc remote bootstrap-vps --apply --daemon-url https://oc-api.example.com
uv run oc remote bootstrap-vps --apply --skip-vercel
uv run oc remote bootstrap-vps --apply --skip-system
uv run oc remote bootstrap-vps --apply --no-verify
uv run oc remote bootstrap-vps --apply --rotate-secrets
```

## 自动化设计

### Daemon URL

选择顺序：

1. 用户传入 `--daemon-url`：直接使用。
2. 用户传入或自动探测 `--public-ip`：
   - 如果 443 可监听，默认 `https://<ip>.nip.io`。
   - 如果 443 不可监听，默认 `https://<ip>.nip.io:8443`。
3. 如果 `nip.io` 健康检查失败且是自动生成 URL，可尝试 `sslip.io` 同端口候选。

本次先实现 443 占用时自动选择 `:8443` 和 `nip.io` 默认域名。

### Caddy

- Caddyfile 从 daemon URL 提取 host:port。
- systemd daemon 仍只监听 `127.0.0.1:8787`。
- `apply` 阶段执行 `caddy validate` 和 `systemctl restart caddy`。
- verify 阶段轮询 `GET <daemon_url>/health`。

### Vercel

- CLI token 继续只通过 `VERCEL_TOKEN` 环境变量传入，不进入 argv、报告或日志。
- deployment URL 只作为审计字段。
- `dashboard_url` 默认使用 `vercel_origin`，即 production alias。
- verify 阶段请求 `${dashboard_url}/api/session`，必须返回 JSON 且 `remote=true`。
- 若返回 HTML/401 Vercel Authentication 页面，部署视为 blocked，并提示关闭外层保护或给 token 增加权限后重试。

### 密码

- 首次生成密码时写入 `reports/deployment/vps-bootstrap/generated-dashboard-password.txt`，权限 `0600`。
- verify 登录只在本次命令能拿到原始密码时执行。
- 如果无法拿到原始密码，verify 会跳过登录验证但保留 session JSON 检查，并提示用
  `--rotate-secrets` 或 `--dashboard-password` 恢复全链路验证能力。

## Review 后计划

1. 扩展 plan schema：加入 `dashboard_url`、`password_available`、verify steps。
2. 扩展 CLI：加入 `--verify/--no-verify`。
3. 修改默认 daemon URL 生成：优先 `nip.io`，443 不可用时自动 `:8443`。
4. 修改 Caddy 安装流程：增加 `caddy validate`。
5. 增加 HTTP verify helpers：daemon health、Vercel session、login、catalog。
6. 更新测试覆盖一键路径、URL 区分、443 fallback、verify 成功/失败。
7. 更新 README 与部署文档。
8. 运行 `uv run ruff format .`、`uv run ruff check .`、`uv run pytest`。

## 成功标准

- 新用户只设置 `VERCEL_TOKEN` 后可以运行一个 apply 命令完成部署。
- 命令最终输出明确包含：
  - Dashboard URL
  - Daemon URL
  - Deployment URL
  - Password path 或无法验证登录的原因
  - Verify status
- 报告和日志不包含 Vercel token、raw shared secret、session secret 或 raw password。
- Vercel 仍只是 password session、CSRF、HMAC proxy，不执行回测、scan、pytest、文件写入或 shell。
