# Open Composer Remote Dashboard 部署说明

日期：2026-05-16

## 边界

Remote Dashboard 是个人敏感控制面。Vercel 只负责 password session、CSRF、HMAC 签名和 API proxy；策略执行、回测、扫描、pytest、文件写入和 paper 控制只在 Open Composer remote daemon 上执行。

## 云服务器目录

```text
/srv/open-composer/repo
/srv/open-composer/repo/.env
/srv/open-composer/repo/reports
/srv/open-composer/repo/strategy_specs
```

推荐运行用户为 `opencomposer`。daemon 只监听 `127.0.0.1:8787`，公网 HTTPS 入口由 Caddy 或 Nginx 反代。

## 环境变量

Vercel:

```text
OC_REMOTE_BASE_URL=https://oc-api.example.com
OC_REMOTE_SHARED_SECRET=<same-random-secret-as-daemon>
OC_DASHBOARD_PASSWORD_HASH=pbkdf2-sha256:<iterations>:<salt>:<hex>
OC_DASHBOARD_SESSION_SECRET=<random-session-secret>
OC_DASHBOARD_OWNER=owner
OC_DASHBOARD_ALLOWED_ORIGIN=https://<vercel-app-domain>
```

Daemon:

```text
OC_REMOTE_SHARED_SECRET=<same-random-secret-as-vercel>
OC_DASHBOARD_OWNER=owner
```

`.env` 在服务器上应为 `0600`。正常 VPS 模式不需要手写这些变量；脚本会生成
secret、hash 密码、合并 `.env`，并把 Vercel 环境变量写入项目。

## VPS 模式（推荐）

当 Codex 已经运行在目标 VPS 上时，推荐使用 VPS 模式。只需要设置
`VERCEL_TOKEN`，然后运行仓库脚本：

```bash
cd /srv/open-composer/repo
export VERCEL_TOKEN=<token>
./scripts/deploy-vps.sh
```

脚本会同步 Python 依赖，然后执行 `uv run oc remote bootstrap-vps --apply`。
默认行为包括：

- 探测 VPS 公网 IPv4，并选择 `https://<ip>.nip.io` 或
  `https://<ip>.nip.io:8443`
- 生成 remote shared secret、session secret、Dashboard password hash
- 合并 `.env` 并设置 `chmod 600`
- 把生成的 Dashboard 明文密码写入 owner-only 文件
- 生成并安装 systemd/Caddy 配置
- 用 Vercel token 创建或链接 project，写入 Vercel env，部署 production BFF
- 验证 daemon `/health`、Vercel `/api/session`、Dashboard 登录和 BFF catalog proxy
- 输出 `Dashboard URL`、`Daemon URL`、`Deployment URL`、密码文件路径和 verify 状态

只生成计划、不部署：

```bash
./scripts/deploy-vps.sh --plan
```

计划默认只写：

```text
reports/deployment/vps-bootstrap/plan.json
reports/deployment/vps-bootstrap/plan.md
reports/deployment/vps-bootstrap/open-composer-remote.service
reports/deployment/vps-bootstrap/Caddyfile
```

生产长期使用建议传入自有域名：

```bash
./scripts/deploy-vps.sh --daemon-url https://oc-api.example.com
```

如果系统文件由 root 管理但当前用户有 sudo：

```bash
./scripts/deploy-vps.sh --sudo
```

如果只想生成本机 daemon 配置，不部署 Vercel：

```bash
./scripts/deploy-vps.sh --skip-vercel
```

如果只想配置 Vercel，不安装 systemd/Caddy：

```bash
./scripts/deploy-vps.sh --skip-system
```

调试时可以跳过部署后验证：

```bash
./scripts/deploy-vps.sh --no-verify
```

底层命令仍可直接使用：

```bash
VERCEL_TOKEN=<token> uv run oc remote bootstrap-vps --apply
```

## 停止和清理远程 Dashboard

标准停止入口：

```bash
./scripts/stop-remote-dashboard.sh --remove-systemd --disable-caddy --remove-caddyfile
```

这个脚本会停止并禁用 `open-composer-remote.service`，可选删除 systemd 单元，
并在 Caddyfile 看起来是 Open Composer 专用反代时才停止 Caddy 或移动
`/etc/caddy/Caddyfile`。如果系统目录需要 sudo：

```bash
./scripts/stop-remote-dashboard.sh --sudo --remove-systemd --disable-caddy --remove-caddyfile
```

当 Caddy 同时服务其他站点时，不要传 `--disable-caddy` 或 `--remove-caddyfile`。

## 通知配置

Dashboard 远程模式支持 outbound-only Telegram 通知。实际配置文件
`config/notifications.yaml` 不入仓；示例文件入仓在
`config/notifications.yaml.example`。VPS `.env` 中只需要放环境变量：

```bash
TELEGRAM_BOT_TOKEN=<bot-token>
TELEGRAM_CHAT_ID=<chat-id>
```

验证命令：

```bash
uv run oc notify status
uv run oc notify test --dry-run
```

Telegram 只用于 Open Composer 向外发送消息；项目不实现 webhook、polling、
callback 或聊天命令入口。

## 手动启动 daemon

```bash
cd /srv/open-composer/repo
uv run oc remote doctor
uv run oc remote serve --host 127.0.0.1 --port 8787
```

正常 VPS 部署不需要手动运行 daemon；`scripts/deploy-vps.sh` 会安装并启动
`open-composer-remote.service`。

`/health` 不需要签名，只返回服务状态。其余 route 都需要 HMAC：

```text
GET  /dashboard/catalog
POST /dashboard/command-plan
POST /dashboard/command-run
GET  /dashboard/jobs/{job_id}
GET  /dashboard/events
GET  /agent-requests
POST /agent-requests
```

## 命令控制

Green action 只需要 session、HMAC、audit 和 job。

Yellow action 执行前创建 `reports/backups/remote/<job_id>/manifest.json`。

Red action 执行前需要原 command confirmation phrase 加二次确认：

```text
CONFIRM REMOTE STRATEGY MUTATION
CONFIRM REMOTE PAPER CONTROL
```

所有 remote command-run 都创建异步 job，job 文件写入：

```text
reports/dashboard/jobs/<job_id>.json
reports/dashboard/jobs/<job_id>.log
reports/dashboard/jobs/events.jsonl
```

## 验证

```bash
uv run oc remote doctor
uv run python scripts/check-agent-parity.py
uv run oc repo check --strict
make verify
```
