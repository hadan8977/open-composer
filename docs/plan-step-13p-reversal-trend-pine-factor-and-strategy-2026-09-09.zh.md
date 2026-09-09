# Step 13-P 计划："Reversal Trend"（用户 Pine 脚本）→ 因子 + 长周期/短周期动量策略

日期：2026-09-09（周三 15:00 UTC）。执行者：P 轨代理（1 小时线与 1 分钟线策略）+ F 轨代理（日线因子表与事件研究，作为其第 5 个库）。本文自足。
门槛合同：`config/promotion/recent-regime-high-return-gates-v2.json`；账本家族 `step13_recent_high_return`。

## 0. 输入与出处（用户 2026-09-09 原话摘要）

- 文件：`docs/inputs/pine/reversal_trend_0522.pine`（Pine v6 指标，169 行）。
- 出处：用户基于 QuanTGT 网站分享的一个**未开源** Pine 指标做的"模拟版"，按原版在图上打点的位置逆向还原；
  参数不可见，细节可能与原版有差异。用户可提供原版在 TradingView 上的截图供比对。
- 用户意图："以此为启发，做一种动量策略"，两个方向：(1) 长周期——官方建议 1 小时线以上，信号更有参考
  意义；(2) 短周期——用户认为在 1 分钟线上也有参考价值。两个方向都可以沿现有思路优化，或作为因子与
  其它指标结合。

## 1. 指标逻辑（Python 语义逐条对应 Pine；移植必须按这里写）

基础量（Pine 内置的精确定义，移植时用同样的递推与种子）：
- `ta.ema(x, n)`：`alpha = 2/(n+1)`，首个值 = 首个非 NA 的 x（**不是** SMA 种子）。
- `ta.rma(x, n)`：`alpha = 1/n`，首个值 = 前 n 个 x 的 SMA。`ta.rsi(close,14) = 100 - 100/(1 + rma(max(Δ,0),14)/rma(max(-Δ,0),14))`。
- `ta.atr(14) = rma(TR,14)`，`TR = max(high-low, |high-close[1]|, |low-close[1]|)`。
- `ta.macd(close,12,26,9)`：`m = ema12 - ema26`，`s = ema(m,9)`，`hist = m - s`。
- `ta.dmi(14,14)`：`+DM/-DM` 经典定义，`+DI = 100·rma(+DM,14)/rma(TR,14)`，`ADX = rma(100·|+DI-(-DI)|/(+DI+(-DI)),14)`。
- `ta.crossover(a,b)`：`a > b and a[1] <= b[1]`；`crossunder` 对称。`ta.highest/lowest(x,n)` 含当前 bar。
- `barstate.isconfirmed`：历史 bar 恒为真；所有信号在 bar 收盘确定。**无 `request.security`，无前视；不重绘。**

参数（全部沿用脚本默认值，本周不调）：EMA 20/50/200；RSI 14，OB 70，OS 30；牛区间 (40,65)，熊区间 (35,60)；
极值回看 15；RecS 峰值 ≥78；事件有效 35 bar；OS 锁复位 RSI ≥45，OB 锁复位 ≤55；MACD 12/26/9，柱确认 "1 Bar"
（`hist > hist[1]`）；ADX 14，牛 ≥18，熊 ≥15；停留 ≥5 bar；ATR 14；RecS 距 EMA20 ≥0.35 ATR；冷却 牛 30 / 熊 20 / RecL 8 / RecS 8。

状态机（每 bar 收盘顺序执行）：
1. 解锁：`osLocked and r >= 45 → osLocked=false`；`obLocked and r <= 55 → obLocked=false`。
2. 进入极值：`enterOS = r<=30 and r[1]>30`；若未锁 → `osArmed=true, obArmed=false, osBar=bar`。`enterOB` 对称。
3. 过期：`bar - osBar > 35 → osArmed=false`（OB 同）。`osActive = osArmed and bar-osBar<=35`。
4. 停留计数：`dwellOS = r<=30 ? dwellOS+1 : 0`；`dwellOB` 对称。
5. 四个信号：
   - `bull = crossover(m,s) and osActive and 40<r<65 and close>ema20 and adx>18 and hist>hist[1]`
   - `recL = crossover(r,30) and dwellOS[1]>=5 and close<ema50 and hist>hist[1]`（再要求 `osActive`）
   - `bear = crossunder(m,s) and obActive and 35<r<60 and close<ema20 and adx>15`
   - `recS = crossunder(r,70) and dwellOB[1]>=5 and highest(r,15)>=78 and close>ema20 and close>ema50 and (close-ema20)/atr>=0.35 and hist<hist[1]`（再要求 `obActive`）
6. 冷却：`fBull = bull and (bar-lastBull>=30)`；`fRecL = recL and (bar-lastRecL>=8) and osActive and not fBull`；熊侧对称（20 / 8）。
7. 触发后：`fBull or fRecL → osArmed=false, osLocked=true`；`fBear or fRecS → obArmed=false, obLocked=true`。

含义：先有超卖事件（RSI ≤30），再等 MACD 金叉、RSI 回到 40-65、价格站回 EMA20、ADX 显示有趋势 → 牛信号
（"回调反转后的趋势延续"）；RecL 是更早的"RSI 从超卖恢复"信号（此时价格还在 EMA50 之下，偏逆势反弹）。
熊侧对称。这是一个**事件型**信号（0/1，稀疏），不是连续因子；因此评估以事件研究为主，横截面因子用其状态量。

## 2. 方向 A：长周期（日线因子 + 1 小时线策略）

### A1 日线因子表（F 轨代理，作为第 5 个库）→ `data/features/reversal_trend/{year}.parquet`
每行 (symbol, trade_date)，float32，约 24 列：`rt_rsi14, rt_macd_hist, rt_macd_hist_slope, rt_bars_since_macd_bull_cross,
rt_bars_since_macd_bear_cross, rt_adx14, rt_close_over_ema20, rt_close_over_ema50, rt_ema20_over_ema50, rt_ema50_over_ema200,
rt_atr_ext_ema20, rt_dwell_os, rt_dwell_ob, rt_rsi_low15, rt_rsi_high15, rt_os_active, rt_ob_active, rt_bars_since_os_event,
rt_bars_since_ob_event, rt_bull_signal, rt_recl_signal, rt_bear_signal, rt_recs_signal, rt_bars_since_bull_or_recl,
rt_bars_since_bear_or_recs`。进入 F 轨 3.5 的筛选（连续列按 rank IC；0/1 列按事件研究）。

### A2 事件研究（F 轨代理，`scripts/event_study_reversal_trend.py`）
日线、全宇宙（PIT top-1500）、2018-2026 与 2024→ 分开：对四个信号各算：事件数、事后 1/5/10/21 日超额收益
（减当日宇宙中位数）的均值/中位数/胜率、按日期聚类的 t 值；对照 = 同日随机等量非信号股票的 1,000 次抽样分布
（占位）。判定："有信息" = 5 日与 10 日超额均值 > 0 且 t > 2.5 且高于占位分布 95 分位。输出
`reports/research/factor_screen/reversal_trend_event_study.md`。

### A3 1 小时线策略（P 轨代理）
- 数据：`data/sip/minute/{year}/{month}/shard-*.parquet`（2023-2026）与 `data/sip-hist/minute/...`（2016-2022），
  时间戳为 UTC，含盘前盘后；1 小时 bar = **常规时段** 09:30-16:00 America/New_York，按 09:30 锚定
  （09:30, 10:30, …, 14:30, 15:30-16:00 为 30 分钟 bar；与 TradingView 美股 1h 一致——**待用户截图确认**）。
  先只建 2024-01 → 今 的 1h bar：宇宙 = 当月 PIT 前 200 美元 ADV + {SPY, QQQ, IWM}（TQQQ 只作参考）。
  DuckDB 按 symbol × 月聚合，`memory_limit 1.5GB`，输出 `data/bars/hourly/{year}.parquet`。
- 信号：在 1h bar 上跑 §1 的移植；多头用 `fBull`/`fRecL`，空头（`fBear`/`fRecS`）只做披露，不进候选。
- 执行：信号 bar 收盘确认 → 下一个 1h bar 开盘成交；成本 5 bp/边（个股）、2 bp/边（ETF）；压力 2.5×。
- 预注册网格（只在退出规则上搜索，指标参数不动）：持有 ∈ {6, 13, 26 个 1h bar}（≈1、2、4 个交易日）×
  退出 ∈ {时间止损, 时间止损或反向信号, 2×ATR(14, 1h) 移动止损} × 信号 ∈ {仅 fBull, fBull+fRecL} = 18 格。
  组合：同时最多 10 个持仓，每个 10% 资金，超额信号按 ADX 高者优先；隔夜持有允许（长周期方向）。
- 评估：`open_composer/research/regime/metrics.py` 的逐笔胜率/盈亏比 + 合同 v2 的组合指标（近期窗、次日开盘、
  DSR 按家族自动计数）；占位 = 同 symbol 同数量随机日期的信号；同时给出 "只在 SPY>200 日线时开仓" 的趋势门变体披露。

## 3. 方向 B：短周期（1 分钟线，P 轨代理，在 A3 之后）

- 标的：SPY、QQQ、IWM 与当月 PIT 前 20 美元 ADV 个股；时段 2024-01 → 今；只用常规时段 1 分钟 bar，不隔夜（收盘前
  5 分钟平仓）。
- 信号：同一移植代码跑在 1 分钟 bar 上（指标参数不变，即 RSI14 = 14 分钟等）。
- 成本：ETF 1.5 bp/边（含半个点差），个股 5 bp/边；压力 2.5×。这是本方向的生死线，报告必须给成本敏感度曲线。
- 网格：持有 ∈ {15, 30, 60 分钟} × 退出 ∈ {时间, 时间或反向信号, 1.5×ATR(14,1m) 移动止损} × 信号 ∈ {fBull, fBull+fRecL} = 18 格。
- 评估：逐笔胜率、盈亏比、日收益序列 → 合同 v2 指标；每日信号数披露；占位同上。
- B2（可选，仅当 A2 证明日线信号有信息）：把分钟级信号聚合成日频特征（当日 fBull/fRecL 次数、最近信号距今 bar 数）
  加入 A1 表，注明这是"信号聚合"，不是被关闭的泛化日内统计特征。

## 4. 代码、测试、归属

P 轨代理：
- `open_composer/research/pine_port/reversal_trend.py`：`compute_reversal_trend(bars: DataFrame[open,high,low,close,volume], params) -> DataFrame`
  （指标列 + 状态列 + 四个信号列；任何 bar 周期通用；状态机按 symbol 顺序循环，其余向量化）。
- `tests/test_reversal_trend_port.py`：(a) 合成序列手算 crossover/停留/武装/过期/锁定/冷却每一条分支；(b) EMA/RMA/RSI/ATR/ADX
  与独立实现（手写公式）对照 `rtol 1e-9`；(c) 一段真实 SPY 日线跑通并断言信号数量为有限且不重绘（逐 bar 增量重算结果一致）。
- `open_composer/research/bars/hourly.py` + `scripts/build_hourly_bars.py`；`scripts/evaluate_reversal_trend_hourly.py`；
  `scripts/evaluate_reversal_trend_minute.py`；`scripts/reversal_trend_parity.py <symbol> <1h|1D> <start> <end>`（打印信号日期时间，
  用来与用户提供的 TradingView 截图逐点比对，差异写进报告）。
F 轨代理：A1 表（`open_composer/research/features/reversal_trend_daily.py`，复用 P 轨的 `compute_reversal_trend`，若 P 轨尚未
提交则先自行实现日线版并在 P 轨提交后对齐）与 A2 事件研究。

## 5. 时间线与交付

- 周三晚：P 轨移植 + 测试提交；`reversal_trend_parity.py` 可用（给用户比对）。
- 周四：1h bar（2024→）+ A3 评估；F 轨 A1 表 + A2 事件研究并入筛选报告。
- 周五 10:00 UTC 前：1 分钟评估（至少 ETF 部分）+ 报告章节 "P 轨：Reversal Trend"
  写进 `reports/research/control/step13-recent-high-return-2026-09.md`；若 A3 某格通过合同 v2，导出为可接入观察模式的候选
  （这类逐笔策略走已有的 StrategySpec 规则路径而不是 model_ranking，产品接入细节在报告里写清，不自行激活）。

## 6. 纪律

与 Step 13 主计划 §6 相同：`run_capped.sh --mem 1.8G`、每代理一个重任务、DuckDB ≤1.5GB/2 线程、`free -m` 可用 <600MB 就等；
只按路径提交；不读 `.env`；等待循环防自匹配（`pgrep -f "build_hourly_bar[s]"`）；每个里程碑给协调者发消息。
不做：调指标参数（保真优先）、空头候选、杠杆、自行安装 cron。
