# Open Composer Context Summary

Date: 2026-05-08

## 1. Executive Conclusion

Open Composer 的产品方向是：

```text
个人使用的对话式 AI 策略工作台。
```

它把自然语言交易想法转成可验证、可提醒、可复盘的策略资产。第一版围绕美股/ETF、手动交易、15m/1h/daily/weekly 频率、Codex 仓库工作流和 TradingView 图表提醒展开。

核心判断：

- `StrategySpec` 是策略真源。
- Codex 是策略工程师，负责编写 spec、代码、Pine、报告、测试和复盘。
- Python runner 是确定性执行骨架，负责回测、扫描、日志和报告。
- Pine Script 是手动交易提醒层，负责图表侧观察和 alert 条件。
- LLM API 是事件分析和候选信号审查层，负责结构化文本、风险解释和反方观点。
- MCP 是外部工具和数据连接层，给 Codex 提供文档、市场数据、研究材料和平台操作能力。
- 用户保留最终交易决定，系统保留完整信号和决策记录。

## 2. Background

项目方向来自一次产品重估。

原始系统偏 dashboard、模块配置和运行时治理，实际目标更接近一个个人可用的 Composer-like 工作台：用户通过自然语言持续生成策略、验证策略、观察信号、记录决策、复盘改进。

Open Composer 的使命：

```text
把交易想法变成结构化策略资产，并围绕策略资产建立测试、提醒、审查和学习闭环。
```

## 3. Target User

目标用户是个人交易学习者：

- 关注美股、ETF 和事件驱动机会；
- 具备基础交易知识和学习意愿；
- 希望用 Codex 生成和维护策略代码；
- 希望用 LLM 处理新闻、财报、宏观和市场上下文；
- 倾向先手动交易，用人工确认降低自动化风险；
- 关注 15m、1h、daily、weekly，谨慎探索 5m；
- 需要报告、日志和复盘来提升纪律性和学习效率。

## 4. Market And Tool Research

### 4.1 Composer

Composer 提供自然语言创建策略、结构化策略编辑和回测体验。它证明了“对话生成策略 + 结构化策略表示 + 回测”的产品路径。

Open Composer 的对应设计：

- 用 `StrategySpec` 承载结构化策略。
- 用 Codex 生成策略资产。
- 用 Python runner 和 Pine export 形成可验证、可观察的执行材料。

### 4.2 Capitalise.ai

Capitalise.ai 的 Smart Notifications 支持自然语言条件、技术指标和宏观新闻事件提醒。它证明了“条件策略 + 提醒 + 人工动作”适合交易学习者和手动交易者。

Open Composer 的对应设计：

- 第一版采用 `manual_signal` 执行模式。
- 每个信号进入 `signal_logs/`。
- LLM review card 为信号补充上下文和风险解释。

### 4.3 TradingView

TradingView 提供 Pine Script、图表、alerts 和 webhook。它是手动交易者熟悉的观察与提醒环境。

Open Composer 的对应设计：

- 从 `StrategySpec` 导出 Pine Script。
- Pine 使用 bar-close alert 语义。
- Python/Pine 之间生成 parity 报告，跟踪信号差异。

### 4.4 Codex, AGENTS.md, Skills, MCP

OpenAI 官方文档给出的 Codex 扩展方式包括：

- `AGENTS.md`：项目级长期指令和约束；
- Skills：可复用的任务工作流，按需加载 `SKILL.md`；
- MCP：连接第三方工具、文档、浏览器、数据服务和平台 API。

Open Composer 的对应设计：

- `AGENTS.md` 固化项目边界、验证要求和安全规则。
- `.agents/skills/*/SKILL.md` 固化策略设计、回测编写、Pine 导出、风险审查、周复盘等任务。
- `.codex/config.example.toml` 给出可选 MCP 配置示例。
- 核心 MVP 用本地 sample data 保持可运行；外部 MCP 在后续适配器阶段扩展。

### 4.5 Alpaca, Lumibot, vectorbt, Qlib, LEAN

这些工具在路线中承担不同层级：

| 工具 | 推荐位置 | 作用 |
|---|---|---|
| Alpaca | 后续数据和 paper tracking adapter | paper account、订单记录、市场数据 |
| Lumibot | 后续 paper execution adapter | 策略生命周期和 Alpaca 执行封装 |
| vectorbt | 后续 research adapter | 快速参数扫描和组合研究 |
| Qlib | 高级 research adapter | ML 因子研究、横截面 alpha、模型训练 |
| LEAN | 成熟部署 adapter | 事件驱动引擎、复杂订单、长期工程化部署 |

第一版采用轻量 Python signal/backtest/scanner engine 作为产品内核。它让 `StrategySpec`、Pine export、signal log 和 journal 先形成闭环，再逐步接入外部引擎。

## 5. LLM + Quant Research View

LLM 与量化交易结合的主流价值集中在：

- 自然语言策略生成；
- 金融文本和事件抽取；
- 候选信号上下文审查；
- 策略日志和交易复盘；
- 人机协作式 alpha/策略研究；
- 用代码代理生成、测试和维护策略资产。

Open Composer 的系统模式：

```text
Codex 生成策略资产
Python 确定性验证和扫描
LLM 结构化文本/事件并审查候选信号
用户记录最终决策和交易结果
Codex 周期性复盘并提出策略改进草案
```

## 6. Product Architecture

```text
Natural-language idea
  -> Codex strategy-designer skill
  -> StrategySpec YAML
  -> spec validation
  -> Python signal/backtest/scanner engine
  -> Pine Script export
  -> signal parity report
  -> signal log
  -> optional LLM review card
  -> manual trade journal
  -> weekly Codex review
```

## 7. StrategySpec

`StrategySpec` 是策略真源。

它表达：

- 标的池；
- 时间周期；
- 入场规则；
- 出场规则；
- 风控规则；
- 数据假设；
- 执行模式；
- 信号确认方式；
- 生命周期状态；
- 人类可读的策略意图和假设。

## 8. Codex And LLM Division

| 场景 | 使用 Codex | 使用 LLM API |
|---|---|---|
| 生成或修改策略 spec | 是 | 可辅助生成草稿 |
| 编写 Python / Pine / 测试 | 是 | 辅助解释 |
| 运行回测并修复失败 | 是 | 辅助总结 |
| 快速审查一个候选信号 | 可用 | 是 |
| 结构化新闻/财报/宏观内容 | 可用 | 是 |
| 周复盘和改进草案 | 是 | 可提供总结输入 |
| 外部平台和数据连接 | 通过 MCP/脚本 | 通过 API 输出结构化结果 |

Codex 适合重型文件工作、代码生成、测试和长期策略资产维护。LLM API 适合轻量、快速、结构化的事件理解和候选信号审查。

## 9. Frequency View

| 频率 | 产品定位 |
|---|---|
| weekly | 策略复盘、组合观察、宏观和事件总结 |
| daily | 策略研究、事件跟踪、低频信号 |
| 1h | 技术信号 + LLM 上下文审查 |
| 15m | 第一版主动信号重点频率 |
| 5m | 小 watchlist、bar-close、强过滤场景 |
| 1m / tick | 后续研究议题 |

## 10. Documentation Design Basis

这组文档按以下原则组织：

- README 是入口和当前状态说明。
- Product MVP 是产品定义、用户、范围、架构、流程和验收。
- Build Handoff 是新 Codex 会话的实现指令。
- Context Summary 是背景研究、产品判断和来源解释。

调研依据：

- PRD 应定义产品目的、功能、行为、用户需求和成功标准。
- MVP 文档应给出足够上下文，同时保持可更新和可执行。
- 技术文档应区分教程、操作指南、参考和解释。
- Codex 项目应通过 `AGENTS.md` 固化长期规则，通过 Skills 固化可复用任务，通过 MCP 连接外部工具和上下文。

## 11. Sources

- Atlassian PRD guidance: https://www.atlassian.com/agile/product-management/requirements
- Diátaxis documentation framework: https://diataxis.fr/
- OpenAI Codex AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- OpenAI Codex Skills: https://developers.openai.com/codex/skills
- OpenAI Codex MCP: https://developers.openai.com/codex/mcp
- OpenAI Skills catalog: https://github.com/openai/skills
- Composer Create with AI: https://help.composer.trade/article/108-create-with-ai
- Composer product site: https://www.composer.trade/
- Capitalise.ai Smart Notifications: https://support.capitalise.ai/en/articles/3339296-smart-notifications
- TradingView Strategy Alerts: https://www.tradingview.com/support/solutions/43000481368-strategy-alerts/
- TradingView Webhook Alerts: https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/
- Alpaca Paper Trading: https://docs.alpaca.markets/docs/trading/paper-trading/
- Lumibot Backtesting: https://lumibot.lumiwealth.com/backtesting.html
- vectorbt: https://vectorbt.dev/
- Microsoft Qlib: https://github.com/microsoft/qlib
- Qlib paper: https://arxiv.org/abs/2009.11189
