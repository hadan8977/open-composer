# H-20260916-02 新闻注意力特征：逐列的确切规则（第 1 阶段，不用 LLM）

这一页是给审阅用的：`data/features/news_attention/{year}.parquet` 每一列到底怎么算的，不用读代码。
机器可读版本是 `data/features/news_attention/_build_manifest.json`；
唯一的实现是 `scripts/build_news_attention_features.py`（它的模块 docstring 就是规范本身）
和 `open_composer/research/features/news_attention.py`（列清单 + 纯文本函数，有测试）。

- 输入：`data/features/news_packets/{2024,2025,2026}.parquet`，684,876 条 Alpaca / Benzinga 文章。
- 输出：一行 = 一个（交易日 `trade_date`，股票 `symbol`），股票池 = **当月点时 top-1000 ADV**
  （`loop.universe_as_of_calendar_month(top_n=1000)`，实际每日约 780 只）。
- **没有任何 LLM 调用。** 关键词是一张固定正则表，新颖度是词 3-gram Jaccard。

## 1. 点时可见性（本族唯一的可见性规则）

一篇文章归属到**第一个「09:30 ET 开盘时刻 ≥ 它的 `visible_at`」的美股交易日**。

- 2024-03-05 14:12 ET 可见 → 落在 **2024-03-06**。
- 2024-03-06 09:29:59 ET 可见 → 落在 **2024-03-06**。
- 2024-03-06 09:30:01 ET 可见 → 落在 **2024-03-07**。

所以 `D` 这一行只数「`D` 的集合竞价开始时就已经公开」的文章，一个在 `D` 开盘下单的策略可以读 `D` 这一行。
`created_at` / `updated_at`（发布方自己的记账；档案文件是按 `updated_at` 分年的，
所以 `2024.parquet` 里会躺着 2011 年的文章）和 `fetched_at`（我们自己的抓取时间，全部是 2026-09-09）
**从不**当可见时间用。

## 2. 窗口约定

`*_5d` / `*_20d` / `*_60d` = 以该行自己的 `trade_date` **结尾且含本日**的连续 5 / 20 / 60 个美股交易日，
窗口跑在「归属日」上，不是发布时间戳上。
`news_count_1d` = 该行自己那一个交易日，也就是「上一个开盘到这个开盘之间公开的全部」。

## 3. 多股票文章

一篇文章归属到它列出的**每一只**股票（NVDA + AMD 的联合报道对两只都算新闻）。

- 列了 **> 10 只**股票的文章**整篇丢掉**（13,289 篇）：那是「周二盘中异动 12 股」这类全市场汇总，
  不是个股新闻；截到前 10 只会凭空造出一个文章本身没有的排序。
- 一只都没列的（21,137 篇）同样丢掉。
- 归属之后，在点时 top-1000 池里至少命中一只的文章 **339,885 篇**，
  展开成 **460,652** 个 (文章, 股票) 行。落在 as-of 之后的 162 篇、落在热身窗之前的 90 篇也丢掉。

## 4. 逐列定义

记 `A(S, w)` = 归属到股票 `S`、落在以 `D` 结尾的 `w` 个交易日窗口里的文章。

| 列 | 定义 |
|---|---|
| `news_count_1d` / `news_count_5d` / `news_count_20d` | `|A(S,1)|`、`|A(S,5)|`、`|A(S,20)|` |
| `attention_surge_5d` | `news_count_5d / max(news_count_60d / blocks, 1)`，其中 `blocks = max(news_history_sessions, 5) / 5` |
| `distinct_sources_5d` | `A(S,5)` 里 `source` 的不同取值数。**本档案里是常数**（见第 5 节） |
| `distinct_authors_5d` | `A(S,5)` 里 `author` 的不同取值数（全档案 509 个作者） |
| `novelty_5d` | `1 − mean over a in A(S,5) of maxoverlap(a)`，见下 |
| `kw_<组>_5d` | `A(S,5)` 里**标题**命中该关键词组的文章数 |
| `days_since_last_news` | 距最近一个「有文章」的交易日多少个交易日（当天有新闻 = 0），算在整个档案历史上，不只 60 日窗；档案里从没有过该股文章则为 null |

元数据列（不当因子）：`visible_at`（该交易日 09:30 ET 的 UTC 时刻）、`news_count_60d`、
`news_baseline_5d`（突增的分母）、`novelty_basis_5d`（进了新颖度均值的去重标题数）、
`news_history_sessions`（该行 60 日窗里档案真正覆盖的交易日数）。

### 4.1 `attention_surge_5d` 的分母

分母 = 60 个交易日的总条数 ÷ **档案真正覆盖的** 5 日块数（下限 1 块），再和 1 取大。

- 为什么不是固定除以 12 块：新闻档案 2024-01-01 才开始，固定除以 12 会让 2024 年初每一行都显示出
  一个纯粹由档案起点造出来的假突增。
- 分母**包含当前这 5 天自己**。这让这个度量偏保守（一次爆发必须先跑赢自己对基线的贡献；
  满历史下的理论上限是 12），并且避开了「跳过最近 5 天」这种任意选择带来的不连续。
- `max(..., 1)` 的下限是卡上自己的：没有它，一只 60 天没新闻、今天来一条的股票会得到无穷大的突增。

### 4.2 `novelty_5d` 的确切算法

1. 对 `A(S,5)` 里的每篇文章 `a`：把标题小写、去标点、压空格，切成**词级 3-gram**
   （少于 3 个词的标题退化成词集合，否则两词标题会被算成「完全新颖」）。
2. `maxoverlap(a)` = `a` 的 3-gram 集合与**该股票**在 `a` 自己那个交易日**之前严格 20 个交易日内**
   的所有**不同**标题的 3-gram 集合之间，Jaccard 相似度的最大值。没有更早的标题则为 0（第一次出现无从重复）。
3. **完全重复的标题按「同一交易日内」去重**：一条通稿同一天出现三次只贡献一项。
   跨日重复**不**去重——同一个标题一周后再出现是真正的重复，必须对着更早的自己打出 ~1.0，
   那正是这个特征存在的意义。
4. `novelty_5d = 1 − mean(maxoverlap)`；`A(S,5)` 为空时是 **null**（没人写过东西时新颖度是未定义，
   不是 1.0）。

**披露的一处读法选择**：「过去 20 日」按**每条标题自己**往前数 20 个交易日，
不是按行的 `D` 往前数（即不是「5 日窗之前的 20 个交易日」）。两种读法都符合卡上的措辞；
按标题算只需要每篇文章算一次而不是每个 (文章, D) 对算一次，而且它是拿每条标题和
「它出现时读者其实已经看过的东西」比。另一种读法已登记为 `news_attention_features` 族的未用变体。

### 4.3 关键词词典（固定，非 LLM，只匹配标题）

只匹配**标题**不匹配摘要：本档案的摘要里有免责声明和 "Benzinga Insights" 模板段落，
会让这些词在根本不是讲这件事的文章上误触发；而标题是人扫一眼信息流时真正读到的部分。
每组是一个整词边界的正则选择：

| 组 | 模式 |
|---|---|
| `earnings` | `earnings`, `eps`, `quarterly results`, `q1 results`, `q2 results` |
| `guidance` | `guidance`, `outlook`, `forecasts?`, `reaffirms` |
| `acquisition` | `acquisitions?`, `acquires?`, `acquired`, `takeover`, `to buy` |
| `merger` | `mergers?`, `merges?`, `merging`, `combine with` |
| `lawsuit` | `lawsuits?`, `sues`, `sued`, `litigation`, `class action`, `settlement` |
| `fda` | `fda`, `clinical trial`, `phase [123]`, `phase i{1,3}` |
| `downgrade` | `downgrades?`, `downgraded`, `cuts price target`, `lowers price target` |
| `upgrade` | `upgrades?`, `upgraded`, `raises price target`, `boosts price target` |
| `ceo` | `ceo`, `chief executive` |

一篇文章可以同时命中几组。

## 5. 已知的档案限制（必须跟着这张表走）

1. **只有一个来源。** 684,876 条全部 `source == "benzinga"`，所以 `distinct_sources_5d` 在有新闻时是 1、
   没新闻时是 0，没有任何横截面信息。它照卡的要求照样产出，但**排除在筛选器的 BH 分母之外**
   （`SCREEN_EXCLUDED_COLUMNS`），并用 `distinct_authors_5d` 当替身。
2. **覆盖 2024-01-01 才开始**（更早只有 45 条）。所以 2024 年前 60 个交易日的基线是截断的，
   分母按实际可用块数除（见 4.1），每行的可用长度写在 `news_history_sessions` 里。
3. **`news_history_sessions` 的起点偏早**：它从「档案里第一条被归属的新闻」那天算，
   也就是 2023-10-30（25 条被 `updated_at` 分区拖进来的旧文重发），而不是 2024-01-01。
   后果是 2024 年 1 月的行被当成有约 40 个交易日的历史，分母偏大、突增偏小——
   **偏保守的方向**，不会造出假突增。
4. **`days_since_last_news` 被档案起点托底**：一个 2024-01 的值 12，可能是「12 个交易日没新闻」，
   也可能是「这只票从来没被收集到过」。

## 6. 符号占位（卡要求的那个）

`--shuffle-symbols-seed N --shuffle-symbols-mode relabel`：抽一个**全样本固定双射** π，
把每篇文章里的每只股票换成 π(股票)。每个伪代码因此继承某只真实股票的**整条**新闻历史
（条数、重尾、周与周之间的持续性、关键词构成都一模一样），被破坏的只有
「新闻序列 ↔ 收益序列」这一个配对。输出写到单独的根目录
`data/features/news_attention_placebo_relabel_seed{N}/`，真实表永不被覆盖。

另一个模式 `draw`（逐篇从当日点时池里均匀抽同样多的票，也就是卡上的字面写法）
**被量化否掉了**，理由和数字见 `placebo-mode-comparison.json`：它把重尾压平了
（2024 年 5 日内有报道 69.2% → 97.4%，`news_count_5d` 标准差/均值 2.18 → 0.52，
「20 日无报道」那一档 6.1% → 0.8%），所以不是同尺寸对照。
CLI 里保留它，只为了让这个比较可复现。

两种模式都保留日历，所以真正按构造同尺寸的对照是周内打乱门的标签
（`kernel/news_gate.shuffle_states_within_date`），判决落在它上面。

## 7. 复现

```bash
./scripts/run_capped.sh --mem 1.8G -- \
    uv run python scripts/build_news_attention_features.py all          # 真实表，约 2 分钟
./scripts/run_capped.sh --mem 1.8G -- \
    uv run python scripts/screen_news_attention_factors.py              # 48 次预登记检验
./scripts/run_capped.sh --mem 1.8G -- \
    uv run python scripts/run_h20260916_02_news_attention.py export     # M0B 持仓导出
./scripts/run_capped.sh --mem 1.8G -- \
    uv run python scripts/run_h20260916_02_news_attention.py precheck   # 前置检查交叉表（先出这个）
for seed in 20260916 20260917 20260918 20260919 20260920; do            # 占位特征表
    ./scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/build_news_attention_features.py all \
        --shuffle-symbols-seed "$seed" --shuffle-symbols-mode relabel
done
./scripts/run_capped.sh --mem 1.8G -- \
    uv run python scripts/run_h20260916_02_news_attention.py gate-states
./scripts/run_capped.sh --mem 1.8G -- \
    uv run python scripts/run_h20260916_02_news_attention.py evaluate   # 定价 + 出报告
```

每一步都有检查点，中断可续；`--force` 才会重算。
