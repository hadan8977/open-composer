# Open Composer 非 ML / 非 A 股产品缺口修复计划

日期：2026-05-28

状态：待外部 agent 严格 review

## 0. 给 no-context Codex / Claude Code 的阅读说明

这份文档用于解决 Claude 对 Open Composer 产品能力审查中，除 ML 和 A 股之外的缺口。实施或审查前必须先读取：

- `AGENTS.md`
- `README.md`
- `docs/strategy-research-product-remediation-plan-2026-05-26.zh.md`
- `docs/product-golden-path-codex-quant-review-2026-05-13.zh.md`
- `.agents/skills/backtest-forensics/SKILL.md`
- `.agents/skills/source-researcher/SKILL.md`
- `.agents/skills/execution-reality-reviewer/SKILL.md`
- `open_composer/models/strategy_spec.py`
- `open_composer/timeframes.py`
- `capabilities/registry.yaml`
- `open_composer/research/factor_lab.py`
- `open_composer/research/parameter_sweep.py`
- `open_composer/adapters/execution/nautilus_runtime.py`
- `/root/OC_REGIME_DECAY_PLAN.md`

本计划不替代 2026-05-26 的策略研究门禁修复计划。那个计划解决“策略生成流程容易过拟合、跳过 research brief、预算失控”的问题；本计划解决更底层的产品能力问题：研究/生产双轨、实验追踪、非 ML 因子研究、tick/LOB 数据契约、执行现实模拟和可观察性。

## 1. 本轮范围

### 1.1 明确纳入

- 研究与生产双轨：`playground` 快速实验和 `audited` 可晋级研究分离。
- 本地实验追踪：统一记录 run、trial、params、metrics、artifacts、dataset hash、spec hash、gate status。
- 非 ML 因子研究：扩展现有 Factor Lab 到截面 panel、ICIR、t-stat、decay、分位组合、相关性和可选中性化。
- 制度感知验证与 alpha 衰减监控：逐 bar equity artifact、regime performance、alpha decay、EvaluationPolicy。
- 搜索与优化治理：继续保留 random/grid，但补统一 `SearchPolicy`、trial pruning、multi-objective router 扩展点。
- Tick / L1 / L2 数据契约：先做 schema、capability 表达和 fixture，不先承诺任何付费数据源。
- 执行现实模拟：沿 NautilusTrader adapter 扩展，不自研第二套完整执行引擎。
- Dashboard / CLI 可观察性：把实验、门禁、阻塞原因和产物关系做成可查询状态。

### 1.2 明确排除

- 不做 `trained_model`、模型训练 loop、checkpoint、GPU、PyTorch/JAX/XGBoost、模型 registry。
- 不做 A 股、Tushare、AKShare、QMT、Ptrade、A 股交易规则。
- 不做真金交易。
- 不做 public Dashboard 或远程执行通道扩展。
- 不把 LLM 解释当 alpha；本轮只允许 LLM 做研究辅助、报告生成、source synthesis 和审查。

### 1.3 产品原则

- `StrategySpec` 仍是策略行为真相来源。
- `playground` 产物默认不能用于 promotion、paper readiness 或 paper_auto。
- 所有可晋级产物必须可重放、可审计、可定位到输入数据和 spec hash。
- Tick/LOB 和执行模拟必须优先复用 NautilusTrader 概念；OC 只做适配、审计和门禁。
- Dashboard 只读统一 artifact/index，不创建第二套状态真相源。

## 2. 核实后的问题列表

### P1. 研究与生产没有双轨

现状：OC 的强项是审计优先、文件优先、paper 安全，但研究阶段也容易被完整 harness gate 拖慢。用户需要快速探索，但产品不能让快速探索绕过生产门禁。

解决方向：新增受限 `playground` 轨道。它允许快速试验和报告，但产物必须带 `research_mode=playground`，并被 lifecycle、promotion、readiness 和 paper_auto 明确阻断。

### P2. 实验追踪仍是报告文件夹，而不是可查询实验系统

现状：`reports/` 有大量产物，但用户无法稳定回答“这次研究跑了多少 trial、参数是什么、最好结果为什么被接受/拒绝、学习曲线如何、哪些工件对应哪个 spec hash”。

解决方向：新增本地 `ExperimentRun` 索引。先用 JSONL 和 manifest 文件实现，不直接引入 MLflow 依赖，但字段设计应与 MLflow 的 runs / params / metrics / artifacts 兼容。

### P3. Factor Lab 有基础指标，但还不是专业非 ML 因子研究工作流

现状：`factor_lab.py` 已有 `rank_ic`、rolling RankIC、分位收益、spread、turnover 和相关矩阵。缺口不是“完全没有 IC”，而是缺截面 panel、ICIR、t-stat、factor decay 展示、中性化和因子组合前的质量门禁。

解决方向：保留现有单标的 Factor Lab；新增 `FactorPanel` 和 `FactorLabV2`，用于多标的截面因子诊断。第一版不引入 ML，只处理表达式因子、feature_packet 因子和已有数值因子。

### P4. 搜索治理仍偏脚本化

现状：`parameter_sweep` 已有 grid/random 和 research brief budget，但不同研究脚本仍可能各写各的搜索逻辑，难以统一记录 trial、prune reason、search policy 和多目标取舍。

解决方向：抽象 `SearchPolicy`、`TrialDecision`、`ObjectiveSet`。普通策略默认 random/grid；router 或多目标场景预留 evolutionary / NSGA-II 接口，但不作为第一批依赖。

### P5. Tick / LOB 缺少产品层数据契约

现状：`StrategyTimeframe` 从 `1m` 起步，capability registry 主要表达 OHLCV bar。即使 NautilusTrader 支持 tick / order book，OC 也没有自己的数据类型、质量报告、schema 验证和 replay contract。

解决方向：先做数据契约，不先做供应商接入。定义 `MarketDataKind = ohlcv_bar | trade_tick | quote_tick | order_book_delta | depth_snapshot`，并为每类数据建立最小字段、时间戳、时区、symbol、venue、source、quality flags 和 replay manifest。

### P6. 执行现实模拟有框架，但不够细

现状：OC 已有 `ExecutionPolicy`、`RealityModel`、impact model 和 Nautilus adapter，但 `ExecutionConfig.fill_assumption` 仍只有 `next_bar_open`。对于 open execution、limit order、partial fill、latency、spread、queue position，当前更多是审查报告，而不是可跑的仿真路径。

解决方向：不自研撮合引擎。扩展 Nautilus adapter 输入，让 OC 能把 tick/quote/depth fixture 和策略意图映射到 Nautilus backtest，再把结果回写到标准 artifact。

### P7. Dashboard / CLI 可观察性不足

现状：Dashboard 可以显示策略、报告和项目状态，但实验 lineage、trial pruning、gate drift、artifact 依赖关系还不够清晰。用户需要电脑和手机都能快速知道“现在卡在哪里、下一步该跑什么、为什么不能 paper”。

解决方向：Dashboard 只读 `ExperimentRun`、`ProjectGateSummary` 和 trace；CLI 提供同等查询命令。移动端先做只读，不增加远程执行能力。

### P8. 长回测缺少制度感知与 alpha 衰减证据

现状：OC 已有 OOS、walk-forward、cost sensitivity、benchmark family、universe audit 和 PBO/DSR proxy，但还不能回答“策略是否只靠老数据撑分”“近期边际是否死亡”“最差市场制度是否可接受”。`/root/OC_REGIME_DECAY_PLAN.md` 已核实这个缺口，并给出可落地方案。

解决方向：把逐 bar equity/return 序列持久化为 artifact；新增 `regime_performance` 和 `alpha_decay` 两个 research gate；新增 opt-in `EvaluationPolicy`，让策略声明 edge half-life、交易频率和回测窗口政策。新 gate 计入 `research_pass`，不是 `paper_ready_pass`。

## 3. 目标架构

```text
playground idea
  -> source research packet
  -> experiment run
  -> factor lab / search / execution sim artifacts
  -> local report
  -> optional promote-to-audited request

audited strategy
  -> research brief
  -> source card linkage
  -> capability / universe / data audit
  -> factor lab evidence
  -> bounded search policy
  -> benchmark / OOS / walk-forward / PBO
  -> execution reality
  -> promotion report
  -> paper readiness
```

关键规则：

- `playground` 可以快，但永远不能直接 paper。
- `audited` 可以慢，但必须所有 gate 可解释。
- 两条轨道共享同一个实验索引和 artifact 引用格式。
- 从 `playground` 晋级到 `audited` 时，必须重新生成 research brief，并重新跑硬门禁。

## 4. 实施计划

### Wave 1：Research Mode 与 Experiment Index

目标：先解决“研究阶段太重、报告不可查询”的核心问题。

新增文件：

- `open_composer/models/experiment.py`
- `open_composer/experiments.py`
- `open_composer/research/research_mode.py`
- `tests/test_experiments.py`
- `tests/test_research_mode.py`

核心模型：

- `ExperimentRun`
  - `run_id`
  - `name`
  - `research_mode: playground | audited`
  - `kind: factor_lab | parameter_sweep | router_research | execution_sim | promotion | readiness`
  - `strategy_name`
  - `source_spec_path`
  - `spec_hash`
  - `dataset_hash`
  - `started_at`
  - `ended_at`
  - `status: running | ok | warning | blocked | failed`
  - `gate_status`
  - `params`
  - `metrics`
  - `artifact_refs`
  - `blocked_reasons`
  - `parent_run_id`
- `ArtifactRef`
  - `path`
  - `kind`
  - `sha256`
  - `created_at`
  - `producer`
- `ExperimentTrial`
  - `trial_id`
  - `run_id`
  - `params`
  - `metrics`
  - `decision: kept | pruned | rejected | failed`
  - `decision_reason`

CLI：

- `oc experiment list`
- `oc experiment show <run_id>`
- `oc experiment compare <run_id> <run_id>`
- `oc experiment artifacts <run_id>`
- `oc experiment trace <strategy-name>`

门禁：

- `paper_readiness` 必须阻断任何 `research_mode=playground` 的来源 artifact。
- `promotion-report` 可以读取 playground artifact 作为参考，但必须标记为 `reference_only`，不能作为 pass evidence。
- `project gate-state` 只写统一 gate summary，不新建平行状态文件。

验收测试：

- `test_playground_artifact_cannot_satisfy_paper_readiness`
- `test_experiment_run_records_spec_hash_dataset_hash_and_artifacts`
- `test_experiment_compare_reports_metric_delta`
- `test_cli_and_dashboard_read_same_experiment_index`

### Wave 2：Factor Lab V2（非 ML）

目标：把“参数组合搜索”前移为“因子质量诊断”，但不引入训练模型。

新增文件：

- `open_composer/research/factor_panel.py`
- `open_composer/research/factor_lab_v2.py`
- `tests/test_factor_lab_v2.py`

核心模型：

- `FactorPanelRow`
  - `timestamp`
  - `symbol`
  - `factor_name`
  - `factor_value`
  - `forward_return`
  - `horizon`
  - `group`
  - `market_cap_bucket`
  - `source`
  - `visible_at`
- `FactorPanelReport`
  - `coverage_pct`
  - `missing_pct`
  - `rank_ic`
  - `ic_mean`
  - `ic_std`
  - `icir`
  - `ic_t_stat`
  - `decay_by_horizon`
  - `quantile_returns`
  - `top_bottom_spread`
  - `turnover`
  - `factor_correlation_matrix`
  - `neutralized_metrics`
  - `quality_flags`

CLI：

- `oc strategy factor-panel build <spec>`
- `oc strategy factor-lab-v2 <panel-path>`

实现约束：

- 第一版只支持本地 panel CSV/Parquet/JSONL 和现有 OHLCV 多标的合成。
- 中性化第一版只做简单 group demean 和 market-cap bucket demean，不做复杂 risk model。
- 缺少 PIT 元数据时输出 `warning` 或 `blocked`，不能静默通过。

验收测试：

- `test_factor_lab_v2_computes_rank_ic_icir_and_decay`
- `test_factor_lab_v2_flags_low_coverage`
- `test_factor_lab_v2_group_neutralization_changes_metrics`
- `test_factor_lab_v2_requires_visible_at_for_feature_packet_panel`

### Wave 3：SearchPolicy 与 Trial Governance

目标：统一普通策略、router、factor search 的搜索记录和剪枝原因。

新增或扩展：

- `open_composer/research/search_policy.py`
- `open_composer/research/kernel/trials.py`
- `open_composer/research/parameter_sweep.py`
- `open_composer/research/router_common.py`

核心模型：

- `SearchPolicy`
  - `strategy: grid | random | evolutionary`
  - `candidate_budget`
  - `random_seed`
  - `objective_set`
  - `prune_rules`
  - `requires_nested_validation`
- `ObjectiveSet`
  - `primary_metric`
  - `secondary_metrics`
  - `constraints`
  - `tie_breakers`
- `TrialDecision`
  - `trial_id`
  - `decision`
  - `reason`
  - `metrics_snapshot`

策略：

- 默认仍是 random/grid。
- `evolutionary` 只允许 router 或多目标策略使用，且必须有 `objective_set`、预算和 OOS 外部评估。
- 不在本轮引入 Optuna、pymoo 或其他依赖；先把接口和 trial governance 做稳。

验收测试：

- `test_parameter_sweep_writes_trial_decisions`
- `test_router_search_requires_objective_set_for_evolutionary_policy`
- `test_search_policy_budget_blocks_excess_trials`
- `test_experiment_index_links_trials_to_run`

### Wave 3A：Regime Performance 与 Alpha Decay

目标：在 OOS、walk-forward、PBO 之外，补“制度最差表现”和“alpha 是否衰减”两道研究证据，直接回答长回测是否被老数据污染。

依据文档：

- `/root/OC_REGIME_DECAY_PLAN.md`

新增或扩展：

- `open_composer/models/backtest.py`
- `open_composer/engines/backtest_engine.py`
- `open_composer/research/series_io.py`
- `open_composer/research/regime_performance.py`
- `open_composer/research/alpha_decay.py`
- `open_composer/research/evaluation_policy.py`
- `open_composer/research/promotion.py`
- `harness/artifact_contracts.yaml`
- `tests/test_regime_performance.py`
- `tests/test_alpha_decay.py`
- `tests/test_backtest_equity_series.py`

前置 M0：逐 bar equity series artifact

- `backtest_frame` 写 `reports/backtests/{run_id}-equity.json`
- 内容包含 `run_id`、`timestamps`、`equity`、`bar_returns`
- `BacktestRun` 加可选 `equity_series_path`
- 新增 `load_equity_series(root, run_id)`
- 首 bar `bar_returns` 置 0，禁止 NaN

Regime Performance：

- 只用截至当前 bar 的 trailing return 和 trailing realized volatility 标签，避免未来函数。
- 制度桶：`bull/bear x low/mid/high volatility`
- 每桶输出 sample share、annualized return、Sharpe proxy、hit rate、max drawdown。
- 输出 `min_regime_sharpe`、`min_regime_return_pct`、`regime_thin`、`regime_unseen`。
- 极差最差制度为 `blocked`；样本不足为 `warning` 或 `not_applicable`。

Alpha Decay：

- 输入 full-window `bar_returns`。
- 输出 rolling Sharpe slope、old/mid/recent Sharpe、recent Sharpe、old PnL concentration、`alpha_stale`。
- 前段强正、近期非正或收益高度集中在老数据时 `blocked`。
- 样本太短时 `not_applicable`，不能伪装成通过。

EvaluationPolicy：

- `StrategySpec` 增 opt-in `evaluation_policy: EvaluationPolicy | None = None`
- 字段：`edge_type`、`edge_half_life_days`、`trade_frequency_per_day`、`backtest_window_policy`、`refit`、`require_recent_oos_positive`
- 旧 spec 必须继续 validate。
- 缺 `evaluation_policy` 的旧 active 策略默认 warning，不默认 block；`OC_HARNESS_STRICT=1` 可升级。

Promotion / CLI / Harness：

- `promotion-report` 新增 `regime_performance`、`alpha_decay` checks。
- 两个 checks 加入 `research_gate_names`，计入 `research_pass`。
- 新增 CLI：
  - `oc strategy regime-performance <spec>`
  - `oc strategy alpha-decay <spec>`
- 新增 artifact contracts：
  - `reports/research/{strategy}-regime-performance.json`
  - `reports/research/{strategy}-alpha-decay.json`

验收测试：

- `test_backtest_writes_equity_series_artifact`
- `test_regime_labels_are_leak_free`
- `test_regime_performance_flags_unseen_crash_bucket`
- `test_alpha_decay_stationary_positive_returns_ok`
- `test_alpha_decay_front_loaded_returns_blocked`
- `test_evaluation_policy_is_optional_for_legacy_specs`
- `test_promotion_report_includes_regime_and_decay_checks`
- `test_regime_and_decay_blocked_status_affects_research_pass`

### Wave 4：Tick / L1 / L2 数据契约

目标：建立 OC 能理解的市场微观结构数据类型，但不承诺供应商。

新增文件：

- `open_composer/models/market_data.py`
- `open_composer/data_contracts.py`
- `data/fixtures/market_data/trade_ticks.jsonl`
- `data/fixtures/market_data/quote_ticks.jsonl`
- `data/fixtures/market_data/order_book_deltas.jsonl`
- `tests/test_market_data_contracts.py`

核心模型：

- `TradeTickRow`
  - `timestamp`
  - `symbol`
  - `price`
  - `size`
  - `exchange`
  - `conditions`
  - `source`
- `QuoteTickRow`
  - `timestamp`
  - `symbol`
  - `bid_price`
  - `bid_size`
  - `ask_price`
  - `ask_size`
  - `exchange`
  - `source`
- `OrderBookDeltaRow`
  - `timestamp`
  - `symbol`
  - `side`
  - `price`
  - `size_delta`
  - `level`
  - `sequence`
  - `source`
- `MarketDataManifest`
  - `kind`
  - `symbol`
  - `venue`
  - `first_timestamp`
  - `last_timestamp`
  - `row_count`
  - `timezone`
  - `source`
  - `quality_flags`
  - `sha256`

Capability registry 扩展：

- `market_data_kinds`
- `min_resolution`
- `book_depth`
- `venues`
- `paper_ready`
- `strict_behavior`

验收测试：

- `test_trade_tick_contract_requires_price_size_timestamp`
- `test_quote_tick_contract_requires_bid_ask_ordering`
- `test_order_book_delta_contract_requires_sequence`
- `test_market_data_manifest_hash_changes_when_rows_change`
- `test_capability_registry_can_express_l2_research_only`

### Wave 5：Execution Simulation via Nautilus

目标：把执行现实从“报告审查”推进到“可跑的受控仿真”。

新增或扩展：

- `open_composer/adapters/execution/nautilus_microstructure.py`
- `open_composer/research/execution_sim.py`
- `open_composer/models/strategy_spec.py`
- `tests/test_execution_simulation.py`

Execution / RealityModel 扩展：

- `fill_assumption`
  - 保留 `next_bar_open`
  - 新增 `bar_limit_touch`
  - 新增 `quote_mid_or_limit`
  - 新增 `nautilus_fill_model`
- `RealityModel`
  - `latency_ms`
  - `partial_fill_model`
  - `spread_model`
  - `queue_model`
  - `volume_participation_cap`

CLI：

- `oc strategy execution-sim <spec> --market-data <manifest>`

实现约束：

- 第一版只支持 fixture 或本地文件，不联网拉 tick 数据。
- 只允许 research / readiness evidence，不自动下 paper order。
- 如果没有 tick/quote/depth 数据，命令必须明确降级或 blocked，不能伪装成微观结构模拟。

验收测试：

- `test_execution_sim_blocks_without_market_data_manifest`
- `test_execution_sim_records_fill_latency_and_partial_fill_metrics`
- `test_execution_sim_artifact_links_to_experiment_run`
- `test_paper_readiness_requires_execution_sim_for_microstructure_strategy`

### Wave 6：Dashboard / CLI 可观察性

目标：让用户在电脑和手机上快速看到进度、结果、阻塞原因和下一步。

新增或扩展：

- Dashboard experiment list/detail payload。
- Dashboard gate blocker summary。
- Dashboard artifact lineage graph payload。
- CLI 与 Dashboard 共用同一读取函数。

界面原则：

- 移动端只读，不提供执行按钮。
- 电脑端可以生成 queue command，但仍通过本地文件队列和明确命令执行。
- 不新增远程任意命令执行能力。

验收测试：

- `test_dashboard_experiment_payload_matches_cli`
- `test_dashboard_mobile_payload_is_read_only`
- `test_gate_blockers_include_next_command_hint`

## 5. 实施顺序与依赖

优先级：

1. Wave 1：Research Mode + Experiment Index
2. Wave 3：SearchPolicy + Trial Governance
3. Wave 3A：Regime Performance + Alpha Decay
4. Wave 2：Factor Lab V2
5. Wave 4：Market Data Contracts
6. Wave 5：Execution Simulation
7. Wave 6：Dashboard / CLI 可观察性

理由：

- 没有 experiment index，后续 factor、search、execution 产物仍会散落在 reports。
- 没有 search governance，继续增加优化器只会扩大过拟合面。
- Regime / decay 依赖逐 bar equity artifact 和 experiment index，且能最快补足长回测可信度问题。
- Factor Lab V2 依赖 experiment index，但不依赖 tick/LOB。
- Tick/LOB 必须先有数据契约，再谈执行模拟。
- Dashboard 应最后接统一数据源，而不是先做 UI。

### 5.1 迁移与兼容策略

- `research_mode` 不进入 StrategySpec 的交易行为语义。它是 `ExperimentRun`、artifact 和 project gate 的研究元数据，避免破坏 `StrategySpec` 作为策略行为真相源。
- 第一版只保证新 run 写入 experiment index；旧 `reports/` 不强制迁移。
- 如需迁移旧报告，新增可选命令 `oc experiment backfill --strategy <name> --since <date>`，读取旧 manifest、promotion report、parameter sweep JSON 和 factor lab JSON，生成 `backfilled=true` 的索引行。
- backfill 产物只能用于检索和历史回顾，不能补充缺失的 paper readiness evidence。
- 对现有 CLI 的默认行为保持兼容：未传 `--research-mode` 时，旧命令继续按原路径执行，但新增的 artifact writer 会尽量记录 experiment index。
- 如果旧命令无法安全生成完整 `ExperimentRun`，必须写入 `status=warning` 和 `quality_flags=["partial_legacy_index"]`，不能伪装成完整可审计运行。

## 6. 外部依据

- QuantConnect 数据分辨率和研究/生产分离说明了成熟平台会区分 research、backtest、live/paper 的不同阶段。
- NautilusTrader 已提供 backtesting、data catalog、fee/fill model 和 tick/order-book 数据概念，OC 应适配它而不是自研执行引擎。
- Alphalens 的 factor tear sheet 思路支持 IC、RankIC、分位收益、turnover、factor decay 作为因子研究基本指标。
- MLflow Tracking 的 runs、params、metrics、artifacts 结构适合作为本地 experiment index 的字段参考，但本轮不直接引入依赖。
- Bergstra & Bengio 的 random search 结论支持继续把 random 作为默认高效基线；遗传算法/NSGA-II 只适合 router 或多目标场景。

## 7. 严格自审

### Q1. 是否真的避开了 ML 和 A 股？

是。本计划没有 `trained_model`、checkpoint、GPU、模型训练，也没有 Tushare、AKShare、QMT、A 股交易规则。`FactorLabV2` 只处理非 ML 因子诊断。

### Q2. 是否会把 playground 变成绕过门禁的后门？

风险存在，所以必须硬性规定：`playground` 产物不能满足 promotion、paper readiness 或 paper_auto evidence。晋级到 `audited` 必须重新跑 research brief、source linkage、capability、factor、OOS、PBO 和 execution gates。

### Q3. 是否会把 tick/LOB 做成过度工程？

本计划把 tick/LOB 第一阶段限制为 schema、fixture、manifest 和 capability 表达，不做供应商接入，不做高频策略承诺。只有数据契约稳定后才进入 Nautilus execution sim。

### Q4. 是否会重复造 MLflow？

短期只做本地 JSONL/manifest，字段参考 MLflow，不提供复杂 UI、server 或远程 tracking。这样保持 local-first 和轻依赖。未来是否接 MLflow 由实际数据量决定。

### Q5. 是否会重复造 Nautilus？

不会。OC 只负责 StrategySpec、artifact、capability、review、readiness 和 adapter。撮合、fill、fee、event loop 应尽量交给 Nautilus。

### Q6. Factor Lab V2 是否和现有 Factor Lab 重复？

不重复。现有 Factor Lab 保留为单策略/单标的轻量诊断；V2 处理多标的截面 panel 和更完整的 factor tear sheet。两者输出都写入 experiment index。

### Q7. 为什么不先做遗传算法？

因为没有 experiment index 和 search governance 时，遗传算法只会更快制造难以审计的多重试验风险。第一阶段先统一 search policy；evolutionary 只作为 router 多目标扩展点。

### Q8. 是否会影响当前可用 workflow？

Wave 1-3 应保持向后兼容。现有 `parameter-sweep`、`factor-lab`、promotion、readiness 不应被破坏；新功能优先以新增 CLI 和 optional fields 落地。

### Q9. Dashboard 是否会成为第二真相源？

不允许。Dashboard 只能读 `ExperimentRun`、`ProjectGateSummary`、trace 和 artifact refs。所有写入仍来自 CLI/agent 受控函数。

### Q10. research_mode 是否会破坏 StrategySpec 的真相源地位？

不会。`research_mode` 是运行和证据的元数据，不是策略行为。策略进出场、数据源、执行、成本、组合、因子仍在 StrategySpec；某次运行是 playground 还是 audited 由 `ExperimentRun` 和 artifact metadata 表达。

### Q11. 哪些验收测试必须优先落地？

最关键的首批测试：

- `test_playground_artifact_cannot_satisfy_paper_readiness`
- `test_experiment_run_records_spec_hash_dataset_hash_and_artifacts`
- `test_search_policy_budget_blocks_excess_trials`
- `test_backtest_writes_equity_series_artifact`
- `test_alpha_decay_front_loaded_returns_blocked`
- `test_regime_labels_are_leak_free`
- `test_factor_lab_v2_computes_rank_ic_icir_and_decay`
- `test_execution_sim_blocks_without_market_data_manifest`

### Q12. Regime / decay gate 会不会让旧策略突然全部失败？

不会。`EvaluationPolicy` 是 opt-in；缺声明的旧 spec 默认只给 warning 或 not_applicable，除非开启 strict harness。真正进入 audited/paper readiness 的新策略才应逐步把这两项变成硬研究证据。

## 8. 明确不做清单

- 不在本计划里接入 Optuna / pymoo / MLflow 运行时依赖。
- 不做模型训练、预测、checkpoint、GPU。
- 不做 A 股相关数据、规则或券商适配。
- 不做公开 Dashboard。
- 不做真金交易。
- 不把移动端做成远程执行控制台。
- 不用全样本统计给 regime 打标签；制度标签必须 leak-free。
- 不把 `regime_performance` 或 `alpha_decay` 塞进 `paper_ready_pass`，它们属于 `research_pass`。

## 9. Done Definition

本计划第一阶段完成标准：

- `uv run ruff format .`
- `uv run ruff check .`
- `uv run pytest`
- `uv run oc repo check --strict`
- 至少完成 Wave 1 和 Wave 3，且测试覆盖 playground 阻断、experiment index、trial decisions、search budget。
- 至少完成 Wave 3A 的 M0 equity series artifact 和 alpha decay 基础测试。
- 文档更新 `docs/user-guide.md`，说明 playground 与 audited 的区别。
- Dashboard 和 CLI 至少有一个共享读取函数验证 parity。

完整完成标准：

- Wave 1-6 全部测试通过，且包含 Wave 3A 的 regime/decay 测试。
- 至少一个现有策略可以在 `audited` 路径保持原行为。
- 至少一个 fixture 策略可以在 `playground` 路径快速跑完，并被 paper readiness 正确阻断。
- 至少一个多标的 fixture panel 可以生成 Factor Lab V2 报告。
- 至少一个前强后弱合成收益序列被 alpha decay 正确判为 blocked。
- 至少一个制度标签单测证明未来 bar 改动不会改变历史标签。
- 至少一份 tick/quote/depth fixture 能生成 market data manifest。
- 至少一个 execution simulation artifact 能链接到 experiment run。
