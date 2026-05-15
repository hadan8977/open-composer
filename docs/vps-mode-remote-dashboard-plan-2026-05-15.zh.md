# Open Composer VPS 模式远程 Dashboard 计划与 Review

日期：2026-05-15

## 目标

新增一个明确的 VPS 模式，让用户已经在 VPS 上运行 Codex 时，只需要提供
`VERCEL_TOKEN`，就能自动生成 Open Composer Remote Dashboard 所需的本机
daemon 配置、Vercel BFF 环境变量和生产部署。

目标命令形态：

```bash
VERCEL_TOKEN=<token> uv run oc remote bootstrap-vps --apply --generate-password
```

默认保持 dry run，只有显式 `--apply` 才写入 `.env`、调用 Vercel CLI、安装或
刷新本机服务配置。dry run 必须输出部署计划和敏感信息占位，不泄露 secret。

## 当前事实

当前远程架构已经存在：

- `oc remote serve`：HMAC 保护的 remote daemon。
- `dashboard/api/*`：Vercel password-session BFF。
- `dashboard/lib/remote.js`：session、CSRF、HMAC proxy。
- `deploy/remote/systemd/open-composer-remote.service`：systemd 模板。
- `deploy/remote/Caddyfile.example`：Caddy 反代模板。
- `docs/remote-dashboard-deploy.zh.md`：手动部署说明。

当前缺口：

- secret 需要用户手工生成和复制。
- daemon URL、Vercel URL、allowed origin 需要手工串起来。
- Caddy/systemd 只有模板，没有项目内 bootstrap 命令。
- Vercel 项目、环境变量和 production deploy 没有自动化入口。
- `remote doctor` 只检查 daemon 本地前置条件，不说明 VPS 模式的部署状态。

## 可行性 Review

### 可行

VPS 模式可行，原因如下：

1. **Vercel token 足够处理 Dashboard/BFF 侧**
   Vercel CLI 可以在非交互模式下通过 token 完成 project link、环境变量写入和
   production deploy。项目的 `dashboard/` 已经是可独立部署的 Vite + API
   functions 目录。

2. **daemon 已经是独立长期进程**
   `oc remote serve --host 127.0.0.1 --port 8787` 已满足 VPS 常驻运行模型。
   systemd 和 Caddy 模板只需要被参数化并安装。

3. **secret 可以由本机安全生成**
   `OC_REMOTE_SHARED_SECRET`、`OC_DASHBOARD_SESSION_SECRET`、dashboard 登录
   密码和 PBKDF2 hash 都可以由 CLI 生成。用户不需要手工计算。

4. **没有自定义域名时可以使用 VPS 公网 IP 域名方案**
   命令可以自动探测 VPS 公网 IPv4，并默认使用
   `https://<ip>.sslip.io` 作为 daemon URL。长期生产环境仍建议换成用户自己的域名。

### 不可省略的边界

1. **不能让 Vercel 执行 Open Composer 命令**
   Vercel 仍只做 password session、CSRF、HMAC 和 proxy。回测、scan、pytest、
   文件写入和 paper 控制继续只在 VPS daemon job 中执行。

2. **浏览器不能接触 shared secret**
   `OC_REMOTE_SHARED_SECRET` 只在 Vercel server env 和 VPS daemon env 中存在。

3. **daemon 不能直接绑定公网接口**
   daemon 必须监听 `127.0.0.1:8787`，公网 HTTPS 由 Caddy/Nginx 反代。

4. **系统级安装必须显式 apply**
   写 `/etc/caddy/Caddyfile`、安装 systemd unit、启动服务属于 VPS 系统变更。
   dry run 只生成计划；`--apply` 才执行。

5. **Vercel token 不能替代 DNS 所有权**
   默认 `sslip.io` 可以避免自定义 DNS。若用户要使用自己的域名，仍需要该域名
   DNS 指向 VPS。

## 实现计划

### P1：部署计划模型

新增 `open_composer/remote/bootstrap.py`：

- 生成 secret 和 PBKDF2 password hash。
- 推导 daemon URL：
  - 用户传入 `--daemon-url` 优先。
  - 传入 `--public-ip` 时生成 `https://<public-ip>.sslip.io`。
  - apply 且未传入时自动请求公网 IP。
- 推导 Vercel origin：`https://<project>.vercel.app`。
- 渲染 daemon `.env`、systemd unit、Caddyfile、Vercel env。
- 输出 JSON/Markdown plan 到 `reports/deployment/vps-bootstrap/`。

### P2：CLI

新增命令：

```bash
uv run oc remote bootstrap-vps
uv run oc remote bootstrap-vps --apply --generate-password
uv run oc remote bootstrap-vps --apply --daemon-url https://oc-api.example.com
```

关键选项：

- `--vercel-token`：默认读取 `VERCEL_TOKEN`。
- `--vercel-project`：默认 `open-composer-dashboard`。
- `--daemon-url`：自定义 daemon HTTPS URL。
- `--public-ip`：手工指定 VPS 公网 IPv4，用于生成 `sslip.io` URL。
- `--dashboard-password` 或 `--generate-password`。
- `--apply`：执行本地写入和 Vercel 部署。
- `--skip-system`：不写 systemd/Caddy，只配置 `.env` 和 Vercel。
- `--skip-vercel`：只配置 VPS 本地 daemon。

### P3：执行器

apply 时执行：

1. `make deploy-prepare`
2. 写入或更新 `.env` 中 remote 变量，并 `chmod 600 .env`
3. 生成 `reports/deployment/vps-bootstrap/open-composer-remote.service`
4. 生成 `reports/deployment/vps-bootstrap/Caddyfile`
5. 可选安装 systemd unit 和 Caddyfile
6. `uv run oc remote doctor`
7. Vercel link/env/deploy
8. 写部署结果报告

### P4：测试

测试必须覆盖：

- secret/hash 生成格式。
- daemon URL 推导。
- `.env` 合并不破坏已有变量。
- dry run 不泄露 raw secret。
- plan JSON/Markdown 输出。
- Vercel CLI 命令计划可检查但不真正访问网络。
- repo check 同步新文档。

## 验收

本功能完成后必须运行：

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
uv run oc repo check --strict
uv run oc remote bootstrap-vps --public-ip 203.0.113.10 --generate-password
```

若依赖和时间允许，再运行：

```bash
make verify
```

## Review 结论

该计划可行，但必须把“自动化”和“安全边界”同时落地。正确产品形态不是把本地
Dashboard 直接暴露公网，而是在 VPS 上自动装配现有 remote daemon、Caddy、
systemd 和 Vercel BFF。

MVP 可以做到用户只提供 `VERCEL_TOKEN`，其余 secret 自动生成。自定义域名、
长期 DNS、系统包安装失败恢复、Vercel team scope 等作为参数化能力处理，不作为
默认阻断项。
