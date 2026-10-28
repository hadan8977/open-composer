# Open Composer 本地产品优化完善计划

日期：2026-05-25

## 0. 结论

接下来不继续推进 Cloudflare / Vercel / 公网远程访问。产品主线回到本地工作台：

```text
Dashboard localhost
  -> Project / StrategySpec / Report files
  -> CLI + Codex / Claude Code work session
  -> audited artifacts
  -> paper readiness only when gates pass
```

优化目标不是增加新架构，而是把现有本地闭环补完整：让 LLM 因子真的能参与全历史研究，让 Dashboard 能编辑和追踪 LLM 因子，让 Activity 能看到 agent 工作轨迹，让 Codex session / file queue 的项目连续性更可靠，让本地 Dashboard 的使用路径更顺。

## 1. 当前产品结构判断

### 1.1 已经成立的主结构

Open Composer 当前本地结构是正确的：

- `StrategySpec` 仍是策略行为真相来源。
- `projects/{id}/` 是策略项目和长会话状态面。
- `reports/` 是研究、回测、promotion、paper readiness、Dashboard read model 的审计面。
- Dashboard 是本地用户入口，不应承担长任务执行引擎职责。
- CLI / Codex / Claude Code 负责生成、修改、研究和验证策略。
- LLM / news / macro / event 信号必须先物化成 point-in-time replay packet，再参与回测和 promotion。
- Paper 自动化只支持 Alpaca Paper，且必须通过 readiness gate、kill switch 和显式确认。

### 1.2 当前需要修正的偏差

1. **远程访问不再是当前主线。**
   Cloudflare Tunnel 已暂停，`cloudflared` service 已停用并禁用自启。后续计划不应再把远程访问作为近期阻塞项。

2. **文档存在部署口径残留。**
   `AGENTS.md` 仍有旧的 Caddy/token canonical 说法，和最新产品方向不一致。当前阶段应统一为“本地优先；远程另行评估”。

3. **LLM 因子闭环还没有真正完成。**
   当前 `llm_materialize.py` 只物化最近 16 根 bar，导致 LLM factor 在 OOS / walk-forward / marginal lift 中缺历史 packet，容易让 LLM 贡献评估失真。

4. **Dashboard 对 agent/session 的观察还不完整。**
   `projects/*/trace.jsonl` 已经是核心轨迹，但 Activity 页面主要展示 catalog 派生数据，没有直接聚合所有 project trace。

5. **Dashboard 的 LLM 因子编辑能力不足。**
   LLM Factors tab 只能看 prompt preview 和触发 materialize，不能直接编辑 prompt、保存 hash、提示重新物化。

6. **部分 Dashboard 指标仍是占位或静态数据。**
   Factor IC 图表仍用占位值；LiveView paper PnL 和 positions 主要依赖 catalog 快照，不是定时拉取。

7. **Codex SDK backend 需要真实接口校验。**
   `codex_sdk` 是可选依赖，当前实现假设其 API 存在。需要更清晰的可用性检查和失败回退说明。

## 2. 产品原则

1. **本地优先。**
   默认路径是 `http://127.0.0.1:8000` + 本地文件系统，不再把域名、Vercel、Cloudflare 作为近期主线。

2. **Agent 发挥优势，但产品保留证据边界。**
   Codex / Claude Code 可以持续规划、写代码、生成报告，但所有关键结论必须落成 `StrategySpec`、`projects/`、`reports/`、`feature_logs/`、`signal_logs/` 等结构化制品。

3. **LLM + 量化必须可回测、可复现。**
   不允许 backtest loop 直接 live call LLM。正确路径是 prompt → feature packet materialization → point-in-time replay → marginal lift / robustness。

4. **Dashboard 是本地工作台，不是隐藏执行引擎。**
   Dashboard 可以创建 project、写 queue、展示 trace、触发受控命令，但长任务仍应通过 CLI / agent / file queue 可审计执行。

5. **先补闭环，不扩概念。**
   不新增策略类型、不改 pass 语义、不重写 Dashboard、不引入 WebSocket、不做远程 BFF。

## 3. 优先级计划

### P0：统一本地产品边界与文档口径

目标：避免产品方向在“本地工作台”和“远程部署平台”之间摇摆。

要做：

- 将 Step 4 原始计划归档到 `docs/archive/`，保留作为参考，不作为当前执行计划。
- 新增本文档作为当前下一阶段总计划。
- 更新 `README.md` 的 Project Docs。
- 更新 `open_composer/repo_check.py:CURRENT_DOCS`，让 repo check 认可当前文档集合。
- 修正 `AGENTS.md` 中远程部署旧口径，统一为本地优先，远程访问暂停。
- 在部署文档中明确：Cloudflare 是可选未来路径，当前不作为主线。
- 保持 `cloudflared` 停用；如未来恢复远程访问，再显式启用。

验收：

```bash
uv run oc repo check --strict
```

### P1：补完 LLM 因子研究闭环

目标：让 LLM factor 不只是“能配置”，而是真正能被全历史回测、promotion 和 Dashboard 评估。

要做：

- `open_composer/research/llm_materialize.py`
  - `materialize_factor()` 增加 `window_bars: int | None`。
  - 默认 `None` 表示全历史物化。
  - `--window-bars` 可限制最近 N 根，便于快速试验和控制成本。
- `open_composer/cli.py`
  - `oc feature materialize` 增加 `--window-bars`。
- Dashboard Strategy Detail
  - Materialize 支持 `Last 16 / Last 200 / Last 1000 / Full history`。
  - 默认对正式研究使用 Full history，快速试验可选窗口。
- 保持 backtest 只读 packet，不 live call LLM。
- promotion 中如果 packet 缺失、prompt_hash 不匹配、PIT 元数据不完整，应降级或 blocked。

验收：

```bash
uv run pytest tests/test_llm_materialize.py
uv run oc feature materialize strategy_specs/drafts/<strategy>.yaml --backend local_test_stub
```

必须能证明默认物化数量大于 16，并覆盖可用历史。

### P2：让 Dashboard 能直接编辑和评估 LLM 因子

目标：用户不打开终端，也能完成 LLM 因子的 prompt 修改、保存、重新物化和贡献查看。

要做：

- 新增 Dashboard API：
  - `GET /api/strategies/{name}/llm-factors/{factor}/prompt`
  - `POST /api/strategies/{name}/llm-factors/{factor}/prompt`
- 保存 prompt 时：
  - 写 prompt 文件。
  - 计算新 prompt hash。
  - 写入 project trace：`dashboard_edit_llm_factor_prompt`。
  - 返回 `needs_rematerialize=true`。
- LLM Factors tab：
  - 增加 `Edit prompt`。
  - inline textarea 编辑。
  - Save 后提示必须重新 materialize。
  - 显示 prompt hash / packet count / PIT 状态。
- Factor IC 图表：
  - 读取 `reports/research/{strategy}-factor-lab.json`。
  - 展示真实 `rank_ic`、`rolling_rank_ic_mean`、`rolling_rank_ic_min`。
  - 无数据时显示 `n/a`，不再用占位 `0.02`。

验收：

```bash
uv run pytest tests/test_dashboard_server.py
npm --prefix dashboard run build
```

### P3：补完项目轨迹与 Activity 观察面

目标：让用户能从 Dashboard 看清 Codex / Claude / CLI 做过什么，而不是只看到最后结果。

要做：

- 新增 `GET /api/activity/trace`：
  - 聚合 `projects/*/trace.jsonl`。
  - 支持 `limit`、`project`、`since_ts`、`kind`。
  - 按 `ts desc` 排序。
- ActivityView：
  - 合并 trace 行。
  - 按 agent 染色：Codex / Claude Code / CLI / Dashboard / system。
  - 保留 signals、orders、reviews、audits。
- Strategy Detail trace SSE：
  - 默认 `ticks=300`，减少 30 秒断流造成的频繁重连。
  - 前端显示 connected / polling fallback 状态。

验收：

```bash
curl http://127.0.0.1:8000/api/activity/trace?limit=20
uv run pytest tests/test_dashboard_server.py
```

### P4：本地 Dashboard 体验抛光

目标：让本地 Dashboard 成为日常主入口，减少“还是要回 Codex 里看状态”的情况。

要做：

- 保留已实现的空工作区 onboarding，不再重复实现 Step 4 的 D.1。
- 4-Pass badge 增加 tooltip：
  - 展示 blocked / warning check 名称和 message。
  - 最多显示前 6 条，超出提示查看 promotion / readiness report。
- LiveView：
  - 每 30 秒拉取 `/api/paper/positions`、`/api/paper/orders`、`/api/paper/alerts`。
  - 保留上一次成功数据，失败不清屏。
  - Paper PnL 图表使用真实账户 / position 快照。
- Settings：
  - 本地模式优先展示 Python、Dashboard build、sample data、OpenAI/Alpaca/Longbridge、notifications。
  - 远程配置降级到“可选/暂停”，不作为当前使用 blocker。
- 清理 Dashboard server 中明显的无效代码残留，例如重复 `return`。

验收：

```bash
npm --prefix dashboard run build
uv run pytest tests/test_dashboard_server.py
```

### P5：Codex session 与 file queue 可靠性

目标：充分发挥 Codex / Claude Code 的长会话优势，同时保留 file queue 的稳定兜底。

要做：

- `CodexAgentBackend` 初始化时检查真实 `codex_sdk` API：
  - `start_session`
  - `send_user_message`
  - `is_session_alive`
  - `cancel_session`
- 缺方法时给出清晰错误，并提示回退：

```bash
OPEN_COMPOSER_AGENT_BACKEND=file_queue
```

- 增加可跳过的 integration test：
  - 默认没有 `codex_sdk` 时 skip。
  - 有 `codex_sdk` 时测试 session create / send / status / stop 的最小闭环。
- Dashboard Settings 显示当前 agent backend、session_id、queue_pending、last_seen。

验收：

```bash
uv run pytest tests/test_project_queue.py tests/test_strategy_projects.py
uv run pytest tests/test_codex_sdk_backend.py
```

## 4. 不做事项

近期不做：

- 不继续配置 Cloudflare Tunnel / Access。
- 不重新启用 Vercel BFF。
- 不开放公网 Dashboard 端口。
- 不让 Vercel、浏览器或 Dashboard 运行回测、pytest、扫描或文件批量编辑。
- 不让 backtest loop 直接调用 live LLM。
- 不引入 LangGraph / NeMo / Perspective / magic-trace / gs-quant 作为依赖。
- 不做实盘 broker 写入。
- 不新增复杂模型路由、预算模型、通知策略。

## 5. 风险与应对

| 风险 | 应对 |
|---|---|
| 全历史 LLM 物化成本高 | `--window-bars` 控制范围；cache key 保证断点续跑；Dashboard Materialize 前提示 packet 数 |
| Prompt 编辑后忘记重新物化 | Save 返回 `needs_rematerialize=true`；Dashboard 显示提示；promotion 检查 hash / PIT 状态 |
| Activity trace 聚合变慢 | 每个 project 只读 tail；全局排序后截断 limit |
| Codex SDK API 漂移 | 初始化时显式检查方法；失败自动建议 file_queue |
| 本地 Dashboard 过度承担执行职责 | 所有长任务仍写 queue / command plan；Dashboard 只触发受控入口 |
| Paper 数据轮询失败 | 保留上次成功状态；UI 标记 stale，不误报实时 |

## 6. 执行顺序

```text
P0  文档与本地边界统一
P1  LLM 因子全历史物化
P2  LLM 因子 Dashboard 编辑 + 真实 IC
P3  Activity trace + SSE 稳定
P4  Dashboard 本地体验抛光
P5  Codex session / file queue 可靠性
```

每个阶段完成后必须跑：

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
uv run oc repo check --strict
npm --prefix dashboard run build
```

如果阶段涉及 Dashboard 主流程，再跑：

```bash
make verify
```

## 7. 完成定义

本计划完成后，产品应达到以下状态：

- 用户可以完全从本地 Dashboard 创建项目、查看项目、继续研究、查看 trace、编辑 LLM prompt、查看 LLM factor evidence。
- Codex / Claude Code 可以基于 `projects/{id}/context.md`、queue、trace、runs 持续推进，不依赖短 memory。
- LLM factor 的贡献评估基于全历史或显式窗口 packet，不再是最近 16 根 bar 的伪闭环。
- Factor Quality、Execution Reality、Alt/LLM Evidence 三条证据在 Dashboard 和报告中都能被看见。
- Paper 自动化仍然只在 readiness pass 后进入 paper-only 流程。
- 本地使用不再被远程部署、域名、Cloudflare、Vercel 阻塞。
