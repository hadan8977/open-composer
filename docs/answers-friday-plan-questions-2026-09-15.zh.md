# 上周五计划里待回答的四个问题 + 下一步建议（2026-09-15）

作者：调研代理（Opus 5）。对应任务：`docs/plan-step-17-paper-rehearsal-portfolio-canary-2026-09-15.zh.md` 第 3 节最后一条
（"上周五计划里待回答的问题由一个后台调研代理起草答案文档"）。

本文件只回答问题，不改任何代码、不跑回测、不改门槛合同。

## 0. 怎么读这份文件

三种信息来源我全程分开标注，请按标注的可信度读：

- **【我们的证据】**＝本仓库自己跑出来的数字（账本 / 报告 / 筛选产出），可以复现。
- **【文献】**＝外部论文或官方文档，每条都带 URL 与访问日期（见文末清单）。凡是我只看到搜索结果摘要、没有逐页核实的，我都写明"**搜索综合，未逐页核实**"。
- **【我的判断】**＝我自己的推断，没有直接证据支撑。这部分你可以直接否掉。

一句话总结：**纯价量这条路（Tier 2/3）我们已经走到它的天花板了，证据很干净；本周的模拟盘是执行管道的彩排，不是策略胜利；下一步应该把工程时间从"再挖价量因子"整体挪到"免费且官方的 Tier-1 数据"（SEC Form 4 内部人、FINRA 空头利息），期权与分析师修正先做"从今天起每日归档"的准备而不是马上花钱回测。**

---

## 1. 每个工作流 / 每条轨，落到你的三层框架里

先把你的分层复述一遍，后面表格都用这个口径：

| 层 | 内容（你 2026-09-11 的说法） |
|---|---|
| Tier 1（最有价值） | 内部人交易（SEC Form 4）、期权隐含信息、分析师修正、财报电话会 NLP、新闻情绪、Reddit/X 关注度 |
| Tier 2 | OHLCV 派生因子：残差动量、波动体制、隔夜效应、流动性异象 |
| Tier 3（基本不值得投入） | 纯技术指标：RSI、MACD、布林 |

### 1.1 计划里的工作流 W0–W6

| # | 工作流 | 落在哪一层 | 现状 | 建议 | 为什么 |
|---|---|---|---|---|---|
| W0 | 补完 Step 16 调研 | 跨层（元工作） | 已完成 | **就此结束，不重开** | 已产出 16 条来源卡；其中两条明确记录"找不到一手证据"（`gap_fade_volatility_compression_breakout_no_rigorous_numbers`、`ic_above_0p05_ohlcv_only_continuation`）。把"找不到"当结论用，比再搜一轮有价值。 |
| W1 | Reversal Trend 做扎实 | **Tier 3**（RSI + MACD + ADX 组合） | 阻塞在你的截图 | **大幅缩小**：只留"执行/入场时机层"的一次 A/B + 与你截图的 parity 核对，取消多周期泛化、阈值学习、部件消融 | 见第 2 节。你自己的框架把这类指标排在最低，我们自己的证据也是 0/18 过门槛。原计划 2 个执行日花在 Tier 3 上，性价比最差。 |
| W2 | Step 14 通用运行器 | 基础设施（不属于任何层） | 已提交检查点（`42ff1ef`：`bar_source` / `signal_engine` / `run_bar_cycle.py` + 1284 行测试） | **继续，并且提高优先级**，但目标改写：不是"为了小时线 Reversal Trend"，而是"为了任何按事件/按周期跑一次的候选" | Tier-1 数据全都是"每天来一批新记录"（Form 4 日更、期权 EOD、分析师修正事件）。没有这个运行器，Tier-1 永远只能算不能下单。它是 Tier-1 的必要管道，不是 Tier-3 的配件。 |
| W3a | 选股层：GTJA-17 | Tier 2/3 边界（纯价量公式） | 已完成 | **到此为止**，不再补 191 里剩下的 id | 【我们的证据】16 个已实现 id 在 2024–2026 窗口 **0 个**通过本仓库 BH-FDR（全库同期也是 0/506）；放宽到论文自己的 `t>2` 口径，recent 窗只有 4/16。已按 plan 规则跳过条件 M1 单元。继续补 id 的边际价值接近零。 |
| W3b | 隔夜/日内分解 + FINRA 空头利息 | 隔夜/日内 = **Tier 2**（你自己列的"隔夜效应"）；空头利息 = **接近 Tier 1**（机构行为、公开但有摩擦） | 未开始（零新数据部分本可由协调者顺手做） | **继续，并且排到 W3a 之后的第一位** | 两项都是"零成本"：隔夜/日内列用已有 SIP 分钟档案就能算；FINRA 空头利息免费下载。【文献】Lou-Polk-Skouras 隔夜十分位三因子 alpha 3.47%/月（`overnight_intraday_tug_of_war_momentum`）；Hong 等 days-to-cover 多空 1.2%/月（`short_interest_days_to_cover_factor`）。这是我们手上"单位成本效应量"最高的两项。 |
| W3c | 内部人 Form 4 PIT 包 | **Tier 1（你排第一）** | 未开始 | **继续，提为选股层第一优先** | 免费、官方、2006-01 起、季度包 + EDGAR 日更补尾段（`sec_insider_transactions_data_sets`）。【文献】Cohen-Malloy-Pomorski：机会型内部人买入组合价值加权异常收益 82 bp/月，例行组≈0（`insider_opportunistic_vs_routine_decay`）。它同时能做因子和"动量确认门"两种用法。 |
| W4a | 两阶段 + 动态因子刷新 | 组合层机制（服务 Tier 2） | 未开始 | **保留但缩小**：只保留"规则前 100 → 模型排前 50"和"每季重筛"两件事，作为以后任何新数据层的标准接法 | 【我们的证据】两阶段用 `daily27` 只有 10.4% 年化，明显输给规则孪生 33.7%；但"先筛后训"确实有效（筛选集验证 IC 0.035 vs 整库 alpha158 0.021）。所以保留机制、不要再在同一批价量特征上扩格子。 |
| W4m | ML 方法按层匹配 | 跨层方法 | 未开始 | **继续，按第 4 节的 10 格小网格执行**，先用已有数据 | 这是你 2026-09-11 的直接批评（"一律 LightGBM 回归 + 等权前 50"）。我同意，并且把它写成可预注册的格子，而不是又一轮自由探索。 |
| W4b | LLM 当因子生成器（挖价量公式） | Tier 2/3（它挖的是价量公式空间） | 阻塞在 LLM 端点 | **降级 / 暂缓** | 【我们的证据】五个公开因子库 240 列筛完，前 40 的近期 ICIR 只有 0.163–0.285，ML 单元 17–19% 年化，全部输给规则孪生。【文献】AlphaMemo 在标普 500 上静态 Alpha158 的 RankIC 只有 0.0081、年化 14.36%（`alphamemo_sp500_alpha158_decay_2026-09-09`）；LLM 挖矿论文 IC 0.045–0.085 多在 A 股或不公开表达式。**【我的判断】**再让 LLM 在同一个价量空间里挖公式，是把最贵的工具用在最低的层上。LLM 该先去读 Tier-1 文本。 |
| W4c | L 轨恢复（新闻事件抽取 → 特征） | **Tier 1（新闻情绪）** | 阻塞在 LLM 端点 | **继续**，但目标改为"事件 → PIT 特征包"，并与其他 Tier-1 列共用同一个筛选/评估协议 | 新闻 PIT 包（2024→，685k 篇）已经在盘上，是我们唯一已落地的 Tier-1 数据。【文献】Lopez-Lira & Tang 的 GPT 读标题可预测反应（`llm_extracted_signals_10k_earnings_calls_verified`）。注意：只有 2024→ 样本（≈140 周），别指望它单独过门槛。 |
| W5 | 组合实验（动量池 × Reversal Trend 入场） | Tier 3 用在执行层 | 未开始 | **降级为 W1 里的一个小实验**，不单列为工作流 | 只有"入场时机是否改善成交价/回撤"这一个问题值得问，答案用一次 A/B（信号入场 / 随机同期入场 / 当日开盘入场）就够。 |
| W6 | 后备清单 | 混合 | 未开始 | **拆开**：13F 倾斜 + 散户关注度 → 提到"下一批 Tier-1"；Kyle-lambda 列 → Tier 2 补充列，顺手做；Chen-Zimmermann 当前样本异象收益 → 一次性抓取做对照；LLM 读 EDGAR → 归入 W4c | 13F（`13f_conviction_consensus_best_ideas`，超越标普 500 3.80%/年）与散户关注度都是 Tier 1；Kyle-lambda（`kyle_lambda_signed_order_flow_daily_crsp`）只用日线价量就能算，属于 Tier 2 的流动性异象，成本极低。 |

### 1.2 Step 13 的四条轨

| 轨 | 内容 | 层 | 建议 | 为什么 |
|---|---|---|---|---|
| M | 规则动量 / ML 选股单元 | 规则动量 = Tier 2（风险调整动量）；ML 部分 = 组合层方法 | **冻结网格**：规则动量保留为"基准 + 本周执行彩排的载体"，ML 单元只在**有新数据层**时再跑 | 【我们的证据】26 个单元全部不过合同 v2；4 个 ML 单元全部输给规则孪生；binding gate 是 `cagr_excess_vol_matched_spy`（最好的单元 -3.4%，连接的候选 -11.0%）。意思很直白：**这个窗口里集中动量书的超额主要来自"跑得更热"，不是"选得更好"。** 再扩格子只会增加多重检验成本。 |
| F | 公开因子库导入 + 筛选 | Tier 2/3 输入；**但筛选器本身是基础设施** | **筛选器保留、当成闸口**：以后内部人、空头利息、期权、分析师修正的每一列都走同一协议（IC/ICIR/FDR/符号稳定性/去重）；**不再导入新的价量库** | 一次性基础设施已经建好（五张表 + 带检查点的筛选器 + 注册表）。价值在闸口，不在再多 100 个价量列。 |
| P | 小时线 Reversal Trend | **Tier 3** | 见第 2 节：降级为执行/入场层候选 | 【我们的证据】日线四个信号事件研究都是 `informative: no`；1h 18 个单元 **0/18** 过门槛；最好单元在网格边缘（h26 才正，h6/h13 不行）；姊妹单元的随机日期占位解释了它 **59%** 的累计收益。 |
| L | LLM 新闻 | **Tier 1** | **继续**（阻塞在端点），恢复后第一优先 | 唯一已落地的 Tier-1 数据源；与你的框架完全一致。 |

### 1.3 重排后的顺序（我的建议）

1. 本周：Step 17 执行彩排（已在做）+ W2 运行器收尾。
2. 下一批（零成本、免费官方数据）：**W3c 内部人 Form 4** → **W3b 隔夜/日内列 + FINRA 空头利息**。
3. 与之并行的方法工作：**W4m 的 10 格小网格**（第 4 节），只在已有数据上跑。
4. 端点恢复后：**W4c**（新闻事件 → PIT 特征），然后才考虑 W4b。
5. 缩到最小：W1 / W5（一次 A/B + parity）。W3a 结束。W6 按上表拆。

---

## 2. W1（Reversal Trend）：我的直接建议

**建议：保留为"执行 / 入场时机层"的一个候选，立刻停掉原计划里 2 个执行日的大工程，不再把"等你的截图"当作开工条件。**

拆成三句可执行的话：

1. **取消**：多周期泛化（1m/2m/5m/15m/30m/1h）、阈值在训练窗学习、部件消融（趋势层/武装态/MACD 触发/冷却）、DSR 计全部周期。
2. **保留**：把已有的 h26 / `bull_and_recl` 单元冻结成"入场时机层"的一个候选，在**已有数据**上做一次 A/B：同一批已选出的股票，比较（i）按 Reversal Trend 信号入场、（ii）同期随机日入场、（iii）当日开盘直接入场，看它是否改善成交价与回撤。只做一次，出一份报告。
3. **截图仍然欢迎**，但用途改为**只做 parity 核对**（我们移植的指标与原版是否一致，见报告里的 SPY 2025H1 10 个事件表），不作为新一轮网格的触发条件。

理由（分开标注）：

- **你自己的框架**：它是 RSI + MACD + ADX + EMA 的组合，按你的分层属于 Tier 3"基本不值得投入"。我不打算用项目惯性去覆盖你的判断。
- **【我们的证据】** 四条，都不支持它当 alpha：
  - 日线四个信号（fBull/fRecL/fBear/fRecS）在 2018–2026 与 2024→ 两个窗口都是 `informative: no`；`rt_bull_signal` 在近期窗 5 日 t=0.26、10 日 t=-1.64。
  - 因子筛选里 `reversal_trend` 库 42 项检验 **0 项**通过 FDR（其他四个库分别有 54/17/7/2 项通过）。
  - 1h 18 个单元 **0/18** 过合同 v2；最好单元 26.25%/-14.68% 仍然低于 30% CAGR 门槛，也低于 SPMO 的 37.4%。
  - 最像"真效应"的反证：好结果只出现在三点网格的**最长边界**（h26），h13 只有 +3.4%、h6 全负；姊妹单元（`time_stop_or_reverse`）的随机日期占位累计 +0.5067 vs 真实 +0.8604，**占位解释了约 59%**。真效应通常出现在网格内部，不是边界。
  - 【我们的证据·补充】它还不能上模拟盘：现有日频 cron 一天只跑一次，小时线需要一个盘中调度 + 准实时小时线构建，这正是 W2 在做的事（所以 W2 留、W1 缩）。
- **【文献】** 纯价量的日内/技术层天花板很低：SPY 市场日内动量样本外 R² 只有 1.4%（首个半小时）/2.0%（两项合用）（`market_intraday_momentum_first_last_half_hour`）；跳空反转与波动压缩突破**找不到任何给出数字的一手学术来源**，只有交易博客（`gap_fade_volatility_compression_breakout_no_rigorous_numbers`）；专门去找"2025–2026 纯价量美股 IC>0.05"也**没找到**可核实的一手论文（`ic_above_0p05_ohlcv_only_continuation`）。
- **【我的判断】** 唯一会让我改主意的条件（写成可检验的）：如果你更新版 Pine 里有我们**没有移植**的部件（例如成交量确认、更高周期过滤、或者与原版不同的阈值），并且把这个部件加进去以后，**h6/h13 也从负转正**（效应出现在网格内部而不是只在 h26），那我会立刻申请再投一轮。否则不投。

**不建议彻底删除**的原因：它作为"入场时机"的假设还没有被否证（事件研究否证的是"当横截面 alpha 因子"，A/B 测的是"同一批股票、换入场时点"），而且这个 A/B 用已有数据就能做完，成本半天。

---

## 3. 两个 Tier-1 空白的数据源扫描

### 3.1 期权隐含信息（IV skew / put-call 比 / 成交量与未平仓量失衡）

我们现在的状态：`capabilities/registry.yaml` 里只有一条 `options.trial_chain`，`provider: unconfigured`、`status: trial`、`strict_behavior: research_only`，也就是**零覆盖**。

| 来源 | 价格 | 内容 | 是否点时（PIT） | 历史深度 | 许可限制 |
|---|---|---|---|---|---|
| **Massive（原 Polygon.io）Options** — 定价页已直接读取 | Basic 免费（EOD）/ **Starter $29/月**（15 分钟延迟）/ Developer $79/月 / Advanced $199/月（实时） | Starter 起含 **greeks、隐含波动率、未平仓量**，标称 100% 美股期权覆盖 | 供应商不提供"当时可见"时间戳；但 EOD 快照按交易日拿是**日频 PIT 可自建**（我们自己抓就有 `fetched_at`）。分钟级 PIT 不行（15 分钟延迟档） | Starter/Basic 2 年、Developer 4 年、Advanced 5 年以上 | Advanced 档标注 "Non-pros only"（非专业用户）。注意：`polygon.io` 已 301 跳转到 `massive.com`，品牌已改名 |
| **Alpaca 期权数据** — 文档页搜索综合，未逐页核实 | OPRA 实时需 `Algo Trader Plus` 订阅（**具体月费我本轮没核实成功，标为未核实**）；15 分钟以上的历史在所有 feed 可用 | 历史期权 bar/quote；Basic 档只有 indicative feed；**是否直接提供 greeks/IV 我没核实** | 与我们现有 SIP 同一提供商、同一密钥、同一采集与 PIT 机制（最大优点） | **仅 2024-02 起**（≈2.5 年） | 按 Alpaca 数据条款 |
| **EODHD** — 定价页已直接读取 | Fundamentals $59.99/月 / ALL-IN-ONE $99.99/月；"EOD Options Data API" 是**单独产品**，是否含在标准档定价页未说明（未核实） | EOD 期权链 | 同上，日频快照自建 | 未核实 | 定价页没有明确的再分发条款，商业用途要单独联系 |
| 免费的个股级期权历史 | — | — | — | — | **本轮预算内没有找到可核实的免费来源**。搜索里出现的 DoltHub 免费期权库没有得到确认；其余全是商业供应商（IVolatility、DeltaNeutral、FirstRate、OptionMetrics）。所以请把"免费"这条路当作**未证实** |

**文献与效应量：**

| 论文 | 信号 | 报告的效应 | 核实程度 |
|---|---|---|---|
| Xing, Zhang, Zhao (2010, JFQA)《What Does Individual Option Volatility Smirk Tell Us About Future Equity Returns?》 | IV skew = OTM put IV − ATM call IV | **最陡 smirk 组比最平组年化低 10.9%（风险调整后）**，可预测性至少持续 6 个月；最陡组下一季度财报冲击最差；数据源 OptionMetrics | **直接核实**（我抓到 PDF 并本地抽取了摘要原文） |
| Cremers & Weinbaum (2010, JFQA 45(2):335-367)《Deviations from Put-Call Parity and Stock Return Predictability》 | 同到期同行权价的 call/put 隐含波动率差（偏离 put-call parity） | **call 相对贵的股票每周比 put 相对贵的股票高 50 bp**；且摘要自己说**样本期内可预测性逐年下降** | 搜索综合（SSRN 摘要），未逐页核实 |
| Pan & Poteshman (2006, RFS 19(3):871-908)《The Information in Option Volume for Future Stock Prices》 | 用"**开新仓的买方发起成交量**"构造 put/call 比 | 低比率组比高比率组**次日高 40+ bp、一周高 1%+**；来源是期权交易者的非公开信息而非市场无效率 | 搜索综合，未逐页核实 |

**【我的判断】可行性结论：**

1. 起点应该是 **IV skew**（Xing 等），不是 put-call 比。因为 Pan-Poteshman 的效应依赖"开仓方向标识的成交量"，那是 CBOE 的专有字段，$29–100/月的供应商给不了；我们只能用公开 volume/OI 近似，效应一定弱于论文。用了论文的名字、拿不到论文的数据，是最容易自欺的一种做法。
2. 最便宜的可行路径：Massive Starter $29/月 拿 **2 年** EOD 链 + IV + OI，先算两列（30 天近月 `iv_skew_otm_put_minus_atm_call`、`oi_imbalance_put_minus_call`），进现有筛选器同一协议跑 IC/FDR/符号稳定性。2 年样本只能做"值不值得继续"的判断，不足以支持晋升。
3. 如果要长历史，从今天起我们自己每天归档一份 EOD 链（`fetched_at` + `input_hash`），一年后才有真 PIT 历史。**所以真正该现在做的是归档脚手架，不是回测。**
4. Cremers-Weinbaum 自己报告效应在样本期内衰减，加上 `ssrn2026_ai_driven_alpha_decay` 估计当前公开信号半衰期约 18 个月——对 2010 年的 50 bp/周不要做线性外推。

### 3.2 分析师修正（EPS / 评级修正）

| 来源 | 价格 | 内容 | 是否点时（PIT） | 历史深度 | 许可限制 |
|---|---|---|---|---|---|
| **EODHD Fundamentals Data Feed / ALL-IN-ONE** — 定价页已直接读取价格档位 | **$59.99/月** / **$99.99/月**（均 10 万次/日） | EPS trend（当前 / 7 / 30 / 60 / 90 天前）、EPS revisions（近 7/30 天上调与下调数）、分析师评级（Strong Buy…Sell）、目标价、升降级 | **不是真 PIT**：EPS trend 是"相对今天的若干天前"的派生快照，不是带时间戳的历史 vintage。搜索综合称 `historical` 参数可取历史评级快照（**未逐页核实**）。要做真 PIT，必须我们自己每天抓一次存档 | 价格历史 30 年，但**估计值的历史 vintage 深度未核实** | 定价页无明确再分发条款；商业用途另谈 |
| **Finnhub** — 端点文档 URL 已确认存在，价格未核实 | 有免费档 + 付费档（**月费本轮未核实成功**） | `company_eps_estimates`（季/年 EPS 共识）、`recommendation_trends`（评级分布趋势） | 同样是快照型；升降级事件带发布日期 → **事件型的那部分接近 PIT**，共识数值不是 | 未核实 | 未核实 |
| **Financial Modeling Prep (FMP)** | — | 有分析师估计与升降级端点（业内常见） | — | — | **定价页返回 403，本轮无法核实，故不作为推荐来源** |
| **Alpha Vantage**（我们已登记 `news.alpha_vantage`） | Premium 档（**页面超时，未核实价格与端点**） | — | — | — | 未核实 |
| 学术标准的真 PIT（I/B/E/S via WRDS） | 机构订阅 | 带 vintage 的历史共识与逐分析师修正 | 是 | 很长 | **个人研究者拿不到**，诚实说明 |

**文献与效应量：**

| 论文 | 信号 | 报告的效应 | 核实程度 |
|---|---|---|---|
| Barber, Lehavy, McNichols, Trueman (2001, JF 56(2):531-563)《Can Investors Profit from the Prophets?》 | 共识推荐等级 + 推荐变化 | 买最好/卖空最差 + **每日再平衡 + 及时反应** → **年化毛异常收益 > 4%**；但需要极高换手，**扣掉交易成本后净异常收益"不可靠地大于零"** | 搜索综合，未逐页核实 |
| Gleason & Lee (2003, The Accounting Review 78(1):193-225)《Analyst Forecast Revisions and Market Price Discovery》 | EPS 预测修正 | 修正后存在**价格漂移**；市场对"高创新"修正（带新信息）与"向共识靠拢"的低创新修正区分不足；覆盖分析师少的公司漂移更慢更不完全（**给的是方向性结论，不是单一数字**） | 搜索综合，未逐页核实 |

**【我的判断】可行性结论：**

1. Barber 等那句"扣成本后不可靠地大于零"对我们是**决定性的**：我们是周频、10 bp 成本、50 只等权。把分析师修正当**独立选股 alpha** 的期望值很低；当**确认门 / 加减仓概率**（和内部人一样的用法）才合理。
2. "免费 + 真 PIT"的分析师修正基本不存在。现实做法只有两条：花 $60–100/月拿快照，并**从今天起每日归档**（这才产生真 PIT）；或者干脆放到内部人与空头利息之后再做。
3. **所以我建议：分析师修正这层，这个月只做"每日快照归档"脚手架，不做回测、不写因子。** 等 2–3 个月自建历史够了再评估，同时也就自然解决了 PIT 问题。

### 3.3 已调研过的两项，可行性重述（引用已有来源卡）

| 项 | 数据可得性 | PIT 粒度 | 文献效应量 | 来源卡 |
|---|---|---|---|---|
| **FINRA 空头利息** | 免费；覆盖全部交易所上市 + OTC 股票；官网按结算日提供**滚动一年**在线数据，更早的要下载归档文件（官网页面已直接核实）；FINRA 数据页写明"提供**非商业用途**" | **每月两次（双周）+ 报告滞后** → 只能做月/双周频排序列或慢门控，不能进分钟/小时单元 | Hong 等（NBER WP 21166）：**days-to-cover 多空 1.2%/月**，且比原始空头利息比率更能预测差股票 | `step16_us_alpha_survey_sonnet_2026-09-11.jsonl` → `short_interest_days_to_cover_factor` |
| **SEC Form 4 内部人** | 免费、官方；**Insider Transactions Data Sets** 自 2006-01 起、季度发布、as-filed XML 展平（SUBMISSION / REPORTINGOWNER / NONDERIV_TRANS，含 FILING_DATE、TRANS_DATE、TRANS_CODE、TRANS_SHARES 等）；尾段用 EDGAR 日更 Form 4 索引补齐 | 可见日 = **FILING_DATE 的次一交易日**（**日粒度**，无受理时刻戳） | Cohen-Malloy-Pomorski (2012, JF)：**机会型内部人买入组合价值加权异常收益 82 bp/月，例行交易组≈0**；Tian-Xiang-Xu (JEF 2025)：内部人在异象多空腿的买卖比例可预测该异象未来收益（→ 支持"择时/确认"用法） | `step15_us_alpha_survey_round2.jsonl` → `sec_insider_transactions_data_sets`、`jef2025_insider_trading_and_anomalies`；`step16_...jsonl` → `insider_opportunistic_vs_routine_decay` |

**【我的判断】** 四项 Tier-1 的性价比排序很清楚：**Form 4（免费 + 官方 + 20 年历史 + 效应量最大）> FINRA 空头利息（免费，但双周频）> 期权 IV skew（$29/月，2 年历史）> 分析师修正（$60–100/月，且真 PIT 要自己养）**。先做免费的两项。

---

## 4. ML 方法 × 层：一个小的预注册网格

原则（回应你 2026-09-11 的批评）：**每层最多 3 格，方法要和这一层要回答的问题匹配，每格必须有规则孪生 + 打乱标签占位 + 留出验证 IC；DSR 按全部格子计数。** 总共 10 格，不是自由探索。

### 4.1 选股层（横截面排序）

| 格 | 方法 | 一句话解释 | 目标（标签） | 现有数据能跑吗 |
|---|---|---|---|---|
| S1 | **岭回归基线** | 带惩罚的线性回归，只用来当"ML 到底有没有增量"的分母 | `label_excess_5` | ✅ 能（SIP 日线 + 五张因子表 + `data/features/labels`） |
| S2 | **LambdaRank（learning-to-rank）** | 直接优化"排序对不对"，而不是预测收益数值——我们真正要的是前 50 名单 | 同一标签的**分组排序**（按周分组） | ✅ 能（LightGBM 自带 `lambdarank`） |
| S3 | **梯度提升二分类** | 只问"下周是否进入超额收益前 20%"，比回归稳 | 二值：`label_excess_5` 是否进入截面前 20% | ✅ 能 |

附加的**标签**变体（不新增方法，只换目标，各 1 格以内）：(a) 残差化标签（剔除市场/行业 beta 后的超额）；(b) **仅隔夜**标签 `ret_overnight_5`（用已有 SIP 分钟档案算，零新数据）——这一条同时检验 Lou-Polk-Skouras 的隔夜溢价在我们数据上是否存在。

### 4.2 择时层（体制判别，门控整个组合的暴露）

| 格 | 方法 | 一句话解释 | 目标 | 现有数据能跑吗 |
|---|---|---|---|---|
| T1 | **三态高斯 HMM** | 无监督地把市场分成"平静上行 / 震荡 / 高波动下行"三种状态 | 状态 → 暴露（1.0 / 0.5 / 0） | ✅ 能（`data/features/regime_daily`，2016→） |
| T2 | **梯度提升分类** | 有监督地直接预测"未来 10 日是否发生 >5% 回撤" | 二值回撤事件 | ✅ 能 |
| T3 | **因子择时分类** | 预测"未来 10 日动量多空腿收益的符号" | 二值符号 | ✅ 能 |

输入列：已实现波动、截面宽度、隔夜/日内收益比、SPY 距 200 日均线、（可选）新闻事件计数。**注意**：新闻计数只有 2024→（≈140 周），带它的格子必须单独标注小样本。

### 4.3 信号接受层（元标签：ML 不选股，只决定"要不要接受这个规则信号、给多少仓位"）

| 格 | 方法 | 一句话解释 | 目标 | 现有数据能跑吗 |
|---|---|---|---|---|
| A1 | **逻辑回归元标签** | 规则先给信号，模型只给"这次成功的概率"，概率 → 仓位档（0 / 1% / 2%） | 规则信号后 N 期收益是否为正 | ✅ 能（日频动量信号 2016→；1h Reversal Trend 信号 1352 笔，2024→） |
| A2 | **梯度提升元标签** | 同上，非线性版本 | 同上 + "是否先触及 1×ATR 收益"（三重障碍法的简化） | ✅ 能 |

元标签的好处正好对上我们的痛点：它不要求模型战胜规则（`ml_must_beat_rule_baseline` 对纯选股模型很难过），它只要求模型**砍掉坏信号**，改善的是回撤和 vol-matched 超额。

### 4.4 组合构造层

| 格 | 方法 | 一句话解释 | 目标 | 现有数据能跑吗 |
|---|---|---|---|---|
| C1 | **等权基线** | 现在的做法，前 50 各 2% | — | ✅ |
| C2 | **概率加权** | 按 S2/S3/A1 的概率在前 K 内分配权重 | 年化波动目标 15% | ✅ |
| C3 | **前 K 内风险平价** | 每只按 1/波动 定权重（或逆协方差） | 同上 | ✅ |

### 4.5 结论：全部 10 格都能在**现有数据**上跑，不需要任何新数据

需要的全部是：`data/sip/daily` + `data/sip/minute`（2016→）、`data/bars/hourly`（2024→）、五张因子表（alpha158 / alpha101 / alpha191 / osap_price / reversal_trend）、`data/features/labels`、`data/features/universe`、`data/features/regime_daily`、新闻 PIT 包（2024→，只喂择时层）。

**【我的判断】纪律条款（建议写进下一份计划）：**
- 在**同一批价量特征**上不再新增 LightGBM 回归格子。新格子只在满足以下之一时才开：(i) 加入了一个新数据层（内部人 / 空头 / 期权 / 分析师 / 新闻）；(ii) 换了一个**新的目标**（隔夜标签、残差化标签、回撤事件、元标签）。
- 每层的胜出格必须与**同层规则孪生**同时上报，且报告里永远带 SPY / MTUM / SPMO 与 vol-matched 超额四个数。

---

## 5. 彩排之后，下一个上模拟盘的候选

**候选：规则动量（PIT 前 500 ADV，`momentum_252_21 / vol_63` 前 50，周频，等权 2%，次日开盘 OPG）+ 内部人（Form 4）确认门 + 元标签仓位分档。**
也就是 W3c 的"确认信号"用法叠在 Step 17 已经彩排好的那条管道上，**换候选只改 spec**。

推理链，逐项写清：

| 项目 | 内容 |
|---|---|
| **用什么数据** | 全部免费：已有 SIP 日线 + `data/features/universe`（零成本）+ SEC Insider Transactions Data Sets（2006-01→，季度包）+ EDGAR 日更 Form 4 补尾段。可见日 = FILING_DATE 次一交易日。可选第二列：FINRA 空头利息 days-to-cover（免费，双周频，只做慢门控） |
| **用什么方法** | 两个孪生单元：门关（= 现在的规则基线）与门开（过去 60 日多头腿内部人净买入比例 > 中位数时满仓，否则减半/转 BIL）；外加一个元标签格 A1（逻辑回归给概率 → 0 / 1% / 2% 三档仓位）。规则基线必须同表上报 |
| **我们的起点（我们的证据）** | 规则动量 2024→ **33.0% CAGR / -28.3% MDD / 周胜率 0.616 / vol-matched SPY 超额 -11.0% / 4 项门槛通过**；诚实对照 SPY 20.9%、MTUM 29.8%、**SPMO 37.4% / -20.1%** |
| **期望（数字范围 + 来源）** | 【文献】Cohen-Malloy-Pomorski：机会型内部人买入 **82 bp/月** 异常收益（1986–2007 样本，价值加权多空组合口径，不是我们这种门控口径）；Tian 等 2025：内部人比例能预测异象多空收益（支持门控用法）。**【我的判断】把它当门控而不是独立组合，合理期望是"回撤改善 3–8 个百分点、CAGR 变动 -3 到 +5 个百分点"**——主要改善的是回撤与 vol-matched 超额，不是提高收益。这个区间是我从"门控只减少暴露、不新增选股信息"推出来的，**不是文献数字**，请当作假设看 |
| **成功判据（预注册）** | `cagr_excess_vol_matched_spy` 从 -11.0% 改善到 **> -3%**，且最大回撤 **优于 -22%**，且门开单元同时不低于门关单元的 CAGR 减 3 个百分点。达到就申请把它替换掉 Step 17 的彩排候选（同一 spec 形状、同一下单通道）|
| **什么会让我们停（任一命中即停，写报告、不上模拟盘）** | (1) 门开单元的 vol-matched 超额没有比门关单元改善 ≥3 个百分点；(2) 内部人特征进筛选器后，recent 窗 `|t| < 2` 且符号稳定性 < 0.7；(3) **可见日占位**：把 FILING_DATE 随机平移 ±30 个交易日后效应仍在 → 说明抓到的是市值/行业代理，不是内部人信息；(4) 采集器发现 10b5-1 计划交易无法从字段区分且占比 > 50%（信息含量被计划性交易稀释）；(5) 样本里门开/门关的切换次数 < 每年 4 次（门几乎不动，等于没加东西） |

**为什么不是期权或分析师修正？** 两者都要新花钱，而且**历史都不够**：Massive Starter 只有 2 年、Alpaca 期权只到 2024-02、分析师估计的真 PIT 要我们自己养 2–3 个月。先用免费且有 20 年历史的 Form 4 把 Tier-1 的管道（能力登记 → 采集器 → PIT 特征 → 筛选器 → 孪生单元 → spec）走通一遍，之后接期权/分析师只是换一个采集器。

**为什么不是继续调 ML 选股？** 【我们的证据】4 个 ML 单元全部输给规则孪生，最好的 alpha158 只有 14.8%；筛选集 IC 0.035 也只换来 17–19% 年化。在同一批价量特征上，ML 的空间已经被测完了。

---

## 6. 我接下来会做什么、为什么

1. **先把本周的 Step 17 彩排跑完，不动策略参数**（已改为每个交易日 23:30 UTC 自动挂单，首批周二晚挂单、周三 2026-09-16 开盘成交）。理由：先有一条能真下单、能做 TCA 的管道，以后换更好的候选只改一个 spec；策略好不好是下一个问题。
2. **立刻把 W1 从 2 个执行日缩成半天**（一次入场时机 A/B + 与你截图的 parity 核对），省下的时间全部给 W3c。理由：Tier-3 + 我们自己 0/18 过门槛 + 最好单元在网格边缘 + 姊妹单元占位解释 59%。
3. **启动 W3c（Form 4 内部人 PIT 包）作为 Tier-1 的第一块落地**：先在 `capabilities/registry.yaml` 登记能力并跑能力评估（项目规则），再写采集器，可见日严格 = FILING_DATE 次一交易日，且第一版就把"可见日占位"检验写进脚本。理由：免费、官方、2006 起、文献效应量最大（82 bp/月）。
4. **并行做两列零成本/免费的特征**：隔夜/日内分解（`ret_overnight_*` / `ret_intraday_*`，用已有分钟档案）+ FINRA days-to-cover（免费下载，双周频当慢门控）。两列都走 F 轨同一筛选协议。理由：单位成本的效应量最高（3.47%/月 与 1.2%/月 的文献量级）。
5. **把 W4m 缩成第 4 节那 10 格预注册网格，只在已有数据上跑**，并写进纪律条款："同一批价量特征上不再新增 LightGBM 回归格子"。理由：这是你指出的问题，我把它变成可检查的规则而不是口号。
6. **期权与分析师修正：本月只做"每日快照归档"脚手架**（`fetched_at` + `input_hash` + 每日一份 EOD 快照），不买订阅、不做回测；同时给你一份"$29/月 Massive Starter 拿 2 年 IV skew 做一次日频横截面检验"的可行性判断供你拍板。理由：这两层的瓶颈不是方法，是**我们还没有 PIT 历史**，而 PIT 历史只能从今天开始养。
7. **W4c（新闻事件 → PIT 特征）等 LLM 端点恢复后立刻插队，W4b（LLM 挖价量公式）继续押后**。理由：LLM 应该用在 Tier-1 文本上；在价量公式空间里挖，文献自己给出的天花板（标普 500 静态 Alpha158 RankIC 0.0081）就在那里。
8. **每周五固定一份对照表**：候选 vs SPY / MTUM / SPMO + vol-matched 超额 + 回撤。只要 vol-matched 超额还是负的，我不会申请晋升，只会申请"彩排/观察"。理由：这是我们 26 个单元唯一一致失败的门槛，它正好在防"跑得更热不是选得更好"。

---

## 附录：本轮用到的网络来源（URL + 访问日期）

全部访问日期均为 **2026-09-15**。

**直接抓取并核实的页面：**
1. Xing, Zhang, Zhao《What Does Individual Option Volatility Smirk Tell Us About Future Equity Returns?》（JFQA 2010）作者 PDF — https://www.ruf.rice.edu/~yxing/option-skew-FINAL.pdf （摘要原文本地抽取核实：10.9%/年）
2. 同论文期刊页（Cambridge Core / JFQA） — https://www.cambridge.org/core/services/aop-cambridge-core/content/view/ECFD16BA9ACBDC8D577D1BD866FBEA72/S0022109010000220a.pdf/what-does-the-individual-option-volatility-smirk-tell-us-about-future-equity-returns.pdf
3. Massive（原 Polygon.io）期权数据定价 — https://massive.com/pricing?product=options （Basic 免费 / Starter $29 / Developer $79 / Advanced $199；历史 2/2/4/5+ 年；Advanced 标注 Non-pros only）
4. EODHD 定价 — https://eodhd.com/pricing （Free / $19.99 / $29.99 / Fundamentals $59.99 / ALL-IN-ONE $99.99）
5. FINRA 股票空头利息数据目录页 — https://www.finra.org/finra-data/browse-catalog/equity-short-interest/data （覆盖全部交易所上市与 OTC；在线滚动一年 + 归档下载；写明"非商业用途"）

**搜索结果综合、未逐页核实（引用时已在正文标注）：**
6. Cremers & Weinbaum《Deviations from Put-Call Parity and Stock Return Predictability》SSRN — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968237 （50 bp/周；JFQA 45(2):335-367）
7. Pan & Poteshman《The Information in Option Volume for Future Stock Prices》RFS — https://academic.oup.com/rfs/article-abstract/19/3/871/1646711 ；作者 PDF https://www.mit.edu/~junpan/volume.pdf （次日 40+ bp、一周 1%+）
8. Barber, Lehavy, McNichols, Trueman《Can Investors Profit from the Prophets?》JF — https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00336 （年化毛异常收益 >4%，扣成本后净额不可靠为正）
9. Gleason & Lee《Analyst Forecast Revisions and Market Price Discovery》TAR — https://meridian.allenpress.com/accounting-review/article-abstract/78/1/193/53357/Analyst-Forecast-Revisions-and-Market-Price ；SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=370425
10. Alpaca 期权历史数据文档 — https://docs.alpaca.markets/us/docs/historical-option-data ；行情订阅说明 https://docs.alpaca.markets/us/docs/about-market-data-api （历史期权自 2024-02 起；OPRA 实时需 Algo Trader Plus）
11. Finnhub EPS 估计端点文档 — https://finnhub.io/docs/api/company-eps-estimates ；定价页 https://finnhub.io/pricing （端点存在已确认，**月费未核实**）

**尝试失败、故不作为来源（诚实记录）：**
12. https://polygon.io/pricing?product=options — 301 跳转到 massive.com（品牌已改名，原 URL 不再直接可用）
13. https://site.financialmodelingprep.com/developer/docs/pricing — HTTP 403，FMP 的价格与端点覆盖**本轮无法核实**
14. https://www.alphavantage.co/premium/ — 请求超时，Alpha Vantage Premium 价格与分析师端点**本轮无法核实**
15. 免费的个股级历史期权链（含 IV/greeks）— 搜索到的都是商业供应商（historicaldata.net / historicaloptiondata.com / ivolatility.com / OptionMetrics / FirstRate），DoltHub 上的免费期权库**未得到确认**；请把"有免费替代"当作未证实

**仓库内已有来源卡（按 claim_id 引用，本轮未重做）：**
`step16_us_alpha_survey_sonnet_2026-09-11.jsonl`：`insider_opportunistic_vs_routine_decay`、`short_interest_days_to_cover_factor`、`13f_conviction_consensus_best_ideas`、`overnight_intraday_tug_of_war_momentum`、`market_intraday_momentum_first_last_half_hour`、`kyle_lambda_signed_order_flow_daily_crsp`、`gap_fade_volatility_compression_breakout_no_rigorous_numbers`、`ic_above_0p05_ohlcv_only_continuation`、`llm_extracted_signals_10k_earnings_calls_verified`、`post_publication_factor_decay_chen_zimmermann_verified`、`end_of_day_reversal_gap_fade_continuation`、`retail_attention_wsb_google_trends_continuation`；
`step15_us_alpha_survey_round2.jsonl`：`sec_insider_transactions_data_sets`、`jef2025_insider_trading_and_anomalies`、`arxiv2601.06499_cross_market_alpha_gtja191_us`、`arxiv2608.12841_aqua`；
`step15_us_alpha17_formulas.jsonl`（GTJA-17 公式核对与两处阻塞）；
`step14_llm_alpha_mining_2026.jsonl`：`ssrn2026_ai_driven_alpha_decay`、`arxiv2602.14670_factorminer` 等；
`step13f_open_factor_libraries.jsonl`：`alphamemo_sp500_alpha158_decay_2026-09-09`、`qlib_benchmark_lightgbm_alpha158_csi300_2026-09-09`、`osap_crsp_only_signals_2026-09-09`。

（按项目规则，不引用 Kim, Muhn, Nikolaev "Bloated Disclosures"——该文已被作者撤回。）
