# Reliable Evaluation：论文学习笔记

- 题名：Toward Reliable Evaluation of LLM-Based Financial Multi-Agent Systems: Taxonomy, Coordination Primacy, and Cost Awareness
- 作者：Phat Nguyen; Thang Pham
- 日期：2026-03-29
- arXiv：[2603.27539](https://arxiv.org/abs/2603.27539v1)
- 主题：评估基准与可靠性研究
- 截图来源：Image #34-36
- PDF 缓存路径（可重新下载）：`pdfs/reliable-evaluation-2603-27539.pdf`
- 本地抽取文本：`extracted_text/reliable-evaluation-2603-27539.txt`

## 一句话定位
提出多 Agent 金融系统评估分类法、协调优先假设和协调盈亏平衡价差，是整组论文的评估底座。

## 研究问题
LLM 金融多 Agent 论文增长很快，但缺少统一评价框架。许多论文存在前瞻偏差、幸存者偏差、回测过拟合、交易成本忽略和制度覆盖不足。

## 方法框架
论文从架构、协调、记忆、工具四维分类 12 个多 Agent 系统和两个单 Agent 基线，并提出 Coordination Primacy Hypothesis 与 Coordination Break-even Spread。

## 数据与实验
它是 survey/方法论论文，汇总多 Agent 交易系统的报告指标和评估质量。截图列出五大普遍性评估失败。

## 指标与结果
关注污染控制、点时宇宙、滚动窗口、净成本收益、制度覆盖、协调成本、Agent 数量边际收益和价差门槛。

## 创新点
最大贡献是把“多 Agent 是否有价值”转成可检验问题：固定模型、数据和工具，只改变协调协议，观察净成本后是否仍有增量。

## 局限性
协调优先假设仍需要严格实证验证；survey 受已发表论文质量限制，很多结果不可直接比较。

## 与其他论文的关系
本报告所有实践判断都应以它为底线。AlphaCrafter、TrustTrade、HiveMind 等都可被放入其分类法中重新评估。

## 对实践的启发
任何声称 Agent Alpha 的报告都应同时提供单 Agent、无协调、多 Agent、成本后和多制度窗口结果，并明确 CBS 是否覆盖实际价差。
