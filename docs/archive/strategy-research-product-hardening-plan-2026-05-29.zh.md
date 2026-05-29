# Open Composer 策略研究产品强化计划

日期：2026-05-29

本文档是自包含执行计划。执行者不需要阅读任何对话上下文，只需要按本文档理解现状、目标、约束和改动顺序。

## 产品定位

Open Composer 是本地优先的个人 AI 策略工作台。核心体验是：

- 用户提出策略方向。
- Codex / Claude Code 在本地项目中生成 StrategySpec、代码、研究报告、证据制品和审查结果。
- Dashboard 只作为本地工作台和只读/轻写交互界面。
- 长时间研究任务仍由本地 CLI、文件制品和 agent session 承担。
- 不默认开放公网 Dashboard，不默认启用 broker 写操作。

`StrategySpec` 是策略行为的事实来源。研究报告、harness artifact、source card、promotion report 和 paper readiness report 是审计来源。

## 必须遵守的边界

1. 不允许启用真实资金交易。
2. 不允许在未通过 paper readiness 前启用 `paper_auto`。
3. Alpaca IEX/cache 只能作为研究数据，不能作为 paper-ready 严格证据。
4. LLM/news/event/macro 不能直接影响订单，除非已经 materialize 成 PIT replay packets，并证明 marginal lift、missing-modality robustness 和单模态基线对比。
5. `workflow_pass`、`research_pass`、`llm_contribution_pass`、`paper_ready_pass` 必须分开显示，不能混用。
6. 对失败或未采用的研究迭代，不应强制补齐 paper/promotion 级完整 harness artifacts。

## 当前策略状态

当前最有研究价值的策略方向是 1m NASDAQ long-short adaptive intraday router。

当前较强候选：

- Spec: `strategy_specs/drafts/nasdaq_long_short_event_router_1m_sweep_001.yaml`
- Route: `lb20_entry2_top1_open0_mom0_rv0.8_qprior_negative_reversal_maxopen0_maxmomnone`
- OOS 年化收益：`68.15%`
- OOS Sharpe：`2.14`
- OOS 最大回撤：`-9.60%`
- Walk-forward 正 alpha：`5/5`
- 状态：`workflow_pass=true`，`research_pass=true`，`paper_ready_pass=false`
- 主要阻塞：`strict_data`，Alpaca IEX/cache 不是 paper-ready 数据证据

最近完成但不采用的反证迭代：

- Spec: `strategy_specs/drafts/nasdaq_long_short_event_router_1m_sweep_002.yaml`
- OOS 年化收益：`7.63%`
- OOS Sharpe：`0.48`
- OOS 最大回撤：`-12.44%`
- Walk-forward 正 alpha：`2/5`
- 状态：`workflow_pass=true`，`research_pass=false`，`paper_ready_pass=false`

结论：不要继续扩展 `sweep_002`。下一步应围绕 `sweep_001` 做产品能力强化：数据严格化、路由级因子归因、运行进度、研究生命周期和 Dashboard 展示。

## 外部调研结论

本计划只吸收轻量、可本地实现的设计，不引入重型外部框架。

### 数据源与 paper readiness

Alpaca 官方文档区分 IEX/Basic 数据与更完整的 US equity market data 覆盖。当前本地 cache/IEX 不能作为 paper-ready 严格证据。

执行含义：

- promotion 继续阻塞 `cached_live` / IEX-only 证据是正确的。
- 产品需要一个数据源对比 artifact，而不是让用户猜测为什么 research pass 不能 paper ready。

参考：

- https://docs.alpaca.markets/us/docs/about-market-data-api

### 短卖执行与 broker 证据

短卖策略需要 broker 侧 shortable/easy_to_borrow 等字段和监管 locate 约束的审查，不能只靠回测结果。

执行含义：

- long-short router 即使 research pass，也必须补 borrow、ex-dividend、squeeze、short exposure policy。
- 这些证据只应在候选被采用后补齐，失败迭代不应强制补全。

参考：

- https://alpaca.markets/sdks/python/api_reference/trading/models.html
- https://www.sec.gov/investor/pubs/regsho.htm

### 运行效率与早停

scikit-learn 的 successive halving、Optuna pruning、Ray Tune scheduler 等系统都体现了同一原则：不要对所有候选无差别跑到底，应在中途根据部分证据淘汰低价值候选。

执行含义：

- Open Composer 不需要引入这些框架。
- 但 adaptive router research 应增加本地早停、progress event、best-so-far 和 runtime budget。

参考：

- https://scikit-learn.org/stable/modules/grid_search.html#successive-halving-user-guide
- https://optuna.readthedocs.io/en/stable/tutorial/10_key_features/003_efficient_optimization_algorithms.html
- https://docs.ray.io/en/latest/tune/

### 实验追踪

MLflow 等工具把 run、params、metrics、artifact 分开记录。Open Composer 已经以文件为核心，不需要引入 MLflow，但需要更明确的 run ledger。

执行含义：

- 每次策略研究应产生结构化 run record。
- Dashboard 和 agent memory 应读取 run record，而不是只读最终 report。

参考：

- https://mlflow.org/docs/latest/ml/tracking/

### 本地 Dashboard 进度

Server-Sent Events / EventSource 适合本地 Dashboard 接收长任务进度事件。Open Composer 不需要公网消息系统。

执行含义：

- Dashboard 可通过本地 SSE 读取 research run progress。
- 不要让 Dashboard 直接执行重任务；它只创建本地 audited request 或显示 CLI/agent 运行状态。

参考：

- https://html.spec.whatwg.org/multipage/server-sent-events.html

## 需要解决的产品问题

### 问题 1：adaptive router 研究运行太黑箱

`sweep_002` 只有 324 个基础候选，但运行约 2186 秒。期间没有阶段进度、预计剩余时间、best-so-far、早停提示或安全 cancel。

应改为：

- 每个 research run 有 `run_id`。
- 每个阶段写 progress event。
- 每 N 个候选写 best-so-far。
- 支持 runtime budget 和 no-improvement early stop。
- 被 cancel 或超时后写 partial result，不丢上下文。

### 问题 2：draft router 必须填写 route label

当前 `adaptive_intraday_internal_router` 在 draft/research 阶段也强制 `selected_route_label`，导致新研究必须伪造占位路线。

应改为：

- draft/research 阶段允许 `selected_route_label: null`。
- scan、target weights、paper readiness 阶段才强制 route label。
- Dashboard 显示“未选择路线”，而不是报错。

### 问题 3：Factor Lab 不适配 portfolio router

通用 Factor Lab 对 1m 多股票 router 太慢，并且它评估的是单因子/单标的，不适合 portfolio-level route。

应改为：

- 新增 route-level factor attribution。
- 对 adaptive intraday router 直接评估 opening return、prior momentum、relative volume、market gate、entry delay 的边际贡献。
- promotion 接受 route attribution 作为 router 的 Factor Lab 等价证据。

### 问题 4：数据严格性缺少可操作路径

`strict_data` 阻塞是正确的，但产品没有给出简单命令来生成 feed/provider comparison。

应改为：

- 新增数据源对比命令。
- 输出 coverage、missing bars、OHLC drift、volume drift、timestamp drift。
- 如果 SIP 或第二数据源不可用，输出明确 blocker 和下一步配置说明。

### 问题 5：universe audit 读不到结构化固定池证据

Spec notes 里的固定 universe 说明不会被 audit 当成结构化证据。

应改为：

- StrategySpec 增加 `universe_metadata`。
- 或新增命令把固定 universe 写成 PIT/fixed-universe artifact。

### 问题 6：失败迭代被迫补完整 promotion artifacts

失败的 `sweep_002` 不应被要求补齐 borrow、target weights、rebalance intents 等 promotion 级制品。

应改为：

- 每次研究迭代有 outcome：`adopted | rejected | needs_more_research`。
- rejected iteration 只要求研究报告、来源卡、指标对比和拒绝原因。
- adopted/promotion candidate 才进入完整 harness artifact 链。

### 问题 7：技能文档与 CLI 不一致

`strategy-research-orchestrator` 仍写着 `oc capability evaluate <spec>`，但当前 CLI 只有 `oc capability list/test`。

应改为：

- 更新 skill 文档。
- 或恢复 `oc capability evaluate <spec>`，用于按策略生成 capability review artifact。

## 实施计划

### P0：文档和技能对齐

目标：让 Codex/Claude Code 不再按过期命令执行。

改动：

- 更新 `.agents/skills/strategy-research-orchestrator/SKILL.md`。
- 将 `oc capability evaluate <spec>` 改成当前真实路径，或新增该 CLI 命令。
- 在 docs 中写明 rejected/adopted/paper-ready 的区别。

验收：

- 新 Codex session 只读 skill 文档即可跑通 research workflow。
- 不出现不存在的 CLI 命令。

### P1：研究运行 ledger 与进度事件

目标：长任务可观察、可恢复、可审计。

新增 artifact：

- `reports/research/runs/{strategy}-{run_id}.jsonl`
- `reports/research/runs/{strategy}-latest.json`

事件字段：

- `schema_version`
- `strategy_name`
- `run_id`
- `event_type`
- `stage`
- `candidate_index`
- `candidate_count`
- `best_label`
- `best_score`
- `best_oos_sharpe`
- `best_oos_return_pct`
- `best_max_drawdown_pct`
- `warning_items`
- `blocked_items`
- `started_at`
- `ended_at`

改动：

- 在 adaptive router research 的数据加载、候选评估、walk-forward、report write 阶段写事件。
- CLI 增加 `--run-id`、`--progress-every`、`--max-runtime-seconds`。
- 超时或 cancel 时写 partial result。

验收：

- 运行 adaptive router 时，`reports/research/runs/` 有实时增量 jsonl。
- 中途失败不会丢失已完成候选摘要。

### P2：Draft router lifecycle 修正

目标：研究阶段不再伪造 route label。

改动：

- `StrategySpec.portfolio.selected_route_label` 对 draft/research adaptive router 可为空。
- `run_adaptive_intraday_router_scan()`、target weights、paper readiness 中继续强制 route label。
- Dashboard catalog 对空 route 显示 `research_pending`。

验收：

- 一个新 draft adaptive router 在无 route label 时可以 `oc spec validate`。
- scan/paper 命令仍会明确报错，要求先选择 route。

### P3：Adaptive router route-level factor attribution

目标：替代不适配的通用 Factor Lab。

新增命令：

- `oc strategy adaptive-factor-attribution <spec>`

新增 artifact：

- `reports/research/{strategy}-adaptive-factor-attribution.json`
- `reports/research/{strategy}-adaptive-factor-attribution.md`

最小 attribution 维度：

- baseline selected route
- no market gate
- no relative-volume filter
- entry delay alternative
- reversal threshold alternative
- prior momentum gate alternative

每项输出：

- full/OOS annualized return
- full/OOS Sharpe
- full/OOS max drawdown
- full/OOS equal-weight alpha
- walk-forward positive alpha folds
- delta vs baseline
- conclusion：`positive | neutral | harmful | inconclusive`

promotion 改动：

- `router_promotion._factor_lab_check()` 对 `adaptive_intraday_internal_router` 读取 `adaptive-factor-attribution`。
- 如果 attribution status 为 ok，则 Factor Lab gate 对 router 通过或降为 advisory。

验收：

- `sweep_001` 不跑通用 Factor Lab，也能获得 router-aware factor evidence。
- promotion 不再错误提示 “Factor Lab diagnostics are missing for this router”。

### P4：数据源对比与 strict_data remediation

目标：把 `strict_data` 从模糊 blocker 变成明确可执行流程。

新增命令：

- `oc strategy data-compare <spec> --primary alpaca:iex --secondary alpaca:sip`
- 允许 secondary 不可用，但必须写 blocker artifact。

新增 artifact：

- `reports/harness/data/{strategy}-data-compare.json`
- `reports/harness/data/{strategy}-data-compare.md`

字段：

- compared_symbols
- compared_window
- provider/feed per side
- bar_count_primary / secondary
- missing_bar_count
- timestamp_alignment_pct
- close_drift_bps_p50 / p95 / max
- volume_drift_pct_p50 / p95 / max
- strict_data_status：`ok | warning | blocked`
- remediation

promotion 改动：

- 如果 comparison 通过，`strict_data` 可从 blocked 降为 warning 或 ok。
- 如果 SIP/secondary 缺失，继续 blocked，但 Dashboard 显示具体配置缺口。

验收：

- 无 SIP 凭证时也能生成明确的 blocked artifact。
- 有第二数据源时能输出 drift/coverage 指标。

### P5：Universe metadata 与 fixed-universe artifact

目标：让固定股票池说明可被 audit 读取。

新增 StrategySpec 字段：

```yaml
universe_metadata:
  selection_timestamp: "2026-05-28T00:00:00Z"
  selection_basis: "fixed research watchlist"
  pit_membership_status: fixed_universe_not_historical_index
  delisting_policy: "No historical constituent backfill; paper readiness requires review."
```

或新增 artifact：

- `reports/research/{strategy}-fixed-universe.json`

改动：

- universe audit 读取 `universe_metadata` 或 fixed-universe artifact。
- current-symbol list 仍可 warning，但不应在明确固定研究池时阻塞 research_pass。

验收：

- `sweep_001` 可生成 fixed-universe artifact。
- universe audit 对固定研究池给出 warning，而不是错误地当成历史指数成分回填。

### P6：Iteration outcome 与 rejected 语义

目标：失败迭代轻量收口，不触发完整 promotion artifact 链。

新增字段：

- research report: `iteration_outcome`
- promotion report: `candidate_status`

取值：

- `adopted`
- `rejected`
- `needs_more_research`

规则：

- rejected：需要 source cards、research report、metric comparison、rejection reason。
- adopted：需要 route attribution、data evidence、forensics。
- promotion candidate：需要完整 harness artifacts。

验收：

- `sweep_002` 被标记 rejected 后，Dashboard 不再显示一堆 paper/promotion artifact 缺失为当前待办。
- `sweep_001` 作为 adopted research candidate，继续显示 strict_data 和 route attribution 待办。

### P7：Dashboard 展示改进

目标：用户能在 Dashboard 看清“研究强，但不能纸盘”的真实状态。

改动：

- Strategy detail 增加 pass matrix：
  - workflow_pass
  - research_pass
  - llm_contribution_pass
  - paper_ready_pass
- 显示 latest run progress。
- 显示 data strictness card。
- 显示 route factor attribution card。
- 显示 iteration outcome timeline。

约束：

- Dashboard 不直接跑重任务。
- Dashboard 只能显示本地 artifacts，或创建 audited request 文件。

验收：

- 用户不需要读 JSON，也能知道为什么 `sweep_001` 不能 paper。
- rejected 的 `sweep_002` 不再污染主要待办列表。

## 执行顺序

推荐按以下顺序执行：

1. P0：修正文档/skill 与 CLI 不一致。
2. P2：允许 draft router 无 route label。
3. P1：加 research run ledger 和进度事件。
4. P3：加 adaptive route-level factor attribution。
5. P6：加 iteration outcome/rejected 语义。
6. P4：加 data compare 和 strict_data remediation。
7. P5：加 universe metadata。
8. P7：Dashboard 展示整合。

原因：

- P0/P2 先解除 agent 和 spec 交互摩擦。
- P1 先解决长任务黑箱问题，否则后续优化仍不可控。
- P3/P6 让当前策略研究状态更准确。
- P4/P5 是 paper readiness 前的关键证据。
- P7 最后整合显示，避免 Dashboard 先做成展示混乱。

## 最终验收标准

执行完本计划后，应满足：

1. 新 adaptive router draft 不需要伪造 route label。
2. 长时间 router research 有 progress jsonl、latest run summary、partial failure snapshot。
3. `sweep_001` 有 route-level factor attribution，不再依赖通用 Factor Lab。
4. `sweep_002` 可被明确标记为 rejected，不再显示完整 paper artifact 缺失。
5. `strict_data` 有可执行 remediation：data compare artifact。
6. fixed universe 说明能被 universe audit 读取。
7. Dashboard 明确区分 research pass 和 paper-ready fail。
8. 没有任何改动默认启用 paper_auto 或公网访问。

## 验证命令

至少运行：

```bash
uv run oc spec validate strategy_specs/drafts/nasdaq_long_short_event_router_1m_sweep_001.yaml
uv run oc strategy adaptive-factor-attribution strategy_specs/drafts/nasdaq_long_short_event_router_1m_sweep_001.yaml
uv run oc strategy data-compare strategy_specs/drafts/nasdaq_long_short_event_router_1m_sweep_001.yaml --primary alpaca:iex --secondary alpaca:sip
uv run oc strategy promotion-report strategy_specs/drafts/nasdaq_long_short_event_router_1m_sweep_001.yaml
uv run oc harness verify strategy_specs/drafts/nasdaq_long_short_event_router_1m_sweep_001.yaml
uv run ruff format .
uv run ruff check .
uv run pytest
```

如果 `alpaca:sip` 不可用，`data-compare` 不应崩溃；它应写出 blocked artifact，并说明缺少配置或订阅。

## 非目标

本计划不做：

- 不接入真实资金交易。
- 不启用 paper_auto。
- 不把 Dashboard 变成远程执行器。
- 不引入 MLflow、Optuna、Ray Tune、scikit-learn 作为产品依赖。
- 不让 LLM/news/event 在没有 PIT replay packets 和 marginal lift 证据前影响订单。
