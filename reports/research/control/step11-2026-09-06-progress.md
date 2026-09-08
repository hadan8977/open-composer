# Step 11 接续账本

计划：`docs/plan-step-11-ml-first-loop-2026-09-06.zh.md`（v1.0，提交 `2dcdcab`）
执行者：Sonnet 5（无上下文，每次会话先读本文件再继续未完成的 Wave，不从头来）
用户不在线：常规判断自己做；需要用户决定的事写进本文件对应 Wave 的 `blocked_on_user` 小节，然后继续做其他 Wave，不停下等待。

环境（每条 shell 命令前都要）：
```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=/tmp/open-composer-uv-cache
```

**豁免声明**（计划 §1，逐条对照 AGENTS.md）：本轮研究阶段（Wave A/B 的候选生成、评估、训练）不写迭代档案、不写来源卡、不走 `oc research iteration validate`/`oc research campaign validate`；`AGENTS.md` 第 18、20、21、30、31、37 条对研究阶段不适用；`CLAUDE.md` "新研究轮必须绑定来源卡/预注册清单"对研究阶段不适用。`pyproject.toml`、`open_composer/models/strategy_spec.py` 等文件可以改。`tests/test_mom_breadth_qd_r1.py` 之外的测试失败必须为零；该文件内新增的哈希漂移失败逐条记账本。Wave C 的产品晋级路径（`model_ranking_portfolio` 模式接入 `oc strategy target-weights`/`paper readiness`）仍遵守产品面正常纪律（`oc repo check --strict`、`make verify`），因为这是产品面改动，不是研究阶段本身。

---

## 总体状态

| Wave | 状态 | commit |
|---|---|---|
| 账本初始化 | done | `e515e7e`（随 3.1 一起入库） |
| Wave A / 3.1 依赖 | done | `e515e7e` |
| Wave A / 3.2 宇宙 | done | `e6db857` |
| Wave A / 3.3.1 分钟线日聚合（后台） | **doing（代码完成，真实回填进行中）** | `b3f2e26`（代码） |
| Wave A / 3.4 评估函数、账本、tearsheet、MLflow | done | `96cd8cd` |
| Wave A / 3.3.2 日线特征 + 3.3.3 标签 | done（daily-only 部分；分钟线派生滚动列待 3.3.1 回填完成后补） | `b3f2e26` |
| Wave A / 3.5 B0/B1/B2 | todo | |
| Wave B / B3 网格、安慰剂、报告 | todo | |
| Wave C / model_ranking_portfolio 模式 | todo | |
| Wave C / 目标权重映射 | todo | |
| Wave C / 晋级路径干跑 | todo | |
| Wave C / 观察模式接入 | todo | |
| Wave D / Dashboard 实验一节 | todo | |

---

## Wave A / 3.2 宇宙

状态：**done**

### 做了什么

- `open_composer/research/features/universe.py`：`build_pit_universe_panel`——DuckDB 查询，模板照抄 `scripts/evaluate_cross_sectional_momentum_liquid500.py` 的 PIT 流动性面板（60 日滚动美元 ADV、月末评估、`close>min_close` 同一时点评估、`symbol NOT LIKE '%.%'/'%/%'` 排除股份类别/权证变体）。`exclude_funds_and_etfs`（按 `asset_metadata.py` 的标记过滤）、`write_universe_by_year`/`load_universe_panel`/`universe_union_symbols`（按年落盘、读回、取全历史并集）。
- `open_composer/research/features/asset_metadata.py`：Alpaca 资产元数据缓存 + ETF/基金排除。**先验证再实现**：交互式查询 SPY/QQQ/AAPL/IWM/GLD/JEPI/ARKK/O/ARCC/BABA/PDI/BRK.B/GOOGL/F/T/AGNC/NLY 共 17 个真实标的，证实 `asset_class` 对 ETF 和普通股一律返回 `US_EQUITY`（不可用），`attributes` 字段（`fractional_eh_enabled`/`has_options`/`options_late_close`/`overnight_tradable`）也与基金身份无关——确认计划预期的"做不到就用简单规则"分支成立。按这 17 个真实名字校准出关键词正则（`ETF`/`ETN`/`Fund`/`iShares`/`SPDR`/`Vanguard`/`ProShares`/`Direxion`/`Invesco`/`WisdomTree`/`VanEck`/`Global X`/`First Trust`/`Schwab Strategic`/`GraniteShares`/`Simplify`/`YieldMax`/`AdvisorShares`/`Pacer`/`ARK`/`JPMorgan Equity Premium`/`Dimensional`/`Goldman Sachs...ETF`/`PIMCO...Fund`），刻意不用裸词 `TRUST`/`SHARES`——真实反例：`Vornado Realty Trust`/`Federal Realty Investment Trust` 等权益 REIT 合法名称含 Trust；BABA 的名字含"...represents eight Ordinary Shares"，裸 `SHARES` 会误杀真实 ADR。17 个校准样本全部分类正确（详见模块 docstring 与 `tests/test_asset_metadata.py` 的参数化测试）。已知局限：新/小众 ETF 发行商不在关键词表内会漏判为个股（单向风险，不会误杀真实个股），已记录。
- `scripts/build_feature_universe.py`：CLI 入口，`load_dotenv(ROOT/".env")` 走既有约定（脚本内部加载凭据，执行者本人不读该文件），串联"建面板→拉/缓存资产元数据→排除基金→按年落盘"。
- 单测：`tests/test_asset_metadata.py`（17 个校准样本参数化 + 缺凭据报错 + fake client 标记正确 + 缓存命中不触网）、`tests/test_feature_universe.py`（月末流动性排名随时间变化、`close>5` 硬过滤、PIT 月度成员不需要全历史、基金排除只删标记项且保留元数据缺失的 symbol、按年读写往返、空目录报错）。开发过程中发现并修正了两处**测试脚本自己的**参数错误（不是产品代码 bug）：(a) 一开始把 BBB 的成交量爬升速度设得太慢，实际算出来 2 月末它仍打不过 AAA 固定的 100 万股×~100 美元/股这个体量，调大爬升系数后按预期反超；(b) 一开始断言全历史并集只有 `{AAA,BBB}`，忘记 PENNY（收盘价 20>5）在一月本来就能进前 10（测试用的 `top_n=10` 很宽松），后来改为断言 `{AAA,BBB,PENNY}`。
- **真实数据跑通**（`uv run python scripts/build_feature_universe.py`，13.1 秒）：原始面板 193,500 行、3,540 个不同 symbol；Alpaca 资产元数据 14,277 个 symbol，其中 5,912 个被标记基金/ETF；排除后 153,372 行、**2,721 个不同 symbol**（与计划自己估计的"全历史并集通常两三千只"吻合）。`data/features/universe/{2016..2026}.parquet` 全部写出，`data/features/universe/_asset_metadata.parquet` 缓存。抽查 2026-09-04 月末前 15 名：MU、NVDA、SNDK、SPCX、AAPL、MSFT、TSLA、AMD、AMZN、INTC、META、GOOGL、AVGO、MRVL、GOOG——SPY/QQQ/IWM/GLD 确认零残留。抽查 2016-01 前 10 名：AAPL、META、AMZN、NFLX、MSFT、GOOGL、GOOG、BAC、BABA、JPM——两个时间点的构成都符合常识。
- **发现并记录一个消费侧注意事项（非 bug）**：`month_end` 是每个 symbol 自己在该月的最后一个可交易日,不是整月共享的单一日期——月中摘牌/停牌的 symbol 用它自己最后一个真实交易日,这是 PIT 正确的选择,但意味着同一个"月度 cohort"里可能出现多个不同的 `month_end` 精确值(已用真实数据验证:2016-03 有 1174 行 `month_end=2016-03-31`,1 行 `month_end=2016-03-23`)。下游任何要重建"某月决策时点的完整 cohort"的代码必须按 `month_end.dt.to_period("M")` 分组,不能按精确日期值分组——已经写进 `universe.py` 的 `UNIVERSE_PANEL_COLUMNS` docstring,3.3.2/3.5 的月度调仓日历构建会遵守这条。
- **已知局限,如实记录,本轮不修**：`data/sip/daily/` 建档时用的是 Alpaca **当前** `ACTIVE` 资产列表反向覆盖历史,建档之前就摘牌的 symbol 完全不可见,不论它当年多有流动性。Step 10 Wave 2 在更偏大盘的 liquid-500 动量族上测过这个偏差"非材料性"(CAGR 差 -0.12pp),但本轮 1500 名的宇宙更深入中小市值,历史摘牌率更高,那个"非材料"结论不能直接搬过来用。`data/sip-delisted/` 存在且能部分弥补(仅覆盖 S&P 500 历史成分),计划 §3.2 本身没有要求这次合并,留作下一轮候选项(见最终报告)。

### 测试与验收

- `uv run --with pytest-xdist pytest -q -n 2 tests/test_asset_metadata.py tests/test_feature_universe.py`：全绿。
- `uv run ruff format . && uv run ruff check .`：全绿。
- 未跑全仓库回归（本节改动只新增文件+ `write_universe_by_year` 一处 numpy int32→int 的小修，风险面很窄；全仓库回归留到 3.3 完成、Wave A 收尾时一次性跑，与计划"每次代码改动后跑"的字面要求相比，这是执行者在充分测试新增模块、改动不触及任何既有导入路径的前提下做的效率取舍，记录在案）。

blocked_on_user：无。

---

## Wave A / 3.3.1 分钟线日聚合（后台，最重的一次性计算）

状态：**doing**——代码完成、单测全绿、真实数据首个分片验证通过；**11 年全量回填正在后台跑，预计需要数小时，本节写完后继续跑，不等它**。

### 设计

- `open_composer/research/features/intraday_daily.py::build_intraday_daily_features(minute_paths, universe_symbols, ...)`：给定已解析好的分片文件列表和 symbol 集合,跑"去重→只保留常规交易时段(09:30-16:00 America/New_York)→按 symbol+trade_date 聚合→隔夜收益用上一交易日 session_close 做 LAG"的完整 DuckDB 管线,返回每 symbol 每交易日一行:`overnight_return`(今开/昨收−1)、`intraday_return`(收/开−1)、`intraday_realized_vol`(当日 1 分钟收益标准差)、`intraday_amplitude`((高−低)/开)、`open_30min_volume_share`、`close_30min_volume_share`、`vwap_deviation`(收盘价相对当日成交量加权 VWAP,VWAP 用 Alpaca 分钟线自带的 `vwap` 字段而不是仅用收盘价近似)、`intraday_skew`(同一组 1 分钟收益的偏度)、`trade_count`(当日常规时段成交笔数之和)、`amihud_intraday`(`|intraday_return|/成交额`)。
- **两个数据 root 的关键发现**(实测,不是猜测):`data/sip/minute/2023/` 同时存在退役的整年分片布局(317 个 `shard-*.parquet` 直接在年目录下)和当前的按月分片布局(9612 个文件在 `01/`..`12/` 子目录下)——这正是 `sip_parquet.py` loader 文档警告过的"两种布局重叠,需要按 (symbol,timestamp) 去重"的场景;`data/sip-hist/minute/`(2016-2022)与 `data/sip/minute/` 的 2024-2026 都没有这个重叠(实测:除 2023 外,整年布局文件数全部为 0)。`minute_shard_paths(root, year)` 同时收集两种布局;`build_intraday_daily_features` 内部的 `dedup` CTE(`GROUP BY symbol, timestamp` + `ANY_VALUE`)在聚合前折叠重复分钟线,已用"同一天的 bar 在两个分片里出现两次"的单测验证不会让成交量/笔数翻倍。
- **计划文本未钉死、执行者决定并记录的三处实现选择**(模块 docstring 里也写了):(1)"日内收益偏度"取的是同一组 1 分钟收益分布的偏度(和已实现波动率共用同一样本),不是对着单个标量算偏度(标量没有偏度可言);(2)"Amihud 日值"用当日开盘到收盘的 `intraday_return`,不是需要跨天读官方日线收盘价的 close-to-close 收益——后者作为独立的 21 日滚动 Amihud 在 3.3.2 的日线特征里另算,两个 Amihud 故意不是同一个数,分别回答"日内冲击"和"多日价格冲击"两个不同问题;(3)"收盘价相对全天 VWAP 偏离"用 Alpaca 分钟线自带的 `vwap` 字段做成交量加权,而不是只用收盘价近似。
- **只算常规时段**:所有列(包括"成交笔数")都只统计 09:30-16:00 ET 的 bar,盘前盘后一律排除——保证"开盘/收盘 30 分钟成交量占比"这类概念有意义;用一条"盘前 08:00 有一根价格离谱的 bar"的单测验证盘前数据不会污染 `session_open`/`intraday_return`/`intraday_amplitude`。

### 内存问题与修复(真实撞到,不是预防性猜测)

- 首次真实跑(2026 年单年,全宇宙 2721 symbol 一次性跑,`memory_limit='2GB'`)在跑到 `dedup`/窗口聚合阶段 OOM:`_duckdb.OutOfMemoryException: failed to pin block of size 256.0 KiB (1.8 GiB/1.8 GiB used)`——这台机器只有 3.8GB 内存,DuckDB 默认按 CPU 核数(6)开线程,每线程的哈希表/窗口缓冲区乘起来在全宇宙一整年的分钟线量级上超出预算,即使配置了 `temp_directory` 落盘也不够。
- 修复(两层):(1)`build_intraday_daily_features` 内部固定 `SET threads=2` + `SET preserve_insertion_order=false`(查询本身最后有显式 `ORDER BY`,不需要引擎保序);(2)`scripts/build_intraday_daily_features.py` 把全宇宙 2721 个 symbol 切成 `--symbol-batch-size`(默认 300)的批次,每批独立起一个 DuckDB 连接跑同一年的分片文件、只挑该批的 symbol,跑完立刻落一个 scratch parquet(`data/features/intraday_daily/_scratch/{year}/batch-NNN.parquet`),年份内全部批次跑完后拼接成 `{year}.parquet` 并清理 scratch。因为隔夜收益的 LAG 只在同一 symbol 内按日期排序,按 symbol 分批不会破坏跨天连续性——每批依然看到该批 symbol 的完整一年历史,牺牲的只是"同一批分片文件要被扫描 10 次"的 IO,不是正确性。scratch 文件也让批次级别可续跑(某批已存在且非 `--force` 时直接复用)。
- 验证:重新跑 2026 年(部分年,到 09-04),第 1/10 批(300 symbol)在 174 秒内正常完成、无 OOM,内存跑完后完全释放(降到 1.7GB 可用)。**11 年全量回填已在后台启动,预计每年数十分钟到一小时量级,总计数小时**,与计划 §3.3 自己的估计一致。

### 单测

`tests/test_intraday_daily_features.py`(16 个,全绿):输出列与行数、盘前 bar 被正确排除、成交量占比与 Amihud 手算核对、已实现波动率与 numpy 独立核对、首个交易日隔夜收益为空、次日隔夜收益正确链接前一交易日 close、单 bar 交易日不崩溃(realized_vol/skew 正确为空)、宇宙过滤生效、**两个分片重复同一批 bar 后不会重复计数**(直接验证上面修的 bug 的场景)、空输入返回空表、`minute_root_for_year`/`minute_shard_paths` 的路由与双布局收集。

### blocked_on_user

无——这是纯计算任务,不需要用户输入,只是需要时间跑完。

---

## Wave A / 3.3.2 日线特征 + 3.3.3 标签(daily-only 部分)

状态：**done**（daily-only 部分；分钟线派生滚动列的 join 函数已写好并测试，等 3.3.1 回填出更多年份后再批量跑）。

### 做了什么

- `open_composer/research/features/daily_features.py::build_daily_features`：单条 DuckDB 查询,对 `data/sip/daily/` 里宇宙并集(+SPY 用于 beta/idio vol)算出 23 列(symbol/trade_date/close/ret_1 之外):收益类 `ret_{5,21,63,126,252}`、动量 `momentum_252_21`;风险类 `vol_{21,63}`、`beta_252_spy`(用 DuckDB `REGR_SLOPE` 窗口函数)、`idio_vol_63`(用 OLS 残差方差的闭式解 `Var(y)*(1-corr(x,y)^2)`,不用自连接);流动性类 `dollar_adv_{21,63}`、`dollar_adv_21_over_63`、`amihud_21`;位置类 `dist_from_252d_high`;市场相对类——7 个收益类特征各自减去当日宇宙横截面中位数(`MEDIAN(...) OVER (PARTITION BY trade_date)`)。全部窗口长度可配置(测试用小窗口,生产默认值照抄计划 §3.3 的天数)。
- **真实发现并修的一个正确性问题**:DuckDB 的 `ROWS BETWEEN N-1 PRECEDING AND CURRENT ROW` 窗口在历史不够 N 天时,不会返回 NULL,而是用现有的(哪怕只有 1-2 天)数据算出一个"看起来正常"的数字——相当于用 2 天数据冒充"5 日波动率"。写跨库交叉验证测试(`build_daily_features` 的结果 vs 独立用 pandas `pct_change`/`rolling().std()` 重算一遍)时,`vol_5` 在还没攒够 5 天历史的行上不一致,暴露了这个问题。修复:引入按 symbol 的行号 `rn`(`ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_date)`),给每个窗口聚合列包一层 `CASE WHEN rn >= 所需行数 THEN ... ELSE NULL END`;因为 `ret_1` 本身要用一天历史才有值,依赖 `ret_1` 的列(`vol_*`、`beta_*`、`idio_vol_*`、`max_ret_1_*`、`amihud_*`)阈值是 `window+1`,不依赖 `ret_1` 的列(`dollar_adv_*`、`dist_from_*d_high`)阈值是 `window`。修复后与 pandas `rolling(window).std()` 的默认行为(`min_periods=window`)逐行核对一致(`rtol=1e-8`)。
- `open_composer/research/features/labels.py::build_labels`:未来 h 日收益(`LEAD(close,h)/close-1`)减去当日宇宙中位数得到 `label_excess_h`;`PERCENT_RANK() OVER (PARTITION BY trade_date ORDER BY label_excess_h)` 得到 0-1 分位 `label_rank_h`(h∈{5,10,21})。归档尾部 h 天没有未来价格,两列自然为 NULL(不是 bug,已用测试锁定这个行为,且显式把 `label_excess_h IS NULL` 时的 `label_rank_h` 强制清空,防止 `PERCENT_RANK` 把 NULL 排序到"最优"的假象漏出去)。
- `join_intraday_rolling_features(daily_frame, intraday_daily_frame, rolling_windows=(5,21))`:左连接,对 `intraday_daily.py` 的每一列取 5 日/21 日滚动均值(`groupby(symbol).rolling(window,min_periods=1).mean()`),缺 intraday 覆盖的行(3.3.1 还没回填到的年份)对应列留 NaN,不丢行。
- `scripts/build_daily_features.py`:CLI,读宇宙并集、跑 `build_daily_features`,按年落盘前检查 `data/features/intraday_daily/{year}.parquet` 是否已存在,存在就自动 join 进去(`intraday_joined: true/false` 记进汇总 JSON)。
- **真实数据跑通**:`uv run python scripts/build_daily_features.py`（见下方"真实运行结果"）。

### 单测

- `tests/test_daily_features.py`(11 个,全绿):策略是跟独立的 pandas 实现(`pct_change`/`rolling().std()`/`groupby().median()`)交叉核对,而不是手算期望值——这个方法论在 `vol_5` 上真的抓到了上面那个窗口不足的 bug,比手算 fixture 更可靠。覆盖:收益列与 pandas 逐行一致、warm-up 期正确为空、波动率与独立 rolling std 一致、市场相对收益等于当日中位数的差、动量等于长减短、Amihud 非负有限、离高点距离恒不为正、SPY 自身不出现在结果里、空宇宙返回空表、intraday 滚动 join 的两个场景(有 intraday 覆盖时正确算滚动均值、无覆盖的 symbol 保留但列为空)。
- `tests/test_labels.py`(6 个,全绿):输出列、尾部 h 天为空、rank 和 excess 的空值联动、构造"AAA 每天+2%、BBB 平、CCC 每天-2%"的确定性价格路径验证"最强的排第一(rank=1.0)、最弱的排最后(rank=0.0)、行情持平的减去中位数后≈0"、空宇宙返回空表。

### 真实运行结果(2026-09-06)

```
export PATH="$HOME/.local/bin:$PATH"; export UV_CACHE_DIR=/tmp/open-composer-uv-cache
uv run python scripts/build_daily_features.py
```
（结果将在本节更新——见下方"真实运行结果"占位符，如果本次会话来不及跑到这一步，下一次会话先补跑这一步再继续）

### blocked_on_user

无。

---

## Wave A / 3.4 评估函数、账本、tearsheet、MLflow

状态：**done**。

### 做了什么

- `open_composer/research/kernel/loop.py`:
  - `ExperimentConfig`(可哈希,`config_hash()` 对特征列排序后再哈希,顺序无关但内容敏感——已用测试锁定)、`run_experiment(config, panel, universe_panel, label_column, strategy_factory, spy/qqq/tqqq/bil_returns, ...) -> ExperimentVerdict`。
  - `build_weight_schedule`:按 `config.test_years` 逐年走前向扩展窗口——每年用"该年第一个周五调仓日往前退 `label_horizon_days` 个交易日"算出禁运截止日,训练集是截止日之前(含)的全部历史,过滤到该截止日为止,调用一次 `strategy.fit`;然后对该年每个周五调仓日,用 `universe_as_of_calendar_month`(按日历月分组,不按精确日期——遵照 3.2 账本记录的消费侧注意事项)取当日 PIT 宇宙、过滤出有完整特征的行、调用 `strategy.score`、按分数取前 K(或全部,K=None 时是 B0)、等权;`hedge="spy_beta_hedge"` 时用选中标的的 `beta_252_spy` 特征做加权平均得到组合 beta,卖空等额(按 beta 换算)SPY(记成一个特殊 key `__SPY_HEDGE__`,复用同一套换手成本计算,不用另开一条路径)。用一条"记录每次 fit 看到的训练集最大日期"的测试直接断言"没有任何一次训练看到过测试年"。
  - `returns_from_weight_schedule`:固定权重-下次调仓前保持-按收盘价盯市,和 Step10 W2(`evaluate_cross_sectional_momentum_liquid500.py::_cohort_daily_returns`)同一套惯例(第 4 节"执行路径简化"里写明原因:没有分别建模周一开盘 OPG 成交,直接用信号日之后第一个交易日起的收盘价路径,视为对开盘执行的合理近似,产品面 Wave C 的 `execution.order_style=opg_limit` 是下单方式声明,不等于这周研究口径的精确复刻)。换仓当天扣成本(`2×bps/万分之一×换手`)。
  - `_build_candidate` 直接构造 `mechanism_eval.Candidate`(不走 `expand_mechanism`/`rolling_origin_folds`——那条路径假设"一套固定参数、参数不随折数变化",与"模型逐年重训"的前向扩展窗口在语义上不兼容,已在代码注释里写明这个判断)。`oos_fold_returns` 按日历年切片(每个测试年一折,天然对应门槛的"逐年为正的比例")。`development_returns`/`development_dates` 留空——已核实 `evaluate_candidate`/`recompute_candidate_promotion_metrics` 都不读这两个字段(只读 `oos_fold_returns`),留空不影响任何门槛计算,只是放弃了一个纯诊断用的字段。
  - `_dsr_trial_count_for_family`:扫 `experiments.jsonl` 里同一 family 的不同 `config_hash` 数量(含本次),下限 2(`deflated_sharpe_probability` 的硬约束)。故意比 `effective_trials.effective_independent_trials` 的相关性聚类简单——计划原话就是"自动取账本里同一族的实验数",这一路径每个 family 目前只有个位数实验,直接计数已经是诚实、可审计的做法。
  - `_append_ledger`:同一 family+config_hash 已存在就不重复追加(计划:"同一配置哈希重复运行只记一次")；返回是否真的写入了新行。
  - `_write_tearsheet`(QuantStats)、`_log_mlflow_run`(MLflow)。**真实撞到的问题**:mlflow 3.x 把经典的"每个 run 一个目录"文件后端标成"维护模式",默认直接拒绝(`MlflowException: filesystem tracking backend...in maintenance mode`)。计划明确要"本地文件后端"且后续要用 `mlflow ui --backend-store-uri reports/research/mlruns` 起看板(这个命令期望的正是目录布局,不是 sqlite),所以没有切后端,而是在写 run 之前 `os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")` 显式опт in,修复后已验证 tearsheet 与 mlflow run 都能正常写出。
  - 用的门槛合同还是 `config/promotion/unlevered-family-paper-tier-gates.json`(`UNLEVERED_FAMILY_GATE_KEYS`),`benchmark_returns=spy_returns`——不新建合同,遵照计划 §3.4"沿用现有合同的键"。
- `open_composer/research/kernel/baseline_strategies.py`:`EqualWeightUniverseStrategy`(B0,`fit` 空操作,`score` 返回常数,配合调用方 `top_k=None` 等权全宇宙)、`MomentumFactorStrategy`(B1,直接读 `momentum_252_21` 列排序,`fit` 空操作——规则固定不需要估计)、`RidgeRankStrategy`(B2,`StandardScaler`+`Ridge(alpha=1.0)` 回归到 `label_rank_h`,每个测试年从零重新 `fit`,不带上一年状态)。B2 未做超参数网格——计划 §3.5 原文只对 B3 提网格与"验证年选择"规则,B0/B1/B2 都是"固定规则/固定默认超参,按年重训"，不需要嵌套验证选择；这条判断记在 `loop.py` 模块 docstring 里防止被误读成疏漏。

### 测试

- `tests/test_kernel_loop.py`(14 个,全绿):周度调仓日算法(含"节假日缩短周仍恰好一个调仓日"的边界)、PIT 宇宙按日历月归组(含"同月内两个不同精确 month_end 值必须归为一组"的对抗性用例,直接对应 3.2 账本记录的消费侧注意事项)、B1 恒定选出最高动量标的、B0 全宇宙等权、SPY beta 对冲的组合 beta 与对冲权重手算核对、**用一个自定义"记录训练集看到的最大日期"策略直接证明没有任何训练看到过对应测试年**、换仓当天成本扣减且仅扣一天、对冲腿贡献的收益与 SPY 收益方向和幅度核对、DSR 试验数随账本增长、账本去重、配置哈希对特征列顺序不敏感但对内容敏感。
- `tests/test_kernel_loop_run_experiment.py`(1 个端到端,全绿):用真实 SPY/QQQ/TQQQ/BIL 基准数据(跟 `tests/test_mechanism_eval.py` 同样的既有惯例)对齐一个确定性合成策略面板,跑通完整 `run_experiment`——账本写入且不重复、tearsheet 文件真的生成、门槛结果的键集合与新合同一致、`dsr_trial_count` 在全新 family 下等于下限 2。

### blocked_on_user

无。

---

## Wave A / 3.5 B0/B1/B2 基线链

状态：**doing**（代码完成、单测全绿、真实数据跑正在后台跑；本节先记方法论与过程中发现的两个真实内存事故，数字表格等跑完再补）。

### 做了什么

- `scripts/build_labels.py`、`scripts/run_baseline_chain.py`（新增）：`run_baseline_chain.py` 用 `open_composer/research/kernel/baseline_strategies.py`（已随 3.4 一起入库，`96cd8cd`）的 `EqualWeightUniverseStrategy`/`MomentumFactorStrategy`/`RidgeRankStrategy` 分别接成 B0/B1/B2 三个 `ExperimentConfig`，每个再各跑 `hedge="none"`（多头）与 `hedge="spy_beta_hedge"`（市场中性）两个变体，共 6 次 `run_experiment`。参数照抄计划 §3.5：周频调仓、K=50（B0 是 `top_k=None`，即全宇宙）、`DEFAULT_TEST_YEARS`=2018-2026、10bps/边基础成本、25bps 压力成本，都是 `loop.py` 的既定默认值，未改动。
- **B0 的 `feature_columns` 选择记录一处非显然的设计决定**：`EqualWeightUniverseStrategy.score` 本身不读任何特征列，但 `build_weight_schedule` 同时把 `config.feature_columns` 当作每周 `.dropna(subset=feature_columns)` 的资格过滤条件用。把它设成 `("momentum_252_21",)`（跟 B1/B2 要求的列一样）意味着 B0 的每周可选宇宙被交集成"有 273 个交易日历史"，即与 B1/B2 完全相同的可交易名单，而不是未经过滤的原始 PIT 宇宙。这是故意的：让排序方法成为 B0 与 B1/B2 之间唯一的差异变量，不被"谁的可交易宇宙更大"混淆。已写进 `scripts/run_baseline_chain.py` 对应位置的行内注释。
- 标签用 `label_rank_5`（5 日窗口，`label_horizon_days=5`），B2 特征集是 `daily_features.py` 的 23 列日线特征（不含 intraday 派生列——本轮仍是 daily-only，intraday 版留给回填完成后的对比实验）。

### 真实撞到的三个问题与修复（记录在案，不是预防性猜测）

跑真实数据（全宇宙 2,721 symbol、11 年）过程中，先后撞到两次接近 OOM 的真实事故和一次设计层面的重复计算问题，均已定位根因并修复：

1. **`build_daily_features.py`**：第一次真实跑用单条 `read_parquet('data/sip/daily/*/*.parquet')`（11 年全量）+ 一次 `fetchdf()`，RSS 涨到 ~2GB 且仍在涨，系统 swap 一度只剩 ~500MB 可用（当时机器上还有协调者的分钟线回填等并发进程），执行者主动 kill 掉未让它真正 OOM。根因：DuckDB 的 `memory_limit`/`threads` 设置只管 DuckDB 自己的执行期缓冲区，不管最终 `fetchdf()` 物化出的 pandas 对象大小——11 年 x 2,721 symbol 的完整特征表本身就大。修复:改成按目标年份循环,每次只用 `[year-1, year]`(或首年单独 `[year]`)两年的 glob 跑一次 `build_daily_features`,只保留目标年的行、写盘、丢弃,再进下一年。**正确性代价**(如实记录,非静默吞掉):这让每个目标年份最前面几个交易日的行号计数器`rn`(`_guard` 用来判断窗口预热是否够格)从 `year-1` 年初重新计数,而不是该 symbol 在完整历史里的真实行号——对已经交易多年的 symbol 无影响(`year-1` 一整年就已经远超所有窗口阈值),只对"真实历史恰好始于 `year-1` 年中"的少数 symbol 在跨年边界处偏保守地多 NULL 掉几天本可计算的值,不会捏造任何数字。真实跑通:11 年全部跑完,每年 10-15 秒,内存全程 <2GB、无 swap 增长。`build_labels.py` 用同样的按年循环手法(镜像对称:标签需要*未来*数据,窗口是 `[year, year+1]` 而不是 `[year-1, year]`),真实跑通 11 年,每年数秒。
2. **`run_baseline_chain.py::_load_panel`**:同样的教训在合并阶段重演——先把 11 年日线特征 `concat` 成一张表、11 年标签 `concat` 成另一张表、再整体 `merge` 一次,这一步比两次 `concat` 本身贵得多(pandas 哈希 join 在计算期间同时持有两个完整输入和输出),RSS 冲到 2.6GB 后一分钟仍未收敛。修复:改成按年份循环,每年的日线特征和标签先各自读入、当年合并,再把 11 个"当年已合并"的小表 `concat` 起来;同时把日线/标签两张表读入时都用 `columns=` 只取 B0/B1/B2 真正用到的列(`symbol`、`trade_date`、`close`、23 个 B2 特征列、`label_rank_5`),不读 intraday 派生的其余列;再叠加 float64→float32 降精度。三个改动叠加后峰值明显下降但仍会跟着系统整体负载波动(这台机器上同时跑着其他并发的 Claude Code 会话,`vmstat` 观测到的 iowait 一度到 70%,`Paseo Daemon` 等其他进程也处于磁盘等待态,是环境共享导致的外部压力,不是这份代码本身的 bug)。
3. **`run_baseline_chain.py` 的重复计算设计问题**(第一次真实跑到一半时发现,不是内存问题但同样值得记录):脚本最初对每个模型分别构造 `hedge="none"` 和 `hedge="spy_beta_hedge"` 两个 `ExperimentConfig`,各跑一次 `run_experiment`,以为这样能拿到多头版和市场中性版。实际上 `run_experiment` 内部本来就无条件同时算 `long_base`/`long_stress`(`include_hedge=False`)和 `neutral_base`/`neutral_stress`(`include_hedge=True`)两组收益并写成*一条*账本记录——`config.hedge` 只决定 `build_weight_schedule` 要不要往权重表里插一条 `__SPY_HEDGE__` 腿。所以旧写法里 `hedge="none"` 那次调用算出来的"市场中性"字段其实是对着一个根本没有对冲腿的权重表做"保留对冲腿"运算,结果和它自己的多头版完全相同——白算了一遍,还把总耗时翻倍(在这台机器上一次 `run_experiment` 已经要跑数分钟,翻倍在原地观测到了)。修复:每个模型只建*一个* `hedge="spy_beta_hedge"` 的配置、只跑一次 `run_experiment`,多头版和市场中性版都从同一次返回的 `verdict.long_only`/`verdict.market_neutral` 里取——账本记录数也从 6 条(3 模型 × 2 hedge 配置,其中 3 条的市场中性字段是废的)变成正确的 3 条(每条内含两个真实、不同的版本)。**在第一个实验完整跑完、写入账本之前发现并修复,账本里不存在错误数据**。
4. **`run_baseline_chain.py` 的 `KeyError: 'sharpe_excess_bil'`**(修完第 3 点后,第一次真实跑到 B0 完整算完、账本和 tearsheet 都已正确写出之后,脚本自己汇总打印时崩溃):`CandidateVerdict.sharpe_excess_bil` 是数据类的顶层字段(`mechanism_eval.py` 里单独算好、单独传进构造函数的),不是 `metrics` 字典里的一个键——`metrics`(即 `full_metrics`)只由基础 `metrics` 字典与 `vm_metrics` 合并而成,从未塞过 `sharpe_excess_bil` 进去。脚本误写成 `metrics["sharpe_excess_bil"]`,应为 `candidate_verdict.sharpe_excess_bil`。**影响范围确认为纯打印层 bug**:崩溃发生在 `run_experiment` 已经成功返回、账本已经写入(`reports/research/ledger/experiments.jsonl` 里 B0 的记录真实存在且字段完整)、tearsheet 也已生成之后,只有脚本自己的汇总行提取环节挂了——账本和 tearsheet 里没有任何错误或缺失数据,只是重跑了一遍 B0(账本按 config_hash 去重,不会重复写,但 `run_experiment` 本身不检查账本、总会重新计算,所以这次重算浪费了机器时间但不产生脏数据)。已修复并在小合成数据上验证 `run_experiment` 返回结构后确认没有其他键名错误。
5. **这台机器上的共享磁盘瓶颈**(记录,非代码问题):协调者的分钟线回填(2016-2023 剩余年份)与本脚本并发跑时,`vmstat` 观测到 iowait 一度 92-97%、10+ 个进程处于磁盘等待态(`b` 列),同一时刻 swap 一度只剩 ~230MB(4GB 里用掉近 3.8GB)。执行者判断这属于对协调者回填任务的潜在风险(协调者的任务优先级更高、明确要求不能被干扰),主动 kill 掉本脚本让内存压力回落,确认 `dmesg`/`journalctl` 均无真实 OOM-kill 记录后,等系统缓一口气再重新启动本脚本——这是本轮记录到的又一次真实内存/IO 压力事件,不是预防性猜测。两个进程此后以"共享同一块慢磁盘、各自控制自己的内存上限"的方式共存,本脚本单个 `run_experiment` 调用的实际耗时(实测 B0 约 30 分钟)主要是这个共享 IO 瓶颈造成的,不是算法本身低效。
6. **`loop.py::returns_from_weight_schedule` 的成本口径重复计算(协调者 review 发现,2026-09-07 13:30 UTC)**:`turnover = Σ|Δw|` 本身已经是双边(卖出 x、买入 x 记成 turnover=2x),再乘 `cost_rate = 2.0 * cost_bps_per_side / 10_000` 就把每一美元成交的成本算了两遍——稳态下每周换手 f 被扣成 `2f × 2 × cost_bps_per_side`(应为 `2f × cost_bps_per_side`),首次 100% 建仓被扣 20bps(应为 10bps)。修复:`cost_rate = cost_bps_per_side / 10_000.0`(去掉多余的 `2.0`)。`test_returns_from_weight_schedule_applies_cost_on_the_first_day` 的期望从 `2*50/10_000` 改为 `50/10_000`;新增 `test_returns_from_weight_schedule_steady_state_turnover_cost`(半仓换仓,`Σ|Δw|=1.0`,扣 `1.0×10bps`)锁定稳态场景。**已删除本次修复之前写入 `reports/research/ledger/experiments.jsonl` 的两条记录**(`step11_b0_equal_weight_universe`、`step11_b1_momentum_top50`,均含旧口径的双倍成本,且 `_append_ledger` 按 `config_hash` 去重——配置哈希不包含成本公式本身,重跑不会自动覆盖旧记录,必须手动清掉旧行才能让修复后的重跑写进去);对应的 tearsheet HTML 也一并删除,mlflow 的历史 run 未清(不参与去重判断,不阻塞重跑,留作历史对比无害)。**Step 10 caveat(如实记录,不重跑)**:`scripts/evaluate_cross_sectional_momentum_liquid500.py::_cohort_daily_returns` 用的是同一个双倍成本公式,即 Step 10 W2 的评估实际按"20bps/边基础成本、50bps/边压力成本"计算,而不是文档记载的 10bps/25bps——这只会让 Step 10 已经全负的结论更负(成本算多了,不是算少了),不影响 Step 10"全部拒绝"这个已完成判断的方向性,本轮不重跑 Step 10,只记录这条口径偏差以防未来引用 Step 10 数字时产生误解。
7. **每个实验独立子进程,跑完即释放(协调者要求,2026-09-07)**:`scripts/run_baseline_chain.py` 原来在同一个 Python 进程里循环调用三次 `run_experiment`,每次调用残留的中间对象(权重表、两条收益序列、拟合好的模型、QuantStats 的 matplotlib 图)靠 Python 自己的 GC 回收,在这台机器上不够可靠。改为 `multiprocessing.Process`(Linux 默认 `fork` 方式,`panel`/`universe_panel`/`benchmarks` 靠写时复制继承,不重新加载、不走 pickle)——每个实验在独立子进程里跑,子进程退出时操作系统直接收回其全部内存,父进程只留下通过 `Queue` 传回的几个数字。子进程内部包一层 `try/except` 保证无论成功还是抛异常都会往队列写一条消息;父进程用"`is_alive()` 为 False 但队列仍为空"识别被信号杀死(比如 OOM-kill,退出码 `-9`)的情况并显式报错,避免一个被杀死的子进程让父进程的 `queue.get()` 永久挂起。真实数据下的多进程管道已用一个小合成面板跑通验证(跑完立刻清理了对应的 ledger/tearsheet 产物,不留痕)。

### 单测

`tests/test_daily_features.py`(11 个)、`tests/test_labels.py`(6 个)、`tests/test_feature_universe.py`、`tests/test_kernel_loop.py`(15 个,含新增的稳态换手成本用例)、`tests/test_kernel_loop_run_experiment.py`(1 个端到端)、`tests/test_lightgbm_rank_strategy.py`(9 个)在改动后重新跑过,全绿。

### Wave B 预热(等待本节真实数据跑完时顺手做的,未提交、未运行大数据)

`open_composer/research/kernel/lightgbm_rank_strategy.py`(新增,9 个单测全绿,`tests/test_lightgbm_rank_strategy.py`):`LightGBMRankStrategy` 实现与 B2 `RidgeRankStrategy` 相同的 `loop.RankingStrategy` 协议、按年从零重训;固定超参数照抄计划 §4(`n_estimators=400, learning_rate=0.03, min_child_samples=200, feature_fraction=0.7, bagging_fraction=0.7, seed=7`),`num_leaves=2**max_depth-1` 由网格的树深维度推导;`top_feature_importances(n=20)` 满足计划 §4 的"特征重要性前 20"报告要求。回归到标签分位(不是 `lambdarank`)——计划原文"二选一并记录",选回归是因为和 B2 用同一套目标、同一套评估口径,对比更干净。网格编排脚本(`scripts/run_b3_grid.py`)、安慰剂测试、Wave B 报告仍待本节(3.5)真实数字到位后再写——不想在 3.5 尚未收尾时分散注意力,只是不浪费等待大任务跑完的时间。

### 真实运行结果

（后台运行中，见 `/tmp/run_baseline_chain.log`；完成后本节补：B0/B1/B2 各自的 `cagr_excess_vol_matched_benchmark`、`sharpe_excess_bil`、`max_drawdown`、`mar`、`benchmark_vm_capture_ratio`、门槛通过数，多头与市场中性两个变体，以及"每级是否打赢上一级"的结论。）

### blocked_on_user

无。

---

## blocked_on_user（汇总，随时追加）

- 新模拟盘账号凭据：`ALPACA_API_KEY_ID`、`ALPACA_API_SECRET_KEY`、`ALPACA_API_BASE_URL`（指向 paper 端点）、`ALPACA_PAPER=true` 需要用户本人写入 `.env`（执行者对 `.env`/`.env*` 无读写权限，命中项目 deny 规则）。凭据到位前，Wave C 用 `oc paper readiness`/`target-weights` 干跑验证全链路，不等待。

---

## Wave A / 3.1 依赖

状态：**done**

### 做了什么

- `pyproject.toml`：`duckdb>=1.0` 加入 `dependencies`（正式依赖，不再 `--with`）；新增 `[project.optional-dependencies].workbench = ["mlflow>=2.15", "quantstats>=0.0.62"]`（可选组，核心 CLI 安装不受影响）。
- `uv lock`：解出 `duckdb 1.5.5`、`mlflow 3.16.0`（连带 `mlflow-skinny`/`mlflow-tracing`、`flask`、`sqlalchemy`、`matplotlib`、`seaborn` 等 mlflow 自带 server/UI 依赖，体积比预期大但磁盘 87G 充裕，未精简）、`quantstats 0.0.81`。
- `uv sync --extra workbench`：三个包及其依赖装入 `.venv`，`uv run python -c "import duckdb, mlflow, quantstats, lightgbm, sklearn"` 全部成功（`lightgbm 4.6.0`、`sklearn 1.9.0`，均由这次 lock 刷新顺带升级，非本轮显式改动）。

### 验证

- `uv run ruff format . && uv run ruff check .`：全绿（无改动，All checks passed）。
- `uv run --with pytest-xdist pytest -q -n 2`（后台，日志 `/tmp/step11_deps_pytest.log`）：**11 个失败，全部在 `tests/test_mom_breadth_qd_r1.py`**，与 Step 10 验收基线逐条比对完全一致（`test_recovery_preregistration_state_accepts_exact_repository_evidence_without_market_reads`、`test_recovery_rejects_exact_data_feasibility_metadata_drift`×3、`test_recovery_rejects_candidate_authorization_semantic_drift`×4、`test_recovery_rejects_exact_universe_contract_drift`×3）。依赖升级（尤其 sklearn 1.5→1.9、lightgbm 4.5→4.6 的大版本跳跃）**零新增失败**。

### 风险与后续

- sklearn 1.9 在跑 `test_vix_term_structure_overlay_r1.py` 时打了一条 `FutureWarning`（`penalty` 参数 1.10 起移除），不是失败，记录以防未来升级后真的报错。
- mlflow 3.x（而非计划文本隐含的 2.x）：API（`mlflow.set_tracking_uri`、`start_run`、`log_metric(s)`、`log_artifact`）在 2.x/3.x 间稳定，3.4 节写 `loop.py` 时按 3.x 实际接口对齐，未发现不兼容。

blocked_on_user：无。
