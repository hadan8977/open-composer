# Open Composer Context Summary

Date: 2026-05-08

## 1. 背景

Open Composer 的出发点不是再做一个 dashboard，也不是做一个自动下单机器人。

用户真正想要的是一种个人可用的、对话式的策略工作台：

- 用自然语言和 Codex 讨论策略；
- 让 Codex 在受约束的仓库里生成代码、测试、回测和报告；
- 用确定性扫描器和事件分析模块把市场信息变成信号；
- 保持手动交易或严格受控的 paper 流程；
- 持续复盘、修正和沉淀策略经验。

这个方向的核心变化是：

1. 重点从“展示型产品”转为“可审计的策略工作台”。
2. 重点从“让人手动操作系统”转为“让 Codex 代替大部分工程和策略整理工作”。
3. 重点从“全自动交易”转为“信号生成 + 人工决策 + 复盘闭环”。

## 2. 补全后的真实问题

更深一层看，这个项目要回答的不是“要不要用 Qlib”或“要不要接 Alpaca”这种单点问题。

真正的问题是：

- 如何让 Codex 变成可控的策略工程师；
- 如何让 Skill 固化策略生成、回测审查、风险审查和复盘流程；
- 如何让 MCP 只作为工具和数据入口，而不是失控的执行权限；
- 如何选择一个足够轻的量化后端，让策略能调试、回测、扫描；
- 如何接 Alpaca，但不把交易权限过早交给模型；
- 如何保留后续接 Qlib、OpenBB、TradingView 的空间；
- 如何让一个非专业用户也能通过对话获得可运行策略和复盘结论。

因此 Open Composer 必须同时定义产品目标和技术骨架。只有产品目标是不够的；没有技术骨架，Codex 也不知道该生成什么、按什么边界生成、用什么 runner 验证。

## 3. 最终结论

研究和讨论之后，最合适的形态不是单独的 App，也不是只靠一个项目文件夹，更不是单靠 skills 或 MCP。

最合适的是一个 **repo-native 的混合式工作台**：

- 仓库本身就是产品；
- Codex 负责策略工程、测试、回测、改写和复盘；
- skills 负责封装工作流；
- MCP 负责接外部工具和数据；
- schema、runner、测试和权限负责硬约束；
- LLM 只在候选信号和文本分析上发挥作用；
- 人始终保留最终交易决定权。

这也是最能发挥 Codex 优势的方式。

技术上，MVP 应该采用“轻量内部量化后端 + adapters”的方式：

- 内部后端负责 spec、数据加载、指标、回测、扫描、风控、报告；
- Alpaca 是数据和 paper account adapter，不是策略托管平台；
- OpenBB / MCP 是研究工具层；
- Qlib 是后续 ML/factor research adapter，不是第一版底座；
- LLM API 是结构化 review/event extraction 服务；
- Codex skills 是策略工程工作流，不是 runtime engine。

## 4. 调研结论

### 4.1 更接近目标的产品

**Composer**

- 最接近“自然语言生成策略”的体验。
- 优点是策略编排和回测路径清晰。
- 局限是更偏低频、组合编排和封闭产品体验。
- 不适合作为 15m/1h 的个人事件+技术混合工作台直接照搬。

**Capitalise.ai**

- 更像自然语言交易/提醒语法。
- 更适合“先提醒、后决定”的 manual trading 场景。
- 但它是闭源且能力边界固定。

**TrendSpider**

- 更强在技术分析、策略测试和提醒。
- 适合主动交易和多周期观察。
- 但不是完整的 LLM 策略工程系统。

**LevelFields**

- 强在事件驱动分析。
- 适合把大量文本、财报、事件映射成可交易信号。
- 但它是事件层，不是完整的策略工程台。

**TradingView**

- 适合提醒、图表、Webhook 和 chart side 触发。
- 适合作为信号出口，不适合作为策略真源。

**QuantConnect / LEAN**

- 是成熟量化平台。
- 更适合后期成熟策略和更正式的研究流程。
- 对个人早期原型来说太重。

**OpenBB / Financial Datasets / Alpaca**

- 更像数据与工具层，不是完整产品。
- 适合被集成进个人策略工作台。

### 4.2 论文和研究的共同结论

从相关论文和行业讨论看，LLM 最有价值的地方不是“自己直接交易”，而是：

- 把非结构化文本转成结构化特征；
- 做事件分类和摘要；
- 做策略改写和研究辅助；
- 对候选信号做上下文审查；
- 帮人复盘和发现策略失效模式。

比较稳定的结论是：

- 纯 LLM 直接做交易，不稳定；
- 纯量化系统直接忽略事件，也不完整；
- 更好的方式是“LLM 转信号，量化负责执行逻辑”；
- 在较低频或 manual trading 场景下，LLM 适合做审查、解释和编排建议；
- 在高频或秒级场景下，LLM 不合适。

## 5. 产品边界

### 5.1 要做什么

Open Composer 要做的是：

- 把自然语言变成策略草案；
- 把草案变成可测试、可回测的策略代码；
- 把市场、新闻、财报、宏观信息转成结构化事件；
- 在候选信号出现后生成 review card；
- 帮用户做 manual trading 的决策辅助；
- 记录交易和复盘；
- 让 Codex 持续改进策略。

### 5.2 不做什么

以下内容不应作为 MVP 的默认目标：

- 不做自动 live trading；
- 不做 1m / tick 级高频策略；
- 不做 LLM 全市场持续扫描；
- 不做把 broker 写权限直接交给模型；
- 不做重 dashboard-first 架构；
- 不做默认多 agent 辩论式系统；
- 不做 Qlib-first 的重型研究框架绑定；
- 不做把所有判断都交给 LLM；
- 不做默认全自动执行和持仓管理。

## 6. 角色分工

| 层级 | 角色 | 主要职责 | 不负责 |
|---|---|---|---|
| Codex | 策略工程师 | 生成/修改策略、测试、回测、报告、复盘 | 直接下单、实时扫描全市场 |
| LLM API | 文本/事件分析器 | 新闻摘要、事件提取、review card | 写策略代码、自动下单 |
| MCP | 工具层 | 接数据源、接研究工具、接 paper 账户信息 | 作为治理层 |
| Runner | 确定性执行层 | 扫描、回测、生成信号、写审计记录 | 做主观判断 |
| Human | 最终决策者 | 是否交易、是否接受策略、是否激活 | 替代不了 |

## 7. 推荐架构

推荐结构是：

```text
项目仓库 = 产品本体
AGENTS.md / CLAUDE.md = Codex 工作约束
skills = 可复用工作流
schemas = 硬格式约束
runners = 确定性执行
SQLite + files = 状态与审计
MCP = 外部工具层
LLM = 结构化审查和事件分析
```

这个结构的优点是：

- 足够轻；
- 足够可控；
- 足够可审计；
- 足够适合个人使用；
- 足够能发挥 Codex 的工程能力。

## 8. 技术底座选择

MVP 的技术底座应当是内部轻量量化后端，而不是直接绑定一个大型量化框架。

推荐选择：

- Python CLI 作为第一操作入口；
- repo-scoped `.agents/skills` 作为 Codex 工作流；
- `.codex/config.example.toml` 作为 MCP 配置示例；
- Pydantic / JSON Schema 作为结构约束；
- SQLite 保存状态和审计；
- Parquet/CSV 保存行情缓存；
- backtesting.py 或简单内部 engine 作为第一回测实现；
- Alpaca adapter 提供美股行情和 paper account；
- OpenBB MCP 提供研究工具；
- Qlib adapter 延后，用于更正式的 ML/factor research。

这个选择能避免两种极端：

- 只靠 Codex prompt，缺少可执行底座；
- 一开始上 Qlib/大型后端，导致复杂度超过产品验证需要。

## 9. 频率判断

### 9.1 适合 LLM 深度参与

- 日频；
- 周频；
- 1 小时；
- 15 分钟的候选信号审查；
- 事件驱动、财报驱动、宏观驱动场景。

### 9.2 可以支持但要强约束

- 5 分钟；
- 只做 bar close；
- 先 deterministic 过滤，再 LLM 审查；
- 只处理 watchlist，而不是全市场。

### 9.3 不建议

- 1 分钟；
- tick 级；
- 需要极低延迟的自动决策。

## 10. 技术和产品原则

- 策略必须先变成 spec；
- spec 必须可校验；
- 代码必须可测试；
- 回测必须可复现；
- 信号必须可追溯；
- review 必须结构化；
- 交易必须可手动确认；
- 复盘必须可沉淀；
- 所有 LLM 输出必须附带证据、时间戳和版本信息。

## 11. 为什么最终选这个方向

因为它最符合下面四个要求：

1. 适合个人独用。
2. 能最大化发挥 Codex 的代码和工程能力。
3. 能保留自然语言交互。
4. 能把风险控制在可审计、可复现、可人工兜底的范围内。

## 12. 后续扩展方向

后续如果需要，可以再加：

- 轻量 UI；
- TradingView webhook；
- Alpaca paper tracking；
- Qlib adapter；
- 更完整的 event pipeline；
- 更成熟的策略库和回测库。

## 13. 参考来源

- OpenAI Codex CLI
- OpenAI AGENTS.md
- OpenAI Codex skills
- OpenAI Codex MCP
- OpenAI Codex hooks
- OpenAI Structured Outputs
- MCP tools specification
- OpenBB MCP docs
- Alpaca MCP server docs
- Alpaca paper trading docs
- Alpaca real-time news docs
- 已完成的 LLM + Quant research notes
