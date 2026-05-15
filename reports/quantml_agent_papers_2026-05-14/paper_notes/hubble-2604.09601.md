# Hubble：论文学习笔记

- 题名：Hubble: An LLM-Driven Agentic Framework for Safe, Diverse, and Reproducible Alpha Factor Discovery
- 作者：Runze Shi; Shengyu Yan; Yuecheng Cai; Chenxi Lv
- 日期：2026-03-09
- arXiv：[2604.09601](https://arxiv.org/abs/2604.09601)
- 主题：自动化因子挖掘与 Alpha 发现
- 截图来源：Image #24-25
- 本地 PDF：`pdfs/hubble-2604-09601.pdf`
- 本地抽取文本：`extracted_text/hubble-2604-09601.txt`

## 一句话定位
用 AST 沙箱、白名单算子、双通道 RAG 和族群多样性约束，构建安全可复现的 LLM 因子发现框架。

## 研究问题
LLM 生成因子代码有运行时崩溃、非法数据访问、表达不可审计和候选因子同质化问题。纯公式搜索又容易局限在拥挤模板中。

## 方法框架
Hubble 限制 LLM 只能生成安全子语言中的操作树，通过 AST 层白名单执行；一个通道检索历史有效因子，另一个通道检索金融理论文献；再用公式相似度惩罚和族群诊断鼓励多样性。

## 数据与实验
论文在约 500 只美股面板上三轮评估 104 个有效候选，截图和摘要都强调零运行时崩溃，顶部因子集中在 range、volatility、trend 家族。

## 指标与结果
使用 RankIC、Pearson IC、RankICIR、ICIR、bucket return、long-short spread、turnover、coverage、公式复杂度和 HAC 显著性等诊断。

## 创新点
把 LLM 因子发现从自由代码生成变成受控研究工作流。安全沙箱和双通道 RAG 让搜索既有历史经验又有理论约束。

## 局限性
论文自己指出没有完整交易成本评估，候选因子仍需前向验证。RAG 也无法完全防止模型从预训练中吸收公开因子知识。

## 与其他论文的关系
与 FactorEngine 同属程序级因子生成；与 AlphaCrafter 连接后，可从因子候选生成进入制度筛选和组合执行。

## 对实践的启发
适合在研究环境做候选生成，但应强制把高分因子移入独立验证队列，执行净成本、容量、行业中性和多市场迁移测试。
