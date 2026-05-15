# QuantCode-Bench：论文学习笔记

- 题名：QuantCode-Bench: A Benchmark for Evaluating the Ability of Large Language Models to Generate Executable Algorithmic Trading Strategies
- 作者：Alexey Khoroshilov; Alexey Chernysh; Orkhan Ekhtibarov; Nini Kamkia; Dmitry Zmitrovich
- 日期：2026-04-16
- arXiv：[2604.15151](https://arxiv.org/abs/2604.15151v1)
- 主题：评估基准与可靠性研究
- 截图来源：Image #33
- 本地 PDF：`pdfs/quantcode-bench-2604-15151.pdf`
- 本地抽取文本：`extracted_text/quantcode-bench-2604-15151.txt`

## 一句话定位
评估 LLM 能否生成可执行算法交易策略，强调主要困难在交易语义和 API 操作，而不是普通语法。

## 研究问题
通用代码 benchmark 无法反映量化策略生成难度。策略代码必须符合金融逻辑、专用 API、历史数据执行和语义对齐，否则即使语法正确也不会产生有效交易。

## 方法框架
QuantCode-Bench 设计多阶段评估管道：语法正确性、回测执行、交易存在性、语义对齐，并用 LLM judge 辅助判断策略是否符合题意。

## 数据与实验
基准任务围绕算法交易策略生成，评估现代 LLM 在不同约束下输出可运行策略的能力。

## 指标与结果
关注代码能否解析、能否运行、是否实际交易、交易逻辑是否符合需求、agentic 多轮设置相对单轮的提升。

## 创新点
它把“会写 Python”与“会写可交易策略”区分开。截图强调主要限制不是语法，而是交易逻辑操作化、API 使用和语义一致性。

## 局限性
LLM judge 可能带来主观偏差；可执行策略不等于有效策略，benchmark 也不能替代真实样本外验证。

## 与其他论文的关系
与 FactorEngine/Hubble 的程序级因子生成直接相关，因为因子代码和策略代码都需要语法、安全、执行和语义多层验证。

## 对实践的启发
内部策略生成平台应把代码生成通过率拆成语法、数据接口、交易行为、风控约束、语义一致性五个门槛，不能只看回测收益。
