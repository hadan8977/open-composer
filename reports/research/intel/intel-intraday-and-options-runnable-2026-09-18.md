# 情报简报：盘中 / 隔夜 / 期权策略——按"我们的模拟盘能不能执行"筛过一遍

日期：2026-09-18（周五）。本简报**不写代码、不跑回测**，只做情报调查，按目录 `README.md` 的四问框架（新不新 / 有没有人验过 / 有没有人分享了实盘或模拟盘净值 / 在我们机器和账户上能不能跑）逐一过筛。

## 0. 范围、账户约束与规则

- 数据：美股 1 分钟线 ~1.34 万只标的 2016–2026（SIP，本地 60GB）、日线 2016–2026。
- 账户：Alpaca **纸面盘**，权益 $103k，日内 4 倍杠杆，可做空，期权 **Level 3**（$50.9k 期权购买力）。
- 算力：3.9GB / 2 核 / 无 GPU；调度粒度是"某分钟跑一次任务"，不是亚秒级。
- 基准：SPMO，2024-01-08→2026-09-16，年化 34.7%、最大回撤 -20.1%、Sharpe 1.43（用户给定，未重新核实，仅作比较锚点）。
- 规则：每条结论都标注来源 URL + 日期；明确区分"作者自己说"和"第三方独立复现"；没人复现的直接写"无第三方复现"。

---

## 1. 逐策略情报卡

### 1.1 开盘区间突破 ORB（QQQ/TQQQ 版本 + "Stocks in Play" 多股票版本）

**规则（原始）**：5 分钟 ORB——如果开盘后第一根 5 分钟 K 线收涨（跌），在第二根 5 分钟开始做多（空）该标的；首根开收盘价接近则不开仓。止损设在开盘区间另一端，当日收盘前平仓或达到止盈（常见 10×ATR 止盈 / 1×ATR 止损，见 [QuantConnect 研究帖](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/)）。

**作者报告的业绩（未经独立复核前，均为作者自称）**：

| 论文 | 标的/样本 | 区间 | 报告业绩 | 状态 |
|---|---|---|---|---|
| Zarattini & Aziz, *Can Day Trading Really Be Profitable?* [SSRN 4416622](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416622) | QQQ 单标的 | 2016–2023/02 | 1,795 笔交易，Sharpe 1.12，零滑点净利 $138,639 | 作者自述 |
| Zarattini, Barbon & Aziz, *A Profitable Day Trading Strategy For The U.S. Equity Market*，2024-03-15 发布/2025-04-29 修订，[SSRN 4729284](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284) | 7000+ 美股，"Stocks in Play"+相对成交量过滤 | 2016–2023 | 累计 1,637%，年化 41.6%，Sharpe 2.81，最大回撤 12% | 作者自述 |
| Zarattini & Aziz 2025 Nasdaq-ETF 论文（同一系列，见 [danfin.net 综述](https://danfin.net/opening-range-breakout-research)，2026 访问） | QQQ / TQQQ | 2016–2023/02 | QQQ：676%/年化33%/Sharpe1.13/回撤22%；TQQQ：1,484%/年化48%/Sharpe1.19/回撤28%；参数寻优版本 9,350%（作者自己也警示这是过拟合风险更高的版本） | 作者自述，假设零滑点 |

**独立验证——最关键的部分**：

- **[github.com/giovannibrusco/zarattini-2023-orb-qqq](https://github.com/giovannibrusco/zarattini-2023-orb-qqq)**（真正的第三方复现，含压力测试）：交易笔数（1,775 vs 论文 1,795）和 Sharpe（1.06 vs 1.12）基本对上原文；但**加入滑点后，净盈亏在约 2.2 美分/股滑点处归零**——而 QQQ 的买卖价差本身就接近 1 美分,安全边际很薄。作者进一步测试"09:25 NQ 期货确认过滤器"：净利升至 $44,332，单笔 t 值 2.05（~5% 显著），edge 提升到 $0.125/股；但用 QQQ 自己的盘前 K 线做安慰剂对照,edge 只有 $0.079/股、t=1.27（不显著），说明 NQ 期货确实带来信息增量。**红旗**：过滤后 76% 的盈亏集中在 2022 年一年；2017、2020、2023 年初均亏损；过滤后 Sharpe(0.77) 只是略高于买入持有(0.72)，置信区间重叠；过滤器是在同一段数据上选出来的，没有样本外验证。
- **[danfin.net 独立综述](https://danfin.net/opening-range-breakout-research)**（2026）：指出两篇论文测的其实是不同规则（不是互相复现），"零滑点"假设在窄止损策略里"后果尤其严重"，没有清晰的样本外验证窗口，论文测的是 QQQ/TQQQ 现货/个股而非实际交易者常用的 NQ 期货或 CFD，最大回撤/低胜率与大多数 prop firm 的评估规则不兼容。结论是"支持进一步测试，但不能证明存在永久或普遍的异象"。
- **作者自己团队 2026 年最新自我修正（不是第三方，但值得记录）**：Zarattini 的公司 Concretum Group（[关于 Zarattini](https://ch.linkedin.com/in/carlozarattini)，公司 2016 年由他创立）2026-07-08 发文 [《Improving the Opening Range Breakout Strategy on SPY》](https://concretumgroup.substack.com/p/improving-the-opening-range-breakout)：用 2008–2025 年 SPY 数据测"朴素版"5 分钟 ORB（单一 ETF，不做多股票筛选），**扣费后 CAGR 只有 1.0%、Sharpe 0.14、年化 alpha 1.75%（不显著）**——即论文作者自己承认，脱离"Stocks in Play"多股票相对成交量过滤后，单 ETF 的朴素 ORB 几乎不赚钱；加过滤/仓位管理后才回到 CAGR 12.1%/Sharpe 0.84/alpha 12.80%（显著）。这是迄今找到的**最新鲜（2026-07）也最诚实的一条证据**：edge 高度依赖"多股票+异常放量"这个具体设计,而不是"开盘突破"本身。
- 社区端（QuantConnect 论坛 [Opening Range Break paper 讨论帖](https://www.quantconnect.com/forum/discussion/19456/opening-range-break-paper/)，90+ 评论）反映过担心过拟合、手续费吃掉约 25% 盈亏、edge 可能来自选股而非 ATR 突破本身，但未取得该帖原文逐条确认，标记为"社区二手转述"。

**成本假设**：原始论文默认零滑点；QQQ 现价差约 1 美分，独立复现给出的真实盈亏平衡点在约 2.2 美分/股滑点。个股版本手续费/冲击成本未在原论文详细披露。

**Broker 需求 vs 我们账户**：需要做多做空、日内开平仓（我们都支持，4 倍日内杠杆+可做空）；NQ 期货确认过滤器需要**期货行情/账户**——**Alpaca 不提供期货交易**，这个具体验证过的变体在我们账户上无法照搬，只能用替代品（如 QQQ 盘前 K 线），但复现已经证明这个替代品是"安慰剂",不显著。"Stocks in Play"版本需要跨 1.3 万+标的的相对成交量实时排序，计算量在 2 核机器上可行（预先算好 ADV，当天早盘做一次排序）。

**最便宜的决定性测试**：用本地 1 分钟线，只对 QQQ/TQQQ 复现 giovannibrusco 的滑点敏感性分析（不同滑点假设下净盈亏归零点在哪里），成本几乎为零（几十分钟单核计算），先确认在我们自己的数据源上盈亏平衡点是否也在 1-3 美分区间。

**红旗**：过拟合警示由作者自己发出（9,350% 的参数寻优版本）；单 ETF 朴素版本 2026-07 被原作者证实几乎不赚钱；NQ 期货过滤器我们broker 不支持；PnL 高度集中在单一年份（2022）。

---

### 1.2 盘中动量 / 噪声带策略（Ákos Maróy 及相关工作）

**规则**：基于 Gao, Han, Li & Zhou (2018) *Market Intraday Momentum*（[JFE 129, 394–414](https://www.sciencedirect.com/science/article/abs/pii/S0304405X18301351)，[SSRN 2440866](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866)）的学术发现——SPY 开盘后前 30 分钟收益能预测收盘前最后 30 分钟收益（1993–2013 数据，波动大/成交量大/宏观新闻日更显著）——衍生出"噪声带"日内动量策略：用一条随时间变化的波动率归一化阈值带（"noise cone"）判断价格突破是否代表真实的供需失衡而非噪声，突破带上沿做多、带下沿做空。

**最新论文**：Ákos Maróy，*Improvements to Intraday Momentum Strategies Using Parameter Optimization and Different Exit Strategies*，2025-01，[SSRN 5095349](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5095349)。用不同出场方式（VWAP 出场、"梯形"出场）在 SPY/QQQ 上做参数寻优，**部分配置报告 Sharpe > 3.0、年化收益 > 50%**（作者自述，样本内寻优）。胜率仅"40% 出头"，靠少数大赚的日子覆盖大量小亏，凸性payoff。

**独立验证**：**没有找到第三方复现**。这是 2025 年 1 月才发表的论文，作者本人此前已发过同题材的早期版本（QuantConnect 社区帖 [Beat the Market: An Effective Intraday Momentum Strategy for SPY](https://www.quantconnect.com/forum/discussion/17091/beat-the-market-an-effective-intraday-momentum-strategy-for-s-amp-p500-etf-spy/)），存在自我引用/自我优化的问题。找到一个第三方代码复现仓库 [github.com/nyyyaomi/intraday-momentum-research](https://github.com/nyyyaomi/intraday-momentum-research)（声称做了交易成本核算和容量诊断），但未能取得其具体复现结论（数字未公开或未被搜索引擎摘要覆盖）——**只能记为"有人在尝试复现,结论未知"，不能算验证**。Quantitativo 有一篇把同思路搬到 ES/NQ 期货上的博客（[quantitativo.com](https://www.quantitativo.com/p/intraday-momentum-for-es-and-nq)），期货工具我们broker不支持,仅供参考。

**成本假设**：论文本身是否含真实交易成本核算不明确（"Improvements"标题聚焦于参数优化和出场方式,而非成本);"高Sharpe靠出场方式优化"本身就是过拟合的经典信号。

**Broker 需求 vs 我们账户**：日内需要多次进出（noise band 需要按 1–5 分钟频率持续监控），我们"整分钟调度"的模式可以覆盖，但需要相当密集的调度（例如每 5–15 分钟一次判断），比其它候选策略运营负担更重。多空都要用（可支持）。

**最便宜的决定性测试**：在本地 SPY/QQQ 1 分钟线上，只实现论文摘要里描述的"noise cone"阈值公式（不做出场方式寻优），看样本外（例如只用 2024–2026 数据,不参与任何参数选择）Sharpe 是否还能到 1 以上;如果连 1 都到不了,直接排除,不用碰"参数优化+出场优化"这层。

**红旗**：单一作者系列论文自我迭代，无第三方复现,出场方式的" улучшение"（改进）本身是常见的过拟合来源，胜率低、payoff 高度依赖尾部,小样本下极易被数据挖掘误导。

---

### 1.3 隔夜 vs 盘中收益分解

**核心发现（学术）**：Alpha Architect，[《Trading Costs Wipe Out the Overnight Return Anomaly》](https://alphaarchitect.com/2020/06/trading-costs-wipe-out-the-overnight-return-anomaly/)，2020-06。用 SPY 1993–2020 数据比较"收盘买入次日开盘卖出"（隔夜）、买入持有、"盘中only"三种策略：**不计成本时隔夜策略累计涨 717%，跑赢买入持有的 627%，远超盘中only 的 12%**；计入当日真实买卖价差 + $0.01/股佣金后（原始"隔夜异象"论文本身没算价差,这篇文章补上了这块），隔夜相对盘中的优势"平均仍然存在,但统计稳健性很低"——即净胜出更像是随机游走噪声,而非可稳定复现的策略（基于搜索引擎摘要转述，原文页面对本工具返回 403，未能直接抓取全文核对，读者可自行访问上述 URL 核实）。

**近期学术进展**：Zirk-Sadowski & Hryckiewicz，*Intraday and overnight return anomalies: Evidence from 11.6 million price observations*，Finance Research Letters 86, 2025，[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1544612325018926)。用纽交所小盘股逐笔数据（11.6M 观测,30秒-60分钟多种持有期）发现"11点效应"在45-60分钟持有期上显著（周二至周四），周一则出现"反向早盘效应"（10点）——见下节。

**"Night Moves"论文**：Haghani, Ragulin & Dewey (2022)，[SSRN 4139328](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4139328)，[Elm Wealth 版](https://elmwealth.com/night-moves-overnight-drift/)：只在闭市期间持仓的多空组合，**年化 38%，Sharpe ≈ 3——但作者明确说明"完全没有计入交易成本"**。这是一个重要的"作者自己承认不含成本"的案例，直接与 Alpha Architect 的发现（成本会大幅侵蚀隔夜异象）相呼应。

**商业化产品的真实结局**：NightShares 500 ETF（NSPY），设计目的就是"买收盘、卖开盘"捕捉隔夜效应（见 [etfdb.com/etf/NSPY](https://etfdb.com/etf/NSPY/)、[US News 简介](https://money.usnews.com/funds/etfs/large-blend/nightshares-500-etf/nspy)）。**该基金已退市，最后交易日为 2023-07-31**——这是一条来自真实市场的"实盘"证据：把隔夜异象包装成产品后，未能吸引到足够资金存续（退市可能因规模不足而非策略本身失效，两种可能都要如实记录，不能只挑对自己有利的解释）。

**Broker 需求 vs 我们账户**：完全可执行——只需在收盘前几分钟买入、开盘后几分钟卖出，多空都支持,不需要期权或杠杆。执行摩擦极小（SPY/QQQ 价差常年在 1 美分左右，比 Alpha Architect 研究窗口 1993–2020 的历史平均价差小很多，现代实现可能比原研究的成本假设更有利，但这只是推测，没有查到 2020 年代价差重做的最新成本敏感性分析）。

**最便宜的决定性测试**：本地 1 分钟线直接切出"15:59 买入价"和"次日 9:31 卖出价"，配 SIP 数据里的估计价差,在 SPY/QQQ 上跑 2016–2026 全样本，几分钟算完，立刻知道净值曲线和 Sharpe，且可以叠加下一节的"星期几"过滤器一起测。

**红旗**：Alpha Architect 的结论是"统计稳健性低,接近随机游走"；Night Moves 的 38%/Sharpe3 明确不含成本；商业化产品已退市。**不建议作为独立策略上实盘,只值得当作免费的、可以立刻在本地数据上验证/证伪的候选**，且应该和下一节的星期几效应结合起来看,而不是单独交易"每天隔夜"。

---

### 1.4 星期几 / 时段效应（周一午后反转、11点效应、午餐效应）

| 效应 | 论文/来源 | 区间/数据 | 报告业绩 | 验证状态 |
|---|---|---|---|---|
| 周一午后反转 | Pigorsch & Schäfer，*Reversal of Monday returns: It is the afternoon that matters*，Finance Research Letters 65, 2024，[ScienceDirect](https://www.sciencedirect.com/science/article/pii/S1544612324005555) | 美股大样本截面 | 按"周一下午收益"分组的多空组合：市值加权年化 **32.36%，Sharpe 1.77**（毛）；**扣除平均买卖价差后 27.14%** | 同行评审期刊发表，但**未找到第三方复现**；周一早盘收益无预测力,只有下午段有效；效应对大盘股更强,不能用常见风险因子/财报公告解释 |
| 11点效应 | Zirk-Sadowski & Hryckiewicz，*Intraday and overnight return anomalies*，Finance Research Letters 86, 2025，[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1544612325018926) | 纽交所小盘股 11.6M 笔观测 | 45–60 分钟持有期上"11点效应"显著（周二至周四）；周一反而在10点出现反向早盘效应 | 同行评审期刊，样本量大，但**同样没有第三方复现**，且是小盘股逐笔数据而非我们熟悉的 SPY/QQQ |
| 午餐效应 | Vojtko & Dujava (Quantpedia)，*Lunch Effect in the U.S. Stock Market Indices*，2024，[SSRN 4934614](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4934614)，[Quantpedia 页面](https://quantpedia.com/lunch-effect-in-the-u-s-stock-market-indices/) | S&P500/NASDAQ/道指 | 午休后价格系统性上涨的日内模式 | 作者自己在文中提醒"不保证是可交易的 edge，交易成本和市场冲击会侵蚀简单的日内策略" |

**Broker 需求 vs 我们账户**：周一午后反转的原始检验是**跨股票截面多空组合**（需要同时做多做空一篮子股票），如果要在我们账户上落地，最现实的简化是把它降级成"单一指数择时"信号——即用 SPY/QQQ 周一 12:00 相对开盘的收益方向，决定本周剩余交易日是否持有该 ETF 多头/空头——**这是我们自己对论文结论的简化改编，论文并没有直接测试这个单指数版本，效果未知，必须在决定性测试里单独验证，不能假设截面因子的 Sharpe 会原样转移到单一指数择时上**。11点效应和午餐效应的样本频次（45-60分钟或午休窗口）适合"整分钟调度"，执行摩擦小。

**最便宜的决定性测试**：
1. 周一午后反转（改编版）：本地数据里，每周一 12:00 记录 SPY/QQQ 相对开盘的收益符号，作为本周剩余四天的持仓方向信号,回测 2016–2026,几分钟出结果。
2. 11点/午餐效应：直接在 SPY/QQQ 分钟线上按论文定义的时间窗口切收益，看 t 统计量在我们自己的数据上是否复现（这比自己设计策略更接近"验证已发表结果"，符合目录规则里"优先复现别人已发表的结果"）。

**红旗**：三个效应都没有第三方复现；周一效应从截面因子简化为单指数择时是我们自己的改编，不是论文原文结论,决定性测试必须把"改编版"和"论文原版"分开评估。

---

### 1.5 缺口回补/延续、VWAP 均值回归、首小时区间、尾盘动量

这一组是证据最弱的一组——**基本没有找到同行评审论文或可核实的实盘/模拟盘净值曲线**，只有零售交易博客的样本内声称：

- 缺口策略：QuantifiedStrategies 声称 SPY 缺口回补历史成功率约 70%，[gap-fill-trading-strategies](https://www.quantifiedstrategies.com/gap-fill-trading-strategies/)、[gap-trading-strategies](https://www.quantifiedstrategies.com/gap-trading-strategies/)，但同一篇文章也承认"容易摘的果子已经被套利掉了""不像以前那么好赚"。TradingStats.net 对 NQ 期货 2015–2025 做过缺口统计（[tradingstats.net/gap-fill-strategy](https://tradingstats.net/gap-fill-strategy/)），期货工具我们broker不支持。
- VWAP 均值回归：只找到零售教程性质的描述（[crosstrade.io](https://crosstrade.io/learn/trading-strategies/vwap-reversion)、[chartswatcher.com](https://chartswatcher.com/pages/blog/6-powerful-vwap-trading-strategies-for-2025)）和一个未署名来源转述的"2022年QuantConnect在100只流动性NASDAQ股票上的回测"（2倍标准差VWAP带,做空胜率63%/做多61%,盈亏比约1.4-1.5:1，但未给出扣费后收益率、也找不到原始回测报告的直接链接，**视为二手转述，不可信度低**）。
- 首小时区间：ORBSetups 等站点给出的胜率/Sharpe（如"2.4 Sharpe、-0.042 beta"）与前述 Zarattini/Aziz 系列高度雷同，很可能是同一批论文结果的转述而非独立首小时策略证据。
- 尾盘动量：唯一站得住脚的学术基础还是 1.2 节引用的 Gao/Han/Li/Zhou (2018) 首尾半小时收益相关性,该论文本身不是一个可直接执行的"策略"，只是一个统计发现;此外，MOC（市价收盘单）失衡交易，[sellside.substack.com 的说法](https://sellside.substack.com/p/exclusive-research-moc-imbalance)明确指出"不要用短期期权去交易 MOC imbalance,这从来不是推荐策略,而且一直不赚钱"——**这是一条明确的"不要做"红旗，直接来自实践者**。

**结论（直说）**：缺口回补/延续、VWAP 均值回归、首小时区间，**目前没有查到任何独立验证或公开对账单/净值曲线**。它们不宜进入 Top 5，只适合"如果闲算力足够,自己先在本地数据上定义规则测一遍再决定要不要投入"，绝不能因为博客说了 70% 胜率就直接分配资金。

---

### 1.6 0DTE / 短期期权策略

**市场背景**：0DTE 期权占 2025 年全美挂牌期权总成交量的 **24.1%**（2024 年为 21.5%，较 2022 年几乎翻倍），[Traders Magazine, 2026-02-19](https://www.tradersmagazine.com/vol-report/vol-report-0dte-flex-options-are-2025-heroes/)。

**最扎实的一条"实盘"证据（非机构审计，但公开、长期、可证伪）**：Karsten Jeske（Early Retirement Now），[《Options Trading Series Part 14 – 2025 Review》](https://earlyretirementnow.com/2026/01/30/options-trading-series-part-14-year-2025-review/)，2026-01-30 发布。策略是**裸卖**（非价差）：1DTE 隔夜看跌（~7.2% 虚值）、0DTE 盘中看跌（~3.9%虚值）、0DTE 盘中看涨（~1.9%虚值）、30-180天的深度虚值看跌（~70%虚值），用止损限价单控制风险。

| 指标 | 数值 | 期间 |
|---|---|---|
| 2025 年净利 | $103,700（0DTE/1DTE 占约 $90,000，权利金捕获率 74.2%） | 2025 全年 |
| 年化收益 vs 标普 | 13.99% vs 14.33% | 2018 至今（退休后自营账户） |
| 波动率 | 约标普的 3/4 | 同上 |
| 月度胜率 | 2022年6月以来零亏损月 | 2022-06 至今 |
| 特殊风险事件 | 2025年4月波动飙升期间出现亏损，尽管有止损限价单保护 | 2025-04 |

作者自己列出的关键说明：容量约每份隔夜看跌合约对应 $17-20万组合规模（规模天花板明显）；止损限价单在闪崩中可能跳空失效，裸卖仓位理论上损失无上限；收益高度依赖保证金杠杆的可获得性。

**关键的账户可行性问题——这是本简报中最重要的一条"broker硬约束"**：直接查了 Alpaca 自己的支持页面（[alpaca.markets/support/what-option-levels-or-tiers-do-you-provide](https://alpaca.markets/support/what-option-levels-or-tiers-do-you-provide)）：

> Level 1：covered call、cash-secured put。Level 2：以上 + long call、long put。Level 3：以上 + spreads、straddles、butterfly spreads、iron condors。**文档从未提及任何级别支持裸卖（naked/uncovered short call 或 put）**。

也就是说，**Alpaca 完全不提供裸卖期权（无论现金账户还是保证金账户），哪怕是 Level 3。ERN 的核心策略（裸卖看跌/看涨）在 Alpaca 上无法照搬**，我们只能做：(a) 全额现金担保的 cash-secured put（占用全部行权价×100 的购买力，资金效率远低于裸卖）；(b) Level 3 允许的**定义风险价差**（put credit spread / iron condor 等，保证金只等于"价差宽度-权利金"，资金效率高得多）。这意味着如果要复刻"卖出下行波动率赚权利金"这个思路，**在我们账户上更现实的实现是 put credit spread，而不是逐字复刻 ERN 或 PUT 指数的全额现金担保结构**——这是我们自己的工程判断，不是任何论文/作者的结论，必须在决定性测试里明示。

**Alpaca 期权 API 现状（详见第 2 节）**：Level 3 多腿单已在纸面盘默认开通（[changelog](https://docs.alpaca.markets/changelog/multi-leg-level-3-options-trading-in-paper)），但**多腿单不支持挂钩止损/条件单（bracket/OCO）**，只能用单腿的 stop / stop_limit（[Alpaca 期权交易文档](https://docs.alpaca.markets/us/docs/options-trading)；社区反馈"multi-leg 报 complex orders not supported for options trading"错误，[论坛帖 2026-05-11 相关讨论](https://forum.alpaca.markets/t/bracket-orders-with-options/13915)）。这意味着任何多腿策略的止损/展期都要靠我们自己的调度任务去监控和下平仓单，不能依赖 broker 原生保护。免费的 Basic 数据计划只给期权"指示性"报价，真实 OPRA 逐笔期权行情需要付费 Algo Trader Plus（[real-time-option-data 文档](https://docs.alpaca.markets/us/docs/real-time-option-data)），这是决策质量和延迟上的额外成本,需要预算。

**独立验证**：ERN 的记录是他本人自己发布的月度更新，**不是被第三方审计的track record，但公开、逐月、跨越 8 年，可以被读者逐年核对**，比大多数"策略贴"更可信，但仍然不算独立验证。学术上，0DTE 卖方赚的是"偏度溢价"（skew premium）,期权卖方为承担不对称尾部风险要求补偿,这是主流共识（见 James O'Donovan, *0DTE Options and the Price of Tail Protection*，[SSRN 6836498](https://papers.ssrn.com/sol3/Delivery.cfm/6836498.pdf?abstractid=6836498&mirid=1)），但没有查到任何第三方对 ERN 具体规则的复现。

**成本/摩擦**：Alpaca 期权交易不收佣金，但有监管过手费（TAF $0.00329/张仅卖方收取、ORF $0.02295/张买卖都收，[Alpaca 手续费说明](https://alpaca.markets/support/what-are-the-commission-fees-per-option-contract)）——对高频短期期权策略而言这些"每张几美分"的监管费会在高换手下累积，需要纳入决定性测试的成本假设。

**最便宜的决定性测试**：不需要实盘期权数据，先用我们自己的 1 分钟标的价格 + Black-Scholes 近似隐含波动率（用 VIX/VIX9D 历史数据做代理），估算"周度 cash-secured put" vs "周度 put credit spread"在 SPY/QQQ 上的历史权利金和名义占用资金,对比资金效率,决定用哪种结构,再决定要不要花钱订阅 OPRA。

**红旗**：ERN 策略的核心杠杆来源（裸卖）我们broker不支持；多腿单无原生止损；真实期权数据要额外付费；监管过手费在高频短期期权上会侵蚀收益,原始研究通常未充分披露。

---

### 1.7 备兑看涨 / 现金担保看跌 / put-write 指数（PUT, BXM）vs SPMO

| 指数/产品 | 规则 | 近期业绩 | 来源 |
|---|---|---|---|
| Cboe S&P 500 PutWrite Index (PUT) | 每月卖出平值现金担保看跌期权 | 2024 年 +17.8%（同期 SPX +25.0%）；2025 YTD +3.38%（数据截取时点未知，需谨慎）；1986-2023/08 长期年化 9.40% vs SPX 9.91%，标准差 10.26% vs 15.38%，最大回撤 -32.66% vs SPX -50.96% | [portfolioslab.com/symbol/^PUT](https://portfolioslab.com/symbol/%5EPUT)、[Cboe PUT 说明书](https://cdn.cboe.com/resources/indices/factsheet/CboeGlobalIndices_PUT-Index.pdf) |
| Cboe S&P 500 BuyWrite Index (BXM) | 持有标普成分股+每月卖出平值看涨 | 2024 年 +20.1%；2025 年 +8.9% | [ycharts.com/indices/^BXM](https://ycharts.com/indices/%5EBXM)、[Cboe BXM 说明书](https://cdn.cboe.com/resources/indices/factsheet/CboeGlobalIndices_BXM-Index.pdf) |
| JEPI（主动备兑，ELN结构） | 低波动股票+期权权利金 | 5年年化约9-11% | [heygotrade.com 对比](https://www.heygotrade.com/en/blog/covered-call-etfs-2026-jepi-jepq-qyld-comparison/) |
| QYLD（纳指100每月平值备兑） | 高权利金但严重封顶上行 | 5年年化约4-6%，存在净值持续侵蚀 | 同上 |

**与 SPMO 基准（年化34.7%/回撤-20.1%/Sharpe1.43，2024-01-08→2026-09-16）的对比**：PUT 和 BXM 在给出的两个可比年份里（2024、2025部分）**都明显跑输 SPMO 的年化水平**，唯一优势是波动率和回撤显著更低（PUT 历史最大回撤只有 SPMO 的约 2/3）。这类策略更适合"降低波动、跑输于强势动量市场"的定位,而不是"打败 SPMO"的定位——如果目标就是超过 SPMO,这条路线大概率不满足,除非叠加杠杆（但杠杆会侵蚀掉它低回撤的核心优势）。

**独立验证**：Cboe 指数本身由交易所计算发布,方法论公开（[Cboe PutWrite 方法论 PDF](https://cdn.cboe.com/api/global/us_indices/governance/Cboe_PutWrite_Indices_Methodology.pdf)），**这是本简报里少数几个"官方指数级别、近40年历史"的强证据**，但它衡量的是被动、无择时的机械月度展期,不是主动策略,收益上限被结构性锁死。

**Broker 需求 vs 我们账户**：现金担保看跌是 Alpaca **Level 1** 就支持的最简单结构,完全兼容我们 Level 3 账户；但**资金效率低**——以 SPY/QQQ 现价计算，一份平值现金担保看跌通常要占用 5-6 万美元级别的购买力,而我们只有 $50.9k 期权购买力,意味着**同一时间基本只能担保 1 份合约**，规模扩展受限,必须用更深度虚值的执行价（降低占用资金）或改用 put credit spread（Level 3 支持,占用资金远小于全额担保）来提高资金利用率——这是我们自己的资金约束推导,不是 PUT 指数的原始方法论。

**最便宜的决定性测试**：直接下载/复用 Cboe 公开的 PUT、BXM 历史指数值（如有本地数据源）与 SPMO 做同期对比;如果没有现成数据源,用我们自己的期权定价近似（1.6节方法）模拟"周度现金担保虚值看跌"在 SPY 上 2016–2026 的净值曲线,与买入持有和 SPMO 对比。

**红旗**：历史上跑输 SPMO 这种强动量基准；资金效率与我们的 $50.9k 期权购买力冲突；QYLD类"高分派率"产品存在净值侵蚀,不能把分派率误当总回报（[QDTE 30天分派率>300%](https://seekingalpha.com/article/4856498-qdte-the-0dte-strategy-is-working-as-intended)这类数字尤其容易误导，那是分派率不是总回报）。

---

### 1.8 波动率/趋势过滤的杠杆 ETF 轮动（TQQQ/SOXL）

**规则（常见变体）**：只有当 QQQ 高于其200日均线且过去126个交易日为正收益时,才持有 TQQQ（或 SOXL）等3倍杠杆ETF,否则持有现金/国债,有的版本再加已实现波动率过滤避免高波动期入场。

**报告业绩**：

- 一个轮动回测（[finlab.finance](https://finlab.finance/en/blog/us-etf-rotation-strategy)）：2016年6月至2026年6月,保守版 CAGR 30.5%/最大回撤-17.9%,激进版 CAGR 55.1%/最大回撤-29.3%。
- 单纯移动均线过滤 TQQQ（不轮动，无来源作者署名的比较,来自搜索引擎摘要,需谨慎）：买入持有 TQQQ 终值 $3.96M/最大回撤-81.61%,加均线过滤后终值降到$1.12M/最大回撤降到-57.19%——**典型的"降回撤但也降终值"权衡**,且该分析本身来源不明确,仅供方向参考。
- **HFEA（Hedgefundie's Excellent Adventure，UPRO+TMF风险平价再平衡）2022年崩溃**是这条路线最著名的公开失败案例：2022年利率飙升、股债双杀,3倍杠杆股+3倍杠杆长债同时暴跌,策略赖以生存的"股债负相关"假设失效（[optimizedportfolio.com 总结](https://www.optimizedportfolio.com/hedgefundie-adventure/)、[hfea.neocities.org](https://hfea.neocities.org/)）。这是一条被广泛记录、影响过大量真实资金的"实盘"教训,不是假设。

**Composer.trade 上的自称实盘（半公开,未经审计）**：Composer 平台上多个公开"symphony"策略（如 [v6 Symphony Sorter](https://www.composer.trade/trading-strategies/v6-symphony-sorter-q4bmyjbVIT0eCKACg8YG)、[TQQQ FTLT with a bit of SOXL](https://www.composer.trade/trading-strategies/tqqq-ftlt-with-a-bit-of-soxl-and--V8PMHSkT4yH87TLz2B7K)）显示 YTD 收益 53%-80%区间。**这些数字是平台展示的、可能存在幸存者偏差（平台上表现差的策略容易被下架或不被推荐展示）,不是审计后的独立业绩,只能算"半公开的用户自建策略展示"，不算严格的第三方验证**。

**独立验证**：均线/波动率过滤对3倍杠杆ETF的效果，普遍被认可的**批评**是：慢速趋势过滤器容易"在暴跌后才卖出、在反弹后期才买回"，在3倍杠杆下这种滞后特别昂贵；波动率衰减不是唯一风险,更大的风险是趋势过滤器本身的滞后导致的大回撤（这一批评方向与我们过去在动量策略里记录过的"capture-ratio 缺陷"教训一致，参见项目内部记忆）。

**Broker 需求 vs 我们账户**：完全兼容——不需要做空、不需要期权，只需要按日频（甚至周频）调仓 TQQQ/QQQ/SOXL/现金,一天一次决策即可,资金效率高（$103k权益+4倍日内杠杆对单标的多头轮动来说绰绰有余,甚至用不到日内杠杆,过夜杠杆由ETF自身3倍杠杆提供）。

**最便宜的决定性测试**：用本地日线数据（不需要1分钟线）跑200日均线+已实现波动率过滤的 TQQQ/QQQ 轮动,重点检验 2022 年和历史上其他杠杆ETF暴跌年份的回撤表现,而不是只看牛市区间的CAGR——这是防止重复 HFEA 教训的关键。

**红旗**：HFEA 2022年崩溃是真实发生过的公开失败;Composer平台数字未经审计、可能存在幸存者偏差;均线过滤在震荡市会不断打脸(whipsaw),侵蚀掉大部分超额收益。

---

### 1.9 其他 2025–2026 零售证据

搜索没有找到新的、有可信实盘对账单支撑的独立新策略类别（除以上已覆盖的）。Composer.trade 一类平台上有大量自建"symphony"策略展示实时收益,但普遍缺乏审计、存在幸存者偏差,不构成独立验证。日内交易的整体统计背景值得记住：据 FINRA 数据,长期只有1-4%的日内交易者能持续盈利,72%整体亏损(来自搜索引擎摘要转述FINRA统计,未直接核实原始数据源),这是一条应该始终背景化的基础比率(base rate)。

---

## 2. Alpaca 期权 API 2026 现状（bracket + 多腿，逐条引用文档）

| 问题 | 结论 | 来源 |
|---|---|---|
| 纸面盘是否支持多腿(Level 3)期权 | 是,纸面盘账户默认自动开通,无需单独申请 | [Multi-leg (Level 3) Options Trading in Paper changelog](https://docs.alpaca.markets/changelog/multi-leg-level-3-options-trading-in-paper)、[Alpaca 支持页](https://alpaca.markets/support/does-alpaca-support-multi-leg-option-orders-such-as-spreads) |
| 支持哪些多腿结构 | spreads(牛/熊价差)、straddles、strangles、iron butterflies、iron condors；`order_class="mleg"`,每条腿在`legs`数组里定义,`leg_ratio`必须化简到最大公约数为1；一个 mleg 单内所有腿必须互相覆盖,不允许裸露空头腿 | [Options Level 3 Trading 文档](https://docs.alpaca.markets/docs/options-level-3-trading) |
| 是否支持裸卖(naked)期权 | **不支持,任何级别都不支持**;Level 1=covered call+cash-secured put,Level 2=+long call/put,Level 3=+价差/跨式/蝶式/铁鹰,官方文档从未列出裸卖 | [Alpaca 官方支持页:期权级别说明](https://alpaca.markets/support/what-option-levels-or-tiers-do-you-provide) |
| 是否支持 bracket/条件止损单(多腿) | **不支持**;多腿单只能整单撤销/替换,不能单独操作某条腿；社区反馈提交类似结构会报"complex orders not supported for options trading"错误 | [论坛帖:Bracket orders with options](https://forum.alpaca.markets/t/bracket-orders-with-options/13915) |
| 是否支持 stop / stop_limit(单腿) | 支持,但**仅限单腿期权订单**,多腿不支持 | [Options Trading 文档](https://docs.alpaca.markets/us/docs/options-trading) |
| 期权订单 Time-in-Force | 文档说明允许 `day` 或 `gtc`(取决于具体订单校验规则,不同文档页表述不完全一致,建议以下单前的API校验报错为准) | [Options Trading 文档](https://docs.alpaca.markets/us/docs/options-trading) |
| 行权/指派处理 | 纸面盘模拟真实行权流程;到期日默认自动行权价内(ITM)合约;若购买力不足会在到期前1小时内自动平仓;指派事件不通过websocket推送,需要轮询REST接口 | [Alpaca支持:期权行权与指派是什么](https://alpaca.markets/support/what-is-an-option-exercise-or-assignment) |
| 期权行情数据 | 底层数据来自OPRA;免费Basic计划的期权部分只有"指示性"报价;需要真实盘口/逐笔OPRA数据需订阅付费的Algo Trader Plus | [Real-time Option Data 文档](https://docs.alpaca.markets/us/docs/real-time-option-data) |
| 期权费用 | 无佣金,但有监管过手费:TAF $0.00329/张(仅卖方),ORF $0.02295/张(买卖都收) | [Alpaca支持:期权合约手续费](https://alpaca.markets/support/what-are-the-commission-fees-per-option-contract) |
| PDT(Pattern Day Trader)规则 | 2026-06-04起FINRA已取消$25,000最低权益的PDT规则,改为按日内风险动态管理的新框架;4倍日内购买力的最低权益门槛从$25,000降到$2,000 | [Alpaca博客:FINRA Retires the PDT Rule](https://alpaca.markets/blog/finra-retires-the-pdt-rule-introducing-alpacas-new-intraday-margin-framework/)、[The Intraday Margin Rule文档](https://docs.alpaca.markets/us/docs/the-intraday-margin-rule) |

**对我们账户的直接含义**：我们的 $103k 权益远超新规$2,000门槛,4倍日内杠杆和做空不受限；但期权只能做"防守型"结构(cash-secured put/covered call/价差/铁鹰),不能裸卖;任何多腿仓位的止损必须靠我们自己的调度任务主动监控和下平仓单,broker不会自动帮忙止损,过夜期间的尾部风险需要额外预算(例如到期前主动平仓,不依赖broker的自动ITM处理作为风控手段)。

---

## 3. 排名候选清单(最多5个,可在今天或周一上纸面盘)

> 前提:所有"决定性测试"必须先在本地1分钟/日线数据上跑完,确认样本外(尽量用2024-2026做样本外)依然有正的、经成本调整后的edge,再排单到纸面盘,不要跳过这一步直接实盘。

| 排名 | 策略 | 一句话规则 | 每日调度(ET) | 决定性测试 | 证据强度 |
|---|---|---|---|---|---|
| 1 | 现金担保虚值看跌 / put credit spread(周度) | 周一或周三卖出SPY或QQQ约3-5周后到期、20-30 delta附近的看跌;资金紧张则用价差代替全额担保 | 1个任务:每周固定1天10:00下单;另加1个任务:到期前1天15:30检查是否需要展期/平仓 | 用本地价格+VIX代理估算隐含波动率,对比cash-secured put与put credit spread的历史权利金/资金效率(1.6/1.7节方法) | 中高:PUT指数近40年历史+ERN 8年公开记录,但ERN的裸卖结构本账户不可用,需要改用价差,效果未经验证 |
| 2 | ORB多股票"Stocks in Play"(相对成交量过滤) | 用前一夜收盘后计算好的ADV,当日09:35(5分钟开盘区间形成后)对放量异常的股票做突破方向的多/空,收盘前平仓 | 2个任务:09:35扫描+开仓,15:55强制平仓检查 | 在本地1分钟线上完整复现giovannibrusco的滑点敏感性分析,并把标的换成我们自己的"stocks in play"筛选,看盈亏平衡滑点是否依然在2-3美分区间 | 中:原论文Sharpe 2.81,但作者自己2026-07承认单ETF朴素版几乎不赚钱,独立复现给出很薄的滑点安全边际 |
| 3 | TQQQ/QQQ 趋势+波动率过滤轮动 | 收盘前检查QQQ是否高于200日均线且已实现波动率低于阈值,决定明日持有TQQQ还是现金/短债 | 1个任务:15:45计算信号,用MOC或次日开盘单执行 | 用本地日线数据跑2016-2026全周期,重点看2022年的回撤表现,不能只看牛市CAGR | 中:多个第三方回测方向一致,但HFEA 2022崩溃是真实发生的公开教训,均线过滤有明确的滞后/whipsaw批评 |
| 4 | 隔夜效应+星期几过滤(组合) | 只在"隔夜历史上偏正"的星期(如周一到周二)做收盘买入/次日开盘卖出,周五到周一的隔夜跳过或反向 | 2个任务:15:58买入(仅特定星期),次日09:31卖出 | 本地1分钟线直接切15:59/09:31价格对,按星期几分组统计2016-2026净值曲线和t值,几分钟出结果,是免费的 | 低中:Alpha Architect认为隔夜异象扣成本后统计稳健性低;NSPY同类产品已退市;这是"最便宜、值得先测,但预期低"的候选 |
| 5 | 周一午后反转→单指数周度择时(改编版) | 每周一12:00记录SPY/QQQ相对开盘的收益方向,作为本周剩余交易日的持仓方向信号 | 1个任务:每周一12:00判断+调仓 | 本地数据回测2016-2026,同时必须与论文原版(截面多空组合)的Sharpe 1.77分开报告,因为这是我们自己的改编,不是论文直接结论 | 低中:论文本身是同行评审的,但从截面因子改编成单指数择时的转移效果完全未经验证 |

**未入围但可以低成本先验证、值得记录的**:1.5节的缺口回补/VWAP均值回归/首小时区间(证据太弱,先做免费的本地验证,不直接排单);1.2节噪声带动量(证据新但无独立复现,且需要的调度密度明显高于以上5个)。

---

## 4. 账户明确不能支持的策略,及原因

| 策略/变体 | 不能支持的原因 |
|---|---|
| ORB的NQ期货确认过滤器(独立复现里唯一被证明显著的版本) | Alpaca不提供期货交易;唯一测试过的替代品(QQQ盘前K线)已被证明是"安慰剂",不显著 |
| ERN式裸卖看跌/看涨(0DTE/1DTE) | Alpaca所有期权级别(含Level 3)都不支持裸卖/无担保空头期权,官方文档明确只到"价差类"结构 |
| 依赖broker原生bracket/止损保护的多腿期权策略(如自动止损的铁鹰) | Alpaca多腿单不支持挂钩条件单/OCO,只能整单撤销替换,止损必须自建调度逻辑,过夜/跳空风险broker不会兜底 |
| 需要亚秒级反应的noise-band/动量出场优化 | 题目本身排除了亚秒级延迟,Maróy论文里"出场方式优化"部分暗示对执行时机敏感,调度粒度匹配存疑,需要在决定性测试里专门检验分钟级调度是否会显著吃掉论文声称的edge |
| 依赖付费实时OPRA数据做出高质量期权定价决策的策略 | 我们当前只有Basic计划的"指示性"期权报价;要做真正的0DTE/短期价差定价,需要额外订阅Algo Trader Plus,这是一个需要用户/预算决定的成本,不是技术不可行,但目前未确认已订阅 |

---

## 5. 一句话总结

证据最扎实、且能直接在我们账户上落地的,是**期权卖方结构(cash-secured put / put credit spread)**——有近40年的Cboe指数级证据和一位公开8年记录的践行者,但那位践行者用的裸卖结构我们broker不支持,必须改用资金效率更高的价差,效果需要重新验证。**ORB**是被研究得最多、被独立复现得最认真的日内策略,但独立复现同时也暴露了它对滑点极其敏感、且原作者本人在2026年最新研究里承认单ETF朴素版几乎不赚钱——edge集中在"多股票+异常放量"这个具体设计上。**杠杆ETF轮动**证据方向一致但2022年的公开崩溃案例(HFEA)提醒必须把回撤测试放在CAGR之前看。**隔夜异象、星期几效应**代码实现成本几乎为零,值得优先拿来做"免费的证伪测试",但不该被当作主力仓位。**缺口/VWAP/首小时**这三类,坦白说,目前没有找到任何独立验证或可信净值曲线,不建议投入。

（本简报未修改仓库内其他任何文件,未运行任何代码或回测,未提交任何commit。）
