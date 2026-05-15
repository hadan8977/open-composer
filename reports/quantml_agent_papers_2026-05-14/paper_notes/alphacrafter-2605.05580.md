# AlphaCrafter：论文学习笔记

- 题名：AlphaCrafter: A Full-Stack Multi-Agent Framework for Cross-Sectional Quantitative Trading
- 作者：Yishuo Yuan; Jiayi Sheng; Sirui Zeng; Jiaqi Wang; Jiaheng Liu
- 日期：2026-05-07
- arXiv：[2605.05580](https://arxiv.org/abs/2605.05580v1)
- 主题：LLM Agent 与多智能体交易系统
- 截图来源：Image #6-7
- PDF 缓存路径（可重新下载）：`pdfs/alphacrafter-2605-05580.pdf`
- 本地抽取文本：`extracted_text/alphacrafter-2605-05580.txt`

## 一句话定位
把因子挖掘、制度状态感知、组合筛选和风险约束执行组织成 Miner-Screener-Trader 闭环，是截图中“全栈 Multi-Agent 量化框架”的代表。

## 研究问题
横截面量化策略不是只找到一个历史有效因子即可。真实流程需要连续发现候选因子、判断市场制度是否改变、筛掉在当前环境中失效的信号，并在风险预算下形成交易组合。传统因子挖掘偏离线搜索，传统执行偏固定规则，二者之间缺少能够从交易反馈回到研究端的闭环。

## 方法框架
框架把系统拆成 Miner、Screener、Trader 三类 Agent。Miner 负责 LLM 引导的连续因子搜索，Screener 结合制度状态和候选因子的历史表现调整权重，Trader 在组合和风险约束下执行。反馈不是停留在语言解释层，而是把执行结果反馈给 Screener 和 Miner，使新因子搜索与旧因子调权形成循环。

## 数据与实验
论文围绕 CSI 300 和 S&P 500 等横截面股票池做实验，截图强调其在中美市场都优于若干 SOTA 基线，并且跨试验方差较低。原文将非平稳市场、微观结构摩擦、行为因素作为背景，但仍属于研究回测而非实盘订单系统。

## 指标与结果
关注年化收益、风险调整收益、跨市场稳定性、因子表现分布和交易组合结果。截图称其在 CSI 300 与 S&P 500 上均显著超越基线，且方差最低；报告中应把该结论表述为论文实验结果，而非可直接复用的实盘收益承诺。

## 创新点
核心价值在于把“因子搜索”从一次性离线优化扩展为全栈自适应管道：因子发现、制度感知、风险约束执行和反馈更新放在同一系统中讨论。它把 FactorEngine/Hubble 式因子发现推进到更接近交易生命周期的位置。

## 局限性
截图指出没有完整报告交易成本细节；从论文设定看，Agent 闭环仍依赖回测数据和任务分解质量。多 Agent 之间的反馈可能引入共振式过拟合，因此需要额外的时间切分、交易成本、容量和延迟验证。

## 与其他论文的关系
可视为 FactorEngine 和 Hubble 的上层集成框架，也与 TrustTrade/Reliable Evaluation 共享一个问题：Agent 之间如何形成可靠共识而不是互相放大错误。

## 对实践的启发
若用于内部研究，应先把 Miner 生成的因子表达、Screener 的制度标签、Trader 的约束和每次组合变更都结构化记录；只有在固定验证窗口、净成本收益和基准族对照通过后，才可进入纸面交易观察。
