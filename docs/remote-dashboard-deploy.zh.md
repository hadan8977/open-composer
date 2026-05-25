# Open Composer 远程 Dashboard 部署说明（暂停）

日期：2026-05-22

## 结论

当前阶段远程 Dashboard 部署已暂停，不作为产品主线、验收项或日常使用前提。Open Composer 的当前标准使用方式是：

```text
localhost Dashboard
  -> 本地 StrategySpec / projects / reports
  -> CLI + Codex / Claude Code work session
```

下面的 VPS / Cloudflare Access 内容只保留为未来可选方案和历史参考。恢复远程访问前，需要重新显式评估安全边界、认证方式和部署脚本。

历史 VPS 方案的边界是：**VPS 直接托管 Dashboard，策略研究和执行仍然保持本地 / CLI / 文件优先**。

不再把 Vercel 作为正常产品路径。旧的 Vercel BFF / remote daemon 代码只保留为遗留兼容，不作为新部署入口。

如果未来恢复手机和异地访问，优先重新评估 **Cloudflare Tunnel + Cloudflare Access**。该模式不暴露 Dashboard 端口：Cloudflare 通过出站 tunnel 访问 VPS 本机 `127.0.0.1:8000`，用户在浏览器中通过 Cloudflare Access 登录。

## 架构边界

```text
Browser
  -> HTTPS Dashboard through Cloudflare Access
  -> Cloudflare Tunnel
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
- Dashboard 对外暴露时必须启用 `OPEN_COMPOSER_DASHBOARD_TOKEN` 或 `OPEN_COMPOSER_DASHBOARD_AUTH_MODE=cloudflare_access`。

## 推荐远程访问：Cloudflare Access

适合手机和异地访问的推荐路径：

```text
Phone / Browser
  -> https://dashboard.example.com
  -> Cloudflare Access policy
  -> Cloudflare Tunnel
  -> http://127.0.0.1:8000
  -> Open Composer Dashboard
```

VPS 不需要开放 Dashboard 公网端口；只需要 `cloudflared` 主动出站连接 Cloudflare。

Dashboard 支持三种认证模式：

```text
OPEN_COMPOSER_DASHBOARD_AUTH_MODE=token
OPEN_COMPOSER_DASHBOARD_AUTH_MODE=cloudflare_access
OPEN_COMPOSER_DASHBOARD_AUTH_MODE=cloudflare_access_or_token
```

生产推荐：

```text
OPEN_COMPOSER_DASHBOARD_AUTH_MODE=cloudflare_access
OC_DASHBOARD_ALLOWED_ORIGIN=https://dashboard.example.com
OC_CLOUDFLARE_ACCESS_TEAM_DOMAIN=https://<team>.cloudflareaccess.com
OC_CLOUDFLARE_ACCESS_AUD=<Access application AUD tag>
OC_DASHBOARD_ALLOWED_EMAILS=you@example.com
```

`cloudflare_access` 模式会验证 Cloudflare Access 注入的 `Cf-Access-Jwt-Assertion` JWT，并要求 JWT 邮箱命中 `OC_DASHBOARD_ALLOWED_EMAILS`。不要把 Dashboard 直接绑定到 `0.0.0.0`；继续让 `oc dashboard serve` 监听 `127.0.0.1:8000`。

迁移期可用：

```text
OPEN_COMPOSER_DASHBOARD_AUTH_MODE=cloudflare_access_or_token
OPEN_COMPOSER_DASHBOARD_TOKEN=<fallback-token>
```

该模式允许 Cloudflare Access 或 Dashboard token 任一通过，用于回滚和本机诊断；稳定后改回 `cloudflare_access`。

## VPS 目录

推荐目录：

```text
/srv/open-composer/repo
/srv/open-composer/repo/.env
/srv/open-composer/repo/reports
/srv/open-composer/repo/projects
/srv/open-composer/repo/strategy_specs
```

推荐运行用户为 `opencomposer`。Dashboard 服务监听 `127.0.0.1:8000`，公网 HTTPS 入口由 Cloudflare Tunnel 提供。VPS 不需要开放 `8000`、`8443` 或任何 Dashboard 反代端口。

## 一键部署本地 Dashboard 服务

在目标 VPS 上进入仓库：

```bash
cd /srv/open-composer/repo
./scripts/deploy-vps.sh --cloudflare-access --dashboard-url https://dashboard.example.com
```

脚本会执行：

- `uv sync`
- `make deploy-prepare`
- `make dashboard-build`
- 写入 `OPEN_COMPOSER_DASHBOARD_AUTH_MODE=cloudflare_access`
- 写入 Cloudflare Access origin JWT 校验变量
- 写入 `.env` 并设置 `chmod 600`
- 生成 `open-composer-dashboard.service`
- 启动 / 重启 systemd 服务
- 验证本机 `http://127.0.0.1:8000/`
- 输出部署报告

部署报告位置：

```text
reports/deployment/vps-dashboard/plan.json
reports/deployment/vps-dashboard/plan.md
```

随后在 Cloudflare Zero Trust 中创建 Tunnel，把 public hostname `dashboard.example.com` 指到 VPS 本机服务 `http://127.0.0.1:8000`。用户访问 `https://dashboard.example.com` 时先通过 Cloudflare Access 登录，origin 再验证 Cloudflare 注入的 JWT。

## 常用命令

只生成计划，不改系统：

```bash
./scripts/deploy-vps.sh --plan --public-ip 203.0.113.10
```

推荐 Cloudflare Access：

```bash
./scripts/deploy-vps.sh \
  --cloudflare-access \
  --dashboard-url https://dashboard.example.com \
  --cloudflare-team-domain https://<team>.cloudflareaccess.com \
  --cloudflare-aud <Access application AUD tag> \
  --allowed-emails you@example.com
```

如果 `OC_CLOUDFLARE_ACCESS_TEAM_DOMAIN`、`OC_CLOUDFLARE_ACCESS_AUD` 和 `OC_DASHBOARD_ALLOWED_EMAILS` 已写入 `.env` 或当前 shell，可以省略后三个参数。

旧 token/Caddy 兼容模式：

```bash
./scripts/deploy-vps.sh --dashboard-url https://composer.example.com
```

系统目录需要 sudo：

```bash
./scripts/deploy-vps.sh --sudo --cloudflare-access --dashboard-url https://dashboard.example.com
```

跳过部署后验证：

```bash
./scripts/deploy-vps.sh --no-verify
```

底层 CLI 入口：

```bash
uv run oc dashboard deploy-vps --apply --dashboard-url https://composer.example.com
uv run oc dashboard deploy-vps --apply --cloudflare-access --dashboard-url https://dashboard.example.com
```

## 停止服务

```bash
./scripts/stop-remote-dashboard.sh --remove-systemd
```

如果系统目录需要 sudo：

```bash
./scripts/stop-remote-dashboard.sh --sudo --remove-systemd
```

Cloudflare Tunnel 模式不安装 Open Composer Caddyfile；只有旧 token/Caddy 兼容模式才需要 `--disable-caddy` 或 `--remove-caddyfile`。

## 环境变量

必需或推荐：

```text
OPEN_COMPOSER_DASHBOARD_AUTH_MODE=cloudflare_access
OC_DASHBOARD_ALLOWED_ORIGIN=https://dashboard.example.com
OC_CLOUDFLARE_ACCESS_TEAM_DOMAIN=https://<team>.cloudflareaccess.com
OC_CLOUDFLARE_ACCESS_AUD=<Access application AUD tag>
OC_DASHBOARD_ALLOWED_EMAILS=you@example.com
ALPACA_PAPER=true
```

迁移 / 调试时可增加 token fallback：

```text
OPEN_COMPOSER_DASHBOARD_AUTH_MODE=cloudflare_access_or_token
OPEN_COMPOSER_DASHBOARD_TOKEN=<random-token>
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

本地调试可以不设 token；远程访问必须使用 Cloudflare Access 或 token fallback。

Cloudflare Access 模式下，本地服务仍监听 `127.0.0.1:8000`；公网入口由 Cloudflare Tunnel 提供，不使用 Caddy 公网反代。

## 验证

```bash
uv run oc dashboard deploy-vps --cloudflare-access --dashboard-url https://dashboard.example.com
uv run oc repo check --strict
make verify
```
