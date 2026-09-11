# Step 14 计划：与 bar 周期无关的通用运行器（bar-cycle runner）

日期：2026-09-11。作者：协调者（Fable）。执行者：额度重置后的执行代理（无上下文，按本文件执行）。

## 0. 为什么要做这个

用户 2026-09-11 的要求："小时级运行器也是需要的，不能每次我说了你才做一个什么运行器，没有什么通用的解决方案吗。"
现状：`scripts/run_daily_paper_cycle.py` 只会跑日频周期（`paper sync-account` + `strategy target-weights`），
`StrategySpec.timeframe` 已经允许 `1m/5m/15m/30m/1h/4h/daily/weekly`（`open_composer/timeframes.py`），
但没有任何一条产品路径能在日线以外的 bar 收盘后计算信号、记录信号、产出目标权重。Step 13-P 的小时线
Reversal Trend 策略（最佳格 26.3%/-14.7%）因此无法接入观察模式。本计划做一个**所有周期共用**的运行器，
之后任何周期的策略只需提供一个信号引擎，不再为每个周期写运行器。

## 1. 设计（三层接口 + 一个幂等周期）

1. **BarSource（bar 源）**：`get_bars(symbols, timeframe, start, end, *, session="regular", as_of) -> DataFrame[symbol, bar_close_ts(UTC), open, high, low, close, volume]`。
   - `ArchiveBarSource`：DuckDB 读 `data/sip/daily`、`data/sip/minute`，分钟聚合到 5m/15m/30m/1h/4h 时**复用**
     `open_composer/research/bars/hourly.py` 的 09:30 ET 锚定与 DST 处理（把它泛化成 `aggregate_regular_session(minute_bars, timeframe)`）。
   - `AlpacaBarSource`：Alpaca 市场数据 v2 bars（当日尾段，档案更新前的实时部分；免费账户是 IEX feed，与 SIP 档案有差异，必须在产物里披露 `feed`）。
   - 两者输出同一 schema；`as_of` 之后收盘的 bar 一律不返回（PIT）。
2. **SignalEngine（信号引擎）**：`compute(bars_panel, spec, state, as_of) -> (TargetWeights, signals, new_state)`。
   - 现有 `model_ranking_target_weights`（规则/ML 排名组合）包一层适配器即可（无状态，周频再平衡）。
   - 新增 `reversal_trend_engine`：把 `open_composer/research/regime/reversal_trend_hourly.py` 的入场/退出规则（持有 h 根 bar、时间止损/反向退出、容量 10 个仓位各 10%）变成**带持久状态**的引擎；
     状态文件 `reports/execution/<strategy>-state.json`（当前持仓、入场 bar、冷却计数、最后处理的 bar_close_ts）。逐笔策略是路径依赖的，没有状态就不能增量运行。
3. **BarCycleRunner（周期）**：`scripts/run_bar_cycle.py --spec <yaml> [--as-of <UTC ts>] [--follow]`，步骤固定：
   `sync-account（只读）→ 取 bars → 找出状态之后新收盘的 bar → 对每根新 bar 依次 compute → 写信号日志 → 写目标权重 → 观察模式到此为止 / paper 模式走现有下单授权`。
   - **幂等**：同一 `bar_close_ts` 只处理一次（状态里记 `last_bar_close_ts`），重复调用是无害的 no-op。这就是"通用"的关键：
     日线用 cron 一天一次；1h 用 cron 每 30 分钟在 13:00-21:30 UTC 之间调一次，运行器自己判断有没有新 bar；1m 用 `--follow`（常驻循环，每分钟拉一次），代码路径完全相同。
   - `run_daily_paper_cycle.py` 改成 `timeframe=daily` 的薄包装，产物路径不变，现有 cron 与测试不受影响。
   - 产物：`reports/paper/bar_cycle/<strategy>-<timeframe>-<YYYYMMDD>.json`（一天一个文件，内含每根 bar 的处理记录）、`signal_logs/<strategy>.jsonl`（每个信号一行，含 bar_close_ts、feed、state 版本）、`reports/execution/<strategy>-target-weights.json`。
4. **调度**：新增 `oc paper schedule-suggest <spec>` 打印对应周期的 crontab 行（不自动安装；安装仍由协调者经用户同意后做）。

## 2. 纪律与边界

- 观察模式默认；`execution.mode/broker`、lifecycle、kill_switch 一律不由运行器改动；下单路径复用现有 Alpaca Paper 授权检查。
- 数据披露：实时尾段用 IEX 而档案是 SIP，信号可能与回测不同；每个产物记录 `feed` 与 bar 数量；回测与实盘的一致性检查（同一天同一 bar 的信号对比）写进测试。
- 杠杆：用户 2026-09-11 决定——**自带杠杆的 ETF（TQQQ 类）允许作为标的**，融资杠杆仍只作参考；`cagr_excess_vol_matched_spy` 门槛**不放宽**。
- 内存：任何回填/批量重放走 `scripts/run_capped.sh --mem 1.8G`；实时周期本身轻量。
- 提交按 pathspec；`uv run ruff format/check`、相关测试、`uv run oc repo check --strict`（产品面）。

## 3. 交付与顺序（执行代理）

1. `open_composer/execution/bar_source.py`（协议 + Archive + Alpaca 实现）+ `open_composer/research/bars/hourly.py` 的聚合函数泛化 + 测试（聚合与 hourly.py 逐 bar 一致；DST 两侧各一天；PIT 截断）。
2. `open_composer/execution/signal_engine.py`（协议）+ `model_ranking` 适配器 + `reversal_trend_engine`（状态持久化）+ 测试（合成 bar 上的入场/退出/冷却；幂等：同一 bar 跑两次只产生一个信号；状态回放等价于一次性回测的结果）。
3. `scripts/run_bar_cycle.py` + `run_daily_paper_cycle.py` 薄包装改造 + `schedule-suggest` + 测试（观察模式零 broker 写；产物 schema）。
4. 用 Step 13-P 最佳格（h26、时间止损、fBull+fRecL）建 `strategy_specs/drafts/us_reversal_trend_1h_h26.yaml`（timeframe 1h），先 `--as-of` 回放最近 5 个交易日与回测对账，再以观察模式接入并给出 cron 行。
5. 报告章节写入 `reports/research/control/step13-recent-high-return-2026-09.md`（P 轨"产品路径"小节从"缺口"改为"已接入观察模式"）。

预计：两个执行代理工作日；先做 1-3（通用部分），4-5 是第一个用例。
