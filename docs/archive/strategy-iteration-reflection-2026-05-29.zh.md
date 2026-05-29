# 策略优化迭代复盘与产品改进计划

日期：2026-05-29

后续执行计划已整理为自包含文档：

- `docs/strategy-research-product-hardening-plan-2026-05-29.zh.md`

## 结论

本轮优化新增并完成了 `nasdaq_long_short_event_router_1m_sweep_002`。它验证了一个更保守的开盘反转假设：更晚入场、相对成交量确认、QQQ regime 过滤能降低部分回撤，但会显著牺牲收益、Sharpe 和 walk-forward 稳定性。

因此，`sweep_002` 不采用。当前更值得保留继续研究的是 `sweep_001` 的路线：

`lb20_entry2_top1_open0_mom0_rv0.8_qprior_negative_reversal_maxopen0_maxmomnone`

## 本轮做了什么

新增策略草案：

- `strategy_specs/drafts/nasdaq_long_short_event_router_1m_sweep_002.yaml`

新增来源卡：

- `reports/harness/source_cards/nasdaq_long_short_event_router_1m_sweep_002.jsonl`

新增/刷新报告：

- `reports/research/nasdaq_long_short_event_router_1m_sweep_002-adaptive-intraday-router.json`
- `reports/research/nasdaq_long_short_event_router_1m_sweep_002-adaptive-intraday-router.md`
- `reports/research/nasdaq_long_short_event_router_1m_sweep_002-promotion.json`
- `reports/harness/verify/nasdaq_long_short_event_router_1m_sweep_002.json`

外部依据：

- Heston, Korajczyk, Sadka 关于 intraday return patterns 的论文支持继续测试开盘窗口短期反转，但不能直接证明当前策略可交易。
- Alpaca 官方文档显示 IEX 与完整市场数据覆盖不同，因此 Alpaca IEX/cache 仍只能作为研究证据，不能作为 paper-ready 证据。

## 结果对比

| 指标 | sweep_001 | sweep_002 | 判断 |
|---|---:|---:|---|
| OOS 年化收益 | 68.15% | 7.63% | sweep_002 明显退化 |
| OOS Sharpe | 2.14 | 0.48 | sweep_002 不合格 |
| OOS 最大回撤 | -9.60% | -12.44% | sweep_002 未改善 |
| OOS 等权 intraday alpha | 68.60% | 14.68% | sweep_002 明显退化 |
| Full 年化收益 | 33.11% | 27.85% | sweep_002 略低 |
| Full Sharpe | 1.28 | 1.19 | sweep_002 略低 |
| Full 最大回撤 | -16.25% | -12.48% | sweep_002 有改善 |
| Walk-forward 正 alpha | 5/5 | 2/5 | sweep_002 失败 |

本轮实际发现：把入场从 2 分钟推迟到 5/10 分钟，并没有提高真实稳健性，反而丢失了主要收益来源。说明当前 alpha 更像是非常短窗口的开盘失衡，而不是可随意延迟执行的日内趋势。

## 当前策略层判断

1. 日线 TQQQ 防守路由不应继续扩大网格。它能控制回撤，但收益和 alpha 稳定性不足。
2. 1m long-short event router 是目前更有研究价值的方向，但只能处于 research 状态。
3. `sweep_001` 仍是当前最优 deterministic route；`sweep_002` 是一次有价值的反证，不应继续加宽。
4. 下一步不应继续盲目加指标，而应先解决数据严格性、前向验证和路由级因子归因。
5. LLM/news/event 仍只能作为 observation-only，不能影响订单，除非 PIT replay packets 和 marginal lift 证据完整。

## 暴露出的产品问题

### 1. 路由优化命令缺少进度、预算和早停

`sweep_002` 只有 324 个基础候选，但实际运行约 2186 秒，其中：

- 数据加载约 50 秒
- 候选评估约 989 秒
- walk-forward 约 1146 秒

问题不是“能不能跑完”，而是用户和 agent 在运行期间看不到阶段进度、预计剩余时间、当前最佳候选或是否应该早停。

需要改进：

- adaptive router 研究命令输出阶段进度事件。
- 每 N 个候选刷新一次 best-so-far。
- 支持 `--max-runtime-seconds`、`--early-stop-no-improvement`。
- 支持安全 cancel，并写入 failure/partial snapshot。

### 2. Draft router 被迫填写 `selected_route_label`

新建 draft router 时，如果没有 `selected_route_label`，spec validation 会失败。为了跑研究，只能填一个占位 route。这个逻辑不合理。

需要改进：

- draft/research 阶段允许 `selected_route_label: null` 或 `research_pending`。
- 只有 scan、target weights、paper readiness 阶段才强制要求可解析 route label。
- Dashboard 应显示“尚未选择路线”，而不是要求用户或 agent 伪造一个占位路线。

### 3. Factor Lab 与 router 策略不匹配

通用 Factor Lab 对 1m 多股票 router 太慢，而且不适合评估 portfolio-level route。promotion 仍然提示 Factor Lab 缺失。

需要改进：

- 为 `adaptive_intraday_internal_router` 增加轻量 route-level factor attribution。
- 至少覆盖 opening return、prior momentum、relative volume、market gate 的 ablation。
- 不再要求 1m router 跑完整单标的 Factor Lab 才能进入研究判断。

### 4. 数据严格性是当前最大硬阻塞

当前强候选使用 Alpaca IEX/cache，promotion 阻塞在 `strict_data`。这是正确的产品门禁。

需要改进：

- 增加“数据源对比”命令：同一窗口比较 Alpaca IEX、Alpaca SIP（如可用）、Longbridge 或其他可配置源。
- 报告字段需要直接显示 feed mismatch、bar coverage、price drift、volume drift、missing bars。
- Dashboard 需要把 `research_pass=true` 和 `paper_ready_pass=false` 明确分开，避免误读。

### 5. Universe audit 与 spec notes 没有打通

`sweep_002` promotion 阻塞在 universe audit。虽然 spec notes 写了固定 universe 的选择背景，但 audit 没有读取这些 notes 作为结构化证据。

需要改进：

- StrategySpec 增加结构化 `universe_metadata`。
- 至少包含 selection_timestamp、selection_basis、delisting_policy、pit_membership_status。
- 或提供 `oc strategy universe-audit --write-fixed-universe-artifact`，把用户确认的固定池写成可审计 artifact。

### 6. 研究失败候选不应强制完整 harness artifacts

`sweep_002` 明确失败，但 harness verify 仍列出 borrow、ex-dividend、target weights、rebalance intents、short squeeze 等大量缺失 artifact。

这对 promotion 候选是合理的，但对 rejected research iteration 太重。

需要改进：

- 增加 iteration outcome：`adopted | rejected | needs_more_research`。
- rejected iteration 只要求 research report、source cards、reason、metric comparison。
- 只有 adopted/promotion candidate 才进入完整 harness artifact 链。

### 7. 技能文档与 CLI 已经不一致

`strategy-research-orchestrator` 中仍写着 `oc capability evaluate <spec>`，但当前 CLI 只有 `oc capability list/test`。

需要改进：

- 更新 skill 和 docs，避免 agent 按旧命令执行。
- 若仍需要按策略评估 capability，应恢复或新增 `oc capability evaluate <spec>`。

## 下一步建议

优先级从高到低：

1. 不再继续扩展 `sweep_002`。保留它作为反证。
2. 回到 `sweep_001`，先做数据严格化：SIP/第二数据源对比、bar drift、coverage audit。
3. 增加 adaptive router 的 route-level factor attribution，替代全量 Factor Lab。
4. 给 `sweep_001` 做 blind forward-test artifact，锁定参数后只记录未来新数据表现。
5. 如果数据严格化通过，再补齐 target weights、execution observation、short borrow/dividend/squeeze artifacts。
6. 最后才讨论 paper readiness；目前不允许 paper_auto。

## 当前状态

- `sweep_001`: research_pass=true，workflow_pass=true，paper_ready_pass=false。
- `sweep_002`: workflow_pass=true，research_pass=false，paper_ready_pass=false。
- 当前没有任何策略可以合规接入 Alpaca Paper 自动运行。
