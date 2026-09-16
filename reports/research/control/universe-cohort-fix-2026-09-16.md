# 股票池月度 cohort 缺陷修复（2026-09-16）

- 缺陷来源：`reports/research/lessons/L-20260916-03.md` 第 4 条（H-20260916-03 执行者顺手记下的数据缺陷）
- 性质：纯数据/工程缺陷，不是策略结论。**没有重跑任何实验，账本 `reports/research/ledger/experiments.jsonl` 一行都没动。**
- 改动范围：股票池构建器、股票池解析函数、小时线构建器的一个守卫、两个测试文件、`data/features/universe/*.parquet` 重建。
  旧文件已备份到 `data/features/universe_backup_2026-09-16/`（含 `_asset_metadata.parquet`）。

## 1. 缺陷是什么

`data/features/universe/{年}.parquet` 本来应该是"每个月末一批、每批约 1100–1240 只票"的月度 cohort。
但里面混进了 **12 个畸形 cohort：每个只有 1 行，日期在月中**。

`open_composer.research.kernel.loop.universe_as_of_calendar_month(panel, date)` 的语义是
"取 `month_end <= date` 的最近那个日历月的整批 cohort"。
当调仓日落在"月中畸形日期之后、真正月末之前"时，这个函数认定的"最近的日历月"就是**当月**，
而当月此时只有那 1 行，于是返回 **1 只票的股票池**。

后果：`build_weight_schedule` 那一周只有 1 行可打分，等权 `1/len(selected)` 只给出 1 只票，
**那一周实际上等于整周空仓/近乎空仓**。基线和所有变体都一样受影响，所以同一轮内部的对比是公平的，
但它安静地吃掉了一部分调仓周。

### 12 个畸形 cohort 全清单（跨全部年份）

| 畸形 month_end | 行数 | 那一行的 symbol | 该行 adv_rank | 同月真正的 month_end（行数） |
|---|---|---|---|---|
| 2016-03-23 | 1 | POM | 376 | 2016-03-31（1174） |
| 2017-10-09 | 1 | MDA | 1215 | 2017-10-31（1229） |
| 2017-11-14 | 1 | Q | 160 | 2017-11-30（1229） |
| 2018-06-14 | 1 | HAWK | 1069 | 2018-06-29（1227） |
| 2018-11-08 | 1 | KTWO | 953 | 2018-11-30（1197） |
| 2019-02-14 | 1 | MB | 805 | 2019-02-28（1174） |
| 2019-08-08 | 1 | APC | 57 | 2019-08-30（1222） |
| 2019-10-02 | 1 | BID | 1014 | 2019-10-31（1210） |
| 2020-12-21 | 1 | HCAC | 1328 | 2020-12-31（1216） |
| 2021-04-05 | 1 | PS | 1078 | 2021-04-30（1223） |
| 2022-10-19 | 1 | CCXI | 598 | 2022-10-31（1164） |
| 2026-09-02 | 1 | APGE | 443 | 2026-09-04（1171，见第 4 节） |

（L-20260916-03 里写的 "2021-04-02" 实际是 **2021-04-05**；它说"约 7 个样本外调仓周"，
实际统计是 **样本外 2018–2026 共 20 周**、全历史 26 周，见第 5 节。这里对那条记录做一次更正。）

这 12 个 symbol 几乎全是**被收购/退市**的名字：POM（Pepco，2016-03 被收购）、HAWK（Blackhawk，2018-06）、
KTWO（K2M，2018-11）、APC（Anadarko，2019-08）、BID（Sotheby's，2019-10）、HCAC（SPAC 合并，2020-12）、
PS（Pluralsight，2021-04）、CCXI（ChemoCentryx，2022-10）等。

## 2. 根因（一段话）

构建器 `open_composer/research/features/universe.py::build_pit_universe_panel` 的 SQL 里，
`monthly` 这个 CTE 用 `ROW_NUMBER() OVER (PARTITION BY symbol, date_trunc('month', trade_date) ORDER BY trade_date DESC)`
取"每只票在每个日历月里自己的最后一根日线"，然后**直接把那一行自己的 `trade_date` 当成 `month_end` 输出**。
对 99.99% 的票来说，这个日期就是该月市场的最后一个交易日，所以看起来没问题；
但一只票如果在月中被收购/退市/长期停牌（或像 APGE 那样在归档的最后一个月里只抓到 09-02 为止的数据），
它"自己的月末"就是月中的某一天，于是它单独变成一个日期值 —— 一个只有 1 行的"cohort"。
排名（`RANK()`）本来就是按整月分区算的，所以这 1 行的 `adv_rank` 是它在整月横截面里的真实排名，
数据本身不错，**错的是它被打上了一个属于自己的 `month_end` 标签**；再叠加消费端"取 `month_end <= date` 的最近日历月"
这条规则，就把"当月"提前激活成了一个 1 只票的股票池。
所以这既不是重复写入，也不是 resample 边界问题，而是"每只票各自的月末"被当成了"整批 cohort 的决策日"。

## 3. 改了什么

### 3.1 构建器（`open_composer/research/features/universe.py`）

1. 新增 `month_last_session` CTE：算出**每个日历月在归档里的最后一个交易日**，作为该月 cohort 的**共享日期**；
   每一行都打上这个共享日期。个股自己的 `dollar_adv` / `close` 仍然取它自己在该月的最后一根日线
   （这是 PIT 正确的：它后面本来就没有价格了），只有 cohort 的**日期标签**变成共享的。
2. 新增 `complete_month_end` CTE：**只输出"已经结束的"日历月**。判据是数据驱动的 ——
   归档里存在更晚月份的交易日，就说明这个月结束了。原因同上：归档尾部那个"还在进行中"的月份
   如果被输出，它的 cohort 日期就必然是月中某一天，会让月度股票池在月中换一批成分，
   这跟上面那个缺陷是同一类错误。等下个月有数据了，重建一次它就会以真正的月末日期出现。
3. `UNIVERSE_PANEL_COLUMNS` 的消费端说明重写（原来那段"两行同一个 cohort 可以有不同 month_end，这是正常的"
   的注释正是缺陷的来源，已改成"一个日历月只有一个共享 month_end"）。

列结构没变，仍是 `month_end, symbol, adv_rank, dollar_adv, close`。

### 3.2 解析函数（`open_composer/research/kernel/loop.py`）

`universe_as_of_calendar_month` 新增关键字参数 `min_cohort_symbols`（默认 `DEFAULT_MIN_COHORT_SYMBOLS = 50`）：

- 从最近的日历月往前找，**成分数少于 50 的 cohort 一律跳过**，退回上一个合法 cohort，并打一条
  `logger.warning`（模块 logger `open_composer.research.kernel.loop`），写明跳过了哪个月、多少只、退回到哪个月。
- 如果所有可用 cohort 都不到 50 只（手搭的小 fixture、故意做小的面板），**仍然返回最近那个 cohort**
  并打一条 warning —— 这样小面板调用方的行为跟修复前完全一致，不会突然变成空集。
- 传 `min_cohort_symbols=0` 可以完全关掉这个下限（等于修复前的行为）。
- 真实 top-1500 面板每月 1124–1236 只，50 这个下限远低于真实最小值，所以它只会挡住畸形 cohort，
  不会误杀一个真的很薄的未来股票池。

所有下游都自动受益（它们都走这个函数）：`scripts/run_step13_m_grid.py`、`scripts/screen_factors.py`、
`scripts/build_insider_features.py`、`open_composer/research/news/extract.py`、
`open_composer/adapters/execution/model_ranking_target_weights.py`。

### 3.3 小时线构建器（`scripts/build_hourly_bars.py`）

`_month_universe` 本来就是按"年-月周期"取整批 cohort，所以**它从来没被这个缺陷影响过**
（小时线 P 轨那 18 个账本单元因此与本缺陷无关）。但因为构建器现在不再输出"进行中的月份"，
给它一个还没结束的月份会静默退化成只剩 `FIXED_SYMBOLS`，所以加了一个显式报错，并把过时的注释改掉。

### 3.4 测试

- `tests/test_feature_universe.py`：fixture 增加 `GONE`（2020-02-13 之后不再交易，模拟月中被收购），
  日期范围延到 2020-03-04。新增两个测试：
  - `test_universe_panel_stamps_one_shared_month_end_per_calendar_month`：一个日历月只能有一个 `month_end` 值，
    2 月那批必须是 `2020-02-28`，且 `GONE` 仍然在 2 月那批里（用它自己的最后一天的价量排名）。
  - `test_universe_panel_omits_the_archives_still_running_final_month`：3 月还在进行中，不输出。
- `tests/test_kernel_loop.py`：新增
  - `test_universe_as_of_calendar_month_skips_a_malformed_one_row_cohort`：60 只票的 1 月/2 月 cohort
    加一个 2020-03-11 的 1 行畸形 cohort；问 2020-03-20 必须拿到 2 月那 60 只、必须打 warning、
    `top_n` 仍然生效、`min_cohort_symbols=0` 能复现修复前的 `{"DELISTED"}`。
  - `test_universe_as_of_calendar_month_falls_back_when_no_cohort_clears_the_floor`：所有 cohort 都不到 50 只时
    仍返回最近那批并打 warning。

## 4. 数据重建：前后对比

命令：`./scripts/run_capped.sh --mem 1.8G -- uv run python scripts/build_feature_universe.py --memory-limit 1200MB`
（数据源 `data/sip/daily/*/*.parquet`；没有刷新 Alpaca 资产元数据，沿用缓存里的那份，因此 ETF/基金剔除口径不变；耗时 111 秒。）

### 每年的 cohort 数（不同 `month_end` 取值个数）

| 年 | 修复前 | 修复后 |
|---|---|---|
| 2016 | 13 | 12 |
| 2017 | 14 | 12 |
| 2018 | 14 | 12 |
| 2019 | 15 | 12 |
| 2020 | 13 | 12 |
| 2021 | 13 | 12 |
| 2022 | 13 | 12 |
| 2023 | 12 | 12 |
| 2024 | 12 | 12 |
| 2025 | 12 | 12 |
| 2026 | 10 | 8 |

修复后每年正好 12 个（2026 只有 1–8 月，9 月还在进行中所以不输出）。

### 每批成分数

| | 修复前 | 修复后 |
|---|---|---|
| 总行数 | 153,372 | 152,200 |
| 按日历月分组的批数 | 129 | 128 |
| 每批最少/中位数/最多（按日历月分组） | 1124 / 1185 / 1236 | 1124 / 1185 / 1236 |
| 按 `month_end` 取值分组时的最少成分数 | **1** | **1124** |
| 少于 50 只的 `month_end` 取值 | 12 个 | 0 个 |
| 一个日历月里出现多个 `month_end` 取值的月份 | 12 个 | 0 个 |

修复后每年的最少/中位数成分数：2016 `1162/1184`、2017 `1173/1220.5`、2018 `1172/1211.5`、2019 `1171/1212`、
2020 `1158/1197`、2021 `1211/1227`、2022 `1153/1161.5`、2023 `1164/1181`、2024 `1168/1179`、
2025 `1137/1165.5`、2026（1–8 月）`1124/1136`。

### 除了日期标签，数据本身有没有变

逐 `(日历月, symbol)` 对比备份文件和新文件，**两份文件在共同月份上的成分完全一致**（索引相同，152,200 行对 152,200 行）：

- 11 行的 `month_end` 标签被改正（上表 12 个畸形 cohort 里除 2026-09 的那 11 个）；
- `close` 完全一致；`dollar_adv` 全部一致（`np.isclose` 全 True，浮点值差异只在最后一位）；
- `adv_rank` 有 **19 行** 差 ±1，全部是相邻名次的互换，只涉及 CVSA/DV、ATYR/LIFE、VANI、APXT、AVPT 这几只。
  原因是这些票的 `dollar_adv` 要么完全并列、要么只差一个浮点最小单位
  （例：2016-01 CVSA 与 DV 都是 25,935,979.3，只在最后一位不同），
  DuckDB 并行求和的加法顺序在两次运行之间不同，`RANK()` 的先后就翻了个。
  **对成分没有任何影响**（成分索引完全相同，`top_n=500`/`1500` 的取舍也没变），不是修复引入的。
- 全历史 symbol 并集少了 1 个（`ATAI`），因为它只出现在被丢掉的 2026-09 那批里。
- 唯一"真的少了一批"的是 **2026-09**：修复前有 `2026-09-02`（1 行）+ `2026-09-04`（1171 行），
  修复后整个 2026-09 不输出（归档最新数据是 2026-09-15，9 月还没结束）。

## 5. 股票池发生变化的每周调仓日（2016→2026）

调仓网格 = 每个 ISO 周的最后一个交易日，取自 `data/features/daily` 的交易日历（2016-01-04 → 2026-09-04，共 557 个调仓日）。
对比口径：**旧文件 + 旧解析逻辑**（实验当时真正用到的东西）对 **新文件 + 新解析逻辑**。

**27 个调仓日的股票池变了**，其中 26 个是"从 1 只票变回完整横截面"：

| 调仓日 | 修复前成分数 | 修复后成分数 | 修复后实际用的是哪批 |
|---|---|---|---|
| 2016-03-24 | 1 | 1170 | 2016-02 |
| 2017-10-13 | 1 | 1228 | 2017-09 |
| 2017-10-20 | 1 | 1228 | 2017-09 |
| 2017-10-27 | 1 | 1228 | 2017-09 |
| 2017-11-17 | 1 | 1230 | 2017-10 |
| 2017-11-24 | 1 | 1230 | 2017-10 |
| 2018-06-15 | 1 | 1223 | 2018-05 |
| 2018-06-22 | 1 | 1223 | 2018-05 |
| 2018-11-09 | 1 | 1211 | 2018-10 |
| 2018-11-16 | 1 | 1211 | 2018-10 |
| 2018-11-23 | 1 | 1211 | 2018-10 |
| 2019-02-15 | 1 | 1171 | 2019-01 |
| 2019-02-22 | 1 | 1171 | 2019-01 |
| 2019-08-09 | 1 | 1226 | 2019-07 |
| 2019-08-16 | 1 | 1226 | 2019-07 |
| 2019-08-23 | 1 | 1226 | 2019-07 |
| 2019-10-04 | 1 | 1213 | 2019-09 |
| 2019-10-11 | 1 | 1213 | 2019-09 |
| 2019-10-18 | 1 | 1213 | 2019-09 |
| 2019-10-25 | 1 | 1213 | 2019-09 |
| 2020-12-24 | 1 | 1203 | 2020-11 |
| 2021-04-09 | 1 | 1228 | 2021-03 |
| 2021-04-16 | 1 | 1228 | 2021-03 |
| 2021-04-23 | 1 | 1228 | 2021-03 |
| 2022-10-21 | 1 | 1174 | 2022-09 |
| 2022-10-28 | 1 | 1174 | 2022-09 |
| 2026-09-04 | 1172 | 1170 | 2026-08（原来用的是还没结束的 2026-09 那批） |

按窗口统计（只算前 26 个"1 只票"的周）：

- 全历史 2016-01-08 → 2026-09-04：**26 / 557 = 4.67%**
- 样本外 2018–2026（Step 11/13 的测试年）：**20 / 453 = 4.42%**
- 2018–2022：**20 / 261 = 7.66%**
- **2024 年以后：0 周**（所以所有"近窗"结论都没被这个缺陷污染）

另外有 3 个调仓日（2016-01-08 / 01-15 / 01-22）股票池是空的，修复前后都空 —— 这是正确的，
第一批 cohort 是 2016-01-29，在它之前本来就没有可用股票池，跟本缺陷无关。

`universe_top_n=500` 的变体同样是这 27 个调仓日发生变化（1 只票或 0 只票 → 382–417 只）。

## 6. 原则上受影响的账本族与单元

以下账本记录**数字一个都没改**，但它们是在"约 4.4% 的样本外调仓周整周只有 1 只票（≈ 空仓）"这个条件下算出来的：

- **`step13_recent_high_return`，32 个单元**（全部走 `loop.build_weight_schedule` → `universe_as_of_calendar_month`）：
  - `step13_m0_*`（6 个：momentum_252_21 / ret_126_rel / ret_63_rel × gate_on/off）
  - `step13_m0b_*`（16 个：mom、mom_over_vol63 × uni200/uni500 × k20/k50 × gate_on/off）
  - `step13_m1_single_cell_*`（9 个：daily27 / alpha158 / alpha101 / alpha191 / osap_price /
    reversal_trend / screened_top40_recent）
  - `step13_m1_two_stage_daily27_uni500_pf100_k50_gate_on`（1 个）
- **`step11_baseline_chain`，7 个单元**：`step11_b0_equal_weight_universe`、`step11_b1_momentum_top50`、
  `step11_b2_ridge_top50`、`step11_b2_ridge_top50_rebalance_dates`、`step11_b3_lightgbm_grid_daily_only`、
  `step11_b3_lightgbm_grid_daily_only_SMOKE_2fold`、`step11_b3_lightgbm_grid_daily_plus_intraday`
- **不受影响**：
  - `step13_p_rt_hourly_*`（18 个单元）—— 走 `scripts/evaluate_reversal_trend_hourly.py`，
    它的股票池来自 `scripts/build_hourly_bars.py::_month_universe`，那里本来就是按"年-月周期"取整批 cohort。
  - `groupb_recent_regime_high_hit_rate`（3 个单元：ETF pullback / QQQ intraday / beta router）——
    不用这个股票池。

同样"原则上受影响"的非账本产物（没有重跑）：`reports/research/iterations/h20260916_03_meta_label/`
（H-20260916-03 那一轮的元标签对比，基线和变体同样受影响，所以那一轮的**相对**结论不变）、
`scripts/screen_factors.py` 的因子筛选输出、`data/features/news_packets` 的每周候选池。

### 怎么理解"数字没改"

- 缺陷对**同一轮内所有单元是同向、同幅度的**（基线和变体用的是同一个股票池），
  所以任何"变体 vs 基线"的相对结论都还成立，这也是 L-20260916-03 那一轮不需要重跑的原因。
- 缺陷对**绝对量级**是有影响的：那 20 个样本外周相当于强制空仓，会同时压低 CAGR、压低回撤、压低波动。
  也就是说，账本里这些单元的绝对收益略偏低、风险指标略偏好。
- 因此：**不要**把修复前的绝对数字和修复后重跑的绝对数字直接比；需要比的时候必须重跑基线。
  本次**没有**重跑任何实验，这是刻意的（族预算和 5 小时额度都不该花在这上面）。
- 下一次任何一个用到 `universe_as_of_calendar_month` 的新实验，自动就是修复后的股票池；
  如果要和账本里的旧行比，必须在同一份新股票池上重跑一个基线。

## 7. 验证

- `uv run ruff format` / `uv run ruff check`：改动的 5 个文件全过。
- `uv run pytest tests/test_kernel_loop.py tests/test_feature_universe.py tests/test_news_extract.py
  tests/test_model_ranking_target_weights.py tests/test_screen_factors.py
  tests/test_reversal_trend_signal_engine.py`：全过（其中 4 个文件是 `universe_as_of_calendar_month`
  的其他调用方，用来确认小面板回退路径没把它们弄坏）。

## 8. 改动文件清单

- `open_composer/research/features/universe.py`（构建器 SQL + 消费端说明）
- `open_composer/research/kernel/loop.py`（`min_cohort_symbols` 下限 + warning + 模块 logger）
- `scripts/build_hourly_bars.py`（空 cohort 显式报错 + 过时注释）
- `tests/test_feature_universe.py`、`tests/test_kernel_loop.py`（新增 4 个测试）
- `data/features/universe/*.parquet`（重建；旧文件在 `data/features/universe_backup_2026-09-16/`）
