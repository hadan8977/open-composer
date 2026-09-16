# H-20260916-01 第 0 步：Form 4 内部人数据管道（采集器 + 点时特征 + 筛选器输入）

- 卡：`reports/research/hypotheses/H-20260916-01-insider-form4-confirmation-gate.md`
- 能力：`capabilities/registry.yaml` 的 `events.sec_form4_insider`（kind=event，status=trial，provider=sec）
- 完成时间：2026-09-16（UTC）
- 结论一句话：**2016 起的 Form 4 数据已经全部落地并变成点时特征，可以直接进筛选器；但"机会型 vs 例行"这个分类在我们的样本里覆盖率很低（严格版只有 1%~3% 的股票日有信号），这是第 1 步要先看清的事。**

---

## 1. 做了什么（按卡的第 0 步）

| 交付 | 产物 | 状态 |
|---|---|---|
| 能力登记 | `capabilities/registry.yaml` 里的 `events.sec_form4_insider` + `data/fixtures/capabilities/sec_form4_insider.jsonl` | 完成，`uv run oc capability test` 打分 1.00 / 8 条记录 |
| 采集器 | `scripts/collect_sec_insider_transactions.py` | 完成，41 个季度 zip 全部下载并解析 |
| 尾段补齐 | 同一个脚本的 `tail-index` / `tail-fetch` 两个阶段 | 完成（EDGAR 日更索引 + 每份申报的 Form 4 XML） |
| 点时特征 | `scripts/build_insider_features.py` → `data/features/insider/{年}.parquet` | 完成，2016-01-04 起，每股每日 |
| 筛选器输入 | `data/features/insider/screening_panel_weekly.parquet`（周五 × top-500） | 完成；因子集注册名 `insider` |
| 占位 | 特征构建器的 `--shift-filing-dates-days N` | 完成（按申报号随机平移可见日，固定种子） |

代码风格、单测：`uv run ruff format` / `uv run ruff check` 通过；`tests/test_insider_form4_collector.py` 29 个用例全过，其中一半专门钉住"可见日 = 申报日的下一个交易日"这条规则。

---

## 2. 数据从哪来

SEC 的 "Insider Transactions Data Sets"：每个季度一个 zip，把当季**申报**的所有 Form 3/4/5 摊平成 TSV。URL 规律（2026-09-16 实测）：

```
https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{yyyy}q{n}_form345.zip
```

下载到 `data/raw/insider/{yyyy}q{n}.zip`（原始 zip 保留，共 41 个 / 约 420 MB，审计用），解析到
`data/raw/insider/parsed/{yyyy}q{n}.parquet`（约 59 MB）。合计 **367 万行**非衍生品交易记录。

**一个容易搞错的点，卡里也强调过**：季度 zip 是按 `FILING_DATE` 分桶的，不是按 `TRANS_DATE`。
2016q1 那个包里最早的交易日期是 **2005-10-31**，最晚的是 **2019-01-19**（后者是申报人填错年份）。
所以可见性只能挂在申报日上，`TRANS_DATE` 永远不能当可见时间用。这条规则写进了能力卡的 caveats、
两个脚本的模块文档、以及单测。

## 3. 覆盖率

### 3.1 原始申报（按申报年，Form 4 / 4-A，每笔交易算一行）

| 年 | 申报份数 | 交易行数 | 有代码的发行人 | 公开市场买入(P) | 公开市场卖出(S) | 10b5-1 字段可用比例 | 其中打勾比例 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2016 | 152,033 | 282,275 | 5,478 | 35,276 | 70,040 | 0% | — |
| 2017 | 151,928 | 286,577 | 5,352 | 28,276 | 77,986 | 0% | — |
| 2018 | 151,860 | 299,645 | 5,330 | 45,387 | 75,749 | 0% | — |
| 2019 | 147,919 | 289,220 | 5,162 | 39,428 | 73,950 | 0% | — |
| 2020 | 152,296 | 305,241 | 5,268 | 31,423 | 92,893 | 0% | — |
| 2021 | 164,925 | 363,962 | 5,727 | 26,218 | 134,371 | 0% | — |
| 2022 | 152,786 | 288,000 | 5,491 | 33,977 | 72,920 | 0% | — |
| 2023 | 154,348 | 282,089 | 5,447 | 28,612 | 70,384 | 66.5% | 15.5% |
| 2024 | 152,504 | 298,305 | 5,138 | 22,496 | 92,641 | 100% | 21.1% |
| 2025 | 144,987 | 282,732 | 4,988 | 22,064 | 83,440 | 100% | 22.2% |
| 2026（到 3/31 季度包） | 49,733 | 101,527 | 4,002 | 4,926 | 22,615 | 100% | 16.3% |

**关于卡的否定判据 (4)（"10b5-1 计划交易无法从字段区分且占比 > 50%"）**：
`SUBMISSION.AFF10B5ONE` 这个字段 2023q2 才出现（10b5-1 修订案加的勾选框），
2023q1 及以前**全部是空**（我们存成 null，不存成 false）。2023q2 起字段 100% 可用，
打勾比例 **15%~22%**，远低于 50%。所以判据 (4) 不触发，但**2016-2022 这段没法区分**，
这一点只能靠"卖出信号在这段时间整体不可信"来处理，不能假装有字段。

### 3.2 特征表（top-500 ADV 池，过去 60 个交易日内至少有一笔可见记录的股票日占比）

| 年 | top-1000 行数 | top-500 行数 | 任一申报 | 有公开市场买入 | 有公开市场卖出 | 机会型买入(字面规则) | 机会型买入(CMP 严格) | 例行买入 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2016 | 188,848 | 93,713 | 81.3% | 15.4% | 62.9% | 15.4% | 0.0% | 0.0% |
| 2017 | 206,811 | 103,146 | 82.9% | 14.7% | 68.0% | 14.7% | 0.0% | 0.0% |
| 2018 | 207,196 | 102,334 | 83.2% | 15.9% | 66.1% | 15.9% | 0.2% | 0.0% |
| 2019 | 204,143 | 100,702 | 84.6% | 16.1% | 68.1% | 16.0% | 2.9% | 0.4% |
| 2020 | 201,745 | 98,884 | 84.8% | 15.9% | 67.2% | 15.6% | 2.8% | 0.7% |
| 2021 | 205,954 | 102,116 | 84.0% | 10.7% | 70.6% | 10.4% | 1.3% | 0.4% |
| 2022 | 194,086 | 95,066 | 86.6% | 15.5% | 67.3% | 15.2% | 1.7% | 0.5% |
| 2023 | 197,118 | 96,227 | 88.4% | 13.2% | 68.2% | 13.1% | 1.9% | 0.4% |
| 2024 | 199,398 | 98,044 | 88.4% | 11.5% | 71.0% | 11.4% | 1.8% | 0.3% |
| 2025 | 196,573 | 97,502 | 88.3% | 13.9% | 70.9% | 13.6% | 1.6% | 0.4% |

（上表是尾段补齐**之前**的口径，2026 年单列在 3.3 节。）

**这张表里最重要的一行不是覆盖率，是"机会型（CMP 严格）"那一列只有 1.3%~2.9%。**
卡的设计是"过去 60 日机会型内部人净买入比例高于截面中位数的股票"。如果只有 2% 的股票日
有一笔严格意义上的机会型买入，那"截面中位数"这个切法在 98% 的股票上都是 0，中位数就是 0，
门实际上退化成"有没有机会型买入"这个二值。第 1 步要先确认这一点，再决定是用字面规则
（`opportunistic_buy_60d`，覆盖 11%~16%，但它几乎等于"有没有买入"）还是把窗口拉长。

### 3.3 尾段缺口

季度数据集最新一期是 **2026q1**（sec.gov 上 2026-04-07 发布，含 2026-01-02 至 2026-03-31 的申报）。
`2026q2`、`2026q3` 都是 HTTP 404，也就是**季度包只到 2026-03-31**。

只用季度包的话，缺口是 **2026-04-01 到今天（2026-09-16）**，约 5.5 个月 / 115 个交易日。
特征表因为是 60 个交易日的滚动窗，会从 2026-04-01 起逐渐掉空，到 **2026-06-26** 完全为 0：

| 2026 年月 | 有任一可见申报的股票日占比（补齐前） |
|---|---:|
| 1 月 | 73.0% |
| 2 月 | 78.9% |
| 3 月 | 83.9% |
| 4 月 | 81.4% |
| 5 月 | 67.8% |
| 6 月 | 19.9% |
| 7 月起 | 0% |

**这个缺口已经补上了**，用的是 EDGAR 日更索引：
`https://www.sec.gov/Archives/edgar/daily-index/{yyyy}/QTR{n}/form.{yyyymmdd}.idx`
→ 过滤出 Form 4 / 4-A → 逐份抓完整申报 `.txt` → 从里面抠出 `<ownershipDocument>` XML → 用
和季度包一样的字段结构解析。落到 `data/raw/insider/tail/index/` 和 `data/raw/insider/tail/parsed/`。

两个让这件事从"一天"变成"一个半小时"的取舍，都写在脚本文档里：
1. **一份申报只发一个请求。** 完整申报 `.txt` 里就含 XML，不需要先请求目录 `index.json` 再请求 XML。
2. **默认只抓我们池子里的发行人。** 日更索引会把同一份 Form 4 按每个申报人各列一行（发行人一行 +
   每个申报所有人各一行），所以"只保留 CIK 属于 top-1000 ADV 发行人的行"同时起到了去重和瘦身两个作用：
   2026-04-01 当天索引里 1,741 行 Form 4，过滤后是 315 份唯一申报（100 个我们池子里的代码）。
   想抓全量就 `--tail-universe-top-n 0`。

**今天（2026-09-16）的日更索引还没发布（HTTP 403），所以数据到 2026-09-15 为止。** 这是 EDGAR 的
正常节奏（当日索引在收盘后才出），不是错误。日常增量只要重跑 `--stage tail-index` + `--stage tail-fetch`，
已下载的日子会自动跳过。

## 4. 点时规则（这一节是给审计看的）

- **可见日 = `FILING_DATE` 的下一个美股交易日**，用 `open_composer.market_calendar.next_us_equity_session`。
  周四申报 → 周五可见；周五申报 → 下周一可见；劳动节前的周五申报 → 下周二可见。三种情况都有单测。
- `*_60d` 是**以该行自己的 `trade_date` 结尾、含当日的 60 个交易日**窗口，窗口比的是**可见日**，不是交易日期。
- 行的 `visible_at` = 该 `trade_date` 当日 09:30 美东转 UTC。也就是说这一行的信息集，是"到这一天开盘为止
  已经公开的申报"，信号可以在当天开盘及之后消费。
- `data/features/insider/_build_manifest.json` 记录了口径（窗口长度、可见性规则、单据类型、买卖代码、
  池子大小、as-of 日、占位参数），机器可读。

### 买 / 卖 / 其他

- 买 = `TRANS_CODE == 'P'` 且 `TRANS_ACQUIRED_DISP_CD == 'A'`
- 卖 = `TRANS_CODE == 'S'` 且 `TRANS_ACQUIRED_DISP_CD == 'D'`
- 其他 = `TRANS_CODE in {M, A, F}`（期权行使 / 授予 / 代扣税），单独进 `other_count_60d`，
  **绝不混进买或卖**。这三个码是薪酬机制产生的，不是对价格的判断。
- 只用 Form 4 / 4-A。Form 3 是初始持仓声明，Form 5 是年度补报，都不是"申报当天的公开市场判断"。

### 联名申报

一份 Form 4 可以由多个申报所有人共同提交，SEC 的表会把同一笔交易按所有人重复一遍（**17.4% 的行**
属于这种）。所以：
- 股数 / 金额 / 笔数只用 `owner_seq == 0` 的行，不会重复计数；
- `buyers_60d` / `sellers_60d` 数的是不同的 `reporting_owner_cik`，联名的每个人各算一个人。

这两条在单测里各有一个用例。

## 5. 机会型 / 例行的确切规则（卡要求写清楚）

对一笔公开市场买入 `e`：申报所有人 `o`，发行人 `i`，`TRANS_DATE` 落在 `y` 年 `m` 月，首次可见于交易日索引 `v`。

> **例行（routine）**：对 `k = 1, 2, 3` 都成立 —— `(o, i)` 这一对在 `y-k` 年的 `m` 月有过至少一笔
> 公开市场交易（代码 `P` 或 `S`），而且那笔交易所在的申报在 `v` 当天或更早就已经可见。
>
> **机会型（opportunistic）**：不是例行。

这就是卡里"是否在往年同月重复交易"的字面实现，对应特征列 `opportunistic_buy_60d`。
三个刻意的取舍：

1. **分类只在这笔买入自己的可见日 `v` 上算一次**，不在后面每个特征日重算。用比 `t` 时刻更少的信息，
   只会让标签更保守，不会泄露未来。
2. **往年历史只认 `P` 和 `S`。** 如果把授予 / 归属 / 代扣税（`A`/`F`/`M`）也算历史，几乎每个高管都会
   变成"例行"——那些事件本来就是每年合同规定的时间发生的。CMP 用的也是公开市场交易。
3. **历史按 `(所有人, 发行人)` 这一对算，不是只按所有人。** 否则一个在很多家公司都申报的 10% 股东或基金，
   会因为同月在 B 公司交易过，就在 A 公司被判成例行。

### 一个必须说清楚的偏差

Cohen-Malloy-Pomorski 原文对**两边**都要求三年记录：例行 = 连续三年同月都有交易；机会型 = **有**
连续三年交易记录但不是同月。没有三年记录的人，他们不归类。而卡的字面规则（"没有在往年同月重复交易"）
会把"没有三年记录"的人全扫进机会型。在我们的样本里这个差别是决定性的：

| 口径 | 占公开市场买入的比例 |
|---|---:|
| 例行（三年同月都有） | 10.3% |
| CMP 意义上的机会型（有三年记录、但不是同月） | 11.5% |
| 无法归类（没有三年记录） | 78.2% |

所以特征表**两种切法都出**，第 1 步不用重建表就能比：
- `opportunistic_buy_60d` = 非例行（字面规则）= `cmp_opportunistic_buy_60d` + `cmp_unclassified_buy_60d`
- `routine_buy_60d` + `opportunistic_buy_60d` = `open_market_buy_count_60d`（恒等式，可校验）

“无法归类”占 78% 有两个原因，都不是 bug：一是绝大多数内部人一辈子只做一两笔公开市场买入；
二是我们自己的档案从 2016 才开始，2016-2018 这三年结构上不可能有三年历史（表里 2016/2017 的
CMP 严格列就是 0.0%）。**CMP 严格口径实际可用的起点是 2019。**

## 6. 特征列清单

`data/features/insider/{年}.parquet`，键 `symbol` + `trade_date`（和仓库里其它因子库同一个形状）：

| 列 | 含义 |
|---|---|
| `net_buy_shares_60d` | 60 日内买入股数 − 卖出股数（float64） |
| `net_buy_usd_60d` | 同上，按每笔申报价格计的金额（float64） |
| `buyers_60d` / `sellers_60d` | 60 日内有买 / 有卖的不同申报所有人个数 |
| `net_buyers_60d` | `buyers_60d − sellers_60d` |
| `open_market_buy_count_60d` / `open_market_sell_count_60d` | `P` / `S` 的笔数 |
| `other_count_60d` | `M`/`A`/`F` 的笔数（期权行使、授予、代扣税） |
| `opportunistic_buy_60d` / `routine_buy_60d` | 第 5 节的字面规则切分 |
| `cmp_opportunistic_buy_60d` / `cmp_unclassified_buy_60d` | CMP 严格切分 |
| `days_since_last_visible_buy` | 距最近一笔可见公开市场买入的交易日数（**全历史**，不限 60 日窗；从未有过则为空） |
| `visible_at` | 该行自己的开盘时刻（UTC），元数据不是因子 |

列名的唯一来源是 `open_composer/research/features/insider.py` 的 `INSIDER_COLUMNS`，
构建器和因子集注册表都从那里读，不会各写一份而漂移。

## 7. 数据质量意外

1. **未来日期的交易。** 415 行（占 0.0115%）的 `TRANS_DATE` 晚于 `FILING_DATE`，最极端的早了
   10,945 天（约 30 年，明显是年份填错）。这些是申报人填表错误。因为我们的窗口只看**可见日**，
   这些行不会造成任何前视；但如果以后有人拿 `TRANS_DATE` 做特征，必须先对着申报日裁剪。
2. **申报延迟的分布是长尾的。** `FILING_DATE − TRANS_DATE` 中位数 2 天（Section 16 要求 2 个工作日内），
   p95 是 8 天，**p99 是 204 天**，最长 10,950 天。也就是说 1% 的申报晚了超过半年。
   这正是"按申报日而不是交易日算可见"的现实理由，不是理论洁癖。
3. **5,623 行没有发行人代码。** `ISSUERTRADINGSYMBOL` 是发行人自己填的自由文本，非上市类别、
   退市后补报等情况会是空。这些行在特征构建时因为 join 不到池子而自然被丢掉，但也说明
   **不能把这个字段当永久证券标识**，所以 `issuer_cik` 一直留着，以后做 PIT 代码映射用。
4. **10b5-1 字段是 2023q2 才有的**（见 3.1 节）。存成三态：True / False / null，**空值绝不当 False**。
   单测里有一条专门钉这个，包括"整列缺失时必须全 null"。
5. **卖出远多于买入。** 公开市场卖出笔数常年是买入的 2~4 倍（2021 年最极端，134,371 : 26,218）。
   Form 4 的"卖"绝大部分是薪酬变现，信息含量本来就低——这也是卡把假设建在"买"上的原因。
6. **`data/features/universe` 的月中单行 cohort 在本轮期间被另一个执行者修掉了。**
   本次特征表用的是修好的版本（128 个月，最小 cohort 754 个代码）。修之前建出来的表，
   2017 年行数是 184,310；修之后是 206,811。如果有人拿更早的中间产物对比，差异来自这里，不是本管道。

## 8. 占位（placebo）

卡要求"第一版就带申报日随机平移"。已实现：

```
./scripts/run_capped.sh --mem 1.8G -- \
    uv run python scripts/build_insider_features.py --shift-filing-dates-days 30
```

- 平移单位是**交易日**（不是自然日），量是 `{-30..-1} ∪ {1..30}` 里的均匀随机整数。
- **按申报号抽一次，不是按行抽**，所以同一份申报的所有行一起移动，联名申报也保持一致。
- 种子固定（`--placebo-seed`，默认 20260916），可复现。
- 输出写到**另一个目录** `data/features/insider_placebo_shift30_seed20260916/`，
  不可能和真表混起来。
- 语义：如果门的效应在平移后还在，说明抓到的是市值 / 行业 / 流动性的代理，不是内部人信息。

按 L-20260916-03 那条教训（元标签那轮），占位**至少要 5 个种子、报分布不报单值**。
这里给不同 `--placebo-seed` 就是 5 个种子，第 2 步跑孪生单元时按那个规矩做。

## 9. 筛选器怎么接（第 1 步的交接）

### 已经做好的

1. `data/features/insider/{年}.parquet` 的形状（`symbol`, `trade_date`, 若干 float 列）**和
   `scripts/screen_factors.py` 的 `_load_library_year` 期望的完全一致**，不需要新代码路径。
2. 因子集注册表里加了 `insider`：
   `resolve_feature_set("insider")` → 13 列 + `data/features/insider` 根目录，
   可以直接传给 `panel.load_feature_panel(..., extra_feature_roots=roots)`。
3. 宽表 `data/features/insider/screening_panel_weekly.parquet`：键 `(friday_date, symbol)`
   （同时带一个同值的 `trade_date` 列，方便按仓库惯例 join），周频 = `loop.weekly_rebalance_dates`
   的 ISO 周最后一个交易日，池子 = 该月 top-500 ADV。

### 故意没做的，以及为什么

**没有把 `insider` 塞进 `scripts/screen_factors.py` 的 `LIBRARIES`。** 那个脚本的模块 docstring
本身就是第 13-F 3.5 节的**预登记**（"先写进本节再跑，不许事后改"），里面写死了
"253 个因子 × 2 个标签 = 506 次检验"这个多重检验计数。往同一次运行里加 13 个内部人因子，
会把一个已经跑完的 FDR 预登记的计数改掉，这是不能做的。

内部人因子的筛选应该是**本卡自己的一次预登记**（一级数据层，和价量库不是一个假设族）。
需要的改动只有两行，留给第 1 步在新的预登记下做：

```python
# scripts/screen_factors.py 或它的一份内部人专用副本
LIBRARIES = ("insider",)          # 本卡自己的预登记，不与 13-F 3.5 的 506 次检验混算
UNIVERSE_TOP_N = 500              # 卡的口径是 top-500，不是 3.5 节的 1500
```

join 的细节（如果第 1 步要自己写）：

- 键：`(symbol, trade_date)`，`trade_date` 是 `loop.weekly_rebalance_dates(calendar)` 的周五。
- 标签：`data/features/labels/{年}.parquet` 的 `label_excess_5` / `label_excess_10`，同键。
- 池子：`loop.universe_as_of_calendar_month(universe_panel, date, top_n=500)`。
- 缺失语义：**这张表没有"缺失"概念**——池子里的每个股票日都有行，没有申报就是 0（
  `days_since_last_visible_buy` 例外，从未有过买入是 null）。所以 IC 计算不要把 0 当缺失丢掉，
  否则样本会从 9.8 万行掉到 1.4 万行，而且是被"有内部人交易"这件事选出来的子样本。
- 建议先看的三个列：`net_buyers_60d`（人数净差，最不受单笔大小影响）、
  `net_buy_usd_60d`（金额，需要截面标准化）、`days_since_last_visible_buy`（时效）。

## 10. 现在能回答卡的哪些判据

| 判据 | 现在的状态 |
|---|---|
| (4) 10b5-1 无法区分且占比 > 50% | **不触发**。2023q2 起字段 100% 可用，打勾比例 15%~22%。但 2016-2022 完全没有字段。 |
| (3) 筛选器 recent 窗 \|t\| < 2 且符号稳定性 < 0.7 | 还没跑，第 1 步的事。数据和输入都已就位。 |
| (1) 同波动超额改善 < 3 个百分点 | 第 2 步（孪生单元）。 |
| (2) 占位平移后效应仍在 | 占位工具已实现，等第 2 步用。 |
| (5) 门每年切换 < 4 次 | 第 2 步。 |

## 11. 还没做 / 已知限制

1. **按发行人 CIK 做 PIT 代码映射**没做。现在直接用 `ISSUERTRADINGSYMBOL` 对齐池子里的代码。
   改名、退市、同代码复用会错配。`issuer_cik` 已经保留，需要的时候可以补一层映射。
2. **`NONDERIV_HOLDING` 默认不解析**（`--with-holdings` 可开）。做"净买入 / 流通股"这类
   归一化时会需要它或别的流通股来源，本轮的特征都是绝对量和人数。
3. **衍生品交易（`DERIV_TRANS`）完全没用。** 期权和限制性股票的申报在那张表里。本卡只看非衍生品。
4. **金额缺价格的比例 1.0%**：`TRANS_PRICEPERSHARE` 为空或 0 的公开市场买入占 1.0%，
   这些行对 `net_buy_usd_60d` 的贡献记为 0（股数照算）。没有用别的价格源回填。
5. **每日增量还没做成定时任务。** 现在是手动重跑两个 tail 阶段。

---

附：可复现的命令

```bash
# 季度包（下载 + 解析，已下载的自动跳过）
nohup ./scripts/run_capped.sh --mem 1.8G -- \
    uv run python scripts/collect_sec_insider_transactions.py --stage quarterly --start 2016q1 \
    > /tmp/insider_quarterly.log 2>&1 &

# 尾段（日更索引 → 逐份 Form 4 XML）
nohup ./scripts/run_capped.sh --mem 1.8G -- \
    uv run python scripts/collect_sec_insider_transactions.py --stage tail-index \
    > /tmp/insider_tail_index.log 2>&1 &
nohup ./scripts/run_capped.sh --mem 1.8G -- \
    uv run python scripts/collect_sec_insider_transactions.py --stage tail-fetch \
    > /tmp/insider_tail_fetch.log 2>&1 &

# 点时特征 + 周频筛选面板
nohup ./scripts/run_capped.sh --mem 1.8G -- \
    uv run python scripts/build_insider_features.py --force \
    > /tmp/insider_features.log 2>&1 &

# 占位
nohup ./scripts/run_capped.sh --mem 1.8G -- \
    uv run python scripts/build_insider_features.py --shift-filing-dates-days 30 \
    > /tmp/insider_features_placebo.log 2>&1 &

# 能力评估
uv run oc capability test
```
