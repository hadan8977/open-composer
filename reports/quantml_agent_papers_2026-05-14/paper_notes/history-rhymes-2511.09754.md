# History Rhymes：论文学习笔记

- 题名：History Rhymes: Macro-Contextual Retrieval for Robust Financial Forecasting
- 作者：Sarthak Khanna; Armin Berger; Muskaan Chopra; David Berghaus; Rafet Sifa
- 日期：2025-11-12
- arXiv：[2511.09754](https://arxiv.org/abs/2511.09754v2)
- 主题：多模态金融预测与另类数据
- 截图来源：Image #28-30
- PDF 缓存路径（可重新下载）：`pdfs/history-rhymes-2511-09754.pdf`
- 本地抽取文本：`extracted_text/history-rhymes-2511-09754.txt`

## 一句话定位
把宏观指标和新闻情感嵌入共享空间，为当前预测检索历史相似宏观制度时期。

## 研究问题
金融市场非平稳，结构性断点会让静态模型在 OOD 环境中失败。简单融合新闻与指标并不能告诉模型“当前更像历史上的哪个时期”。

## 方法框架
论文提出 macro-contextual retrieval，把 CPI、失业率、收益率曲线、GDP 增速等宏观指标与金融新闻情感共同嵌入，检索历史类似制度期，并把检索结果用于预测。

## 数据与实验
实验包括股票和宏观相关预测场景。截图称 OOD 测试中 AAPL 达到 PF=1.18 和 Sharpe=0.95，而静态基线在制度转换下崩溃。

## 指标与结果
关注 OOD 表现、profit factor、Sharpe、检索质量和静态基线在制度变化下的退化程度。

## 创新点
创新在于把 RAG 从文本问答迁移到金融制度检索：检索对象不是文档事实，而是历史宏观上下文。

## 局限性
检索质量依赖嵌入空间，若宏观变量选择不全或新闻情感滞后，可能检索到表面相似但机制不同的时期。

## 与其他论文的关系
与 Hubble 的双通道 RAG 思路相通；与 Reliable Evaluation 的制度覆盖要求相互支持。

## 对实践的启发
策略报告应展示当前窗口最相似的历史制度、相似度、当时市场表现和失败案例，而不是只给最终预测。
