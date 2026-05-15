# Open Composer Claude Code 兼容与 Vercel 远程命令 Dashboard 计划

日期：2026-05-14

## 状态

这份文档是对另一个 worktree 中同名计划的当前产品化修订版。它已经按用户确认的决策重写：

1. 不采用 read-only 优先路线；首个远程版本必须能执行受控命令。
2. Vercel 端使用 password session，等价于单用户登录。
3. 当前 Dashboard 支持的 paper、strategy、system 命令不默认禁用；高风险命令通过策略备份、双确认、readiness、audit 和 job 隔离控制。
4. 本文纳入当前 repo 文档白名单，后续实现必须同步 `repo_check`、测试和 README 索引。

## 本地执行收敛

本次落地按最小可运行闭环执行，不把 Dashboard 变成第二事实源：

- Codex / Claude parity 由 `CLAUDE.md`、`.claude/settings.json`、`.claude/commands/` 和 `scripts/check-agent-parity.py` 固化。
- `.claude/skills/` 必须由 `.agents/skills/` 生成；漂移会被 `repo_check` 和 `make agent-parity` 阻断。
- remote daemon 只暴露 catalog、command-plan、command-run、job、events 和 agent request，不暴露 shell 或任意文件 API。
- Vercel BFF 只处理 password session、CSRF、HMAC 和 proxy；所有任务执行仍在 daemon job 内完成。
- agent request 首版只是 `reports/agent_requests/<request_id>.json` 文件交接，不做云端 agent 托管。

## 产品裁定

Open Composer 仍是个人 AI 策略工作台，不是多人 SaaS、公开 API、云端 agent 托管平台或真金交易系统。

固定边界：

- `StrategySpec` 仍是策略行为源头。
- CLI 加文件产物仍是第一产品表面。
- Dashboard 是 read model 加受控 command surface，不是第二真相源。
- Alpaca Paper 是当前唯一自动化模拟盘写入通道；实盘 broker write 仍不在范围内。
- 所有命令必须回写 plan、job、result、audit 和必要报告。
- Vercel 不执行回测、pytest、参数扫描、Dashboard build 或任意 shell。
- 云服务器 daemon 不提供任意文件读取、任意路径写入或 shell API。

远程 Dashboard 会暴露策略、报告、paper 状态、命令计划和 job 日志，因此按“个人敏感控制面”处理。即使不接实盘，也不能把它当普通静态展示页。

## 当前事实

当前本地 Dashboard 已有这些可复用能力：

- `open_composer/dashboard/commands.py` 已提供 command plan、confirmation phrase、执行结果和 audit event。
- `open_composer/models/dashboard_command.py` 已定义 paper、strategy、system action schema。
- `open_composer/dashboard/server.py` 可本地提供 `/api/dashboard/catalog`、`command-plan` 和 `command-run`。
- React Dashboard 已能从 `/api/dashboard/catalog` 刷新 catalog，并调用 command API。

当前本地模式不能直接公网化：

- API token 只保护 `/api/dashboard/*`，静态资源不鉴权。
- 本地 server CORS 当前允许 `*`。
- 前端支持 `?token=` 并写入 `localStorage`。
- `command-run` 是同步执行，适合本地，不适合远程长任务。

结论：保留本地模式；新增 remote mode。remote mode 必须使用 Vercel session、BFF 代理、HMAC、job queue、backup 和 audit，不复用本地 server 直接暴露公网。

## 目标架构

```text
Browser
  -> Vercel Dashboard app
  -> Vercel API / BFF
  -> HMAC signed request
  -> Cloud server Open Composer remote daemon
  -> job queue
  -> existing DashboardCommandAction executor
  -> StrategySpec / reports / audit / backups
```

Codex 和 Claude Code 通过用户已有远程连接方式操作同一个 workspace。本计划不负责 agent 的远程连接，只负责让两类 agent 共享规则、技能和命令工作流。

## Claude Code 平级兼容

目标：Codex 和 Claude Code 都能完整操作 Open Composer，不维护两套互相漂移的研究纪律。

新增或修改：

- `CLAUDE.md`：Claude Code 项目入口，引用同一套产品规则。
- `.claude/settings.json`：允许项目必要命令，禁止或强确认 secrets、破坏性 git 和未确认 paper 操作。
- `.claude/skills/`：由 `.agents/skills/` 生成或镜像，不手写第二套。
- `.claude/commands/`：只封装 `uv run oc ...`、验证命令和安全审查命令。
- `scripts/sync-agent-skills.py`：从 repo skills 生成 Claude skills。
- `scripts/check-agent-parity.py`：检查 Codex / Claude 规则、skills 和命令模板是否漂移。
- `make agent-parity`：纳入本地验证。

共享规则必须覆盖：

- 策略设计必须输出 parameter ranges、method variants、factor variants 和 bounded search space。
- 新 required capability 必须先走 `capabilities/registry.yaml` 和 capability evaluation。
- 回测必须生成报告，信号必须先落日志。
- promotion 必须检查 benchmark family、OOS、walk-forward、成本、数据源敏感性和 sample/fallback caveat。
- LLM/news/event/macro 输入影响交易前必须先成为 point-in-time feature packet。
- 分开 `workflow_pass`、`research_pass`、`llm_contribution_pass`、`paper_ready_pass`。
- Dashboard 只能走 confirmed command surface。

## Password Session

这里的 password session 就是单用户登录：

1. 用户打开 Vercel URL。
2. 输入 Dashboard 密码。
3. Vercel server route 校验密码 hash。
4. Vercel 写入 HttpOnly、Secure、SameSite session cookie。
5. 浏览器之后只携带 cookie，不接触 daemon shared secret。

remote mode 禁止：

- `?token=` 登录。
- `localStorage` 保存 API token。
- 浏览器直接访问 daemon。
- 把 daemon shared secret 下发到前端。

session 要求：

- password hash 只存在 Vercel server 环境变量。
- session secret 只存在 Vercel server 环境变量。
- POST 请求使用 CSRF token 或等价的 same-origin nonce。
- 登录失败限速。
- 登出清 cookie。
- session cookie 轮换或设置合理过期时间。

## Vercel BFF

Vercel 负责：

- Dashboard 页面。
- password login / logout / session。
- API proxy。
- HMAC 签名。
- CSRF、rate limit、body size limit。
- 只允许用户浏览器访问 Vercel，不允许浏览器直连 daemon。

Vercel 不负责：

- 跑回测。
- 跑 scan。
- 跑参数扫描。
- 跑 pytest / ruff。
- 跑 Dashboard build。
- 写 repo 文件。
- 执行 shell。

建议 route：

```text
POST /api/login
POST /api/logout
GET  /api/session
GET  /api/dashboard/catalog
POST /api/dashboard/command-plan
POST /api/dashboard/command-run
GET  /api/dashboard/jobs/:id
GET  /api/dashboard/events
```

环境变量：

```text
OC_REMOTE_BASE_URL=https://oc-api.example.com
OC_REMOTE_SHARED_SECRET=<random-secret>
OC_DASHBOARD_PASSWORD_HASH=<password-hash>
OC_DASHBOARD_SESSION_SECRET=<random-secret>
OC_DASHBOARD_OWNER=owner
OC_DASHBOARD_ALLOWED_ORIGIN=https://<vercel-app-domain>
```

## HMAC 请求签名

Vercel 到 daemon 的每个非 health 请求都必须签名：

```text
X-OC-Timestamp
X-OC-Nonce
X-OC-Actor
X-OC-Body-SHA256
X-OC-Signature
```

canonical string：

```text
METHOD
PATH
TIMESTAMP
NONCE
ACTOR
BODY_SHA256
```

daemon 验证：

- timestamp 在短窗口内。
- nonce 在 TTL 内未使用过。
- body hash 匹配。
- signature 正确。
- actor 是允许的 owner。
- request body 未超过大小限制。

nonce store 可以先用本地文件或 sqlite。重启后至少不能接受明显过期 timestamp；P1 再做持久化清理。

## Remote Daemon

新增模块：

```text
open_composer/remote/auth.py
open_composer/remote/jobs.py
open_composer/remote/backups.py
open_composer/remote/schemas.py
open_composer/remote/server.py
```

新增 CLI：

```bash
uv run oc remote serve --host 127.0.0.1 --port 8787
uv run oc remote job-list
uv run oc remote job-status <job-id>
uv run oc remote doctor
```

daemon API：

```text
GET  /health
GET  /dashboard/catalog
POST /dashboard/command-plan
POST /dashboard/command-run
GET  /dashboard/jobs/{job_id}
GET  /dashboard/events
```

实现要求：

- `/health` 不泄露路径、环境变量或 repo 内容。
- 除 `/health` 外全部 HMAC 验签。
- 不接受任意 shell。
- 不接受任意 file path API。
- command-run 必须异步创建 job，不同步执行。
- job worker 并发默认为 1。
- 每个 job 有 timeout、started_at、finished_at、actor、request_id。
- workspace 写操作加 lock，避免 Codex / Claude / daemon 同时改同一策略。

job 状态：

```text
queued -> running -> executed | blocked | failed | timed_out
```

job 文件：

```text
reports/dashboard/jobs/<job_id>.json
reports/dashboard/jobs/<job_id>.log
reports/dashboard/jobs/events.jsonl
```

## 命令执行策略

首个远程版本直接支持执行命令，不走 read-only 试运行阶段。

remote daemon 允许当前 `DashboardCommandAction` 中的全部 action：

- `paper.status.refresh`
- `paper.monitor.refresh`
- `paper.sync.orders`
- `paper.sync.account`
- `paper.kill_switch.enable`
- `paper.kill_switch.clear`
- `system.prepare_workspace`
- `system.readiness.refresh`
- `strategy.draft`
- `strategy.workflow.verify`
- `strategy.validate`
- `strategy.capabilities.refresh`
- `strategy.approve`
- `strategy.activate.manual`
- `strategy.activate.paper_auto`
- `strategy.backtest.rerun`
- `strategy.scan.rerun`
- `strategy.disable`

仍然始终禁止：

- 任意 shell command。
- 实盘 broker write。
- 任意路径读取或写入。
- 读取 `.env`、`.env.*`、private keys、remote secret。
- 破坏性 git。
- 绕过 readiness 的 paper automation。
- 在 backtest / paper loop 内实时调用 LLM。

风险分层：

| 等级 | Actions | 额外控制 |
|---|---|---|
| Green | `catalog`、`health`、`paper.status.refresh`、`system.readiness.refresh`、`strategy.validate`、`strategy.capabilities.refresh` | HMAC、session、audit、job |
| Yellow | `system.prepare_workspace`、`strategy.draft`、`strategy.workflow.verify`、`strategy.backtest.rerun`、`strategy.scan.rerun`、`paper.monitor.refresh`、`paper.sync.orders`、`paper.sync.account` | job lock、timeout、pre-job backup、confirmation phrase |
| Red | `strategy.approve`、`strategy.activate.manual`、`strategy.activate.paper_auto`、`strategy.disable`、`paper.kill_switch.enable`、`paper.kill_switch.clear` | pre-job strategy backup、double confirmation、readiness/paper gates、audit reason 必填 |

Red action 不默认禁用，但必须有更强确认：

- 用户输入原有 confirmation phrase。
- 用户再输入 action-specific phrase，例如 `CONFIRM REMOTE STRATEGY MUTATION` 或 `CONFIRM REMOTE PAPER CONTROL`。
- UI 展示受影响 strategy、spec hash、data_source、paper readiness、backup path 和预计输出。
- job result 回写 backup manifest、command result 和 audit event。

## 策略备份

任何 Yellow / Red command-run 执行前都必须创建备份。

备份目录：

```text
reports/backups/remote/<job_id>/
```

最小备份内容：

- `manifest.json`：actor、action、job_id、command_id、timestamp、git commit、dirty flag、affected paths、spec hash。
- `strategy_specs/`：执行前完整策略 specs 快照，至少包含目标 strategy 和 lifecycle 相关目录。
- `reports/dashboard/commands/<command_id>.json`：执行前 command plan。
- `git-status.txt`。
- `git-diff.patch`。
- 对 Red action，额外保存目标 StrategySpec 的独立 `.before.yaml`。

恢复原则：

- 备份只保证文件级恢复证据，不自动执行 rollback。
- 后续可增加 `oc remote backup-list` 和 `oc remote backup-restore --dry-run`，但首版不提供浏览器一键回滚。
- backup manifest 必须出现在 job result 和 audit event 中。

## Dashboard 前端改造

remote mode 必须新增：

- login page。
- session status。
- deployment mode badge：
  - `Local`
  - `Remote Commands Enabled`
- command plan preview。
- double confirmation modal。
- job status panel。
- backup path display。
- audit/result/output path links。
- command execution history。

remote mode 必须移除：

- query token 登录。
- localStorage token。
- 直接请求 daemon base URL。

按钮必须清楚显示：

- action。
- risk level。
- warnings。
- confirmation phrase。
- affected strategy。
- current spec hash。
- readiness status。
- backup requirement。
- job timeout。

失败态优先展示：

- 未登录。
- session 过期。
- HMAC 被拒。
- nonce replay。
- confirmation 错误。
- backup 创建失败。
- readiness 阻断。
- job timed out。
- workspace lock 被占用。

## 云服务器部署

建议目录：

```text
/srv/open-composer/repo
/srv/open-composer/repo/.env
/srv/open-composer/repo/reports
/srv/open-composer/repo/strategy_specs
```

运行用户：

```text
opencomposer
```

启动：

```bash
cd /srv/open-composer/repo
uv run oc remote serve --host 127.0.0.1 --port 8787
```

公网入口：

```text
https://oc-api.example.com -> 127.0.0.1:8787
```

要求：

- daemon 不用 root 跑。
- daemon 只监听 `127.0.0.1`。
- Caddy 或 Nginx 做 HTTPS reverse proxy。
- `.env` 权限 `0600`。
- 只开放 443 和 SSH。
- SSH 使用 key。
- request body 限制。
- job 并发限制。
- 所有 command、job、backup、result、event 写 audit。

## 实施阶段

### P0：文档与规则入库

交付：

- 本文档。
- `repo_check.CURRENT_DOCS` 更新。
- README Project Docs 更新。
- `tests/test_repo_check.py` 更新。

验收：

```bash
uv run oc repo check --strict
uv run pytest tests/test_repo_check.py
```

### P1：Claude Code 平级兼容

交付：

- `CLAUDE.md`
- `.claude/settings.json`
- `.claude/skills/`
- `.claude/commands/`
- `scripts/sync-agent-skills.py`
- `scripts/check-agent-parity.py`
- `make agent-parity`

验收：

```bash
uv run python scripts/check-agent-parity.py
uv run ruff check .
uv run pytest
```

### P2：可执行 remote daemon

交付：

- HMAC auth。
- nonce/timestamp/body hash 校验。
- async job queue。
- workspace lock。
- strategy backup。
- `oc remote serve`。
- `oc remote job-list`。
- `oc remote job-status`。
- `oc remote doctor`。
- 所有当前 `DashboardCommandAction` 可通过 signed remote request 创建 job 执行。

验收：

- 签名错误拒绝。
- timestamp 过期拒绝。
- nonce replay 拒绝。
- body hash 错误拒绝。
- unknown action 拒绝。
- path traversal 拒绝。
- confirmation 错误 blocked。
- Yellow / Red action 缺 backup 时 blocked。
- Red action 缺 double confirmation 时 blocked。
- `strategy.activate.paper_auto` 仍受 paper readiness 阻断。
- job 成功写 result、log、backup manifest 和 audit event。

### P3：Vercel Dashboard 命令执行

交付：

- password login/logout/session。
- catalog proxy。
- command-plan proxy。
- command-run proxy。
- job-status proxy。
- events proxy。
- remote login UI。
- remote command modal。
- job status UI。
- backup path UI。
- remote mode 禁用 query token。

验收：

- 未登录不能访问 Dashboard API。
- 登录后可读 catalog。
- 可生成 command plan。
- 可执行 `system.readiness.refresh` 并获得 job id。
- 可执行 `strategy.validate` 并看到 result。
- Red action 必须展示 backup、readiness 和双确认。
- 浏览器看不到 daemon secret。

### P4：部署模板与 remote readiness

交付：

- `deploy/remote/systemd/open-composer-remote.service`
- `deploy/remote/Caddyfile.example` 或 Nginx example。
- `docs/remote-dashboard-deploy.zh.md`，若进入 `docs/` 必须同步白名单。
- `.env.example` remote variables。
- `oc remote doctor` 纳入 readiness。

验收：

- daemon 非 root。
- daemon 不直接监听公网。
- `.env` 权限检查可报告 warning/blocked。
- remote readiness 能检查 Vercel env、daemon health、HMAC、backup dir、job dir、workspace lock。

### P5：Dashboard 到 agent 的任务交接

交付：

- `reports/agent_requests/<request_id>.json` schema。
- Dashboard 创建 agent request。
- Codex / Claude Code skills 可读取 agent request。
- agent 完成后写 result link。

验收：

- 长参数扫描和复杂优化不由 Vercel function 跑。
- Dashboard 只创建受控 request。
- agent result 回链到 reports、jobs 和 audit。

## 多视角复审

| 视角 | 结论 | 对计划的约束 |
|---|---|---|
| 产品 | 用户明确要远程可执行命令；不能先做只有展示价值的 read-only 阶段 | P2/P3 直接交付 command-run job |
| 安全 | 远程命令面比本地 Dashboard 高一个风险等级 | password session、HMAC、CSRF、job、backup、double confirmation 都是首版要求 |
| 量化工作流 | 远程按钮不能绕过 `StrategySpec`、capability、feature packet、readiness | 继续复用 existing DashboardCommandAction 和 paper readiness |
| 工程 | 不能把 Vercel Functions 当任务执行器 | Vercel 只做代理和登录；daemon 执行 job |
| 运维 | 单用户也需要恢复路径 | 每个 Yellow / Red action 执行前写策略备份 |
| Agent 协作 | Codex / Claude Code 平级兼容不能导致规则分裂 | skills 生成、parity check、shared command workflow |

## 不做事项

近期不做：

- 多用户系统。
- RBAC / tenant isolation。
- 实盘交易。
- 在线 IDE。
- 浏览器任意 shell。
- Vercel 直接跑策略研究。
- 公开 API。
- 云端 agent 托管平台。
- 一键浏览器 rollback。
- 把 Dashboard 做成策略行为事实源。

## 最小成功标准

第一版可接受交付必须满足：

1. 用户打开 Vercel URL。
2. 用户用 password session 登录。
3. Dashboard 显示云服务器 catalog。
4. 用户远程生成 command plan。
5. 用户输入 confirmation phrase。
6. 对 Red action，用户输入 double confirmation。
7. daemon 创建 backup。
8. daemon 创建 job。
9. job 执行已有 DashboardCommandAction。
10. job 写 result、log、backup manifest 和 audit event。
11. Dashboard 显示 job status、result、backup path 和最新 catalog。
12. Codex 与 Claude Code 都能继续操作同一个 Open Composer workspace。

## 官方文档校准

- Claude Code 使用 `CLAUDE.md`、settings、hooks 和 skills 承载项目级规则与扩展能力；因此本计划选择共享规则源和 skill parity，而不是手写两套 agent 说明。
- Vercel Functions 有运行时间和请求体限制；因此本计划不让 Vercel 执行回测、pytest、扫描或长任务。
- Vercel Deployment Protection 可作为外层保护选项，但本计划仍实现应用内 password session，因为用户确认可接受类似登录的体验。
