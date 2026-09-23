# I-20260923-02：高频因子 / 加密趋势 / 两个开源模型的一手源核验

纯联网调研，不跑回测。8 个既定条目，每条都打开一手来源（论文原文、官方文档、issuer 官网、GitHub README/issue）自己读，不采信仅靠搜索摘要得到的数字；确实打不开一手来源的（SSRN 对自动抓取返回 403/Cloudflare 挑战，curl 直连同样被拒），改用作者自己挂在个人主页/机构主页上的同一篇 PDF，或独立第三方复现页，并在下面明确标注哪些数字属于这一类、哪些是纯搜索摘要（未核实）。数字一律引用原文，不换算、不重算。约 45 次网络请求（WebSearch + WebFetch + 4 次 curl 直拉 PDF/CSV 后本地 `pdftotext`/`grep` 抽取）。

判定口径：`reproduce-cheap`（数据/算力都现成，一次便宜测试能定生死）/ `reproduce-costly` / `not-feasible-for-us`（写明原因）/ `evidence-too-weak`。

## 汇总表

| # | 条目 | 关键数字（原文引用） | 证据质量 | 数据/算力匹配 | 判定 |
|---|---|---|---|---|---|
| 1 | 已实现偏度 Amaya-Christoffersen-Jacobs-Vasquez 2015 JFE | 2011 工作稿：周频 24bp，t=3.65（十分位）；**独立复现 paperswithbacktest.com 1990–2026：年化 0.19%，夏普 0.14** | 一手工作稿 + 2020 年同族论文内复现 + 独立衰减复现，三方一致指向"已衰减" | 需分钟级数据算已实现偏度，我们有 | **evidence-too-weak**（衰减证据干净，不值得再测）|
| 2 | 符号跳跃变差/好坏波动率 Bollerslev-Li-Zhao 2020 JFQA | 价值加权 High−Low **−29.35bp/周（t=−5.83）**，等权 −38.54bp（t=−9.66）；1993–2013；效应集中在流动性差、交易成本高的股票 | 一手论文完整读完，数字扎实；但无干净的衰减证据（同网站复现数字明显有 bug，弃用） | 分钟线可近似已实现半方差，我们有；无需做空即可测多头一侧（VW 低 RSJ 十分位本身 FFC4 alpha +16.56bp/周，点估计未见自身 t 值） | **reproduce-cheap** |
| 3 | 日终反转 Baltussen-Da-Soebhag 2024/25 | VW 多空 3.78bp/日（t=10.69，~9.5%/年）；**买方（日内跌幅最大者）单腿 27 年累计 ~400%，卖方腿收益接近零** | 一手论文完整读完；作者自己明说"按现有形式，扣成本后可能大多数投资者无法获利" | 需分钟线判早盘收益 + 收盘前 30 分钟执行，我们有；无需做空（多头腿扛了几乎全部毛收益）| **reproduce-cheap**（本条目内最值得优先）|
| 4 | 中国卖方高频因子（开源/方正/东吴） | 开源证券"理想反转" IR 2.51，月胜率 74%，**全篇无一处提及美股** | 二手聚合页（非原始研报 PDF），未经同行评审 | 方法论可移植到我们的分钟线，但 A 股微观结构（T+1、涨跌停、散户占比）与美股差异未被来源讨论 | **evidence-too-weak** |
| 5 | 真高频对我们是否可行 | Alpaca Paper 按 NBBO 撮合、10% 随机部分成交、**不模拟市场冲击/排队位置/延迟滑点**；Baron et al 2019 JFQA：DECISION_LATENCY 最快 42 微秒、最慢均值 25 毫秒 | broker 官方文档 + 监管一手文件 + 学术论文，三方都直接打开读了 | 我们只有 OHLCV+vwap+trade_count 分钟线，无盘口/逐笔，无托管；学术证据说胜负在微秒级 | **not-feasible-for-us** |
| 6a | 加密趋势 Zarattini-Pagani-Barbon 2025 | BTC 单腿净费后 CAGR 30%、夏普 1.56、回撤 −19%（被动持有 >80%）；Top20 月度轮动 CAGR 18%、回撤 −11% | SSRN 本身 403 打不开，用作者自己机构（Concretum）两个页面 + 合作者个人主页交叉核对，一致 | 两个变体按字面数字**都够不到本项目门槛**（≥50%/年且回撤≤35%，或夏普≥2 且≥30%/年）| **evidence-too-weak**（不是数据/算力问题，是数字本身不够）|
| 6b | 加密动量 Liu-Tsyvinski-Wu 2022 JF | 周频价值加权动量五分位多空 1–4 周分别 2.7%/3.3%/4.1%/2.5% | 一手 NBER 工作稿完整读完 | 多空设计（我们不能做空币）；样本止于 2018，无近期证据 | **evidence-too-weak**（设计不匹配 + 过时）|
| 6c | Bitwise BTOP 实盘记录 | 2023-09-29 上市，10/20 日 EMA 定趋势轮动 BTC/ETH 期货 vs 国库券；**发行方已于 2026-05-29 清盘** | issuer 官网直接打开 | CME 期货，非现货，且产品已下架 | **not-feasible-for-us**（错的场地 + 已被终止）|
| 6d | Alpaca 加密基础设施 | 手续费 0.15%/0.25%（maker/taker，最低档）到 0/0.10%（最高档）；20+ 币种、56 交易对 | 官方文档直接打开 | Paper 是否支持加密未见明文（仅见一个打给 paper-api 的 curl 示例），历史 K 线起点未见文档说明 | **reproduce-cheap**（把两个空白点操作性验证一下即可，不需要研究算力）|
| 7 | RD-Agent(Q) 微软 arXiv 2505.15155 | NASDAQ100（2024–2025/06，前 20 大、成本 0.1%/笔）：o4-mini 版 **年化 28.40%、IR 1.7737、回撤 −6.34%**；同窗口 LightGBM 基线反而亏钱 | 一手论文 PDF 完整读完（含两列表格排版纠错）；GitHub README 直接读 | Docker 必需；README 未写最低内存/GPU，但框架自带训练多种深度学习基线，隐含需要不小算力；无独立（非微软）复现 | **not-feasible-for-us**（3.9GB/无 GPU 的机器几乎跑不动 Docker 化的多智能体+深度学习循环）|
| 8 | Kronos arXiv 2508.02739 | mini 4.1M/small 24.7M/base 102.3M/large 499.2M 参数，MIT 协议；**大模型权重未公开** | GitHub README + issue 直接读；训练用 3 pod × 8×RTX4090D | CPU 推理未见任何文档确认或否认；本机无 AVX2 是文档完全没提到的额外风险 | **evidence-too-weak**（独立评测者明确表态"没人测过，扣成本前别当交易信号"）|

---

## 1. 已实现偏度（Amaya, Christoffersen, Jacobs, Vasquez）

一手来源：2011-12-26 工作稿（合著者 Andrew Patton 在杜克大学个人主页挂的 PDF，与后来发表的 2015 JFE 版本同一作者组）[public.econ.duke.edu/~ap172/ACJV_26Dec2011.pdf](https://public.econ.duke.edu/~ap172/ACJV_26Dec2011.pdf)。SSRN（[abstract_id=1898735](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1898735)）和 ScienceDirect（[S0304405X15001257](https://www.sciencedirect.com/science/article/abs/pii/S0304405X15001257)）都对抓取返回 403，未能打开最终发表版原文。

摘要原句："A trading strategy that buys stocks in the lowest realized skewness decile and sells stocks in the highest realized skewness decile generates an average weekly return of **24 basis points with a t-statistic of 3.65**。" 样本 TAQ 1993-01-04 至 2008-09。Table 2 Panel B：价值加权最低偏度十分位 40bp/周 vs 最高偏度 17bp/周；等权 55bp vs 12bp，"both differences are statistically significant"。搜索引擎摘要给出的"19bp，t=3.70，五分位"是发表版的常见转述，**未被我们独立打开核实**，与工作稿的十分位口径不完全一致，可能是评审期间方法调整所致。

**post-2015 证据（两条，方向一致，都指向衰减）：**

1. Bollerslev-Li-Zhao (2020, JFQA) 在自己的 1993–2013 样本上重新按已实现偏度（RSK）排序（Table 3 Panel C），明确写"confirm the findings in ACJV"：价值加权 High−Low 原始 −18.14bp/周（t=−4.35），FFC4 alpha −17.11bp（t=−4.11）；等权 −31.09bp（t=−9.79）/ −30.75bp（t=−10.08）。这是同族信号在**发表后**（2020）、不同作者组的独立重建，方向和量级都对得上。
2. [paperswithbacktest.com](https://paperswithbacktest.com/strategies/does-realized-skewness-predict-the-cross-section-of-equity-returns) 自己跑的复现，回测窗口 **1990–2026**，周频，96 个持仓（48 多 48 空）：年化收益 **0.19%**，夏普 **0.14**，波动率 1.44%，最大回撤 −7.68%。相比原论文样本内 ~10–13%/年的量级，这是几乎完全衰减到零的结果。该页数字内部自洽（小波动率、小回撤，符合一个市场中性周频策略应有的形状），可信度高于同网站对 item 2 的复现（见下）。

另查 Open Source Asset Pricing 的信号库（[SignalDoc.csv](https://raw.githubusercontent.com/OpenSourceAP/CrossSection/master/SignalDoc.csv) 原始文件，本地 grep）：**OSAP 并未收录 ACJV 这个周频、日内已实现偏度信号本身**，只有一个近亲信号 `ReturnSkew`（Bali-Engle-Murray 2015，月频、用日收益率算偏度，样本 1963–2012，t=4.01 等权），OSAP 自己的复现笔记写"OP finds negative and significant relationship EW, and positive and significant relationship VW. They conclude that results are difficult to interpret"——连这个近亲信号的符号都因加权方式而不稳定。

**数据/算力**：算已实现偏度需要日内三次方收益的加总；我们有 2016–2026 分钟线（原论文用的应是更高频的 tick/5 分钟数据，分钟线是合理近似）。计算量极小，6 核机器绰绰有余。

**判定：evidence-too-weak。** 不是因为数据或算力不够（两者都够，技术上完全是 reproduce-cheap 的活），而是独立衰减证据已经很干净：一个跨 36 年、样本外延伸到 2026 的复现给出 0.19%/年、夏普 0.14，这已经是"不用再测"级别的负面证据。按 `research-mission.zh.md` 的规则，没有新的可指认信息不重开。

## 2. 符号跳跃变差 / 好坏波动率（Bollerslev, Li, Zhao 2020 JFQA）

一手来源完整读完：作者自己挂在杜克大学网站的已发表版 PDF（与 doi:10.1017/S0022109019000097 一致）[public.econ.duke.edu/~boller/Papers/jfqa_19.pdf](https://public.econ.duke.edu/~boller/Papers/jfqa_19.pdf)。

样本：NYSE/AMEX/NASDAQ 普通股，股价 $5–$1000，**1993–2013**，每周二收盘排序，持有 1 周。主结果（Table 3 Panel A，按 RSJ 排序）：价值加权 High−Low 原始收益 **−29.35bp/周（t=−5.83）**，摘要原文称"approximately 15% per year"；FFC4 alpha −28.80bp（t=−5.77）。等权：原始 −38.54bp（t=−9.66），FFC4 alpha −37.89bp（t=−9.95）。稳健性：限定标普 500 成分股子样本，价值加权 FFC4 alpha 仍有 −26.23bp（t=−5.22）。

**成本相关的关键警示**：按 Amihud 非流动性做双重分组（Table 7 Panel C），流动性最好（最便宜交易）分位 FFC4 alpha 只有 −27.61bp（t=−4.76），流动性最差（最贵交易）分位达到 −61.62bp（t=−10.03），差值 −34.02bp（t=−4.64）——**效应集中在难交易、贵交易的股票上**，这与我们最近否定 Concretum gap fade（H-20260922-08）的模式相同，是一个必须在本地成本模型里显式测试的警示，而不是可以忽略的细节。论文本身没有给出扣费后的具体数字，只有这个间接的流动性代理分析。

OSAP 信号库同样检索确认：**完全没有 RSJ / signed jump variation / Bollerslev-Li-Zhao 这一条**（grep "realiz"/"RSJ"/"jump"/"Bollerslev" 只命中两个无关信号）。

搜索层面（未独立打开，标记未核实）找到几篇 2023–2025 的后续复现，但全部落在**中国 A 股**：PLOS ONE 的"sign realized jump risk...evidence from China"、[SSRN 4342028](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4342028)（2023，"Relative Signal Jump Variance, Investor Attention, and the Cross-Section of Chinese Stock Returns"）、[SSRN 5583481](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5583481)（2025，"Systematic Signed Jump Variation and Chinese Stock Return Predictability"）；没有找到一篇专门做**美股 2013 年之后**样本外检验的论文。

[paperswithbacktest.com 对这篇论文的复现](https://paperswithbacktest.com/strategies/good-volatility-bad-volatility-and-the-cross-section-of-stock-returns) 数字明显有问题：年化收益 20.00%、夏普 0.09、**波动率 6276.20%、最大回撤 −185.02%**，当前仅显示 4 个持仓（多 AAPL/AMZN，空 PG/XOM）。波动率超过 1000%、回撤跌破 −100% 对一个正常的多空组合是不可能的，大概率是该站点这一页的杠杆缩放或实现口径有 bug（也可能是把"前 N 名"实现成了极小的 N）。**这组数字不采信，也不作为衰减或存活证据的任何一侧。**

**可长可短的结构提示**：Table 3 Panel A 的分位数据里，价值加权最低 RSJ 十分位单独的 FFC4 alpha 是 **+16.56bp/周**（正号，即"好消息多、跳跃正向"的股票本身长期跑赢），这是多头一侧的点估计，我们没有采到它自己的 t 值。由于我们不能做空，如果要落地这个信号，天然只能用这条腿。

**数据/算力**：把已实现方差拆成正/负日内增量的平方和，分钟线足够（原论文用高频数据，5 分钟采样是这类文献的常见做法，分钟线只会更细）。计算量小，无需 ML，6 核机器足够。

**判定：reproduce-cheap。** 一手证据扎实、样本量大、t 值高、跨子样本稳健；没有找到能一锤定音的衰减证据（同类网站复现反而因为明显的实现 bug 被排除）；数据和算力都现成；且我们只需要验证多头一侧（与不能做空的约束天然吻合）。需要在设计里显式纳入 item 2 自己给出的警示：效应在低流动性名字里更强，落地时必须扣真实冲击成本重新评估，且优先在大盘股子集里验证是否还剩残余。

## 3. 日终反转（Baltussen, Da, Soebhag）

一手来源完整读完：合著者 Zhi Da 挂在圣母大学个人主页的 2025 年 4 月稿 [academicweb.nd.edu/~zda/EOD.pdf](https://academicweb.nd.edu/~zda/EOD.pdf)，与 SSRN [abstract_id=5039009](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5039009)（2024-11-29 首次挂出，FEB-RN Research Paper No. 77/2025）一致。SSRN 本身同样 403，未直接打开。

规则：每日用 ROD3（早盘到收盘前一段的累计收益）把股票分五组，**只在收盘前最后 30 分钟**持有"买入早盘跌幅最大者、卖出早盘涨幅最大者"的多空组合，每天重新建仓。样本 1993–2019（27 年），NYSE/AMEX/NASDAQ，$5 和 $1 两档价格过滤都测了。

核心数字：价值加权多空原始收益 **3.78bp/日（t=10.69）**，六因子 alpha 3.71bp/日（t=10.61），论文原句"about 9.5% a year"（按 252 个交易日年化，因为策略每天只交易一次）。等权：原始 6.86bp/日（"17.3% a year"），风险调整后 6.38bp/日（t=17.30）。按市值二次分组：最小 20% 个股六因子 alpha 达 **14.71bp/日（t=27.20）**，最大 20% 个股仍有 3.41bp/日（t=10.61）——**这个效应在大盘股里依然显著**，流动性画像明显好于 item 1/2 那类效应。

**对我们最重要的一句话**：论文自己承认"Given that trading on end-of-day reversal requires frequent rebalancing, the strategy as presented might not be exploitable by many investors after accounting for transaction costs"，并点名做市商和自营交易台才有足够低的成本吃到它。同时，27 年样本里，日内跌幅最大的那档股票（也就是买方腿，一天只持有 30 分钟）**累计涨了约 400%，"more than double the returns on the market portfolio"**，而对应的卖方腿（日内涨幅最大者）"returned close to zero over the sample period"——**几乎全部毛收益都在多头腿上**，这正好是我们唯一能交易的那一侧。论文没有给出扣费后的具体数字，也没有单独报告一个"只做多"版本的净收益序列。

**数据/算力**：需要日内数据判早盘收益、在收盘前 30 分钟下单，我们有 2016–2026 分钟线，覆盖面完整；不需要期权、盘口。计算是简单的每日横截面排序，不需要机器学习。

**判定：reproduce-cheap，本轮 8 项里最值得优先的一条。** 一手证据完整、t 值大、跨市值稳健（连大盘股都显著）、边际优势恰好落在我们能交易的多头腿上、数据现成、执行逻辑简单（日频排序+收盘前下单）。真正的悬念是扣真实冲击成本后还剩多少——这是一个便宜就能测的问题（在收盘前 30 分钟这个流动性通常尚可的窗口里，用我们自己的分钟线估算冲击成本，不需要任何新数据源）。

## 4. 中国卖方"高频因子"（开源/方正/东吴等）

按任务要求只做了 2–3 次检索。直接打开了一个二手聚合页 [bigquant.com/wiki/doc/krTwRtm1Qi](https://bigquant.com/wiki/doc/krTwRtm1Qi)（不是开源证券原始研报 PDF，原始 PDF 不在免费可抓取范围）：开源证券"理想反转"因子，用"W 形切割法"对 20 日窗口内的**单笔平均成交金额**排序切割，据称 IR 2.51、月胜率 74%，"significantly superior robustness compared to traditional reversal factor Ret20"，**全篇只出现 A 股（沪深）语境，没有任何美股或英文测试的痕迹**。

另有"聪明钱因子"（用分钟级量价数据识别机构参与度）和方正证券"适度冒险"因子（由"耀眼波动率"+"耀眼收益率"合成，据搜索摘要报 Rank IC −8.89%、ICIR −4.84、多空年化 37.46%、IR 4.10、月胜率 87.74%，测试范围 CSI300/500/1000）——这两条**只做了搜索、没有直接打开原始或二手页面**，按项目规则标记为"未核实"，不采信为已读证据。

**没有找到任何一篇把这类信号（无论是"理想反转"的成交金额切割法，还是"聪明钱"的分钟级参与度识别）应用到美股并报告结果的公开资料**——检索到的全部是 A 股（CSI300/500/1000）语境。这些都是未经同行评审的卖方研报或其二手转述，方法论细节部分公开（大致机制说得清）、部分不公开（精确的阈值/权重不公开），且明确没有人讨论过 A 股与美股微观结构差异（T+1、涨跌停、散户占比、做市商制度都不同）对信号有效性的影响。

**判定：evidence-too-weak。** 不是数据或算力问题（我们的分钟线技术上完全可以复刻类似的量价切割逻辑），而是（a）没有任何美股证据，（b）来源本身在其"主场"A 股市场也未经独立验证，（c）没有人处理过跨市场微观结构差异这个问题。在没有更具体线索之前不值得分配算力去"翻译"这些因子。

## 5. 真高频对我们是否可行

**(a) Alpaca Paper 成交模拟**：官方文档 [docs.alpaca.markets/docs/paper-trading](https://docs.alpaca.markets/docs/paper-trading) 直接打开确认：按 NBBO 最优报价撮合；"When orders are eligible to be filled, they will receive partial fills for a random size 10% of the time"；明确列出**不**模拟的项目——订单的市场冲击、非 marketable 限价单的排队位置、因延迟造成的滑点；且不按 NBBO 挂单量校验订单数量（可以对一只薄股票整单成交一万股）。

**(b) 路由/延迟声明**：官方文档里没有找到关于真实（非模拟盘）订单路由机制或具体延迟数字的声明，只在"不模拟的项目"里提到"不模拟因延迟造成的滑点"这一条限制性描述。

**(c) PDT 规则**：这是本轮意外发现的一个重要监管变化。FINRA 官方通知 **[Regulatory Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10)**（2026-04-20 发布，直接打开原文确认）：取消传统的"5 个交易日内 4 次当日交易"PDT 认定和 **$25,000 最低权益要求**，改为实时"日内保证金"标准（Intraday Margin Level / Intraday Margin Deficit，缺口低于 $1,000 或账户权益 5%（取更低者）的可豁免），**生效日期 2026-06-04**，18 个月分阶段实施期到 2027-10-20。Alpaca 官方文档 [docs.alpaca.markets/us/docs/the-intraday-margin-rule](https://docs.alpaca.markets/us/docs/the-intraday-margin-rule) 直接打开，措辞一致："pattern day trader"的定义已被取消，券商不再需要追踪"round-trip"次数。**但**：Alpaca 另一页面（paper-trading 文档）仍描述旧版 PDT 拒单逻辑（"4th Day Trade within 5 business days will be rejected if real-time net worth is below $25,000"），我们没有找到把两页对齐的单一说明——**是否 Paper 账户的拒单逻辑已经真的按新规则更新，未核实，值得在正式依赖前操作性验证一次**（比如直接下单试）。

**(d) 学术一手证据**：Baron, Brogaard, Hagströmer, Kirilenko (2019, JFQA 54(3):993-1024) [Imperial College 开放仓储 PDF](https://spiral.imperial.ac.uk/bitstreams/efefa306-435f-471c-9e4e-087ee65fd4af/download) 完整读完。核心结论"differences in relative latency account for large differences in HFTs' trading performance"，交易收入"disproportionally accumulat[e] to a few firms"（定性表述，**没有找到一个量化的"前 X% 赚 Y%"具体百分比**，标记未核实）；扣除交易所手续费和流动性返佣后结论不变。核心延迟指标 DECISION_LATENCY（从被动成交到同一家公司下一次主动成交的间隔）：样本里最快的公司 **42 微秒**，最慢（且几乎不变）的公司均值 **25 毫秒**；有公司从 2010 年 1,280+ 微秒追到 2014 年逼近龙头的约 10 微秒。作为参照：纳斯达克 2012 年宣传材料自称"sub-40 microsecond latency"；CME Globex 2015 年 10 月宣传的中位入站延迟 52 微秒。数据来自瑞典股票市场（Nasdaq Stockholm），论文脚注提到早期版本在 E-mini标普期货 2010–2012 样本上得到类似结论。

**判定：not-feasible-for-us。** 经纪商和学术两条证据同时指向一个结论：我们既没有盘口/逐笔数据（只有 OHLCV+vwap+trade_count 分钟/日线），也没有托管，Alpaca Paper 官方文档自己承认不模拟排队位置和延迟滑点——而学术证据说这个游戏本质上是微秒级延迟的零和竞争。这条路线可以明确关闭，不用再有人重新提议。

## 6. 加密趋势/动量，一个可能的新市场

**(a) Zarattini, Pagani, Barbon "Catching Crypto Trends"**（SSRN [5209907](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907)，SSRN 本身对 WebFetch 和直接 curl 都返回 403/Cloudflare 挑战，未能打开）。改用论文合著者 Andrea Barbon 个人主页（[abarbon.com/papers/catching-crypto-trends](https://www.abarbon.com/papers/catching-crypto-trends)）和主作者 Carlo Zarattini 所在研究机构 Concretum 的两个页面（[concretumgroup.com](https://concretumgroup.com/catching-crypto-trends-a-tactical-approach-for-bitcoin-and-altcoins/)、[concretumgroup.substack.com](https://concretumgroup.substack.com/p/catching-crypto-trends)）直接打开，三处数字一致：BTC 单腿多头趋势策略，2015 年 1 月起，净费后 **CAGR 30%、夏普 1.56、最大回撤 −19%**（对比被动持有 BTC 回撤"exceeding 80%"）；Top 20 流动性最好币种的月度轮动版本：净费后 **CAGR 18%、最大回撤 −11%**、相对 BTC 的 alpha 约 10.8–11%。信号是 9 个不同回看窗口的 Donchian 通道突破集成 + 年化 25% 波动率目标仓位管理。

**这两个数字按字面值都够不到本项目的门槛**（≥50%/年且回撤≤35%，或夏普≥2 且≥30%/年）——BTC 单腿 30%/年、夏普 1.56 两条都不满足；Top20 版本 18%/年更是明显不够。这不是数据或算力问题，是证据本身不支持门槛。没有找到针对 2023-09 至 2025-12 这个"近期窗口"单独拆出的数字。

**(b) Liu, Tsyvinski, Wu (2022, Journal of Finance 77(3):1133-1177)**，一手 NBER 工作稿完整读完（[nber.org/system/files/working_papers/w25882/w25882.pdf](https://www.nber.org/system/files/working_papers/w25882/w25882.pdf)）。动量因子：周频价值加权五分位多空收益，"about 3 percent excess weekly returns (2.7 percent for one-week momentum, 3.3 percent for two-week momentum, 4.1 percent for three-week momentum, and 2.5 percent for four-week [momentum])"，均为统计显著。样本 2014 年初至 2018 年底，市值 $100 万以上的币种从 2014 年 109 个增长到 2018 年 1,583 个，总池 1,707 个币种，周频调仓。这是多空设计（我们做不了空），且样本止于 2018 年，没有近期证据；作为"加密市场存在动量"的学术背书是扎实的，但不是一条可以直接落地的规则。

**(c) Bitwise BTOP** —— 按项目规则应该先查"有没有人已经在实盘跟踪"，查到的结果本身就是一条重要提示。直接打开发行方官网 [btopetf.com](https://btopetf.com/)：2023-09-29 上市，用比特币 10 日和 20 日 EMA 作趋势信号，上涨期等权持有 BTC/ETH 的 CME 期货，下跌期转为 100% 短期美国国债（"The Fund does not invest directly in bitcoin or ether"）；截至最后一次公布数据（2026-03-30）的"Since Inception"表现为 NAV 30.70% / 市价 30.68%（是否为累计还是年化未在页面说明，未核实）。**该基金已于 2026-05-29 被发行方清盘**（在 issuer 自己的页面上确认）。也就是说：一个由主流发行商推出、跑了约 2.7 年、账面上不算亏钱的加密趋势实盘产品，还是被下架了——这条负面（或至少是警示性）信息是我们自己回测不会告诉我们的，值得记一笔。产品用的是 CME 期货而非现货，与我们的现货账户场地本来就不匹配。

**(d) Alpaca 加密基础设施**：官方 FAQ 和文档直接打开（[alpaca.markets/support/crypto-maker-taker-gmt-faq](https://alpaca.markets/support/crypto-maker-taker-gmt-faq)、[docs.alpaca.markets/docs/crypto-trading](https://docs.alpaca.markets/docs/crypto-trading)）：maker/taker 阶梯手续费，最低档（30 日交易量 $0–$10 万）0.15%/0.25%，最高档（$1 亿+）0%/0.10%；"支持 20+ 种加密资产、56 个交易对"，交易对以 BTC/USD/USDT/USDC 为基础。加密交易文档里给的 curl 示例打的是 `paper-api.alpaca.markets/v2/orders`，暗示 Paper 账户支持加密下单，但**没有一页用明文直接说"加密支持 Paper 交易"**；历史 K 线数据最早覆盖到哪一年，两页都没写，未核实。

**判定**：6a/6b 都是 evidence-too-weak（6a 是数字够不到门槛，6b 是设计不匹配+过时）；6c 是 not-feasible-for-us（错的场地，且产品已下架）；6d 本身不是一个"策略主张"而是基础设施问题，是 reproduce-cheap——两个文档空白（Paper 是否支持、历史数据起点）都可以用一次操作性检查（比如真的去 Paper 账户下一笔加密单、查一下最早能拉到哪天的 K 线）秒杀，不需要额外的研究算力。

## 7. RD-Agent(Q)（微软，arXiv 2505.15155）

一手论文 PDF 完整读完（[arxiv.org/pdf/2505.15155](https://arxiv.org/pdf/2505.15155)，NeurIPS 2025 接收）。**注意**：论文 Table 2（CSI500+NASDAQ100 并排的汇总表）和 Table 8（NASDAQ100 专表）在 PDF 双栏排版下用 `pdftotext -layout` 抽取时会把两张表的数字错位拼接，我们逐行核对两张表消除了这个歧义后才引用下面的数字。

NASDAQ100 样本外测试（测试窗口 **2024 年至 2025 年 6 月**，约 18 个月；组合规则是每期选前 20 只，交易成本 0.1%/笔，无涨跌停限制——对比 CSI300 设置用 50 只、0.5% 成本）：R&D-Agent(Q)（o4-mini 版）IC 0.0162，ICIR 0.1035，**年化收益 28.40%**，IR（类夏普）1.7737，最大回撤 −6.34%，Calmar 4.4814；R&D-Agent(Q)（GPT-4o 版）年化 23.28%，IR 1.3312，回撤 −10.44%。同一窗口里，最好的经典因子库基线（Alpha360）只有年化 7.56%、IR 0.5890、回撤 −11.82%；**LightGBM 基线在这个窗口反而亏钱**（年化 −2.93%、IR −0.2603、回撤 −13.42%）。

GitHub README（[github.com/microsoft/RD-Agent](https://github.com/microsoft/RD-Agent)）直接读：**"Users must ensure Docker is installed before attempting most scenarios"**——Docker 是大多数场景的硬性前提，不是可选项；框架"now support[s] LiteLLM as a backend"，并给出了接入 DeepSeek 等 OpenAI 兼容端点的配置示例（这点对我们有利，能接现有的 DeepSeek 评分端点）；README **全文没有给出最低内存或 GPU 要求**。搜索没有找到任何非微软作者的独立复现报告（只找到论文本身、微软研究院自己的镜像页、以及一篇仅转述论文数字、并未自己重新跑一遍的爱好者博客）。

**判定：not-feasible-for-us。** 关键不在于 NASDAQ100 那组数字本身（那组数字在 18 个月的短窗口里、连 LightGBM 都会亏钱的市况下取得，多重检验/短样本过拟合风险不低，值得存疑而非照单全收），而在于跑这套框架需要的东西：Docker 是硬性要求，而框架比较表里那一串深度学习基线（GRU/LSTM/Transformer/GATs/iTransformer/TRA）说明"Development 阶段"很可能隐含反复训练小型深度学习模型——这是我们基于框架实际做什么得出的推断，不是 README 里的原话。3.9GB 内存、无 GPU、无 AVX2 的机器上跑 Docker 化的多智能体循环 + 深度学习训练，大概率跑不动或跑得极慢。

## 8. Kronos（arXiv 2508.02739）

GitHub README（[github.com/shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos)）直接读：四个规格——Kronos-mini（4.1M 参数）、Kronos-small（24.7M）、Kronos-base（102.3M）、Kronos-large（499.2M），**MIT 协议**；mini/small/base 权重在 Hugging Face（NeoQuasar 组织）公开可下载，**large 权重未公开**。GitHub issue [#273](https://github.com/shiyu-coder/Kronos/issues/273)（2026-04-19 开）是一个第三方询问 Kronos-large 商用授权、用于美股生产平台的请求，截至我们检查时（2026-09-23）**没有维护者回复**，即已挂了 5 个多月无人处理。

论文正文描述的训练/评估硬件是 3 个 Kubernetes pod，每个 96 核 CPU（Intel Xeon Gold 6330）+ 200GB 内存 + 8 张 RTX 4090D，合计 24 张 GPU——这是训练用的重度 GPU 基础设施，不直接等于推理的最低要求。README 全文**没有一处提到 CPU-only 推理**；GitHub issue [#66](https://github.com/shiyu-coder/Kronos/issues/66)（"各个模型需要什么样的 GPU 及显存才能够流畅运行模型？"）同样**没有维护者回复**。也就是说，CPU 推理是否可行——对任何一个规格，包括最小的 4.1M 参数版——是真正的文档空白，不是"文档说不行"，是"没人写"。我们的机器还有一个来源完全没提到的额外风险：无 AVX2，很多预编译 PyTorch wheel 依赖 AVX2，可能直接跑不起来或要从源码编译。

独立评测（美股、2025-08 之后、扣成本的可交易数字）：**一个都没找到**。找到的独立评论里最有价值的一条来自独立量化研究者 Jonathan Kinlay 的博客（2026 年 2 月）[jonathankinlay.com](https://jonathankinlay.com/2026/02/time-series-foundation-models-for-financial-markets-kronos-and-the-rise-of-pre-trained-market-models/)，直接打开确认：他**自己没有测试 Kronos**（原话："Since Kronos is not yet publicly available, we can demonstrate the foundation model approach using Amazon's Chronos [instead]"），并指出"the paper benchmarks on MSE and CRPS — statistical metrics, not economic ones"，明确写道："A forecast that's statistically significant but not economically significant after transaction costs is useless for trading... **Show me a backtest with realistic execution costs before calling this a trading signal**... don't deploy for live trading until someone demonstrates economically exploitable returns after costs."——一个同情这类方法的独立评论者都明确拒绝背书，而且明确指出目前没人给出这个背书。

**判定：evidence-too-weak。** 论文自身的 IC/RankIC 类数字（声称比通用 TSFM 高 93% 的排序 IC）是统计指标，不是交易指标；CPU 可行性和授权状态都是悬而未决的空白；没有任何人（不论作者还是第三方）给出过一个扣成本的可交易结果。这与我们已知的本地背景一致（据交接记录，TimesFM/Chronos 这类零样本时序基础模型此前已在本地测过并因负 R² 被否定）——Kronos 架构上是同类"K 线基础模型做零样本预测"的思路，在没有新的可交易证据之前，不值得优先分配算力去验证。

---

## 未能核实的点（清单）

1. Amaya-Christoffersen-Jacobs-Vasquez **最终发表版**（2015 JFE）的精确基点数字/t 值——SSRN 和 ScienceDirect 都拒绝抓取，只读到了 2011 工作稿（24bp，t=3.65，十分位）；网上常见转述的"19bp，t=3.70，五分位"未被我们独立打开核实。
2. RSJ（符号跳跃变差）在**美股、2013 年之后**的独立样本外检验——没找到；找到的都是中国 A 股的后续复现（2023、2025），未直接打开原文，标记未核实。
3. Baron et al (2019) 里一个量化的"HFT 利润集中度"百分比（例如"前 X% 的公司赚 Y% 的利润"）——只确认了定性表述，没有找到具体数字。
4. Alpaca **Paper 账户**的 PDT 拒单逻辑是否已经真的按 2026-06-04 生效的新版 FINRA 日内保证金规则更新——两份官方文档口径不完全对齐，没找到把二者显式对齐的页面。
5. Zarattini-Pagani-Barbon 加密趋势论文的精确数字来自作者自己机构的两个二手页面（Concretum 官网+ Substack）交叉核对，**不是** SSRN 原文本身（403 打不开）；如果这条要往前推进，值得再想办法拿到 PDF 原文核对表格细节和成本假设的确切定义。
6. Bitwise BTOP"Since Inception"30.70%/30.68% 这个数字是累计还是年化，官网页面没有说明。
7. Alpaca 加密业务是否明文支持 Paper 账户下单、历史 K 线数据最早覆盖到哪一年——两个官方页面都没有明文说明。
8. RD-Agent(Q) 官方 README 未给出最低内存/GPU 要求（这本身是一个确认过的"空白"，不是我们没找到）。
9. RD-Agent(Q) 在 NASDAQ100 上的优势能否延续到测试窗口（2024–2025/06）之外——框架发布太新，没有更长样本可查。
10. Kronos 是否支持 CPU-only 推理，对任一模型规格——README 和两个相关 GitHub issue 都没有维护者给出确认或否认。
11. Kronos-large 的商用授权条款（含是否允许美股场景）——issue 挂了 5 个多月无人回复。
12. 方正证券"适度冒险"、东吴证券"量价因子"的精确定义、样本区间、成本处理——只做了搜索，没有直接打开原始或二手页面，标记未核实。
