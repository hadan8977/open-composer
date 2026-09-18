# 情报简报：免费/低成本另类数据里还有证据的信号（2026-09-18）

- 范围：回答"哪些免费或很便宜的数据源，在美股上有第三方验证过的可交易 alpha 证据，其中哪些已经被别人做成了公开分享的策略"。
- 纪律（按 `reports/research/intel/README.md` 的四问）：每类信号先答"新不新 / 有没有人验过 / 有没有人已经做出来分享 / 在我们这台机器上能不能跑（3.9GB、无 GPU、免费/极低成本预算）"，再给最便宜的决定性测试。
- 已知背景：我们已有 Form 4（2016–2026）、13D/13G、FINRA 双月空头余额、Alpaca/Benzinga 新闻标题表、美股日线+分钟线（2016–2026）的点时表；且已经在自己的数据上**证伪**：内部人买入作为动量层的门、新闻注意力门、元标注仓位分层、13D 事件漂移、空头回避清单，以及内部人买入作为独立月频策略（跑赢同尺寸随机对照 82bp/月 t=3.1，但年化只有 9.5%、从未跑赢 SPY——见 `reports/research/iterations/h20260917_01_insider_independent/report.md`）。
- 写作规则：每条声明标注来源 URL 和日期；区分"作者自称"与"独立复现"；没人复现的直接写"无独立复现"。全部为公开网络检索结果，未读取任何 `.env` 或密钥文件。

---

## 1. 逐类信号盘点

### 1.1 SEC 结构化申报文本：XBRL 财务异常 + 申报文本变更（"Lazy Prices"）

| 项目 | 内容 |
|---|---|
| 信号 | (a) 传统财务报表异常（应计项目、F-Score）；(b) 10-K/10-Q 逐句文本变更（新增/删除的句子），做多"未改写"、做空"大幅改写"的公司 |
| 最强已发表结果 | **Lazy Prices**（Cohen, Malloy, Nguyen, *Journal of Finance* 2020）：1995–2014 美股全体上市公司，"改写"做空/"未改写"做多的多空组合月均 alpha 达 **188bp/月（年化超过 22%）**，且公告日当天没有异常反应（说明是缓慢扩散、未被套利），[Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12885)（2020-06）、[NBER w25084](https://www.nber.org/papers/w25084)（工作论文版）。作者自称的结果，纳入交易成本前 |
| 独立复现 | 未检索到 2014 年之后样本的独立复现；某回测网站的实现提到"2019 年后的复现遇到困难"（[paperswithbacktest.com/strategies/lazy-prices](https://paperswithbacktest.com/strategies/lazy-prices)，访问于 2026-09-18），但这是二手转述而非同行评审复现，**无法确认样本外仍然成立** |
| 2024–2026 是否存活 | **未知，无人公开验证**。原文样本止于 2014，这正是我们要做的"最便宜决定性测试" |
| 应计/F-Score 侧证 | Piotroski F-Score 九项里只有低应计一项在 21 世纪仍然有效，整体 F-Score "在 Piotroski 原样本外已经不再有效"（[blog.portfolio123.com](https://blog.portfolio123.com/why-piotroskis-f-score-no-longer-works/)，访问于 2026-09-18；[seekingalpha.com/article/4407684](https://seekingalpha.com/article/4407684-why-piotroskis-f-score-no-longer-works)，访问于 2026-09-18）。这是多篇二级来源的一致说法，**未见严谨的同行评审 2020 年代复现**，应视为"作者/从业者共识声称"而非独立验证 |
| 获取成本/API/PIT | 完全免费：SEC EDGAR Full-Text Search（[sec.gov/edgar/search](https://www.sec.gov/edgar/search/)）、Financial Statement Data Sets 季度批量 zip（自 2009 起，[sec.gov/data-research/.../financial-statement-data-sets](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets)，访问于 2026-09-18）。EDGAR 接受时间戳本身就是 PIT，没有回填问题 |
| 最便宜的决定性测试 | 不需要 ML：用我们已有的 EDGAR 访问能力，对同一 CIK 连续两次 10-K/10-Q 做逐句 diff（Jaccard 或编辑距离），生成"变更幅度"分位特征，直接跑我们标准的月频多空评估管线（不需要新基础设施，属于纯文本处理，3.9GB 内存足够）。这是"先复现别人已发表的结果"，不是发明新变体 |
| 红旗 | 原样本止于 2014，且该做法一旦被写进教科书/量化课程（[quantt.co.uk](https://www.quantt.co.uk/resources/lazy-prices-snowflake-cortex-ai) 等多篇二级转述），大概率已被部分套利；F-Score 类经典财务异常的普遍共识是"已经不好使了" |

### 1.2 Form 4 内部人交易细分（职务/集群/机会型/10b5-1）

| 项目 | 内容 |
|---|---|
| 信号 | 把内部人买入按：董事/高管/10% 股东角色、是否集群（同窗口多人）、机会型 vs 例行型（Cohen-Malloy-Pomorski, CMP）、是否 10b5-1 预设计划（应排除）细分 |
| 最强已发表结果 | CMP《Decoding Inside Information》（*Journal of Finance* 2012；[SSRN 1692517](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1692517)、[NBER w16454](https://www.nber.org/system/files/working_papers/w16454/w16454.pdf)）：剔除"例行型"后，"机会型"买入的价值加权多空组合月均异常收益 **82bp**，例行型基本为零。原始样本约到 2010 年代初 |
| 独立复现（关键，含衰减幅度） | 后续扩展样本至 **2024 年**的复现研究发现：**因子调整后的机会型 alpha 从约 1.2%–1.6%/月降到约 0.3%–0.4%/月，降幅 60%–70%**（多个检索到的二手转述一致给出这一数字，但未定位到可直接引用的单一论文标题/URL，只能标注为"多篇二手来源转述的样本扩展结果"，建议按"作者+跟随者合并声称"对待，而不是标注为强独立复现）。另有 2025-12 的工作论文《The Death of Insider Trading Alpha: Most Returns Occur Before Public Disclosure》（Ozlen & Batumoglu，[SSRN 5966834](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5966834)，2025-12）称**70%–80% 的内部人交易 alpha 在公开披露前就已经消散**，即公开 Form 4 之后能抓到的部分本就有限——这是一条重要的、独立于 CMP 团队的补充证据，但同样是作者自称，未见第三方复现 |
| 2024–2026 是否存活 | 上述文献均指向"存活但已大幅衰减"；我们自己 2026-09-18 的独立测试（`H-20260917-01`）在**最不流动分段 + 集群买入 + 1 个月持有**这一格上，相对同尺寸随机对照拿到 **+82bp/月，t=3.1**——数量级与 CMP 原始论文的 82bp 完全吻合，可以理解为"信号仍在，但集中在小微盘"，与文献里"信息不对称大的小盘股信号更强"的一致说法吻合 |
| 获取成本/API/PIT | 我们已经有该数据源（Form 4 XML 本身含 isDirector/isOfficer/isTenPercentOwner 字段，2023-04 起还新增了 10b5-1 计划勾选框，[SEC 2022 年 10b5-1 修订规则]，无需新增抓取，只是没解析进特征表——见下方第 4 节直接回答） | 
| 最便宜的决定性测试 | 不需要新数据：重跑 `H-20260917-01` 的特征管线，加入 (a) 角色权重、(b) 排除 10b5-1 勾选交易、(c) 加空头腿（机会型卖出） |
| 红旗 | 我们自己的检验已经证明"月度调仓、纯做多、不分角色"这个实现方式跑不赢 SPY；文献衰减到 0.3-0.4%/月说明即便做对了，绝对收益空间也有限，容量小（集中在小微盘） |

### 1.3 13F 持仓复制（Clone Portfolio）

| 项目 | 内容 |
|---|---|
| 信号 | 复制 13F 披露的机构持仓（尤其是高集中度/高换手基金），按季度调仓 |
| 最强已发表结果 | Schroeder & Posch，《Outperforming the Market: Portfolio Strategy Cloning from SEC 13F Filings》（2024-03，[SSRN 5399672](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5399672)）：2013–2023 年超过 15 万个组合，按披露日再平衡的复制组合"跑赢标普 500 24.3%（年化风险调整后）"。作者自称 |
| 独立复现 | **未检索到独立复现**，这是单一团队（2 位作者）的 SSRN 工作论文，未见被其他团队重复；Quantpedia 收录了同类"Alpha Cloning"策略（[quantpedia.com/strategies/alpha-cloning-following-13f-fillings](https://quantpedia.com/strategies/alpha-cloning-following-13f-fillings)，访问于 2026-09-18），但页面本身也是转述学术文献，不构成独立样本外验证 |
| 2024–2026 是否存活 | 不明，上述论文样本到 2023 年 |
| 获取成本/API/PIT | 官方免费批量数据：SEC Form 13F Data Sets（[sec.gov/data-research/.../form-13f-data-sets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets)）。**关键红旗：13F 有约 45 天披露滞后**（季度末后 45 天内申报），这是结构性的、无法通过更快抓取解决的滞后（多篇来源一致确认，例如 [cxoadvisory.com](https://www.cxoadvisory.com/miscellaneous/form-13f-clone-portfolio-performance/)，访问于 2026-09-18）。PIT 本身没问题（申报日公开可查），但"信息新鲜度"先天就差 |
| 最便宜的决定性测试 | 用免费 13F 批量数据 + 我们已有的价格表，复制"高集中度机构"组合，检验按披露日/45天滞后调仓后是否还有超额——这本质是在验证"滞后是否已经把 alpha 吃光"，预期大概率是否定 |
| 红旗 | 45 天滞后是文献公认的老问题；免费复制工具（WhaleWisdom 等）已经存在多年，若真有稳定 alpha，早该被套利掉；唯一的正面证据来自未经独立复现的单篇论文 |

### 1.4 13D/13G：换个用法（维权持仓的长期效应，而不是短期漂移）

| 项目 | 内容 |
|---|---|
| 信号 | 13D 维权举牌后，跟随维权基金的**长期**（1–5 年）持仓，而不是申报后的短窗漂移 |
| 最强已发表结果 | Brav, Jiang, Partnoy, Thomas，《Hedge Fund Activism, Corporate Governance, and Firm Performance》（*Journal of Finance* 2008；[Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2008.01373.x)）：2001–2006 年数据，13D 申报前后 20 日买入持有异常收益约 **6.0%–7%**，且**后续 5 年不发生反转**（即长期跑赢是真实的，不是短期反应过度）。作者自称，但该文是维权对冲基金研究里被引用最多的论文之一 |
| 独立复现 | 该文长期以来被后续多篇维权基金文献引用和部分复现其"公告效应不反转"的定性结论（[NBER w17517](https://www.nber.org/system/files/working_papers/w17517/revisions/w17517.rev0.pdf) 等系列后续论文），可视为**学术界内广泛认可但集中于同一批作者及合作者**，非完全独立的第三方复现 |
| 2024–2026 是否存活 | 不明，样本止于 2006；但我们自己的数据已经证实了该文献里最关键的一个组成部分——见下方"重要交叉证据" |
| **重要交叉证据（我们自己的数据，2026-09-18）** | `H-20260916-05`（13D 事件漂移）显示：13D 申报公开当天的超额收益是真实且稳健的（**+1.73%，t=4.15，787 个事件，十年三段都显著**），问题只是**这笔钱在我们能够下单之前（次日开盘）就已经被定价完了**——次日开盘后再持有 20/60 个交易日，超额转负（-0.39%/-1.07%）。这恰好印证了 Brav 等文献的机制：**真正的钱在"参与/跟随维权活动本身"（长期持有campaign期间），不在"看到申报后抢跑几十个交易日"** |
| 获取成本/API/PIT | 零新增成本，复用我们已有的 13D/13G 点时表 |
| 最便宜的决定性测试 | 不追加数据：把 `H-20260916-05` 的持有期从 20/40/60 个交易日改成 6/12/24 个月，并按 Item 4（是否明确提出维权诉求，而非被动持股）过滤申报人，重跑同一批评估脚本 |
| 红旗 | 维权基金数量少、目标公司数量少，样本量天然小；长期持有会引入更多幸存者偏差和行业/风格暴露，需要更强的对照组 |

### 1.5 空头兴趣 + 借券费率 + 日度做空成交量 + 挤压策略

| 项目 | 内容 |
|---|---|
| 信号 | (a) 双月空头余额/流通股比例、days-to-cover；(b) 借券费率（cost-to-borrow）；(c) 逐日做空成交量（Reg SHO）；(d) 挤压策略 |
| 最强已发表结果 | Asquith, Pathak, Ritter（2005，[NBER w10434](https://www.nber.org/system/files/working_papers/w10434/w10434.pdf)）：空头利息在**最小市值股票**里对未来收益有显著预测力（做空信息在大盘股里较弱）。Boehmer, Jones, Zhang，《Which Shorts Are Informed?》（*Journal of Finance* 2008）：**逐日做空成交量**（不是双月空头余额）比普通交易更能预测未来收益，是"知情卖空"（[top1000funds.com PDF](https://www.top1000funds.com/wp-content/uploads/2011/08/Which-shorts-are-informed.pdf)）。这两篇都是学术界公认的经典，多次被后续文献引用/复现其方向性结论 |
| 独立复现 | 上述两篇本身已经是被广泛引用、方向一致的经典发现（"全球大部分市场空头都能预测收益"，[academic.oup.com/raps](https://academic.oup.com/raps/article-pdf/13/4/691/53403664/raad007.pdf)），可视为有相当程度的独立复现，但都是**用逐日做空成交量或空头余额本身**，不是我们已经测过的"用双月空头余额做回避清单叠加层"这种用法 |
| **重要交叉证据（我们自己的数据，2026-09-18）** | `H-20260916-07` 做了非常严格的分解：宽口径下"空头比例"最高最低五分位的 21 日利差看起来极强（-0.98%，**t=-6.27**，15 次预登记检验里唯一过 BH-FDR 的），但把空头股数在同日跨股票随机打乱后仍能复现真实效应的 **81%（21日）/65%（5日）**；纯粹按"1÷63日日均成交量"排序（完全不看空头）能复现 **86%/52%**。**结论：这个信号里值钱的是分母（流动性/换手率），不是分子（空头持仓）——真正能归因于空头信息的残差只有 21 日 -0.18%、5 日 -0.08%，且未单独通过显著性检验**。这与 Boehmer-Jones-Zhang 的机制吻合：**双月空头余额（存量快照）本身信息含量有限，真正有信息的是逐日做空成交量（流量）**，而我们此前一直没有逐日做空成交量数据 |
| 借券费率/挤压 | 常见免费借券费率来源：**iBorrowDesk**（聚合 Interactive Brokers 借券费率和可借数量，[iborrowdesk.com](https://www.iborrowdesk.com/)，访问于 2026-09-18）、IBKR 自己的 Securities Lending Dashboard（[interactivebrokers.com](https://www.interactivebrokers.com/en/trading/securities-lending-dashboard.php)，2023-07 上线）。挤压策略方面，从业者共识是"**单独用高空头利息做逆势挤压策略通常会亏钱**，因为你是在买入市场有充分理由不看好的股票"（[tradingstrategiesdaily.com](https://tradingstrategiesdaily.com/p/short-squeeze-trading-strategy-backtest-do-high-short-interest-and-days-to-cover-predict-explosive-r)，访问于 2026-09-18），**无严谨学术验证支持"挤压策略"本身可交易**，多为从业者/数据商营销内容 |
| **免费的逐日做空成交量数据（新发现，建议纳入候选）** | **FINRA Daily Short Sale Volume Files**：免费、逐日、覆盖 NMS 全部交易所报告（Consolidated NMS 文件历史回溯到 **2018-08-01**），字段为 日期/代码/空头成交量/总成交量/市场，可通过网页、批量文件或 Query API 获取（[finra.org/finra-data/.../daily-short-sale-volume-files](https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files)，[文件格式说明 PDF](https://www.finra.org/sites/default/files/DailyShortSaleVolumeFileLayout.pdf)，访问于 2026-09-18）。这与我们已有的"双月空头余额"是**不同粒度的数据**，直接对应 Boehmer-Jones-Zhang 的机制 |
| 获取成本/API/PIT | FINRA 双月空头余额、日度做空成交量文件全部免费；iBorrowDesk 网页可看历史但**未见公开免费批量 API**（红旗：可能没有 PIT 批量历史，需要自己爬取积累） |
| 最便宜的决定性测试 | 用免费的 FINRA 逐日做空成交量文件（2018-08 起），复现 Boehmer-Jones-Zhang 的核心检验（做空成交量占比分组的次日/次周收益），并与我们已经跑过的"双月空头余额"结果对比，看信息含量是否明显更强 |
| 红旗 | iBorrowDesk 等借券费率源缺乏可验证的免费历史批量下载；挤压类"策略"证据薄弱，主要是数据商/自媒体内容，不建议投入 |

### 1.6 期权衍生信号（put/call 比率、IV 偏斜、异常期权活动、GEX）

| 项目 | 内容 |
|---|---|
| 信号 | put/call 成交量比率、隐含波动率偏斜（skew/smirk）、异常期权活动、做市商 Gamma 敞口（GEX） |
| 最强已发表结果 | Pan & Poteshman，《The Information in Option Volume for Future Stock Prices》（[NBER w10925](https://www.nber.org/system/files/working_papers/w10925/w10925.pdf)）：1990–2001 年，买方新开仓 put/call 比率最低组合跑赢最高组合次日 40bp+，次周 1%+，来源是期权交易者掌握的非公开信息。Xing, Zhang & Zhao（隐含波动率偏斜，[rice.edu PDF](https://www.ruf.rice.edu/~yxing/option-skew-FINAL.pdf)）：1996–2005 年，偏斜最陡组合跑输最平组合 **年化 10.9%**（Fama-French 三因子调整后），预测力可持续至少 6 个月 |
| 独立复现（关键红旗） | Quantpedia 明确记录了一个**非常重要的反例**：某只股票 put/call 比率的收益预测力，在**一次内部交易被捕并逮捕后突然消失**——多空周度 alpha 从盘前 0.24%/0.23% 直接跌到盘后 -0.04%/-0.01%（[quantpedia.com/how-common-is-insider-trading-evidence-from-the-options-market](https://quantpedia.com/how-common-is-insider-trading-evidence-from-the-options-market/)，访问于 2026-09-18）。**这意味着历史上"期权异常活动"信号里，至少有一部分文献验证过的样本，其信息来源就是字面意义上的内幕交易，一旦执法打击就消失**——这是一条独立于原作者的、非常有说服力的证伪/警示证据 |
| 2024–2026 是否存活 | GEX / 做市商 Gamma 敞口类信号目前**几乎全部证据来自数据商营销内容**（SpotGamma、FlashAlpha、InsiderFinance 等，[spotgamma.com](https://spotgamma.com/gamma-exposure-gex/)、[flashalpha.com](https://flashalpha.com/articles/what-is-gamma-exposure-gex-explained) 等，访问于 2026-09-18），**未检索到同行评审的独立学术验证**，唯一学术引用是 Bouchaud & Bonart（2018）关于对冲流的价格冲击，属于机制性研究而非策略回测证据 |
| 获取成本/API/PIT | 免费/极便宜的期权数据源仅能看当前链（CBOE、Yahoo Finance、Market Chameleon 免费但**无批量历史下载**）；有历史批量的都不便宜：ORATS 起价 $99/月、Polygon.io 期权 $79+/月起、CBOE DataShop 端到端 $500/月起、历史临时请求 $400/次（[flashalpha.com/articles/best-options-data-apis-2026](https://flashalpha.com/articles/best-options-data-apis-2026)，访问于 2026-09-18）。**PIT 红旗：免费期权数据源普遍不提供可回测的逐日历史链，只有实时快照**，这直接违反我们"没有 PIT 历史就不能回测"的硬性要求 |
| 最便宜的决定性测试 | 在无法获得免费历史期权数据的前提下，没有低成本的决定性测试可做 |
| 红旗 | (1) 免费/低成本源没有可回测的 PIT 历史；(2) put/call 类信号的证据里混有真实内幕交易的痕迹；(3) GEX 类证据主要来自卖数据/卖工具的商业机构，**没有独立学术验证** |

### 1.7 散户情绪（Reddit/WSB、StockTwits、Google Trends）

| 项目 | 内容 |
|---|---|
| 信号 | WSB/StockTwits 提及量、情绪分类；Google 搜索量指数（GSVI） |
| 最强已发表结果 | 2021 年 GameStop 事件期间，WSB 情绪与 GME/AMC 收益存在 Granger 因果关系（多篇论文，例如 [aclanthology.org/2021.finnlp-1.4](https://aclanthology.org/2021.finnlp-1.4.pdf)）。Google Trends 早期研究（Da, Engelberg, Gao 等风格）称高搜索量预测短期上涨后反转 |
| 独立复现（关键：post-2021 证据） | 用 ChatGPT 标注情绪的最新研究发现，Reddit 情绪与股价"仅有弱相关性"，与 2021 年狂热期的强预测力形成对比（[arxiv 2507.22922](https://arxiv.org/abs/2507.22922)，2025-07）；另一批 2024-2025 的研究发现"情绪是收益的**反向**指标"而非正向指标（[sciencedirect.com/.../S2405918825000212](https://www.sciencedirect.com/science/article/pii/S2405918825000212)）。Google Trends 方面，用不同时段数据复现发现**高搜索量对应负收益**，与早期论文方向相反（多篇二手来源转述，一致指向"跨样本不稳定"）；即使在原始论文里，**扣除交易成本后策略也不再盈利**（[medium.com/analytics-vidhya](https://medium.com/analytics-vidhya/how-to-predict-stock-returns-using-google-search-volumes-78e2be3be7c2)，访问于 2026-09-18） |
| 2024–2026 是否存活 | **明确证据显示 2021 年之后边际消失或反转**，多篇独立团队的复现方向不一致 |
| 获取成本/API/PIT | Reddit 官方 API 目前已收费且限制严格；StockTwits 有限免费但覆盖有限；Google Trends 免费但只有**周度、相对值、无法拿到绝对搜索量的历史 PIT 快照**（Google 会不定期重新缩放历史数据，存在轻微的非 PIT 风险） |
| 最便宜的决定性测试 | 不建议投入——文献已经给出足够多相互矛盾的样本外结果 |
| 红旗 | 样本外方向不一致（有的说消失、有的说反转）；原始论文本身扣成本后就不盈利；数据获取端本身也在变贵/变难（Reddit API 收费） |

### 1.8 财报电话会 + 8-K/新闻稿 NLP（含 LLM）

| 项目 | 内容 |
|---|---|
| 信号 | 用 LLM 或词典法给财报电话会文字稿、8-K、新闻稿打情绪/语气分，预测收益 |
| 最强已发表结果 | Ghosal，《LLM-Driven Investment Models: Evidence from Earnings Call Transcripts》（[SSRN 6510327](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6510327) / [6351439](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6351439)）：2019–2023 年财报电话会文字稿，微调 LLM 情绪策略多空年化 **8.4%**，是词典法（4.2%）的两倍，**近年优势更明显**（说明并未随时间衰减，反而扩大）；作者自称已经**扣除交易成本、信号延迟和组合约束** |
| 独立复现 | **未见独立第三方复现**，这是同一作者系列的两篇 SSRN 工作论文。同时存在**相反证据**：另一批研究指出"在合理换手、真实建仓规模、且排除 LLM 训练集数据泄漏的前提下，LLM 生成的买卖信号跑不赢简单基线"（检索到的综述性说法，[gaper.io](https://gaper.io/can-llms-crack-algorithmic-trading-code) 等，访问于 2026-09-18）——**这是一个尚有争议、未有共识的领域**，必须明确写"证据双方都存在，无定论" |
| 相关但机制不同的验证结果 | **Lazy Prices**（见 1.1）是同一批作者（Cohen, Malloy）+ Nguyen 用**纯文本变更**（不需要 LLM）在 10-K/10-Q 上做出的、发表在顶刊、有 22%/年量级效果的结果，机制是"投资者对文本变化不敏感"，跟"情绪打分"是不同的信号构造方式 |
| 获取成本/API/PIT | 财报电话会文字稿**没有免费的批量历史来源**（付费厂商如 AlphaSense、Capital IQ、Motley Fool 转录服务），这是一个**访问成本红旗**；8-K/新闻稿本身通过 EDGAR 免费且 PIT 清晰 |
| 最便宜的决定性测试 | 不用付费买电话会文字稿：先在免费的 8-K/新闻稿全文 + 我们已有的新闻标题表上，用文本"变更幅度"（1.1 节的方法）而不是情绪打分做测试，成本几乎为零；等用户配置好非 Claude 的便宜 LLM 端点后，再对**样本**（不是全量）新闻/新闻稿做情绪抽取，与文本变更特征对比增量 |
| 红旗 | 财报电话会转录本身不便宜；LLM 情绪抽取的样本外证据两派都有，本项目规则明确"批量用非 Claude 模型打分需要用户先配置"，不能默认动用 Claude token 做批量标注 |

### 1.9 分析师预期修正（Analyst Revisions）

| 项目 | 内容 |
|---|---|
| 信号 | 分析师上调/下调盈利预测的动量效应 |
| 最强已发表结果 | 学术界长期共识：分析师预测修正幅度对未来收益有增量解释力，且与价格动量、盈余公告后漂移（PEAD）高度相关（[sciencedirect.com/.../S1057521916301314](https://www.sciencedirect.com/science/article/abs/pii/S1057521916301314) 等） |
| 独立复现 | 该效应是资产定价文献里最"教科书化"的效应之一，长期被大量论文复现，但也因此**几乎肯定已经被机构充分利用和套利**（属于 Guerard 等人在 FactSet 研讨会材料里讨论的经典因子，[go.factset.com PDF](https://go.factset.com/hubfs/Symposium%20Images/Guerard_EARNINGS%20FORECASTS%20AND%20REVISIONS,%20PRICE%20MOMENTUM,%20AND%20FUNDAMENTAL%20DATA.pdf)） |
| 获取成本/API/PIT（关键红旗） | 免费来源（Zacks 网页版、Seeking Alpha 90 天修正摘要）**都不提供可批量下载的历史 PIT 数据**，只有"当前快照"（[tikr.com/blog](https://www.tikr.com/blog/6-of-the-best-free-tools-to-monitor-a-stocks-analyst-estimates)，访问于 2026-09-18）。学术界标准数据源是付费的 I/B/E/S，不在预算内 |
| 最便宜的决定性测试 | 无——这正是"没有免费 PIT 历史，直接判定今天做不了"的典型例子 |
| 红旗 | **PIT 不可用，直接淘汰**，即便信号本身在文献里是可信的 |

### 1.10 指数成分股调整（Index Add/Delete）

| 项目 | 内容 |
|---|---|
| 信号 | 标普/罗素等指数纳入/剔除公告后的价格反应 |
| 最强已发表结果 | 经典效应：标普 500 纳入公告到生效日平均上涨 8.8%（早期文献）。但 Greenwood & Sammon，《The Disappearing Index Effect》（NBER，[nber.org/w30748](https://www.nber.org/system/files/working_papers/w30748.pdf)）证明：**近年"毕业式"纳入（从标普 400 升入 500）的效应已经趋近于零**，因为市场流动性供给能力大幅提升、套利者已提前布局 |
| 独立复现 | Greenwood & Sammon 本身是对这个领域大量历史文献的元分析和更新，**属于对旧效应的独立、样本外证伪**，可信度高 |
| 2024–2026 是否存活 | **对标准标普 500"毕业式"纳入已基本消失**；但"非毕业式"新纳入（公司此前不在任何主要指数）和**强制剔除**仍然有可衡量的价格扭曲（[ideas.repec.org/.../S0378426623001747](https://ideas.repec.org/a/eee/jbfina/v154y2023ics0378426623001747.html)，2023） |
| 获取成本/API/PIT | 指数变更公告免费公开（标普/罗素官网、交易所公告），PIT 清晰 |
| 最便宜的决定性测试 | 若要做，只值得做"非毕业式纳入"和"强制剔除"这两个细分子集，样本量很小 |
| 红旗 | 主流效应已被公认套利掉；剩余的细分效应样本量小、执行需要速度优势（对我们这种非高频账户没有优势） |

### 1.11 股票回购公告（Buyback Announcements）

| 项目 | 内容 |
|---|---|
| 信号 | 公开市场回购计划公告后的价格反应 |
| 最强已发表结果 | 经典文献（1994–2014 样本）发现回购公告后有正向长期异常收益，但**样本越往后效应越弱**（多篇二手转述一致）。欧洲最新样本（Stoxx Europe 600，76 家公司，2020–2024）：3 日窗口累计异常收益 1.11%，但**2023–2024 年（"平静"市场环境）已经不再显著**，只有 2020–2022 高波动期显著（期刊文章摘要，[journals.lib.uni-corvinus.hu](https://journals.lib.uni-corvinus.hu/index.php/penzugyiszemle/article/view/1775)） |
| 独立复现 | 多篇不同时期、不同地区的论文方向一致地指向"效应在减弱"，可视为对"回购公告有稳定 alpha"这一说法的**独立证伪性证据的积累** |
| 2024–2026 是否存活 | 证据指向**没有存活**（2023-2024 平静市场下不显著）；另外 2023 年是**近八年回购公告最少的一年**（[wallstreethorizon.com](https://www.wallstreethorizon.com/blog/2023-Tracks-as-the-Weakest-Buyback-Announcement-Year-Since-Before-2016)），样本本身也在萎缩 |
| 获取成本/API/PIT | 回购公告免费（8-K/新闻稿，EDGAR） |
| 最便宜的决定性测试 | 不建议投入 |
| 红旗 | 效应本身证据指向已消失；样本量还在萎缩 |

### 1.12 国会交易 / 游说 / 政府合同 / FDA 日历 / 专利授权

| 子类 | 信号与最强证据 | 独立复现/2024-2026 存活 | 获取成本/PIT | 红旗 |
|---|---|---|---|---|
| **国会交易披露** | STOCK Act 要求 45 天内披露；Ziobrowski 等 2004/2011 论文称参议员跑赢市场 12.3%/年、众议员组合月均超额 55bp（[digitalcommons.lindenwood.edu](https://digitalcommons.lindenwood.edu/faculty-research-papers/240/)；[researchgate.net/.../227378283](https://www.researchgate.net/publication/227378283_Abnormal_Returns_From_the_Common_Stock_Investments_of_Members_of_the_US_House_of_Representatives)）| **后续独立复现方向相反**：Eggers & Hainmueller (2013)、Belmont et al. (2022) 发现众议员/参议员平均而言**买指数基金反而更好**（多篇来源转述一致，例如 [nber.org/w26975](https://www.nber.org/system/files/working_papers/w26975/w26975.pdf) "Senators As Feckless As the Rest of Us at Stock Picking"）。真实资金验证：**NANC/KRUZ ETF**（分别跟踪民主党/共和党议员持仓，2023-02 成立）截至 2026-04-30，NANC 累计 +88%、KRUZ +73%，同期 Vanguard 标普 500 ETF 跑赢 KRUZ、被 NANC 小幅跑赢约 7 个百分点（主要由 NVDA 等大盘科技股驱动，非议员"信息优势"）；2025 年只有 **32.2% 的议员跑赢标普 500**（[etf.com](https://www.etf.com/sections/etf-basics/nanc-vs-kruz-battle-congress-stock-trackers)、[unusualwhales.com/congress-trading-report-2025](https://unusualwhales.com/congress-trading-report-2025)，均访问于 2026-09-18）| 官方原始披露**完全免费**：众议院 Clerk 年度批量 XML（`disclosures-clerk.house.gov`）、参议院 eFD（`efdsearch.senate.gov`），**结构性 45 天滞后**（[github.com/api-evangelist/bargo-congress-trades-api](https://github.com/api-evangelist/bargo-congress-trades-api)，访问于 2026-09-18）；付费层（Quiver Quantitative、Unusual Whales）只是做了解析和 API 封装，不是数据本身收费 | 早期正面证据（2004/2011）已被后续独立研究部分推翻；真实 ETF track record 显示"跟随议员"约等于"持有大盘科技股"，与议员的信息优势关系存疑；45 天滞后是硬伤 |
| **游说支出** | 游说支出与股票收益关系，证据混合：正面（税收/国防/贸易类游说，[researchgate.net/.../41834907](https://www.researchgate.net/publication/41834907_Corporate_Lobbying_and_Financial_Performance)）与负面/不显著（环境类游说，及修正内生性问题后，[ssrn.com/abstract=2779697](https://www.ssrn.com/abstract=2779697)）均有 | 学术界本身就没有一致结论，不构成"已验证的可交易信号" | 免费：参众两院 LDA 申报（`lda.senate.gov` API） | 双向证据并存，无法作为独立信号使用 |
| **政府合同流** | USAspending.gov 合同中标数据与股价反应：从业者产品（Federal Contract Momentum 等）称"合同中标信息未被市场立即消化"（[insight.factset.com/government-receivables-as-a-stock-market-signal](https://insight.factset.com/government-receivables-as-a-stock-market-signal)）| **无同行评审学术验证**，全部是数据商/自媒体产品页的说法 | USAspending.gov 官方免费批量 API；数据经 FPDS 上传，存在数天到数周的滞后（因机构而异） | 纯从业者声称，无独立学术验证；适合作为**辅助特征**而非独立策略 |
| **FDA 日历（PDUFA 日期）** | 生物科技股在 FDA 审批决定前后有明显波动，是行业公认的催化剂事件 | FDA **不公开发布前瞻性 PDUFA 日历**（保密规则），第三方日历都是从公司自愿披露中拼凑（[rttnews.com](https://www.rttnews.com/corpinfo/fdacalendar.aspx) 等），**没有严谨的、扣成本后的学术回测证据**，全部是从业者叙述 | 拼凑日历本身免费（可以用我们已有的 EDGAR 全文检索抓取公司自己披露的 PDUFA 日期），但没有官方免费的前瞻数据源 | 证据质量最弱的一类，几乎全是叙事而非回测数字；且这是**二元事件+期权类策略**的传统打法，跟我们现有的日线/分钟线股票工具不匹配 |
| **专利授权** | Kogan, Papanikolaou, Seru, Stoffman (KPSS)，《Technological Innovation, Resource Allocation, and Growth》（*QJE* 2017，[nber.org/papers/w17769](https://www.nber.org/papers/w17769)）：用专利授权公告 3 日窗口股价反应衡量专利经济价值，该指标能预测企业未来增长率、生产率 | **高引用、多篇后续论文复现和扩展**其"专利授权后有股价漂移，且漂移幅度可预测专利真实价值"这一结论（[sciencedirect.com/.../S1544612324013631](https://www.sciencedirect.com/science/article/abs/pii/S1544612324013631)，2024）；但**该文献主线是公司金融/增长研究，不是直接验证过的交易策略**，需要我们自己把它改造成交易规则 | KPSS 官方数据**免费公开**，GitHub 仓库持续更新，专利价值数据更新到 **2022 年底**、被引次数更新到 **2024 年**（[github.com/KPSS2017/...Extended-Data](https://github.com/KPSS2017/Technological-Innovation-Resource-Allocation-and-Growth-Extended-Data)，访问于 2026-09-18）。原始专利授权数据（USPTO PatentsView，[patentsview.org](https://patentsview.org/)）本身也免费、批量、PIT 清晰（专利授权公告日是公开事实） | 学术引用量大不等于"已验证的交易策略"；需要自己做专利-公司匹配和最新窗口的事件研究（2023–2026 无现成数据，需要自建） |

### 1.13 卫星影像 / App 下载量 / 供应链数据

| 项目 | 内容 |
|---|---|
| 信号 | 卫星拍摄停车场车流预测零售商销售；App 下载/收入数据预测公司业绩 |
| 最强已发表结果 | Berkeley Haas 的 Patatoukas & Katona 用 RS Metrics 480 万张卫星图片（6.7 万家门店）研究发现：**利用卫星停车场数据做多/做空能在财报公布后几天内获得扣费后约 4-5% 的收益**（[newsroom.haas.berkeley.edu](https://newsroom.haas.berkeley.edu/how-hedge-funds-use-satellite-images-to-beat-wall-street-and-main-street/)）；学术论文（15/44 家零售商样本）确认停车场车流对财报有预测力（[sciencedirect.com/.../S0022435922000240](https://www.sciencedirect.com/science/article/abs/pii/S0022435922000240)） |
| 独立复现 | 该研究本身是**独立学术团队**（非数据商自己发的白皮书）对商业数据的验证，可信度较高；另有独立论文验证"机构确实把卫星数据用进了日常交易，且信号发布后 3 个月内没有反转"（[sciencedirect.com/.../S1544612324013709](https://www.sciencedirect.com/science/article/pii/S1544612324013709)，2024） |
| 2024–2026 是否存活 | 从业者共识："这个信号在变得拥挤之前赚了好几年钱"（alpha decay 的典型案例，[thedatascore.substack.com](https://thedatascore.substack.com/p/satellite-data-3-good-and-3-bad-use)），暗示**目前边际已经不如从前** |
| 获取成本/API/PIT（关键红旗） | **RS Metrics、Orbital Insight 均为企业级定价**（未检索到公开价格，但行业惯例是每年数万到数十万美元级别），**没有免费或极低成本层级**，与我们的预算硬性不符 |
| 最便宜的决定性测试 | 无——直接被预算否决 |
| 红旗 | 证据质量是本报告里最高的一类之一，但**成本完全不在预算内**，属于"方向对、但今天做不了" |

### 1.14 加密货币 / 预测市场信号

| 项目 | 内容 |
|---|---|
| 信号 | 比特币与纳指的领先/滞后关系；Polymarket 等预测市场赔率与个股/大盘走势的关系 |
| 最强已发表结果 | 比特币与纳指 100 的相关性从 2024 年的 0.23 升到 2025 年的 0.52，2024 年一度达到 0.87（[financefeeds.com](https://financefeeds.com/crypto-and-nasdaq-correlation-what-it-means/)、[arxiv 2501.09911](https://arxiv.org/pdf/2501.09911)）——**这是同涨同跌的相关性/beta关系，不是可交易的领先-滞后 alpha 证据**。Polymarket 方面，**未检索到任何将预测市场赔率与个股价格反应联系起来的学术或独立验证研究**，只有 Polymarket 官方关于自身赔率"90-96% 准确"的自我描述（[polymarket.com](https://polymarket.com/predictions)），且这是对**它自己市场事件本身**（选举、体育等）的准确率，不是对股价的预测力 |
| 独立复现 | 无——这个方向目前没有可引用的、独立验证过的"预测市场→股票"交易证据 |
| 2024–2026 是否存活 | 无从谈起，因为没有已发表的交易证据可供检验存活与否 |
| 获取成本/API/PIT | Polymarket 数据本身免费/低成本可取，但缺乏证据基础 |
| 最便宜的决定性测试 | 不建议投入，属于"没有证据基础，纯属臆测方向" |
| 红旗 | 整个方向目前是叙事驱动而非证据驱动，应直接跳过 |

---

## 2. 排序后的候选清单（最多 5 个，按"证据强度 × 我们自己已有的交叉证据 × 便宜程度"排序）

| 排名 | 数据源 | 为什么值得做 | 最便宜的决定性测试 | 预估工时 |
|---|---|---|---|---|
| 1 | **FINRA 逐日做空成交量文件**（免费，2018-08 起） | 直接命中我们自己 `H-20260916-07` 的诊断结论：双月空头余额里没有信息的部分恰好是"分母"，而 Boehmer-Jones-Zhang 的机制是**逐日流量**而非存量快照；这是目前唯一"文献验证 + 我们自己反证已定位缺口 + 完全免费"三条都满足的候选 | 用免费文件复现 Boehmer-Jones-Zhang 的做空成交量占比分组测试，与已跑过的双月空头余额结果直接对比信息含量 | 约 0.5–1 个执行者工作日（PIT 表结构与 FINRA 空头余额表几乎一致，可复用现有管道） |
| 2 | **Form 4 结构复用（角色 + 10b5-1 + 空头腿）** | 零新增数据抓取；我们已经打到 82bp/月、t=3.1 的量级（与 CMP 原始论文一致），文献明确说缺口在"没分角色、没排除 10b5-1、没做空腿" | 重跑 `H-20260917-01` 的特征管线，加入三处过滤/权重，不新增基础设施 | 约 0.5 个执行者工作日 |
| 3 | **SEC 10-K/10-Q 文本变更信号（"Lazy Prices"复现）** | 唯一一个"顶刊发表、22%/年量级、无独立复现"的候选；完全免费（EDGAR 全文检索），且方法论极其便宜（文本 diff，不需要 ML/GPU），是"先复现别人已发表的结果"的典型案例 | 对同一 CIK 连续申报做逐句 diff，生成变更幅度分位特征，跑标准月频评估 | 约 1–1.5 个执行者工作日（含文本 diff 管道搭建） |
| 4 | **USPTO PatentsView + KPSS 专利价值方法论扩展到 2023–2026** | 高引用、机制清晰（专利授权公告 3 日窗口价格反应），免费批量数据，且我们已有分钟线可以做比原论文更精细的事件窗口；缺口在于官方 KPSS 数据止步 2022 年底，需要自己延伸 | 用 PatentsView 免费专利授权数据 + 我们的价格表，复现 KPSS 方法论在小样本（如近 12 个月）上的事件研究，检验效应是否还在 | 约 2 个执行者工作日（含专利-代码匹配这一额外工程量） |
| 5 | **13D 长期维权持仓（同一数据源、新用法）** | 零新增数据；我们已经证明了该机制里"申报当天有真实钱（+1.73%, t=4.15）"和"次日进场已经晚了"这两件事，文献（Brav et al.）明确说真正的钱在长期持有，这是一个尚未测试过的、方向明确的复用 | 把 `H-20260916-05` 的持有期从 20/40/60 个交易日改成 6/12/24 个月，按 Item 4 维权诉求过滤 | 约 1 个执行者工作日 |

---

## 3. 明确跳过的清单及理由

| 数据源 | 跳过理由 |
|---|---|
| 期权衍生信号（put/call、IV 偏斜、GEX、异常期权活动） | 免费/低成本源没有可回测的 PIT 历史（红旗，直接淘汰）；GEX 类证据几乎全部来自卖数据的商业机构，无独立学术验证；put/call 类历史证据里至少有一部分被证实源于真实内幕交易，执法打击后信号消失（Quantpedia 案例） |
| 散户情绪（Reddit/WSB、StockTwits、Google Trends） | 多篇独立研究显示 2021 年后边际消失甚至反转；原始论文扣成本后本就不盈利；数据获取端在变贵变难（Reddit API 收费） |
| 分析师预期修正 | 免费源没有可批量下载的历史 PIT 数据，只有当前快照（红旗，直接淘汰）；标准数据源 I/B/E/S 付费且不在预算内 |
| 指数成分调整（标普 500 标准纳入） | Greenwood & Sammon 的独立研究证明"毕业式"纳入效应已消失；剩余细分子集样本量太小，且需要执行速度优势 |
| 股票回购公告 | 多篇独立研究显示效应在减弱，2023-2024 平静市场下不再显著；公告数量本身也在萎缩 |
| 国会交易披露 | 早期正面证据已被后续独立研究部分推翻；真实 ETF track record 显示"跟随议员"效果接近"持有大盘科技股"；45 天结构性滞后 |
| 游说支出 | 学术界本身证据方向不一致（正负都有），不构成已验证信号 |
| 政府合同流 | 无同行评审学术验证，全部是数据商/自媒体产品页的从业者说法 |
| FDA 日历 | 没有官方免费前瞻数据源；证据质量最弱，几乎全是叙事而非回测数字；且是二元事件期权打法，与我们工具集不匹配 |
| 财报电话会 LLM 情绪 | 转录本身没有免费批量历史来源（访问成本红旗）；样本外证据两派并存无定论；本项目规则要求批量 LLM 打分需用户先配置非 Claude 端点 |
| 卫星影像/App 下载/供应链数据 | 证据质量高（独立学术验证），但访问成本是企业级定价，完全不在预算内 |
| 加密货币/预测市场信号 | 没有任何独立验证过的"预测市场/加密货币→股票"交易证据，纯属叙事驱动 |
| 13F 持仓复制 | 结构性 45 天滞后；唯一的正面证据（24.3% 年化跑赢）来自未经独立复现的单篇工作论文；免费复制工具已存在多年，若真有稳定 alpha 早该被套利 |

---

## 4. 直接回答：已有的 Form 4 / 13D / 空头兴趣 / 新闻标题，按文献的真实用法，哪个最可能自己就能成为策略？

**答案：Form 4 内部人买入，且要按文献的方式重新构造（角色加权 + 排除 10b5-1 + 多空双腿 + 不局限于最不流动分段），是四者中最可能的一个。** 理由：

1. **我们自己的数字已经和文献原始量级对上了。** CMP 原始论文的机会型买入多空组合月均 alpha 是 **82bp**（[SSRN 1692517](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1692517)）；我们 2026-09-18 的独立测试在最不流动分段+集群+1个月持有这一格，相对同尺寸随机对照拿到的正是 **+82bp/月，t=3.1**（`reports/research/iterations/h20260917_01_insider_independent/report.md`）。这不太可能是巧合——更合理的解释是：**信号本身是真的**，只是我们的实现方式（纯做多、月度调仓、不分角色、不排除 10b5-1、只做多单一波段）没有按文献的配方来。
2. **文献明确指出了我们没做的三件事，且都是零新增数据成本的修改：** (a) 按角色/集群加权（Form 4 XML 已含 isDirector/isOfficer/isTenPercentOwner 字段，只是没解析进特征表，`H-20260917-01` 报告原文写明"申报人角色…本轮未做"）；(b) 排除 10b5-1 预设计划交易（SEC 2022 年规则修订后，2023-04 起 Form 4/5 必须勾选，我们的数据已经覆盖这段时期）；(c) 加空头腿（CMP 原始策略是多空对冲，我们目前只做多）。
3. **绝对收益低（9.5% 年化、跑不赢 SPY）有具体、可解释的成本/结构性原因，而不是信号是假的：** 我们自己的报告显示，最强的那一格月双边换手率高达 0.76（年化约 9 倍），集中在最不流动的分段，10bp/边的成本假设可能低估真实执行成本；同时 Ozlen & Batumoglu（2025-12，[SSRN 5966834](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5966834)）称 **70-80% 的内部人交易 alpha 在公开披露前就已消散**，说明 Form 4 发布后能抓到的本就是"剩下的一小部分"，不该期待和内部人自己的收益率一样高。这些都是"如何更接近文献配方地去交易剩余部分"的工程问题，不是"方向错了"的证据。
4. **相比之下，另外三个数据源要么机制不同、要么关键成分缺失：**
   - **13D**：申报当天的钱是真的（+1.73%，t=4.15，`H-20260916-05`），但被我们证明**在次日开盘前就已经定价完**；文献（Brav, Jiang, Partnoy, Thomas 2008）的真实机制是**参与/跟随维权活动的长期持有**（5 年不反转），这是一个我们**还没有测试过的不同持有期设计**，是很好的第二候选，但目前还只是"文献指出方向、我们尚未验证"，不如 Form 4 那样已经有匹配文献量级的自己的数字。
   - **空头兴趣**：`H-20260916-07` 的分解证明我们现在这张"双月空头余额存量表"里能归因于空头信息本身的部分几乎为零（21 日残差只有 -0.18%，未单独显著），文献真正有效的机制（Boehmer-Jones-Zhang）用的是**逐日做空成交量**，是我们**没有的数据粒度**——所以空头兴趣要变成策略，前提是先补上第 2 节候选 #1 那份免费的 FINRA 逐日做空成交量数据，不是重新排列现有数据就能解决的。
   - **新闻标题**：目前测试的是"注意力/新颖度"计数特征（`H-20260916-02`），而文献里真正验证过、效果最大的机制（Tetlock 2007 的媒体悲观情绪、Loughran-McDonald 2011 的负面词典、Cohen-Malloy-Nguyen 2020 的 *Lazy Prices* 文本变更）用的都是**文本内容/语气**而不是**报道数量**——这不是"新闻标题没用"，而是**我们还没有按文献的方式测试它**（LLM 情绪打分那一阶段本来就在等用户配置非 Claude 端点），所以严格说它是"未测试"而非"已证伪失败"，但也因此不能说它"最可能"，因为还没有任何契合文献配方的自己的数字支持。

**一句话总结：Form 4 是唯一一个"文献配方 vs 我们的实现差距"可以清楚列出、且全部零成本可修的数据源；13D 有同等质量的交叉证据但需要换一个持有期设计去验证；空头兴趣需要先补一个免费的新数据粒度；新闻标题的文献配方我们还完全没跑过。**

---

## 5. 本简报引用来源一览（按出现顺序，不重复列出正文已有 URL 的条目）

见正文各表格内联 URL；全部为公开网页/论文，访问日期均为 2026-09-18（除另有署名日期的论文/工作论文本身日期外）。
