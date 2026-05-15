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
