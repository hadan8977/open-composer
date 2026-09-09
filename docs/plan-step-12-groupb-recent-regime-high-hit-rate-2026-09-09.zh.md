# Step 12 · 策略 B 组：高胜率、近期年化高、适配当前市场（2026-09-09）

版本 v1.0。执行者：Sonnet 5（无上下文，先读本文再动手）。与 Step 11（A 组：九年走查、长期超额）**并行且独立**，两组各自的门槛互不套用。

## 0. 用户需求原话与翻译

用户 2026-09-09 原话："我希望找一些高胜率，近期年化高，更适配当前市场，不会特别要求长期收益的策略。"

翻译成可验收的契约：
- **评价窗口是最近约 2.7 年**（2024-01-02 至档案最新日），不是 2018 起的九年。
- **主要指标是持有期胜率与近期净年化**，其次是回撤与盈亏比；长期（2018-2023）表现**只作信息披露，不作门槛**。
- **代价要写明**：短窗口证据脆弱，高胜率策略常伴随负偏度（小赚多次、偶尔大亏），当前市场风格一变就可能失效。这些是用户明确接受的取舍，但报告必须把它们量化出来，不许省略。

## 1. B 组验收契约（预注册，见到结果后不得放宽）

写成 `config/promotion/recent-regime-high-hit-rate-gates.json`（`contract_id: recent_regime_high_hit_rate_gates_v1`），字段：

| 门槛 | 阈值 | 说明 |
|---|---|---|
| `hit_rate_by_holding_period` | ≥ 0.60（周持有）/ ≥ 0.55（日持有或日内） | 每个持有期净收益 > 0 的比例；空仓期不计入分母 |
| `cagr_recent_net` | ≥ 0.20 | 2024-01-02 起，每边 10bp 成本后 |
| `max_drawdown_recent` | ≥ -0.15 | 同窗口 |
| `sharpe_excess_bil_recent` | ≥ 1.5 | 同窗口，相对 BIL |
| `profit_factor` | ≥ 1.5 | 盈利持有期总和 / 亏损持有期总和 |
| `positive_quarter_fraction` | ≥ 0.70 | 按自然季度 |
| `dsr_probability` | ≥ 0.5 | 试验数自动取账本里 `groupb_` 同族实验数 |
| `stress_cost_still_positive` | 25bp/边下近期 CAGR > 0 | 压力成本 |
| ML 类额外 | 安慰剂（打乱标签）rank IC 绝对值 < 0.02 | 只对 F4 |

**披露项（必须报告，不设门槛）**：2018-2023 同一策略的 CAGR/回撤/胜率；收益偏度与最差单周；换手与年成交次数；策略在 2024-2026 每个季度的表现；"如果 2022 年再来一次会怎样"（直接报 2022 全年）。

**走查方式**：按季度滚动，训练/选参窗口为紧邻的前 24 个月，测试下一季度，共约 11 折（2024Q1 起）。规则型策略"训练"= 在前 24 个月网格内选参；ML = 只用前 24 个月训练。隔离期 = 标签周期。成交路径一律 `next_open`（周五收盘信号→周一开盘）或该机制自带的对等路径（F3 用其日内路径）。

## 2. 候选族（网格已在此预注册，不得增加）

按优先级，前三个数据小、跑得快，先出结果：

**F1 ETF 回调均值回归**（经典高胜率族）。标的：SPY、QQQ、IWM、XLK、SMH、XLF、XLE、XLV、XLY、XLI（10 只，`data/sip/daily`）。入场：`close > SMA200` 且 {`RSI2 < 10` | 连续 3 日收阴 | `close < SMA5 − 1.0×ATR14`}（三种入场规则）；出场：{`close > SMA5` | `RSI2 > 70` | 持有满 N 日，N∈{3,5}}；多标的同时触发时等权分配现金，无信号持 BIL。网格 = 3 入场 × 2 出场规则 × 2 N = 12。信号日收盘算、次日开盘成交。

**F2 趋势过滤的动量 + 现金开关**。A 组 B1 的 12-1 动量前 50 等权，叠加市场状态：`SPY > SMA{100,200}` 时持有，否则全部转 BIL；可选波动率目标 {none, 15%}。周频。网格 = 2 × 2 = 4。直接复用 `open_composer/research/kernel/loop.py` 与特征库（在 `RankingStrategy.score` 外层加状态开关，**不改 loop.py**，写在 B 组自己的模块里）。

**F3 QQQ 日内动量**（首 30 分钟收益预测末 30 分钟，Gao 等 2018）。复用 `open_composer/research/kernel/mechanisms/intraday_momentum_etf.py`，分钟线来自 `data/sip/minute`（2023-2026）。参数：信号窗口 {30, 60} 分钟、阈值 {0, 0.2%} 、只做多或多空 = 2×2×2 = 8。**必须**披露 Step 10 §8 记录的模拟盘对等问题（日内成交时点、滑点），把它作为"能否接入"的独立判断。

**F4 横截面短周期 ML**（近期窗口训练）。`GridSelectedLightGBMStrategy`，只用 h=5 与 h=10、深度 {3,6} = 4 格，特征集 `daily_plus_intraday`（短周期反转信息主要在 `ret_1/ret_5/vwap_deviation/overnight_return_5d_mean/intraday_return_5d_mean`），面板先按 `trade_date ≥ 2022-01-01` 裁剪再传入 `run_experiment`（`test_years=(2024,2025,2026)`），`train_row_dates="rebalance_dates"`。**只在 A 组的 B3 intraday 网格结束后运行**（`pgrep -f run_b3_grid` 为空），否则内存不够。

**F5 参考项（不参与晋级）**：QQQ/TQQQ/现金趋势路由（Step 10 的 `beta_exposure_router` 标签），在 2024-2026 窗口上报同一套指标，让用户看到"近期年化最高但回撤最大"的对照，杠杆 ETF 不作为 B 组推荐。

## 3. 产出与时限

- 周三 09-09 22:00 UTC 前：F1、F2、F5 结果进账本（`reports/research/ledger/experiments.jsonl`，family 以 `groupb_` 开头），报告初稿。
- 周四 09-10 22:00 UTC 前：F3、F4 结果，报告成稿 `reports/research/control/step12-groupb-recent-regime-2026-09.md`，B 组最佳候选导出到 `reports/research/candidates/groupb_<experiment_id>/`，接口与 A 组一致（`model.joblib` 可为空、`features.json`、`config.json`、`README.md`），供 Wave C 接入时二选一。
- 进度账本：`reports/research/control/step12-2026-09-09-progress.md`，每个交付物一行 commit 号。

## 4. 执行纪律

- 文件归属：B 组拥有 `open_composer/research/regime/**`（新包）、`scripts/evaluate_groupb_*.py`、`config/promotion/recent-regime-high-hit-rate-gates.json`、`reports/research/control/step12-*.md`；**不得修改** `loop.py`、`mechanism_eval.py`、`b3_grid_strategy.py`、`run_baseline_chain.py`、`run_b3_grid.py`（A 组正在用），也不得碰产品面目录。需要新指标（胜率、盈亏比、季度正比例）写在 `open_composer/research/regime/metrics.py`，门槛评估写 `open_composer/research/regime/gates.py`，可以调用 `mechanism_eval.evaluate_candidate` 拿基础指标再叠加自己的。
- 内存：机器 3.9GB。F1/F2/F3/F5 走 `./scripts/run_capped.sh --mem 1.2G --`；F4 走 `--mem 1.8G` 且只在 A 组网格不在跑时运行。DuckDB `memory_limit='1GB'`、`threads=2`。
- git：只提交自己的路径，用 `git commit -m "..." -- <路径>`（两组共用 index，裸 commit 会误带别人的暂存）。不 push。`Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`。
- 绝不以"等后台通知"结束回合；等就用 `run_in_background: true` 的自退出循环并同时做别的。
- 不读 `.env`，不下单，不碰账户。
- 诚实条款：门槛在本文预注册，看到结果后不得改阈值、不得加网格、不得缩窗口；全部不过就写"全部不过"，并给出最接近的一个与差距。

## 5. 与 A 组的关系

两组并行，共用特征库与账本，互不套用门槛。周五接入模拟盘时由用户在两组各自的最佳候选之间选择；观察模式下也可以两个都接（各自独立的信号日志），这一点在 Wave C 报告里给出方案。
