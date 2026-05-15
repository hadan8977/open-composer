# Expert Investment Teams：论文学习笔记

- 题名：Toward Expert Investment Teams: A Multi-Agent LLM System with Fine-Grained Trading Tasks
- 作者：Kunihiro Miyazaki; Takanobu Kawahara; Stephen Roberts; Stefan Zohren
- 日期：2026-02-26
- arXiv：[2602.23330](https://arxiv.org/abs/2602.23330v1)
- 主题：LLM Agent 与多智能体交易系统
- 截图来源：Image #6, #11-12
- 本地 PDF：`pdfs/expert-investment-teams-2602-23330.pdf`
- 本地抽取文本：`extracted_text/expert-investment-teams-2602-23330.txt`

## 一句话定位
把“投研团队角色扮演”推进到细粒度任务分解，说明 Agent 角色不是越宏观越好，而是越接近真实流程越可检验。

## 研究问题
早期多 Agent 交易系统常设 Analyst、Trader、Risk Manager 等粗角色，但角色边界含糊，信息传递噪声大，很难知道是哪个环节产生价值。论文认为，真实投研流程包含更细的任务单元，粗粒度提示会损害推理透明度和组合质量。

## 方法框架
系统把投资分析拆成细粒度任务，让多个 Agent 分别完成信息提取、风险与收益展望、组合判断等子流程，再汇总形成交易决策。与粗粒度团队相比，细粒度设计更利于消融实验和错误定位。

## 数据与实验
论文围绕日本股票与 TOPIX 100 等场景评估，使用月度组合收益、风险展望和 10bps 单边交易成本设定。截图强调 fine-grained task design 比 coarse-grained baseline 有更高 Sharpe。

## 指标与结果
主要看 Sharpe、年化收益、波动、与指数的相关性、组合配置比例和消融后性能变化。值得注意的是论文不只报告 Agent 组合本身，还讨论与指数组合后的风险调整效果。

## 创新点
贡献在于把 Agent 系统评估对象从“几个角色”转成“任务组织方式”。这与软件工程中的 workflow design 类似：性能提升来自流程结构，而不只是更强模型。

## 局限性
细粒度任务会增加 token 成本和延迟，且若各角色共用同一模型与相似上下文，独立性可能不足。任务拆分过细也可能让错误在链路中累积。

## 与其他论文的关系
与 HiveMind 的贡献归因可结合：一个负责设计任务图，一个负责量化各节点贡献；与 Reliable Evaluation 的协调优先假设直接呼应。

## 对实践的启发
若搭建内部投研 Agent，不应只写“你是分析师”。更稳妥的方法是把输入、输出、证据字段、拒答条件和下游消费者全部固定，并做逐节点消融。
