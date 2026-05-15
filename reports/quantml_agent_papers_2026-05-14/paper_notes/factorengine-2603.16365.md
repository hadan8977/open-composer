# FactorEngine：论文学习笔记

- 题名：FactorEngine: A Program-level Knowledge-Infused Factor Mining Framework for Quantitative Investment
- 作者：Qinhong Lin; Ruitao Feng; Yinglun Feng; Zhenxin Huang; Yukun Chen; Zhongliang Yang; Linna Zhou; Binjie Fei; Jiaqi Liu; Yu Li
- 日期：2026-03-17
- arXiv：[2603.16365](https://arxiv.org/abs/2603.16365v2)
- 主题：自动化因子挖掘与 Alpha 发现
- 截图来源：Image #23-24
- PDF 缓存路径（可重新下载）：`pdfs/factorengine-2603-16365.pdf`
- 本地抽取文本：`extracted_text/factorengine-2603-16365.txt`

## 一句话定位
把因子表达从固定公式或神经黑盒提升到可执行程序，用知识注入缩小搜索空间。

## 研究问题
符号因子搜索表达能力有限，神经预测器可解释性差且容易过拟合。真正可用的因子应当可执行、可审计、可调参，并能在大规模搜索中保持计算可控。

## 方法框架
FactorEngine 将因子视为程序级表达，分离逻辑修正与参数优化、LLM 引导方向搜索与贝叶斯超参搜索、LLM 使用与本地计算。它把非结构化财报等知识转成可执行因子程序的种子。

## 数据与实验
论文围绕量化投资因子挖掘任务评估 IC、ICIR、Rank IC/ICIR、年化收益和 Sharpe 等指标。截图称其显著高于 SOTA 预测和投资组合表现。

## 指标与结果
核心指标是 IC/ICIR、Rank IC/ICIR、AR/Sharpe、因子可执行率和搜索效率。程序级表达使每个候选因子的失败原因可以定位到语法、运行、数据或经济逻辑。

## 创新点
关键设计哲学是 separation of concerns：逻辑、参数、LLM、计算分别约束。这样既利用 LLM 的语义搜索能力，又避免让 LLM 直接控制所有计算。

## 局限性
程序级空间更强也更危险，隐性未来函数、数据依赖链和高复杂度代码都可能引入前瞻偏差。需要沙箱、静态检查和严格数据接口。

## 与其他论文的关系
FactorEngine 是 AlphaCrafter 的潜在 Miner 组件，也是 Hubble 的程序级前身或对照：二者都把因子生成约束在可审计空间。

## 对实践的启发
内部因子平台应把每个候选因子的代码 AST、数据列、窗口参数、滞后规则、运行日志和验证结果一起归档，而不只保存最终公式。
