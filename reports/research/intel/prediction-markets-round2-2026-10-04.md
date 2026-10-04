# 预测市场方向调研（第二轮）：赔率能否变成美股/ETF/加密现货的可交易规则

协调码 R1004-0112-PMI。抓取时间（date -u）：2026-10-04 01:12:23 至 01:21:14 UTC。只做调研，不跑回测，不写预注册。
原文快照与接口实测记录：`reports/research/intel/sources/prediction-markets-round2-2026-10-04/`（下称 sources/）；其中 `web-extractions-and-api-probes.md` 标明哪些是原文、哪些是二手摘录。

## 1. 结论（先看这里）

1. 学术上"赔率预测股价"的直接证据只有一篇有交易检验：Goldstein-Li-Wang（2026-09-03 版）。样本是 2024 年大选一个事件，样本内、未扣成本、无独立复现。
2. 宏观侧的一手研究（FEDS 2026-010、Angelini 2026）只证明 Kalshi 的分布准确，没有一处检验股票收益（FEDS 全文 grep stock/equity/S&P/VIX，无收益检验）。
3. 值得做的新方向是公司层面：Polymarket 的"X 公司本季是否超预期"合约。已结算 1354 个（2025-09 至 2026-10），每个财报季约 450 个，样本增长快，登记表里没有同类条目。
4. 推荐第一个实验：财报超预期赔率对公告窗口收益的预测力（候选 A）。第二个是用同一套价格抓取做的政策赔率领先滞后样本外检验（候选 B），成本很低。

## 2. 查询词

英文检索（WebSearch，2026-10-04）：prediction markets Polymarket Kalshi odds predict stock returns tariffs；Polymarket election odds sector returns Trump trade event study；Kalshi recession probability equity returns SSRN/arXiv/NBER；Kalshi Fed odds vs fed funds futures FEDS；arXiv prediction market lead financial markets tariff；Iran strike odds oil energy stocks；Polymarket Binance lead-lag OpenMarket；Kalshi S&P range implied volatility vs VIX；Snowberg Wolfers Zitzewitz partisan impacts；Supreme Court IEEPA tariff ruling odds stocks；Wolfers Zitzewitz Iraq war oil S&P；Polymarket earnings beat accuracy stock reaction；Rabetti Shao Zhang "Beating the Earnings Game"；Gómez-Cram Guo Jensen Kung financial prediction markets；midterms 2026 odds sector ETF；backtest Polymarket probability lead SPY QQQ。
登记表：`oc research directions check` 查 prediction market polymarket kalshi / earnings announcement / earnings surprise / tariff / geopolitical oil / recession probability。

## 3. 来源与关键数字（读原文者标"原文"，否则标"二手"）

- Goldstein, Li, Wang, "Learning from Prediction Markets", 2026-09-03（原文，`wang-learning-from-prediction-markets.txt`）。数据 Polymarket 2024-01-05 至 2024-11-05。Trump 获胜概率每升 1 个百分点，次日"Trump trades"收益 +13 bp（合并样本，7,618 个观测）；与总统选举联系紧的资产 +42 bp，第 2 天 -23.5 bp 部分反转。策略：ΔP 做 5 日 EMA，转为 60 日滚动分位，仓位 [-1,1]，滞后一天；2024-04-01 至 11-05 年化 18.93%、波动 9.72%、Sharpe 1.95、总收益 16.45%、最大回撤 4.58%。论文自己写明"样本内、未计交易成本"。资产清单含 SPY QQQ IWM DIA XLF KRE XLI XLE XAR 与六只银行股，Alpaca 都能交易。散户噪声部分两天内反转，知情资金部分持续三天。
- Diercks, Katz, Wright, FEDS 2026-010（原文，`feds-2026-010-diercks-katz-wright.txt`）。FOMC 前一天 Kalshi 的众数每次都对（2022 起），对联邦基金期货的改进统计显著；150 天前 FOMC 的平均绝对误差与纽约联储 SME 相近；头条 CPI 显著优于 Bloomberg 共识，核心 CPI 与失业率相近。数据发布后利率分布方差下降。没有股票收益检验。
- Leigh, Wolfers, Zitzewitz, NBER w9587（2003，原文，`nber-w9587-...txt`）。战争概率每升 10 个百分点：油价约 +1 美元/桶（3-4%），标普 500 约 -1.5%；同期 30% 的标普波动和 75% 的现货油价波动可用战争概率解释。年代久，只作机制依据。
- Snowberg, Wolfers, Zitzewitz, QJE 2007 / NBER w12073（二手，搜索摘要）：2004 年选举夜高频数据，共和党当选使股票估值约 +2%-3%。
- Gómez-Cram, Guo, Jensen, Kung, SSRN 5933475，2025-12 首发、2026-03 更新（二手，全文 403）。Polymarket 财报合约隐含预期比分析师更准、更无偏、对公告收益有增量信息、价格发现领先；前 1 天正确分类 77%（分析师 62%）；前 1 天 81% 的合约定价在 50 美分以上，实际 beat 率 74%，均价 0.71，"区分度好、校准偏乐观"；同时存在短期过度反应。样本约两个月。
- Rabetti, Shao, Zhang, SSRN 6649938，2026-04（二手）。469 个合约、383 家公司，2025-09 至 2026-02；市场 78.5% 对 分析师共识 43.7%；同期 beat 基准率 75.9%。注意：永远猜"beat"就有约 76% 的命中率，78.5% 只比它高约 2.6 个百分点；"赢过分析师"主要是共识口径（约等于抛硬币）造成的。
- OpenMarket, arXiv 2607.26245（二手摘要）：Binance 大幅波动后约 347 ms Polymarket 报价才响应。方向是现货领先赔率，且是亚秒级，Alpaca 做不了。
- 负面/风险：Abid, SSRN 6670638（二手）：一个交易者 11 个钱包在 2024 年 10 月把 Trump 概率抬高 10-15 个百分点；Sherwood 2025-11-05：关税敏感股篮子（UBS）当日 +3.7%，同时 Polymarket"维持关税"概率日内从 >50% 降到约 18% 再回到约 30%，赔率与股价同日同向，不能判断谁先动。
- 搜索未找到：独立的 Goldstein-Li-Wang 复现；2025-2026 年关税、衰退、停摆赔率对板块 ETF 的任何同行评审检验；"Wall Street Quants See an Edge in Polymarket Earnings Forecasts"（Bloomberg 2026-04-16）全文 403，只有标题，不能当证据。

## 4. 数据可得性（只看元数据 + 约 25 个小请求）

- HF `TimeSeventeen/Polymarket-v1`：许可 cc-by-4.0（README 与 HF 元数据一致）。文件：OrderFilled 42 个月文件共 27.4 GB（2026_04 单月 5.5 GB）；CTF 5 个表共 8.5 GB；daily_aligned（二元市场）前 1000 个文件 591 MB（列表分页截断在 2025_08_23）；daily_aligned_multi 857 个文件 3.63 GB（2023_12_22 至 2026_04_28）。
  - 粒度是逐笔成交（price、p_event、block_timestamp、market_slug、category_refined），没有逐日价格表，没有盘口；按 UTC 日分文件。
  - 单日文件小：2025_04_09 的 daily_aligned 1.6 MB，66,931 笔，984 个市场，含 us-recession-in-2025（858 笔）、对华 54% 关税、5 月降息等；daily_aligned_multi 2.2 MB。覆盖 2025 年关税、衰退、美联储，没核对停摆和选举。全量远超 50 MB，只能按日期和市场切片，或上 Modal。
- Polymarket Gamma + CLOB（免费、无密钥）：`/prices-history` 对已结算市场可回溯，"US recession in 2025?"日频 359 个点（2025-01-09 至 2026-01-01）；小时线需用 startTs/endTs 窗口（一周窗口 168 点），`interval=max&fidelity=60` 返回空；`fidelity=1` 一周 10,080 点。限速（官方文档）：/prices-history 1000 次/10 秒，/events 500、/markets 300、/public-search 350，Cloudflare 排队不拒绝。
- Polymarket 财报合约：Gamma 已结算 1354 个，成交额分位数 10/25/50/75/90% = 915/2534/6310/14904/30097 美元；>=5k 美元 785 个，>=10k 美元 486 个。规则：共识非 GAAP EPS，严格大于才算 Yes（TSLA 2025-10 样本：共识 0.50，末日价约 0.83，结果 No）。市场很薄，价格噪声大。清单见 `polymarket-earnings-events-closed-gamma-2026-10-04.json`。
- Kalshi 公共接口（无密钥）：14,584 个系列；94 个带 tariff；shutdown 最早 2021-09-28（KXGOVSHUT）、Fed 主席提名 2024-12-18、加拿大关税 2025-03-18、全面关税 2025-04-02。公司 KPI 类（Starbucks、Carnival 等）2026-06 才开，历史太短。成交量字段此次读到 0，待核对。
- 本地可复用：`data/features/earnings_events/{2024,2025,2026}.parquet`（8-K 2.02 的 acceptance_utc，可判盘前/盘后）、SIP 日线、`price_hygiene`、上一轮 Kalshi 抓取代码。

## 5. 候选排序

### A. 财报超预期赔率 -> 公告窗口收益（推荐第一个做）
- 机制：Polymarket 财报合约比分析师共识更准（二手）；若股价没有完全吸收这份信息，P(beat) 高的公司公告窗口超额收益更高，反之更低。
- 证据：Gómez-Cram 等"对公告收益有增量信息"（二手，未读到系数）；Rabetti 等 78.5% 对基准 75.9%（区分度弱）。反面：市场对 beat 校准偏乐观（81% 定价 >50 美分，实际 74%）；公告收益取决于相对股价预期的惊喜，不是相对共识；两篇都是 2-6 个月、未发表。
- 数据：免费、点时。Gamma 清单 + CLOB 小时价（2025-09 起），公告时刻用本地 8-K 2.02 表。无需 Modal，约 1354 次小请求。
- 样本与功效：N=1354（高流动性子集 486）。假设公告窗口超额收益标准差 6%（待用本地数据核对）：高低三分位价差的标准误 N=1354 时约 40 bp，最小可检测 112 bp（80% 功效、双侧 5%）；N=785 为 147 bp，N=486 为 187 bp（用 2.8×SE 计算，见本轮 Python 输出）。结论：现在只能分辨 100 bp 以上的价差；更小的效应要靠前向累积（每季 +450 个）。
- 最便宜的否定测试：流动性前 486 个合约，P(beat) 的横截面排序对窗口超额收益的 Spearman IC 与三分位价差；安慰剂：周内打乱 P、用 7 天前的 P；对照"只用上季是否 beat"这类无赔率基线。几小时内能出结果。
- 交易与成本：多高 P、空低 P，个股，每边 10 bp；空头只做易借股并计借券费；公告日点差和跳空滑点要加压力情形。已有先例：上一轮用 15:00 ET 前的信号配 MOC 成交。
- 与登记表差别：登记表的财报条目（SUE/PEAD、8-K 语气、收益-盈余缺口、盈利公告溢价）都用财报文本或财务数据，没有一个用预测市场价格；这是新信息源。

### B. 政策赔率领先滞后：Goldstein-Li-Wang 的样本外检验
- 机制：散户和交易者从 Polymarket 价格学习政策消息，次日在相关资产上反应，随后部分反转。
- 证据：13 bp/百分点，Sharpe 1.95（样本内、无成本、单事件）。只有 2024 大选一个样本，没有独立复现。
- 数据：CLOB 日频免费，2024 起；2025-2026 有 us-recession、关税、Fed 路径、停摆、最高法院关税案；篮子用 SPY QQQ IWM XLF KRE XLE XAR TLT 等，Alpaca 可交易。
- 功效：2025-01 至 2026-09 约 440 个交易日；有效样本按 150-440 估，最小可检测相关系数 0.23 至 0.13。论文隐含相关约 0.26（若 ΔP 日标准差 2 个百分点、篮子日标准差 1%，这两个是假设，待核对）。冲击集中在少数几个政策事件上，有效样本偏低。
- 最便宜的否定测试：冻结论文的 5 日 EMA + 60 日分位变换，在 2025-2026 的 15-20 个高流动性政策市场上做次日收益检验，加"换市场/换日期"安慰剂。一天内能做完，与候选 A 共用 CLOB 抓取。
- 交易与成本：ETF 多空，每边 10 bp，次日换手较高。
- 与登记表差别：`dir:prediction_market_crypto_as_equity_signal`（evidence_too_weak）是泛泛的赔率领先滞后；本条有明确机制与新论文，但仍是单篇未发表论文，只够当样本外的杀伤测试，不是重开方向。

### C. 战争/地缘赔率 -> 油价、能源、国防、标普
- 机制：战争概率每升 10 个百分点，油价 +3-4%、标普 -1.5%（Leigh 等，2003，原文）。2026 年有 Iran/Hormuz 市场且成交活跃。
- 证据：机制强，但是同期关系，没有证明赔率领先；2023-2026 年没有一手检验。
- 数据：Gamma/CLOB 小时线可取；逐笔在 Polymarket-v1 可切片。
- 功效：独立战争事件约 2-3 个（2025-06、2026-03 前后），只能做事件研究，不能做统计检验。
- 否定测试：几个事件内赔率 ΔP 与同日小时 USO/XLE/ITA/SPY 收益，看赔率是否先动。
- 与登记表差别：登记表没有地缘赔率条目；`narrow_industry_etf_momentum_rotation` 是动量，不重复。放在 B 之后，复用 B 的管线。

### D. 2026-11-03 中期选举赔率 -> 板块（只作前向观察）
- 机制：SWZ 2007，政党结果改变板块估值（共和党当选使估值约 +2%-3%，二手）。
- 数据：Kalshi/Polymarket 国会控制市场，免费。众议院民主党约 81%-85%（二手），多数已被定价。
- 功效：一个事件，没有统计功效；价值只在于给 B 提供一个真正的前向样本外窗口（距今 1 个月）。不单独立项。

### 不做/停放
- 衰退赔率作择时状态：只有 2025 年 4 月一个冲击，相对 VIX、信用利差的增量无法检验，建议不开。
- Kalshi 与联邦基金期货的分歧：FEDS 只证明 Kalshi 预测利率更准，没有股票收益关联；FOMC 样本约 28 次；期货点时数据要付费；这是预测市场内部套利，不是我们能交易的。
- Polymarket BTC 15 分钟市场 vs Binance：赔率滞后现货约 347 ms，方向相反且 Alpaca 无法执行。
- Kalshi 标普/纳指区间市场当波动率曲面：等价于期权隐含分布，期权方向因不买付费数据而停放；VIX1D 免费且更直接。
- 公司 KPI 与"提及"市场：2026-06 才开，历史短；提及类与股价无机制联系。
- 知情钱包识别（Goldstein 等用逐笔链上数据）：需要 OrderFilled 逐笔（27 GB），超过 50 MB 与本机内存，应在 A/B 有信号之后再上 Modal。
- 交易预测市场本身：不在授权范围。

## 6. 推荐的第一个可证伪实验（设计要点，不含预注册文件）

- 命题：Polymarket 财报超预期价格对 beat 之外的公告窗口超额收益有增量预测力。
- 样本：Gamma 已结算财报事件（2025-09 至 2026-10，1354 个），主检验按成交额预设门槛（如 >=5k 美元）；先报覆盖率（CLOB 小时价能取到的比例；老市场历史可能被裁剪）。
- 信号时点：公告前最后一个小时价，不晚于 15:00 ET（盘前报 T-1 日，盘后报 T 日），判断盘前盘后用 8-K 2.02 的 acceptance_utc；用同周横截面排序去掉整体乐观偏差。
- 成交与退出：信号后 MOC 入场，反应日收盘退出；次要口径用次日开盘退出。冻结规则写的是"收盘信号、次日开盘成交"，MOC 先例来自上一轮，预注册时要明确采用哪一种，不能事后换。
- 检验：高低三分位价差和 IC；每边 10 bp 加公告日点差压力；空头仅易借股并计借券费；周内置换、7 天前价格、"上季是否 beat"基线三个安慰剂；日期聚类标准误。
- 停止规则（预注册时定数）：可用事件不少于 1000 个后，净价差不过正或不优于安慰剂即否定；功效不足（最小可检测约 100 bp）写明，不得因此放宽门槛。通过则转前向影子，扩展现有每小时采集器的观察清单，不用等历史。
- 资源：不上 Modal；CLOB 约 1354 次小请求（远低于限速），SIP 日线（代码数待从事件标题统计，估计数百个），1.8 GB 内可跑。
- 同日并行（可选）：候选 B 的样本外杀伤测试，共用价格抓取。

## 7. 未完成/待核对

- Gómez-Cram 等和 Rabetti 等全文未读到（SSRN 403），公告收益回归系数未知；预注册前应再试其他镜像或作者主页。
- Kalshi 历史市场成交量字段读到 0，流动性待核对。
- 公告窗口收益标准差 6% 和 ΔP 标准差 2 个百分点是假设，需用本地数据核对后再定功效。
- 本轮没有核对 Polymarket-v1 是否覆盖停摆和选举市场。
