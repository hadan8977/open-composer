# Open Composer Remote Dashboard 部署说明

日期：2026-05-14

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

`.env` 在服务器上应为 `0600`。

## VPS 模式（推荐）

当 Codex 已经运行在目标 VPS 上时，推荐使用 VPS 模式自动生成 secret、写入
本机 `.env`、生成 systemd/Caddy 模板，并用 Vercel token 配置 Dashboard BFF：

```bash
cd /srv/open-composer/repo
VERCEL_TOKEN=<token> uv run oc remote bootstrap-vps --generate-password
VERCEL_TOKEN=<token> uv run oc remote bootstrap-vps --apply --generate-password
```

dry run 默认只写：

```text
reports/deployment/vps-bootstrap/plan.json
reports/deployment/vps-bootstrap/plan.md
reports/deployment/vps-bootstrap/open-composer-remote.service
reports/deployment/vps-bootstrap/Caddyfile
```

`--apply` 才会写 `.env`、设置 `chmod 600`、安装或刷新 systemd/Caddy，并调用
Vercel CLI。若不传 `--daemon-url`，apply 模式会探测 VPS 公网 IPv4 并使用
`https://<ip>.sslip.io` 作为默认 daemon HTTPS URL。生产长期使用建议传入自有域名。
dry run 阶段如果也想看到准确的 `sslip.io` URL，可传 `--public-ip <vps-ip>`。

```bash
VERCEL_TOKEN=<token> uv run oc remote bootstrap-vps \
  --apply \
  --daemon-url https://oc-api.example.com \
  --generate-password
```

如果系统文件由 root 管理但当前用户有 sudo：

```bash
VERCEL_TOKEN=<token> uv run oc remote bootstrap-vps --apply --sudo --generate-password
```

如果只想生成本机 daemon 配置，不部署 Vercel：

```bash
uv run oc remote bootstrap-vps --public-ip <vps-ip> --skip-vercel --generate-password
```

如果只想配置 Vercel，不安装 systemd/Caddy：

```bash
VERCEL_TOKEN=<token> uv run oc remote bootstrap-vps --apply --skip-system --generate-password
```

## 启动 daemon

```bash
cd /srv/open-composer/repo
uv run oc remote doctor
uv run oc remote serve --host 127.0.0.1 --port 8787
```

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
