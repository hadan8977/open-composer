# Open Composer 能力补强测试计划

日期：2026-05-10

## 目标

本测试计划验证当前能力补强是否形成一个可运行闭环：

1. 策略可以从自然语言生成。
2. 策略会生成不可变版本快照和 manifest。
3. 回测、扫描、paper order、paper runner 可以绑定 `version_id` 和 `spec_hash`。
4. 新增自定义因子表达式可以在 Python 回测和 Pine Strategy 导出中运行。
5. LLM 生成的结构化 feature packet 可以作为可回放因子参与 Python 回测。
6. Dashboard catalog 可以从仓库产物重建策略、版本、运行、信号和兼容性状态，并生成静态只读 HTML 页面。
7. NautilusTrader 后端接入后，执行语义、版本绑定和 replay 路径仍然可测试、可回归。
8. 回测可以显式记录佣金、滑点和总费用。
9. 策略版本可以做 diff，并能安全回滚到 draft/manual 模式。
10. Longbridge 与 Alpaca 的低成本双源路线可以被缓存、标注 provenance，并做同标的同周期差异比较。

## 覆盖范围

### 1. 版本与溯源

- `register_strategy_version()` 会写入：
  - `strategy_versions/<strategy>/<version_id>.yaml`
  - `strategy_versions/<strategy>/<version_id>.json`
- manifest 记录：
  - `strategy_id`
  - `version_id`
  - `content_hash`
  - `source_paths`
  - `snapshot_path`
  - `parent_version_id`
  - `created_by`
  - `prompt_session_id`
  - 数据、执行、LLM 和能力摘要
- lifecycle 操作会记录父子版本关系。
- `oc strategy diff-versions` 可以输出两个版本的 unified diff。
- `oc strategy rollback-version` 会把指定版本恢复到 `strategy_specs/drafts/`，并强制进入 manual/draft 审查流。

### 2. 自定义因子与扩展因子

`StrategySpec.factors` 支持两类因子：

- `expression`：确定性表达式因子，可以被 entry / exit 规则引用。
- `llm_feature`：由 LLM 或外部流程预先写入 JSONL feature packet，再按 timestamp 做无未来函数回放。

新增并验证以下确定性表达式函数：

- `highest(series, window)`
- `lowest(series, window)`
- `lag(series, periods)`
- `roc(series, window)`
- `atr(window)`
- `crossover(left, right)`
- `crossunder(left, right)`
- `stddev(series, window)`
- `zscore(series, window)`
- `macd(series, fast, slow)`
- `macd_signal(series, fast, slow, signal)`
- `macd_hist(series, fast, slow, signal)`
- `bollinger_mid(series, window)`
- `bollinger_upper(series, window, mult=2.0)`
- `bollinger_lower(series, window, mult=2.0)`

这些函数必须满足：

- `oc spec validate` 可验证。
- Python 回测和扫描可执行。
- Pine Strategy 可导出支持的等价表达式。
- unsupported 函数仍会被 capability report 拦截。

### 2.1 成本与滑点

`StrategySpec.costs` 支持：

- `commission_pct`：每次成交的佣金百分比。
- `slippage_bps`：每次成交的滑点 bps。

回测必须满足：

- 默认成本为 0，保持旧策略行为兼容。
- 入场按 long 方向不利滑点调高 fill price。
- 出场按 long 方向不利滑点调低 fill price。
- 报告写入 `Total fees`。
- trade 记录写入 entry / exit fee 和 gross / net PnL。

LLM feature 因子必须满足：

- feature packet 是结构化 JSONL。
- 每条记录必须有 `timestamp` 和指定字段。
- 回测和扫描只使用 bar timestamp 之前或等于当时的最新 feature 值。
- 如果 feature packet 缺失，则使用 `default` 值并保持可回放。

### 2.2 数据源 provenance 与差异检查

新增数据源测试必须满足：

- 每次行情获取都会写入 cache manifest，记录 provider、feed、timeframe、请求区间、缓存路径、记录数和 caveat。
- `oc data compare` 可以比较两路 OHLCV 数据，并输出 JSON / Markdown 差异报告。
- 差异报告必须包含 feed、manifest 路径、匹配覆盖率、close bps 差异、volume 差异比例、缺失 timestamp 样本和数据源 caveat。
- 无外部凭证时，差异比较命令必须能从 `data/fixtures/capabilities/` 回放样例数据，而不是强制 live fetch。
- Longbridge trial 数据源必须至少覆盖：
  - cache replay；
  - live fetch 的可选错误提示；
  - 15m 及以上周期的 OHLCV 回放；
  - 与 Alpaca IEX 的同标的同周期差异报告。

### 3. 新策略生成

端到端生成并验证：

- idea：`Create a QQQ 15m breakout strategy with volume expansion and volatility filter.`
- spec：`strategy_specs/drafts/qqq_breakout_volume_15m.yaml`
- 类型：纯量化策略
- 新因子：
  - `breakout_level = lag(highest(close, 6), 1)`
  - `volatility_range = atr(5)`
  - `bear_cross = crossunder(ema(close, 3), ema(close, 8))`

### 4. 产物绑定

回测、扫描、信号和 paper 产物必须包含或继承：

- `strategy_id`
- `version_id`
- `spec_hash`

Dashboard catalog 读取后，相关 run 必须能回链到版本。

### 5. NautilusTrader 接入

当前已经引入 NautilusTrader 单标的 OHLCV backtest adapter。测试必须覆盖：

- backend 标记可见，且每个 run 能区分 `python_reference`、`nautilus_backtest`、`nautilus_paper` 等执行路径；
- 纯确定性规则在 Python reference 和 NautilusTrader 后端之间保持语义一致；
- replayable 的自定义因子和 `llm_feature` packet 只能以 point-in-time 方式进入执行层；
- paper gate、审计记录、version/spec hash 绑定在后端切换后仍然成立。
- 自然语言生成的策略可以先生成草稿，再激活为 `nautilus_trader`，然后完成真实 backtest、signal log、report 和 Dashboard catalog 回链。
- active `nautilus_trader` 策略执行 paper cycle 时会写出 Nautilus paper plan；该 plan 必须绑定 version/spec hash，并以 `nautilus_paper` execution backend 生成最新 bar paper 信号，再经 Alpaca Paper safety gate。

## 自动化测试

当前新增和扩展的测试覆盖：

| 测试文件 | 验证内容 |
|---|---|
| `tests/test_indicators_expressions.py` | 新增因子函数和表达式求值。 |
| `tests/test_indicators_expressions.py` | 统计类因子到 Pine 的导出。 |
| `tests/test_backtest_scan_pine.py` | 回测报告、信号日志、成本和滑点模型。 |
| `tests/test_strategy_versions_and_capability_expansion.py` | 版本快照、运行绑定、新策略生成、Pine 导出、Dashboard catalog。 |
| `tests/test_strategy_versions_and_capability_expansion.py` | NautilusTrader 真实 backtest、计划文件、版本绑定和 Dashboard 回链。 |
| `tests/test_strategy_versions_and_capability_expansion.py` | 版本 diff、安全 rollback、Dashboard lineage 字段。 |
| `tests/test_strategy_versions_and_capability_expansion.py` | LLM feature 因子的可回放接入。 |
| `tests/test_dashboard_catalog.py` | Dashboard read model 从 repo artifacts 重建，并生成静态只读 HTML。 |
| `tests/test_dashboard_catalog.py` | Dashboard feature packet 区可见 llm_feature replay input logs。 |
| `tests/test_alpaca_paper.py` | paper status、kill switch 和 Dashboard 审计事件。 |
| `tests/test_alpaca_paper.py` | paper account / positions sync、status 聚合和 Dashboard summary 读取。 |
| `tests/test_alpaca_paper.py` | paper orders / account / positions reconciliation、Markdown/JSON 报告和 Dashboard issue count。 |
| `tests/test_alpaca_paper.py` | paper alerts 报告、status 聚合和 Dashboard alert count。 |
| `tests/test_alpaca_paper.py` | paper monitor refresh 一次性重建 reconciliation、alerts、status 和 monitor report。 |
| `tests/test_alpaca_paper.py` | paper monitor loop 按 cycle 重复刷新，并写入 `monitor_cycles.jsonl`。 |
| `tests/test_context_and_research_workflow.py` | 自然语言策略、能力评估、context、paper order 版本绑定。 |
| `tests/test_strategy_lifecycle_and_runner.py` | approve / activate / disable 父子版本和 paper runner 版本绑定。 |
| `tests/test_strategy_lifecycle_and_runner.py` | paper runner cycle 进入 Dashboard run read model，并保留 backend、version 和 spec hash。 |
| `tests/test_strategy_lifecycle_and_runner.py` | Nautilus paper plan 写入 `reports/runs/nautilus_paper/*.json`，`nautilus_paper` paper 信号写入 signal log，并被 Dashboard paper run 回链。 |
| `tests/test_strategy_capabilities.py` | capability report 区分 supported 和 unsupported 表达式。 |
| `tests/test_longbridge_data_adapter.py` | Longbridge cache replay、manifest 写入、Alpaca/Longbridge 差异报告、coverage / bps / caveat 字段。 |

## 实测命令

已执行：

```bash
uv run oc capability test
uv run oc strategy draft --idea "Create a QQQ 15m breakout strategy with volume expansion and volatility filter."
uv run oc spec validate strategy_specs/drafts/qqq_breakout_volume_15m.yaml
uv run oc spec capabilities strategy_specs/drafts/qqq_breakout_volume_15m.yaml
uv run oc strategy versions --strategy qqq_breakout_volume_15m
uv run oc backtest strategy_specs/drafts/qqq_breakout_volume_15m.yaml
uv run oc scan strategy_specs/drafts/qqq_breakout_volume_15m.yaml
uv run oc compile pine-strategy strategy_specs/drafts/qqq_breakout_volume_15m.yaml
uv run oc dashboard catalog
uv run oc dashboard html
uv run oc dashboard review-plan
uv run oc data compare --symbol QQQ --timeframe 15m --left alpaca --right longbridge
uv run ruff format .
uv run ruff check .
uv run pytest
```

## 当前结果

- `uv run ruff check .`：通过。
- `uv run pytest`：`60 passed, 1 warning`。
- `uv run oc capability test`：全部通过。
- 新策略回测：自然语言生成的 breakout strategy 可以完成回测并写入本地 runtime 报告。
- 新策略扫描：生成 1 条最新 entry signal。
- Dashboard catalog：已收录 14 个策略、16 个版本、21 个运行、352 条信号。
- Dashboard HTML：可生成 `reports/dashboard/index.html` 和 `reports/dashboard/strategies/*.html`，作为当前只读工作台基线。
- 数据差异报告：`oc data compare --symbol QQQ --timeframe 15m --left alpaca --right longbridge --left-feed iex` 可以无凭证运行，并在本地 `reports/data/comparisons/` 下生成 JSON / Markdown 差异报告。
- Paper cycle：Dashboard run read model 已可收录 `reports/runs/paper_cycles.jsonl`，显示 `kind=paper` 与版本 / backend 绑定。
- Nautilus paper runtime MVP：paper cycle 会写出 target `nautilus_paper`、selected `nautilus_paper` 的 plan，并生成 `nautilus_paper` paper 信号；订单仍由 Alpaca Paper safety gate 控制。
- Paper account：`oc paper sync-account` 对应的同步逻辑可写入 account / positions 快照，status 和 Dashboard 可读取 equity、cash、buying power、持仓数量、市值和 unrealized PnL。
- Paper reconciliation：`oc paper reconcile` 对应的检查逻辑可生成 JSON / Markdown，识别 filled buy 无持仓、缺失 positions snapshot 等问题，并进入 paper status / Dashboard summary。
- Paper alerts：`oc paper alerts` 对应的告警逻辑可生成 JSON / Markdown，并把 reconciliation、kill switch、open orders、缺失 account、unrealized loss 汇总到 paper status / Dashboard summary。
- Paper monitor：`oc paper monitor` 对应的刷新逻辑可一次性生成 reconciliation、alerts、status 和 monitor report。
- Paper monitor loop：`oc paper monitor-loop` 对应的循环逻辑可重复刷新，并记录每轮 monitor report。
- Dashboard feature packet view：Dashboard HTML 现在可显示 `feature_logs` JSONL 文件、记录数、字段和时间范围。

## 仍不承诺的范围

- 不承诺支持所有量化策略。
- 不承诺 Pine 可导出所有策略。
- 不承诺 ML、组合编排、横截面、多资产权重优化已经完成。
- 不开放真钱实盘写入。
- Dashboard 已具备只读 catalog、D0 review 和静态 HTML 页面；尚未开放前端写控制或远程 paper 管理。
