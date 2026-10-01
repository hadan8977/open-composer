# 来源索引：阶段评估、因子择时、Alpaca 模拟盘事实（2026-10-01）

抓取时间 2026-10-01 约 10:20 UTC，交互会话（Opus）。用于 `reports/research/program/regimes-2026-10-01/report.md` 和修正案 A1。

## 查询
1. `factor momentum out-of-sample post-publication performance Ehsani Linnainmaa Gupta Kelly time-series factor momentum recent evidence`
2. `Alpaca multiple paper trading accounts per user API keys how many paper accounts`
3. `Alpaca time_in_force cls market on close order paper trading short selling support`

## 已打开的原文

| 文件 | 来源 | 用到的内容 |
|---|---|---|
| `fan2022_reexamination_factor_momentum.txt` | Fan, Liu 等，"A reexamination of factor momentum: How strong is it?"，Financial Review 57 (2022) 585–615，开放获取 PDF（pureadmin.qub.ac.uk） | 摘要："The factor momentum strategies do not outperform the corresponding long-only strategies in either sample"；EL 样本 FMOM 年化 4.07% < 买入持有 4.26%；只有 22%–27% 的因子有强延续 |
| `neuhierl_randl_reschenhofer_timing_factor_zoo.txt` | Neuhierl, Randl, Reschenhofer, Zechner，"Timing the factor zoo"，2023-03-15 版（afajof.org） | 摘要：300 多个因子、39 个预测量；"Past factor returns and volatility stand out as the most successful individual predictors"；"The median improvement of a timed vs. untimed factor is about 2% p.a."；择时多因子组合收益比不择时高 20% |

## Alpaca 文档（WebFetch 原文引用，未另存快照）

https://docs.alpaca.markets/us/docs/paper-trading
- "To create a new paper account, click the paper account number in the upper left corner of the dashboard and select 'Open New Paper Account.'"
- "Don't forget to generate new API keys for any newly created account."
- "All orders submitted in paper trading will be matched against the best available current market price (NBBO)."
- 文档列出模拟盘不计入：market impact、information leakage、latency slippage、order queue position、dividends、borrow fees。
- "When orders are eligible to be filled, they will receive partial fills for a random size 10% of the time."
- 默认 10 万美元；"You can reset the paper trading account at any time later with arbitrary amount as you configure."

https://docs.alpaca.markets/us/docs/orders-at-alpaca
- CLS："This order is eligible to execute only in the market closing auction." "CLS orders submitted after 3:50pm but before 7:00pm ET will be rejected." "CLS orders submitted after 7:00pm will be queued and routed to the following day's closing auction."
- OPG 截止 9:28am ET。
- 文档没有写模拟盘如何撮合 CLS 和 OPG 订单。这要在模拟盘两周的执行验证里实测。

每个用户最多 3 个模拟账户：只有搜索摘要和社区帖子这么说（forum.alpaca.markets "Multiple Paper Trading Subaccounts"），官方文档页没有写上限。标记为待核对。
