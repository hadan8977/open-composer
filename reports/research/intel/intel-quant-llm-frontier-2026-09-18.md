# 情报侦察报告:2026年9月LLM+现代ML量化前沿现状

- 日期:2026-09-18
- 范围:仅做研究情报侦察,**不写代码、不跑回测**。全部结论来自公开网页/论文/GitHub的检索与阅读,时间戳与URL均随claim标注。
- 阅读方式提示:「已验证结果」= 论文/仓库本身报告的数字,且至少经过同行评审或有可运行代码;「声称/未证实」= 仅作者自述,无第三方复现证据;凡本报告未找到独立复现证据的,一律标注「未见独立复现」。
- 我们的硬件基线:3.9GB内存单机、2核、无GPU、未装PyTorch。凡方法明确需要GPU/PyTorch训练深度网络的,直接标记「本机不可行」。

---

## 1. LLM驱动的alpha挖掘/因子发现方法

### 1.1 汇总表

| 方法(论文/仓库) | 两句话描述 | 报告数字(市场/时间段) | 独立复现状态 | 代码/许可/硬件 | 数据需求 vs 我们已有 | 最便宜的判定实验 |
|---|---|---|---|---|---|---|
| **RD-Agent(Q)** [arXiv:2505.15155](https://arxiv.org/abs/2505.15155)(2025-05,NeurIPS 2025 Datasets&Benchmarks track,[poster](https://neurips.cc/virtual/2025/poster/121804))/[GitHub microsoft/RD-Agent](https://github.com/microsoft/rd-agent) | 双阶段多智能体(Research提假设→Development/Co-STEER写因子代码),做"因子库+模型"联合优化,LLM从不直接看原始行情数据 | CSI300 训练2008-2014/验证2015-2016/测试2017-2020:IC 0.0532(对比Alpha158基线0.0341,+26.7%),年化收益14.21%(对比TRA基线+38%),信息比率1.7382(对比MASTER基线+30%);另在CSI500、**NASDAQ100(美股)**2024-2025做样本外/晚于LLM知识截止的测试([arXiv:2505.15155 HTML](https://arxiv.org/html/2505.15155v2)) | 未见独立复现,论文本身2025-05挂出,已并入官方Qlib仓库 | MIT协议;仅支持Linux+Docker;LLM走LiteLLM(OpenAI/Azure/DeepSeek API);因子挖掘agent本身**API+CPU即可**(单次实验LLM费用<$10),但论文里用于对比的深度时序模型(MASTER/TRA)基线跑在双路Xeon+4×RTX A6000 48GB上——**若只借用因子挖掘循环、跳过深度模型基线对比,本机可行** | 需要PIT行情+能跑沙箱代码的因子回测环境,与我们已有的Alpha101/158/191/OSAP+滚动重训练排序管线概念一致,只需把Qlib CN数据源换成我们自己的美股PIT loader | 不搭建完整RD-Agent,只借"假设→代码→回测反馈→再假设"这套Co-STEER式循环模式,用Claude在我们已有因子库上跑5-10轮小规模迭代,只看IC/RankIC相对现有zoo的提升,不做深度模型对比 |
| **AlphaAgent** [arXiv:2502.16789](https://arxiv.org/abs/2502.16789)(2025-02,KDD 2025,[ACM](https://dl.acm.org/doi/10.1145/3711896.3736838))/[GitHub RndmVariableQ/AlphaAgent](https://github.com/RndmVariableQ/AlphaAgent) | 用"正则化探索"惩罚与已有因子过于相似的新因子,专门对抗alpha衰减 | **CSI500 与 S&P500(美股)**,"过去四年"牛熊市中持续跑赢传统方法与其他LLM方法(原文未给出逐年精确数字) | 未见独立复现 | 代码公开,formulaic alpha框架,无需深度网络训练,理论上API+CPU可跑 | 是本报告中**少数明确在美股上测试过**的方法,数据需求与我们已有的美股PIT行情/因子库直接兼容 | 把"新因子与已有因子相关性惩罚"这条正则化思路,套在我们自己的Alpha191公式空间上做小规模消融,比较有/无该惩罚项时1年滚动IC的衰减速度 |
| **Chain-of-Alpha** [arXiv:2508.06312](https://arxiv.org/abs/2508.06312)(2025-08) | 双链架构:因子生成链+因子优化链并行迭代,只用行情数据 | A股真实基准,声称多项指标超过现有基线(未给具体数字) | **未见公开代码**,未见独立复现 | 论文未附GitHub链接;若无代码需自行按论文重实现 | 与我们已有的Alpha191管线概念重叠度高 | 不单独复刻整套框架;用Claude手工模拟"生成链/优化链"两阶段prompt,在我们现有回测harness上花半天验证该分工模式是否比单链prompt产出更好的候选公式,不追求复现原文数字 |
| **Alpha-R1** [arXiv:2512.23515](https://arxiv.org/abs/2512.23515)(2025-12)/[GitHub iamzuoyou/Alpha-R1](https://github.com/iamzuoyou/Alpha-R1)、[FinStep-AI/Alpha-R1](https://github.com/FinStep-AI/Alpha-R1) | 8B参数、RL训练的"语义门控"推理模型,不是从零挖因子,而是根据市场状态描述筛选/门控已有候选因子 | CSI300主测,**CSI1000零样本**:累计收益42.49%、年化78.18%、夏普4.03([alphaXiv](https://www.alphaxiv.org/overview/2512.23515)) | **未见任何独立复现**;数字极端(零样本夏普4.03),需按我们自己的backtest-forensics标准高度怀疑 | 8B模型,RL训练需GPU(A100级);CPU推理理论可行但极慢,**训练环节本机不可行** | 需要重新训练该门控模型,门槛高 | 不建议投入;若真想验证思路,可先用Claude做"市场状态→因子可信度打分"的零训练prompt版本,而非训练8B模型 |
| **AlphaSAGE** [arXiv:2509.25055](https://arxiv.org/abs/2509.25055)(2025-09,ICLR 2026)/[GitHub BerkinChen/AlphaSAGE](https://github.com/BerkinChen/AlphaSAGE) | 把formulaic alpha挖掘从"RL最大化期望收益"改写为"GFlowNet按奖励比例采样",用RGCN结构编码器+多维稠密奖励 | 声称优于现有基线,挖出低相关、结构新颖的因子组合(具体市场/数字未在摘要中给出,沿用AlphaGen系脉络多为CSI300/Qlib数据) | 未见独立复现;ICLR 2026同行评审通过 | GFlowNet+RGCN=PyTorch图神经网络训练,**需要GPU** | 依赖Qlib CN数据管线 | **本机不可行**,跳过 |
| **AlphaPROBE** [arXiv:2602.11917](https://arxiv.org/abs/2602.11917)(2026-02)/[GitHub gta0804/AlphaPROBE](https://github.com/gta0804/AlphaPROBE) | 把alpha挖掘重新表述为在DAG上导航:贝叶斯因子检索器(探索/利用平衡)+DAG感知因子生成器(利用因子祖先链避免冗余) | 三个中国股票市场数据集,对比8个基线,预测精度/收益稳定性/训练效率均提升(未给具体数字) | 未见独立复现,2026-02刚挂出 | 代码已开源;检索+DAG搜索部分不明显依赖深度网络训练,**可能本机可行**(需读代码确认是否内嵌神经网络评分器) | 三个中国市场数据集,非美股 | 借用"避免与已有因子冗余的DAG检索"思路,在我们已有500+因子的Alpha101/158/191/OSAP zoo上做一次CPU端的冗余度重排,不引入其训练循环 |
| **AlphaForge** [arXiv:2406.18394](https://arxiv.org/abs/2406.18394)(2024-06,AAAI 2025)/[GitHub dulyhao/AlphaForge](https://github.com/dulyhao/alphaforge) | 两阶段:生成式-预测式神经网络挖因子("Factor Zoo"),再用动态权重组合模型按因子近期表现调仓 | 中国市场真实数据,声称组合收益优于当代基准,并提及"real money investment"验证(未给具体数字) | AAAI同行评审通过,但**未见第三方独立复现** | 生成式神经网络训练**需要GPU/PyTorch** | 中国市场,非美股 | **本机训练不可行**;若想借鉴,只能借"因子池+动态再加权"的组合层思路,套用在我们已有静态因子库上做纯CPU的加权优化 |
| **AlphaGen** [GitHub RL-MLDM/alphagen](https://github.com/RL-MLDM/alphagen)(KDD 2023) | 用强化学习(PPO类)生成一组"协同"的formulaic alpha集合,奖励函数考虑组合IC而非单因子IC | CSI300,论文报告显著优于既有技术(该系列后续论文如AlphaForge/AlphaSAGE/Alpha²均以此为基线复现对比) | **无独立复现研究**,但被后续多篇2024-2026论文当作标准基线反复重跑,构成事实上的"多次间接复现" | PyTorch+stable-baselines3(RL)+Qlib+Baostock中国数据;RL训练**建议GPU**,CPU可跑但慢 | 依赖中国数据源(Baostock/Qlib CN provider),需要移植到我们的美股PIT数据 | 不建议本机训练RL策略;如果一定要试,先用CPU跑其"生成器"在极小universe(如50只票、1年数据)上验证代码能否落地,而非追求论文级效果 |
| **alpha-gfn** [GitHub nshen7/alpha-gfn](https://github.com/nshen7/alpha-gfn) | 用GFlowNet生成formulaic alpha,PyTorch实现 | 未见配套论文给出的市场/数字(来源信息不足以确认这是独立发表方法还是对AlphaGen/AlphaSAGE思路的个人复刻) | **来源不明**,大概率是个人/课程级复刻而非同行评审方法,置信度低 | PyTorch+GFlowNet,**需要GPU** | 未知 | 不投入 |
| **CogAlpha(Cognitive Alpha Mining via LLM-Driven Code-Based Evolution)** [arXiv:2511.18850](https://arxiv.org/abs/2511.18850)(2025-11,ACL 2026,[OpenReview](https://openreview.net/forum?id=jfgdjMhdVo))/代码疑似镜像:[sanchez0623/cogalpha-aicode](https://github.com/sanchez0623/cogalpha-aicode)、[DracoUnion/cogalpha-aicode](https://github.com/DracoUnion/cogalpha-aicode) | 7层21个LLM智能体分层生成代码级alpha,多智能体质量检查器+5维指标过滤+"思维进化"模块反复精炼 | 5个股票数据集、3个股票市场,预测精度/鲁棒性/泛化性均优于现有方法(未给具体数字,市场是否含美股未确认) | **未见独立复现**;两个GitHub代码仓库均非明显的官方组织账号,**官方代码归属存疑**,谨慎对待 | 纯LLM+Python代码生成(OpenAI SDK+Pydantic),**不需要GPU/训练神经网络**,本机API+CPU理论可行 | 与我们现有Alpha101/191公式空间兼容 | 本报告认为这是**性价比最高的一类**:用Claude模拟"生成候选代码alpha→质量检查→5维指标过滤→迭代精炼"的流程,直接在我们已有的screen_factors.py式管线上跑一批候选,只看是否有新因子1年OOS IC为正且与现有zoo低相关 |
| **MCTS Alpha Jungle**("Navigating the Alpha Jungle") [arXiv:2505.11122](https://arxiv.org/abs/2505.11122)(2025-05,AAAI) | LLM提出/变异符号化alpha公式,MCTS搜索由真实回测反馈(IC类奖励)引导,逐步收窄搜索空间 | 真实股票市场数据,声称预测精度/交易表现/可解释性均优于现有方法(市场细节未在检索到的摘要中给出) | **未见独立复现** | **未找到公开代码仓库**;纯LLM+MCTS+回测,理论上不需要GPU | 数据需求与我们已有回测管线一致,但因无代码需要重新实现搜索逻辑 | 用我们已有的回测引擎做reward,搭一个极简MCTS(几十次rollout)包一层Claude做公式变异提议,只在小样本(如100只票、2年数据)上验证是否能优于随机变异 |

### 1.2 关键结论
- 这11个方法里,**只有AlphaAgent明确在S&P500(美股)上测试过**,其余全部以CSI300/CSI500/CSI1000/中国A股为主战场——这意味着几乎所有"报告数字"都不能直接当作美股的预期效果。
- 需要GPU/PyTorch训练深度网络、本机不可行的:AlphaSAGE、AlphaForge、AlphaGen(强训练)、alpha-gfn、Alpha-R1(训练8B模型)。
- 不需要训练神经网络、纯LLM+代码/搜索、本机API+CPU可行的:RD-Agent的因子挖掘循环本身(不含深度模型基线对比)、AlphaAgent、Chain-of-Alpha、AlphaPROBE(部分)、CogAlpha、MCTS Alpha Jungle。
- **没有一个方法被第三方独立复现**——这是整个领域(截至2026-09)的共性问题,不是个别方法的缺陷。

---

## 2. LLM智能体设计/管理整个策略(基准测试及其结论)

| 项目 | 两句话描述 | 结果 | 复现/可信度 | 代码/硬件 | 对我们的意义 |
|---|---|---|---|---|---|
| **AlphaForgeBench** [arXiv:2602.18481](https://arxiv.org/abs/2602.18481)(2026-02)/[GitHub finbrain-lab-hkustgz/AlphaForgeBench](https://github.com/finbrain-lab-hkustgz/AlphaForgeBench) | 把LLM重新定位为"量化研究员"而非"随机交易智能体":要求生成可执行的alpha因子代码并组合成策略,而非直接输出交易动作,以此规避直接交易型agent的不稳定性 | 覆盖claude-sonnet-4.5、deepseek-v3.2、gemini-3-flash/pro、gpt-5.2、grok-4.1-fast共6个前沿模型、7类资产、903条查询、35190次实现;发现该范式"温度不变、高度可复现",比直接交易基线更具区分度 | 这是一个**评测框架**,不是alpha来源的证明——它证明的是"LLM写因子代码"比"LLM直接下单"更可复现,**没有**证明任何LLM设计的策略真的能跑赢经典基线并产生真实边际收益 | GitHub公开;跑基准本身是LLM推理调用,CPU可行,但我们没必要复现整套基准,只需借鉴其评测方法论 | 提醒我们:评估自己用LLM设计的因子/策略时,应优先看"确定性、可复现性",这本身不等于"有alpha" |
| **Agent Market Arena / "When Agents Trade"** [arXiv:2510.11695](https://arxiv.org/abs/2510.11695)(2025-10) | 首个跨加密货币和股票市场的"终身、实时"LLM交易智能体基准,测试GPT-4o/4.1、Claude-3.5-haiku、Claude-sonnet-4、Gemini-2.0-flash等模型backbone,配合4种agent架构 | 发现**agent框架/架构对行为的影响远大于底层LLM模型本身**——即研究者主要在测试自己的prompt/架构工程,而非模型的真实市场判断力 | 论文本身是新基准,暂无第三方复现;但其发现与AlphaForgeBench"直接交易型评测不稳定"的动机互相印证 | — | 支持"不要把LLM直接当交易决策者"的结论(见第7节) |
| **QRAFTI** [arXiv:2604.18500](https://arxiv.org/abs/2604.18500)(2026-04) | 多智能体框架模拟量化研究团队,通过MCP server把面板数据操作(读数据/建因子/写代码)暴露为标准化工具调用,辅以反思式规划和结构化日志 | 初步评估显示,在多步骤实证研究任务上,"工具调用+反思规划"比"纯代码生成"更具可解释性和稳定性(未给具体收益数字——这是一个研究流程工具,不是alpha生成器) | 未见独立复现,2026-04刚发布 | MCP工具化架构,理论上CPU+API可行 | 这类工具的价值在"研究流程标准化/可复现",而非直接产生alpha——与我们项目里"每次回测都要出report、每个信号都要记录"的规则方向一致 |
| **QuantaAlpha** [arXiv:2602.07085](https://arxiv.org/abs/2602.07085)(2026-02)/[GitHub QuantaAlpha/QuantaAlpha](https://github.com/QuantaAlpha/QuantaAlpha) | LLM+进化策略结合的alpha挖掘框架,号称"自演化轨迹" | 论文自称结果良好,但一名第三方评测者(独立博客)明确写道"我没有复现出这些结果"([hysenlabs.com评测](https://hysenlabs.com/en/projects/quantaalpha-quantaalpha)) | **有反例的失败复现**,应归入炒作/存疑清单 | — | 不建议投入 |

---

## 3. LLM新闻/文件/财报电话会议信号抽取,成本后alpha证据

| 来源 | 两句话描述 | 报告数字(市场/时间段/成本) | 可信度评估 |
|---|---|---|---|
| **"From Text to Alpha: Can LLMs Track Evolving Signals in Corporate Disclosures?"** [arXiv:2510.03195](https://arxiv.org/html/2510.03195v5)(2025-10,作者来自LinqAlpha/MIT/BlackRock/Blackstone/摩根大通/富达等机构联合) | "LLM作抽取器、embedding作标尺"框架,追踪企业披露文本中演变的语义信号,预测异常收益 | S&P100成分股,2010年1月-2024年12月,64个季度、5615个"公司-季度"观测点;显著优于传统文本方法预测异常收益 | 目前本报告中**可信度最高**的LLM文本信号研究之一:样本长(15年)、跨牛熊周期、多机构联合作者背书。**但**未在检索中确认是否报告了扣费后净收益数字,需读全文核实 |
| **"Taxonomy-Aligned Risk Extraction from 10-K Filings with Autonomous Improvement Using LLMs"** [arXiv:2601.15247](https://arxiv.org/abs/2601.15247)(2026-01) | 三阶段管线:LLM抽取风险因子并附原文引用→embedding映射到分类体系→LLM-as-judge校验 | 从标普500公司10-K中抽取10688条风险因子(方法论文,未报告交易层面alpha数字) | 这是**基础设施/特征工程论文**,不是alpha证明,但抽取方法可直接产出符合我们"point-in-time feature packet"规则的结构化特征 |
| **Ghosal, "LLM-Driven Investment Models: ... Earnings Call Transcripts"**,SSRN [6351439](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6351439)、[6510327](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6510327)(2026-02/03) | 用LLM从财报电话会议文本抽取信号预测收益 | 未在检索摘要中给出具体成本后收益数字 | **单作者SSRN预印本,未同行评审**,置信度低,仅作方向参考 |
| **"355%累计收益"OPT情绪策略** [Substack博客转述](https://navnoorbawa.substack.com/p/how-llm-sentiment-analysis-generated),转述一篇分析2010-2023年96.5万条美股新闻的研究 | 用类GPT模型(OPT)做新闻情绪打分,OPT预测收益准确率74.4%,多空策略在2021-08至2023-07产生355%累计收益,含10bp交易成本 | 短窗口(2年)、单一博客二次转述、未直接核实原始论文的样本外/多重检验处理 | **炒作嫌疑高**:数字极端、来源是营销向博客而非论文本身直接阅读,需要找到并精读原始论文再评估,当前**不采信** |
| **混合情绪多阶段LLM市场中性alpha** [MDPI 2673-2688/7/4/138](https://www.mdpi.com/2673-2688/7/4/138) | 多阶段LLM情绪抽取,构建市场中性组合 | 16年测试期,年化超额收益51.02%(扣除交易成本后),夏普1.06,索提诺2.61 | 有具体扣费后数字和长样本期,但发表在MDPI开放期刊(审稿严格度普遍低于顶会/顶刊),51%年化中性alpha的量级本身值得怀疑,建议列为"需要forensic复核"而非直接采信 |
| **"A Review of LLMs for Stock Price Forecasting from a Hedge-Fund Perspective"** [arXiv:2605.05211](https://arxiv.org/abs/2605.05211)(2026-04投稿,IEEE CAI西班牙2026-05接收) | 从对冲基金视角综述LLM在情绪抽取/财报文本/价格序列token化/多智能体交易中的应用 | 综述性论文,专门列出"未被充分强调的坑":情绪分析脆弱性、数据集/预测horizon设计问题、评估指标误用、数据泄漏、流动性溢价污染、股价可预测性的理论极限 | 本报告认为这是**最值得直接精读的一篇综述**,因为它专门整理了"看起来好但其实是方法论缺陷"的陷阱清单,与我们backtest-forensics技能的关注点高度重合 |

**小结**:文本信号抽取里,唯一同时具备"长样本+跨机构背书+明确预测对象"的是`From Text to Alpha`(S&P100, 2010-2024);其余要么是方法论文(无alpha数字)、要么是单作者预印本、要么是数字过于漂亮但来源不够硬。**没有一篇文本信号论文的扣费后alpha经过了独立第三方复现。**

---

## 4. 现代非深度表格方法是否击败GBDT(财务面板数据)

| 方法/证据 | 结论 | 来源 |
|---|---|---|
| TabReD、TabArena基准 | 在**贴近实盘的时间切分(而非IID切分)评估**下,GBDT依然是稳健首选;注意力类架构在时间分布漂移下退化更快,而多数表格基准假设IID切分,与财务walk-forward验证的场景不符 | [TabReD/TabArena综述,delphicalpha.substack.com](https://delphicalpha.substack.com/p/the-quiet-revolution-tabular-machine)(未能取得付费墙后全文,以搜索摘要为准) |
| **OmniTabBench** [arXiv:2604.06814](https://arxiv.org/pdf/2604.06814)(2026-04) | 系统性描绘GBDT、神经网络、表格基础模型在大规模场景下的经验前沿边界 | 同上 |
| **TabPFN v2**(Nature发表,[GitHub PriorLabs/tabpfn](https://github.com/PriorLabs/tabpfn)) | 小数据集上的上下文学习表格基础模型确实真实有效,但**"没有CPU兜底方案"**,只有小数据集才能在CPU/集成显卡上勉强跑,生产级用法需要GPU(推荐H100/A100级) | [搜索摘要综合](https://news.ycombinator.com/item?id=42647343)、[TabPFN-2.5论文](https://arxiv.org/pdf/2511.08667) |
| 时序基础模型(TSFM)在金融收益预测上的表现 | 现成的(off-the-shelf)时序基础模型在零样本/微调场景下**跑不赢标准的集成学习和神经网络基线**;针对金融数据原生预训练能显著缩小差距,但需要大规模预训练算力 | ["Re(Visiting) Time Series Foundation Models in Finance" arXiv:2511.18578](https://arxiv.org/pdf/2511.18578)、["Deep Learning for Financial Time Series" arXiv:2603.01820](https://arxiv.org/html/2603.01820v1)、["Pretrained TSFM for Financial Return Forecasting" arXiv:2606.27100](https://arxiv.org/html/2606.27100) |

**直接结论**:截至2026-09,**没有找到任何在真实(非IID、walk-forward)财务面板数据上被证明系统性击败GBDT的非深度方法**。唯一有实质突破的挑战者(TabPFN v2)是深度模型(transformer架构),且明确需要GPU,在我们的硬件上不可行,即便有GPU,其优势场景也是小数据集而非我们这种大规模滚动面板。**结论:继续用LightGBM/GBDT类方法作为表格模型主力是当前证据支持的选择,不是因循守旧。**

---

## 5. "ML能否跑赢横截面收益里的动量/价值基线"复现之争(两方证据)

**正方(ML/因子择时有真实、扣费后能存活的边际收益)**
- Gu, Kelly, Xiu (2020), *Empirical Asset Pricing via Machine Learning*, RFS 33(5):2223-2273 / [NBER WP 25398](https://www.nber.org/system/files/working_papers/w25398/w25398.pdf):树模型与神经网络通过捕捉非线性交互显著跑赢线性方法,但**所有方法一致认定的主导预测信号本身就是动量、流动性、波动率的变体**——即ML更多是在更好地组合动量类信号,而非发现与动量正交的新信息。
- ["What Drives the Performance of Machine Learning Factor Strategies?" (Esakia, Lancaster, FoFI 2026工作论文)](http://wp.lancs.ac.uk/fofi2026/files/2026/03/FoFI-2026-012-Mikheil-Esakia.pdf)(2026-03):因子层面的短期动量择时是ML因子策略收益的主要驱动力之一,且这一价值增量**扣除交易成本后依然稳健存活**,即便择时会提高换手率。
- QuantPedia,["The Expected Returns of Machine-Learning Strategies"](https://quantpedia.com/the-expected-returns-of-machine-learning-strategies/):部分ML策略扣费后月度净收益可达1.42%,即便换手率超过50%。

**反方(大部分"因子"经不起复现检验,ML输入本身可能是噪音)**
- Hou, Xue, Zhang (2020), *Replicating Anomalies*, RFS 33(5):2019-2133([SSRN 2961979](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2961979)):对452个已发表异象,用NYSE断点+市值加权+多重检验校正(t>2.78)重新检验,**65%无法通过单一检验门槛,提高到多重检验门槛后失败率升到82%**;即使复现成功的异象,经济量级也远小于原文声称。
- 领域共识(见第1、6节引用的多篇2025-2026 alpha挖掘论文):formulaic alpha挖掘普遍面临"data snooping/p-hacking"风险,回测里显著但实盘迅速衰减的伪因子大量存在。

**本报告结论**:这场争论**目前双方证据都站得住脚,没有一锤定音的胜负**——ML/LLM驱动的横截面策略确实能在严谨研究里展示扣费后的真实边际收益,但(a)这部分边际收益相当一部分可以被"因子动量/短期择时"这类相对简单的机制解释,(b)作为ML输入的因子库本身有很高比例经不起标准复现门槛的检验。**没有找到任何研究令人信服地证明存在一种ML/LLM方法,能在扣费后以大幅度、无争议地跑赢一个简单动量或价值基线**——每一个"能跑赢"的结果背后都跟着"但其实主要是动量"或"未被复现"的注脚。

---

## 6. Qlib现状

- **最近一次带版本号的发布是v0.9.7,2024-08-15**([GitHub Releases](https://github.com/microsoft/qlib/releases))——距今2026-09已超过2年,官方发布节奏已经停滞,即便仓库本身仍有新commit(主要是RD-Agent集成相关)。
- **美股(US)基准路径存在未修复的bug**:[GitHub Issue #1428](https://github.com/microsoft/qlib/issues/1428)(开于2023-01-28)记录了把官方LightGBM+Alpha158配置从`csi300`改成`sp500`、`region`改成`us`后出现`AttributeError: 'float' object has no attribute 'lower'`(instrument变量被求值为NaN),**该issue目前看不到被解决的证据**。
- 检索未发现任何被广泛引用的、独立第三方发表的"Qlib Alpha158+LightGBM在美股(Russell/S&P500)上"的基准论文——最接近的是Microsoft自己团队的RD-Agent(Q)论文里对NASDAQ100 2024-2025的补充测试([arXiv:2505.15155](https://arxiv.org/abs/2505.15155)),这是官方团队自证,不是第三方复现,且测的是NASDAQ100而非我们用的广谱含退市美股全市场。
- Qlib的官方旗舰基准(Alpha158/Alpha360+LightGBM/DoubleEnsemble等)**持续被验证、被引用的对象始终是CSI300/A股**([examples/benchmarks](https://github.com/microsoft/qlib/tree/main/examples/benchmarks))。
- 新一代LLM因子挖掘论文(RD-Agent(Q)、AlphaAgent、Chain-of-Alpha等)全部把"Alpha158+通用GBDT"当作**待超越的2020年代经典基线**,而不是当前SOTA——RD-Agent(Q)自己在CSI300上就把Alpha158的IC/年化收益/信息比率甩开了26.7%/38%/30%。

**第7节会给出对"是否该用Qlib Alpha158+LightGBM(CSI300,2008-2020)作为2026美股起点"的直接回答。**

---

## 7. 2025-2026年综述/批判性回顾

| 来源 | 核心观点 | 日期 |
|---|---|---|
| Zhang, Liu, Zhang, Shi, *A survey on large language model-based alpha mining*, Frontiers of Information Technology & Electronic Engineering, 26(10):1809-1821, DOI [10.1631/FITEE.2500386](https://link.springer.com/article/10.1631/FITEE.2500386) | 从"智能体角色"视角系统梳理LLM alpha挖掘系统;指出现有方法普遍存在:(1)依赖人工反馈或已有alpha做in-context learning种子,自动化程度有限(如AlphaGPT、AlphaAgent);(2)多模态输入的通用性不足;(3)alpha衰减问题在现有框架里基本未被有效约束解决 | 2025 |
| ["The Alpha Factory Illusion: Why Your Factor Mining Agent Only Looks Like It Is Learning"](https://llmquant.substack.com/p/the-alpha-factory-illusion-why-your) | 实践者批评:LLM因子挖掘agent的"错误类型"会随迭代演变(从方向性错误→操作性错误→策略性自我过滤),看起来像人类研究员的成长曲线,但**总错误量/失败率并未真正下降**——这是"进步的错觉"而非真实进步 | 2026-08-10 |
| ["LLMs in Quant Research: What Actually Works in 2026"](https://www.zerve.ai/blog/llms-in-quantitative-research) | LLM在**代码生成(2-4倍提速)、调试(2-3倍)、文档撰写(3-5倍)**上确实有硬提速;但在**原创研究/假设生成**上基本无效——"假设建议很少能通过验证",市场预测能力增量很小;结论:把LLM当"生产力基础设施"的团队受益,当"alpha生成基础设施"的团队没有受益 | 2026(未标注具体日期,内容指向2026年) |
| ["A Review of Large Language Models for Stock Price Forecasting from a Hedge-Fund Perspective"](https://arxiv.org/abs/2605.05211)(IEEE CAI西班牙2026-05接收) | 从对冲基金视角系统列出容易被文献低估的陷阱:情绪分析脆弱性、数据集/预测horizon设计缺陷、评估指标误用、数据泄漏、流动性溢价污染、股价可预测性的理论上限 | 2026-04投稿 |

---

## 8. 排名前5的方法(值得未来一周投入算力),含理由与最便宜的判定实验

1. **RD-Agent式"假设→代码→回测反馈→再假设"研究循环(仅借循环模式,不要整套框架/深度模型对比)**——理由:唯一有NeurIPS 2025同行评审背书、且明确报告过美股(NASDAQ100)样本外测试的方法,因子挖掘agent本身LLM成本<$10、CPU可跑([arXiv:2505.15155](https://arxiv.org/abs/2505.15155))。判定实验:在我们已有Alpha101/158/191/OSAP+滚动重训练排序管线上,用Claude跑5-10轮"提假设→写因子代码→用IC/RankIC打分→反馈"迭代,只看能否产出优于现有zoo的新因子,不做深度模型对比。
2. **CogAlpha式多阶段LLM代码alpha生成+5维过滤**——理由:纯LLM+代码,不需要GPU/PyTorch,ACL 2026同行评审通过([arXiv:2511.18850](https://arxiv.org/abs/2511.18850)),与我们现有因子DSL兼容;唯一警示是官方代码归属存疑,应重新实现思路而非直接拉取代码。判定实验:用Claude生成20个候选OHLCV公式化因子,过我们现有screen_factors.py式流程做IC+冗余度筛选,看1年OOS是否有存活者。
3. **AlphaEval式回测前(backtest-free)预筛选**([arXiv:2508.13174](https://arxiv.org/abs/2508.13174),[GitHub LeoDingggg/AlphaEval](https://github.com/LeoDingggg/AlphaEval))——理由:这是让方法1、2变得可负担的基础设施,开源、无需GPU,五维度(预测力/稳定性/鲁棒性/金融逻辑/多样性)评估声称与完整回测一致但效率更高。判定实验:先在我们已经跑过完整walk-forward回测、已知样本外结果的几个老因子上跑一遍AlphaEval的指标,检查其排序是否与我们真实回测结果一致,再决定是否用它给新候选做初筛。
4. **文本→PIT特征包抽取(10-K风险分类、财报电话会议语义追踪)**([arXiv:2601.15247](https://arxiv.org/abs/2601.15247)、[arXiv:2510.03195](https://arxiv.org/html/2510.03195v5))——理由:是本报告中唯一同时具备"长样本(2010-2024)+跨机构背书+明确预测目标"的LLM文本信号研究,且直接契合我们项目"LLM/新闻/文件输入必须先变成point-in-time特征包"的规则,不需要GPU。判定实验:用Claude给~50只票×8个季度做结构化风险标签抽取,作为特征加入现有排序管线,看小样本IC是否有提升,再决定是否用用户后续提供的非Claude批量标注端点做全量扩展(遵守"不用Claude token做批量数据标注"的规则)。
5. **QRAFTI式工具调用型研究助手**([arXiv:2604.18500](https://arxiv.org/abs/2604.18500))——理由:风险最低、确定性最高的收益来源,与Zerve.ai"LLM在代码/报告基础设施上ROI最高"的结论完全一致;不是为了找alpha,而是为了降低我们自己因子复现、报告撰写、source card维护的人工成本。判定实验:不需要"是否有alpha"的测试,直接在下一轮研究报告/因子复现工作中试用这套"工具调用+反思规划"模式,用节省的人工时间衡量价值。

---

## 9. 炒作/本机不可复现清单(一行理由)

- **AlphaForge**([arXiv:2406.18394](https://arxiv.org/abs/2406.18394))——生成式神经网络训练需要GPU,且仅在中国市场验证,无独立复现。
- **AlphaGen / alpha-gfn / AlphaSAGE**([RL-MLDM/alphagen](https://github.com/RL-MLDM/alphagen)、[nshen7/alpha-gfn](https://github.com/nshen7/alpha-gfn)、[arXiv:2509.25055](https://arxiv.org/abs/2509.25055))——RL/GFlowNet训练需要GPU,绑定Qlib CSI300/Baostock中国数据源,alpha-gfn来源归属存疑。
- **Alpha-R1**([arXiv:2512.23515](https://arxiv.org/abs/2512.23515))——训练8B模型需要GPU,CSI1000零样本夏普4.03等数字极端且无任何独立验证,应默认视为过拟合/未经审视直到被复现。
- **QuantaAlpha**([arXiv:2602.07085](https://arxiv.org/abs/2602.07085))——已有第三方评测者明确表示"未能复现"其结果([hysenlabs.com](https://hysenlabs.com/en/projects/quantaalpha-quantaalpha))。
- **MASTER等深度时序SOTA模型**([SJTU-DMTai/MASTER](https://github.com/SJTU-DMTai/MASTER))——transformer架构需要GPU,且是中国市场调优,不建议本机采用。
- **TabPFN v2作为GBDT替代**([PriorLabs/tabpfn](https://github.com/PriorLabs/tabpfn))——虽是Nature发表的真实成果,但"无CPU兜底方案",本机规模完全跑不动,即便有GPU其优势场景也是小数据集而非我们的大规模滚动面板。
- **直接把LLM当交易决策者/组合经理**(Agent Market Arena风格,[arXiv:2510.11695](https://arxiv.org/abs/2510.11695))——已有基准证明其行为主要由agent框架而非模型真实市场判断力驱动,run-to-run不稳定,这正是AlphaForgeBench要另起炉灶的原因。
- **"LLM情绪355%累计收益"的博客化传播**([Substack](https://navnoorbawa.substack.com/p/how-llm-sentiment-analysis-generated))——营销向二次转述,窗口短、未核实原始论文的多重检验处理,当前不采信。
- **Chain-of-Alpha**([arXiv:2508.06312](https://arxiv.org/abs/2508.06312))——未找到公开代码,无法独立验证其"跑赢基线"的说法。
- **MCTS Alpha Jungle**、多数formulaic因子挖掘论文——普遍缺乏第三方复现,应把它们的"跑赢基线"数字当作待验证声称,而不是既定事实。

---

## 10. 直接回答:Qlib的Alpha158+LightGBM(CSI300,2008-2020基准)对2026年美股是否是合理起点,还是已经过时?

**两者都对,取决于问的是"方法论形状"还是"具体基准数字"。**

- **作为方法论形状(特征工程taxonomy+滚动重训练+GBDT横截面排序),它并不过时**:第4节的证据(TabReD/TabArena/OmniTabBench,2026)显示,在贴近实盘的时间切分评估下GBDT依然是稳健首选,没有找到系统性击败它的非深度或深度方法(TabPFN v2需要GPU,优势场景也不是大规模walk-forward面板)。我们已经独立复刻了这套形状(Alpha101/158/191/OSAP+滚动重训练排序管线),这个选择本身没有问题。
- **作为具体基准数字/数据集,它是过时且不可迁移的**:(1)v0.9.7版本发布于2024-08-15,官方发布节奏已停滞超过2年([GitHub Releases](https://github.com/microsoft/qlib/releases));(2)Qlib官方的美股基准路径有一个开放两年多未解决的bug([Issue #1428](https://github.com/microsoft/qlib/issues/1428)),说明核心团队并未真正维护、验证过美股配置;(3)没有找到任何被广泛引用的第三方美股Alpha158+LightGBM基准论文,唯一的官方补充测试(NASDAQ100 2024-2025)来自Microsoft自己的RD-Agent(Q)论文而非独立第三方;(4)CSI300(2008-2020)和美股(2016-2026)在市场微观结构、流动性机制、可做空规则、因子zoo构成上差异巨大,直接套用其数字毫无意义;(5)新一代LLM因子挖掘文献(RD-Agent(Q)、AlphaAgent等)全部把"Alpha158+通用GBDT"当作**待超越的经典基线**而非当前SOTA,RD-Agent(Q)自己在CSI300原地就把它的IC/年化收益/信息比率甩开了26.7%-38%。

**结论**:不要把Qlib的CSI300数字当作性能目标或起点基准,但可以把它的"特征taxonomy+滚动重训练+GBDT排序"架构继续当作正确的形状——而我们已经用自己的Alpha101/158/191/OSAP+广谱PIT美股universe做到了这一点,某种意义上已经超越了直接套用Qlib CSI300基准的做法。

---

## 11. 直接回答:对于无GPU、只有纸面账户的单人操作者,LLM在策略管线里当前最高期望值的用法在哪里?(排名+证据)

1. **代码/研究生产力副驾驶**(写/调试因子与回测代码、写source card、写PIT特征包抽取脚本、写报告)——证据:["LLMs in Quant Research: What Actually Works in 2026"](https://www.zerve.ai/blog/llms-in-quantitative-research)报告代码生成2-4倍、调试2-3倍、文档撰写3-5倍的确定性提速,并明确指出这是ROI最可靠的用法;与我们项目本身"Claude用于研究/代码"的规则完全一致。
2. **在我们已有因子库之上做"假设→代码→回测反馈"式的因子挖掘研究助手**(RD-Agent/CogAlpha/MCTS-Alpha-Jungle式模式)——证据:RD-Agent(Q)报告单次实验LLM成本<$10、CPU可跑([arXiv:2505.15155](https://arxiv.org/abs/2505.15155));但必须叠加AlphaEval式回测前预筛选([arXiv:2508.13174](https://arxiv.org/abs/2508.13174))控制成本,且必须像对待人类提出的假设一样,经过完整的样本外/PIT纪律检验——因为FITEE综述([DOI:10.1631/FITEE.2500386](https://link.springer.com/article/10.1631/FITEE.2500386))和实践者批评(["Alpha Factory Illusion", 2026-08](https://llmquant.substack.com/p/the-alpha-factory-illusion-why-your))都警告这个模式容易产生"看起来在进步但其实没有"的错觉。
3. **把新闻/文件/财报文本抽取为point-in-time特征包,作为ML模型的输入特征而非独立信号**——证据:["From Text to Alpha"](https://arxiv.org/html/2510.03195v5)(S&P100,2010-2024,多机构联合)和["Taxonomy-Aligned Risk Extraction from 10-K"](https://arxiv.org/abs/2601.15247)显示这是LLM语言理解力真正能提供GBDT从OHLCV数据中拿不到的信息增量的地方;这恰好也是我们项目本身"LLM/新闻/事件/宏观输入必须先变成point-in-time特征包才能影响交易行为"的既定规则——文献支持的最高价值用法,正是我们已经被要求遵循的架构。
4. **不建议(当前阶段)**:让LLM直接充当交易决策者/组合经理——证据:Agent Market Arena基准([arXiv:2510.11695](https://arxiv.org/abs/2510.11695))发现LLM交易agent的行为主要由agent架构而非模型真实市场判断力驱动;AlphaForgeBench([arXiv:2602.18481](https://arxiv.org/abs/2602.18481))正是因为直接交易型LLM评测run-to-run不稳定、难以复现才另起炉灶;对冲基金视角综述([arXiv:2605.05211](https://arxiv.org/abs/2605.05211))单独列出情绪分析脆弱性、数据泄漏、流动性溢价污染等被低估的坑。

---

## 附:本报告未能验证/需要进一步精读全文的项目

- ["From Text to Alpha"](https://arxiv.org/html/2510.03195v5)是否报告了扣费后净收益数字——需读全文核实,当前只确认了预测异常收益的显著性。
- ["混合情绪分析" MDPI论文](https://www.mdpi.com/2673-2688/7/4/138)的51.02%年化中性alpha数字,量级异常,需要用backtest-forensics标准复核样本内外划分与多重检验处理。
- AlphaPROBE、MCTS Alpha Jungle的代码是否真的不依赖任何神经网络训练(本报告基于摘要判断为"可能CPU可行",需要实际读代码确认)。
- CogAlpha的两个GitHub镜像仓库([sanchez0623](https://github.com/sanchez0623/cogalpha-aicode)、[DracoUnion](https://github.com/DracoUnion/cogalpha-aicode))与ACL 2026论文作者的关系未核实,使用前应先确认是否为官方仓库。
