# PolyBench：论文学习笔记

- 题名：PolyBench: Benchmarking LLM Forecasting and Trading Capabilities on Live Prediction Market Data
- 作者：Pu Cheng; Juncheng Liu; Yunshen Long
- 日期：2026-04-03
- arXiv：[2604.14199](https://arxiv.org/abs/2604.14199)
- 主题：评估基准与可靠性研究
- 截图来源：Image #32-33
- 本地 PDF：`pdfs/polybench-2604-14199.pdf`
- 本地抽取文本：`extracted_text/polybench-2604-14199.txt`

## 一句话定位
用 Polymarket 实时预测市场快照构造防污染基准，评估 LLM 语言流畅性与真实概率交易能力的差距。

## 研究问题
传统金融 LLM benchmark 容易被训练数据污染，也常缺少可交易市场价格。预测市场提供带时间戳、订单簿和新闻流的实时概率环境，更适合检验模型能否把信息转成收益。

## 方法框架
PolyBench 收集 38,666 个二元预测市场、4,997 个事件的点时快照，同步 CLOB 状态与实时新闻，让 7 个 LLM 在同一时间锁定市场状态下输出预测并模拟执行。

## 数据与实验
数据来自 2026 年 2 月 6-12 日的实时市场，生成 36,165 个预测。时间窗口短但污染控制强。

## 指标与结果
使用方向准确率、Confidence-Weighted Return、APY、Sharpe 和订单簿执行模拟。摘要称只有 2/7 个模型实现正收益，MiMo-V2-Flash CWR 17.6%，Gemini-3-Flash CWR 6.2%。

## 创新点
核心是 contamination-proof design：模型无法提前看到未来事件，并且收益必须通过可交易价格实现。

## 局限性
预测市场不同于股票市场，流动性、参与者结构和事件类型都有差异；一周窗口不足以覆盖制度变化。

## 与其他论文的关系
与 OOM-RL 一样强调外部经济反馈，与 QuantCode-Bench 一起把 LLM 能力评估从语言输出推进到交易后果。

## 对实践的启发
适合作为 LLM 金融推理基准，但用于策略研究时应补充更长窗口、更多市场和严格滑点容量假设。
