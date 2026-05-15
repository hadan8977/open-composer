# HiveMind：论文学习笔记

- 题名：HiveMind: Contribution-Guided Online Prompt Optimization of LLM Multi-Agent Systems
- 作者：Yihan Xia; Taotao Wang; Shengli Zhang; Zhangyuhua Weng; Bin Cao; Soung Chang Liew
- 日期：2025-12-06
- arXiv：[2512.06432](https://arxiv.org/abs/2512.06432)
- 主题：LLM Agent 与多智能体交易系统
- 截图来源：Image #11-12
- 本地 PDF：`pdfs/hivemind-2512-06432.pdf`
- 本地抽取文本：`extracted_text/hivemind-2512-06432.txt`

## 一句话定位
用 Shapley/DAG-Shapley 给多 Agent 工作流做贡献归因，再在线优化低贡献 Agent 的提示词。

## 研究问题
多 Agent 系统的问题不是只有“怎么协作”，还包括“谁真正贡献了收益”。如果无法度量单个 Agent 的边际贡献，系统只能靠人工调 prompt，容易把无效角色保留下来。

## 方法框架
HiveMind 提出 CG-OPO：先用 Shapley value 度量 Agent 对最终任务的贡献，再用 DAG-Shapley 利用工作流 DAG 剪枝，减少组合枚举成本。被识别为低贡献的 Agent 会被自动提示优化。

## 数据与实验
论文在多 Agent 股票交易等场景验证，arXiv 摘要称 DAG-Shapley 在保持近似归因准确度时减少超过 80% 的 LLM 调用。

## 指标与结果
关注 Agent 贡献值、LLM 调用次数、交易任务收益、Sharpe、回撤和在线优化前后差异。它的关键指标不只是交易收益，还包括归因计算的可扩展性。

## 创新点
把合作博弈中的贡献归因引入 LLM 多 Agent 管理，并针对 DAG 工作流做成本优化。它让多 Agent 研究可以从“增加角色”转向“保留有贡献角色”。

## 局限性
Shapley 归因依赖任务价值函数定义；金融场景中用 Sharpe 或收益作为价值函数时，短样本噪声会影响归因。在线 prompt 优化也可能过拟合近期市场。

## 与其他论文的关系
可作为 Expert Investment Teams 的诊断层，也能嵌入 AlphaCrafter 的 Agent 闭环，帮助判断 Miner、Screener、Trader 哪个环节贡献最大。

## 对实践的启发
在实盘前建议只把 HiveMind 用作研究诊断：定期冻结窗口，计算角色贡献和调用成本，把低贡献 Agent 降级为离线审查，而不是自动扩大权限。
