# Open Composer Step 3：Dashboard-first 全交互（Plan C）

日期：2026-05-22
执行者：Codex / Claude Code
前置：Step 1（简化与重构）+ Step 2（worksession + LLM factor + Codex SDK）均完成
后续：无（路线图收尾）

## 0. 一句话目标

把 Dashboard 从"只读 catalog + 受控命令面板"升级为"个人用户的唯一交互入口"：所有策略生命周期动作（创建 / 研究 / 迭代 / promote / paper 监控 / 复盘）都能在 Dashboard 单页内完成，无需打开终端。CLI 作为 agent 与 advanced 用户的对等通道保留，但**普通用户的工作流 0 行 CLI**。

## 1. 背景（无上下文也能看懂）

Open Composer 是个人 AI 量化策略工作台，源头是 `StrategySpec`（YAML）。Step 1 完成后产品基线干净；Step 2 完成后有：

- `projects/{id}/queue.jsonl`：用户 → agent 命令队列
- `projects/{id}/trace.jsonl`：agent → 自我记录轨迹
- `projects/{id}/context.md`：32KB 完整上下文
- `oc feature materialize`：LLM 因子 PIT 物化
- `open_composer/agent_backend/`：`FileQueueAgentBackend` + `CodexAgentBackend` 双轨

但 Dashboard 当前仍是"看 catalog + 点几个 button 写命令计划"的辅助面板，**没有真正承担"用户唯一入口"**。用户视角的痛点：

1. 创建新策略要先写自然语言 idea，到终端跑 `oc strategy draft`，回 Dashboard 才看到草稿
2. "继续优化"按钮只生成一个一次性 agent_request（Step 2 改成 queue 但 UI 没跟上）
3. 看不到 trace 实时进展、没有 equity curve、没有 paper PnL 实时图
4. promote / activate / paper submit 都要回 CLI
5. spec edit 只能改 YAML 文件，没有 diff view / 一键确认

参考产品（如 Composer Trade、QuantConnect Cloud、TrendSpider）的共同模式：**所有动作以"策略卡 → 详情页"为中心，对话或一键按钮驱动，状态实时回填**。Open Composer 与它们的差异是**对话驱动**而不是 visual node editor —— 用户描述需求，AI 编辑 spec，Dashboard 显示 diff，用户确认。

## 2. 目标 / 非目标

### 目标

1. **Strategy Detail 页**成为单页工作台：含 spec / runs / promotion / paper / conversation / trace / charts 7 个面板，所有动作通过按钮 + 对话框完成。
2. **Conversation Panel**：内嵌对话框，用户写自然语言 → 写入 `queue.jsonl` → 通过 `AgentBackend` 真实驱动 Codex SDK（如已配置）或等待外部 agent 消费。
3. **Spec Diff View**：agent 修改 spec 后，Dashboard 显示 YAML diff，用户一键 Accept / Reject。
4. **实时 Trace Stream**：通过 SSE / 长轮询把 `trace.jsonl` 增量推到前端，agent 每写一行用户立即看到。
5. **实时图表**：equity curve / drawdown / signal log / paper PnL，用 lightweight 图表库内嵌。
6. **一键操作按钮**：Continue Research / Materialize LLM Factors / Run Evidence / Promote / Activate Paper / Disable，每个按钮都有对应的 backend API 和 audit trail。
7. **Build 页升级**：自然语言对话创建项目，含 LLM factor 模板选择（pure_quant / quant_with_llm_review / quant_with_llm_factor）。
8. **Settings 页**：env / capability / agent backend / notifications / dashboard token 一处集中可视化管理。
9. **CLI 与 Dashboard 双向等价**：Dashboard 每个动作都对应一条 CLI 命令；反之亦然。trace 字段记录 `via=dashboard|cli|api`。

### 非目标（明确不做）

- 不做 visual node editor（用对话 + spec diff 替代；这是与 Composer Trade 最大差异）。
- 不做策略社区市场（个人用，无社交需求）。
- 不做真钱 broker 写入（永远 out of scope）。
- 不做多用户 / 权限系统（个人工作台）。
- 不让 Dashboard 直接执行 backtest / pytest / shell — 它只调 `AgentBackend` 与 backend API；长任务由 agent / CLI / VPS 执行。
- 不改 `StrategySpec` schema。
- 不改 4 个 pass 语义。
- 不改 harness 规则与 paper safety chain。
- 不引入 GraphQL / tRPC / 复杂前端框架 — 沿用现有 React 18 + Vite + Tailwind + REST。

## 3. 当前状态扫描（Step 2 完成后的关键文件）

```text
dashboard/                               # React 18 + Vite + Tailwind 4
  src/main.tsx
  src/app/App.tsx                        # Tab 路由（已含 strategy / project 详情）
  src/app/components/
    sidebar.tsx                          # NavKey: overview/projects/build/live/research/activity/catalog/settings
    overview.tsx                         # 总览（已存在）
    projects.tsx                         # ProjectsView + ProjectDetail
    build.tsx                            # Build 视图（占位为主）
    live.tsx                             # paper 监控（已存在）
    sections.tsx                         # ActivityView + ResearchView
    library.tsx                          # 策略库
    strategy-detail.tsx                  # Strategy 详情 ★ Step 3 主要扩展点
    settings.tsx                         # 设置（占位）
    runtime.ts                           # catalog sync + session（已有）
    data.ts                              # 静态样例数据 ★ Step 3 改为完全从 API 拿
    notifications.tsx
    sparkline.tsx                        # 极简 sparkline，需要扩展为完整图表
    blocks.tsx                           # Card / KPI / SectionTitle 复用块
    hero.tsx
    topbar.tsx
    footer.tsx
    command-details.tsx

open_composer/dashboard/
  server.py                              # HTTPServer + /api/dashboard/* 端点
  catalog.py                             # build_dashboard_catalog
  commands.py                            # dashboard command plan/run（受控命令）
  html.py
  vps_deploy.py
```

```text
projects/{id}/                           # Step 2 已就位
  project.yaml
  context.md                             # 32KB
  queue.jsonl
  trace.jsonl
  runs/round-XXX.yaml
  session-binding.yaml                   # Codex SDK 时存在

reports/                                 # 各类报告 JSON / MD
```

## 4. 改动清单（按 Wave 分批）

### Wave 3.1 — Backend API 扩展（**先把 API 装齐**）

**4.1.1 新增 / 扩展 `open_composer/dashboard/server.py` 端点**

为前端的对话、操作按钮、实时 trace、spec diff 提供 API。

```text
GET    /api/dashboard/catalog                              # 已有
GET    /api/dashboard/health                               # 已有

★ 新增：项目对话与队列
GET    /api/projects/{id}                                  # 完整 project + context.md 头部 + 最近 trace
GET    /api/projects/{id}/context                          # context.md 全文（最大 128KB）
POST   /api/projects/{id}/queue                            # body: {kind, body, metadata} → 写 queue.jsonl + 调 AgentBackend
GET    /api/projects/{id}/queue                            # 列出未消费 + 已消费 N 条
GET    /api/projects/{id}/trace?since_ts=&limit=           # 增量获取 trace.jsonl
GET    /api/projects/{id}/trace/stream                     # SSE：trace.jsonl 实时推送
POST   /api/projects/{id}/stop                             # 停止当前 session

★ 新增：策略动作
GET    /api/strategies/{name}                              # 详情：spec / latest run / promotion / paper / 4 pass / evidence tracks
GET    /api/strategies/{name}/spec                         # 当前 active/approved/draft spec 全文
GET    /api/strategies/{name}/spec/diff?vs=<hash>          # 任意两版 spec 的 YAML diff
POST   /api/strategies/{name}/spec/accept                  # 接受 agent 写入的草稿（搬到 active/approved 目录）
POST   /api/strategies/{name}/spec/reject                  # 拒绝草稿（删除草稿文件）
POST   /api/strategies/{name}/actions/evidence             # 触发 oc strategy evidence
POST   /api/strategies/{name}/actions/materialize          # 触发 oc feature materialize
POST   /api/strategies/{name}/actions/promote              # 触发 oc strategy approve
POST   /api/strategies/{name}/actions/activate             # body: {mode: manual|paper_auto, confirm_phrase}
POST   /api/strategies/{name}/actions/disable              # 触发 oc strategy disable
GET    /api/strategies/{name}/runs                         # 历史 run 列表
GET    /api/strategies/{name}/runs/{run_id}/signals        # signal log
GET    /api/strategies/{name}/runs/{run_id}/equity         # equity curve 数据（OHLC + signals + trades 时间序列）

★ 新增：图表数据
GET    /api/strategies/{name}/equity?source=backtest|paper&since=&until=
GET    /api/strategies/{name}/drawdown
GET    /api/strategies/{name}/signals?limit=&offset=

★ 新增：Build
POST   /api/build/draft                                    # body: {idea, use_llm, strategy_kind} → 创建 project + draft spec
GET    /api/build/templates                                # 策略模板列表（pure_quant / with_llm_review / with_llm_factor / router）

★ 新增：Settings
GET    /api/settings/environment                           # env 变量状态（不暴露值）
GET    /api/settings/capabilities                          # capability 列表 + 评估状态
POST   /api/settings/capabilities/test                     # 触发 oc capability test
GET    /api/settings/agent-backend                         # 当前 backend + 可选项
POST   /api/settings/agent-backend                         # 切换 backend
GET    /api/settings/notifications                         # notification config 状态（已有 /api/notifications/config）

★ 新增：Paper 监控（部分已有）
POST   /api/paper/kill-switch                              # body: {enabled, reason}
POST   /api/paper/sync
POST   /api/paper/monitor/refresh
GET    /api/paper/positions
GET    /api/paper/orders
GET    /api/paper/alerts
```

**4.1.2 API 实现原则**

- 所有 POST 端点都通过 `oc` CLI 同名命令对应；HTTP handler 不直接跑长任务，而是：
  - 同步动作（≤2 秒，纯文件读写）：直接执行返回。
  - 异步动作（backtest / materialize / evidence / promote）：写 queue.jsonl 一条命令，立即返回 `{queue_command_id, status: "queued"}`，由 `AgentBackend` 真实执行；前端订阅 trace SSE 获取进展。
- 所有 POST 端点必须写一行 `trace.jsonl`，字段 `via: "dashboard"`。
- 鉴权：复用现有 `OPEN_COMPOSER_DASHBOARD_TOKEN` + `Access-Control-Allow-Origin` 机制。

**4.1.3 SSE 实现**

简单 SSE，不引入 WebSocket：

```python
def _handle_trace_stream(self, project_id: str) -> None:
    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream")
    self.send_header("Cache-Control", "no-store")
    self.end_headers()
    last_ts = self.headers.get("Last-Event-ID") or ""
    while True:
        rows = read_trace_since(project_id, last_ts, self.root)
        for row in rows:
            self.wfile.write(f"id: {row.ts}\ndata: {json.dumps(row)}\n\n".encode())
            self.wfile.flush()
            last_ts = row.ts
        time.sleep(1.0)
        if self._client_disconnected():
            return
```

**4.1.4 异步动作的 backend 集成**

```python
def _handle_strategy_evidence(self, name: str) -> None:
    project_id = _resolve_project_for_strategy(name, self.root)
    cmd_id = get_agent_backend().send_command(
        project_id,
        kind="run_evidence",
        body=f"strategy={name}",
        root=self.root,
    )
    self._send_json({"queue_command_id": cmd_id, "status": "queued"})
```

当 backend 是 `CodexAgentBackend` 时，Codex 会立即在仓库里跑 `oc strategy evidence`；当是 `FileQueueAgentBackend` 时，外部 agent / cron / 人工 tail 队列后执行。任意一种 backend，**trace.jsonl 都是单一审计源**。

**Wave 3.1 验收**：

```bash
# 起本地 dashboard
make dashboard-build
uv run oc dashboard serve --host 127.0.0.1 --port 8000 &

# API 烟雾测试
curl http://127.0.0.1:8000/api/projects/<id>
curl -X POST http://127.0.0.1:8000/api/projects/<id>/queue \
  -H 'Content-Type: application/json' -d '{"kind":"advice","body":"test"}'
test -f projects/<id>/queue.jsonl

curl http://127.0.0.1:8000/api/strategies/<name>
curl http://127.0.0.1:8000/api/strategies/<name>/runs
curl -X POST http://127.0.0.1:8000/api/strategies/<name>/actions/evidence
# 返回 queue_command_id

# SSE 烟雾测试
curl -N http://127.0.0.1:8000/api/projects/<id>/trace/stream &
# 另一个终端 append 一行 trace.jsonl，能在 SSE 流里看到
```

---

### Wave 3.2 — 前端：Strategy Detail 单页工作台（**核心 UI**）

**4.2.1 重写 `dashboard/src/app/components/strategy-detail.tsx`**

布局（参考 Composer Trade Symphony Page，但用对话替代 visual builder）：

```text
┌──────────────────────────────────────────────────────────────────────┐
│ StrategyDetail [name]                                                │
│  Lifecycle: active   Mode: paper_auto   Backend: nautilus_trader     │
├──────────────────────────────────────────────────────────────────────┤
│  ╔════════════ 4 Pass Status (sticky on top) ═════════════╗          │
│  ║ workflow ✅   research ✅   llm_contribution ⚠️   paper ❌ ║          │
│  ╚══════════════════════════════════════════════════════════╝         │
├──────────────────────────────────────────────────────────────────────┤
│  Tabs: [Overview] [Conversation] [Spec] [Runs] [Promotion]           │
│        [Paper] [LLM Factors] [Trace]                                 │
├──────────────────────────────────────────────────────────────────────┤
│  ── Overview tab ────────────────────────────────────────────────── │
│  ┌────────────────────────────────┐ ┌─────────────────────────────┐ │
│  │ Equity Curve (recharts)        │ │ Key Metrics                 │ │
│  │   line + drawdown shade        │ │ Sharpe / Calmar / Win rate  │ │
│  └────────────────────────────────┘ │ MaxDD / Annualized Return   │ │
│                                     │ Total Fees / Trades         │ │
│  ┌─ Action Buttons ────────────┐    └─────────────────────────────┘ │
│  │ [Continue Research]          │                                    │
│  │ [Materialize LLM Factors]    │   ┌─ Evidence Tracks ─────────┐   │
│  │ [Run Evidence]               │   │ Factor Quality:  ✅       │   │
│  │ [Generate Pine]              │   │ Execution Reality: ⚠️     │   │
│  │ [Promote → Approved]         │   │ Alt/LLM Evidence: ❌      │   │
│  │ [Activate (Manual / Paper)]  │   └───────────────────────────┘   │
│  │ [Disable]                    │                                    │
│  └──────────────────────────────┘                                    │
└──────────────────────────────────────────────────────────────────────┘
```

每个动作按钮：

- 点击 → 弹 modal 确认（含 `confirmation_phrase` 等审计要求）
- 确认 → POST `/api/strategies/{name}/actions/...`
- 立即切到 Trace tab 显示实时进展
- 成功 → 顶部 toast + 刷新数据

**4.2.2 Conversation Tab**

```text
┌─────────────────────────────────────────────────────────────────┐
│ Conversation                                                    │
├─────────────────────────────────────────────────────────────────┤
│ [User · 2026-05-22 10:00]                                       │
│  "尝试更激进的止损 0.5-0.8% 并加成交量过滤"                    │
│                                                                 │
│ [Agent · codex · 2026-05-22 10:01 → reading context.md ...]    │
│ [Agent · codex · 2026-05-22 10:02 → editing spec ...]          │
│ [Agent · codex · 2026-05-22 10:03 → strategy_specs/drafts/...] │
│ [Agent · codex · 2026-05-22 10:04 → oc strategy evidence ...]  │
│ [Agent · codex · 2026-05-22 10:08 → promotion: warning]        │
│ [Agent · codex · 2026-05-22 10:10 → ⚠ marginal_lift fail]     │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────┐     │
│ │ Compose advice...                                       │     │
│ │                                                         │     │
│ │ [Continue]  [Stop]  [Materialize LLM Factors]           │     │
│ └─────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

实现：

- 上半部分从 `/api/projects/{id}/trace/stream` SSE 拉取并渲染（按 `agent` + `operation` 染色）
- 下半部分输入框 → POST `/api/projects/{id}/queue` body `{kind: "advice|continue|stop|materialize", body: text}`
- Trace 每行根据 `gate.name` / `tool.name` / `artifact.path` 渲染为不同样式（artifact 路径变成可点击链接，跳到对应文件/报告）

**4.2.3 Spec Tab + Spec Diff View**

```text
┌──────────────────────────────────────────────────────────────────┐
│ Spec   current_hash: abc1234   draft_hash: def5678 (pending)    │
├──────────────────────────────────────────────────────────────────┤
│  ┌─ Active ──────────────┐  ┌─ Draft (agent-edited) ─────────┐  │
│  │ name: foo             │  │ name: foo                      │  │
│  │ entry:                │  │ entry:                         │  │
│  │   all:                │  │   all:                         │  │
│  │   - close > ema(...)  │  │ - close > ema(...)             │  │
│  │   - rsi > 55          │  │ - rsi > 55                     │  │
│  │ -                     │  │ + - volume > sma(volume, 20)  │  │
│  │ risk:                 │  │ risk:                          │  │
│  │   stop_loss_pct: 1.1  │  │ ~ stop_loss_pct: 0.6           │  │
│  └───────────────────────┘  └────────────────────────────────┘  │
│                                                                  │
│  [Accept Draft → strategy_specs/active/]                         │
│  [Reject Draft]                                                  │
│  [Edit Manually (open in editor)]                                │
└──────────────────────────────────────────────────────────────────┘
```

实现：

- 左侧调 `/api/strategies/{name}/spec`
- 右侧从 `strategy_specs/drafts/<name>.yaml` 拿；如果没有 draft，整列灰显
- diff 渲染用 `diff` npm 包（已是 React 生态常见库）
- Accept → POST `/api/strategies/{name}/spec/accept` → 后端调 `oc strategy approve` 等价逻辑

**4.2.4 Runs / Promotion / Paper / LLM Factors Tabs**

- **Runs Tab**：表格展示 `reports/runs/*.json` 列表，行点击展开 equity curve + signal log
- **Promotion Tab**：展示 `reports/research/{name}-promotion.json`，含 12+ check 项颜色标识；末尾"Run Evidence"按钮
- **Paper Tab**：embedded `LiveView` 当前策略部分 — paper position / orders / kill switch / readiness
- **LLM Factors Tab**：列出 spec 中 `source=llm_feature` 的 factor，每个含：
  - prompt_template_path 内容预览
  - input_view_version / prompt_hash / model
  - 物化状态：packet_count / last_materialized_at / cache hit rate
  - 按钮：[Materialize] [Refresh All] [Edit Prompt]

**4.2.5 Trace Tab**

完整 trace.jsonl 历史 + 实时流（同 Conversation 上半部分，但是更宽更详细，含 input_hash / output_hash / tokens）。

**4.2.6 顶部 4 Pass Status Bar**

固定吸顶：

```text
[ ✅ workflow_pass ]  [ ✅ research_pass ]  [ ⚠ llm_contribution_pass ]  [ ❌ paper_ready_pass ]
                                            ↑hover 显示 blocked check 列表
```

每个 badge hover 显示 blocked / warning reasons（从 promotion JSON 拿）。

**Wave 3.2 验收**：

```bash
make dashboard-dev    # vite dev server
# 浏览器访问 http://127.0.0.1:5173/?token=...
# 走通："Click 策略卡 → Conversation tab → 写一条 advice → trace 实时流显示 → spec diff 出现 → Accept"
```

---

### Wave 3.3 — Build View 升级（**自然语言创建策略**）

**4.3.1 重写 `dashboard/src/app/components/build.tsx`**

```text
┌─────────────────────────────────────────────────────────────────┐
│ Build a new strategy                                            │
├─────────────────────────────────────────────────────────────────┤
│ Strategy Kind                                                   │
│  ( ) Pure quant (deterministic only)                            │
│  ( ) Quant + LLM Review (advisory)                              │
│  ( ) Quant + LLM/news/macro factor                              │
│  ( ) Router meta-selection                                      │
│                                                                 │
│ Template (optional)                                             │
│  [ Memory storage momentum ▼ ]                                  │
│                                                                 │
│ Idea (natural language)                                         │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ "在 QQQ 15m 上，结合 ema 趋势和成交量过滤做开盘 30 分钟    │    │
│  │  延续动量。LLM 因子做新闻情绪打分。"                       │    │
│  │                                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│ ☑ Use LLM-assisted drafting (gpt-5)                             │
│ ☐ Auto-run evidence after draft                                 │
│                                                                 │
│  [Create Strategy]                                              │
└─────────────────────────────────────────────────────────────────┘
```

提交 → POST `/api/build/draft` → 后端调 `oc strategy draft` → 拿到 spec_path → 创建对应 `StrategyProject` → 自动写一条 `queue.jsonl` "请审查刚创建的 strategy 并跑 evidence" → 前端跳转到该 Strategy Detail 页。

如果勾"Quant + LLM factor"，draft 后弹"Edit prompt template" modal，要求用户填 prompt_template_path 内容。

**Wave 3.3 验收**：

- 创建一个 pure_quant 策略：跳转到 detail 页，4 Pass 全 N/A 或 workflow_pass=true
- 创建一个 quant_with_llm_factor 策略：detail 页 LLM Factors tab 含 1 条 factor 占位，prompt template 可在 modal 编辑

---

### Wave 3.4 — Live + Activity + Settings 升级

**4.4.1 LiveView**：

- 顶部 KPI：account equity / cash / buying power / position count / open orders
- 中部：positions table + orders table（已有，加 sort/filter）
- 右侧：kill switch toggle（带确认 modal）+ alerts list
- 底部：paper monitor loop 控制（start/stop）+ readiness 各策略列表

**4.4.2 ActivityView**：

- 时间线：合并 trace.jsonl（all projects） + signals + paper orders + reviews + journal + audit events
- 过滤器：by project / by kind / by date range
- 每条点击展开详情或跳详情页

**4.4.3 SettingsView**：

```text
┌────────────────────────────────────────────────────────────────┐
│ Environment & Secrets                                          │
│  OPENAI_API_KEY        ✓ set                                   │
│  OPENAI_BASE_URL       openai-compat.example.com               │
│  ALPACA_API_KEY_ID     ✓ set                                   │
│  ALPACA_PAPER          true                                    │
│  LONGBRIDGE_*          ✓ set                                   │
│  ...                                                           │
│ ─────────────────────────────────────────────────────────────  │
│ Capabilities                                                   │
│  market.sample_ohlcv      approved   ✅                        │
│  market.alpaca_bars       approved   ✅  [Re-evaluate]         │
│  market.longbridge_bars   trial      ⚠   [Re-evaluate]         │
│  news.alpha_vantage       trial      ✅                        │
│  ...                                                           │
│ ─────────────────────────────────────────────────────────────  │
│ Agent Backend                                                  │
│  ( ) file_queue (always works)                                 │
│  (•) codex_sdk  (gpt-5-codex)  status: idle                    │
│  ( ) claude_code_sdk (planned)                                 │
│  [Switch]                                                      │
│ ─────────────────────────────────────────────────────────────  │
│ Notifications                                                  │
│  Telegram  ✓ enabled  [Test send]                              │
│  Policies: signal_actionable ⇒ telegram, kill_switch ⇒ ...     │
│ ─────────────────────────────────────────────────────────────  │
│ Dashboard                                                      │
│  Token: ✓ set                                                  │
│  Allowed origin: http://127.0.0.1:8000                         │
└────────────────────────────────────────────────────────────────┘
```

只 read 不暴露 secret 值。所有 `[Re-evaluate]` `[Test send]` `[Switch]` 都走 backend API。

**Wave 3.4 验收**：

- Live 页能 toggle kill switch（含 confirm modal），后端写 `paper_kill_switch_events.jsonl` 一行 + 发 Telegram 通知
- Activity 页能筛 "kind=paper_order" + 跨 project 时间线
- Settings 页能切换 agent backend，写入 `.env` 后下次 dashboard server 启动生效

---

### Wave 3.5 — 图表与可视化

**4.5.1 引入轻量图表库**

```bash
npm --prefix dashboard install recharts@2
```

不引入 d3 / plotly / nivo（过重）。recharts 足够：line / area / bar / scatter。

**4.5.2 新增 `dashboard/src/app/components/charts/`**

```text
charts/
  equity-curve.tsx           # line + drawdown area overlay
  drawdown.tsx               # area chart
  signal-log.tsx             # scatter on price chart
  factor-ic.tsx              # bar chart of rolling RankIC
  paper-pnl.tsx              # live paper PnL line
```

数据从 `/api/strategies/{name}/equity` 等端点拿，统一 `{ts, value}` 数组格式。

**4.5.3 嵌入位置**

- StrategyDetail Overview tab：equity-curve（含 buy_hold 对比线）+ drawdown
- StrategyDetail Runs tab：每个 run 行展开后 signal-log
- StrategyDetail LLM Factors tab：每个 factor 旁边 mini factor-ic sparkline
- LiveView：paper-pnl

**Wave 3.5 验收**：

- StrategyDetail Overview 渲染出真实 equity curve（取自 `reports/runs/<run_id>.json` 的 equity 序列；若无则取自 `reports/backtests/`）
- charts 响应窗口宽度自适应；移动端 ≥ 320px 不破

---

### Wave 3.6 — CLI 与 Dashboard 等价 audit

**4.6.1 写一份"动作对照表"测试**

新增 `tests/test_dashboard_cli_parity.py`：

```python
"""验证 Dashboard 每个 POST 动作都有对应 CLI 命令；反之亦然。"""

DASHBOARD_ACTIONS = {
    "POST /api/strategies/{name}/actions/evidence":      "oc strategy evidence",
    "POST /api/strategies/{name}/actions/materialize":   "oc feature materialize",
    "POST /api/strategies/{name}/actions/promote":       "oc strategy approve",
    "POST /api/strategies/{name}/actions/activate":      "oc strategy activate",
    "POST /api/strategies/{name}/actions/disable":       "oc strategy disable",
    "POST /api/strategies/{name}/spec/accept":           "(internal: file move + version register)",
    "POST /api/projects/{id}/queue":                     "oc project continue",
    "POST /api/projects/{id}/stop":                      "oc agent stop",
    "POST /api/paper/kill-switch":                       "oc paper kill-switch",
    "POST /api/paper/sync":                              "oc paper sync",
    "POST /api/paper/monitor/refresh":                   "oc paper monitor",
    "POST /api/settings/capabilities/test":              "oc capability test",
    "POST /api/settings/agent-backend":                  "oc agent use",
    "POST /api/build/draft":                             "oc strategy draft",
}

def test_every_dashboard_action_has_cli_equivalent():
    # 验证 CLI 命令存在
    ...

def test_every_relevant_cli_command_has_dashboard_action():
    # 反方向：核心 CLI 都在 Dashboard 暴露
    ...
```

**4.6.2 在 trace.jsonl 强制 `via` 字段**

任意写 trace 的入口都必须填 `via in {"dashboard", "cli", "api", "agent"}`，便于审计来源。`oc agent status` 输出按 `via` 分组。

**4.6.3 README 更新**

`README.md` 增加一段：

```markdown
## Two Ways to Use Open Composer

| Audience | Primary interface |
|---|---|
| Day-to-day user | Dashboard at http://127.0.0.1:8000 — every action available without CLI |
| Agent (Codex / Claude Code) | CLI + file contracts: `oc strategy ...`, `projects/{id}/queue.jsonl`, `trace.jsonl` |
| Advanced power user | Both — Dashboard for status / one-clicks, CLI for batch and debugging |

Each Dashboard action writes a trace entry with `via=dashboard`; each CLI invocation writes `via=cli`. Use `oc agent status <project_id>` to see who did what.
```

**Wave 3.6 验收**：

```bash
uv run pytest tests/test_dashboard_cli_parity.py
# 所有动作都有 CLI 对偶
make verify
```

---

### Wave 3.7 — Onboarding / 首次使用引导

**4.7.1 首次启动检测**

Dashboard 加载时，如果检测到：

```text
- strategy_specs/active/ 为空 且
- projects/ 为空
- reports/runs/ 为空
```

显示首次使用 hero：

```text
Welcome to Open Composer

Three ways to start:
[1] Try a sample strategy (qqq_pullback_15m)  ← 一键 evidence → 看结果
[2] Build from your idea                       ← 跳 Build 视图
[3] Import a YAML strategy file                ← upload modal
```

**4.7.2 每个动作首次执行时显示 inline tip**

例如第一次按"Continue Research"，弹 tooltip："This appends a queue.jsonl command and (if codex_sdk configured) drives Codex to keep working in this strategy's project. See trace.jsonl for live progress."

不强制弹窗，可以 dismiss + 记忆 localStorage。

**Wave 3.7 验收**：

- 干净仓库（无 active 策略）打开 dashboard：显示 onboarding hero
- 已有策略仓库：直接看到 strategy 列表

## 5. 验收清单（Wave 3.1 - 3.7 全部完成）

```text
[ ] Backend API：新增 30+ 端点全部就位（catalog/projects/strategies/build/settings/paper）
[ ] SSE /api/projects/{id}/trace/stream 实时推送 trace.jsonl 增量
[ ] POST 端点正确写 trace.jsonl 含 via=dashboard
[ ] StrategyDetail 重写为 7 tabs：Overview / Conversation / Spec / Runs / Promotion / Paper / LLM Factors / Trace
[ ] 4 Pass Status Bar 顶部 sticky
[ ] Spec Diff View 可 Accept / Reject draft；后端正确移动文件 + 注册 version
[ ] Conversation Tab 含 SSE 实时流 + 输入框写 queue
[ ] Build View 支持 4 种 strategy_kind 模板 + 一键创建
[ ] LiveView 含 kill switch / paper PnL chart / monitor 控制
[ ] ActivityView 跨 project 时间线 + 过滤
[ ] SettingsView 含 env / capabilities / agent backend / notifications / dashboard token
[ ] recharts 图表：equity curve / drawdown / signal log / paper PnL 至少 4 种
[ ] tests/test_dashboard_cli_parity.py 通过
[ ] README 新增 "Two Ways to Use" 段
[ ] 首次启动 onboarding hero 显示逻辑就位
[ ] 普通用户工作流 0 CLI 走通：Build → Strategy Detail → Continue → Materialize → Evidence → Promote → Activate (manual)
[ ] uv run pytest 全绿
[ ] uv run oc repo check --strict 通过
[ ] make verify 通过
[ ] make dashboard-build / dashboard-serve 不报 warning
```

## 6. 不做什么（Step 3 边界）

```text
✗ 不引入 visual node editor（YAML diff + 对话即可）
✗ 不引入策略社区市场（个人用）
✗ 不引入真钱 broker 写入
✗ 不引入多用户 / 权限
✗ 不让 Dashboard 直接跑 backtest / pytest / shell — 仅调 AgentBackend + REST
✗ 不改 StrategySpec schema
✗ 不改 4 个 pass 语义
✗ 不改 harness / paper safety chain
✗ 不引入 GraphQL / tRPC / Next.js / SvelteKit — 保持 React 18 + Vite + Tailwind + REST
✗ 不引入 d3 / plotly / nivo — recharts 足够
```

## 7. 风险与对冲

| 风险 | 对冲 |
|---|---|
| SSE 在 Caddy / 反代后断流 | Caddyfile 加 `flush_interval -1`；同时前端实现 `EventSource` 自动重连 + `Last-Event-ID` 续接 |
| 长任务（evidence/materialize）需要 30s-5min 完成 | 异步：POST 立即返回 queue_command_id，前端订阅 SSE；不阻塞 HTTP 连接 |
| Spec Accept 后旧 active 文件直接覆盖 | `accept` 先注册 parent version，再写新 active；可通过 `oc strategy versions` / `oc strategy rollback-version` 回滚 |
| Conversation 写入 queue 但 agent 没消费 | UI 显示 queue_pending 计数；超过 5 分钟无 trace 反馈时提示"agent backend may be idle, check `oc agent status`" |
| 多 tab 并发写 queue 导致重复指令 | 每条 queue.jsonl 行带 idempotency_key（从 dashboard 生成 uuid）；后端去重 |
| 大文件 spec / 长 trace.jsonl 拖慢前端 | 后端分页（trace 增量 since_ts）；context.md 切片 head/tail；spec diff 用 web worker |
| recharts 在 ~5k 数据点变卡 | equity curve 自动降采样（每窗口取 max/min/first/last 5 个点）；signal scatter 仅展示最近 N 个 |
| 用户在 Build 页 "Auto-run evidence after draft" 误触 | confirm modal + trace 显示 queue_command 内容 |
| Activate Paper 在 Dashboard 误点 | 强制 confirmation_phrase 输入（同现有 dashboard_command 模式）+ 双重 modal |

## 8. 回滚预案

每个 Wave 单独 PR。Wave 3.1（API）出问题：前端会降级显示静态数据（保留 data.ts 作为 fallback），不会破坏现有 catalog 路径。Wave 3.2-3.5 是纯前端，可 git revert 单独 wave。Wave 3.6 / 3.7 是 polish，问题 revert 无下游影响。

## 9. 完成定义

执行完 Wave 3.1 - 3.7 后：

- 一个新用户从 `make start` 到完成第一个策略 paper readiness 全程 0 CLI
- 每个策略详情页就是该策略的"驾驶舱"：spec、运行、研究证据、对话、轨迹、LLM 因子、图表全在一个屏
- agent 与用户共享 `queue.jsonl` / `trace.jsonl` / `context.md` 三份文件契约：CLI / Dashboard / Codex SDK 任意入口写入都互相可见
- 不同动作（Continue Research / Materialize / Promote / Activate）的 trace 来源（via=dashboard|cli|api|agent）清晰可审计
- 关闭 Dashboard 后所有产物仍在文件系统，仍可 CLI / agent 接续 — Dashboard 是入口，不是真相
- 总代码量（Step 1 基线之后）期望前端净增 ~150KB（React + recharts + 新组件），后端净增 ~30KB（API handlers）

完成后，Open Composer 完整路线图收官。

## 10. 三步路线图总结（写给 Codex）

如果你（执行 agent）从头看到这里，三份计划的执行次序是：

```text
1. docs/plan-step-1-simplification-2026-05-22.zh.md         (先做)
   ↓ 完成后仓库基线干净、抽象统一
2. docs/plan-step-2-worksession-llm-factor-2026-05-22.zh.md (再做)
   ↓ 完成后 LLM 因子闭环 + queue/trace + Codex SDK 双轨就位
3. docs/plan-step-3-dashboard-first-2026-05-22.zh.md        (最后做)
   ↓ 完成后用户唯一入口是 Dashboard，CLI 是 agent / advanced 通道
```

每一步内部按 Wave 分批，每个 Wave 单独 PR。每个 PR 后 `make verify` 必须通过。

任意一步停下都是可发布状态：

- 停在 Step 1 后：产品更小更快，没有新功能
- 停在 Step 2 后：LLM+量化能力可用，但只能通过 CLI 与现有 Dashboard 操作
- 停在 Step 3 后：完整 Dashboard-first 体验

如果三步全部完成，Open Composer 就是一个"个人 AI 策略工作台"的稳定 v1.0：
- 输入：策略想法（自然语言）+ 可选 prompt 模板
- 处理：agent 在 Dashboard 对话框中持续研究迭代，每步落 file contract
- 输出：审计完整的策略 + paper readiness 证据 + 实时 paper PnL 仪表盘
