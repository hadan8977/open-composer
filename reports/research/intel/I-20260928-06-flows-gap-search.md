# I-20260928-06：flows/relative-value/public-records 缺口搜索——给自动轮补队列任务

任务来源：缺口搜索指令（`found_by: gap-search-2026-09-28-22`），目的是补 2-4 个下一轮就能跑的批量测试任务（队列当时 `ready` 的任务不足 3 个：只有 T-20260927-03、T-20260927-05、T-20260928-19 三个杂项任务，主力批量任务 T-20260928-40/41/22/16/17 全在 `running`/`blocked`）。范围限定：`docs/runbook-autonomous-round.zh.md` 第 0/4/5/9 节的边界和格式；只调研登记+写队列，不跑任何回测/训练/Modal。

## 起点：覆盖地图指定的四个格子

`reports/research/harvest/coverage.json` 里指定的四个格子：
- `flows_structural.rebalance_and_hedging_flows`：`gap` 字段原文"options-expiration and LETF-rebalance effects on constituents never searched"。
- `relative_value.pairs_stat_arb`：`gap` 字段原文"never tested; the short leg needs an owner permission, the long-only leg (buy the cheap side) was never isolated"。
- `public_records.copy_verified_live`：`gap` 字段是 Collective2/Kinfo 两个站点被封锁/没有可复制规则的死路（`I-20260924-02`）。
- `flows_structural.calendar_and_fomc`：月末反转、板块季节性领跑已测过并在 `watch_recent` 前向跟踪（H-20260928-20），按指令不重复。

## 搜索记录（6 次，全部 `channel web`，`reports/research/harvest/search-log.jsonl` 自动记录）

1. `search:20260928:web:leveraged_etf_end_of_eef1c5`——"leveraged ETF end of day rebalancing flow return predictability 2024 replication"。找到的最相关来源（EFMA 2023 working paper PDF、SSRN 流动性供给论文）都是关于杠杆 ETF 再平衡流对**期权市场**流动性/做市商库存的影响，不是可直接转成"只做多 weights_fn"规则的股票方向性效应；且都读不到具体近期股票收益数字。判定：证据不够具体，不开队列任务，仅留作以后参考（未写入 directions.jsonl）。
2. `search:20260928:web:russell_index_reconstitution_trade_c1c4c6`——"Russell index reconstitution trade returns 2023 2024 2025 replication"。搜到的都是 LSEG/CME/Callan 的机制说明文档，WebFetch 尝试打开 LSEG 官方 PDF（`https://www.lseg.com/content/dam/ftse-russell/en_us/documents/other/russell-indexes-impacts-of-reconstitution-2025.pdf`）失败（二进制/压缩流，读不出文本）。而且 Russell 重构效应本质上和已判定 `evidence_too_weak` 的 `dir:index_addition_deletion_effect`（Greenwood & Sammon："graduation" 纳入效应已消失）是同一族现象的年度子集，重开条件是"某个具体细分（如中小盘指数变更）在 2023 年后仍有效应"的证据——本次没找到这样的证据，且重构交易需要额外的成分股变更事件日历数据（不在现有 SIP 收盘价面板里），不是纯函数能低成本测的。**放弃，不开任务。**
3. `search:20260928:web:option_expiration_week_equity_87284d`——"option expiration week equity returns anomaly post-publication decay"。命中 Quantpedia "Option-Expiration Week Effect"（相关性评分 0.593，最高），WebFetch 全文打开确认规则细节（见下）。另找到 Garcia-Ares & Muravyev 2025（FMA 2025 working paper）和其摘要博客 harbourfronts.com，均已 WebFetch 打开全文。**采纳，开 T-20260928-42。**
4. `search:20260928:web:etf_pair_relative_strength_b021c2`——"ETF pair relative strength rotation long only switch between two correlated ETFs backtest"。命中 QuantConnect 论坛帖子"QQQ/SPY Momentum Rotation System"（相关性 0.88），WebFetch 全文打开。**采纳，开 T-20260928-44。**
5. `search:20260928:web:publicly_disclosed_live_tracked_e662b2`——"publicly disclosed live tracked trading strategy rules verified returns 2024 2025 not black box"。命中 "Congressional Trade Tracking"（bit.com 知识库，相关性 0.331），WebFetch 全文打开，发现国会/政治交易复制型 ETF（NANC/GOP）这条新线索。
6. `search:20260928:web:congressional_stock_trading_abnormal_666d04`——"congressional stock trading abnormal returns academic study STOCK Act disclosure lag eliminated edge"。两篇学术论文（ScienceDirect、SSRN）均 403/付费墙打不开全文，只有 SSRN 摘要片段（不算读过原文，未作为证据使用）。改用 WebSearch + WebFetch 打开 24/7 Wall St 文章（2026-04-20，含具体数字和反面证据），**采纳，开 T-20260928-43。**

四类证据（论文复现、反面证据、开源代码、从业者实盘记录）覆盖情况：论文/研究（Garcia-Ares 2025、Quantpedia 设计稿）、反面/怀疑证据（24/7 Wall St 对 NANC 的"科技股集中巧合"质疑、QuantConnect 论坛工作人员指出代码 bug）、开源/复现（GitHub `AlphaRotationLab/US-ETF-Rotation-Model` 搜到但未深入，非本次采纳方向）、从业者实盘记录（NANC/GOP 自身就是实盘 ETF，24/7 Wall St 给出自发行以来的真实回报）都有覆盖。

## 证据表（每条来源都用 WebFetch 打开过全文，不是只读搜索摘要）

| 方向 | 来源 | 样本期/机制 | 已知数字 | 反面/弱点 | 取舍 |
|---|---|---|---|---|---|
| **期权到期周日历效应** | Quantpedia，https://quantpedia.com/strategies/option-expiration-week-effect（2026-09-28 全文）；Garcia-Ares & Muravyev 2025，https://www.fma.org/assets/docs/Derivatives2025/GarciaAres.pdf（2026-09-28 全文）；harbourfronts.com 摘要（2026-09-28 全文） | Quantpedia：只做多 S&P100 大盘股，含第三个星期五的一周持仓、其余现金，1988-2010；Garcia-Ares：近期（2025 发表）研究到期日+次周一的订单失衡驱动的期权收益异象，机制仍在起作用，但研究的是期权收益不是股票方向 | 年化 9.3%、夏普 0.61、最大回撤 -15.14%（老样本） | 无近期股票方向的数字、无衰减信息、machine-generated 数据挖掘风险（"第三个星期五"）需要安慰剂对照 | **开 T-20260928-42**：纯日历+收盘价规则，零新数据管线，直接填补覆盖地图明确标注的空白 |
| **国会/政治交易复制 ETF 轮动** | bit.com，https://www.bit.com/knowledge-hub/congressional-trade-tracking（2026-09-28 全文）；24/7 Wall St，https://247wallst.com/investing/2026/04/20/if-you-invested-in-these-congressional-trading-etfs-at-launch-heres-what-youd-have-today/（2026-09-28 全文） | STOCK Act 30-45 天披露延迟；NANC/GOP 2023-02-07 发行至今实盘 | NANC 总回报 88.49%（跑赢标普 74.70%），GOP 64.31%（跑输） | 24/7 Wall St 原文明确质疑"跑赢是科技股集中持仓的巧合，不是信息优势"（NVDA/MSFT/AMZN 占比高）；披露延迟可能已让市场消化优势；本地面板只从 2024-01 起（~2.7 年），无压力期覆盖；成交量薄（千股量级），需要价差敏感性测试 | **开 T-20260928-43**：填补 `public_records.copy_verified_live` 格子（C2/Kinfo 此前判定为死路），标的已在本地面板，规则完全由基金自身价格体现，不需要抓取国会原始披露数据 |
| **ETF 对相对强弱切换（只做多 pairs）** | QuantConnect 论坛，https://www.quantconnect.com/forum/discussion/19216/qqq-spy-momentum-rotation-system/（2026-09-28 全文） | QQQ/SPY 20 日相对动量+0.5%阈值+5 日调仓，2010-2024 | CAGR 19.02%、夏普约 0.8（作者自估） | 单一作者、平台工作人员在同帖指出代码有 bug（未终止字符串、计数器提前递增）、无人复现、无样本外/实盘数据——弱证据但未被反面证据否定 | **开 T-20260928-44**：填补 `relative_value.pairs_stat_arb` 格子明确标注"只做多一腿从未单独测过"；复用现有轮动引擎（菜单=2、top_n=1），零工程成本，扩展到 6 对相关 ETF |

## 丢弃的方向

- **杠杆 ETF 收盘再平衡流**：找到的都是期权市场流动性/做市商库存影响的研究，没有可转成"只做多 weights_fn"规则的股票方向性数字，未开任务。
- **Russell 重构交易**：官方 PDF 打不开（二进制），且和已判 `evidence_too_weak` 的指数纳入/剔除效应同族，重开需要"细分仍有效"的具体证据，本次没找到；即使有效也需要额外的成分股变更事件日历（不在现有收盘价面板里），engineering 成本不低，未开任务。
- **期权到期日的期权收益异象本身**（Garcia-Ares 论文的原始主题）：研究对象是期权收益，不是股票方向收益，我们不能交易期权（Alpaca Paper 只做多股票/ETF），只借用它作为"机制近期仍在起作用"的旁证，不单独开任务。

## 产出

- `reports/research/harvest/directions.jsonl` 新增 3 行：`dir:option_expiration_week_calendar_effect`、`dir:congressional_political_trade_replica_etf_rotation`、`dir:etf_pair_relative_strength_switch`（均 `status: queued`，`found_by: gap-search-2026-09-28-22`）；`uv run oc research directions validate` 通过。
- `reports/research/harvest/coverage.json`：四个指定格子（`flows_structural.rebalance_and_hedging_flows`、`relative_value.pairs_stat_arb`、`public_records.copy_verified_live`、`flows_structural.calendar_and_fomc`）都追加了本次搜索记录；前三个格子的 `directions` 数组各加了一条新方向 id。
- `reports/research/control/autonomous-queue.md` 文件末尾追加三个 `status: ready` 任务块：T-20260928-42（期权到期周，priority 2）、T-20260928-43（政治交易复制 ETF，priority 2）、T-20260928-44（ETF 对相对强弱切换，priority 3）。
- 本文件。
