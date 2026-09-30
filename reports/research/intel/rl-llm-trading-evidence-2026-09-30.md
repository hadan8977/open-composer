# 强化学习交易 / "大模型 + 强化学习"交易：公开证据简报（T-20260930-18，接手 T-20260929-31）

日期 2026-09-30（UTC 13:45–13:52 抓取）。只调研，没有训练、没有调用 Modal、没有下单。来源快照在 `reports/research/intel/sources/rl-llm-2026-09-30/`（文件名即来源，全部 .txt）。

## 结论（5 行）

1. **现在不值得花 Modal 钱试，登记为 `parked`。** 没有一条证据同时满足"实盘或前向 + 扣了成本 + 有基线 + 独立复现"。
2. **最强的正面证据是 Alpha-R1**（Qwen3-8B + GRPO，2024 训练、2025 全年样本外，每边 10 bp，标普 500 池年化 47.87%、夏普 1.62）。但它只有一年、无独立复现、训练用 64 张 H800 约 120 小时（约 7,680 卡时，我们的 $3 约合 0.76 个 H100 小时），新闻输入是专有数据，作者自己报的多重检验后 DSR：标普 500 为 0.6641（N=158）到 0.8369（N=34），小盘池只有 0.39–0.41。本仓库跑不了，也复现不了。
3. **最强的反面证据有两条。**（a）Alpha Arena 1.5：32 个实盘账户只有 6 个为正，赢过第 1 季的 Qwen3 Max 在 4 个账户里全亏（-6.79% 到 -82.06%）。（b）独立复现的 FinRL PPO：15 只纳指股、每笔 0.10% 成本、2019–2023 测试，夏普 0.559，等权持有 1.115。
4. **前视与记忆是结构性问题**：大模型在训练截止日之前的回测都是样本内。只有截止日之后的数据才算干净，所以任何测试都必须落在 2025 年以后的窗口。
5. **重开条件**：出现"权重和数据都公开、训练截止日之后、扣 ≥10 bp 成本、且赢过同输入表格基线"的独立复现，或 nof1 公布多次重复运行并给出显著性。**若要现在试的最便宜否定测试**：先用 $0 的表格基线（同输入的 LightGBM/岭回归排序，同成本，冻结窗口）判断输入里有没有信号；没有就停，有才花 ≤$3 跑 0.5B–1.5B 模型的 GRPO 与它对比（设计见第 5 节）。

## 1. 证据表

图例：类型 = 实盘（真钱）/ 前向（实时数据、非真钱或未成交）/ 回测。"独立复现"栏写"无"表示没有找到。数字都能在对应快照里找到。第三方转述的 nof1 数字标"转述"。

| # | 证据 | 类型 | 市场、时期、样本长度 | 成本 | 结果（原文数字） | 对比买入持有/基线 | 独立复现 | 对本仓库的相关性 |
|---|---|---|---|---|---|---|---|---|
| 1 | nof1 Alpha Arena 第 1 季（6 个大模型，零样本提示，无 RL 训练） | 实盘 | Hyperliquid 加密永续 BTC/ETH/SOL/BNB/DOGE/XRP，每模型 $10,000，2025-10-18 至 2025-11-03，约 16 天，每 2–3 分钟一次推理（转述 tradepartner-g6…report） | 真实手续费；转述 TechPost1："PnL was dominated by trading costs in early runs"；未见滑点、资金费率数字 | 转述 iweaver（nof1 网站数字）：Qwen3 Max +22.3%（约 43 笔），DeepSeek +4.89%，Claude Sonnet 4.5 -30.81%，Grok 4 -45.3%，Gemini 2.5 Pro -56.71%，GPT-5 -62.66%。Forklog 用创始人发布的余额：Qwen $12,231，DeepSeek $10,489，Claude $5,799，Gemini $5,445，Grok $4,208，GPT-5 $4,126（两处口径不一致，Gemini/Grok 名次也不同） | 无买入持有或随机基线；nof1 自己说"single run"不能定最佳模型，"early successes may be the result of luck"（转述） | 无；第 1.5 季换了市场和提示，不算复现 | 低：加密永续高杠杆；模型没有做 RL；16 天 |
| 2 | Alpha Arena 第 1.5 季（8 个模型 × 4 个并行赛，共 32 个账户） | 实盘 | 美股名字（TSLA、NDX、NVDA、MSFT、AMZN、GOOGL、PLTR；是否为杠杆永续无法确认），2025-11-20 至 2025-12-03，约 2 周（KuCoin/MarsBit 转述开始日） | 排行榜列手续费；如 qwen3-max 新基线赛 $1,299/976 笔，grok-4.20 情境赛 $730/158 笔 | 32 个账户中 6 个为正（转述 tradepartner 表）；Grok 4.20 四赛 +34.59%、+3.66%、+1.93%、+0.48%；第 1 季冠军 Qwen3 Max 四赛 -6.79%、-20.24%、-41.37%、-82.06%；32 个账户 P&L 之和约 -$112,580 / $320,000 = 约 -35.2%（转述方自己的加总）。首页称赢家 12.11% / $4,844，排行榜四行加总约 $4,066（+10.17%），未对上 | 无买入持有基线；四个并行赛共用同一段行情，不是独立样本 | 无；名次在两季之间翻转（第 1 季冠军第 1.5 季全亏） | 低-中：证明零样本大模型实盘多数亏，与 RL 无关。第 2 季：截至 2026-08-06 无公开结果（TradeRank 转述，8-27 重访被 403） |
| 3 | LiveTradeBench（Yu 等，UIUC，21 个大模型，零样本） | 前向（实时价格 + 新闻，非真钱） | 美股 15 只（yfinance）与 Polymarket，2025-08-18 至 2025-10-24，50 个交易日 | **无**：论文局限一节明写不计手续费、买卖价差、流动性 | 美股累计收益 1.78%（Qwen3-235B-Thinking）到 6.25%（GPT-4.1），21 个模型全为正；GPT-5 5.31%，Qwen2.5-72B 5.15%。Polymarket 多数大负（如 Qwen3-235B-Thinking -57.62%）。两市场夏普相关约 0；LMArena 分数与美股收益的 Spearman 0.054 | 表中没有买入持有或等权行；提示词要求跑赢等权，但没有报数 | 无 | 中：说明通用能力与收益无关；没扣成本、窗口是科技股上涨段（论文提到 8-28 科技股反弹） |
| 4 | Trading-R1（Tauric，Qwen3-4B，SFT + GRPO 三阶段课程） | 回测 | NVDA/AAPL/MSFT/AMZN/META/SPY，测试 2024-06-01 至 2024-08-31（3 个月）；训练语料 2024-01 至 2025-05，14 只股票，10 万样本 | 回测未见交易成本说明；成本项 κ 只在训练奖励里 | NVDA 累计 8.08% 夏普 1.88；AAPL 夏普 1.80（GPT-4.1 为 1.24）；SPY 累计 3.34%、夏普 1.60、最大回撤 1.52%；AMZN 5.39%（1.72）；META 5.12%（0.86） | 表里的对手是其他大模型，没有买入持有行；论文自己写"best used as a research and thesis-generation tool"，回测"not a guarantee" | 无；README 至 2026-09-30 仍写 "Terminal coming soon"，未见权重链接 | 中低：小模型可训（8×H100 做 SFT，8×H200 做 RL，我们跑不动）；测试窗口落在训练语料的日历范围内，且只有 3 个月 |
| 5 | FLAG-Trader（SmolLM2-135M + PPO，部分微调） | 回测 | MSFT/JNJ/UVV/HON/TSLA，测试 2020-10-01 至 2021-05-06；BTC 测试 2023-04-05 至 2023-11-05 | 论文未见成本设定 | 累计收益 vs 买入持有：MSFT 20.106 vs 15.340；JNJ 33.724 vs 13.895；UVV 46.799 vs 36.583（最大回撤 35.039 vs 15.406）；HON 34.342 vs 33.256；TSLA 50.394 vs 39.244；BTC 45.511 vs 21.821 | 有买入持有行；取"中位数运行"汇报，未给多种子区间；同表 13 个零样本大模型里 MSFT 有 7 个低于买入持有（我数的） | 无 | 中：模型极小、算力可行；窗口全在 2021 年前，且成本未扣 |
| 6 | Fin-R1（Qwen2.5-7B，SFT + GRPO） | 基准问答（非交易） | FinQA/ConvFinQA 等 5 个数据集 | — | 平均 75.2，对 Qwen2.5-7B-Instruct 的 65.6；FinQA 76.0 vs 60.0 | — | 无 | **无关**：没有任何交易或收益测试，只说明 RL 能提高金融问答，不是赚钱证据 |
| 7 | TradingAgents（Tauric，多智能体，未做 RL 训练） | 回测 | AAPL/GOOGL/AMZN，2024-01-01 至 2024-03-29（3 个月） | 未见成本说明 | 累计收益 26.62%/24.36%/23.21%；夏普 8.21/6.39/5.60（作者自注"exceeds our expected empirical range"，归因"few pullbacks"） | 买入持有 -5.23%/7.78%/17.1%；MACD、KDJ+RSI、ZMR、SMA 也在 | 无；Profit Mirage 复测：基座模型发布后夏普衰减 55.68% | 低：3 个月，且落在 GPT-4o 已知区间内 |
| 8a | FinRL 竞赛 2023 任务 1（数据为中心的股票交易） | **前向**（提交截止后的真实窗口） | 道指 30 只，2023-10-25 至 11-14（15 个交易日）、11-15 至 11-22（6 个交易日） | 论文未说明 | 前三名累计收益 1.05%/3.50%/2.35%（DJIA 5.42%）；第二窗口 -0.03%/0.04%/-0.05%（DJIA 0.80%）。论文原文："poorer profitability compared with the Dow Jones Index"，夏普"reported wrongly" | 全部低于道指的收益，只在夏普和回撤上占优 | 竞赛本身即多队 | 中：这是少有的真前向，且结果是输给被动持有 |
| 8b | FinRL 竞赛 2023–24 集成方法论文（Columbia） | 回测 | 道指 30 只，2020-01-01 至 2023-01-01，滚动窗口；BTC 订单簿 12 天 | 论文框架提到成本/滑点，结果表未单列 | PPO 累计 63.37%、夏普 1.55；DJIA 18.95%、夏普 0.47；最小方差 13.9%。BTC 任务：集成 0.66% vs BTC 价格 0.74% | 有指数与最小方差基线 | 无 | 低：窗口含 2020 年反弹，训练与测试同一段 |
| 8c | FinRL 竞赛 2025 任务 1（FinRL-DeepSeek）榜单 | 回测 | 纳指 100 成分；评估期 2019–2023（据 DAPO 论文对竞赛指南的说明，榜单表本身未写期间） | 未说明 | Refined GRPO 累计 335.57%、夏普 0.95、最大回撤 -50.24%；标普 500 90.03%（-33.93%）；纳指 100 164.52%（-35.56%）；Queen's Gambit 342.65% 但回撤 -92.47% | 高收益伴随 -50% 到 -92% 回撤 | 无 | 低：回撤不可用，测试窗 6 年且与训练重叠 |
| 8d | FinRL 竞赛 2024 RLMF（LLaMA-3.2-3B 用市场反馈微调，做情绪信号） | 回测 | 7 只大盘股，2022-10-09 至 2023-12-15（229 天），做多情绪最高 3 只、做空最低 3 只，持有 3 天 | 未说明 | 累计 134.05% vs 买入持有 72.71%，盈亏比 1.5 | 有买入持有 | 无 | 中：最接近"小模型 + RL + 文本信号"的便宜形态；但窗口在 LLaMA 3.2 已知区间内 |
| 9 | FinRL-DeepSeek（Benhenda，CPPO + LLM 新闻信号） | 回测 | 纳指 100，2019–2023（训练 2013–2018）与 2023 年 | 未说明 | 原文："The use of LLM always worsens performance in this test"；PPO"remains too volatile"；两次运行结果不同 | 图 1 的配置没能跑赢纳指 100 | 无 | 中：作者自己的负面结果 |
| 10 | DAPO/GRPO 股票交易（Columbia，竞赛第 2 名） | 回测 | 纳指 100，2020–2023 与 2019–2023 | 未见成本说明 | 累计 230.49%（回撤 -49.11%，信息比率 0.37）；2019–2023 为 335.58%（-50.24%） | 对手只有 CPPO-DeepSeek（约 215%）；纳指 100 本身 164.52%（见 8c） | 无 | 低 |
| 11 | News-aware Direct RL（GRPO/DDQN + LLM 情绪） | 回测 | BTC 分钟线，测试期至 2024-01，三个动作（多、空、持有） | 未见手续费设定（只有 0.1% 止盈止损） | GRPO LSTM 带 LLM 信号 124.5%，不带 68.3%；BTC 市场基线 56% | 有 BTC 持有基线 | 无 | 低：分钟级无成本，结果不可信 |
| 12 | **Alpha-R1**（Qwen3-8B + GRPO，做二阶段因子重排；输出 top-10 等权多头，5 日持有） | 回测（作者称严格样本外） | 标普 500 与沪深 300 等 4 个池，训练 2024，测试 2025-01-01 至 2025-12-31，12 个月 | **是**：双边 10 bp、VWAP 成交、槽位轮换；论文用时间点成分股 | 标普 500 年化 47.87%、夏普 1.62、回撤 16.91%；沪深 300 40.57%/2.23；罗素 2000 80.54%/2.46；沪深 1000 73.52%/2.80。PSR 0.9612（标普）；DSR 在保守试验数 N=158 下 0.6641，N=34 下 0.8369；PBO 0.0494 | 标普买入持有 19.34%/夏普 0.80；FinRL 风格 PPO 7.68%，SAC 37.60%；零样本 Qwen3-8B 12.85%；作者称去掉 RL 后 AR 降到 12.85% | **无**；代码在 GitHub，但原始行情/新闻和专有模型输出不再分发 | 中：唯一同时有"截止日后 + 成本 + DSR"的 RL+LLM 结果。但 64 张 H800 × 约 120 小时，输入依赖专有新闻和 Claude 3.7 做状态合成，一年一个窗口，作者自己给出的热力图峰值 176.03%（TopN=2–3）说明结果对参数敏感 |
| 13 | 独立诊断：QINN-FinRL-Evaluation（GitHub，第三方学生仓库，匹配种子） | 回测（样本外） | 15 只纳指股，PPO 训练 2013–2018，测试 2019–2023 | **是**：每笔 0.10% | 基础 FinRL PPO 夏普 0.559、总收益 73.24%、回撤 -40.46%；加 ANN 信号 0.735；等权基线夏普 1.115、总收益 218.25%、回撤 -28.54%。十种子正式评估：ANN 0.821，MPS 0.784 | 全部低于等权持有（三种子参考运行） | 第三方独立评估，不是对某一篇论文的逐项复现 | 高：与本仓库口径接近（成本、多种子、基线），结论为负 |
| 14 | StockBench（清华，13 个大模型 + 被动基线，零样本） | 回测（截止日后、称"contamination-free"） | 道指 20 只，2025-03-03 至 2025-06-30（82 个交易日），每模型 $100,000，开盘成交 | 快照里未见手续费/滑点设定 | 期末收益：Qwen3-235B-Thinking 2.5%、Qwen3-235B-Instruct 2.4%、GLM-4.5 2.3%、Kimi-K2 1.9%（Sortino 最高 0.0420）、GPT-5 0.3%、GPT-OSS-20B -2.8% | 被动等权买入持有 +0.4%、回撤 -15.2%；13 个模型中 8 个高于被动收益（我数的）。**版本冲突**：摘要写"most models struggle to outperform"，正文 v2 写"Most tested models outperform the passive baseline" | 无 | 中：窗口短、差距 1–2 个百分点、单次运行、无成本 |
| 15 | InvestorBench（Stevens/FinAI，13 个大模型） | 回测 | 2020-07 至 2021-05 的股票、BTC、ETF | 未见 | 逐模型与买入持有比较；它的基线数字与 FLAG-Trader 表 1 是同一组（MSFT 买入持有 15.340 等），我数得 13 个模型里 7 个低于买入持有 | 大量模型不超买入持有 | 无（FLAG-Trader 沿用同一数据集） | 低：窗口完全在这些模型的训练数据内 |
| 16 | AI-Trader（HKU，6 个大模型，零样本） | 前向（实时，未见真钱） | 纳指 100 每小时 2025-10-01 至 2025-11-07；加密 2025-11-01 至 11-14；A 股 | 快照未见成本设定 | 美股：MiniMax-M2 9.56%、DeepSeek-v3.1 8.39%、Claude-3.7 3.11%、GPT-5 1.56%、Qwen3-Max 0.39%、Gemini-2.5-Flash -0.06%；QQQ 1.87%。加密：6 个全为负（GPT-5 -16.41%、Qwen3-Max -16.85%、Gemini -18.63%），DeepSeek -12.18% 是唯一好于 CD5 指数 -14.30% 的。A 股：无一超过 SSE-50 的 1.65% | 有 QQQ/指数基线；作者结论"General intelligence ... does not automatically translate into effective trading capability" | 无 | 中：窗口 5 周；美股 6 个里 3 个没跑赢 QQQ |
| 17 | Agent Market Arena（FinAI，4 种智能体 × 5 个模型） | 前向（实时） | TSLA、BMRN、BTC、ETH，约 2 个月（2025-08 至 09） | 未见成本说明 | InvestorAgent 在 TSLA 夏普 6.47；作者结论"consistently outperform simple buy & hold"；框架比模型更决定行为 | 有买入持有 | 无 | 低：4 个品种、2 个月、夏普 6.47 本身就是过拟合信号 |
| 18 | ChatGPT Micro-Cap Experiment（Nathan Smith，ChatGPT 每周深度研究选股，无 RL） | 实盘（小额，$100 规模） | 美股微盘股（<$3 亿市值），24 周至 2025-12-14 | 未详述 | 早期四周约 +24%（Decrypt/Benzinga，仅检索摘要）；第 24 周：净值 $82.59，同期标普 $110.72；最大回撤 -50.33%（2025-11-06）；年化 alpha -34.84%（R² 0.017，观测 110）；年化夏普 -0.2888 | 落后标普约 28 个点 | 作者公开日志 | 中：典型"前几周运气，后面回吐"的案例；无 RL |
| 19 | dev.to 转述的中文社区帖（Claude 每日分析 + 券商 API） | 实盘（$500） | 7 个交易日 | 零佣金 | $510.65（+2.20%）；同期 VOO 1.88%、QQQ 2.05% | 略高于指数 | 无 | 轶事级，不作证据 |
| 20 | 综述：Agentic Trading（深圳大学，2026-05，77 项研究） | 综述 | 截至 2026-03-09 | — | 主要实证子集 19 项中：仅 2 项有时间一致的数据划分、1 项明确交易成本模型、1 项处理幸存者偏差、11 项报告成交时点，0 项达到最高可复现等级 R3 | — | — | 高：直接说明这个领域的样本外证据质量很低 |

论坛与博客：按要求搜过 Reddit r/algotrading 与 QuantConnect 论坛的实盘帖，检索没有返回可用的原帖（只有通用文章和 TradingView 日记），所以这一块没有证据可列，不是"没有帖子"的证明。

## 2. 证据质量的判断

- **实盘证据只有 Alpha Arena 和 ChatGPT 微盘股。** 两者都是零样本大模型，没有 RL 训练；Alpha Arena 每季只有 16 天和约 2 周，没有买入持有基线，名次在两季之间翻转；微盘股账户运行 24 周，从早期的 +24% 变成落后标普约 28 个点。这类证据说明"零样本大模型直接下单多数亏"，不说明"RL 训练后的大模型赚钱"。
- **有 RL 训练的证据全是回测**（Trading-R1、FLAG-Trader、FinRL 系、DAPO、Alpha-R1），而且测试窗口多为 3 个月到 5 年，常与训练窗口重叠，绝大多数没扣成本。综述（第 20 行）量化了这一点：1/19 报成本。
- **有基线的对比里，RL 输给被动持有的居多**：FinRL 竞赛 2023 前向（第 8a 行）、独立 PPO（第 13 行）、FinRL-DeepSeek 自己的负面结果（第 9 行）。赢的多数出现在含大牛市的样本内窗口（第 8b、8c、10 行），且回撤 -50% 起步。
- **Alpha-R1 是例外**：设计最规范（截止日之后、10 bp、PSR/DSR/PBO），但也是单一年份（2025 年，标普买入持有 19.34%）、无人复现、我们复现不了。作者的 DSR 在保守试验数下只有 0.6641（标普 500，N=158）和 0.8459（沪深 300），沪深 1000、罗素 2000 只有 0.4121/0.3858（N=101）。没有其他人能在不同数据、不同年份重复它之前，只能当作"值得关注的单点"。

## 3. 前视与记忆问题

- **大模型的训练截止日之前，任何回测都是样本内。** Lopez-Lira 等（2504.14765）：大模型能回忆经济与金融数据的精确值，"Instructions to respect historical boundaries fail to prevent recall-level accuracy"，遮蔽实体和日期也失败（模型会从少量上下文还原），"Post-cutoff, we observe no recall"。Gao 等（2512.23847）给出统计检验：前视倾向在样本内为正，"collapses essentially to zero right after the training-data cutoff"，新闻标题预测收益的预测力在高倾向样本上被放大，截止日后不再显著。
- **Profit Mirage（2510.07920）**：GPT-4o 等对"某日市场是否上涨"的历史问答正确率超过 85%；TradingAgents、FinMem、FinCon 等在基座模型发布之后夏普衰减 51.48%–62.23%，TradingAgents 为 55.68%。
- **对本仓库的含义**：（1）一切用大模型的测试，测试窗口必须在该模型训练截止日之后。Alpha-R1 的表 10 给出 Qwen3-8B 的截止日为 2024-09（提供方文档，论文称无法独立验证）；Qwen2.5 的截止日未见官方数字，本简报不假设具体日期，建议按 ≤2024-09 处理。因此干净窗口是 2025-01 起。（2）训练窗口在截止日之前没问题，因为我们自己训练策略；危险在测试窗口。（3）遮蔽代码和日期不够，只有截止日之后的窗口才算数。（4）2025 年以后只有约 20 个月，含 2025 年 4 月关税冲击和之后的动量行情，只是一个或两个行情阶段，结论必须写明适用状态和有效期。
- **纯表格 RL**（不含大模型）没有这个问题，但它的问题是第 13 行所示的样本内外差距。

## 4. 与本仓库已有结论的关系

- `docs/research-program.zh.md` 的"模型只能放大已有的信号，不能凭空造出信号"：证据与它一致。FinRL-DeepSeek 里加 LLM 反而更差（第 9 行）；LiveTradeBench 里通用能力与收益无关（第 3 行）；Alpha-R1 自己的消融显示去掉 RL 后夏普跌到 0.80 以下，但这个增量建立在一个已经含 Alpha101 因子池预筛选的候选池上，也就是"信号是别处给的，RL 只在重排"，并不是无中生有。
- 登记簿已有两行：`dir:finrl_deep_rl`（evidence_too_weak，理由是独立诊断里 PPO 低于所有基线）和 `dir:llm_as_trader_portfolio_manager`（evidence_too_weak，Agent Market Arena 一类）。本简报新增的可指认信息：Alpha Arena 1.5 的 32 账户实盘表、LiveTradeBench/StockBench/AI-Trader 的截止日后前向窗口、Alpha-R1 的带成本与 DSR 的样本外结果、FinRL 竞赛 2023 的真前向结果、综述的证据质量统计。它们没有改变结论，只是把"证据太弱"细化成"没有可复现的正面，一个不可复现的强正面"。
- 与已有线的关系：文本信号线（`dir:pead_xbrl_8k_llm`、`dir:llm_8k_gdelt_sentiment_acceleration` 等）才是大模型真正能提供新信息的地方；RL 是训练手段，不是信息来源。如果那些线出现表格基线有信号的文本特征，才轮到问"RL/GRPO 能不能在它上面增量"。

## 5. 能不能便宜地试

**判断：现在不试。** 理由：（1）没有正面证据值得排在已排队的隔夜延续线（T-20260930-14/16）前面；（2）RL 的种子方差很大（FinRL-DeepSeek 两次运行结果不同；FinRL 竞赛论文写策略对超参数和随机种子敏感），$3 预算跑不出有统计功效的多种子对比；（3）Alpha-R1 那种设置我们复现不了。

若机主要求先看一眼，**最便宜的否定测试**（草案，尚未预注册，跑之前要走 `direction-check` 和 `iteration validate`）：

1. **阶段 P0（$0，本机）：同输入表格基线有没有信号。** 用仓库已有的 SIP 日线（先 `sanitize_price_matrices`，去掉拆股类触发日），把将要喂给小模型的同一组数字特征（滞后收益、成交量 z、行业）做成表格，用岭回归或 LightGBM 按周排序做多空/多头 top-N，10 bp 每边，收盘信号次日开盘成交，冻结测试窗 2025-01-01 至今。若净夏普不显著大于 0（我们已有的 ML 排序线历史上多数如此），**停止，RL 无信号可放大**，花费 $0。
2. **阶段 P1（仅 P0 通过后，Modal，估算 ≤$3）：** Qwen2.5-0.5B（或 1.5B）+ LoRA + GRPO，输入为匿名化的数字提示（代号替代代码、相对日期、无新闻），奖励为下周相对收益扣 10 bp 成本；训练 ≤2024-06，验证 2024-07 至 2024-12，测试 2025-01 至今且不得重用已看过的窗口。3 个种子，加"打乱奖励"的安慰剂运行，和 P0 的表格基线、零样本同模型、等权持有同口径比较。
3. **门槛**：净夏普比表格基线高 ≥0.3，配对自助法区间下界 >0；三种子同号；安慰剂 ≤0；按 DSR 计入试验数后 ≥0.95。任一不满足即关闭这条线。
4. **算力估算（未实测）**：用本仓库 `scripts/modal_budget.py` 的费率，A10G $1.10/小时，T4 $0.59/小时，H100 $3.95/小时；$3 约合 2.7 个 A10G 小时。0.5B 模型、短提示、短输出的 GRPO，估计 3 个种子共 2 个 A10G 小时以内，仍需先用 `python3 scripts/modal_budget.py check` 通过，函数 `timeout=` 等于检查的分钟数，只上传特征 parquet，不上传任何密钥。
5. **前视防护**：测试窗只用 2025-01 以后；训练/验证窗与测试窗之间留空；提示里不放真实代码和日期；另跑一个零样本同模型运行，若零样本在测试窗也有非零"预测力"，说明提示里泄漏了实体信息，作废。
6. **需要的数据**：仓库现有 SIP 日线；不需要新闻。要做文本信号版本，需要带发布时点的新闻数据集，本仓库目前没有，也不属于本任务。

**重开条件**（`reopen_if`）：（a）Alpha-R1 或同类（权重与数据公开、截止日后、≥10 bp 成本、赢过同输入表格基线）出现独立复现；（b）nof1 公布重复运行与显著性检验，或 Alpha Arena 第 2 季给出多次运行；（c）我们的文本线拿到带发布时点的特征且表格基线有信号，此时再问 RL/GRPO 的增量。

## 6. 没做完 / 局限

- nof1 官网（TechPost1、排行榜）对抓取返回 429，Wayback 也被拦，所以第 1、2 行的 nof1 原始数字来自第三方对 nof1 原文的转述（tradepartner 报告逐字引用 TechPost1 和排行榜，iweaver/Forklog/KuCoin 转述赛果），未能直接核对原页。三处转述的第 1.5 季赢家数字并不一致（12.11%、约 10.17%、22.38%）。
- **主审补注（Opus 交互主审，2026-09-30 13:56 UTC）**：tradepartner G6 报告本身是 AI 研究代理写的（文件头写着 "Agent/model: researcher, claude-opus-5-5"，2026-09-26），属于三手来源。它的 Alpha Arena 数字（32 个账户中 6 个为正、Qwen3 Max 四赛全亏）没有和 nof1 原页核对过，只能当方向性证据；结论不依赖这组数字，因为有 RL 训练的证据全是回测这一点不受它影响。
- 论坛/Reddit 实盘帖没有搜到可用原帖。
- 没有读完全文的：InvestorBench（只读了设置与表头，逐模型对比引用了 FLAG-Trader 同表数字）、DAPO 论文（读了摘要、结果表与成本相关词）、Fin-R1（读了摘要和结果表）、FinRL 竞赛 2025 总览（读了榜单与任务描述）、Agentic Trading 综述（读了摘要和引言统计）。
- 未审计的：Trading-R1、FLAG-Trader 的代码；未查 Hyperliquid 链上记录。
- 所有 GPU 小时与美元估算都是按本仓库费率表的粗算，未实测。

## 7. 来源清单

层次：全文 = 下载了全文并搜读了相关章节；摘要 = 只读了摘要与部分章节；检索摘要 = 只有 WebSearch 摘要。抓取时间均为 2026-09-30 UTC。

| 来源 | URL | 抓取（UTC） | 层次 | 快照文件 |
|---|---|---|---|---|
| nof1 博客索引 | https://nof1.ai/blog | 13:45 | 索引页（列出四个赛、无第 2 季） | nof1-blog.txt |
| nof1 About | https://nof1.ai/about | 13:45 | 抓取成功，未引用具体数字 | nof1-about.txt |
| nof1 TechPost1 / 排行榜 | https://nof1.ai/blog/TechPost1 ；https://nof1.ai/leaderboard | 13:45 | **失败（429 安全检查页），只有转述** | 未保存（页面为拦截页） |
| tradepartner G6 报告（第三方，AI 研究代理所写，声称逐字引用 nof1；三手来源） | https://raw.githubusercontent.com/josejuarez96/tradepartner/main/docs/research/2026-09-26-g6-alpha-arena.md | 13:46 | 全文 | tradepartner-g6-alpha-arena-report.txt |
| iweaver 第 1 季结果 | https://www.iweaver.ai/blog/alpha-arena-ai-trading-season-1-results/ | 13:45 | 全文 | iweaver-alpha-arena-s1-results.txt |
| Forklog 第 1 季 | https://forklog.com/en/four-out-of-six-ai-models-suffer-losses-in-trading-tournament/ | 13:45 | 全文 | forklog-four-of-six-losses.txt |
| KuCoin 转述第 1.5 季 | https://www.kucoin.com/news/flash/alpha-arena-1-5-season-results-grok-4-20-leads-with-22-38-return | 13:46 | 全文（含大量页面模板） | kucoin-alpha-arena-1-5.txt |
| TradeRank Alpha Arena 评述（第 2 季状态） | https://www.traderank.ai/blog/alpha-arena-alternatives-2026 | 13:51 | 全文 | traderank-alpha-arena-alternatives-2026.txt |
| LiveTradeBench 2511.03628 | https://arxiv.org/pdf/2511.03628 | 13:46 | 全文（读了摘要、结果表、局限） | arxiv-2511.03628-livetradebench.txt |
| Trading-R1 2509.11420 | https://arxiv.org/pdf/2509.11420 | 13:46 | 全文（读了摘要、评估设计、表 3/4、局限） | arxiv-2509.11420-trading-r1.txt |
| Trading-R1 GitHub | https://github.com/TauricResearch/Trading-R1 | 13:51 | README 全文 | github-tauric-trading-r1-readme.txt |
| FLAG-Trader 2502.11433 | https://arxiv.org/pdf/2502.11433 | 13:46 | 全文（读了设置、表 1/2、局限） | arxiv-2502.11433-flag-trader.txt |
| Fin-R1 2503.16252 | https://arxiv.org/pdf/2503.16252 | 13:46 | 摘要+结果表 | arxiv-2503.16252-fin-r1.txt |
| TradingAgents 2412.20138 | https://arxiv.org/pdf/2412.20138 | 13:46 | 全文（读了设置、表 1、脚注） | arxiv-2412.20138-tradingagents.txt |
| StockBench 2510.02209 | https://arxiv.org/pdf/2510.02209 | 13:47 | 全文（v2，2026-03） | arxiv-2510.02209-stockbench.txt |
| InvestorBench 2412.18174 | https://arxiv.org/pdf/2412.18174 | 13:47 | 摘要+设置+表头 | arxiv-2412.18174-investorbench.txt |
| FinRL 竞赛 2023–24 集成 2501.10709 | https://arxiv.org/pdf/2501.10709 | 13:47 | 全文（读了结果表） | arxiv-2501.10709-finrl-contest-2023-24-ensemble.txt |
| FinRL 竞赛 2023–25 总览 2504.02281 | https://arxiv.org/pdf/2504.02281 | 13:50 | 全文（读了榜单与任务描述） | arxiv-2504.02281-finrl-contests-overview.txt |
| FinRL-DeepSeek 2502.07393 | https://arxiv.org/pdf/2502.07393 | 13:47 | 全文 | arxiv-2502.07393-finrl-deepseek.txt |
| DAPO 股票交易 2505.06408 | https://arxiv.org/pdf/2505.06408 | 13:47 | 摘要+结果表 | arxiv-2505.06408-dapo-stock-trading.txt |
| News-Aware Direct RL 2510.19173 | https://arxiv.org/pdf/2510.19173 | 13:47 | 摘要+结果表 | arxiv-2510.19173-news-aware-direct-rl.txt |
| Alpha-R1 2512.23515 | https://arxiv.org/pdf/2512.23515 | 13:47 | 全文（读了设置、表 1/2、附录 F/G/H） | arxiv-2512.23515-alpha-r1.txt |
| QINN-FinRL-Evaluation（独立 PPO 诊断） | https://raw.githubusercontent.com/Aarav-Nagar/QINN-FinRL-Evaluation/main/README.md | 13:47 | README 全文 | github-qinn-finrl-evaluation-readme.txt |
| Agentic Trading 综述 2605.19337 | https://arxiv.org/pdf/2605.19337 | 13:47 | 摘要+引言统计 | arxiv-2605.19337-agentic-trading-survey.txt |
| Memorization Problem 2504.14765 | https://arxiv.org/pdf/2504.14765 | 13:49 | 摘要 | arxiv-2504.14765-memorization-problem.txt |
| Profit Mirage 2510.07920 | https://arxiv.org/pdf/2510.07920 | 13:49 | 摘要+第 2 节结果 | arxiv-2510.07920-profit-mirage.txt |
| Detecting Lookahead Bias 2512.23847 | https://arxiv.org/pdf/2512.23847 | 13:49 | 摘要 | arxiv-2512.23847-detecting-lookahead-bias.txt |
| AI-Trader 2512.10971 | https://arxiv.org/pdf/2512.10971 | 13:49 | 全文（读了设置与表 1） | arxiv-2512.10971-ai-trader.txt |
| Agent Market Arena 2510.11695 | https://arxiv.org/pdf/2510.11695 | 13:49 | 摘要+引言+结论 | arxiv-2510.11695-agent-market-arena.txt |
| ChatGPT 微盘股第 24 周 | https://nathanbsmith729.substack.com/p/chatgpts-micro-cap-portfolio-week-e5e | 13:49 | 全文 | substack-chatgpt-micro-cap-week24.txt |
| dev.to Claude 交易帖 | https://dev.to/shenao_yu_e15c14815264a44/claude-as-a-trading-agent-what-does-the-llm-actually-add-over-a-plain-script-21l2 | 13:50 | 全文 | devto-claude-trading-agent-what-does-llm-add.txt |
| Decrypt/Benzinga 微盘股早期 +24% | https://decrypt.co/332826/high-school-students-chatgpt-trading-bot | 检索 | **只有检索摘要** | 无 |
| 检索：FinRL 竞赛、DRL 过拟合、Reddit/QuantConnect | WebSearch | 13:4x | **只有检索摘要**（Reddit/QuantConnect 无可用原帖） | 无 |

内部引用：`docs/research-program.zh.md`（"模型只能放大已有的信号"）、`reports/research/harvest/directions.jsonl`（`dir:finrl_deep_rl`、`dir:llm_as_trader_portfolio_manager`）、`scripts/modal_budget.py`（Modal 费率）。
