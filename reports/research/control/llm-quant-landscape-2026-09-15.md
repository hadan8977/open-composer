# LLM + 量化：2023–2026 现状核查（写给非专业读者）

- 撰写日期 / 访问日期：全文所有链接均为 **2026-09-15** 访问。
- 预算：本轮只允许 12 次联网调用，已全部用完。因此**只有 2 篇原文被真正打开**，其余靠搜索摘要，标注见下。
- 核实等级标记：
  - `[已打开]` = 我打开了这个 URL 并读到了内容。
  - `[仅摘要]` = 只看到搜索引擎返回的标题/摘要，**没有**打开原文；数字可能被摘要生成环节扭曲。
  - `[未核实]` = 打不开（403/404）或预算用尽，数字一律不要当证据用。
- 全文用 `【文献】`（有来源）和 `【判断】`（我的推断，没有来源）分开。

---

## 1. LLM 驱动的"研究自动化闭环"：RD-Agent / R&D-Agent-Quant

- **它是什么**【文献】：微软的 R&D-Agent(Q) 把量化研究拆成"研究阶段（提假设→变成任务）+ 开发阶段（Co-STEER 生成代码→真实市场回测）+ 反馈阶段（评估结果→决定下一轮方向，用多臂老虎机调度）"，是一个自己会迭代的因子/模型联合优化循环。`[已打开]` https://arxiv.org/abs/2505.15155
- **报告的数字**【文献】：摘要称"年化收益最高可达经典因子库的 **2 倍**，同时**少用 70% 的因子**"，并称优于当时最好的深度时序模型。作者 Yuante Li 等，v1 2025-05-21 / v2 2025-09-25，NeurIPS 2025。`[已打开]` https://arxiv.org/abs/2505.15155 ；会议页 `[仅摘要]` https://neurips.cc/virtual/2025/poster/121804
- **可复现性警告**【文献+判断】：**摘要里没有写市场、没有写样本区间、没有写信息比率**（我打开原文摘要确认了这一点）。"2 倍年化"是相对"经典因子库"这个基线，不是相对大盘；换基线数字就没了。`[已打开]` 同上
- **开源**【文献】：代码在 https://github.com/microsoft/RD-Agent （摘要里明确给出）。Qlib 仓库自述也说它已接入 RD-Agent 来自动化 R&D。`[仅摘要]` https://github.com/microsoft/qlib
- **4 GB CPU 能不能跑**【判断】：循环本身（调 LLM、生成代码、跑 LightGBM/线性模型）不吃内存，真正的门槛是 (a) 它默认用 Docker 跑实验，(b) 基线里有 GRU/LSTM/Transformer 类深度时序模型。**结论：轻量版（只跑树模型 + 日线）大概可行；官方完整流程在 4 GB 上不要指望。** `[未核实]`（官方没有给内存需求）

## 2. LLM 挖因子（alpha mining）

- **AlphaAgent (2025)**【文献】：LLM 挖因子 + "正则化探索"来对抗因子衰减。搜索摘要给出：CSI 500 与 S&P 500，2021-01 至 2024-12，**扣交易成本后年化超额 11.0%（IR 1.5，CSI500）和 8.74%（IR 1.05，S&P500）**；有效因子命中率高 81%，token 少用 30%。`[仅摘要]` https://arxiv.org/abs/2502.16789 ；代码 `[仅摘要]` https://github.com/RndmVariableQ/AlphaAgent
- **是不是只有 A 股？**【文献】：**不是**。AlphaAgent 同时报了 S&P 500，且美股那一组明显弱于 A 股（8.74% vs 11.0%，IR 1.05 vs 1.5）——这本身就是"A 股更容易出因子"的证据。`[仅摘要]` 同上
- **Chain-of-Alpha (2025)**【文献】：arXiv 2508.06312，主题是用 LLM 做链式 alpha 挖掘。**我尝试打开 PDF 返回 404，IC/RankIC 数字一律 `[未核实]`。** https://arxiv.org/pdf/2508.06312
- **Alpha-GPT / QuantAgent**【文献】：只在其他论文的相关工作里被引用到（Alpha-GPT = 人机交互式挖因子；QuantAgent = 自我改进的 LLM 交易 agent）。**具体 IC 数字 `[未核实]`。** `[仅摘要]` https://arxiv.org/html/2502.16789v2
- **RL 前身 AlphaGen**【文献】：被描述为"用强化学习优化一组 alpha 因子"，是 LLM 挖因子之前的主流做法，常被当基线。**数字 `[未核实]`。** `[仅摘要]` https://arxiv.org/html/2502.16789v2
- **这个领域已经有综述**【文献】：FITEE 有一篇《A survey on large language model-based alpha mining》，说明 2025–2026 这条线已经卷成一个子领域。`[仅摘要]` https://link.springer.com/article/10.1631/FITEE.2500386
- **可复现性警告**【判断】：这类论文的通病是"因子池 + 回测框架 + 股票池"三件都由作者自己定，而 IC 对股票池和中性化处理极其敏感；再加上 LLM 知识截止日晚于回测区间（2021–2024 的行情 LLM 其实"见过"），**泄漏风险结构性存在**。
- **4 GB CPU 能不能跑**【判断】：挖因子这一步主要是 LLM 调用 + pandas 算因子，日线、几百只股票在 4 GB 里可行；把因子池放大到上千个同时评估会 OOM。

## 3. LLM 做"文本 → 信号"（这一类证据最扎实，但也最容易被高估）

- **Lopez-Lira & Tang 2023（ChatGPT 读新闻标题）**【文献】：让 LLM 把公司新闻标题判为利好/利空/中性，得分与次日收益显著相关。摘要给出**年化 Sharpe：GPT-4 = 2.97、GPT-3.5 = 1.66、DistilBART-MNLI = 1.26，而 GPT-1/BERT 等小模型为负**——作者的论点是"预测能力是随模型变强才涌现的"。`[仅摘要]` https://arxiv.org/abs/2304.07619 ；SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4412788
- **可复现性警告**【判断】：Sharpe 2.97 是**日频换手、按标题下注**的结果，样本窗口短（论文原始版本只覆盖约一年多），且这类效应在小盘/低流动性股票上最强——扣掉真实点差和冲击后通常大幅缩水。**样本窗口与成本处理我没打开原文核实 `[未核实]`。**
- **Chen, Kelly & Xiu《Expected Returns and Large Language Models》**【文献】：用 GPT / LLaMA 系列从新闻里抽 embedding 来预测横截面收益，结论是 LLM 新闻信号相对传统技术类预测变量有**增量信息**。**我尝试打开 SSRN 返回 403，Sharpe、OOS R²、样本区间全部 `[未核实]`。** https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416687 ；另有 Wharton 讲稿 PDF 未打开 https://jacobslevycenter.wharton.upenn.edu/wp-content/uploads/2024/09/Kelly-WhartonJL.pdf
- **重要警告：Kim, Muhn & Nikolaev 2024（GPT 做财报分析）已撤稿**【文献】：我打开 arXiv 页面，上面写明**论文已被撤回（withdrawn）**，原因是共同作者发现"数据与分析存在不一致"，暂时撤下复核。原摘要声称 GPT-4 在预测盈余变动方向上优于人类分析师、策略 Sharpe 与 alpha 更高。**结论：这篇不能再当证据引用。** `[已打开]` https://arxiv.org/abs/2407.17866
- **财报电话会议类**【文献】：有 SSRN 工作论文直接问"LLM 能否从 earnings call 里提取 alpha"，说明这是活跃方向。**数字 `[未核实]`。** `[仅摘要]` https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6351439
- **衰减**【判断】：文本信号的半衰期短（多在 1–5 天），且一旦公开化就被抢；这也是 AlphaAgent 专门做"抗衰减正则"的原因。**"衰减多少"我没有拿到可引用的数字 `[未核实]`。**
- **开源 / 4 GB**【判断】：这一类不需要训练大模型，只需要把新闻喂给 API 拿分数再做横截面回归/排序——**是 4 GB 盒子上最现实的一类**。

## 4. LLM 多 agent 交易系统（热度最高，证据最弱）

- **TradingAgents (Xiao et al.)**【文献】：模仿交易公司分工（基本面/情绪/技术分析师 + 多头空头研究员辩论 + 交易员 + 风控），报告在累计收益、Sharpe、最大回撤上优于基线。`[仅摘要]` https://arxiv.org/abs/2412.20138
- **证据质量（关键）**【文献】：回测只有 **2024-01-01 至 2024-03-29（约 3 个月）**，标的只有 AAPL/NVDA/MSFT/META/GOOGL **5 只大型科技股**。`[仅摘要]` https://arxiv.org/html/2412.20138
- **作者方自己的免责**【文献】：二手资料称官方把它定位为"研究脚手架、不要用真钱"，且**结果会随模型、temperature、日期区间、数据质量和采样而变，不保证复现任何已发表数字**。`[仅摘要]` https://twistersai.blogspot.com/2026/06/tradingagents-open-source-ai-hedge-fund.html
- **FinMem**【文献】：分层记忆 + 角色设定的 LLM 交易 agent（profile / memory / decision 三模块）。**数字 `[未核实]`。** `[仅摘要]` https://arxiv.org/abs/2311.13743
- **FinAgent**【文献】：多模态金融交易基础 agent，摘要称"在 6 个指标上优于 12 个 SOTA 基线，收益平均提升 36%+"。**arXiv 编号与样本区间 `[未核实]`。** `[仅摘要]`（来自 arXiv 检索页摘要）
- **FinRobot**【文献】：AI4Finance 的开源金融 agent 平台（LLM + RL + 量化分析）。`[仅摘要]` https://arxiv.org/abs/2405.14767 ；代码 https://github.com/AI4Finance-Foundation/FinRobot
- **共性缺陷**【文献】：一篇综述/评测线的资料指出：多依赖闭源模型（隐私）、推理延迟使其不适合高频、与真实交易系统的对接几乎没人讨论、token 成本高。`[仅摘要]` https://arxiv.org/pdf/2408.06361
- **已经出现"打假型"基准**【文献】：《When Agents Trade: Live Multi-Market Trading Benchmark for LLM Agents》和《Backtrader-Bench》都是用统一基准重测 LLM agent 的工作——说明学界自己也不信单篇论文的回测。`[未核实]` https://arxiv.org/pdf/2510.11695 ； https://arxiv.org/html/2608.11232
- **幸存者/泄漏**【判断】：3 个月、5 只 2024 年暴涨的科技股，同时 LLM 的训练数据覆盖了这段行情——**这既是选样偏差也是前视泄漏**，几乎不可能构成可交易证据。
- **4 GB CPU**【判断】：能跑（计算在云端 LLM 里），但**成本在 token 上**，而且它输出的是"叙事 + 买卖决定"，不是可回测的因子，对我们价值低。

## 5. 从业界共识 2024–2026（本轮最弱的一块，必须诚实标注）

- **我没能核实任何一家（Man Group/AHL、Two Sigma、AQR、JPMorgan、Bloomberg）的一手表态**。预算用完前的那次检索只返回招聘/面试指南类页面，没有可引用的生产用途声明。以下全部 `[未核实]`。
- **[未核实]**【文献】：二手行业文章称基金实际用法是"隔夜批量扫读并总结几十份财报电话会议记录，标出语气/指引变化，让人去做高确信度判断"，即**研究助手 + 文本特征**。 https://resonanzcapital.com/insights/how-hedge-funds-are-really-using-generative-ai-and-why-it-matters-for-manager-selection
- **[未核实]**【文献】：另一篇称通用消费级 AI 不够用，基金需要接入券商研报、专家访谈、监管申报等付费语料。 https://www.alpha-sense.com/blog/trends/generative-ai-in-hedge-funds/
- **[未核实]**【文献】：有一篇"从对冲基金视角审视 LLM 股价预测"的综述，明确把学术方法按现实条件压力测试：**数据泄漏、流动性约束、评价指标选择、股价可预测性的根本上限**，并指出文献低估了情绪分析的脆弱性。 https://awesomepapers.io/ai-agents/papers/2605.05211
- **[未核实]**【文献】：JPMorgan 的生产量化工作主要在自研 Python 定价/风险平台 Athena 里。 https://www.quantt.co.uk/resources/jpmorgan-quant-research-guide
- **我的读法**【判断】：可核实的一手材料缺失本身就是信息——**"LLM 直接预测价格"在生产里没有公开背书，而"文本→特征""研究/代码助手"有大量间接背书**。如果要把这一块做实，需要单独一轮预算去抓 Man Group / Two Sigma 官方研究博客与 Bloomberg 的 BloombergGPT 论文。

## 6. "先建规则策略再上 ML" vs "ML 优先"——你的直觉是对的

- **Gu, Kelly & Xiu 2020《Empirical Asset Pricing via Machine Learning》**【文献】：该文直接把资产定价当成**预测问题**来做（不是先有规则策略再补 ML）。摘要给出：用神经网络自下而上预测来做 S&P 500 择时，**样本外年化 Sharpe 从买入持有的 0.51 提到 0.77**；直接按神经网络预测值排序做多空十分位，**市值加权样本外年化 Sharpe 1.35**；最好的方法是树和神经网络，收益来源是"非线性变量交互"。`[仅摘要]` https://www.nber.org/papers/w25398 ；PDF https://dachxiu.chicagobooth.edu/download/ML.pdf **（样本区间与股票数 `[未核实]`）**
- **有第三方复现**【文献】：Tidy Finance 有一篇公开的 Gu-Kelly-Xiu 复现文章——对小盒子很有价值，说明这套 pipeline 不需要机构算力。`[仅摘要]` https://www.tidy-finance.org/blog/gu-kelly-xiu-replication/
- **Kelly & Xiu 2023《Financial Machine Learning》综述**【文献】：金融 ML 的标准参考综述，NBER w31502 / SSRN 4501707 / now publishers FIN-064。`[仅摘要]` https://www.nber.org/papers/w31502 ； https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4501707
- **Learning-to-Rank 选股**【文献】：把"预测收益"改成"给股票排序"是独立成熟的一条线：Neurocomputing 的 LTR+新闻情绪组合选股、AAAI 的时空超图 LTR 选股、MDPI 的 LTR+遗传算法做美股组合构建。`[仅摘要]` https://www.sciencedirect.com/science/article/abs/pii/S0925231217311098 ； https://ojs.aaai.org/index.php/AAAI/article/view/16127 ； https://www.mdpi.com/2227-7072/14/4/95
- **Meta-labeling（López de Prado, 2017）**【文献】：**这是唯一"规则策略在前、ML 在后"被正当化的位置**——它把"方向"和"下多大注"拆开，二级模型只负责评估一级信号的置信度、压掉假阳性、动态调仓位。`[仅摘要]` https://en.wikipedia.org/wiki/Meta-Labeling
- **但它不是万能药**【文献】：Hudson & Thames 有专文问"meta-labeling 到底有没有提升信号效力"，QuantConnect 论坛有《Why Meta-Labeling Is Not a Silver Bullet》。`[仅摘要]` https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/ ； https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/
- **端到端组合学习 / 统一评测 / 上限**【文献】：QuantBench（统一评测 AI 量化方法）和《Limits To (Machine) Learning》代表 2025–2026 的两个新重点：可比性与可预测性上限。`[未核实]` https://arxiv.org/pdf/2504.18600 ； https://arxiv.org/pdf/2512.12735
- **现代标准流水线顺序**【判断】：文献的实际做法是 **目标(label) → 特征 → 模型 → 组合构建 → 执行**，规则指标（RSI/MACD 之类）只是"特征"或"基线"，不是研究的起点。"先写一个规则策略，再拿 ML 去优化它的参数"在学术主流里**不是标准做法**——你的质疑成立。唯一例外是 meta-labeling，它明确只管 sizing/过滤，不负责发现 edge。**这段是我的归纳，没有一句可直接引用的原文，标 `【判断】`。**

## 7. 值得直接引入而不是自己造的开源框架

- **Qlib（微软）**【文献】：AI 量化平台，支持监督学习/市场动态建模/RL，且已接入 RD-Agent 自动化研发。许可证 **MIT**（二手）。`[仅摘要]` https://github.com/microsoft/qlib
- **RD-Agent（微软）**【文献】：上面第 1 节那套自动化研发循环，代码公开。`[已打开确认链接出现在论文摘要]` https://github.com/microsoft/RD-Agent
- **FinRL / FinRL-X（AI4Finance）**【文献】：金融强化学习基础设施。**许可证 `[未核实]`。** `[仅摘要]` https://github.com/AI4Finance-Foundation/FinRL-Trading
- **TradingAgents（TauricResearch）**【文献】：许可证 **Apache 2.0**（二手）；星数从 2026-03 的约 9.3k 涨到 2026-08-24 的 99,456，是星数最多的 AI 交易仓库；同一来源提到"已经安静了一个月"，维护活跃度要自己复核。`[仅摘要]` https://github.com/tauricresearch/tradingagents ； https://ultralab.tw/en/blog/ai-finance-github-projects-2026
- **AlphaAgent**【文献】：仓库 https://github.com/RndmVariableQ/AlphaAgent 。**许可证 `[未核实]`。** `[仅摘要]`
- **4 GB 可行性总评**【判断】：Qlib + LightGBM + 日线美股全域 = 勉强可行（要分块读、控内存）；Qlib + 分钟线 + 深度时序 = 不可行；FinRL（RL 训练）在 4 GB 上不值得；TradingAgents/FinRobot 内存不是瓶颈但产出不可回测。**没有任何官方文档给出内存要求，全部 `[未核实]`。**
- **命名陷阱**【文献】：GitHub 上有同名但完全无关的 "AlphaAgent"（一个 PPO 交易 agent，自称 24.3% 收益 / Sharpe 1.87），不要拿错仓库。`[仅摘要]` https://github.com/mfzhang/20260416-AlphaAgent

---

## 对我们的含义（10 行）

1. 【文献】学术主流从不是"先规则策略再 ML"：Gu-Kelly-Xiu 直接从预测目标出发做，样本外多空十分位年化 Sharpe 1.35、择时 Sharpe 0.51→0.77（`[仅摘要]` https://www.nber.org/papers/w25398 ，2026-09-15）。
2. 【文献】唯一让"规则在前"正当化的是 meta-labeling：一级模型定方向、二级 ML 定仓位与过滤（`[仅摘要]` https://en.wikipedia.org/wiki/Meta-Labeling ，2026-09-15），且它不被认为是万能药（https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/ ）。
3. 【文献】LLM 最可信的用法是"文本→信号"：GPT-4 读新闻标题的年化 Sharpe 2.97、小模型为负（`[仅摘要]` https://arxiv.org/abs/2304.07619 ，2026-09-15）；但同一家族里最出名的财报分析论文**已撤稿**（`[已打开]` https://arxiv.org/abs/2407.17866 ，2026-09-15）。
4. 【文献】研究自动化闭环确实有成果且开源：RD-Agent(Q) 声称"年化 2 倍、因子少 70%"，代码在 https://github.com/microsoft/RD-Agent （`[已打开]` https://arxiv.org/abs/2505.15155 ，2026-09-15），但摘要不写市场和样本区间。
5. 【文献】多 agent 交易系统的证据最弱：TradingAgents 只回测 2024-01-01→2024-03-29 的 5 只科技股（`[仅摘要]` https://arxiv.org/html/2412.20138 ，2026-09-15）。
6. 【判断】**第一件事**：把 Reversal Trend 这类规则降级为"基线 + 一级信号"，主线改成 target→features→model→portfolio→execution。目标先定成横截面 5/20 日相对收益排序（日线、2016 年起），用 learning-to-rank 而不是回归。
7. 【判断】**第二件事**：把 2024→ 的新闻 PIT packet 接成横截面文本因子（Anthropic LLM 打分 → 去行业/市值中性化 → 与价量因子一起进模型），只做"文本→特征"，不让 LLM 直接给买卖指令。这是 4 GB 盒子上唯一既有文献支持又算得动的路。
8. 【判断】**第三件事**：给现有规则策略加一层 meta-labeling 二级模型（只管"这一笔要不要做、做多大"），这样历史上"先有策略"的沉没成本变成资产而不是包袱，且是可独立验证的小实验。
9. 【判断】**要避免**：整体搬 TradingAgents/FinRobot 做实盘；把论文里的年化/Sharpe 当我们的预期（全部是作者自选股票池+自选基线）；在 4 GB 上训练深度时序模型或 RL；再引用 Kim-Muhn-Nikolaev（已撤稿）。
10. 【判断】**要补的核查**：从业界共识那一块我没拿到任何一手来源（第 5 节全 `[未核实]`），以及 Chain-of-Alpha（404）和 Chen-Kelly-Xiu（SSRN 403）的具体数字——建议下一轮专门花预算抓 Man Group/Two Sigma 官方研究页、BloombergGPT 论文、以及这两篇的可访问镜像。
