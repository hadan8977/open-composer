# Open Composer VPS Dashboard 部署说明

日期：2026-05-22

## 结论

Open Composer 的标准部署方式只有一个：**VPS 直接托管 Dashboard，策略研究和执行仍然保持本地 / CLI / 文件优先**。

不再把 Vercel 作为正常产品路径。旧的 Vercel BFF / remote daemon 代码只保留为遗留兼容，不作为新部署入口。

## 架构边界

```text
Browser
  -> HTTPS Dashboard on VPS (Caddy)
  -> oc dashboard serve (systemd)
  -> repo files: projects/, reports/, strategy_specs/, signal_logs/

Codex / Claude Code / CLI
  -> local workspace commands
  -> writes audited files and reports
```

关键规则：

- Dashboard 是用户入口和状态面板，不在浏览器里跑长任务。
- 策略行为仍以 `StrategySpec` 为真相来源。
- 回测、扫描、pytest、构建、策略文件写入由本地 CLI / agent 请求完成。
- Alpaca Paper 仍需 readiness gate 和显式确认。
- 真钱 broker 写入不属于 MVP。
- Dashboard 对外暴露时必须启用 `OPEN_COMPOSER_DASHBOARD_TOKEN`。

## VPS 目录

推荐目录：

```text
/srv/open-composer/repo
/srv/open-composer/repo/.env
/srv/open-composer/repo/reports
/srv/open-composer/repo/projects
/srv/open-composer/repo/strategy_specs
```

推荐运行用户为 `opencomposer`。Dashboard 服务监听 `127.0.0.1:8000`，公网 HTTPS 入口由 Caddy 反代。

## 一键部署

在目标 VPS 上进入仓库：

```bash
cd /srv/open-composer/repo
./scripts/deploy-vps.sh
```

脚本会执行：

- `uv sync`
- `make deploy-prepare`
- `make dashboard-build`
- 生成或复用 `OPEN_COMPOSER_DASHBOARD_TOKEN`
- 写入 `.env` 并设置 `chmod 600`
- 生成 `open-composer-dashboard.service`
- 生成 Caddyfile
- 启动 / 重启 systemd 服务和 Caddy
- 验证 `/api/dashboard/health`
- 输出部署报告和 token 文件路径

部署报告位置：

```text
reports/deployment/vps-dashboard/plan.json
reports/deployment/vps-dashboard/plan.md
reports/deployment/vps-dashboard/generated-dashboard-token.txt
```

首次打开 Dashboard 时使用：

```text
https://<your-dashboard-domain>/?token=<OPEN_COMPOSER_DASHBOARD_TOKEN>
```

浏览器会把 token 存到 localStorage，之后正常访问域名即可。

## 常用命令

只生成计划，不改系统：

```bash
./scripts/deploy-vps.sh --plan --public-ip 203.0.113.10
```

使用自有域名：

```bash
./scripts/deploy-vps.sh --dashboard-url https://composer.example.com
```

系统目录需要 sudo：

```bash
./scripts/deploy-vps.sh --sudo --dashboard-url https://composer.example.com
```

轮换 Dashboard token：

```bash
./scripts/deploy-vps.sh --rotate-token
```

跳过部署后验证：

```bash
./scripts/deploy-vps.sh --no-verify
```

底层 CLI 入口：

```bash
uv run oc dashboard deploy-vps --apply --dashboard-url https://composer.example.com
```

## 停止服务

```bash
./scripts/stop-remote-dashboard.sh --remove-systemd --disable-caddy --remove-caddyfile
```

如果系统目录需要 sudo：

```bash
./scripts/stop-remote-dashboard.sh --sudo --remove-systemd --disable-caddy --remove-caddyfile
```

当 Caddy 同时服务其他站点时，不要传 `--disable-caddy` 或 `--remove-caddyfile`。

## 环境变量

必需或推荐：

```text
OPEN_COMPOSER_DASHBOARD_TOKEN=<random-token>
OC_DASHBOARD_ALLOWED_ORIGIN=https://composer.example.com
ALPACA_PAPER=true
```

可选：

```text
OPENAI_API_KEY=<optional>
OPENAI_BASE_URL=<optional>
OPENAI_MODEL=<optional>
ALPACA_API_KEY_ID=<optional-paper>
ALPACA_API_SECRET_KEY=<optional-paper>
TELEGRAM_BOT_TOKEN=<optional>
TELEGRAM_CHAT_ID=<optional>
```

Dashboard Settings 页面只显示 secret 是否存在，不显示 secret 值。

## 通知配置

Dashboard 支持 outbound-only Telegram 通知。实际配置文件 `config/notifications.yaml` 不入仓；示例文件在 `config/notifications.yaml.example`。

验证：

```bash
uv run oc notify status
uv run oc notify test --dry-run
```

Telegram 只用于向外发送通知；不实现 webhook、polling、callback 或聊天命令入口。

## 手动运行 Dashboard

```bash
cd /srv/open-composer/repo
uv run oc dashboard serve --host 127.0.0.1 --port 8000
```

本地调试可以不设 token；VPS 对外暴露必须设 `OPEN_COMPOSER_DASHBOARD_TOKEN`。

## 验证

```bash
uv run oc dashboard deploy-vps --dashboard-url https://composer.example.com
uv run oc repo check --strict
make verify
```
