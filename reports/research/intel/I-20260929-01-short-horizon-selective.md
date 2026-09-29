# 情报简报 I-20260929-01：短时间线、少出手、高胜率高收益的策略/模型/因子

日期：2026-09-29。**本简报只做联网情报调查，不写代码、不跑回测、不改队列、不提交。** 按 `reports/research/intel/README.md` 的四问框架（新不新 / 有没有人验过 / 有没有人分享了实盘或模拟盘净值 / 在我们机器和账户上能不能跑）逐一过筛。

## 0. 用户的问题

> "有没有那种高频交易的策略或者模型或者因子…看起来都是比较低频比较宏观的？不一定是频率高，而是关注的时间线短，可以出手少，但是胜率高收益多的那种，你搜搜"

翻译成研究口径：**持有期短（几分钟到约5个交易日）、入场稀疏（由具体设置/催化剂触发）、扣除现实成本后胜率高且单笔收益有意义**的候选。优先 2020-2026 证据。

## 1. 方法与查询记录

用 `scripts/harvest_search.py run`（exa/web/github 三个渠道，`--site` 限定站点）执行了 **37 条查询**（含 2026-09-29 预检的 3 条），全部记录在 `reports/research/harvest/search-log.jsonl`，原始结果存于 `reports/research/harvest/raw/2026-09-29/`。用 `scripts/harvest_search.py fetch` 完整读取了 **13 篇主要来源全文**（另有约 20+ 篇通过 search 流程内的 jina/exa_fetch 阅读器读到摘要或全文，记在各条 raw jsonl 里），来源清单见 `reports/research/intel/sources/I-20260929-01/manifest.json`。中文站点检索（`--site zhihu.com`、`--site xueqiu.com`、微信公众号）大多被反爬拦截或返回无关结果（一条查询甚至返回了 Domino's Pizza 官网），能读到的中文材料只来自 exa 渠道的通用网络索引（发现报告网 fxbaogao.com 的国盛证券研报、10jqka.com.cn），不是站点限定检索的结果——如实记录这一检索盲区，而不是假装覆盖了中文渠道。

在写任何候选之前，对每个机制跑了 `uv run oc research directions check`，逐条核对 `reports/research/harvest/directions.jsonl` 里的既有记录，避免重复已判定的方向。

## 2. 逐候选情报卡

### 2.1 SPY/QQQ 盘中噪声带动量——post-2022/0DTE 时代持续性：本项目已否定，且被第三方独立复现进一步证实

**机制**：Zarattini-Aziz-Barbon "Beat the Market"（噪声带阈值 + VWAP/梯形止损 + 动态仓位）。

**作者报告**：2007-2024，年化 19.6%，Sharpe 1.33（[Concretum Substack 全文已读](https://concretumgroup.substack.com/p/beat-the-market-with-intraday-momentum)）。

**独立复现——这是本轮最重要的新证据**：Sheimy Paz (University of South Florida), *Out-of-Sample Evaluation of an Intraday Momentum Strategy for the S&P 500 ETF (SPY)*, SSRN 2026-08-19（[7290621](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7290621)，摘要全文已读）：用 IQFeed 1 分钟数据独立复现，样本内（2015-2024）Sharpe 1.34 与原文高度吻合，**但样本外（2024-05 至 2026-03，约两年）总回报只有 9.4%（买入持有 29.5%），Sharpe 骤降到 0.39**，作者明确讨论了市场微观结构变化、0DTE 期权爆发式增长等可能解释。

**与本仓库已有结论的关系**：本项目的 `dir:spy_noise_band_intraday` 早已被否定（2016-2026 全样本，作者自己口径下 gross 约 2.2%/yr，Sharpe 0.30，扣成本后为负）。这篇 2026-08 的独立复现是**同一被否定方向的加固证据**，不构成重开条件，因此**未新增条目**，只在此记录：本地否定结论和第三方独立复现方向一致。

**一个不一致的细节，如实记录**：Zarattini 本人 2025-04 在 LinkedIn（[原文](https://www.linkedin.com/posts/carlozarattini_heres-the-latest-update-on-the-intraday-activity-7325909248368939008-i3CU)）自称当月 +10.7% YTD vs 标普 -5%（高波动/下跌月份），单股 PnL 达 $1.60/股，滚动 1 年均值 $0.25/股"远超保守成本假设"。这是作者自报、未经审计的前向记录，和独立复现的"样本外 Sharpe 骤降"并不矛盾——凸性 payoff 策略本就在个别高波动月份表现突出，但不能代表整个样本外窗口的风险调整收益，两条证据都如实列出。

**结论**：不建议重新投入——已经是被否定+独立复现双重确认的方向。

---

### 2.2 个股层面"无消息大跌反转"（Chan 2003）—— 新方向，未在本仓库测过

**机制**：Wesley S. Chan, *Stock price reaction to news and no-news: drift and reversal after headlines*, JFE 70(2), 2003, 223-260（[ScienceDirect 摘要+导言已读](https://www.sciencedirect.com/science/article/abs/pii/S0304405X03001466)，ScienceDirect 显示 686 次引用）。用新闻标题数据库区分"有可识别公开消息"和"无消息但价格同样大幅波动"两组股票：**有坏消息的股票在随后最多12个月里显著负向漂移**（投资者对消息反应慢）；**无消息的大幅波动下个月出现显著反转**（投资者对无基本面支撑的价格波动过度反应），控制规模和账面市值比后依然显著，但**效应集中在小盘、流动性差的股票**，剔除低价股后减弱但未消失。

**情报核查**：`uv run oc research directions check "large stock price drop no news reversal individual stocks"` 未命中既有条目；已加入 `directions.jsonl`（`dir:no_news_price_shock_reversal_chan`，status: harvested）。本轮搜索只找到 2003 原文和两篇相关 SSRN 摘要（Savor 风格的《Stock Returns after Major Price Shocks》），**没有找到 2020 年代独立复现**，当前市场下的量级和持续性未经验证。

**我们能不能跑**：需要"当天是否有可识别新闻"的分类——我们已有 SEC 8-K 文本打分管线 + Alpaca PIT 新闻包（14,817 只标的）+ 日线数据，**不需要新数据源**。原始设计是月度持有期，不完全是"几分钟到5天"的短时线，但坏消息漂移这一腿可以先用 1-5 日持有期做更廉价、更选择性的子测试。

**执行性**：长仓兼容（买入无消息下跌股/回避无消息上涨股）；坏消息漂移腿若要完整捕获需要做空。

---

### 2.3 IPO 解禁期漂移——新方向，未在本仓库测过

**机制**：Laura Casares Field & Gordon R. Hanka, *The Expiration of IPO Share Lockups*, SSRN 2000（[摘要已读](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=205011)）。3,217 份解禁协议：解禁当周成交量永久性上升 40%，累计异常收益 **-1.8%**（统计显著），**在其10年样本中保持稳定，不会被快速修正**，风投持股的公司效应更强（VC 卖得更激进），约6%的解禁在到期前就被大额内部人抛售提前打破。

**情报核查**：`uv run oc research directions check "IPO lockup expiry short selling"` 未命中已有方向（一张 FINRA 空头回避清单假设卡提到过这个机制"合理但本轮未读到量化数字"）；已加入 `directions.jsonl`（`dir:ipo_lockup_expiration_drift`，status: harvested）。**没有找到2020年代独立复现**——25年前的样本，当前市场解禁日历透明度更高、VC二级市场更发达，量级可能已经变化，未经验证。

**我们能不能跑**：异常收益是**负**的（解禁期价格下跌），要把它变成 alpha，要么做空（需要空头授权，已标记待定），要么长仓兼容版——干脆避免/低配临近解禁的次新股多头仓位。数据缺口：确切的合同解禁日不在免费 PIT 源里，需要用"IPO 日 + 90/180天惯例"近似，或找免费的解禁日历网站。

---

### 2.4 指数增减样本效应——新方向，但证据本身就是负面结果（不建议投入）

**机制**：Robin Greenwood & Marco Sammon, *The Disappearing Index Effect*, Journal of Finance 80(2), 2025, 657-698（[摘要已读](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13410)，同行评审、已发表、附带复现代码，已有3次引用）。**这是命名并最早发现"指数效应"的同一团队自己做的最新测量**：标普500新增股票的异常收益从1990年代平均7.4%降到过去十年（约2014-2024）**不到1%**；剔除同样从大幅负收益降到2010-2020年间平均**只有0.1%**；其它指数家族也观察到同样的衰减。

**情报核查**：`directions check` 未命中已有条目，已加入 `directions.jsonl`（`dir:index_reconstitution_disappearing_effect`，status: triaged，附带 triage 四问）。**结论直接写在摘要里**：最权威、最新的来源自己证明这条路已经不值得测——不到1%的量级低于任何现实成本调整后的门槛，**不建议本地测试**，只做记录以防以后重复调研。

---

### 2.5 PDUFA/FDA 事件——本仓库已有结论（evidence_too_weak），新增的叙事性数字不改变结论

**已有条目**：`dir:fda_calendar_binary_events`，status: evidence_too_weak，理由"没有免费的前瞻性FDA日历数据源；证据几乎全是叙事性的，没有回测；payoff结构是二元/类期权的，和我们的工具不匹配"。

**本轮新读到的数字**（[bioradar.io，2026-07 更新](https://bioradar.io/how-biotech-stocks-move-around-fda-decisions/)，方法论透明：67-72个PDUFA事件，2025-05至2026-09追踪，价格取自Yahoo Finance）：决策日平均 **-1.7%**，5日平均 **-4.5%**，但只有52%当天收跌（即胜率略低于50%）；决策前30天平均run-up +2.3%；**获批组**：30天run-up +14.2%，决策日几乎持平(-0.1%)，5日+0.1%；**CRL（拒批）组**：run-up -14.7%，决策日**-13.7%**，5日**-33.1%**；单事件最大波动 +41.5% / **-70.7%**。样本小（67-72个事件）、非同行评审、数据源是免费但非官方的初创公司站点。**这组数字没有改变既有结论**（仍然缺一个可靠的免费前瞻日历数据源，payoff仍然是二元的），因此**未新增条目**，只在此记录，并用于第4节"高胜率隐藏尾部风险"的例证。

---

### 2.6 财报后延续/反转（大跳空+放量过滤）——探索后证据不足，无新增条目

**已有条目**：`dir:pead_classic_sue_microcap_decay`（经典SUE版本，evidence_too_weak，"剔除微小盘后t值降到1.43，不显著"）。

本轮搜索了"大跳空+放量过滤"这个和经典SUE不同的变体（brief family 2 明确要求区分开），读到的是 Cambridge JFQ 论文摘要（*Earnings Autocorrelation and the Post-Earnings Announcement Drift*）和几个 GitHub PEAD 复现仓库（[mcravi8/PEAD-mini-WRDS](https://github.com/mcravi8/PEAD-mini-WRDS)），**没有找到量化的、专门针对"大跳空+放量"这个变体的2020年代独立证据**——搜索结果要么是经典SUE的变体，要么是不含具体数字的复现代码仓库。诚实结论：**这个子方向本轮探索后仍然证据不足，不新增条目**，如果以后要测，需要先找到一篇专门量化"跳空幅度×成交量"过滤效果的论文，而不是自己发明变体。

---

### 2.7 个股（非指数ETF）Connors RSI(2)/IBS 短线反转——探索后仍只找到 ETF/指数证据

Brief family 4 明确要求：已知 `dir:etf_dip_reversion_ibs_connors` 在 SPY/QQQ 上 0/24、0/12 被否定，**要求换成个股或未覆盖的品种/时段**。本轮搜索（QuantifiedStrategies、backtestedstrategies.com）**再次只找到 SPY/指数层面的回测**（[quantifiedstrategies.com/connors-rsi 全文已读](https://www.quantifiedstrategies.com/connors-rsi/)：2日回看 CRSI<15/>85 在 SPY 上 profit factor≈2.08，288笔交易），**没有找到任何独立的、量化的、针对单只个股的 Connors RSI(2)/IBS 回测或实盘记录**。诚实结论：这个方向本轮没有找到可执行的新证据，不新增条目。

---

### 2.8 0DTE/1DTE 期权——已有账户结论未变，新读到的数字加固"散户亏钱"这条红旗

已有的 2026-09-18 简报（`intel-intraday-and-options-runnable-2026-09-18.md`）已经详细覆盖了 ERN 的公开8年记录和 Alpaca 不支持裸卖的账户约束。本轮新读到两篇更硬的证据：

- Beckmeyer, Branger & Gayda, *Retail Traders Love 0DTE Options... But Should They?*，FoFI 2024 working paper（[全文已读，32页](https://wp.lancs.ac.uk/fofi2024/files/2024/04/FoFI-2024-146-Leander-Gayda.pdf)）：2021-02至2023-09，散户在标普500期权（75%以上是0DTE）**平均每天亏损 $241,000**；2022-05引入每日到期日历以来，这个数字涨到**平均每天 $350,000**。单腿交易、需要预付权利金的交易、高隐含波动率期权是亏损主因；多腿交易和捕获波动率/跳跃风险补偿的交易明显更赚钱。
- Reddit 用户对 ERN 式"卖1DTE 5-delta SPX看跌"策略的1990年至今回测（[全文已读](https://www.reddit.com/r/options/comments/1gr7kwj/selling_options_on_sp500_backtest_from_1990_an/)）：**用VIX直接当隐含波动率**（不加偏度）做Black-Scholes定价，30年累计**亏损约一半本金**；加5%偏度溢价后转为-20%；只有加到10%偏度溢价才转为+50%累计（约1.3%年化）——一个"裸卖权利金"策略对波动率偏度假设极其敏感的具体证明。

这两条不改变已有的账户结论（Alpaca 不支持裸卖，只能用资金效率更低的现金担保或价差），但为第4节的"高胜率隐藏尾部风险"提供了扎实的一手数字。

---

## 3. 排名候选表（最多10个）

| 候选 | 证据强度 | 2020年后存活情况 | 我们的可执行性 |
|---|---|---|---|
| SPY/QQQ噪声带盘中动量 | 高（同行评审+第三方独立复现，SSRN 7290621） | **不存活**：样本外Sharpe从1.34降到0.39，跑输买入持有；本地早已否定 | 已否定，不建议重开 |
| 个股无消息反转（Chan 2003） | 中（同行评审，686次引用，但25年前样本） | 未知——无2020年代独立复现 | 是，数据已有，长仓兼容 |
| IPO解禁期漂移 | 中（学术论文，25年前样本，效应机制合理） | 未知——无2020年代独立复现 | 部分：长仓兼容版可行，完整捕获需做空 |
| PDUFA/FDA事件 | 弱（非同行评审，小样本67-72事件） | 有数据但结论仍是"前瞻日历数据源缺失" | 否（已有结论：数据源+payoff结构均不匹配） |
| 指数增减样本效应 | 高（同行评审JoF 2025，作者自证效应已消失） | **明确不存活**：从7.4%降到<1%/0.1% | 不建议：证据自证不值得 |
| 财报大跳空+放量PEAD变体 | 弱（无专门量化来源） | 未知 | 未探明，证据不足以判断 |
| 个股Connors RSI(2)/IBS | 无（只找到ETF证据） | 不适用 | 未探明，无证据支持个股版本 |
| 0DTE/1DTE期权（散户视角） | 高（学术论文，交易所级数据） | 存活但方向相反：散户系统性亏钱（日均$241k-$350k） | 否（我们broker不支持裸卖，散户亏钱恰恰是"别人赚我们的钱"这条路的反面证据） |

---

## 4. 最便宜的决定性测试（3条，各附placebo和止损规则）

**测试1：IPO解禁期漂移的本地首测**
- 数据需求：用 IPO 日期 + 90/180天惯例近似解禁日（精确合同解禁日无免费PIT源），或找免费解禁日历站点；已有日线数据 `data/features/daily` 做价格/成本侧。
- 设计：2016-2026，在近似解禁周测CAR，用已有日线几分钟内可以跑完。
- Placebo：把同一个CAR窗口整体平移 ±60个交易日，若真实效应存在，平移后的窗口不应有类似幅度的负收益。
- 止损规则：若平移后的placebo产生同等量级的负收益（即效应对日期不敏感），或扣除个股实际成本（2-5bp/边）后CAR不显著，直接否定，不进入信号卡阶段。

**测试2：无消息大跌反转（Chan 2003）本地首测——坏消息漂移腿优先（更短、更廉价）**
- 数据需求：SEC 8-K文本打分管线 + Alpaca PIT新闻包（有）+ 日线数据（有），不需要新数据源。
- 设计：2020-2026，用"当天有无可识别公开新闻"给单日大幅波动（如|收益|>2倍标准差）分组，先测坏消息组的1-5日持有期漂移（比原论文的12个月版本更贴近本轮"短时线"要求，也更便宜）。
- Placebo：打乱新闻标记（即在不改变价格波动分布的前提下随机分配"有/无新闻"标签），检验新闻条件本身是否比通用超调反转带来增量。
- 止损规则：净值扣除个股实际成本（2-5bp/边）后，近期窗口（2024-2026）Sharpe 不能达到本项目K1门槛1.19，直接否定。

**测试3：Connors RSI(2)/IBS家族——从ETF换成个股，复用已冻结的G1-G5协议**
- 数据需求：已有日线数据，直接复用 `dir:etf_dip_reversion_ibs_connors` 已经搭好的G1-G5冻结协议和候选集，只把信号标的从SPY/QQQ换成流动性最好的50-100只个股（排除杠杆ETF）。
- 设计：2020-2026同一套placebo和显著性检验，直接套用已有工具链，成本极低。
- Placebo：复用已有的随机日期placebo（这套已经在ETF版本里验证过其区分力）。
- 止损规则：若0/N个候选通过G1-G5（和ETF结果一致），直接否定整个IBS/RSI(2)家族的个股版本，正式关闭这条线，不再重复搜索"换个标的试试"。

---

## 5. 为什么"高胜率"经常掩盖负偏度——如实说明

三条一手证据，不是泛泛而谈：

1. **裸卖期权/短波动率的爆仓史**：本轮读到的Reddit回测显示，用VIX直接当隐含波动率（不加偏度溢价）卖1DTE 5-delta SPX看跌，1990年至今**累计亏损约一半本金**——"卖权利金=稳定小赚"的直觉在没有偏度调整时是错的；即便加上偏度调整变正，也只是约1.3%年化，远低于"高胜率"的直觉暗示。2026-09-29已否定的`dir:vix_term_structure_short_vol`（一个50/50 SMH/QQQ持有跑赢每一个候选）和2026-09-18简报里ERN"2025-04波动飙升期间尽管有止损限价单仍然亏损"的记录，是同一类教训的两个独立案例。
2. **散户0DTE系统性亏钱**：FoFI 2024论文（Beckmeyer/Branger/Gayda）用交易所级数据证明，散户在0DTE期权上日均亏损从$241k（2021-2023）升到$350k（2022年每日到期日历后）——这是"看似有很多小赢面"的期权交易结构性地把钱转移给做市商/对手方的直接证据，高频次小额"胜率"和整体净亏损可以同时为真。
3. **PDUFA二元事件的尾部**：bioradar.io数据显示，FDA决策日52%收跌（胜率略低于50%），但获批和CRL两组的分布完全不对称——获批组5日几乎不动(+0.1%)，CRL组5日**-33.1%**，单事件最大跌幅-70.7%。"平均胜率接近50%"这个数字本身完全掩盖了背后极不对称的payoff结构：少数几次-70%的尾部足以吃掉大量正常年份的小赚。
4. **RSI(2)/IBS家族在本项目自己的否定记录里**：`dir:etf_dip_reversion_ibs_connors`已经记录过"最佳anchor Sharpe 1.50 vs 2.0门槛"，胜率看起来体面，但deflated Sharpe（24次试验调整后）只有0.92——多重检验本身就会把"看似高胜率"的策略洗出来，这是偏度问题之外的另一层陷阱，两者经常同时出现在被过度挖掘的短线均值回归策略里。

共同教训：**报告"胜率"数字时必须同时报告平均盈利/平均亏损的比例和尾部分布，否则"高胜率"这个词本身就是一种误导性摘要**；这也是为什么第3节的排名表和第4节的止损规则都要求扣成本后的Sharpe和显著性检验，而不是单独看胜率。

---

## 6. 未覆盖 / 检索盲区（如实记录）

- 中文站点（知乎、雪球、微信公众号）的站点限定检索基本被反爬拦截（`camoufox`/`trafilatura`模块缺失），只能靠 exa 渠道的通用索引间接读到零星中文内容（国盛证券研报摘要、10jqka.com.cn一篇文章），**不构成对中文论坛/公众号观点的系统覆盖**，如果用户认为中文渠道信息密度更高，需要先解决爬虫依赖（安装`camoufox`/`trafilatura`或改用其他阅读器）才能真正覆盖这块。
- 加密货币：只做了一次搜索（family 7 "只有证据格外扎实才做"），结果是零星的GitHub机器人仓库，没有找到证据格外扎实的候选，未继续深挖，符合brief的"only if unusually strong"门槛。
- 微观结构类（opening drive/VWAP反转、52周新高放量突破、停牌反转）三个方向的搜索结果全部是零售博客/screener页面，没有同行评审或可信净值曲线，已在2026-09-18简报里有过同样结论，本轮再次确认没有新证据，不重复记录到候选表。

---

（本简报未修改仓库内除 `reports/research/harvest/directions.jsonl`、`reports/research/harvest/search-log.jsonl`、`reports/research/harvest/raw/2026-09-29/*` 和本目录下文件外的任何文件，未运行任何回测，未提交任何commit。）
