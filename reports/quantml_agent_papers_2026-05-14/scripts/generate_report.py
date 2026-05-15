from __future__ import annotations

import csv
import html
import json
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTES_DIR = ROOT / "paper_notes"
TODAY = date(2026, 5, 14).isoformat()


DETAILS: dict[str, dict[str, str]] = {
    "AlphaCrafter": {
        "title": "AlphaCrafter: A Full-Stack Multi-Agent Framework for Cross-Sectional Quantitative Trading",
        "authors": "Yishuo Yuan; Jiayi Sheng; Sirui Zeng; Jiaqi Wang; Jiaheng Liu",
        "published": "2026-05-07",
        "one_liner": "把因子挖掘、制度状态感知、组合筛选和风险约束执行组织成 Miner-Screener-Trader 闭环，是截图中“全栈 Multi-Agent 量化框架”的代表。",
        "problem": "横截面量化策略不是只找到一个历史有效因子即可。真实流程需要连续发现候选因子、判断市场制度是否改变、筛掉在当前环境中失效的信号，并在风险预算下形成交易组合。传统因子挖掘偏离线搜索，传统执行偏固定规则，二者之间缺少能够从交易反馈回到研究端的闭环。",
        "method": "框架把系统拆成 Miner、Screener、Trader 三类 Agent。Miner 负责 LLM 引导的连续因子搜索，Screener 结合制度状态和候选因子的历史表现调整权重，Trader 在组合和风险约束下执行。反馈不是停留在语言解释层，而是把执行结果反馈给 Screener 和 Miner，使新因子搜索与旧因子调权形成循环。",
        "data": "论文围绕 CSI 300 和 S&P 500 等横截面股票池做实验，截图强调其在中美市场都优于若干 SOTA 基线，并且跨试验方差较低。原文将非平稳市场、微观结构摩擦、行为因素作为背景，但仍属于研究回测而非实盘订单系统。",
        "metrics": "关注年化收益、风险调整收益、跨市场稳定性、因子表现分布和交易组合结果。截图称其在 CSI 300 与 S&P 500 上均显著超越基线，且方差最低；报告中应把该结论表述为论文实验结果，而非可直接复用的实盘收益承诺。",
        "innovation": "核心价值在于把“因子搜索”从一次性离线优化扩展为全栈自适应管道：因子发现、制度感知、风险约束执行和反馈更新放在同一系统中讨论。它把 FactorEngine/Hubble 式因子发现推进到更接近交易生命周期的位置。",
        "limits": "截图指出没有完整报告交易成本细节；从论文设定看，Agent 闭环仍依赖回测数据和任务分解质量。多 Agent 之间的反馈可能引入共振式过拟合，因此需要额外的时间切分、交易成本、容量和延迟验证。",
        "relation": "可视为 FactorEngine 和 Hubble 的上层集成框架，也与 TrustTrade/Reliable Evaluation 共享一个问题：Agent 之间如何形成可靠共识而不是互相放大错误。",
        "practice": "若用于内部研究，应先把 Miner 生成的因子表达、Screener 的制度标签、Trader 的约束和每次组合变更都结构化记录；只有在固定验证窗口、净成本收益和基准族对照通过后，才可进入纸面交易观察。",
    },
    "TrustTrade": {
        "title": "TrustTrade: Human-Inspired Selective Consensus Reduces Decision Uncertainty in LLM Trading Agents",
        "authors": "Minghan Li; Rachel Gonsalves; Weiyue Li; Sunghoon Yoon; Mengyu Wang",
        "published": "2026-03-23",
        "one_liner": "把 LLM 交易 Agent 的“统一信任偏差”形式化为风险源，并用选择性共识替代简单投票或平均。",
        "problem": "LLM Agent 很容易把检索到的材料都当成同等可信，尤其在新闻、指标、评论和历史价格同时输入时，模型会把噪声和事实混在一起。金融交易中这种 uniform trust 会导致错误信息被放大，进而表现为不稳定的风险收益特征。",
        "method": "TrustTrade 让多个独立 LLM Agent 形成候选信号，再按语义一致性、数值一致性和时间锚点给信号动态加权。它的思想不是让 Agent 越多越好，而是让互相独立的判断承担交叉验证作用，对分歧、弱依据和时间不一致的输入降权。",
        "data": "论文以高噪声市场环境下的 LLM 交易行为为主要评估场景，截图称其把极端风险-回报区间校准到更接近人类对齐的中风险-中回报区间。数据和实验更适合作为 Agent 信任机制研究，不应被视为单一策略 Alpha。",
        "metrics": "关注决策不确定性、风险-回报区间、共识一致性和交易表现稳定性。重要的是机制指标与交易指标同时出现：只提高语言一致性没有意义，必须观察这种一致性是否降低极端风险。",
        "innovation": "创新点是把人类投资流程里的选择性共识、交叉核验和经验加权转成可工程化的多 Agent 聚合机制。它为多 Agent 系统提供了比多数投票更细的信号质量刻画。",
        "limits": "共识机制可能过滤掉少数但正确的反转信号，也可能在所有 Agent 共享同一底层模型或同一检索语料时形成表面独立。实际落地需要对模型多样性、信息源独立性和少数派信号保留机制做压力测试。",
        "relation": "与 BlindTrade 共同回答“LLM 交易信号是不是记忆和偏见”的问题；与 Reliable Evaluation 的 CPH 关系密切，因为它把协调协议本身变成主要性能来源。",
        "practice": "适合作为研究工作台中的审议层：每个信号都记录来源、Agent 观点、共识得分、分歧理由和时间戳，避免把最终建议误认为单一模型的确定判断。",
    },
    "BlindTrade": {
        "title": "Can Blindfolded LLMs Still Trade? An Anonymization-First Framework for Portfolio Optimization",
        "authors": "Joohyoung Jeon; Hongchul Lee",
        "published": "2026-03-18",
        "one_liner": "用股票标识匿名化来区分真实市场理解与训练数据中的股票-收益记忆，是 LLM 交易评估里很关键的反事实设计。",
        "problem": "如果 LLM 看到 AAPL、TSLA、NVDA 等标识后表现好，不能确认它理解当前市场，也可能只是记住了训练语料中的公司叙事和历史收益关联。对交易 Agent 来说，这种记忆偏差会让回测看起来有效，实盘却不可迁移。",
        "method": "BlindTrade 匿名化股票标识，让 Agent 在不知道真实 ticker 的情况下输出评分，并结合 GNN 与 PPO-DSR 等策略模块做组合优化。框架还用负控制实验检验信号合法性，尝试排除靠名称、行业标签或历史名气获利的路径。",
        "data": "使用真实股票多资产数据并进行 2025 年 YTD 等实验。截图报告其 Sharpe 为 1.40±0.22，且在波动环境中表现较优，但在趋势性牛市中 Alpha 下降。",
        "metrics": "关注 Sharpe、稳定性、不同市场环境下的收益差异，以及匿名化前后性能是否仍然存在。若匿名化后表现完全消失，说明原信号更可能是记忆或标签偏差；若仍存在，则更接近可泛化结构。",
        "innovation": "创新在于把“遮蔽身份”作为评估协议，而不是只作为隐私处理。它让 LLM 交易研究从直接比较收益转向追问收益来源。",
        "limits": "匿名化能削弱 ticker 记忆，但不能完全消除训练数据中行业结构、价格路径或指数成分带来的隐含记忆。截图也指出牛市环境 Alpha 衰减，说明框架不自动保证跨制度有效。",
        "relation": "与 TrustTrade 的信任校准互补；与 Reliable Evaluation 的前瞻偏差、幸存者偏差议题一致；也为 AlphaCrafter 这类多 Agent 框架提供了验证模块。",
        "practice": "做 LLM 选股实验时，建议同时跑真实标识、匿名标识、随机映射标识和行业保留匿名四组实验，比较信号差异并记录所有映射哈希。",
    },
    "Expert Investment Teams": {
        "title": "Toward Expert Investment Teams: A Multi-Agent LLM System with Fine-Grained Trading Tasks",
        "authors": "Kunihiro Miyazaki; Takanobu Kawahara; Stephen Roberts; Stefan Zohren",
        "published": "2026-02-26",
        "one_liner": "把“投研团队角色扮演”推进到细粒度任务分解，说明 Agent 角色不是越宏观越好，而是越接近真实流程越可检验。",
        "problem": "早期多 Agent 交易系统常设 Analyst、Trader、Risk Manager 等粗角色，但角色边界含糊，信息传递噪声大，很难知道是哪个环节产生价值。论文认为，真实投研流程包含更细的任务单元，粗粒度提示会损害推理透明度和组合质量。",
        "method": "系统把投资分析拆成细粒度任务，让多个 Agent 分别完成信息提取、风险与收益展望、组合判断等子流程，再汇总形成交易决策。与粗粒度团队相比，细粒度设计更利于消融实验和错误定位。",
        "data": "论文围绕日本股票与 TOPIX 100 等场景评估，使用月度组合收益、风险展望和 10bps 单边交易成本设定。截图强调 fine-grained task design 比 coarse-grained baseline 有更高 Sharpe。",
        "metrics": "主要看 Sharpe、年化收益、波动、与指数的相关性、组合配置比例和消融后性能变化。值得注意的是论文不只报告 Agent 组合本身，还讨论与指数组合后的风险调整效果。",
        "innovation": "贡献在于把 Agent 系统评估对象从“几个角色”转成“任务组织方式”。这与软件工程中的 workflow design 类似：性能提升来自流程结构，而不只是更强模型。",
        "limits": "细粒度任务会增加 token 成本和延迟，且若各角色共用同一模型与相似上下文，独立性可能不足。任务拆分过细也可能让错误在链路中累积。",
        "relation": "与 HiveMind 的贡献归因可结合：一个负责设计任务图，一个负责量化各节点贡献；与 Reliable Evaluation 的协调优先假设直接呼应。",
        "practice": "若搭建内部投研 Agent，不应只写“你是分析师”。更稳妥的方法是把输入、输出、证据字段、拒答条件和下游消费者全部固定，并做逐节点消融。",
    },
    "HiveMind": {
        "title": "HiveMind: Contribution-Guided Online Prompt Optimization of LLM Multi-Agent Systems",
        "authors": "Yihan Xia; Taotao Wang; Shengli Zhang; Zhangyuhua Weng; Bin Cao; Soung Chang Liew",
        "published": "2025-12-06",
        "one_liner": "用 Shapley/DAG-Shapley 给多 Agent 工作流做贡献归因，再在线优化低贡献 Agent 的提示词。",
        "problem": "多 Agent 系统的问题不是只有“怎么协作”，还包括“谁真正贡献了收益”。如果无法度量单个 Agent 的边际贡献，系统只能靠人工调 prompt，容易把无效角色保留下来。",
        "method": "HiveMind 提出 CG-OPO：先用 Shapley value 度量 Agent 对最终任务的贡献，再用 DAG-Shapley 利用工作流 DAG 剪枝，减少组合枚举成本。被识别为低贡献的 Agent 会被自动提示优化。",
        "data": "论文在多 Agent 股票交易等场景验证，arXiv 摘要称 DAG-Shapley 在保持近似归因准确度时减少超过 80% 的 LLM 调用。",
        "metrics": "关注 Agent 贡献值、LLM 调用次数、交易任务收益、Sharpe、回撤和在线优化前后差异。它的关键指标不只是交易收益，还包括归因计算的可扩展性。",
        "innovation": "把合作博弈中的贡献归因引入 LLM 多 Agent 管理，并针对 DAG 工作流做成本优化。它让多 Agent 研究可以从“增加角色”转向“保留有贡献角色”。",
        "limits": "Shapley 归因依赖任务价值函数定义；金融场景中用 Sharpe 或收益作为价值函数时，短样本噪声会影响归因。在线 prompt 优化也可能过拟合近期市场。",
        "relation": "可作为 Expert Investment Teams 的诊断层，也能嵌入 AlphaCrafter 的 Agent 闭环，帮助判断 Miner、Screener、Trader 哪个环节贡献最大。",
        "practice": "在实盘前建议只把 HiveMind 用作研究诊断：定期冻结窗口，计算角色贡献和调用成本，把低贡献 Agent 降级为离线审查，而不是自动扩大权限。",
    },
    "OOM-RL": {
        "title": "OOM-RL: Out-of-Money Reinforcement Learning Market-Driven Alignment for LLM-Based Multi-Agent Systems",
        "authors": "Kun Liu; Liqun Chen",
        "published": "2026-04-13",
        "one_liner": "提出用真实资金损失作为 Agent 对齐信号，把金融市场视为无法被语言奖励轻易投机的外部约束。",
        "problem": "RLHF 和 RLAIF 的弱点是奖励模型可以被讨好或规避，执行型评估又可能被测试规避。论文认为，在高摩擦、非平稳的真实市场中，资本亏损是一种难以伪造的负反馈。",
        "method": "OOM-RL 把多 Agent 系统置于长期市场反馈中，通过资金损失迫使系统从高换手、迎合式输出转向严格测试驱动的 Agentic Workflow。论文强调 STDAW、RO-Lock 和至少 95% 代码覆盖约束矩阵。",
        "data": "论文报告 2024 年 7 月到 2026 年 2 月的 20 个月纵向研究。它既讨论交易系统，也讨论自主软件工程中的对齐问题，因此不应被简单归入普通策略回测。",
        "metrics": "关注阶段性 Sharpe、回撤、换手、代码覆盖、成熟阶段稳定性。arXiv 摘要称成熟阶段年化 Sharpe 达 2.06；这应视为作者系统的经验报告，需要独立复现。",
        "innovation": "把“经济后果”作为对齐信号，是截图中最激进的思想。它从奖励模型转向外部世界约束，提醒研究者不要只依赖语言偏好或离线 benchmark。",
        "limits": "真实资金反馈成本高、样本少、不可控因素多，且伦理和风控门槛远高于离线研究。市场亏损可以惩罚错误，但不能解释错误来源，也不能保证学习方向总是正确。",
        "relation": "与 PolyBench 的实时市场基准同样强调防污染和外部约束；与 Reliable Evaluation 的净成本、制度覆盖和交易成本意识高度相关。",
        "practice": "不应把 OOM-RL 直接理解为鼓励实盘烧钱训练。更现实的做法是把可验证损失函数、交易成本、滑点和代码覆盖作为纸面交易前的硬门槛。",
    },
    "SNAPO": {
        "title": "SNAPO: Smooth Neural Adjoint Policy Optimization for Optimal Control via Differentiable Simulation",
        "authors": "Dmitri Goloubentsev; Natalija Karpichina",
        "published": "2026-05-07",
        "one_liner": "把神经策略嵌入已知可微模拟器，用伴随法一次反传得到策略梯度和大量敏感度。",
        "problem": "动态规划在高维状态下指数爆炸，黑盒 RL 训练慢且缺乏敏感度。金融和能源等最优控制问题需要的不只是策略，还需要对输入、曲线、风险因子变化的敏感度解释。",
        "method": "SNAPO 使用平滑近似替代硬约束，把策略网络放进可微模拟器，通过伴随反向传播计算目标对参数和输入的精确梯度。复杂度关键是一次 reverse pass，而不是对每个风险因子做 bump-and-revalue。",
        "data": "论文展示天然气储存、养老金资产负债管理和制药流程控制三类任务。arXiv 摘要称天然气任务一分钟内训练，365 条远期曲线敏感度无额外逐项成本，养老金任务敏感度速度提升 6.5 到 200 倍。",
        "metrics": "关注目标值、训练时间、敏感度计算成本、与 DP/有限差分/黑盒 RL 的速度差异。对金融读者，最关键指标是敏感度的边际成本和可审计性。",
        "innovation": "范式从黑盒策略梯度转向白盒伴随微分。它不是只问策略能不能赚钱，而是问策略对市场输入、约束和风险因子如何响应。",
        "limits": "前提是模拟器可微且足够可信。对于限价订单簿、离散成交、队列位置等强离散微观结构，平滑近似可能产生偏差。",
        "relation": "与 MACE 的现实成本建模形成张力：SNAPO 需要可微结构，MACE 强调真实冲击模型；未来方向是把可微近似和真实执行约束结合。",
        "practice": "适合用于已知动力学较强的资产负债、库存、储能、养老金目标管理。若用于交易，应先验证模拟器误差，而不是只调神经策略。",
    },
    "MetaRL-GBWM": {
        "title": "A Meta Reinforcement Learning Approach to Goals-Based Wealth Management",
        "authors": "Sanjiv R. Das; Harshad Khadilkar; Sukrit Mittal; Daniel Ostrov; Deep Srivastav; Hungjen Wang",
        "published": "2026-05-04",
        "one_liner": "把元强化学习用于目标型财富管理，在大量 GBWM 问题上预训练，再对新客户/新目标快速适配。",
        "problem": "每个投资者的目标、资金流、风险偏好和时间约束都不同。传统方法常为每个问题单独求解，计算昂贵且难以实时服务大量客户。",
        "method": "论文把目标型财富管理形式化为序贯决策问题，在数千个 GBWM 问题上进行 MetaRL 预训练，让模型学习问题的元结构，再对新目标组合做零样本或少样本适配。",
        "data": "实验围绕多年度财富管理情景，投资者每年选择组合并决定满足哪些目标。截图称模型达到最优动态规划期望效用的 97.8%，推理阶段约 0.01 秒生成近最优策略。",
        "metrics": "关注相对 DP 的期望效用、推理速度、制度变化鲁棒性和适配效率。它不是高频交易论文，而是金融规划与资产配置的序贯控制论文。",
        "innovation": "证明预训练-微调范式可迁移到金融决策，而不是只用于语言或图像。关键在于任务分布设计，模型学到的是目标管理问题的结构，而不是某个市场历史。",
        "limits": "预训练问题分布与真实客户分布的偏移会影响泛化；若 GBWM 模拟假设过于理想，实盘适配可能失败。报告应强调它仍主要在模拟/建模环境中验证。",
        "relation": "与 SNAPO 同属从传统 DP 走向可扩展策略学习；与 Reliable Evaluation 共同提醒，样本效率和现实性之间存在权衡。",
        "practice": "在投顾系统中可先用于离线情景分析和目标可达性评估，并把每个建议的目标满足概率、约束违背和分布外距离展示给人类顾问。",
    },
    "MACE / Realistic Market Impact": {
        "title": "Realistic Market Impact Modeling for Reinforcement Learning Trading Environments",
        "authors": "Lucas Riera Abbade; Anna Helena Reali Costa",
        "published": "2026-03-30",
        "one_liner": "用 Almgren-Chriss 与平方根冲击定律重构 Gymnasium 交易环境，说明成本模型会改变 RL 算法排名。",
        "problem": "很多开源 RL 交易环境使用固定 bps 或忽略交易成本，Agent 会学习高换手、现实不可执行的策略。若环境成本错，算法排名和结论都可能错。",
        "method": "论文提出 MACE 环境套件，包含股票交易、保证金交易和组合优化，支持可插拔成本模型、永久冲击衰减和交易级日志。实验比较固定 10bps 成本与 Almgren-Chriss/平方根冲击模型。",
        "data": "使用 NASDAQ 100 股票池，评估 A2C、PPO、DDPG、SAC、TD3 等 DRL 算法。截图和原文摘要强调在真实冲击模型下，固定成本下表现最好的算法可能变差。",
        "metrics": "关注 OOS Sharpe、总收益、不同成本模型下算法排名、交易日志和冲击参数敏感性。论文摘要示例指出股票交易中 PPO 在固定成本下较优，但在 AC 模型下收益下降。",
        "innovation": "贡献不是提出新 RL 算法，而是提供更真实的环境和成本假设。它把“环境工程”上升为论文核心，因为环境决定策略学到什么。",
        "limits": "冲击模型参数校准困难，AC 和平方根模型仍是简化表达，难覆盖订单簿队列、隐含流动性和市场参与者反应。",
        "relation": "与 SNAPO 的可微模拟互补；与 Reliable Evaluation 的交易成本忽略批评一致，是评估 RL 交易论文时必须引用的基准思想。",
        "practice": "任何 RL 交易策略在报告前都应至少跑固定成本、非线性冲击、滑点压力和容量约束四组环境，否则收益结论容易被环境假设主导。",
    },
    "SBCA": {
        "title": "SBCA: Cross-Modal BERT-driven Actor-Critic for Multi-Asset Portfolio Optimization",
        "authors": "Jinfeng Pan; Jiahao Chen",
        "published": "2026-05-02",
        "one_liner": "用 BERT 文本语义和价格时序特征驱动 Actor-Critic，多资产组合优化中加入下行风险与换手惩罚。",
        "problem": "传统组合优化常依赖线性假设，很多 DRL 组合模型又只看价格序列，忽略文本情绪和实践交易约束。多模态信息如果不能与组合约束一起建模，容易变成噪声拼接。",
        "method": "SBCA 使用跨模态门控融合，把价格时间序列特征与金融文本语义特征结合，Actor-Critic 输出动态组合，并在奖励中嵌入下行风险和换手惩罚。",
        "data": "论文在 11 年美国股票多资产数据上实验，比较等权、买入持有和市场基准，另做消融和交易成本敏感性分析。",
        "metrics": "关注组合价值、年化收益、Sharpe、最大回撤、交易成本敏感性以及 Actor-Critic 与跨模态模块的消融贡献。",
        "innovation": "把跨模态 BERT 特征与 RL 组合控制放在同一端到端框架中，并显式把风险和换手约束写入奖励函数。",
        "limits": "BERT 文本特征的时点可得性、新闻覆盖偏差和文本来源质量需要严格记录；多模态融合机制可能提升指标，但解释性仍弱于规则化因子。",
        "relation": "连接 RL 交易与多模态预测两条线；可与 SEMF/Uni-FinLLM 比较“融合发生在特征层、策略层还是任务头层”。",
        "practice": "落地时必须为文本输入建立 visible_at、published_at、fetched_at 和去重规则，否则文本特征很容易引入前瞻偏差。",
    },
    "FactorEngine": {
        "title": "FactorEngine: A Program-level Knowledge-Infused Factor Mining Framework for Quantitative Investment",
        "authors": "Qinhong Lin; Ruitao Feng; Yinglun Feng; Zhenxin Huang; Yukun Chen; Zhongliang Yang; Linna Zhou; Binjie Fei; Jiaqi Liu; Yu Li",
        "published": "2026-03-17",
        "one_liner": "把因子表达从固定公式或神经黑盒提升到可执行程序，用知识注入缩小搜索空间。",
        "problem": "符号因子搜索表达能力有限，神经预测器可解释性差且容易过拟合。真正可用的因子应当可执行、可审计、可调参，并能在大规模搜索中保持计算可控。",
        "method": "FactorEngine 将因子视为程序级表达，分离逻辑修正与参数优化、LLM 引导方向搜索与贝叶斯超参搜索、LLM 使用与本地计算。它把非结构化财报等知识转成可执行因子程序的种子。",
        "data": "论文围绕量化投资因子挖掘任务评估 IC、ICIR、Rank IC/ICIR、年化收益和 Sharpe 等指标。截图称其显著高于 SOTA 预测和投资组合表现。",
        "metrics": "核心指标是 IC/ICIR、Rank IC/ICIR、AR/Sharpe、因子可执行率和搜索效率。程序级表达使每个候选因子的失败原因可以定位到语法、运行、数据或经济逻辑。",
        "innovation": "关键设计哲学是 separation of concerns：逻辑、参数、LLM、计算分别约束。这样既利用 LLM 的语义搜索能力，又避免让 LLM 直接控制所有计算。",
        "limits": "程序级空间更强也更危险，隐性未来函数、数据依赖链和高复杂度代码都可能引入前瞻偏差。需要沙箱、静态检查和严格数据接口。",
        "relation": "FactorEngine 是 AlphaCrafter 的潜在 Miner 组件，也是 Hubble 的程序级前身或对照：二者都把因子生成约束在可审计空间。",
        "practice": "内部因子平台应把每个候选因子的代码 AST、数据列、窗口参数、滞后规则、运行日志和验证结果一起归档，而不只保存最终公式。",
    },
    "Hubble": {
        "title": "Hubble: An LLM-Driven Agentic Framework for Safe, Diverse, and Reproducible Alpha Factor Discovery",
        "authors": "Runze Shi; Shengyu Yan; Yuecheng Cai; Chenxi Lv",
        "published": "2026-03-09",
        "one_liner": "用 AST 沙箱、白名单算子、双通道 RAG 和族群多样性约束，构建安全可复现的 LLM 因子发现框架。",
        "problem": "LLM 生成因子代码有运行时崩溃、非法数据访问、表达不可审计和候选因子同质化问题。纯公式搜索又容易局限在拥挤模板中。",
        "method": "Hubble 限制 LLM 只能生成安全子语言中的操作树，通过 AST 层白名单执行；一个通道检索历史有效因子，另一个通道检索金融理论文献；再用公式相似度惩罚和族群诊断鼓励多样性。",
        "data": "论文在约 500 只美股面板上三轮评估 104 个有效候选，截图和摘要都强调零运行时崩溃，顶部因子集中在 range、volatility、trend 家族。",
        "metrics": "使用 RankIC、Pearson IC、RankICIR、ICIR、bucket return、long-short spread、turnover、coverage、公式复杂度和 HAC 显著性等诊断。",
        "innovation": "把 LLM 因子发现从自由代码生成变成受控研究工作流。安全沙箱和双通道 RAG 让搜索既有历史经验又有理论约束。",
        "limits": "论文自己指出没有完整交易成本评估，候选因子仍需前向验证。RAG 也无法完全防止模型从预训练中吸收公开因子知识。",
        "relation": "与 FactorEngine 同属程序级因子生成；与 AlphaCrafter 连接后，可从因子候选生成进入制度筛选和组合执行。",
        "practice": "适合在研究环境做候选生成，但应强制把高分因子移入独立验证队列，执行净成本、容量、行业中性和多市场迁移测试。",
    },
    "SEMF": {
        "title": "Multimodal Forecasting for Commodity Prices Using Spectrogram-Based and Time Series Representations",
        "authors": "Soyeon Park; Doohee Chung; Charmgil Hong",
        "published": "2026-03-28",
        "one_liner": "把商品价格序列转成小波频谱图，用 ViT 捕捉频率结构，再与外生变量时序 Transformer 融合。",
        "problem": "金融时间序列既有趋势、周期、波动和噪声，也受宏观指标等外生变量影响。传统时序模型通常在时间域工作，容易忽略频率成分携带的预测信号。",
        "method": "SEMF 使用 Morlet 小波把目标序列转为频谱图，Vision Transformer 提取局部频率感知特征；外生变量由 Transformer 编码，最后通过双向交叉注意力整合。",
        "data": "实验面向多种商品价格预测任务，使用价格序列、宏观指标等外生变量。截图称其在多个商品预测任务上一致超过 7 个竞争基线。",
        "metrics": "关注预测误差、不同商品一致性、消融后频谱分支与时序分支贡献。对交易应用，还需进一步把预测误差转成可交易收益。",
        "innovation": "创新在于强调频率域信息：趋势偏低频，波动偏中频，噪声偏高频，不同频段可携带不同预测含义。",
        "limits": "频谱图特征可解释性有限，且只在商品数据上验证。频域优势是否能迁移到股票、外汇或链上数据，需要独立验证。",
        "relation": "与 Uni-FinLLM 同属多模态融合，但 SEMF 更专注时序和频率结构；与 Acoustic Camouflage 形成提醒：不是所有新增模态都会提高预测。",
        "practice": "使用时应先验证频域分支单独贡献，再做交易层回测。若预测改进无法覆盖滑点和换手，不应直接视为 Alpha。",
    },
    "Uni-FinLLM": {
        "title": "Uni-FinLLM: A Unified Multimodal Large Language Model with Modular Task Heads for Micro-Level Stock Prediction and Macro-Level Systemic Risk Assessment",
        "authors": "Gongao Zhang; Haijiang Zeng; Lu Jiang",
        "published": "2026-01-06",
        "one_liner": "用共享 Transformer 主干和模块化任务头统一金融文本、数值时序、基本面与视觉数据。",
        "problem": "金融机构既要做微观股票预测，也要做宏观系统性风险评估。现有模型常按任务孤立训练，难以利用不同尺度之间的关系。",
        "method": "Uni-FinLLM 采用共享主干、跨模态注意力和多任务优化，通过模块化任务头处理股票方向、信用风险、宏观预警等任务。",
        "data": "输入覆盖金融文本、数值时间序列、基本面和视觉数据。截图报告股票方向准确率 67.4% 对比基线 61.7%，信用风险 84.1% 对比 79.6%，宏观预警 82.3%。",
        "metrics": "关注分类准确率、风险识别率、宏观预警效果和多任务之间的互相促进或竞争。模块间竞争是截图中指出的主要局限之一。",
        "innovation": "它把金融多模态从单一任务模型推进到统一主干+任务头架构，提供了 Agent richer state representation 的可能。",
        "limits": "统一模型可能因任务冲突损害某些子任务；跨模态注意力机制复杂，解释某个预测由哪种模态驱动并不容易。",
        "relation": "可作为多 Agent 交易系统的状态表示层，也能为 SBCA 或 AlphaCrafter 的 Agent 提供更丰富输入。",
        "practice": "用于实盘前应逐任务做时点一致性、模态缺失、任务冲突和校准曲线检查，避免一个统一模型遮盖不同任务的失败模式。",
    },
    "History Rhymes": {
        "title": "History Rhymes: Macro-Contextual Retrieval for Robust Financial Forecasting",
        "authors": "Sarthak Khanna; Armin Berger; Muskaan Chopra; David Berghaus; Rafet Sifa",
        "published": "2025-11-12",
        "one_liner": "把宏观指标和新闻情感嵌入共享空间，为当前预测检索历史相似宏观制度时期。",
        "problem": "金融市场非平稳，结构性断点会让静态模型在 OOD 环境中失败。简单融合新闻与指标并不能告诉模型“当前更像历史上的哪个时期”。",
        "method": "论文提出 macro-contextual retrieval，把 CPI、失业率、收益率曲线、GDP 增速等宏观指标与金融新闻情感共同嵌入，检索历史类似制度期，并把检索结果用于预测。",
        "data": "实验包括股票和宏观相关预测场景。截图称 OOD 测试中 AAPL 达到 PF=1.18 和 Sharpe=0.95，而静态基线在制度转换下崩溃。",
        "metrics": "关注 OOD 表现、profit factor、Sharpe、检索质量和静态基线在制度变化下的退化程度。",
        "innovation": "创新在于把 RAG 从文本问答迁移到金融制度检索：检索对象不是文档事实，而是历史宏观上下文。",
        "limits": "检索质量依赖嵌入空间，若宏观变量选择不全或新闻情感滞后，可能检索到表面相似但机制不同的时期。",
        "relation": "与 Hubble 的双通道 RAG 思路相通；与 Reliable Evaluation 的制度覆盖要求相互支持。",
        "practice": "策略报告应展示当前窗口最相似的历史制度、相似度、当时市场表现和失败案例，而不是只给最终预测。",
    },
    "Acoustic Camouflage": {
        "title": "The Acoustic Camouflage Phenomenon: Re-evaluating Speech Features for Financial Risk Prediction",
        "authors": "Dhruvin Dungrani; Disha Dungrani",
        "published": "2026-04-16",
        "one_liner": "证明财报电话会中的声学特征融合可能降低尾部风险预测，提出 Acoustic Camouflage 边界条件。",
        "problem": "声学特征在情绪、压力和认知负荷识别中有效，但高管在财报电话会中经过媒体训练，可能通过语音调节隐藏认知负荷，使声学信号变成矛盾噪声。",
        "method": "论文用双流 late-fusion 架构比较声学流与 NLP 文本流，声学特征包括 pitch、jitter、hesitation 等，任务是预测尾部下行风险事件。",
        "data": "使用企业财报电话会议数据，将下行尾部事件作为成本敏感分类目标。截图和摘要给出 NLP 单模型召回率 66.25%，加入声学融合后降到 47.08%。",
        "metrics": "主要指标是尾部事件召回率，强调成本敏感风险预测中漏报比误报更严重。",
        "innovation": "它是多模态研究中的反例：更多模态不必然更好，尤其当新增模态受策略性行为影响时，会污染模型。",
        "limits": "研究范围集中在财报电话会和声学特征，不能否定所有语音或另类数据；结果可能受样本、事件定义和模型架构影响。",
        "relation": "与 SEMF、Uni-FinLLM 形成边界对照，提醒多模态 Agent 需要验证每个模态的边际贡献。",
        "practice": "任何新增另类数据进入策略前，都应做单模态、双模态、随机化和缺失模态实验；若融合降低尾部召回，应果断剔除或降权。",
    },
    "PolyBench": {
        "title": "PolyBench: Benchmarking LLM Forecasting and Trading Capabilities on Live Prediction Market Data",
        "authors": "Pu Cheng; Juncheng Liu; Yunshen Long",
        "published": "2026-04-03",
        "one_liner": "用 Polymarket 实时预测市场快照构造防污染基准，评估 LLM 语言流畅性与真实概率交易能力的差距。",
        "problem": "传统金融 LLM benchmark 容易被训练数据污染，也常缺少可交易市场价格。预测市场提供带时间戳、订单簿和新闻流的实时概率环境，更适合检验模型能否把信息转成收益。",
        "method": "PolyBench 收集 38,666 个二元预测市场、4,997 个事件的点时快照，同步 CLOB 状态与实时新闻，让 7 个 LLM 在同一时间锁定市场状态下输出预测并模拟执行。",
        "data": "数据来自 2026 年 2 月 6-12 日的实时市场，生成 36,165 个预测。时间窗口短但污染控制强。",
        "metrics": "使用方向准确率、Confidence-Weighted Return、APY、Sharpe 和订单簿执行模拟。摘要称只有 2/7 个模型实现正收益，MiMo-V2-Flash CWR 17.6%，Gemini-3-Flash CWR 6.2%。",
        "innovation": "核心是 contamination-proof design：模型无法提前看到未来事件，并且收益必须通过可交易价格实现。",
        "limits": "预测市场不同于股票市场，流动性、参与者结构和事件类型都有差异；一周窗口不足以覆盖制度变化。",
        "relation": "与 OOM-RL 一样强调外部经济反馈，与 QuantCode-Bench 一起把 LLM 能力评估从语言输出推进到交易后果。",
        "practice": "适合作为 LLM 金融推理基准，但用于策略研究时应补充更长窗口、更多市场和严格滑点容量假设。",
    },
    "QuantCode-Bench": {
        "title": "QuantCode-Bench: A Benchmark for Evaluating the Ability of Large Language Models to Generate Executable Algorithmic Trading Strategies",
        "authors": "Alexey Khoroshilov; Alexey Chernysh; Orkhan Ekhtibarov; Nini Kamkia; Dmitry Zmitrovich",
        "published": "2026-04-16",
        "one_liner": "评估 LLM 能否生成可执行算法交易策略，强调主要困难在交易语义和 API 操作，而不是普通语法。",
        "problem": "通用代码 benchmark 无法反映量化策略生成难度。策略代码必须符合金融逻辑、专用 API、历史数据执行和语义对齐，否则即使语法正确也不会产生有效交易。",
        "method": "QuantCode-Bench 设计多阶段评估管道：语法正确性、回测执行、交易存在性、语义对齐，并用 LLM judge 辅助判断策略是否符合题意。",
        "data": "基准任务围绕算法交易策略生成，评估现代 LLM 在不同约束下输出可运行策略的能力。",
        "metrics": "关注代码能否解析、能否运行、是否实际交易、交易逻辑是否符合需求、agentic 多轮设置相对单轮的提升。",
        "innovation": "它把“会写 Python”与“会写可交易策略”区分开。截图强调主要限制不是语法，而是交易逻辑操作化、API 使用和语义一致性。",
        "limits": "LLM judge 可能带来主观偏差；可执行策略不等于有效策略，benchmark 也不能替代真实样本外验证。",
        "relation": "与 FactorEngine/Hubble 的程序级因子生成直接相关，因为因子代码和策略代码都需要语法、安全、执行和语义多层验证。",
        "practice": "内部策略生成平台应把代码生成通过率拆成语法、数据接口、交易行为、风控约束、语义一致性五个门槛，不能只看回测收益。",
    },
    "Reliable Evaluation": {
        "title": "Toward Reliable Evaluation of LLM-Based Financial Multi-Agent Systems: Taxonomy, Coordination Primacy, and Cost Awareness",
        "authors": "Phat Nguyen; Thang Pham",
        "published": "2026-03-29",
        "one_liner": "提出多 Agent 金融系统评估分类法、协调优先假设和协调盈亏平衡价差，是整组论文的评估底座。",
        "problem": "LLM 金融多 Agent 论文增长很快，但缺少统一评价框架。许多论文存在前瞻偏差、幸存者偏差、回测过拟合、交易成本忽略和制度覆盖不足。",
        "method": "论文从架构、协调、记忆、工具四维分类 12 个多 Agent 系统和两个单 Agent 基线，并提出 Coordination Primacy Hypothesis 与 Coordination Break-even Spread。",
        "data": "它是 survey/方法论论文，汇总多 Agent 交易系统的报告指标和评估质量。截图列出五大普遍性评估失败。",
        "metrics": "关注污染控制、点时宇宙、滚动窗口、净成本收益、制度覆盖、协调成本、Agent 数量边际收益和价差门槛。",
        "innovation": "最大贡献是把“多 Agent 是否有价值”转成可检验问题：固定模型、数据和工具，只改变协调协议，观察净成本后是否仍有增量。",
        "limits": "协调优先假设仍需要严格实证验证；survey 受已发表论文质量限制，很多结果不可直接比较。",
        "relation": "本报告所有实践判断都应以它为底线。AlphaCrafter、TrustTrade、HiveMind 等都可被放入其分类法中重新评估。",
        "practice": "任何声称 Agent Alpha 的报告都应同时提供单 Agent、无协调、多 Agent、成本后和多制度窗口结果，并明确 CBS 是否覆盖实际价差。",
    },
}


TOPIC_ORDER = [
    "LLM Agent 与多智能体交易系统",
    "强化学习组合优化与交易",
    "自动化因子挖掘与 Alpha 发现",
    "多模态金融预测与另类数据",
    "评估基准与可靠性研究",
]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def load_rows() -> list[dict[str, str]]:
    rows = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
    by_key = {row["key"]: row for row in rows}
    normalized: list[dict[str, str]] = []
    for key, detail in DETAILS.items():
        row = {k: str(v) for k, v in by_key[key].items()}
        row["title"] = detail["title"]
        row["authors"] = detail["authors"]
        row["published"] = detail["published"]
        row["abs_url"] = row.get("abs_url") or f"https://arxiv.org/abs/{row['arxiv_id']}"
        row["pdf_url"] = row.get("pdf_url") or f"https://arxiv.org/pdf/{row['arxiv_id']}"
        row["report_section"] = {
            "LLM Agent 与多智能体交易系统": "第 3 章",
            "强化学习组合优化与交易": "第 4 章",
            "自动化因子挖掘与 Alpha 发现": "第 5 章",
            "多模态金融预测与另类数据": "第 6 章",
            "评估基准与可靠性研究": "第 7 章",
        }[row["topic"]]
        normalized.append(row)
    return normalized


def write_inventory(rows: list[dict[str, str]]) -> None:
    fields = [
        "key",
        "title",
        "topic",
        "arxiv_id",
        "authors",
        "published",
        "updated",
        "abs_url",
        "pdf_url",
        "pdf_file",
        "text_file",
        "pdf_status",
        "text_status",
        "image_refs",
        "confidence",
        "report_section",
        "categories",
    ]
    with (ROOT / "paper_inventory.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def md_link(row: dict[str, str]) -> str:
    return f"[{row['arxiv_id']}]({row['abs_url']})"


def note_for(row: dict[str, str]) -> str:
    d = DETAILS[row["key"]]
    return f"""# {row['key']}：论文学习笔记

- 题名：{row['title']}
- 作者：{row['authors']}
- 日期：{row['published']}
- arXiv：{md_link(row)}
- 主题：{row['topic']}
- 截图来源：{row.get('image_refs', '')}
- PDF 缓存路径（可重新下载）：`{row.get('pdf_file', '')}`
- 本地抽取文本：`{row.get('text_file', '')}`

## 一句话定位
{d['one_liner']}

## 研究问题
{d['problem']}

## 方法框架
{d['method']}

## 数据与实验
{d['data']}

## 指标与结果
{d['metrics']}

## 创新点
{d['innovation']}

## 局限性
{d['limits']}

## 与其他论文的关系
{d['relation']}

## 对实践的启发
{d['practice']}
"""


def write_notes(rows: list[dict[str, str]]) -> None:
    NOTES_DIR.mkdir(exist_ok=True)
    for row in rows:
        path = NOTES_DIR / f"{slugify(row['key'])}-{row['arxiv_id']}.md"
        path.write_text(note_for(row), encoding="utf-8")


def paper_block(row: dict[str, str], index: int) -> str:
    d = DETAILS[row["key"]]
    return f"""### {index}. {row['key']}：{row['title']}

**定位。** {d['one_liner']} 这篇论文在本报告中的作用不是提供一个可以直接照搬的交易策略，而是提供一个可讨论的技术构件：它回答了“量化 Agent 应该怎样组织、怎样验证、怎样约束”的一个具体侧面。原文入口为 arXiv:{md_link(row)}，PDF 可按清单重新下载，抽取文本已保留到交付目录，便于复查。

**研究问题。** {d['problem']} 从没有上下文的读者角度看，论文真正关心的是“传统金融机器学习假设在 Agent 时代哪里失效”。这些失效点包括非平稳、信息时点、角色协作、交易成本、任务分布、程序安全和评估污染。理解这个问题比记住模型名字更重要，因为同一模型换到不同市场后，首先失败的往往不是网络结构，而是问题设定。

**方法框架。** {d['method']} 需要注意，方法中的每个模块都隐含接口约束：输入是什么、是否点时可得、输出是否可执行、下游如何消费、失败时是否有拒绝路径。量化系统的工程风险通常来自这些接口没有固定，而不是来自论文里某个模块名字本身。

**实验与指标。** {d['data']} {d['metrics']} 报告采用保守口径：论文报告的数值只说明在作者设定的数据、窗口、成本和基准下成立，不能直接外推到实盘。读者应重点观察实验是否有样本外、是否净成本、是否多制度、是否包含可执行约束，以及是否有消融说明性能来自哪个模块。

**创新与边界。** {d['innovation']} 但边界同样关键：{d['limits']} 这也是为什么本报告把“评估基准与可靠性”单列一章。任何 Agent 或多模态模块，如果不能通过前瞻偏差、幸存者偏差、成本、制度和代码安全检查，都只能被视为研究候选。

**与论文网络的关系。** {d['relation']} 对实践而言，{d['practice']} 这条启发可以转化为一个最低要求：把论文里的技术点拆成可记录、可回放、可消融的结构化流程，再讨论收益。
"""


def build_report(rows: list[dict[str, str]]) -> str:
    by_topic = {topic: [r for r in rows if r["topic"] == topic] for topic in TOPIC_ORDER}
    lines: list[str] = []
    lines.append(f"# 量化 Agent 元年：QuantML 截图论文学习报告\n")
    lines.append(f"生成日期：{TODAY}\n")
    lines.append(
        "说明：本报告根据用户提供的小红书截图逐项抽取可见论文，并对可解析论文联网核验 arXiv 原文、下载 PDF、抽取文本后整理；仓库保留抽取文本和清单，PDF 作为可再下载缓存不纳入 Git。报告不构成投资建议，也不把论文回测结果视为可交易承诺。\n"
    )
    lines.append("## 目录\n")
    for item in [
        "1. 背景导读",
        "2. 论文全景与分类",
        "3. LLM Agent 与多智能体交易系统",
        "4. 强化学习组合优化与交易",
        "5. 自动化因子挖掘与 Alpha 发现",
        "6. 多模态金融预测与另类数据",
        "7. 评估基准与可靠性研究",
        "8. 技术依赖关系",
        "9. 未来研究方向",
        "10. 实践检查清单",
        "11. 术语表",
        "12. 逐篇论文附录",
    ]:
        lines.append(f"- {item}")
    lines.append("\n<!-- BODY_START -->\n")

    lines.append("""## 1. 背景导读

截图标题把 2026 年称为“量化 Agent 元年”，这句话的核心并不是说传统时间序列、深度学习或强化学习已经失效，而是说研究重心正在从“单一模型预测收益”转向“可持续运行的研究-评估-执行系统”。过去的量化 AI 论文常把任务定义为价格预测、收益预测或组合权重优化，模型结构是注意力、图网络、强化学习或多模态融合；而这一组论文更频繁地讨论 Agent、工具、记忆、代码、检索、共识、沙箱、交易成本和评估污染。换句话说，研究对象从模型本体扩展成了完整工作流。

要让没有上下文的读者理解这组论文，首先需要区分三个层次。第一层是信号层：模型是否能从价格、基本面、新闻、宏观、语音、频谱图或链上数据中提出有预测意义的特征。第二层是决策层：信号如何进入组合、如何受风险预算、换手、冲击成本和制度状态约束。第三层是系统层：多个 Agent 如何协作，谁负责发现，谁负责筛选，谁负责执行，谁负责复盘，谁对错误负责，如何避免一个语言模型把幻觉包装成交易建议。截图中的六大方向基本沿着这三层展开。

这组论文的共同背景是金融市场非平稳。非平稳意味着过去的有效关系会衰减、反转或只在特定制度中存在。传统机器学习可以通过滚动训练、正则化、交叉验证和样本外测试缓解一部分问题，但当 LLM 进入量化流程后，风险变复杂了。LLM 可能记住公开历史叙事，可能在检索结果中混入未来信息，可能生成表面合理但无法执行的代码，也可能在多 Agent 会话中形成回声室。于是，论文不再只问“模型准确率高不高”，而开始问“信号是不是来自合法信息”“代码是不是可执行”“协作是不是产生净增益”“收益是不是扣除成本后仍存在”。

从工程角度看，Agent 化的真正价值不是让模型替代研究员拍脑袋下单，而是让研究流程可组合。一个合理的量化 Agent 工作台应当能完成候选因子生成、数据可得性检查、表达式安全审计、回测、基准对照、报告、信号日志、人工复核和纸面交易观察。截图里的 AlphaCrafter、FactorEngine、Hubble、QuantCode-Bench 和 Reliable Evaluation 分别覆盖了这些环节中的不同接口。它们共同说明，未来的竞争可能不只是单个预测模型的竞争，而是研究工厂的流程质量竞争。

本报告采取保守读法。凡是论文报告的收益、Sharpe、CWR 或准确率，均只视为作者设定中的实验结果；凡是涉及真实资金、Agent 自主执行或 LLM 生成代码，均需要额外风险约束。尤其在 Open Composer 的产品规则下，真实券商写入和实盘自动交易不属于本报告范围。报告的目标是学习论文思想、提炼技术关系和形成研究检查清单，而不是给出任何可直接交易的策略。
""")

    lines.append("""## 2. 论文全景与分类

附件截图声称从数百篇量化论文中筛出 61 篇高水平论文，主题覆盖 LLM 多 Agent 交易、强化学习组合优化、自动化因子挖掘、多模态预测、评估基准等方向。经截图逐页抽取和联网搜索，本报告可明确识别并核验 19 篇带 arXiv 原文的论文。没有找到公开可验证的完整 61 篇清单，因此本报告不臆造其余论文；所有结论只覆盖截图中可见且可解析的论文。

这 19 篇论文可以分成五组。第一组是 LLM Agent 与多智能体交易系统，包括 AlphaCrafter、TrustTrade、BlindTrade、Expert Investment Teams、HiveMind 和 OOM-RL。它们讨论 Agent 如何分工、如何形成共识、如何处理记忆偏差、如何在线优化提示、如何把市场损失转成对齐信号。第二组是强化学习组合优化与交易，包括 SNAPO、MetaRL-GBWM、MACE 和 SBCA。它们关注序贯决策、可微模拟、目标型财富管理、真实市场冲击和多模态 Actor-Critic。第三组是自动化因子挖掘，包括 FactorEngine 和 Hubble，并与 AlphaCrafter 的 Miner 形成强关联。第四组是多模态预测，包括 SEMF、Uni-FinLLM、History Rhymes 和 Acoustic Camouflage。第五组是评估基准与可靠性，包括 PolyBench、QuantCode-Bench 和 Reliable Evaluation。

从时间线上看，截图里的论文集中在 2025 年 11 月到 2026 年 5 月。这个时间段的特点是 LLM Agent 论文迅速增多，同时传统 RL 与多模态方向开始补上“现实性”和“可验证性”。例如 MACE 并没有提出新的 RL 算法，而是说明成本模型足以改变算法排名；PolyBench 不只评估语言预测，还把预测放入实时订单簿执行；QuantCode-Bench 不只看代码语法，而是检查是否真的产生交易。也就是说，研究质量的门槛从模型指标转向系统指标。

如果用“可实盘迁移难度”排序，评估类论文最容易转化为内部标准，因为它们主要定义检查项；因子挖掘类论文可转化为研究工具，但必须加沙箱、数据时点和成本评估；多模态预测类论文需要最严格的数据治理，因为新闻、语音、视觉和宏观数据都可能带来前瞻或选择偏差；多 Agent 执行类论文最接近交易流程，但风险最高，因为每增加一个 Agent 就增加一次解释、通信、调用成本和错误传播路径。

本报告后文不按截图顺序机械复述，而按技术栈组织。每章先解释该方向要解决的问题，再逐篇解读核心论文，最后给出横向比较和实践边界。这样读者可以把论文看成一个系统地图：Agent 提出问题，因子挖掘生成候选，多模态模型丰富状态，RL/最优控制做决策，评估基准决定哪些结果可信。

### 可核验论文清单
""")
    for topic in TOPIC_ORDER:
        lines.append(f"\n**{topic}**")
        for row in by_topic[topic]:
            lines.append(f"- {row['key']}：{row['title']}，arXiv:{md_link(row)}。")

    lines.append("""\n## 3. LLM Agent 与多智能体交易系统

这一方向是截图中占比最高的集群。它的底层问题是：如果一个 LLM 可以阅读财报、新闻、价格、宏观和历史策略，那么多个 LLM 是否能像投研团队一样协作，并稳定产生比单模型更好的交易决策？这不是一个简单的“多模型投票”问题。金融任务里，错误可能来自事实检索、时间错位、策略逻辑、风险约束、执行成本或模型记忆；多 Agent 只会增加一个新的风险源：通信和协调。

多 Agent 交易系统的第一条主线是角色分工。Expert Investment Teams 强调细粒度任务拆分比粗粒度角色更有效，AlphaCrafter 进一步把角色映射到 Miner、Screener、Trader 的交易生命周期。第二条主线是共识与信任。TrustTrade 指出 LLM 容易对所有输入统一信任，因此需要选择性共识；BlindTrade 则通过匿名化检验模型是否真的理解市场而不是记住 ticker。第三条主线是贡献归因和在线改进。HiveMind 用 Shapley/DAG-Shapley 找出哪个 Agent 有贡献，并优化低贡献提示。第四条主线是外部约束。OOM-RL 把真实资金损失视为对齐信号，提醒我们语言奖励和离线测试都可能被规避。

这些论文的共同启示是，Agent 数量本身不是优势。一个由七个相同底层模型、相同检索语料和相同提示风格组成的系统，可能只是把同一个偏差重复七遍。多 Agent 的价值来自异质信息、明确任务边界、可度量贡献、可追溯证据和净成本后仍存在的增量。如果没有这些条件，所谓“投研团队”只是更昂贵的单模型。
""")
    for i, row in enumerate(by_topic["LLM Agent 与多智能体交易系统"], 1):
        lines.append(paper_block(row, i))
    lines.append("""### 3.7 横向比较：从单 Agent 到全栈 Multi-Agent

AlphaCrafter 代表“全栈闭环”，把因子发现、制度筛选和交易执行连起来；Expert Investment Teams 代表“角色细化”，把投研流程拆成更小任务；TrustTrade 代表“选择性共识”，解决信息可信度；BlindTrade 代表“反事实验证”，解决记忆偏差；HiveMind 代表“贡献归因”，解决哪个 Agent 有用；OOM-RL 代表“外部对齐”，把真实损失或成本作为反馈。它们并非互斥，而像一个系统的不同层次。

如果要构建一个研究级多 Agent 系统，较稳妥的组合不是直接让 AlphaCrafter 下单，而是把 BlindTrade 的匿名化、TrustTrade 的共识得分、HiveMind 的贡献归因和 Reliable Evaluation 的评估清单嵌入 AlphaCrafter 的每个阶段。Miner 生成候选后先做匿名和前瞻检查，Screener 只接受通过点时验证的因子，Trader 只在成本后风险预算内生成纸面信号，复盘器再把收益和错误结构反馈给贡献归因模块。

最危险的误读是把多 Agent 当作提高收益的捷径。多 Agent 更像提高研究流程表达能力的工具，它同样会放大成本、延迟和错误。真正值得研究的是协调协议的边际收益是否超过边际成本，这正是 Reliable Evaluation 提出的 Coordination Break-even Spread 思想。
""")

    lines.append("""## 4. 强化学习组合优化与交易

强化学习在量化交易中长期存在一个悖论：它天然适合序贯决策，但现实交易环境太复杂，导致很多实验在简化环境中有效、在真实执行中失效。截图中的 RL 论文不再只展示 DQN、PPO、A2C、SAC、DDPG 或 TD3 谁更强，而是关注环境、成本、敏感度、任务分布和多模态状态。

SNAPO 走的是可微模拟路线：如果环境动力学已知或可近似可微，就可以用伴随法一次反传得到大量敏感度。MetaRL-GBWM 走的是任务分布路线：在许多财富管理问题上预训练，让模型学习目标型投资的元结构。MACE 走的是环境现实性路线：把 Almgren-Chriss 和平方根冲击写入 Gymnasium 交易环境，证明成本模型会改变算法排名。SBCA 则把价格时序与文本语义结合，用 Actor-Critic 做多资产组合优化。

这组论文提醒我们，RL 策略的核心不是“用了哪个算法”，而是状态、动作、奖励、环境、成本和约束是否真实。奖励函数如果没有下行风险和换手惩罚，Agent 可能学到高杠杆高换手；环境如果没有市场冲击，Agent 可能学到现实中无法成交的策略；任务分布如果只覆盖模拟客户，MetaRL 在真实客户上可能失效。
""")
    for i, row in enumerate(by_topic["强化学习组合优化与交易"], 1):
        lines.append(paper_block(row, i))
    lines.append("""### 4.5 横向比较：样本效率、现实性与可解释性的三角

SNAPO 的优势是敏感度和速度，但要求可微信息；MACE 的优势是现实成本，但模型更难优化；MetaRL-GBWM 的优势是快速适配，但依赖预训练任务分布；SBCA 的优势是多模态状态，但引入文本数据治理问题。四者构成一个三角：样本效率、现实性和可解释性很难同时最大化。

对交易系统而言，最重要的不是在论文表格中选择最高 Sharpe 的算法，而是把环境假设写清楚。一个策略在固定 10bps 成本下表现最好，在非线性冲击模型下可能变差；一个策略在可微模拟器中可解释性强，在离散订单簿中可能出现误差。研究流程应把环境版本、成本模型、冲击参数、行动空间和奖励项作为可审计配置，而不是散落在代码里。
""")

    lines.append("""## 5. 自动化因子挖掘与 Alpha 发现

自动化因子挖掘是量化研究最容易被 LLM 改造的环节之一，因为它既需要金融直觉，又需要程序表达和大规模搜索。传统人工因子依靠研究员提出经济假设，遗传编程依靠预设算子组合，深度学习依靠端到端表示。LLM 带来的新能力是从文本、财报、论文、历史因子和代码模式中生成候选表达，但这也带来安全与前瞻风险。

FactorEngine 和 Hubble 的共同点是：它们都不让 LLM 自由写任意代码。FactorEngine 把因子提升为程序级表达，同时分离逻辑修正、参数优化、LLM 搜索和本地计算；Hubble 更强调 AST 沙箱、白名单算子、双通道 RAG 和候选家族多样性。AlphaCrafter 则把这类因子发现能力放进更大的 Agent 闭环中。

因子挖掘方向的关键不是找到一个高 IC 因子，而是建立候选生成、审计、验证、去拥挤、成本估计和前向监控的流水线。LLM 让搜索空间扩大，但也让隐藏未来函数、数据依赖链、复杂度过高和语义不一致更常见。真正有价值的系统必须能解释每个因子的输入列、滞后规则、计算窗口、经济含义和失败原因。
""")
    for i, row in enumerate(by_topic["自动化因子挖掘与 Alpha 发现"], 1):
        lines.append(paper_block(row, i))
    lines.append("""### 5.3 横向比较：FactorEngine、Hubble 与 AlphaCrafter

FactorEngine 更像“程序级因子矿机”，Hubble 更像“安全可复现的 LLM 因子实验室”，AlphaCrafter 更像“把因子矿机接入交易闭环的全栈系统”。三者的关系可以理解为从候选生成到候选筛选再到组合执行的逐层扩展。FactorEngine 强调表达能力，Hubble 强调安全与多样性，AlphaCrafter 强调持续反馈和制度自适应。

如果没有 Hubble 式沙箱，FactorEngine 式程序空间可能过强，生成难以审计的复杂代码；如果没有 FactorEngine 式知识注入，Hubble 的安全子语言可能表达不足；如果没有 AlphaCrafter 式执行反馈，因子挖掘容易停留在离线高分候选。一个成熟系统应当把三者组合，但每一层都需要独立验收，而不是让最终回测收益掩盖中间缺陷。
""")

    lines.append("""## 6. 多模态金融预测与另类数据

多模态方向的核心诱惑是：金融市场有大量非价格信息，文本、语音、图像、宏观指标、频谱图、链上数据和订单簿都可能补充价格序列。但这组论文给出的结论并不是“模态越多越好”。SEMF 和 Uni-FinLLM 展示了多模态融合的潜力，History Rhymes 展示了宏观上下文检索的价值，Acoustic Camouflage 则明确指出声学特征可能伤害尾部风险预测。

理解多模态，必须区分“信息量”和“可交易信息量”。一个模态可能包含信息，但信息发布时间、可得性、覆盖率、噪声、策略性操纵和交易成本都会影响其可交易价值。财报电话会的声学特征可能被高管训练和媒体策略污染；新闻情感可能在价格中已被快速反映；宏观数据有发布延迟和修订；视觉或频谱图特征可能提高预测误差指标却无法覆盖换手成本。

因此，本报告把多模态论文分成三类：结构增强型，如 SEMF 的频谱图；统一表示型，如 Uni-FinLLM；上下文检索型，如 History Rhymes；边界反例型，如 Acoustic Camouflage。真正的实践结论是：每个新增模态都必须证明边际贡献，并在缺失、延迟、噪声和策略性行为下做压力测试。
""")
    for i, row in enumerate(by_topic["多模态金融预测与另类数据"], 1):
        lines.append(paper_block(row, i))
    lines.append("""### 6.5 横向比较：什么时候融合有效，什么时候有害

SEMF 之所以可能有效，是因为频域分解与金融时序的结构假设匹配：趋势、波动和噪声可能分布在不同频段。History Rhymes 之所以可能有效，是因为宏观制度相似性本身就是金融预测的重要上下文。Uni-FinLLM 之所以有价值，是因为统一表示能让不同尺度任务共享信息。Acoustic Camouflage 之所以失败，是因为新增模态受到策略性行为影响，融合后让模型接收了矛盾噪声。

这给多模态研究一个简单但严格的标准：新增模态必须满足点时可得、经济机制合理、单模态有效、融合后边际改善、缺失时可降级、交易后仍有效。缺少任一项，模态融合都可能只是提高论文复杂度，而不是提高策略质量。
""")

    lines.append("""## 7. 评估基准与可靠性研究

评估类论文是本报告最重要的底座。没有可靠评估，Agent、RL、因子和多模态论文都可能被漂亮指标误导。PolyBench 解决实时预测市场中的污染问题，QuantCode-Bench 解决策略代码生成的可执行性和语义问题，Reliable Evaluation 则系统总结 LLM 金融多 Agent 的评估失败模式。

金融 AI 评估至少需要五条底线：第一，信息必须点时可得，不能让模型看到未来。第二，股票池必须点时构成，避免幸存者偏差。第三，回测应滚动窗口或多制度覆盖，不能只选有利年份。第四，收益必须扣除佣金、滑点、冲击和资金成本。第五，系统复杂度必须有对照，证明多 Agent 或多模态的边际贡献超过成本。截图里 Reliable Evaluation 对这些问题有集中归纳。
""")
    for i, row in enumerate(by_topic["评估基准与可靠性研究"], 1):
        lines.append(paper_block(row, i))
    lines.append("""### 7.4 横向比较：从语言能力到交易后果

PolyBench 的重点是模型能不能在实时市场状态下把概率判断转为收益；QuantCode-Bench 的重点是模型能不能生成可执行并符合语义的策略代码；Reliable Evaluation 的重点是多 Agent 系统声称的收益是否能在净成本、多制度和无污染条件下成立。三者共同把评估从“输出看起来合理”推进到“后果可验证”。

这对所有量化 Agent 研究都是约束。一个 Agent 可能能写出漂亮报告，但 PolyBench 会问它是否能在时间锁定市场中赚钱；它可能能写出代码，但 QuantCode-Bench 会问代码是否执行、是否交易、是否符合题意；它可能能组织多个角色，但 Reliable Evaluation 会问协调协议是否真的带来净增益。只有通过这些问题，Agent 才能从演示走向研究资产。
""")

    lines.append("""## 8. 技术依赖关系

把 19 篇论文放在同一张依赖图上，可以看到几条清晰路径。第一条是 LLM Agent 到因子挖掘：AlphaCrafter 的 Miner 可以调用 FactorEngine 或 Hubble，后两者生成可执行或安全受限的因子候选。第二条是 LLM Agent 到评估基准：TrustTrade、BlindTrade、HiveMind 和 Expert Investment Teams 都需要 Reliable Evaluation 的分类法和成本意识，否则很难判断协调是否真实有效。第三条是 RL 交易到评估基准：MACE 为 RL 提供真实成本环境，SNAPO 和 MetaRL-GBWM 提供样本效率和敏感度路线，但都需要成本、制度和模拟误差检查。第四条是多模态到 Agent：Uni-FinLLM 和 History Rhymes 可以为 Agent 提供 richer state representation，SEMF 和 SBCA 可以提供频域或文本状态，Acoustic Camouflage 则提醒 Agent 不应盲目相信新增模态。

依赖关系还揭示了一个重要方向：未来系统可能从单点模型演变为“量化工厂”。在这个工厂里，因子生成器持续产出候选，沙箱执行器拒绝非法表达，评估器做点时和净成本验证，多 Agent 协调器整合证据，风险控制器决定是否进入纸面交易，复盘器记录失效原因。每个模块都可以由不同论文中的技术实现，但系统级可靠性取决于接口和日志，而不是某个模块的论文指标。

技术融合有三种高风险路径。第一是把 LLM 生成代码直接接入回测，不做 AST 限制和数据列审计。第二是把多模态特征直接喂给交易 Agent，不做 visible_at、published_at、fetched_at 和缺失模态测试。第三是把多 Agent 共识当成置信度，不验证 Agent 独立性和共识成本。所有这些路径都可能产生看似智能、实则不可复现的结果。
""")

    lines.append("""## 9. 未来研究方向

第一，协调协议需要严格消融。Reliable Evaluation 提出的协调优先假设很有启发，但还需要固定底层模型、工具、数据和成本，只改变协调拓扑，观察收益、延迟和成本变化。未来论文应报告单 Agent、无协调多 Agent、选择性共识、多轮会议、DAG 工作流等多个版本，而不是只展示最终系统。

第二，Agent 记忆需要反事实验证。BlindTrade 说明 ticker 匿名化是必要步骤，但还不够。未来应测试行业匿名、随机名称、历史窗口打乱、新闻替换、特征滞后和负控制资产，判断 LLM 到底使用了什么信息。Agent 的“记忆”也应区分短期上下文、检索库、长期经验和预训练知识。

第三，因子代码生成需要静态和动态双重审计。FactorEngine 和 Hubble 已经给出程序级表达与沙箱方向，但未来要更严格处理隐性未来函数、滚动窗口边界、复权数据、行业分类重算和缺失值填充。每个因子都应有机器可读的 provenance。

第四，RL 环境应从固定成本升级为可校准市场冲击。MACE 证明成本模型能改变算法排名，未来工作需要把成交量、波动、价差、订单簿深度、冲击衰减和交易容量纳入环境，并报告策略对这些参数的敏感性。SNAPO 的可微路线也值得扩展到半连续、半离散执行环境。

第五，多模态融合要从“拼接”走向“模态价值审计”。SEMF、Uni-FinLLM 和 History Rhymes 都显示多模态有潜力，但 Acoustic Camouflage 说明新增模态会带来噪声。未来论文应报告每个模态的边际信息、延迟、覆盖、缺失、操纵风险和融合失败案例。

第六，实时防污染 benchmark 会变得更重要。PolyBench 的价值在于时间锁定和真实市场执行，QuantCode-Bench 的价值在于可执行策略生成。未来标准应同时覆盖实时数据、代码执行、成本后收益、语义一致性和长期复现。
""")

    lines.append("""## 10. 实践检查清单

如果要把这组论文转化为内部研究流程，建议按以下顺序执行。首先建立论文级资产库：每篇论文的题名、arXiv、PDF、抽取文本、核心方法、数据和局限都要结构化保存。其次建立数据时点规范：所有新闻、财报、宏观、价格、音频、预测市场快照都必须记录 visible_at、published_at、fetched_at、source 和 input hash。再次建立代码与因子沙箱：LLM 生成的任何表达式必须经过 AST 或 DSL 白名单、数据列审计、窗口边界检查和运行日志记录。然后建立评估基准族：同标的买入持有、等权、市场代理、行业代理、现金代理、事后最佳标的都应出现，且报告净成本收益。最后建立纸面交易前闸门：只有通过点时验证、滚动窗口、多制度、净成本、容量、风控和人工复核的信号，才进入纸面观察。

对多 Agent 系统，实践检查还要包括 Agent 数量、角色独立性、通信拓扑、每轮 token 成本、延迟、失败重试、共识阈值、分歧处理和贡献归因。对多模态系统，检查项包括模态发布时间、缺失率、采集成本、版权许可、单模态效果、融合消融和噪声注入。对 RL 系统，检查项包括动作空间、奖励项、成本模型、冲击参数、交易容量、环境版本和随机种子。对 benchmark 系统，检查项包括数据污染、题目泄漏、LLM judge 偏差、代码执行沙箱和语义一致性。

最重要的实践原则是：研究通过不等于 Alpha，通过回测不等于可交易，通过 Agent 共识不等于事实，通过多模态融合不等于信息增量，通过代码可运行不等于策略正确。每个“等号”都需要单独验证。
""")

    lines.append("""## 11. 术语表

- **Agent**：在给定角色、工具和记忆下执行任务的 LLM 或模型驱动组件。金融场景中 Agent 必须有明确输入、输出和权限边界。
- **Multi-Agent**：多个 Agent 通过流程或通信协议协作。优势来自异质信息和流程结构，风险来自成本、延迟和错误传播。
- **统一信任偏差**：LLM 把不同来源信息都当成同等可信的倾向，TrustTrade 将其视为交易 Agent 的核心风险。
- **匿名化验证**：BlindTrade 使用的反事实评估方法，用于判断模型是否依赖 ticker 记忆。
- **DAG-Shapley**：HiveMind 的贡献归因近似方法，利用工作流 DAG 结构降低 Shapley 计算成本。
- **可微模拟**：SNAPO 使用的思想，使策略和环境能通过反向传播计算梯度和敏感度。
- **市场冲击**：交易本身对价格产生的影响，MACE 强调忽略冲击会扭曲 RL 结论。
- **IC/RankIC**：因子值与未来收益之间的相关性及秩相关性，是因子研究常用指标。
- **RAG**：检索增强生成。Hubble 用双通道 RAG 检索历史因子和金融理论，History Rhymes 用宏观上下文检索历史制度。
- **前瞻偏差**：策略使用了当时不可获得的信息。所有 LLM、新闻、多模态和因子代码都容易引入该风险。
- **幸存者偏差**：只用当前仍存在的股票或基金回测，忽略退市或失败样本。
- **净成本收益**：扣除佣金、滑点、价差、市场冲击和资金成本后的收益，是评估交易策略的最低要求。
- **Coordination Break-even Spread**：Reliable Evaluation 提出的思想，用于判断多 Agent 协调带来的信号增益是否覆盖实际交易价差和协调成本。
""")

    lines.append("## 12. 逐篇论文附录\n")
    for i, row in enumerate(rows, 1):
        lines.append(paper_block(row, i))

    lines.append("\n<!-- BODY_END -->\n")
    lines.append("## 参考文献\n")
    for row in rows:
        lines.append(f"- {row['authors']}. *{row['title']}*. arXiv:{md_link(row)}, {row['published']}.")
    return "\n".join(lines)


def write_source_extraction(rows: list[dict[str, str]]) -> None:
    text = f"""# 附件截图抽取与消歧记录

生成日期：{TODAY}

## 覆盖范围

用户附件共有 38 张截图，来自小红书/QuantML 帖子《量化Agent元年：我读了上百篇论文后，看到的六大技术前沿》。截图显示原帖声称筛选 61 篇论文，时间跨度约 2025-11 至 2026-05，主题包含 LLM Agent、多 Agent 交易、强化学习组合优化、自动化因子挖掘、多模态预测、评估基准等。

经逐图阅读和联网检索，本次可明确解析并核验 arXiv 原文的论文为 19 篇。未找到公开可访问的完整 61 篇清单，因此本交付不补造未见论文。

## 可见主题结构

- 研究全景：月度发表趋势、主题分布、关键词频率。
- LLM Agent 与多智能体交易系统：AlphaCrafter、TrustTrade、BlindTrade、Expert Investment Teams、HiveMind、OOM-RL。
- 强化学习组合优化与交易：SNAPO、MetaRL-GBWM、MACE/Realistic Market Impact、SBCA。
- 自动化因子挖掘与 Alpha 发现：FactorEngine、Hubble。
- 多模态金融预测与另类数据：SEMF、Uni-FinLLM、History Rhymes、Acoustic Camouflage。
- 评估基准与可靠性：PolyBench、QuantCode-Bench、Toward Reliable Evaluation。

## 论文清单

"""
    for row in rows:
        text += f"- {row['key']}：{row['title']}，arXiv:{row['arxiv_id']}，截图位置 {row.get('image_refs', '')}，置信度 {row.get('confidence', '')}。\n"
    text += """
## 消歧说明

- OpenClaw 在截图中作为背景词出现，没有在附件中看到完整题名、作者或 arXiv ID，本次不作为独立论文处理。
- MACE 是截图中方法/环境缩写，对应论文题名为 *Realistic Market Impact Modeling for Reinforcement Learning Trading Environments*。
- SBCA、SNAPO、OOM-RL、HiveMind、Hubble、PolyBench 在 arXiv API 中部分摘要字段不完整，本次以 arXiv 页面和 PDF 正文题名为准。
- 由于截图并非原帖全文，未能确认“61 篇”完整清单。本报告透明标注该限制。
"""
    (ROOT / "source_post_extraction.md").write_text(text, encoding="utf-8")


def write_claims(rows: list[dict[str, str]]) -> None:
    claim_rows = [
        ("量化 Agent 的核心变化是从单模型预测转向研究-评估-执行系统。", "AlphaCrafter; Reliable Evaluation; QuantCode-Bench"),
        ("多 Agent 数量本身不是优势，协调协议和贡献归因更重要。", "Reliable Evaluation; HiveMind; Expert Investment Teams"),
        ("LLM 交易信号需要检验 ticker 记忆和统一信任偏差。", "BlindTrade; TrustTrade"),
        ("真实交易成本和市场冲击会改变 RL 算法排序。", "MACE / Realistic Market Impact"),
        ("可微模拟能提升敏感度计算效率，但依赖模拟器可微且可信。", "SNAPO"),
        ("MetaRL 可以把预训练-适配范式用于目标型财富管理，但分布偏移是关键风险。", "MetaRL-GBWM"),
        ("程序级因子生成需要沙箱、数据审计和前向验证。", "FactorEngine; Hubble"),
        ("多模态融合不是必然有效，声学特征在财报电话会中可能降低尾部风险召回。", "SEMF; Uni-FinLLM; Acoustic Camouflage"),
        ("宏观上下文检索可缓解制度转换下的 OOD 预测失败。", "History Rhymes"),
        ("LLM benchmark 应从语言输出走向时间锁定、可执行和净成本后结果。", "PolyBench; QuantCode-Bench; Reliable Evaluation"),
    ]
    by_key = {row["key"]: row for row in rows}
    text = "# 关键结论可追溯表\n\n| 结论 | 来源论文 |\n|---|---|\n"
    for claim, keys in claim_rows:
        links = []
        for key in [k.strip() for k in keys.split(";")]:
            row = by_key[key]
            links.append(f"[{key}]({row['abs_url']})")
        text += f"| {claim} | {', '.join(links)} |\n"
    (ROOT / "claims_traceability.md").write_text(text, encoding="utf-8")


def write_unresolved() -> None:
    text = """# 未完全解析或仅作上下文处理的提及

- OpenClaw：截图第 2 页文字提到“在 openclaw 之后，LLM Agent 和多模态融合迎来爆发式增长”。附件中未出现完整论文题名、作者、日期或 arXiv ID；联网检索未确认与本帖对应的一手论文条目。因此本报告只把 OpenClaw 作为背景上下文，不纳入 19 篇核心论文清单。
- “61 篇高水平论文”：截图说明原帖筛选 61 篇，但附件没有完整论文列表。联网检索未发现公开完整清单。本报告只覆盖截图中可见且可核验的论文。
- “Graph NN”“Factor Mining”等关键词：截图中作为关键词频率或主题标签出现，不必然对应单篇论文。
"""
    (ROOT / "unresolved_mentions.md").write_text(text, encoding="utf-8")


def write_bib(rows: list[dict[str, str]]) -> None:
    entries = []
    for row in rows:
        key = slugify(row["key"]).replace("-", "")
        year = row["published"][:4]
        authors = " and ".join(a.strip() for a in row["authors"].split(";"))
        entries.append(
            f"""@misc{{{key}{year},
  title = {{{row['title']}}},
  author = {{{authors}}},
  year = {{{year}}},
  eprint = {{{row['arxiv_id']}}},
  archivePrefix = {{arXiv}},
  url = {{{row['abs_url']}}}
}}"""
        )
    (ROOT / "references.bib").write_text("\n\n".join(entries) + "\n", encoding="utf-8")


def markdown_to_html(markdown_text: str) -> str:
    try:
        import markdown  # type: ignore

        body = markdown.markdown(markdown_text, extensions=["tables", "toc", "fenced_code"])
    except Exception:
        body = f"<pre>{html.escape(markdown_text)}</pre>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>量化 Agent 元年论文学习报告</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.72; margin: 48px auto; max-width: 980px; color: #1f2933; }}
    h1, h2, h3 {{ color: #111827; line-height: 1.28; }}
    h1 {{ font-size: 2.2rem; border-bottom: 3px solid #111827; padding-bottom: 0.4rem; }}
    h2 {{ margin-top: 2.2rem; border-bottom: 1px solid #d1d5db; padding-bottom: 0.25rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d1d5db; padding: 6px 8px; vertical-align: top; }}
    code, pre {{ background: #f3f4f6; }}
    pre {{ padding: 16px; white-space: pre-wrap; }}
    a {{ color: #0f766e; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def write_readme(body_chars: int, rows: list[dict[str, str]]) -> None:
    text = f"""# QuantML 量化 Agent 论文学习报告交付目录

生成日期：{TODAY}

## 阅读顺序

1. `quantml_agent_paper_study_report.zh.md`：主报告，正文约 {body_chars} 个非空白字符。
2. `paper_inventory.csv`：19 篇可见论文的元数据、来源链接、抽取状态和报告落点。
3. `paper_notes/`：逐篇学习笔记。
4. `claims_traceability.md`：关键结论到论文的可追溯表。
5. `source_post_extraction.md`：截图抽取与消歧记录。
6. `unresolved_mentions.md`：未作为论文纳入的截图提及。

## 文件说明

- `pdfs/`：可由 `scripts/collect_sources.py` 重新下载的 arXiv PDF 缓存，默认不纳入 Git。
- `extracted_text/`：由 PDF 抽取出的原文文本，已保留以便本地检索和审计。
- `references.bib`：BibTeX 参考文献。
- `quantml_agent_paper_study_report.zh.html`：可由 `scripts/generate_report.py` 重新生成的 HTML 版本，默认不纳入 Git。
- `pdf_generation_status.txt`：PDF 生成可用性说明；生成出的 PDF 默认不纳入 Git。

## 范围说明

本次没有找到公开完整的 61 篇清单，因此只覆盖附件截图中可见、可解析并可联网核验的一手论文。报告不构成投资建议。
"""
    (ROOT / "README.md").write_text(text, encoding="utf-8")


def count_body_chars(report: str) -> int:
    body = report.split("<!-- BODY_START -->", 1)[1].split("<!-- BODY_END -->", 1)[0]
    return len(re.sub(r"\s+", "", body))


def write_pdf_if_possible(html_path: Path) -> None:
    status_path = ROOT / "pdf_generation_status.txt"
    pdf_path = ROOT / "quantml_agent_paper_study_report.zh.pdf"
    try:
        from weasyprint import HTML  # type: ignore

        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        status_path.write_text(f"PDF generated on {TODAY}: {pdf_path.name}\n", encoding="utf-8")
    except Exception as exc:
        status_path.write_text(
            "PDF not generated because no working PDF renderer was available in this environment. "
            f"HTML was generated instead. Detail: {exc}\n",
            encoding="utf-8",
        )


def main() -> None:
    rows = load_rows()
    write_inventory(rows)
    write_notes(rows)
    write_source_extraction(rows)
    write_claims(rows)
    write_unresolved()
    write_bib(rows)
    report = build_report(rows)
    body_chars = count_body_chars(report)
    report_path = ROOT / "quantml_agent_paper_study_report.zh.md"
    report_path.write_text(report, encoding="utf-8")
    html_path = ROOT / "quantml_agent_paper_study_report.zh.html"
    html_path.write_text(markdown_to_html(report), encoding="utf-8")
    write_pdf_if_possible(html_path)
    write_readme(body_chars, rows)
    print(f"report={report_path}")
    print(f"body_chars={body_chars}")
    print(f"papers={len(rows)}")


if __name__ == "__main__":
    main()
