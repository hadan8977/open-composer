# 计划 Step 18：只读 Cockpit（拆掉旧 Dashboard，重做一个）— 2026-09-19

> **这份文档写给没有上下文的执行者（Sonnet）。** 每个任务自带背景、文件清单、验收命令。
> 不要去读其它 plan 文档，不要自己扩大范围。任何与本文冲突的旧规则，以本文为准，并按第 9 节同步改掉规则原文。

## 0. 一句话

把 `open_composer/dashboard/` 里的界面、命令执行、密码会话、VPS 部署全部删掉，保留其中的数据聚合层；
在它的位置上建一个**纯只读**的 Web cockpit：FastAPI + Jinja2 + HTMX/SSE，服务端渲染，无 node 构建，
只绑 `127.0.0.1`，鉴权完全交给前面的 Cloudflare Access。

## 1. 为什么要做（背景，执行者需要知道的最小集）

机主一个人在一台 3.9GB 内存的 VPS 上跑这个项目：AI agent 全天做量化策略研究，同时有 4 个策略在一个 Alpaca 模拟账户上自动下单。
他平时通过手机远程连过来，只能靠打断 agent 问"你在干什么 / 进展如何 / 额度还剩多少"来了解状态。
Cockpit 的唯一目的是**把这些询问固化成页面**，让他不用打断。发指令仍然走他现有的工具（Paseo），cockpit 不承担任何指令入口。

调研结论（六份情报在 `reports/research/intel/I-20260919-0{1..6}-*.md`，不需要重读）：
市面上的执行侧看板（Freqtrade / OpenAlgo / Hummingbot 等）都绑着自己的下单引擎，研究侧 UI（RD-Agent / TradingAgents 等）都是"跑一次看一次"的单次任务视图，
**没有任何成熟产品把"跨天的假设 → 试验 → 门槛 → 证伪"当成一等公民**。所以这一块必须自建，只借它们的通用部件。

## 2. 已定的决策（不要重新讨论、不要替换）

| 项 | 决定 | 依据 |
|---|---|---|
| 栈 | FastAPI + Jinja2 + HTMX/SSE 服务端渲染 | `I-20260919-04`：单进程 50–80MB、原生 SSE、直接读文件、无需建库。Grafana/Metabase/Superset 因内存出局，Streamlit/Panel/Reflex 因"会话内存不释放"出局 |
| 前端构建 | **不引入 node 构建链**。模板 + 手写 CSS + 少量原生 JS | 机器上已有一个 162MB 的 node_modules 要删，不要再造一个 |
| 图表 | 服务端生成 inline SVG（直方图、热力图、水下回撤、迷你曲线）；仅"净值曲线"用 vendored uPlot（MIT，约 45KB，直接放进 `static/vendor/`） | 同上；uPlot 是单文件，不需要构建 |
| 鉴权 | 应用内**零鉴权代码**，只监听 `127.0.0.1:8770`，由 Cloudflare Access 在边缘鉴权 | 机主 2026-09-19 选择；应用不碰凭证 = 安全面最小 |
| 写操作 | **整个应用没有任何 POST/PUT/PATCH/DELETE 路由** | 机主要求；也是这个方案安全性的根据 |
| 推送通知 | **不做** | 机主 2026-09-19 明确说不需要 |
| 主屏 | 假设卡看板 | 机主 2026-09-19 |
| 终端 | 手机和电脑都要，关键屏做两套布局而不是等比缩放 | 机主 2026-09-19 |
| Codex 额度 | 本机 Codex 现在是 `auth_mode: apikey`（走本地代理池），**没有订阅额度可读**。读取层要把接口留好，但现在不切换登录方式，面板如实显示"按量计费 / 无订阅额度" | 机主 2026-09-19 |
| 旧 dashboard | 拆干净，但 `catalog.py` 搬家保留 | 见第 3 节 |

## 3. 拆除清单，以及为什么顺序不能反

`open_composer/dashboard/` 共 8,234 行，**其中 2,753 行的 `catalog.py` 不是界面代码**，它是全仓库的数据聚合层
（策略、版本、运行、信号、订单、模拟盘持仓、研究报告、项目、因子、审计），被 `readiness.py`、`deployment.py` 和 8 个测试文件依赖。
先删包再建新的会立刻打掉 `make readiness` 和 `make deploy-prepare`。所以顺序必须是：**先搬家，再删，删掉的东西连同它的检查一起删**，这样 `make verify` 在每一步之后都是绿的。

**保留并搬家**：`catalog.py` → `open_composer/cockpit/data/catalog.py`（内容不改，只改导入路径和包名）。

**删除**（Python，合计约 5,442 行）：`server.py`(2350)、`html.py`(1246)、`commands.py`(725)、`auth.py`(111)、`vps_deploy.py`(1010)。

**删除**（前端）：整个 `dashboard/` 目录，54 个受版本控制的文件 + `node_modules`（162MB）+ `dist/`。

**删除**（周边）：
- `oc dashboard` 的 7 个子命令（`cli.py` 中 `catalog` / `review-plan` / `html` / `serve` / `deploy-vps` / `command-plan` / `command-run`）；其中 `catalog` 以 `oc cockpit index` 的名义保留等价能力。
- `open_composer/models/dashboard_command.py` 与 `repo_check.py` 里的 `_dashboard_command_model_check`。
- `Makefile` 的 `dashboard-catalog` / `dashboard-html` / `dashboard-build` / `dashboard-dev` / `dashboard-serve` / `dashboard-check` 六个目标、`bootstrap` 里的 `npm --prefix dashboard install`、`verify` 链里的 `dashboard-check`。
- `deploy/remote/systemd/open-composer-dashboard.service`、`deploy/remote/Caddyfile.example`、`scripts/deploy-vps.sh`、`scripts/stop-remote-dashboard.sh`、`Makefile` 的 `vps-plan/vps-deploy/vps-stop`。
- 测试：`test_dashboard_server.py`、`test_dashboard_commands.py`、`test_dashboard_cli_parity.py`、`test_vps_dashboard_deploy.py` 整文件删除；
  `test_dashboard_catalog.py`、`test_readiness.py`、`test_deployment.py`、`test_feature_validation.py`、`test_factor_decay.py`、`test_strategy_projects.py`、`test_strategy_lifecycle_and_runner.py`、`test_strategy_versions_and_capability_expansion.py`、`test_alpaca_paper.py` 只改导入路径。
- `readiness.py` 里的 `dashboard_bundle` 检查项和 `dashboard_auth_mode` / `dashboard_api_token` / `dashboard_allowed_emails` 相关检查一并删除（应用不再有鉴权层）；`dashboard_catalog` 检查项改名 `cockpit_catalog` 保留。
- `deployment.py` 里 `write_dashboard_html` 那一步删除，`build/write_dashboard_catalog` 改指向新包。

## 4. 信息架构（五屏 + 常驻顶栏）

**常驻顶栏**（每一屏都在，手机上折叠成一行图标 + 可展开）：
- Claude 额度：5 小时窗和 7 天窗两条进度条 + 重置倒计时 + **按当前燃烧速率推算的撞线时间**（抄 `futin/claude-agents-dashboard`）。
- Codex：显示"按量计费 / 无订阅额度"，接口留好（见 T6）。
- agent 状态点：每个活着的 agent 一个点，颜色 = running / idle / error。
- 数据新鲜度红绿灯、彩排授权到期倒计时（现有两份授权分别到 2026-09-29 与 2026-10-02，过期会静默停掉，倒计时必须醒目）。

**屏 1 · 假设卡看板（默认首屏）**
泳道：`预注册` / `在跑` / `完成·已上线` / `完成·否定` / `搁置` / `未分类`。
每张卡显示：卡号、标题、上一环、状态芯片、**预注册判定标准 vs 实际数字并排**（这是整个 cockpit 最重要的一块）、门槛通过/拒绝徽标、一行证伪说明。
布局范式抄 `henryzhangpku/autonomous-quant-researcher`，状态芯片用 discovery / validation / holdout 三段式。
解析不确定的卡进 `未分类` 泳道并显示原因，**绝不静默丢卡**。

**屏 2 · 研究血统图**
节点 = 假设卡。节点颜色 = 结局。点击节点跳卡片详情。手机上退化成缩进列表（不要在手机上画力导向图）。

边有**两种，必须分开画、分开标注**：
- **实线 = 显式"上一环"**。2026-09-19 实测：20 张卡里只有 1 张写了这个字段，所以单靠它画不出图。这是事实，不是解析器的缺陷。
- **虚线 = 正文里的卡号引用**（正则扫 `[HD]-\d{8}-\d{2}`，排除卡片自身）。这是弱关系，可能只是"提到"而不是"承接"。

把弱关系当成因果画成实线就是在编造研究脉络，禁止。今后新卡应写 `上一环：`，图会自动变强。

**屏 3 · agent 活动**
每个 agent 一张卡：provider / 模型 / 状态 / 已运行时长 / 当前在读的文件 / 最近一条思考摘要。
展开 = SSE 跟随该会话的思考流与工具调用，抄 QuantDinger 的"可审计决策时间线"部件形态（谁 / 做了什么 / 结果 / 耗时 / 原因）。
另有"当前重活"区：`run_capped.sh` 起的任务，显示内存上限、已运行时长、日志尾部。

**屏 4 · 模拟盘**
总览 = 四个 sleeve 汇总（抄 FreqUI 多 bot 汇总），点进去是单个策略明细。
每个 sleeve：权益曲线（含未实现盈亏，抄 Freqtrade Wallet Balance）、目标权重 vs 实际持仓、成交率与滑点（数据已在 `*-fills-summary.md`）、订单流水、授权状态。
组织原则：**"策略"是贯穿全站的一等维度**（抄 OpenAlgo），不按标的堆数据。

**屏 5 · 健康**
cron 每条任务的上次运行时间与退出码、数据新鲜度（SIP 归档、内部人、空头、因子表各自的最新日期）、磁盘、内存、最近的错误日志尾部。
布局抄 OpenAlgo 的 Traffic/Latency Monitor：总量 + 错误数 + 平均耗时 + 维度过滤，极简。

**详情页 · 卡片 / 回测**
卡片详情 = 卡片 markdown 渲染 + 该卡的试验表格 + **安慰剂分布 vs 真值图**（inline SVG 直方图，真值画一条竖线）+ 试验预算条
（视觉上和顶栏的额度条一样，但计的是"这个假设族还剩多少次试验预算"——额度条防撞限流，试验预算条防多重检验）。
回测详情 = 直接浏览 `reports/**` 下已有的静态产物；新产出的 tearsheet 采用自包含单文件 HTML（抄 NautilusTrader），cockpit 只做浏览入口，不在常驻进程里渲染重图。

## 5. 数据来源映射（全部只读，禁止写入）

| 面板 | 来源 | 解析 |
|---|---|---|
| 假设卡 | `reports/research/hypotheses/*.md` | 容错解析器：首行 `# H-YYYYMMDD-NN 标题`；`状态：`、`上一环：`、`卡：`、`教训：` 行；可选 YAML front-matter 优先。解析失败 → `未分类` 泳道 + 原因 |
| 教训 | `reports/research/lessons/L-*.md` | 标题 + 首段 |
| 试验/数字 | `reports/research/iterations/*/report.md`、`summary.json` | 读 summary.json 的 cell 列表；安慰剂分布字段见各 runner |
| 血统 | 同假设卡的"上一环" | 构 DAG，检测环并显示警告 |
| 模拟盘 | `reports/paper/rehearsal/*-latest.json`、`*-orders.jsonl`、`*-fills-summary.md`、`cycles.jsonl`、`signal_logs/` | 已是结构化 |
| 现有聚合 | `open_composer/cockpit/data/catalog.py`（搬家后） | 直接调用，不重写 |
| agent | `~/.paseo/agents/<工作区>/<id>.json`（状态、provider、模型、lastStatus、sessionId） + `~/.claude/projects/<slug>/<sessionId>.jsonl`（思考流、工具调用） + `~/.codex/sessions/**/rollout-*.jsonl` | SSE 尾随，**只读最后 N 行，绝不整文件载入内存** |
| Claude 额度 | `GET https://api.anthropic.com/api/oauth/usage`，Bearer 用 `~/.claude/.credentials.json` 里的 OAuth token，必须带 `anthropic-beta: oauth-2025-04-20` 和 `claude-code/<版本>` 的 User-Agent（UA 不对会被硬限流）。返回 `five_hour` / `seven_day` / `seven_day_opus` / `seven_day_sonnet` / `extra_usage` | **未公开接口，逆向而来**，必须容错：失败时退化为读会话记录里的 `quotaLimits`（只在被限流时出现，带 `resetsAt`）+ token 估算，页面上标明"估算" |
| Codex 额度 | 现在 `auth_mode: apikey`，无订阅额度。**预留**：切到 ChatGPT 登录后走 `codex app-server` 的 `account/rateLimits/read`，返回 `{usedPercent, resetsAt, windowDurationMins}` | 见 `I-20260919-02` |
| 健康 | `crontab -l`、`logs/*.log` 的 mtime 与尾部、`df`、`free`、各特征表最新日期 | 只读 |

## 6. 安全铁律（违反任何一条即为任务失败）

1. 只监听 `127.0.0.1`，绝不 `0.0.0.0`。
2. 没有任何写路由；不执行 shell 命令来改变状态（`crontab -l`、`df`、`free` 这类纯读取允许）。
3. 任何页面、日志、JSON 响应里**绝不出现** token、密钥、`.env` 内容、broker 凭证。渲染 agent 会话时按正则屏蔽 `sk-`、`Bearer `、`CLAUDE_CODE_OAUTH_TOKEN`、`OPENAI_API_KEY` 等模式。
4. 文件浏览入口必须做路径规范化，限制在仓库根以内，拒绝 `..`。
5. 读取大文件一律流式或只读尾部；单次响应内存占用不得超过 50MB（这台机器只有 3.9GB，且 OOM 时优先杀 agent 会话）。

## 7. 任务分解（交给 Sonnet，**同时最多两个**）

每个任务一个交付物、一次提交。执行者必须在自己的任务结束时跑通验收命令，跑不通就不算完成。

- **T1 · catalog 搬家**（先做，独占）
  新建 `open_composer/cockpit/__init__.py`、`open_composer/cockpit/data/__init__.py`，把 `open_composer/dashboard/catalog.py` 原样移到 `open_composer/cockpit/data/catalog.py`（`git mv`，内容只改包内导入），更新 `readiness.py`、`deployment.py`、`cli.py` 与 9 个测试文件的导入路径。此步不删任何东西。
  验收：`uv run ruff check . && uv run pytest && uv run oc repo check --strict` 全绿。

- **T2 · 拆除旧 dashboard**（依赖 T1，独占）
  按第 3 节逐条删除，包括 CLI 子命令、Makefile 目标、systemd/Caddy/部署脚本、四个整测试文件、`readiness.py` 的 `dashboard_bundle` 与鉴权检查、`repo_check.py` 的命令模型检查、`deployment.py` 的 html 步骤。
  同步改规则原文（见第 9 节）。
  验收：`make verify` 全绿；`git grep -n "open_composer.dashboard"` 无结果；`ls dashboard` 不存在。

- **T3 · 只读后端骨架**（可与 T4 并行）
  `open_composer/cockpit/app.py`：FastAPI 应用，只读路由，Jinja2 模板目录，`static/`，`oc cockpit serve --host 127.0.0.1 --port 8770`。
  健康屏（屏 5）作为第一个可用页面，因为它数据源最简单。
  验收：`uv run oc cockpit serve` 起得来，`curl -s localhost:8770/healthz` 返回 200，`curl -s localhost:8770/ | head` 有内容；进程 RSS < 150MB。

- **T4 · 假设卡解析器 + 看板**（可与 T3 并行，但依赖 T3 的模板约定，故实际排在 T3 之后）
  `open_composer/cockpit/data/hypotheses.py`：容错解析 + 血统 DAG；屏 1 与屏 2；卡片详情页（含判定 vs 实际并排）。
  验收：`uv run pytest tests/test_cockpit_hypotheses.py` 通过（新写）；现有 20 张卡全部出现在某个泳道，`未分类` 的每一张都带原因。

- **T5 · 模拟盘屏**：屏 4，复用搬家后的 `catalog.py` + `reports/paper/rehearsal/**`。验收：四个 sleeve 都显示，授权倒计时正确。
- **T6 · 额度层**：`open_composer/cockpit/data/quota.py`，Claude 走 oauth/usage 并带完整容错与"估算"标注，Codex 返回"按量计费"占位但接口按 `{usedPercent, resetsAt, windowDurationMins}` 定型。验收：断网时页面不报错、显示降级状态。
- **T7 · agent 活动屏 + SSE**：屏 3。验收：打开页面能看到本会话自己，思考流能实时追加，屏蔽规则对构造的假 token 生效。
- **T8 · 手机布局 + Cloudflare 上线**：两套布局；`cloudflared` 用现有 `~/.cloudflared/dsh-vps.json` 令牌起 systemd 服务，确认 Access 策略生效后才对外可达。验收：手机上五屏都可读；未登录 Access 时返回 403。

## 8. 验收（整体）

1. `make verify` 绿。
2. cockpit 常驻进程 RSS < 150MB，空载 CPU < 1%。
3. 五屏在手机与电脑上都能读，且**没有任何按钮能改变系统状态**。
4. 断开外网（额度接口不可达）时页面仍完整，只是额度区标注降级。
5. 机主能从看板上回答出四个问题：我不在时发生了什么、agent 在干什么、研究走到哪、模拟盘和额度什么状态。

## 9. 必须同步改掉的规则原文

- `CLAUDE.md` / `AGENTS.md` 里"Dashboard commands must use the confirmed command surface. Remote Dashboard commands must go through password session, Vercel BFF, HMAC, async job, backup, audit, and double confirmation for Red actions"
  → 改为："Cockpit 是只读的，不提供任何命令入口；远程访问由 Cloudflare Access 在边缘鉴权；发指令走 Paseo 会话。"
- `docs/remote-dashboard-deploy.zh.md` → 标记为历史，指向本文。
- `repo_check.py` 的 `CURRENT_DOCS` 里加入本文，移除随旧看板删掉的文档引用。
