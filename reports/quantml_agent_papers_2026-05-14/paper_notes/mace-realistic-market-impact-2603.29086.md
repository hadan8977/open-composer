# MACE / Realistic Market Impact：论文学习笔记

- 题名：Realistic Market Impact Modeling for Reinforcement Learning Trading Environments
- 作者：Lucas Riera Abbade; Anna Helena Reali Costa
- 日期：2026-03-30
- arXiv：[2603.29086](https://arxiv.org/abs/2603.29086)
- 主题：强化学习组合优化与交易
- 截图来源：Image #17, #19
- 本地 PDF：`pdfs/mace-realistic-market-impact-2603-29086.pdf`
- 本地抽取文本：`extracted_text/mace-realistic-market-impact-2603-29086.txt`

## 一句话定位
用 Almgren-Chriss 与平方根冲击定律重构 Gymnasium 交易环境，说明成本模型会改变 RL 算法排名。

## 研究问题
很多开源 RL 交易环境使用固定 bps 或忽略交易成本，Agent 会学习高换手、现实不可执行的策略。若环境成本错，算法排名和结论都可能错。

## 方法框架
论文提出 MACE 环境套件，包含股票交易、保证金交易和组合优化，支持可插拔成本模型、永久冲击衰减和交易级日志。实验比较固定 10bps 成本与 Almgren-Chriss/平方根冲击模型。

## 数据与实验
使用 NASDAQ 100 股票池，评估 A2C、PPO、DDPG、SAC、TD3 等 DRL 算法。截图和原文摘要强调在真实冲击模型下，固定成本下表现最好的算法可能变差。

## 指标与结果
关注 OOS Sharpe、总收益、不同成本模型下算法排名、交易日志和冲击参数敏感性。论文摘要示例指出股票交易中 PPO 在固定成本下较优，但在 AC 模型下收益下降。

## 创新点
贡献不是提出新 RL 算法，而是提供更真实的环境和成本假设。它把“环境工程”上升为论文核心，因为环境决定策略学到什么。

## 局限性
冲击模型参数校准困难，AC 和平方根模型仍是简化表达，难覆盖订单簿队列、隐含流动性和市场参与者反应。

## 与其他论文的关系
与 SNAPO 的可微模拟互补；与 Reliable Evaluation 的交易成本忽略批评一致，是评估 RL 交易论文时必须引用的基准思想。

## 对实践的启发
任何 RL 交易策略在报告前都应至少跑固定成本、非线性冲击、滑点压力和容量约束四组环境，否则收益结论容易被环境假设主导。
