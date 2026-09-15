# 研究循环（research loop）设计调研：LLM 驱动 + 人在环

- 日期：2026-09-15
- 目的：为「把本项目的策略研究核心重做成一个 LLM 驱动、人在环的研究循环（读知识库 → 提出假设卡 → 诚实地跑 → 把教训写回去）」提供外部参考。用户明确要求：不要只看 RD-Agent，也要看别的新的、公开发表的知名设计，然后我们自己写自己的。
- 范围：只看**循环的机械结构**（步骤、记忆、选择机制、人在哪、跑起来要什么），**不看它们宣称的交易收益**。论文里的收益数字在本文一律不作为论据。
- 预算与诚实声明（重要）：本次调研共用 15 次网络调用（4 次搜索 + 7 次抓取 + 4 次搜索，已用满）。
  - `[已打开]` = 我确实抓取了那个页面并读到了内容。**但 arXiv 的 `/abs` 页面只有摘要**，所以标 `[已打开]` 的 arXiv 条目意思是「摘要层已读」，正文/附录没读。
  - `[仅摘要]` = 我只看到搜索引擎返回的摘要片段或标题，没有打开原页面。
  - `[未核实]` = 我既没打开也没看到可靠片段，只知道它存在（通常只有标题+链接）。这类条目**不能作为决策依据**，只能当线索。
  - 所有 URL 的访问日期均为 2026-09-15。
  - 许可证（license）除特别注明外多为 `[未核实]`——我只核实了 RD-Agent 一个。要真的引用某个仓库的代码前必须自己再查一遍 LICENSE 文件。

---

## 0. 怎么读下面的卡片

每个系统都用同样 8 个字段，方便横向比：

1. **循环步骤**：一轮从头到尾做什么
2. **知识/记忆**：经验存在哪、下一轮怎么用
3. **选择/分配**：多个候选里怎么挑（bandit / 树搜索 / 进化 / 锦标赛辩论 / 没有）
4. **人在哪**：无人 / 审核闸门 / 副驾驶
5. **跑起来要什么**：GPU、Docker、模型账号
6. **开源 + 许可**
7. **量化专用 or 通用**
8. **证据质量**

---

## A. 量化专用的研究循环

### A1. Microsoft RD-Agent / R&D-Agent-Quant（RD-Agent(Q)）

- **循环步骤**【文献】`[已打开]`：三段式——Research（动态生成与目标对齐的 prompt、基于领域先验提出假设、把假设映射成具体 task）→ Development（由代码生成 agent **Co-STEER** 写出任务代码，并在真实市场回测中执行）→ Feedback（评估实验结果并指导下一轮）。原文措辞："a Research stage that dynamically sets goal-aligned prompts, formulates hypotheses based on domain priors, and maps them to concrete tasks"。<https://arxiv.org/abs/2505.15155>（2026-09-15）
- **知识/记忆**`[未核实]`：**我没能核实**它的 trace / 知识库机制。摘要层完全没提知识如何持久化（我抓取后的结论是 "lacks specific information about knowledge persistence mechanisms or trace storage systems"）。项目里若要引用「append-only trace / 知识库」这个设计，必须去读正文或源码再确认。
- **选择/分配**：多臂老虎机调度器做「方向选择」【文献】`[已打开]`（摘要里明确有 "a multi-armed bandit scheduler for adaptive direction selection"）。更细的说法——把它写成 **contextual Thompson sampling**，每个 arm 一个贝叶斯线性模型，每步从后验采样、选采样收益最高的动作、执行后用观测到的「改进量」更新后验——`[仅摘要]`，来自搜索片段，未打开原文核对。
- **人在哪**：**无人**【文献】`[已打开]`。摘要把它描述成 "automate the full-stack research and development"；我抓取的 GitHub 首页也没有任何 human-in-the-loop / 审批闸门的描述。
- **跑起来要什么**【文献】`[已打开]`：**必须装 Docker**（"Users must ensure Docker is installed before attempting most scenarios"）；需要 LLM API（ChatCompletion + JSON mode + embedding，经 LiteLLM 支持 OpenAI / Azure OpenAI / DeepSeek）；GPU 非强制。<https://github.com/microsoft/RD-Agent>（2026-09-15）
- **开源 + 许可**【文献】`[已打开]`：开源，**MIT**。
- **量化专用 or 通用**：两者都是——同一个 R&D 循环壳子下挂了多个 scenario（量化交易 / 因子演化 / 模型演化 / 财报抽因子 / Kaggle 数据科学 / LLM 微调）`[已打开]`。回测侧建在 Microsoft Qlib 上 `[仅摘要]`。
- **证据质量**：高（NeurIPS 2025 Datasets & Benchmarks track 有收录页 <https://neurips.cc/virtual/2025/poster/121804>，`[仅摘要]`）+ 活跃开源仓库。但**统计诚实性方面摘要层零提及**（见 C 节）。

### A2. QuantAgent（Wang et al., 2024）

- **循环步骤 + 知识/记忆**【文献】`[仅摘要]`：双层循环。内环：agent 从自己的**知识库**里取东西来改进自己的回答；外环：把这些回答放到真实场景里检验，并把新洞见**自动写回知识库**。这正是「跑完把教训写回去」的最小可用形态。<https://arxiv.org/abs/2402.03755v1>（2026-09-15）
- **选择/分配**：无显式 bandit / 树搜索 / 锦标赛；靠内外双环迭代 `[仅摘要]`。
- **人在哪**：无人（自我改进）`[仅摘要]`。
- **跑起来要什么/ 开源许可**：`[未核实]`。
- **量化专用**：是（交易信号 / 金融预测）。
- **证据质量**：中。2024-02 的 arXiv preprint，作者与 Alpha-GPT 系列同组（Saizhuo Wang / Hang Yuan / Jian Guo）`[仅摘要]`。我只读到摘要级描述。

### A3. Alpha-GPT 与 Alpha-GPT 2.0（人在环的 alpha 挖掘）

- **循环步骤**【文献】`[已打开]`：围绕「人与 AI 的反复交互」组织整条量化研究流水线；摘要原话是 "iterative Human-AI interaction based on large language models"，并把人类研究员的洞见 "assimilat[e] ... into the systematic alpha research process"。<https://arxiv.org/abs/2402.09746>（2026-09-15）
- **三层架构**`[仅摘要]`：三层多 agent，每层管一个环节——Alpha Mining（找候选）→ Alpha Modeling（建预测模型）→ Alpha Analysis（分析与缓解风险）。这条来自搜索片段，我打开 `/abs` 页时**没有**看到三层架构的描述，所以它只算摘要级。
- **知识/记忆**`[未核实]`：怎么把人类反馈沉淀成可复用资产，摘要层没说清。
- **选择/分配**：无公开的显式算法（不是 bandit/树搜索）`[未核实]`。
- **人在哪**：**副驾驶 + 全程介入**——这是整篇文章的卖点，人类研究员和 AI 协作贯穿从挖因子到风险分析`[已打开]`。
- **跑起来要什么 / 开源**：`[未核实]`；我抓取的页面上**没有**任何开源信息（很可能是闭源的商业系统，但我没有证据）。
- **量化专用**：是。
- **证据质量**：中。2024-02 preprint，工业界背景，缺可复现代码。**但对我们最重要**：它是这批系统里唯一把「人在环」当作核心设计目标而不是可选开关的量化系统。

### A4. AlphaAgent（2025，带正则化的探索）

- **循环步骤**【文献】`[已打开]`：LLM agent 挖公式化因子，但把挖掘目标**改写成带正则项的目标函数**，主动惩罚三件事：复杂度、低原创性、与市场假设不对齐。<https://arxiv.org/abs/2502.16789>（2026-09-15）；已发表于 KDD '25 <https://dl.acm.org/doi/10.1145/3711896.3736838>（`[仅摘要]`）
- **三个正则项怎么量**【文献】`[已打开]`：
  1. 原创性：用**抽象语法树（AST）相似度**跟已有因子库比，太像就罚；
  2. 假设一致性：让 LLM 评「市场假设 ↔ 生成因子」的语义一致性；
  3. 复杂度：基于 AST 的结构约束，原话 "preventing over-engineered constructions that are prone to overfitting"（**这是本次调研里唯一在摘要层就把机制和过拟合直接挂钩的量化系统**）。
- **知识/记忆**：有「已有 alpha 库」作为原创性比对基准；是否有跨轮次的经验沉淀 `[未核实]`。
- **选择/分配**：不是 bandit/树搜索，而是**在目标函数里加惩罚项**来约束搜索方向。
- **人在哪**：摘要层未提人类角色 → 按无人理解 `[已打开，但属"未提及"]`。
- **跑起来要什么 / 开源许可**：`[未核实]`。
- **量化专用**：是（CSI 500 与 S&P 500 上做的实验）。
- **证据质量**：**较高**（KDD 2025 正式发表）。设计模式（原创性/一致性/复杂度三罚）可以直接搬。

### A5. Chain-of-Alpha（2025）

- **循环步骤 + 选择/分配**【文献】`[仅摘要]`：双链结构——Factor Generation Chain（生成）+ Factor Optimization Chain（优化），迭代地生成、评估、精炼候选因子，只用市场数据，靠**回测反馈 + 先前的优化知识**驱动。<https://arxiv.org/abs/2508.06312>（2026-09-15）
- **知识/记忆**：靠「prior optimization knowledge」在链间传递`[仅摘要]`；存储形式未核实。
- **人在哪**：**明确无人**——宣传语是 "without human involvement" / "fully automated"`[仅摘要]`。
- **跑起来要什么 / 开源许可**：`[未核实]`。
- **量化专用**：是（A 股 benchmark）。
- **证据质量**：中（preprint，我只有摘要级）。**对我们的意义主要是反面**：用户要的是人在环，Chain-of-Alpha 的"全自动、无人参与"正是要避免的方向；但它的「生成链 / 优化链 分开」这个角色切分值得借。

### A6. AlphaForge（AAAI 2025）

- **循环步骤**【文献】`[仅摘要]`：两阶段——先挖公式化 alpha，再**动态组合**。它针对的痛点是：目前最强做法用强化学习挖出一组**固定权重**的组合因子，结果因子表现不稳定，固定权重跟不上市场变化。<https://ojs.aaai.org/index.php/AAAI/article/view/33365>（2026-09-15）
- **知识/记忆**：因子池 + 动态权重（不是 LLM 记忆）`[仅摘要]`。
- **选择/分配**：生成-预测式网络 + 动态加权组合（非 LLM、非 bandit）`[仅摘要]`。
- **人在哪**：无人。
- **跑起来要什么**：`[未核实]`（应为 GPU 训练）。
- **开源 + 许可**：有官方实现 <https://github.com/dulyhao/alphaforge> `[仅摘要]`；许可 `[未核实]`。
- **量化专用**：是。**注意它不是 LLM 循环**，是纯 ML/搜索方法。
- **证据质量**：高（AAAI 2025 正式发表）。对我们的价值是「候选因子的**组合层**要跟**挖掘层**分开、且权重要能随时间变」这一点。

### A7. FITEE 2025 综述：LLM-based alpha mining

- **内容**【文献】`[仅摘要]`：从 agent 视角对新出现的 LLM alpha 挖掘系统做结构化梳理，把 LLM 的功能角色分成 **miner（挖掘者）/ evaluator（评估者）/ interactive assistant（交互助手）** 等；并指出 LLM 方案的定位是「人工引导」与「全自动」之间的**中间地带**，兼顾速度和语义深度。Zhang, J., Liu, S., Zhang, T. et al., FITEE 2025, 26(10): 1809-1821, DOI 10.1631/FITEE.2500386。<https://journal.hep.com.cn/fitee/EN/10.1631/FITEE.2500386>（2026-09-15）
- **对我们的用处**：这个「miner / evaluator / assistant 三种角色」的分类，可以直接当我们循环里 agent 角色划分的外部依据；而「中间地带」这句话正好支持用户要的人在环定位。
- **证据质量**：中高（正式期刊综述），但我**只读到摘要**，没读分类细节。

### A8. 2026 的后继者（**只到标题级，全部 `[未核实]`**，仅作线索）

搜索结果里出现、但我预算耗尽未能核实的新条目。**不要当证据用**，只作为下一轮要查的清单：

- AlphaPROBE: Alpha Mining via Principled Retrieval and On-graph biased evolution — <https://arxiv.org/pdf/2602.11917>（检索式 + 图上有偏进化，名字直指「知识库检索 + 进化」，与我们的设计最相关）
- QuantaAlpha: An Evolutionary Framework for LLM-Driven Alpha Mining — <https://arxiv.org/pdf/2602.07085>
- AlphaCrafter: A Full-Stack Multi-Agent Framework for Cross-Sectional Quantitative Trading — <https://arxiv.org/pdf/2605.05580>
- ContestTrade: A Multi-Agent Trading System Based on Internal Contest Mechanism — <https://arxiv.org/pdf/2508.00554>（「内部竞赛」= 锦标赛机制的量化版）
- **Profit Mirage: Revisiting Information Leakage in LLM-based Financial Agents** — <https://arxiv.org/pdf/2510.07920>（标题就是「利润幻觉：重审 LLM 金融 agent 的信息泄漏」，**这是本清单里最该优先读的一篇**，直接关系到我们循环的诚实性）
- Trade in Minutes! Rationality-Driven Agentic System — <https://arxiv.org/pdf/2510.04787>
- AlphaResearch: Accelerating New Algorithm Discovery with Language Models — <https://arxiv.org/pdf/2511.08522>

---

## B. 通用「AI 科学家」循环

### B1. Sakana AI Scientist v1

- **状态：`[未核实]`**。本轮预算没有专门核实 v1，只从 v2 的摘要里**间接**知道 v1 依赖「人工编写的代码模板」且领域泛化差（见 B2 原话）。v1 常被引的 arXiv 编号（2408.06292）我**未核实**，引用前请自己查。
- 可确证的唯一一点【文献】`[已打开]`：v2 相对 v1 的改进是"eliminates the reliance on human-authored code templates"，所以 **v1 = 模板驱动的固定循环**。这对我们反而是个有用的提示：模板化循环虽然不够"聪明"，但在小硬件和小预算下更可控。

### B2. Sakana AI Scientist-v2（2025）

- **循环步骤**【文献】`[已打开]`：端到端一条龙——提出科学假设 → 设计并执行实验 → 分析与可视化数据 → 自动写论文。<https://arxiv.org/abs/2504.08066>（2026-09-15）
- **选择/分配**：**渐进式 agentic 树搜索**（"progressive agentic tree-search methodology"），由一个专门的 **experiment manager agent** 管理树的推进`[已打开]`。
- **知识/记忆**：树本身就是记忆（节点 = 实验变体及其结果）；另有 **VLM（视觉语言模型）反馈回路**专门迭代改图`[已打开]`。跨论文/跨轮次的长期知识库 `[未核实]`。
- **人在哪**：**基本无人**——宣传点是产出了"第一篇完全由 AI 生成、且通过同行评审被 workshop 接收"的论文`[已打开]`。
- **跑起来要什么**：摘要层没写 GPU 需求`[已打开，属"未提及"]`；实际做 ML 实验必然要 GPU`【判断】`。
- **开源 + 许可**：代码开源（摘要明言 "open-sourced"）`[已打开]`，仓库 <https://github.com/SakanaAI/AI-Scientist-v2>；**许可证名称 `[未核实]`**。
- **通用**（ML 领域，非量化）。
- **证据质量**：高关注度 preprint + 可运行仓库。**风险提示**`【判断】`：它的成功指标是「论文被接收」，即一种**自评/同行评审代理指标**，不是外部可验证的钱或 P&L；把这种循环直接套到交易上，会把「说服评审」误当成「赚钱」。

### B3. Google / DeepMind AI co-scientist（2025）

- **循环步骤**【文献】`[已打开]`：科学家用自然语言给一个 research goal，然后六个专职 agent 在 **Supervisor** 调度下进入自我改进循环：**Generation（生成）→ Reflection（反思/评审）→ Ranking（排名）→ Evolution（演化改良）→ Proximity（相近性/去重聚类）→ Meta-review（元评审）**。原话："automated feedback to iteratively generate, evaluate, and refine hypotheses, resulting in a self-improving cycle"。<https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/>（2026-09-15）
- **选择/分配**：**锦标赛 + Elo**。用「self-play 式科学辩论」做两两比较，赢的加 Elo 分、输的减分；并且博客称"higher Elo ratings positively correlate with a higher probability of correct answers"（Elo 越高，答对概率越高）`[已打开]`。补充细节（弱者胜强者时分数变动更大、高分假设优先被继续精炼）`[仅摘要]`。
- **知识/记忆**：博客**没有**明确讲记忆机制`[已打开，属"未提及"]`；只提到"recursive self-critique, including tool use for feedback"。Meta-review agent 的作用类似「把本轮共性教训汇总给下一轮」`【判断】`。
- **人在哪**：**专家在环（副驾驶）**——科学家定 research goal、可以直接投喂自己的种子想法（seed ideas）、也可以用自然语言对产出给反馈`[已打开]`。
- **跑起来要什么**：Gemini 2.0 作底座 + 网页搜索 + 领域专用模型 + 专家反馈`[已打开]`。
- **开源 + 许可**：**不开源**。只有 Trusted Tester 申请制`[已打开]`。（另有通过 Gemini Enterprise 提供的迹象 `[仅摘要/标题级]`：<https://docs.cloud.google.com/gemini/enterprise/docs/co-scientist-and-alphaevolve>）
- **通用**（生物医药为主）。
- **证据质量**：高（Google 官方博客；另有 2026-05 的 Nature 论文说法 `[未核实]`）。**但不可复制**——我们只能借设计，不能用它的实现。

### B4. DeepMind AlphaEvolve 与 FunSearch

- **循环步骤**【文献】`[仅摘要]`：**FunSearch** = 把一个 LLM 与一个**程序化评估器（programmatic evaluator）**配对，进化式地搜出新程序；**AlphaEvolve** 把它从「进化单个 10–20 行的 Python 函数」推广到「进化整个几百行的代码文件、任意语言」，底座是 Gemini。<https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/>（2026-09-15）
- **知识/记忆**：进化种群（program database）即记忆，好解被保留、复用、再变异`[仅摘要]`。
- **选择/分配**：**进化算法**，适应度由自动评估器给出（不是 LLM 自评）`[仅摘要]`。
- **人在哪**：**人定义「要什么」**——人给出评估标准和初始解，系统自己找「怎么做到」。原话大意："Humans define what they want to achieve by specifying evaluation criteria and providing initial solutions"`[仅摘要]`。**这是全调研里对我们最关键的一句设计原则**：人的职责是定义可自动验证的评分函数与护栏，而不是审每一行代码。
- **跑起来要什么**：Gemini 访问 + 可大量并行跑评估器的算力`[仅摘要]`。
- **开源 + 许可**：AlphaEvolve **未见开源**`[未核实]`；社区有开源复现 CodeEvolve <https://arxiv.org/html/2510.14150v1>`[未核实，标题级]`。
- **通用**（数学/算法/基础设施优化）。
- **证据质量**：高（FunSearch 发表在 Nature；AlphaEvolve 有 DeepMind 白皮书）——但**FunSearch 的 Nature 出处我本轮没核实** `[未核实]`。
- **对量化的硬约束**`【判断】`：这套方法的前提是「评估器便宜、快、且不会被钻空子」。金融回测**不满足**这个前提（样本有限、可被过拟合、评估一次就消耗一点样本的独立性）。所以直接照搬进化搜索到回测指标上，等于自动化地制造过拟合。

### B5. Weco AIDE（AI-Driven Exploration in the Space of Code）

- **循环步骤 + 选择/分配**【文献】`[已打开]`：把 ML 工程当成**代码优化问题**，把试错形式化为「在候选解空间里做树搜索」（"formulates trial-and-error as a tree search in the space of potential solutions"），不断复用和精炼有希望的解，即「把算力换成性能」。<https://arxiv.org/abs/2502.13138>（2026-09-15）
- **知识/记忆**：解树（每个节点是一份可跑的代码草稿 + 它的分数）`[已打开]`；draft/debug/improve 三个算子的细节我**没读到**`[未核实]`。
- **人在哪**：无人（人只给任务和指标）`[已打开]`。
- **跑起来要什么**：LLM API + 能跑候选代码的沙箱/算力`[未核实具体要求]`。
- **开源 + 许可**：开源 <https://github.com/WecoAI/aideml>`[仅摘要]`；**许可 `[未核实]`**。
- **通用**（ML 工程 / Kaggle）。
- **证据质量**：高——在 Kaggle、OpenAI **MLE-bench**、METR **RE-bench** 上取得 SOTA`[已打开]`；MLE-bench（75 个真实 Kaggle 比赛）里 AIDE 的树搜索拿奖牌数是最好的线性 agent（OpenHands）的约 4 倍`[仅摘要]`。
- **对我们的意义**`【判断】`：**树搜索 vs 线性重试的差距是有外部 benchmark 支撑的**，这是本调研里少见的「机制层面有硬证据」的一条。

### B6. Google MLE-STAR

- **循环步骤 + 选择/分配**【文献】`[仅摘要]`：Machine Learning Engineering via **S**earch **a**nd **T**argeted **R**efinement——先（网页/模型）搜索找到合适方法，再对方案里**特定模块**做定向精炼（而不是整份代码反复重写）。<https://arxiv.org/pdf/2506.15692>（2026-09-15）
- **知识/记忆**：外部检索到的方案 + 被逐块替换的候选`[仅摘要]`。
- **人在哪**：无人`[仅摘要]`。
- **跑起来要什么**：LLM（论文里用 Gemini-2.0-Flash）+ 搜索`[仅摘要]`。
- **开源 + 许可**：`[未核实]`。
- **通用**（Kaggle/MLE-bench）。
- **证据质量**：中高——在 MLE-bench 上把 AIDE 的「拿到任意奖牌」比例从 25.8% 提到 43.9%`[仅摘要]`。
- **对我们的意义**`【判断】`：「**定向改一块**，而不是让模型重写整个策略文件」这个粒度控制，在我们这种代码库里比 AIDE 式整体重写更安全、更好审。

### B7. Agent Laboratory（2025）

- **循环步骤**【文献】`[仅摘要]`：接受**人给的研究想法**，走三阶段——文献综述 → 实验 → 写报告，产出一个代码仓库 + 一份研究报告。<https://arxiv.org/abs/2501.04227>（2026-09-15）
- **人在哪（重点）**：**支持两种模式：autonomous 与 co-pilot**。co-pilot 模式下，人类研究员在**预定检查点**给反馈来调整 agent 的决策，从而在保留部分自主性的同时精修产出`[仅摘要]`。论文的结论之一是：**人在每个阶段给反馈会显著提升整体研究质量**`[仅摘要]`。
- **知识/记忆**：文献综述阶段的产物 + 阶段间传递；长期知识库`[未核实]`。后继工作 AgentRxiv <https://arxiv.org/pdf/2503.18102> 讲跨 agent 共享论文式知识`[未核实，标题级]`。
- **选择/分配**：无显式 bandit/树搜索/锦标赛`[仅摘要]`。
- **跑起来要什么**：LLM API（论文里 o1-preview 效果最好）；另称比此前的自主研究方法**便宜 84%**`[仅摘要]`。
- **开源 + 许可**：开源 <https://github.com/SamuelSchmidgall/AgentLaboratory>`[仅摘要]`；许可`[未核实]`。
- **通用**。
- **证据质量**：中（preprint + 仓库，我只有摘要级）。**这是本调研里"人在环该怎么落地"最直接可抄的模板**：明确的 co-pilot 模式 + 预定检查点 + 有对照结论说人类反馈提升质量。

### B8. Curie（严谨性优先的自动实验）

- **循环步骤 + 设计重点**【文献】`[仅摘要]`：把**严谨性（rigor）嵌进实验流程**，三个模块——intra-agent rigor module（单 agent 内部的可靠性）、inter-agent rigor module（跨 agent 的方法论控制）、experiment knowledge module（提升可解释性/知识沉淀）。端到端覆盖从提假设到解释结果。<https://arxiv.org/html/2502.16069v1>（2026-09-15）
- **知识/记忆**：显式的 experiment knowledge module`[仅摘要]`。
- **选择/分配**：不是 bandit/树搜索，靠严谨性约束`[仅摘要]`。
- **人在哪**：人提问题；无审核闸门`[仅摘要]`。
- **跑起来要什么 / 许可**：`[未核实]`；开源仓库 <https://github.com/Just-Curieous/Curie>`[仅摘要]`。
- **通用**（计算机系统类实验）。
- **证据质量**：中（preprint + OpenReview 记录 `[仅摘要]`）；对照最强基线「正确回答实验问题」提升 3.4 倍`[仅摘要]`。
- **对我们的意义**`【判断】`：它是唯一把「**严谨性本身当作一个可被设计的模块**」的系统。我们的 `workflow_pass / research_pass` 那套 gate 其实就是同一类东西——Curie 给了它一个外部学术说法。

### B9. MetaGPT Data Interpreter / AutoKaggle

- **状态：`[未核实]`**。预算耗尽，本轮未调研。留作下一轮线索。

---

## C. 循环内部的统计诚实性

### C1. 这些系统里谁真的管了「搜索导致的过拟合 / 多重检验」

- **AlphaAgent：管了，而且写进了目标函数**【文献】`[已打开]`。复杂度正则的原话直接点名过拟合："AST-based structural constraints, preventing over-engineered constructions that are prone to overfitting"；原创性正则（AST 相似度 vs 已有因子库）实际上也在压「换个写法再试一遍」这种变相重复试验。<https://arxiv.org/abs/2502.16789>（2026-09-15）
- **RD-Agent / RD-Agent-Quant：摘要层没有任何过拟合或多重检验控制**【文献】`[已打开，属"未提及"]`。我抓取 arXiv 摘要页后的明确结论是 "Neither overfitting mitigation nor multiple-testing corrections are addressed"。注意这是**「未提及」而非「确认没有」**——正文或源码里可能有，需要下一轮核实。这点对我们很重要：它是个**无人值守 + bandit 加速搜索**的循环，而 bandit 的作用恰恰是让系统更快地朝「回测更好看」的方向试更多次。
- **Chain-of-Alpha：明确无人、全自动**`[仅摘要]`，摘要层未见任何试验计数或多重检验控制 → 风险最高的一类。
- **Sakana v2 / AIDE / MLE-STAR / AlphaEvolve**：它们的评估指标是**外部客观的**（Kaggle 榜、数学问题、benchmark 分数），并且测试集通常独立于搜索过程，所以「搜索过拟合」问题存在但相对可控；**AI Scientist-v2 是例外**——它的成功指标是「论文被接收」，接近自评`【判断】`。
- **Curie**：把严谨性模块化，但我未核实它是否含任何统计多重检验校正`[未核实]`。

### C2. 金融文献对「搜索式循环」的要求

- **Deflated Sharpe Ratio（DSR）—— Bailey & López de Prado**【文献】`[仅摘要]`：DSR 校正两个主要的业绩虚高来源：**多重检验下的选择偏差**，以及收益的非正态性。它把「**未被选中的那些试验**」的信息也算进来——具体是**独立实验的次数**、各次夏普比率的**方差**，再加上样本长度、偏度、峰度。<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551> / <https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf>（2026-09-15）
  - **对我们循环的直接含义**`【判断】`：要算 DSR，就**必须记录试验次数**。也就是说，「append-only trace + 试验计数」不是文书工作，而是最终能不能给出一个可信夏普的**前置条件**。一个不数自己试了多少次的循环，事后永远补不回这个数。
- **Probability of Backtest Overfitting（PBO）—— Bailey, Borwein, López de Prado, Zhu**【文献】`[仅摘要]`：PBO 衡量的是**「策略选择过程」本身**是否导致过拟合，判据是：被选中的策略在样本外是否倾向于**跑输所有试验的中位数**。另有结论：只回测相对**很少**几个策略配置，就很容易得到很高的模拟业绩；金融序列的记忆效应会让过拟合策略在样本外系统性地跑输。<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253>（2026-09-15）
  - **含义**`【判断】`：PBO 评的是**循环**，不是某个策略。这正好是我们要的——我们要审的对象就是这个研究循环本身。
- **Combinatorial Purged Cross-Validation（CPCV）**【文献】`[仅摘要]`：López de Prado 的 CPCV 在一项合成受控环境下的对比研究（KBS 2024）中，被报告为在抑制过拟合上明显优于传统方法，表现为**更低的 PBO** 与**更优的 DSR 检验统计量**。<https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110>（2026-09-15）
- **预注册式的试验计数**：我没有找到一篇专门讲「量化研究预注册」的权威文献 `[未核实]`；上面 DSR/PBO 两条是我能给出的最强支撑——它们在数学上就**要求**你诚实上报试验次数，等价于预注册的效果`【判断】`。

---

## 1. 值得借的设计模式（按优先级）

1. **人定义「要什么」（可自动验证的评分函数 + 护栏），机器找「怎么做」**——来自 AlphaEvolve/FunSearch`【文献】`。落到我们这里：人写死 gate 和指标定义，agent 不许改评分逻辑。
2. **co-pilot 模式 + 预定检查点**——来自 Agent Laboratory`【文献】`（有对照结论：人在每阶段给反馈显著提升质量）+ Alpha-GPT 2.0 的全程人机协作`【文献】`。这直接对应用户要的「人在环」，而且不必牺牲全部自动化：默认 co-pilot，autonomous 只在明确授权时开。
3. **Research / Development / Feedback 三角色分开**——来自 RD-Agent(Q)`【文献】`；再加 FITEE 综述的 **miner / evaluator / interactive assistant** 角色分类`【文献】`。关键是**提假设的 agent 不能同时是给自己打分的 agent**。
4. **假设卡要带「预期结果 + 反驳判据」**——`【判断】`，由 AlphaAgent 的「假设-因子语义一致性」正则推广而来`【文献】`：既然它能用 LLM 判「因子是否忠于假设」，我们就该把假设写成可被检验/可被推翻的形式，并在结果出来后强制回判。
5. **显式的原创性 / 复杂度正则**——来自 AlphaAgent`【文献】`：用 AST 相似度挡「换皮重复试验」，用结构约束挡过度工程化。这同时是**变相的试验计数控制**：它减少了「同一个想法被数十种写法重复试」造成的隐性多重检验。
6. **对实验变体做树搜索，而不是线性重试**——来自 AIDE`【文献】`（MLE-bench 上约 4 倍奖牌的外部证据）+ Sakana v2 的渐进式树搜索 + experiment manager`【文献】`。
7. **定向精炼单个模块，而不是整份重写**——来自 MLE-STAR`【文献】`。在我们的代码库里这还额外带来可审性：diff 小，人才审得动。
8. **把算力按「假设家族」用 bandit 分配**——来自 RD-Agent(Q) 的多臂老虎机方向选择`【文献】`（contextual Thompson sampling 的细节`[仅摘要]`待核实）。**但必须配上第 10 条**，否则 bandit 就是过拟合加速器`【判断】`。
9. **锦标赛 / 辩论 + Elo 给想法排序**——来自 AI co-scientist 的 generate–debate–evolve + Elo`【文献】`；量化侧的对应物是 ContestTrade 的「内部竞赛」`[未核实]`。用于**回测之前**的想法筛选：便宜、且能在不消耗样本的情况下淘汰弱想法`【判断】`。
10. **append-only 的 trace，下一轮必须引用，并且强制计数试验次数**——`【判断】`，但由 DSR 的数学要求**硬性支撑**`【文献】`（DSR 需要独立试验次数与试验间夏普方差）。加上 PBO 评的是「选择过程」而非单策略`【文献】`。QuantAgent 的外环「把新洞见自动写回知识库」是最小可用形态`【文献】`。
11. **把严谨性当成一个模块来设计，而不是当成文档**——来自 Curie 的 intra/inter-agent rigor + experiment knowledge 三模块`【文献】`。
12. **挖掘层与组合层分离，且组合权重随时间可变**——来自 AlphaForge 两阶段设计`【文献】`。

## 2. 要避免的

1. **不数试验次数的循环**——RD-Agent(Q) 在我读到的摘要层**完全没提**过拟合/多重检验控制，却同时用 bandit 去加速搜索`【文献，属"未提及"】`。后果由 DSR/PBO 的数学直接给出：没有试验计数，事后算不出可信的夏普，也评不了 PBO`【文献】`。**这是抄 RD-Agent 时最大的坑。**
2. **自评打分、没有外部数字**——AI Scientist-v2 的成功判据是「论文被同行评审接收」`【文献】`，接近自评；co-scientist 的 Elo 也是 LLM 辩论产生的`【文献】`。可以用它们做**想法排序**，绝不能用来判定「这个策略行不行」——那必须由外部的、人定义好且 agent 改不了的回测/paper 数字来判`【判断】`。
3. **「全自动、无人参与」当卖点**——Chain-of-Alpha 明确宣传 "without human involvement"`【文献】`；RD-Agent 的 GitHub 首页也没有任何审核闸门`【文献】`。用户要的是人在环，照抄这个定位等于做错方向`【判断】`。
4. **在小硬件上做无模板的自由代码生成**——Sakana v2 去掉人工模板`【文献】`、AIDE 靠「把算力换成性能」`【文献】`、RD-Agent 要求装 Docker 且需要 embedding 接口`【文献】`。我们这台机器 earlyoom 会优先杀掉 agent 进程（见项目记忆），所以树搜索的宽度和代码生成的自由度都必须**先设上限**`【判断】`。
5. **夜间无人值守跑批**——与用户明确要求的 human-in-the-loop 冲突；也与 Agent Laboratory 那条「人在每阶段给反馈显著提升质量」的对照结论相反`【文献】`。
6. **把进化/树搜索直接挂在回测指标上当适应度函数**——AlphaEvolve/FunSearch 之所以成立，是因为它们的评估器**便宜、快、且难以被钻空子**`【文献】`；金融回测三条都不满足`【判断】`。要么先做 CPCV 式的评估协议`【文献】`，要么把进化限制在**不消耗样本**的层面（如假设生成、代码质量）。
7. **让 agent 自己改评分/gate 的定义**——`【判断】`。AlphaEvolve 的分工原则（人定评估标准）反过来说就是：一旦 agent 能动评分函数，整个循环的所有数字立即失去意义。

---

## 下一轮该补什么（本轮预算耗尽的坑）

1. 读 RD-Agent **源码/正文**，核实它的 trace / 知识库到底怎么存、怎么被下一轮引用（本轮 `[未核实]`）——这是我们最想抄的部分，却恰好是我最没核实到的部分。
2. 读 **Profit Mirage（2510.07920）**「LLM 金融 agent 的信息泄漏」——直接关系到我们循环的诚实性。
3. 读 **AlphaPROBE（2602.11917）**「检索 + 图上有偏进化」——名字与我们「读知识库 → 提假设」的结构最接近。
4. 核实各仓库的 LICENSE（AIDE / AI-Scientist-v2 / AgentLaboratory / Curie / AlphaForge），引用代码前必做。
5. 核实 FunSearch 的 Nature 出处、Sakana v1 的 arXiv 编号、Alpha-GPT 2.0 的三层架构细节（本轮均只到摘要或未核实）。
