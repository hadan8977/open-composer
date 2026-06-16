# Open Composer Step 6.6：Step 7 前研究证据加固计划

日期：2026-06-08
前置：Step 6 因子库与 `oc research auto`；Step 6.5 auto research 修复
后续：Step 7.A/B/C 的条件执行

## 0. 一句话目标

在引入 Step 7 的 ML / decay / LLM propose 前，先把 Step 6/6.5 产出的研究证据链修到可审计、可复现、不会把 sample/cache/fallback 误当成 paper-ready。重点是数据 provenance、OOS/过拟合控制、成本假设、因子重复控制。

## 1. 当前问题

### 问题 1：真实 Alpaca run 仍被 strict_data blocking

QQQ + `--data-source alpaca` 的 auto research run 没有 fallback，但 promotion 仍显示：

```text
promotion:strict_data: Promotion requires research_strict or paper_ready data;
acquisition_tier=cache...
```

根因是产品没有区分：

- 本次 fresh live pull 后落盘的缓存；
- 旧 cache replay；
- cache resampled；
- fixture/sample fallback。

当前只要 `source_mode=cache` 就一律 blocked。这会让后续 Step 7 的 ML、LLM、decay 全部建立在 promotion gate 不承认的证据上。

### 问题 2：auto research 缺独立 data provenance artifact

run 目录目前有 `candidates.json`、`ic_scores.json`、`selected_factors.json`、`report.md`，但没有 `data_profile.json`。用户不能直接判断本次研究到底用了 Alpaca live fetch、cache、cache_resampled、fixture fallback，还是 sample。

### 问题 3：因子选择过度集中

最新 `oc research compare` 显示：

- `volatility_rank_20_252` 被选中 23/30；
- `drawdown_guard_20_60` 被选中 17/30；
- 同一个 top-3 组合出现 7 次。

Step 6.5 修好了“选错 family”，但还没解决“不同 thesis 都被同一组 risk filters 主导”的问题。

### 问题 4：IC rejection 不够解释 thesis 对齐

例如 QQQ overnight thesis 中，`overnight_gap` candidates 有有效 IC，但 IC 很弱，没有进入 selected。当前报告没有把“thesis family present but rejected due to weak IC”作为一等信息表达，容易让用户误判为 selection bug。

### 问题 5：缺 OOS / walk-forward 证据

auto research 当前主要是单窗口 IC + draft spec + evidence。它没有为 candidate selection 生成 chronological OOS 检查，也没有记录 selected factor 的 train/test IC sign consistency。

### 问题 6：成本假设默认是 0

auto spec 目前写入：

```yaml
commission_pct: 0.0
slippage_bps: 0.0
impact_eta: 0.0
```

报告会提示 zero fees，但研究入口不应该默默生成零成本策略。对个人 QQQ daily，默认应至少使用保守 slippage。

### 问题 7：数据源质量等级没有产品化

`data.source=alpaca` 不等于 paper-ready。Alpaca IEX/SIP、Longbridge Nasdaq Basic、live fetch、cache replay、resampled cache、fixture fallback 需要进入统一 evidence tier。

## 2. 外部调研约束

- Alpaca market data feed 有 IEX/SIP/overnight 等 feed 差异；feed 会影响 OHLCV 完整性与 overnight 研究解释。
- Broker order type、auction 与 OPG 行为必须以 broker / exchange 官方文档为准，不能靠经验。
- Bailey 与 López de Prado 关于 Probability of Backtest Overfitting、Deflated Sharpe Ratio 的研究支持先补 multiple-testing / OOS guard，再引入 ML。
- Qlib Alpha158 + LightGBM 是机构常见 baseline，但 Open Composer 只有在规则因子证据触发时才应进入 Step 7.A。

## 3. 修复计划

### P0：数据证据分级与 provenance

目标：

- `oc research auto` 支持 `--refresh-data/--use-cache`；
- 每个 auto run 写 `data_profile.json`；
- fresh pull 与旧 cache replay 分开；
- fallback/sample 仍 blocked；
- fresh Alpaca/Longbridge pull 可以进入 `research_strict`，但 paper_ready 仍由 paper readiness gates 控制。

建议 tier：

```text
sample_smoke          sample data; workflow only
fixture_replay        fixture/fallback; workflow only
research_replay_cache local provider cache; reproducible research only
research_strict       fresh provider pull, no fallback, sufficient coverage
paper_ready_live      explicit paper/live readiness context
```

验收：

- sample run 写 `data_profile.json` 且 tier=`sample_smoke`；
- Alpaca cache run tier=`research_replay_cache`；
- Alpaca `--refresh-data` run tier=`research_strict`；
- promotion strict_data 不再把 `research_strict` blocked 为 workflow-only cache。

### P1：报告透明度

目标：

- `report.md` 增加 Data Provenance、Factor Rejection、Thesis Alignment；
- selected 没选 thesis 主 family 时，写明是 weak IC、low coverage、zero variance、insufficient observations；
- `oc research compare` 增加 thesis group 汇总。

验收：

- overnight QQQ report 明确显示 `overnight_gap` candidates 有 IC 但弱，因此未 selected；
- fallback/sample/cached/fresh 状态在 report 首屏可见。

### P2：OOS / anti-overfit guard

目标：

- 对每个 candidate 生成 70/30 chronological IC split；
- 写 `oos_summary.json`；
- report 增加 train/test IC sign consistency；
- 记录 candidate count 作为 multiple-testing budget 下限。

验收：

- 每个 auto run 都有 OOS summary；
- selected factors 的 train/test IC 不一致时 report 给 warning。

### P3：成本默认与 zero-cost 控制

目标：

- auto spec 不再默认为全 0 成本；
- daily QQQ/SYN 默认使用保守 slippage；
- 只有显式 `--zero-cost-smoke` 才允许 0 slippage/fee。

验收：

- 新 auto spec 的 `slippage_bps` 非 0；
- report 不再因为默认 zero fees 给出 blocking warning。

### P4：因子重复控制

目标：

- `_select_top_k` 加 family cap / risk filter cap；
- compare 输出 concentration metrics；
- 同一 thesis primary family 至少保留解释性候选和 rejection reason。

验收：

- 5 个 canonical QQQ thesis 不再全部由 `volatility_rank + drawdown_guard` 主导；
- compare 报告 top factor concentration 与 top-3 signature repeat count。

## 4. Step 7 决策

P0-P4 完成前不执行 7.A。

- 7.A ML backend：暂缓。当前 30 个 auto run 的弱 IC 触发条件未满足。
- 7.B decay monitor：P0-P2 后可做基础版 baseline，不做 retire 决策。
- 7.C.L1 LLM propose：P4 后再做 research-only，先解决选择器重复，再让 LLM 补新维度。

## 5. 非目标

- 不引入 ML 依赖。
- 不修改 4-pass / harness / paper safety 语义。
- 不把 LLM 输出直接接入交易。
- 不删除旧 auto research run。
- 不把 cache replay 伪装成 paper-ready。
