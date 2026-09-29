# New tasks from gap-search-2026-09-29-01

Coordinator: merge these two blocks into `reports/research/control/autonomous-queue.md`
(do not edit that file directly from this task). Format matches
`docs/runbook-autonomous-round.zh.md` section 9.

### T-20260929-01 批量筛选：杠杆 ETF 收盘再平衡流引发的次日均值回归（SPY/QQQ/SMH，只做多）
- status: ready
- priority: 2
- not_before:
- goal: 缺口搜索（`gap-search-2026-09-29-01`）覆盖地图 `flows_structural.rebalance_and_hedging_flows` 格子明确标记"LETF close-rebalancing flow ... 从未搜索"。机制：2x/3x 杠杆和反向 ETF 每天收盘前必须再平衡以维持目标杠杆比例，标的当日出现大幅波动时会产生方向已知、规模可估的收盘买卖盘，文献认为这会造成尾盘动量和次日均值回归。这是纯收盘价规则（不需要期权、AUM 或流量数据），只需要已在本地面板里的 SPY/QQQ/SMH 及其杠杆对，是这个格子最便宜能测的候选。
- plan: |
    新建迭代 `h20260929_01_letf_flow_reversal`，候选模块 `scripts/screen_batches/h20260929_01_letf_flow_reversal.py`（纯函数 `weights_fn(close, asof) -> weights`，只读 `close.loc[:asof]`，照抄 `h20260928_42_opex_week.py`/`h20260928_18_vix_putw.py` 的写法），候选清单 `reports/research/iterations/h20260929_01_letf_flow_reversal/candidate-manifest.json`，`direction-review.json` 引用 `dir:letf_close_rebalancing_flow_reversal`。

    来源与规则要点（已打开原文，非只读摘要）：
    - Lenkey (2024)，"The market impact of leveraged ETFs: A Survey of the literature"，Quantitative Finance and Economics（开放获取，http://www.aimspress.com/article/doi/10.3934/QFE.2024031，已用 WebFetch 读全文）：文献"一致报告 ETF 再平衡需求与尾盘收益/波动率之间存在统计显著的关联"，但"现有大多数论文存在潜在的严重方法论错误，经济意义上的关联看起来并不显著"；总体结论是"政策制定者等提出的担忧没有得到整体经验证据的支持"。机制是机械性的（不是行为偏差），所以理论上不该像日历效应一样被套利消失；但来源本身认为经济幅度小——这是一个"值得测但预期偏弱"的候选，不是强先验。同一次搜索找到的其他论文（Ivanov & Lenkey、SFI working paper、一篇 2021 FMA PDF、一篇 2016 REPEC 条目）未能打开全文（PDF 读取失败/付费墙），不作为独立引用来源，只在 direction 的 notes 里提及。

    **只做股票/指数类杠杆 ETF，不做跨资产**：标的限定 SPY、QQQ、SMH（未加杠杆）及其对应 3x 产品 UPRO/SPXU、TQQQ/SQQQ、SOXL/SOXS（均已确认在本地面板 `data/sip/daily/_LAYOUT.json`，分片 0278/0243/0275/0305/0278/0296/0278/0275/0275）。**明确排除** TMF/TMV（债券杠杆）和 UVXY/SVXY（波动率产品），避免触碰机主否决的跨资产边界。

    规则：某标的（SPY/QQQ/SMH）在收盘时，若"今日收盘价相对昨日收盘的涨跌幅"（或其对应 3x 产品当日涨跌幅，作为再平衡流规模的更直接代理）的绝对值 >= 阈值，则次日开盘买入该标的、持有 N 个交易日，否则持有现金。
    网格：3 个标的 x 2 种信号来源（自身收益 vs 3x 对应产品收益）x 3 个阈值 {1.5%, 2%, 3%}（文献中常用的"大幅波动日"分界）x 2 个持有期 {1, 3 个交易日} = 36 个候选，若检查后自身/3x代理两种信号高度重合可预注册收窄到 <=18 个（在 candidate-manifest.json 里写清楚精简理由，精简须在跑批之前做，不能看结果后再删）。**必须加安慰剂对照**：同样触发频率下随机选择交易日持有的对照版本（不是真的大幅波动日），检验"大幅波动日"本身是否比随机进场更好（冻结合同 G3 之外的内部否证，因为"大幅波动"是有数据挖掘风险的阈值选择）。

    `uv run oc research direction-check <path>` 和 `uv run oc research iteration validate h20260929_01_letf_flow_reversal --stage pre-backtest` 通过后跑 `uv run python scripts/screen_batch.py --batch h20260929_01_letf_flow_reversal --iteration h20260929_01_letf_flow_reversal`（全部标的已在本地面板，无需取数）。判定：K1 为主路径（偏移中位数夏普对标窗 >=1.19、压力期 >=0.65，20bp 下两窗年化为正）；K2 为备选（和 S3 组合增量 >=0.05，两窗都成立）；候选族（不含安慰剂对照）报告 DSR。`--stage final` 通过后更新登记簿 `dir:letf_close_rebalancing_flow_reversal` 和覆盖地图 `flows_structural.rebalance_and_hedging_flows`。
- done_when: 迭代 `--stage final` 通过；每个候选（含安慰剂对照结果）都有 K1/K2 判定和 DSR；`dir:letf_close_rebalancing_flow_reversal` 从 queued 更新为终态并带 verdict、evidence、reopen_if。
- notes:
  - 2026-09-29 gap search (`gap-search-2026-09-29-01`) 添加。

### T-20260929-02 节前效应在小盘/低流动性股票层面的复现（signal_card 事件模式，不需要新数据）
- status: ready
- priority: 2
- not_before:
- goal: 缺口搜索覆盖地图 `flows_structural.calendar_and_fomc` 格子表面写"harvested, not tested"，但逐条查过登记簿后发现月末反转、板块季节性、pre-FOMC drift、turn-of-month 都已经测过并有结论（不要重复）。本任务找到一个该格子确实没测过的子方向：Ariel (1990) 的经典"节前溢价"效应，被后续复现研究发现在样本外（1983-2019）"只在小盘股里还存在，大盘股的溢价已基本消失"。机主 2026-09-28 明确说小盘/低流动性股票可以做（按价差建成本），这个候选正好落在这个偏好里，且能直接复用已有的股票层面信号评估工具（`open_composer/research/signal_card.py` 的 event 模式），不需要新数据管线。
- plan: |
    来源与规则要点（已打开摘要，非只读搜索片段）：
    - "The Pre-Holiday Premium of Ariel (1990) Has Largely Become A Small-Firm Effect Out of Sample"（https://exa.ai/library/publication/k47n5zm6fft，同一篇也见 https://www.nowpublishers.com/article/Details/CFR-0111，已用 WebFetch 读摘要）：Ariel (1990) 发现节前交易日的市场指数收益是平常的"9 到 14 倍"；本复现把样本延长到 1983-2019，发现节前溢价"现在只在小盘股中存在"，大盘股的溢价"已基本消失，尤其是 1990 年后"。只读到摘要（全文在付费墙/Exa API 后面），没有具体的 bps/百分比数字或显著性水平，判定只能用方向性结论，不能用具体数字做预注册目标。另有一篇 2026 年新论文（Apergis, "Abnormal returns and stock performance prior and after federal holidays", Review of Financial Economics）搜到但 WebFetch 返回 403，没有读到内容，不作为证据引用，只在 direction 的 notes 里标注避免下次盲目重试同一个付费墙。

    工具：直接用 `open_composer/research/signal_card.py` 的 `--mode event`（已内置 t1 1-500 / t2 501-1500 / t3 1501-top_n 三档按美元 ADV 分层、10bp/20bp 成本、`redate_events` 内置安慰剂——把每个事件在同一只股票上随机移动 ±126 个交易日，满足冻结合同 G3 式的内部否证要求，不需要额外写代码）。

    信号构造：事件日期 = 每个联邦市场假日休市前 2 个交易日（这样次日开盘买入正好落在假日前一个交易日，持有 h 个交易日捕捉"节前效应"文献衡量的那一段）。假日日期**不引入新数据源**：直接从已有收盘面板自身的交易日历推导（"哪些交易日之后出现了一个不能用周末解释的多日缺口"），和 `scripts/screen_batches/h20260928_42_opex_week.py` 处理"第三个星期五"日历锚点用的是同一套"已知交易日历，不是价格穿越"的约定（该脚本的 docstring 有详细说明，照抄它的日历推导方式）。构造一张 `symbol, trade_date, value=1` 的表：对 universe_broad 里每只股票，在每个符合条件的 formation date 上都置 1（同一天所有股票拿到同样的事件——这是市场层面的日历事件，不是个股特征，signal_card 的 event 模式天然支持"同一天很多只股票同时触发"）。

    两次独立跑（或一次跑两个 `--sql`/`--where` 变体）：`pre_holiday_t1`（限定 t1 tier 股票，机制预期里"已消失"的对照组）和 `pre_holiday_t3`（限定 t3 tier 股票，机制预期里"仍然存在"的目标组），`--primary-horizon 5`。用 `run_capped.sh --mem 1.8G --` 跑（signal_card 会读整张 universe_broad 面板）。

    判定（signal_card 自带的"信号是否被采纳"标准，不是策略级 K1/K2——按其 docstring，单个信号不适用策略门槛）：读 `card["flags"]` 的四项 `car_t_ge_3`、`beats_redated`（内置安慰剂）、`book_positive_20bp`、`book_positive_20bp_recent`。t3 全部为真且 t1 不全为真才算"信号采纳，和来源的小盘专属结论一致"；否则按对应结论否定或标记证据不足。
- done_when: `pre_holiday_t1` 和 `pre_holiday_t3` 两张 signal card 都生成在 `reports/research/signal-cards/`；`dir:pre_holiday_effect_small_cap_tier` 从 queued 更新为终态（admitted/refuted/evidence_too_weak）并带 verdict、evidence（signal card 路径）、reopen_if；结论要写清楚 t1 与 t3 是否复现了来源的"只在小盘股"模式。
- notes:
  - 2026-09-29 gap search (`gap-search-2026-09-29-01`) 添加。
