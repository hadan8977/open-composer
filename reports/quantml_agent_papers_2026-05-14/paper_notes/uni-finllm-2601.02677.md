# Uni-FinLLM：论文学习笔记

- 题名：Uni-FinLLM: A Unified Multimodal Large Language Model with Modular Task Heads for Micro-Level Stock Prediction and Macro-Level Systemic Risk Assessment
- 作者：Gongao Zhang; Haijiang Zeng; Lu Jiang
- 日期：2026-01-06
- arXiv：[2601.02677](https://arxiv.org/abs/2601.02677v1)
- 主题：多模态金融预测与另类数据
- 截图来源：Image #28-30
- 本地 PDF：`pdfs/uni-finllm-2601-02677.pdf`
- 本地抽取文本：`extracted_text/uni-finllm-2601-02677.txt`

## 一句话定位
用共享 Transformer 主干和模块化任务头统一金融文本、数值时序、基本面与视觉数据。

## 研究问题
金融机构既要做微观股票预测，也要做宏观系统性风险评估。现有模型常按任务孤立训练，难以利用不同尺度之间的关系。

## 方法框架
Uni-FinLLM 采用共享主干、跨模态注意力和多任务优化，通过模块化任务头处理股票方向、信用风险、宏观预警等任务。

## 数据与实验
输入覆盖金融文本、数值时间序列、基本面和视觉数据。截图报告股票方向准确率 67.4% 对比基线 61.7%，信用风险 84.1% 对比 79.6%，宏观预警 82.3%。

## 指标与结果
关注分类准确率、风险识别率、宏观预警效果和多任务之间的互相促进或竞争。模块间竞争是截图中指出的主要局限之一。

## 创新点
它把金融多模态从单一任务模型推进到统一主干+任务头架构，提供了 Agent richer state representation 的可能。

## 局限性
统一模型可能因任务冲突损害某些子任务；跨模态注意力机制复杂，解释某个预测由哪种模态驱动并不容易。

## 与其他论文的关系
可作为多 Agent 交易系统的状态表示层，也能为 SBCA 或 AlphaCrafter 的 Agent 提供更丰富输入。

## 对实践的启发
用于实盘前应逐任务做时点一致性、模态缺失、任务冲突和校准曲线检查，避免一个统一模型遮盖不同任务的失败模式。
