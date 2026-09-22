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
