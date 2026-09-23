# I-20260922-03：巨人的肩膀普查（一次性扫荡，2026-09-22）

四个 Sonnet 采集员并行，各扫一个来源池；主会话汇总。数字均为来源原文，未本地复算；"未核实"表示付费墙或未找到一手来源。用途：喂给 `scripts/run_giants_sweep.py` 的 manifest（见 `reports/research/briefs/ENGINE-giants-sweep-2026-09-22.md`）。

## D. 零售杠杆 ETF 与波动率 ETP 经典（公开记录，2025–2026）

| 名称 | 规则 | 2024–2026 报告表现 | 来源类型 | 风险 | 数据 |
|---|---|---|---|---|---|
| HFEA 55/45（UPRO/TMF）[Bogleheads t=288192](https://www.bogleheads.org/forum/viewtopic.php?t=288192) | 55% UPRO + 45% TMF，季度再平衡 | 作者实盘累计 2024-04 +26%、2024-10 +46%、2025-04 +37%；2022 年 −64%（55/45）；最大回撤 −70.8%（2023-10），两年未回本 | 社区个人实盘 | 股债同跌、加息周期 | UPRO、TMF 日线 |
| 9-Sig（TQQQ + AGG）[PortfoliosLab](https://portfolioslab.com/portfolio/vyshlq6kapi8qy8rdgibte59) | 信号线季度 +9%，季度再平衡，债券下限 10% | 2010-02→2026-04 CAGR 39.4%、回撤 −72.1%；近 12 月夏普 1.20 | 第三方回测 | 回撤 72%–99.7% | TQQQ、AGG 日线 |
| Leverage for the Long Run（Gayed & Bilello）[SSRN 3718828](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID3718828_code2224980.pdf) | 标普收于 200 日线上方持 2–3x，否则国库券 | 1928–2015 2x 夏普 0.51 vs 0.30；2024–26 未核实 | 论文 + 大量复现 | 震荡市反复止损；本地 L-20260918-05 同族在 2023–26 窗口不过安慰剂 | 标普、T-bill |
| TQQQ 200 日线趋势 [GitHub WildWest000](https://github.com/WildWest000/tqqq-trading-strategy) | 收盘 > 200 日线持有，否则清仓 | 2020-01→2026-06 总回报 ~917% vs 买持 661%，回撤 −42% vs −82% | 个人回测 | 未计滑点 | TQQQ 日线 |
| Composer《TQQQ RSI Strategy》[链接](https://www.composer.trade/trading-strategies/tqqq-rsi-strategy-Lh0fYfA5RJQmpyfGEORb) | 200 日线定趋势 + RSI/PPO 超买超卖买 TQQQ，否则短债 | 2025 YTD +37.8%，回撤 −23.5% | 平台展示 | 口径不透明 | TQQQ、短债 ETF |
| Composer《TQQQ Safe Strategy》[链接](https://www.composer.trade/trading-strategies/tqqq-safe-strategy-5Hta0uxaYbx5NktfwlWF) | QQQ > 200 日线持 TQQQ（强 100% / 弱 70%+30% 国库券），RSI<30 补仓 / >78 转短债 | 2025 YTD +38.4%，回撤 −28.9% | 平台展示 | 参数多 | QQQ、TQQQ、国库券 ETF |
| Composer《TQQQ FTLT 2.0》[链接](https://www.composer.trade/trading-strategies/tqqq-ftlt-20-iM4mdWcn3DPeUNZPsYNW) | 多资产宏观/趋势轮动（TQQQ/TECL/UPRO/UDOW/SVXY），细则未核实 | 2025 YTD +48.7%，回撤 −47.3% | 平台展示 | 回撤接近裸持 3x | 多只 3x + SVXY |
| Composer《TQQQ/SQQQ 动量反转》[链接](https://www.composer.trade/trading-strategies/tqqqsqqq-0BfsbDtcVcDNFVEsQgra) | TQQQ 10 日涨 >31% 买 SQQQ；SQQQ 10 日涨 >25% 买 TQQQ；TQQQ RSI(10)<31 买 TECL | 未核实 | 平台页 | 双向杠杆反复切换 | TQQQ、SQQQ、TECL |
| Composer《SOXL RSI》[链接](https://www.composer.trade/trading-strategies/soxl-rsi-strategy-XJKF0TG7NrcX33NQrfyW) | 趋势 + 深回调加仓，超买转 SOXS/债券/UVXY | 未核实（SOXL 2025 +56%，2026Q1 回撤 −55%） | 平台页 | 季度回撤可超 50% | SOXL、SOXS |
| VIX 期限结构四象限做空波动率 [Concretum](https://concretumgroup.substack.com/p/automating-a-volatility-strategy) | eVRP>0 且 VIX<VIX3M 满仓做空波动率；contango 但 eVRP≤0 半仓；backwardation 且两信号负转做多 | 2008→2025-05 回测，90% 时间做空；收益未核实 | 独立回测 | 2018-02 Volmageddon | VIX、VIX3M、VX 期货 —— **本机无期货，暂不可跑** |
| NTSX（90/60）、RSSB（100/100）公开净值 | 基金内置杠杆 1.5x–2x 股债 | NTSX 近 12 月 +19.8%，史上回撤 −31.3%；RSSB 近 12 月 +22.3%，回撤 −16.2% | 基金实盘 | RSSB 历史短 | 基金净值（可直接买） |
| TQQQ/TMF 50/50 两月再平衡 [Medium](https://medium.com/@setupalpha.capital/3x-leveraged-etf-strategy-2-600-return-with-38-drawdown-trading-strategy-rules-f4dad806bc25) | 各 50%，每两月再平衡 | 2010→2025-10 CAGR 23.8%，回撤 −38.7%，夏普 0.95 | 个人回测 | 股债双杀 | TQQQ、TMF |
| Logical Invest UISX3 [链接](https://logical-invest.com/app/strategy/uisx3/) | 资产配置模型 3x 版，细则未核实 | 自 2002 年化 45%、夏普 1.3（未核实） | 商业订阅 | 近两年样本外未核实 | 未公开 |

D 组结论：(1) 长记录的是 HFEA / 9-Sig，也是最惨的公开先例（−70%/−72%）；(2) Composer 上 TQQQ 趋势+RSI 类给出 2025 年 38%–49%，无第三方验证；(3) 做空波动率有 2018 年清零先例，且本机无 VIX 期货数据；(4) NTSX/RSSB 风险调整后最稳但收益不"爆炸"；(5) 200 日线择时被大量复现，能把 3x 回撤减半，但本地窗口内不过安慰剂。**进引擎的**：HFEA 与 TQQQ/TMF 固定权重族（`fixed_weights`）、9-Sig（`signal_growth`）、TQQQ/QQQ 趋势+RSI 分支族（`gate` 嵌套，与 B-1 合并）、TQQQ/SQQQ 动量反转（`gate`）。**不进**：VIX 期限结构（无数据）、UISX3（规则不公开）。

## B. TAA 经典（Allocate Smartly 跟踪范围；规则全部免费公开，近期数字在付费墙后）

| 策略 | 规则要点 | 已知数字 | 数据 | 进引擎 |
|---|---|---|---|---|
| Keller BAA [SSRN 4166845](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4166845) | canary（SPY/EFA/EEM/AGG）任一 13612W 动量 ≤ 0 → 防御篮（TIP/DBC/BIL/IEF/TLT/LQD/AGG 按绝对动量选）；否则进攻篮相对动量选 1；月频 | 原文 1970–2022 年化 ≥ 20%、月度回撤 ≤ 15%；AS 提示"历史过拟合"；近期未核实 | 全为美股 ETF 日线 | 是（`canary`）|
| Keller DAA [SSRN 3212862](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3212862) | canary VWO/BND 决定防御比例 0/50/100%；风险篮相对动量 | 第三方称 CAGR 13.7% | 同上 + SHY | 是 |
| Keller HAA [SSRN 4346906](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4346906) | BAA 简化，单 canary（TIP）转负则半/全防御 | AS 会员占比第 2；近期未核实 | 少量 ETF | 是 |
| Keller PAA / VAA / GPM [SSRN 2759734](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2759734) / [3002624](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3002624) / [AS](https://allocatesmartly.com/keuning-kellers-generalized-protective-momentum/) | 广度动量（正动量资产数）决定防御权重；VAA 用 13612W；GPM 加相关性调整 | VAA G4 第三方 CAGR 16.3%；其余未核实 | 全球资产 ETF | 是 |
| Antonacci GEM / 复合双动量 | SPY vs BIL 绝对 + SPY vs VEU 相对，负则 AGG；复合版 5 组资产对 | 官方长期 CAGR 15.2%、回撤 −21.7% | SPY VEU AGG BIL | 是（`abs_filter`+`rank`）|
| Faber GTAA 5/13、Ivy、Trinity | 各资产 10 月 SMA 上方持有否则现金；Trinity 50% 静态 + 50% 趋势 | 2008 回撤 −8.5%；近期未核实 | 5–13 类 ETF | 是（`gate: sma`）|
| Accelerating Dual Momentum [AS](https://allocatesmartly.com/taa-strategy-accelerating-dual-momentum/) | SPY vs SCZ 1/3/6 月均值动量取正且高者；都负转 TLT/TIP | 未核实 | SPY SCZ TLT TIP | 是 |
| Keller LAA [SSRN 3498092](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3498092) | 失业率趋势 + SPX 趋势同时转空才现金 | 未核实 | 需 FRED 失业率 | 否（宏观序列，第二批）|
| Kipnis KDA、Varadi 最小相关 | 1-3-6-12 动量选前 5 + 最小方差配权；最小相关是权重算法 | 第三方 CAGR 10.9% | ETF 池 + 协方差 | 第二批 |

B 组结论：规则全免费可复现，Alpaca 全能执行；预期收益 10%–20%，不"爆炸"，价值在于 **canary/广度防御逻辑**可作为杠杆执行的风险开关（把 BAA/VAA 信号叠到 UPRO/TQQQ/TMF 上是引擎里要测的变体）；AS 不跟踪杠杆策略，所以这类变体没有公开记录，只能本地验。

## C. 2024–2026 学术（SSRN 原文多为 403，数字来自检索摘要）

| 论文 | 规则 | 报告指标 | 数据 | 进引擎 |
|---|---|---|---|---|
| Zarattini & Antonacci 2024《A Century of Profitable Industry Trends》[SSRN 4857230](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4857230) | 48 行业组合多头时序动量趋势跟踪 | 1926–2024 年化 18.2%、波动 12.6%、夏普 1.39 vs 市场 0.63 | 行业指数/行业 ETF 日线 | 是（行业 ETF 菜单 + `gate: sma`/时序动量）|
| "Weekly Seasonality in Overnight Effects"（Redfame AEF 2025-07） | QQQ 隔夜多头、跳过周五夜 | 夏普 7.75（可疑） | 日线开收盘 | 是，但成本档 1/2/5 bp（`overnight` 原语）|
| Lin et al. 2025《Volatility Decay and Arbitrage in LETFs》[SSRN 5421274](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5421274)；Khadivar 2024 | 贝塔中性做空杠杆 ETF 对吃衰减 | 夏普最高 2.12（摘要） | 日线 | 研究单列（需做空，非现有彩排通道）|
| Harvey/Mazzoleni/Melone 2025《Unintended Consequences of Rebalancing》[SSRN 5122748](https://ssrn.com/abstract=5122748) | 月末指数再平衡流可预测 | 无策略端夏普 | 需再平衡日历 | 第二批 |
| Chen et al.《Maxing Out Short-term Reversals》[SSRN 4622831](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4622831) | 高 MAX 股票周度反转 | 高 MAX 周均 1.66% vs 0.65% | 个股日线 | 第二批（个股周频，需成本）|
| Zarattini/Aziz/Barbon《Beat the Market》SSRN 4824172；Maróy 2025 [SSRN 5095349](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5095349) | SPY 非 ORB 日内动量（噪声带）；改进版加 VWAP 止盈 | 年化 19.6% 夏普 1.33（扣费）；改进版夏普 >3（未核实） | 分钟线 | 是，分钟线引擎（H-20260918-02 后半已 approved 未跑）|
| Kethan《Predictive OFI》SSRN 7053198 | 订单流失衡 | 毛夏普 +0.98，扣价差后 **−1.73** | tick | 否 |
| Heitz et al.《Disappearing Earnings Announcement Premium》SSRN 3296537 | 财报前溢价 | 标题即"消失" | 日线 | 否 |
| Zhang & Zhou 2026 EAR-AI；Yu et al. 2026（见 I-20260922-01） | LLM 读财报文本 | 见 I-20260922-01 | 文本 | 轨道 A |

C 组结论：可信且能进日线引擎的是 **行业趋势跟踪**（Zarattini-Antonacci）与 **隔夜效应**（成本敏感，必须 1/2/5 bp 三档）；SPY 日内动量进分钟线引擎；OFI、财报前溢价明确排除。

## A. Composer 公开 symphony（OOS ≥ 9 个月且年化 ≥ 40% 或夏普 ≥ 2；12 个核实，11 个去重）

| 名称 | 规则骨架（页面原文摘述） | 年化 / 回撤 / 夏普 | 回测起 / OOS 起 | 持仓 | 族 |
|---|---|---|---|---|---|
| v6 Symphony Sorter | 20/200 日均线趋势 + RSI 走强 → TQQQ/SOXL/TECL/UPRO；RSI>70 或波动/债券走弱 → UVXY/VIXY 或 SQQQ/SOXS；盘整 → BIL/SHY/TLT 或 XLP/XLV | 144.8% / −48.4% / 1.81 | 2022-10 / 2023-09-22 | 83 池，日频 | F3 3x 板块动量 + 对冲 |
| Hedged Sector Rotator（两个 URL 同数字） | 60% 按 RSI 热度轮动至最强标普板块，过热转防御；40% 按 QQQ/SPY/债券热度在多空债券、多空股票、VIX 基金间切换 | 140.4% / −19.9% / 2.46 | 2019-10 / 2024-08-03 | 40，日频 | F2 60/40 双腿 |
| 2007 @ 2.25 Sharpe – ETFs | 60% RSI 热度 + SPY/QQQ 200 日线：过热 SHV/PSQ/SH，过冷 QQQ/QLD+TLT/XLV，否则 XLP/GLD；40% 按债券强弱 EEM/EUM/TLT/SHV | 42.8% / −8.6% / 2.37 | 2007-11 / 2024-08-19 | 20 | F2 |
| UVXY & TQQQ | SPY>200 日线顺势 TQQQ；动能过热转 UVXY；科技走弱/波动或利率抬升转国债/T-bill/黄金/美元或 SQQQ | 279.6% / −36.7% / 2.38 | 2012-04 / 2024-06-17 | 25 | F1 趋势 + RSI 双阈值 + 对冲 |
| QQQ – Bull or Hedge | SPY>200 日线持 QQQ/TQQQ；RSI 与回撤触发转 UVXY 或 UUP/GLD | 72.1% / −28.3% / 1.62 | 2011-10 / 2022-09-21 | 9，日频 | F1 |
| TQQQ RSI Strategy / Infinite RSI! – QQQ / Holy Moly（同一回测起点 2011-10-04，同作者模板） | 价格>200 日线定趋势；RSI(10) 超买（70/79/80/81）→ UVXY/SQQQ；超卖（30/34）→ TQQQ/TECL/SOXL；否则顺势或 SHV | 68.9% / −33.1% / 1.46；97.3% / −32.5% / 1.64；140.7% / −33.3% / 1.72 | 2011-10 / 2023-09、2024-06、2025-11 | 6–8，日频 | F1 |
| S&P Symphony w/ Leverage | SPY>200 日线且 RSI 不极端 → SSO 或最强国债/黄金；跌破 → QQQ/PSQ 反向；否则 SHV | 58.6% / −33.6% / 1.54 | 2010-02 / 2023-11-04 | 单持仓 | F1（2x）|
| angarey sector 3x v2 | TQQQ 与长期均线判趋势；上升持近 10 日最强 3x 板块，过强短暂 UVXY，走弱买 SOXL；下降找超卖反弹或 SQQQ/UGL | 351.6% / −46.7% / 2.51 | 2018-12 / 2025-11-18 | 13，日频 | F3 |
| SOXL Growth v2.4.5 RL | 波动率+RSI+收益+回撤综合打分；顺境持 2–3 只 3x 多头，逆境转 3x 空头或 TMV/TMF | 139.2% / −88.8% / 1.45 | 2011-03 / 2023-03-14 | 8 | F3 |
| Volatility Index Black Swan Catcher | VIXM 触发 crash-mode；10/20/30 日 RSI 判 QQQ/SMH 温度：过热 SQQQ/SOXS，过冷 TQQQ/SOXL，中性 BIL/债券篮 | 90.5% / −45.8% / 1.66 | 2022-03 / 2022-12-14 | 20，日频 | F1 变体 |

A 组规律：(1) 骨架 = **200 日线定趋势 + RSI(10) 双阈值**（超买 70–81 → UVXY/SQQQ，超卖 30–34 → 加仓 3x 多头）；(2) **60/40 双腿**（轮动腿 + 独立债券/波动率对冲腿）夏普最高、回撤最低；(3) 3x 板块动量族年化最高（139%–352%）但回撤 46%–89%，收益来自尾部杠杆；(4) 三个"RSI"策略共享回测起点，是同一模板的迭代，算一个家族；(5) 警告：发现页只展示赢家，作者可更新后重置 OOS。

## 汇总：进引擎的家族与 manifest 条目（供 ENGINE 执行者直接构造）

| 族 | 原语 | 网格要点（预注册，≤ 给定 cell 数） |
|---|---|---|
| F1 趋势 + RSI 双阈值 + 对冲（Composer A 组 5 个实例；D 组 TQQQ RSI/Safe） | `gate(sma200 of SPY/QQQ)` 嵌套 `gate(rsi10)`：超买 → {UVXY, BIL, SQQQ}；超卖 → {TQQQ, TECL}；否则 → {TQQQ, QQQ, SSO} | RSI 标的 {SPY, QQQ} × 超买 {70, 80} × 超卖 {30} × 超买资产 3 × 顺势资产 3 × 再平衡 {日, 周} = 72 |
| F2 60/40 双腿 | 腿 1 = `rank`(11 SPDR, 21 日, top1) 套 `gate(rsi10 过热 → XLP/GLD)`；腿 2 = `rank`({TLT, SHV, EEM/EUM 或 SQQQ/QQQ}, 21 日, top1)；权重 {60/40, 50/50} | ≤ 24 |
| F3 3x 板块动量 + 对冲（B-1 卡已覆盖核心） | `rank`({TECL, FAS, ERX, CURE, DUSL, SOXL, TQQQ}, {10, 21} 日, top{1,2}) 套 `gate(rsi10 过热 → UVXY/BIL)` 与 `gate(sma200 趋势 → 否则 SOXL 超卖买 / SQQQ)` | ≤ 48（与 H-20260922-04 合并去重）|
| F4 固定权重杠杆（HFEA、TQQQ/TMF、9-Sig） | `fixed_weights` {UPRO/TMF 55/45, TQQQ/TMF 50/50, TQQQ/AGG 9-sig} × 再平衡 {月, 季, 双月} | ≤ 12 |
| F5 canary/广度防御叠杠杆（Keller BAA/VAA/HAA、Antonacci GEM、Faber GTAA） | `canary` 与 `abs_filter`/`gate(sma10m)` 原版 + 进攻篮换成 {UPRO/TQQQ/SSO} 的杠杆版 | 原版 6 + 杠杆版 12 = 18 |
| F6 行业趋势跟踪（Zarattini-Antonacci） | 11 SPDR + 可得行业 ETF 各自 `gate(sma{126,200} 或 12 月时序动量)`，等权持有在趋势内者，否则 BIL | ≤ 12 |
| F7 隔夜效应 | `overnight`(QQQ/TQQQ/SPY 收盘买次日开盘卖) × 跳过周五 {是, 否} × 成本 {1, 2, 5} bp | ≤ 18 |
| 已在跑 | B-2 波动率目标/回撤刹车（H-20260922-02）；B-1 RSI 分支（H-20260922-04）| — |
| 不进 | VIX 期限结构（无 VX 期货）、OFI（tick）、财报前溢价（消失）、LAA（宏观序列）、ORB | — |

合计约 200–250 个新 cell，加 B-1/B-2 的 80 个。全部日线，一次跑完。

## E. 有代码、有美股结果的高阶策略（第二次采集，2026-09-22）

| 名称 | 方法 | 数据需求 | 报告结果 | 复现/衰减证据 | 判定 |
|---|---|---|---|---|---|
| Open Source Asset Pricing [openassetpricing.com](https://www.openassetpricing.com/) / [OpenSourceAP/CrossSection](https://github.com/OpenSourceAP/CrossSection) | 209 个已发表个股特征的月度宽表 + 组合收益，PyPI 包 `openassetpricing` | 免费；v2.0.0（2025-10）覆盖至 2024-12；标识为 permno，无 ticker/CUSIP 映射；Price/Size/STreversal 三个信号需 CRSP | 特征库，非策略 | 不需复现 | **第一优先**：这是文献里真正有效的截面 ML（Gu-Kelly-Xiu 一类）的免费训练集。缺口：permno→ticker 映射；数据只到 2024-12，实盘要自算可算子集（价量类 + XBRL 财务类） |
| Deep Learning Statistical Arbitrage [arXiv 2106.04028](https://arxiv.org/abs/2106.04028) / [官方 repo](https://github.com/JorgeGuijarro/Deep-Learning-Statistical-Arbitrage) | FF/PCA/IPCA 残差 + 卷积 Transformer | 日线 + FF 因子（有）；IPCA 需特征 | 2002–2016 残差空间夏普 3.2–3.9（未扣费） | [bsiranosian 复现](https://bsiranosian.com/blog/deep-learning-statistical-arbitrage-part-1/)：残差空间对得上，映射回可交易股票后 FF 版夏普 2.30 → **0.97**；官方 repo 只有 PDF | 第二批：FF 残差版本本地可做，但按复现者的口径扣费后重估，日频换手是硬伤 |
| Fischer & Krauss 2018 LSTM / Krauss-Do-Huck 2017 | 逐日截面排序，多空 top-k | S&P 500 历史成分（需自建） | 2010 年前日均 0.3–0.4% | **2010 年后收益消失**，多方证实 | 不做 |
| QuantConnect 日内协整配对 / PCA 残差均值回归 | 10 分钟协整配对；PCA 残差 z-score | 分钟线（有）/日线 | 官方展示夏普 3.0 但样本一个月未扣费 | 独立复现夏普 0.47–0.85 | 不做（先否证）|
| Learning-to-Rank 截面（Poh 等 2020，[repo](https://github.com/qclijun/Cross-Sectional-Momentum-LTR)） | LambdaMART 排序 | 截面特征 | 未核实 | 官方代码 | 并入 OSAP 路线的模型选项 |
| Momentum Transformer / Spatio-Temporal Momentum（[2302.10175](https://arxiv.org/abs/2302.10175)、[2412.12516](https://arxiv.org/pdf/2412.12516)） | 时序 + 截面动量神经网络 | 日线 | 美股 2020–23 年化 4.1% / 夏普 1.12 | 非官方复现 | 不做（收益太低）|
| 2025–26 LLM 因子挖掘（Chain-of-Alpha、Alpha Jungle、AlphaLogics、FactorEngine、CrossAlpha） | LLM 生成公式因子 | 多为 A 股基准 | 未核实 | 作者自证 | 不做 |
| je-suis-tm/quant-trading、stefan-jansen/machine-learning-for-trading | 策略合集 / 教材代码 | 日线 | 无统一战绩 | — | 只作工具参考 |

E 组结论：高阶策略里真正能在本机、用免费数据、且有文献背书的只有一条：**OSAP 特征库上的截面 ML 排序**（GKX 范式）。它不是"爆炸"型，文献口径是月频多空夏普 1–2 扣费前、long-only 前十分位年化 15–25%；价值在于它是唯一还没在本地试过的、文献里 ML 真正有效的做法（此前本地 ML 全在价量特征上，先验本来就低）。DLSA 排第二批。其余排除。

## F. 日内 / 高频策略普查（第三次采集，2026-09-22，18 次检索）

| 名称 | 规则 | 标的与频率 | 报告结果 | 复现/衰减证据 | 判定 |
|---|---|---|---|---|---|
| Zarattini-Aziz-Barbon [Beat the Market](https://www.sfi.ch/en/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy)（SSRN 4824172） | 噪声带突破 + VWAP 跟踪止损，日终平 | SPY，分钟 | 2007–2024 初总 1,985%、年化 19.6%、夏普 1.33，摩擦 $0.0035/股佣金 + $0.001/股滑点 | **本地已复现并否定：H-20260922-07** | **已否定**：按论文自己的成本口径，2016–2026 年化 +2.2%、夏普 0.30，随机方向安慰剂 80% 打赢 |
| Maroy [Improvements to Intraday Momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5095349)（SSRN 5095349, 2025-01） | 对上族做全参数优化，比较固定止盈 / VWAP / Ladder / VWAP+Ladder 退出 | SPY，分钟 | 自称 VWAP/Ladder 退出夏普 >3.0、年化 >50% | 第三方自动复现同族仅 0.41；**本地 H-20260922-07 测到 VWAP 跟踪止损把毛收益从 +3.6% 打到 +0.3%** | **不做**：头条来自对退出维度的参数搜索，那正是它的过拟合维度 |
| Gao-Han-Li-Zhou [Market Intraday Momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866)（JFE 2018） | 首个 30 分钟收益预测末 30 分钟收益 | SPY 等 11 只 ETF，30 分钟 | 原文 1993–2013 称显著，具体数字未核实 | paperswithbacktest 自建可执行版 1990–2026：年化 3.14%、夏普 0.41、回撤 −29.7% | 不做（独立复现的量级已低于无风险利率）|
| Concretum [Identifying Stocks to Fade](https://concretumgroup.substack.com/p/identifying-stocks-to-fade) | Russell 3000 剔除流动性最差 30%，隔夜异常大跳空个股日内做反向 | 美股个股，日内 | 2012-01 → 2026-05 毛 CAGR ~98%、夏普 ~2.08、回撤 ~67%；作者明示"扣费后有实质差异" | 作者自陈 2022 年后结构性走弱，归因卖空基础设施普及 | **第一优先**：见下 |
| Schlie & Zhou [Interday Cross-Sectional Momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4934543) | 某半小时收益预测次日同一半小时 | 9 个发达市场成分股，半小时 | 作者自认"美股该效应已减弱" | paperswithbacktest 1990–2026：年化 **−5.58%**、夏普 −0.49、回撤 −93% | 不做 |
| [MG-source-1/equities-and-vol](https://github.com/MG-source-1/equities-and-vol) | 隔夜缺口 + 开盘 30 分钟同向做空末 30 分钟 | SPY，5 分钟 | 2020–2024 总 +14%、夏普 0.10 | 作者自己因夏普过低未纳入组合 | 不做 |
| VWAP 偏离反转（行业博客） | 偏离当日 VWAP N 倍标准差反向 | 流动股，分钟 | 无扣费学术级结果 | 无独立复现，来源多为教学/营销 | 不做 |
| 隔夜/日内拆分文献（[Alpha Architect](https://alphaarchitect.com/trading-costs-wipe-out-the-overnight-return-anomaly/)、Muravyev JoF 2025） | 检验隔夜异象扣真实成本/借券成本后是否存活 | 美股，日频 | 结论：基本被抹平 | 本身即否定性复现 | 不必重新论证（本地扫荡 F7 已独立测到 −20%/年）|
| ESN / ELM 等纯 K 线日内 ML（[2504.19623](https://arxiv.org/abs/2504.19623)、[2505.09551](https://arxiv.org/pdf/2505.09551)） | 储备池计算 / 极限学习机预测 5 分钟方向 | 未核实 | 无可核实数字、无代码 | 无 | 不做 |

**F 组结论**：日内这一族里，单标的择时（SPY 噪声带、30 分钟动量、隔夜）已被本地或独立复现逐条打掉，共同形态是**毛边际 2–4%/年、扣任何摩擦都不剩**。唯一还没被否定、且与我们数据匹配的是 **Concretum 的截面 gap fade**——它是横截面而非单标的，规则具体，作者自曝 2022 年后走弱（可直接切两段证伪），本地分钟线全覆盖。

**与本地证据的一个交叉点（值得单开一张卡）**：H-20260922-01 在 8-K 盈余事件日测到开盘跳空对当日 open→close 收益的 t = **4.63**，方向是**延续**；Concretum 则对异常跳空做**反向**。两者同时成立的唯一方式是按"跳空是否由新闻驱动"分工：**有新闻的跳空延续、没新闻的跳空反转**。我们有 680k 条带 `visible_at` 的 Benzinga 标题，能按事件时点精确切开这条线，这是别人公开资料里没有的本地优势。

## G. 可在本机训练的模型普查（第三次采集，2026-09-22，18 次检索）

约束：4 GB 内存 / 2 核 / 无 GPU，只用已有免费数据。

| 名称 | 方法 | 报告结果 | 反面证据 | CPU 可行性 | 判定 |
|---|---|---|---|---|---|
| **Conformal Kelly**（[arXiv 2608.01494](https://arxiv.org/abs/2608.01494) / SSRN 7221760） | 用 75% 保序预测区间的**宽度**缩放分数 Kelly 仓位：区间越宽仓位越小 | 2016–2021 含成本与杠杆上限：年化净对数增长 **28.5%**、夏普 **1.34**，同期 SPY 15.9% | 未见第三方复现 | 是——保序校准几乎零额外算力 | **第一优先**：直接作用于**仓位**而非选股，与"只有杠杆账本 + 仓位层能过 50% 门槛"的结构性判断正面吻合，也是 S3 加档那条线的自然下一步 |
| 统计跳跃模型（[arXiv 2402.05272](https://arxiv.org/abs/2402.05272)） | 跳跃惩罚代替 HMM 转移矩阵做 regime 识别再择时 | 称较 HMM/买入持有降波动与回撤、计入成本与延迟；具体数字未核实 | 未见第三方复现 | 是（凸优化，比 HMM 更轻） | 第二批：先定位作者的 `jumpmodels` 包并核实扣费后数字 |
| HAR + SVM 方向性波动率（T&F 2024） | HAR 上叠 SVM 预测已实现波动率方向 | 称多个 horizon 策略夏普最高，数字未核实 | — | 是 | 第二批（作为仓位层的输入）|
| 波动率择时反面证据（ScienceDirect S1062940826000276） | 更精细 RV 预测驱动 vol targeting | **各模型风险调整后夏普均为负** | 本身即"更准的波动预测→更好 sizing"的反面 | — | **重要负面**：与本地 H-20260922-05 "vol target 在 S1 是收益税"同向，压低"换更好的波动率模型"这条线的优先级 |
| LightGBM + 不确定性门控（[arXiv 2603.13252](https://arxiv.org/abs/2603.13252)） | 7 因子排序 + 不确定性退出门 | 全样本 walk-forward 夏普 2.73（含 10 bp）；**2024 后 OOS 降到 1.91、回撤 −18.1%** | 论文自报的 OOS 衰减 | 是 | 并入 OSAP 路线 |
| Qlib + Alpha158 | 158 技术因子截面 LightGBM 排序 | 官方 benchmark 主要在 A 股，无美股专版数字 | 本地已否定（H-20260918-03） | 是 | 不做 |
| meta-labeling（Hudson & Thames / mlfinlab） | 规则主模型 + ML 二级过滤 | 反转 0.28→0.97、趋势 0.36→0.53，**均未扣成本** | 作者自陈"主模型差时只能减损失" | 是 | 第三批：只在已通过的 S2/S3 规则上试，且必须扣费 |
| FinRL 深度 RL（[repo](https://github.com/AI4Finance-Foundation/FinRL)） | PPO/A2C/DDPG/TD3/SAC 做配置/仓位 | 官方对比 MVO/DJIA | [独立诊断](https://github.com/Aarav-Nagar/QINN-FinRL-Evaluation)：五只票 2018–2026 多种子含成本，PPO 平均夏普**低于全部经典基线含买入持有** | 否（4 GB/2 核跑不动） | 不做 |
| Kronos（[arXiv 2508.02739](https://arxiv.org/abs/2508.02739)） | K 线专用 Transformer 基础模型 | 排序 IC 较通用 TSFM +93%；**无美股可交易回测数字** | 未核实 | 预训练不可行，推理未核实 | 不做（无可交易证据）|
| TimesFM / Chronos / Moirai 零样本（[arXiv 2511.18578](https://arxiv.org/abs/2511.18578)） | 通用时序基础模型零样本预测个股收益 | **R² 为负**：TimesFM −2.80%/策略 −1.47%，Chronos −1.37% | 论文本身即反面证据 | 是（只需推理） | 不做 |
| RL 执行（[arXiv 2507.06345](https://arxiv.org/abs/2507.06345)） | RL 学最优限价/市价混合 | 无美股可交易数字 | — | 否（需盘口/tick，我们没有） | 不做 |

**G 组结论（2026-09-22 初版）**：模型这一侧的证据-投入比排序是 Conformal Kelly（仓位层）> 跳跃模型 regime 择时 > OSAP 截面 ML > meta-labeling > 其余全部不做。基础模型（Kronos/TimesFM）和深度 RL 都有明确的负面或缺失证据，不值得占用本机算力。

### G 组更正（2026-09-23，读了 Conformal Kelly 原文摘要之后）

**Conformal Kelly 被作者自己的预注册留出窗否定，下架，不复现。** 采集卡只抄了开发窗的数字。原文摘要（快照 `reports/research/intel/sources/20260923-conformal-kelly/`，sha256 `ac04cde38463…`）写得非常清楚：

> "These numbers came from an autonomous LLM-agent search over **200 configurations**, so we **sealed all data from 2022 onward and pre-registered** configurations, benchmarks, and interpretation rules before one evaluation. Calibration held (0.745 coverage against 0.750, weakest through 2022); **growth did not: the two configurations earned 8.5% and 7.0% per year, below the passive benchmarks**, and a pre-registered hindsight benchmark beat them on raw growth while taking a 46% drawdown."

也就是说 28.5% / 夏普 1.34 是在 2016–2021 开发窗上由一次 200 配置的自动搜索得到的，作者自己把 2022 起封存、预注册、然后**跑输了被动基准**。按 `research-mission.zh.md` 的规则（已被否定的路线只有在新增可指认的信息、数据或机制时才能重开），这条不重开。

论文本身是一篇很诚实的作品，从它身上能拿走的是两条**方法结论**而不是一个策略：

1. **"更快适应市场的区间"全都更差**：作者报每一个加速适应的改动都要付 0.7–5.3 个百分点的年化增长，赢家是最笨的那个——slow, unweighted, per-asset rolling quantiles。"When an interval sizes a position rather than describing one forecast, **width stability beats local sharpness**."
2. **校准会外推，增长不会**：留出窗上覆盖率 0.745 对 0.750 守住了，收益没守住。所以"我的不确定度估计更准了"不能当成"我的仓位会更赚钱"的证据。

**这条与另一条独立负面证据同向**：G 组已收录的 ScienceDirect S1062940826000276 发现更精细的 RV 预测驱动的 vol-targeting 组合风险调整后夏普**均为负**。两条独立证据指向同一个结论——**把仓位层做得更精巧不会带来增长**。这也解释了为什么我们自己的 S3-vt40（一个最朴素的 21 日已实现波动率目标）能过 G1–G5，而更复杂的版本（回撤刹车）没有增量。**结论：仓位层已经做到位了，不要再往那个方向投入；剩下的杠杆在别处。**

**统计跳跃模型的独立证据（2026-09-23 补，比采集卡准确得多）**：

- 论文（[arXiv 2402.05272](https://arxiv.org/abs/2402.05272)）确实含**成本、交易延迟和样本外**评估，美/德/日股指 1990–2023，但摘要不给具体数字。
- 公开实现存在且质量不错：[`jumpmodels`](https://github.com/Yizhan-Oliver-Shu/jump-models)，scikit-learn 风格 API，官方例子跑在 Nasdaq-100 上，含 JM / CJM / 稀疏 JM。
- **独立复现给了重要的负面校正**：[atanasovkaloyan7-ui/statistical-jump-model](https://github.com/atanasovkaloyan7-ui/statistical-jump-model) 明确写"**detector did not replicate 原论文的 1.43 夏普**，按他们诚实的成交约定只得到 0.25–0.52"。他们的整体结果（SPY 2008–2025，含成本）：跳跃模型 + sleeve **9.13% CAGR / −22.5% 回撤 / 夏普 0.922**，对比 SPY 11.55% / −51.5% / 0.649。**收益更低、回撤减半、夏普更高——这是风险叠加层，不是 alpha。** 单看 regime 叠加层把回撤从 −43.8% 压到 −33.8%，并且**赢过暴露匹配的平坦账本 17.5 个百分点**。
- 他们的对照电池值得直接抄：8 项控制，其中作者自称"decisive"的是**暴露匹配对照**（择时是不是只等于长期持有更低的平均暴露），还有**与真策略换手率相同的随机信号安慰剂**。这与我们在 S2 波动率目标上得到的结论同构（夏普升了但随机挑选安慰剂 23.3%，所以只能算风险叠加）。

**更正后的 G 组排序**：**统计跳跃模型 regime 择时 > OSAP 截面 ML > meta-labeling > 其余不做**。Conformal Kelly 移入"已被作者否定"。但要注意跳跃模型的定位已经被独立证据钉死在**回撤控制**上，不是收益来源；而我们本地已经有一条同类的负面（H-20260922-02 的回撤刹车在 S3 上无增量，70% 的日历平移种子打赢它）。所以它只有在"压低回撤 → 允许把杠杆/波动目标调高"这条路径上才有价值，必须带暴露匹配对照一起测。
