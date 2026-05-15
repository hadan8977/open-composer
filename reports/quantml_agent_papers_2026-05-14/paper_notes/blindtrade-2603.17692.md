# BlindTrade：论文学习笔记

- 题名：Can Blindfolded LLMs Still Trade? An Anonymization-First Framework for Portfolio Optimization
- 作者：Joohyoung Jeon; Hongchul Lee
- 日期：2026-03-18
- arXiv：[2603.17692](https://arxiv.org/abs/2603.17692v1)
- 主题：LLM Agent 与多智能体交易系统
- 截图来源：Image #9
- 本地 PDF：`pdfs/blindtrade-2603-17692.pdf`
- 本地抽取文本：`extracted_text/blindtrade-2603-17692.txt`

## 一句话定位
用股票标识匿名化来区分真实市场理解与训练数据中的股票-收益记忆，是 LLM 交易评估里很关键的反事实设计。

## 研究问题
如果 LLM 看到 AAPL、TSLA、NVDA 等标识后表现好，不能确认它理解当前市场，也可能只是记住了训练语料中的公司叙事和历史收益关联。对交易 Agent 来说，这种记忆偏差会让回测看起来有效，实盘却不可迁移。

## 方法框架
BlindTrade 匿名化股票标识，让 Agent 在不知道真实 ticker 的情况下输出评分，并结合 GNN 与 PPO-DSR 等策略模块做组合优化。框架还用负控制实验检验信号合法性，尝试排除靠名称、行业标签或历史名气获利的路径。

## 数据与实验
使用真实股票多资产数据并进行 2025 年 YTD 等实验。截图报告其 Sharpe 为 1.40±0.22，且在波动环境中表现较优，但在趋势性牛市中 Alpha 下降。

## 指标与结果
关注 Sharpe、稳定性、不同市场环境下的收益差异，以及匿名化前后性能是否仍然存在。若匿名化后表现完全消失，说明原信号更可能是记忆或标签偏差；若仍存在，则更接近可泛化结构。

## 创新点
创新在于把“遮蔽身份”作为评估协议，而不是只作为隐私处理。它让 LLM 交易研究从直接比较收益转向追问收益来源。

## 局限性
匿名化能削弱 ticker 记忆，但不能完全消除训练数据中行业结构、价格路径或指数成分带来的隐含记忆。截图也指出牛市环境 Alpha 衰减，说明框架不自动保证跨制度有效。

## 与其他论文的关系
与 TrustTrade 的信任校准互补；与 Reliable Evaluation 的前瞻偏差、幸存者偏差议题一致；也为 AlphaCrafter 这类多 Agent 框架提供了验证模块。

## 对实践的启发
做 LLM 选股实验时，建议同时跑真实标识、匿名标识、随机映射标识和行业保留匿名四组实验，比较信号差异并记录所有映射哈希。
