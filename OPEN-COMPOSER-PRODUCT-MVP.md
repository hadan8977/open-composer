# Open Composer Product MVP

Date: 2026-05-08

## 1. Product Statement

Open Composer 是一个个人使用的对话式 AI 策略工作台。

MVP 将自然语言交易想法转成结构化 `StrategySpec`、Python 回测/扫描、TradingView Pine Script、信号日志、报告、LLM 审查卡和手动交易 journal。用户通过这些资产研究策略、观察信号、手动决策、记录结果并持续复盘。

## 2. Target User

MVP 服务一个个人用户：

- 交易或学习美股、ETF；
- 希望先手动执行交易；
- 希望 Codex 生成和维护策略资产；
- 希望 LLM 分析事件、新闻、财报和候选信号；
- 希望用报告和 journal 建立可复盘的学习闭环；
- 使用 15m、1h、daily、weekly 工作流，并谨慎使用 5m。

## 3. Product Problem

用户有交易想法，也能和 AI 对话，但缺少稳定流程把想法转成可测试、可提醒、可复盘的策略资产。

核心问题：

- 策略想法停留在自然语言，难以验证和复用；
- 代码生成结果缺少统一 schema、生命周期和测试；
- TradingView 信号和 Python 回测容易语义漂移；
- 新闻、财报、宏观等文本信息难以稳定进入策略流程；
- 手动交易决策缺少结构化日志和周复盘；
- 直接自动交易会放大模型、代码和用户经验的风险。

## 4. MVP Objective

MVP 验证这条闭环：

```text
Idea
  -> StrategySpec
  -> Python backtest/scanner
  -> Pine Script export
  -> signal parity report
  -> signal log
  -> optional LLM review card
  -> manual trade journal
  -> weekly Codex review
```

## 5. Value Proposition

Open Composer 给用户一套可重复的策略工作流：

- 用 Codex 更快创建策略资产；
- 用 `StrategySpec` 固化策略结构；
- 用 Python 回测验证历史行为；
- 用 Pine Script 支持 TradingView 图表提醒；
- 用 signal parity report 管理 Python/Pine 差异；
- 用 LLM review card 提升候选信号审查质量；
- 用 journal 和周复盘提升纪律性、风控和学习效率。

## 6. MVP Technical Architecture

### 6.1 System Layers

```text
Codex workspace
  AGENTS.md
  repo skills
  StrategySpec files
  generated Python/Pine artifacts

Deterministic runner
  spec validation
  indicators
  signal engine
  backtest engine
  scanner
  report writer
  journal writer

Optional intelligence services
  LLM review cards
  MCP research/data tools

External user tools
  TradingView Pine alerts
  future data providers
  future paper tracking
```

### 6.2 Codex Layer

Codex 负责生成、修改和验证仓库资产：

- 读取 `AGENTS.md` 获取全局产品规则；
- 通过 `.agents/skills/*/SKILL.md` 执行专门任务；
- 生成 `StrategySpec`、Python、Pine、测试、报告和复盘；
- 运行 CLI 和测试，修复失败结果；
- 在周复盘中提出策略改进草案。

第一批 repo skills：

- `strategy-designer`
- `python-backtest-writer`
- `pine-exporter`
- `signal-parity-reviewer`
- `risk-reviewer`
- `weekly-reviewer`

### 6.3 StrategySpec Layer

`StrategySpec` 是策略真源。

它描述：

- `name`
- `timeframe`
- `universe`
- `entry`
- `exit`
- `risk`
- `execution`
- `data_assumptions`
- `notes`
- `lifecycle`

Python 和 Pine 都从同一份 spec 生成或对齐。

### 6.4 Runner Layer

Runner 是本地确定性执行骨架。

MVP 使用轻量 Python 实现：

- Python 3.11+；
- `typer` CLI；
- `pydantic` 或 `jsonschema` 做 schema validation；
- `pandas` / `numpy` 做 OHLCV、指标和信号计算；
- `PyYAML` 读取策略；
- `pytest` 和 `ruff` 做验证。

Runner 提供：

- `oc doctor`
- `oc spec validate`
- `oc backtest`
- `oc scan`
- `oc compile pine`
- `oc journal add`

### 6.5 Pine Layer

Pine export 负责 TradingView 侧观察和提醒：

- 生成 Pine Script；
- 生成 `alertcondition`；
- 使用 bar-close 语义；
- 输出 repaint、lookahead、fill assumption 说明；
- 与 Python signal log 做 parity 对照。

### 6.6 LLM API Layer

LLM API 负责轻量结构化智能任务：

- 新闻和事件摘要；
- 财报和公告结构化；
- 候选信号审查；
- 风险解释；
- 反方观点；
- invalidation 条件；
- 手动动作建议。

输出采用 JSON schema 或 Markdown 模板，保存到 `reports/reviews/`。

### 6.7 MCP Layer

MCP 负责给 Codex 连接外部上下文和工具：

- OpenAI Docs MCP；
- 金融数据/新闻 MCP；
- GitHub MCP；
- 浏览器/TradingView 辅助工具；
- 后续 Alpaca/OpenBB/Polygon 工具。

MVP 的本地样例路径使用 sample data 保持可运行。MCP 在真实数据、研究扩展和平台集成阶段发挥作用。

### 6.8 Data And Adapter Roadmap

数据和执行能力按阶段接入：

| 阶段 | 能力 | 工具 |
|---|---|---|
| MVP | sample OHLCV、本地扫描、Pine export | pandas, local CSV |
| Data Adapter | 美股历史/实时数据 | Alpaca, Polygon, OpenBB |
| Research Adapter | 参数扫描、组合研究 | vectorbt |
| Paper Tracking | paper account 状态和订单记录 | Alpaca |
| Paper Execution | approval-gated paper execution | Lumibot + Alpaca |
| ML Research | 因子、横截面 alpha、模型训练 | Qlib |
| Mature Engine | 复杂事件驱动和部署 | LEAN |

## 7. MVP Scope

### 7.1 Core Features

1. **StrategySpec**
   - YAML 策略定义。
   - 覆盖 universe、timeframe、entry、exit、risk、execution、data assumptions 和 lifecycle。

2. **Spec Validation**
   - JSON Schema 或 Pydantic validation。
   - 生命周期状态：draft、approved、active、retired。

3. **Codex Strategy Workflow**
   - Repo skills 指导 Codex 创建和修改策略资产。
   - Codex 写 spec、Python、Pine、测试、报告和复盘。

4. **Python Backtest / Scanner**
   - 从 sample data 开始。
   - 支持 15m、1h、daily 样例。
   - 产出 signal logs 和 backtest reports。

5. **Pine Script Export**
   - 生成 TradingView-ready Pine Script。
   - 生成手动交易 alert 条件。

6. **Signal Parity**
   - 对照 Python signal log 和 Pine 语义。
   - 记录时间、bar close、fill assumption 和 repaint 风险。

7. **Reports**
   - 每次 backtest 生成 Markdown report。
   - 包含假设、指标、信号数量、风险和下一步。

8. **Journal**
   - 记录手动交易、跳过信号、入场/出场备注和结果。

9. **LLM Review Card**
   - 对候选信号生成结构化审查。
   - 覆盖 catalyst、risk、invalidation、evidence 和 action suggestion。

10. **Doctor Command**
    - 检查本地环境、依赖、sample data 和可选 API key。

### 7.2 Later Features

这些能力在 MVP 闭环可运行后接入：

- Alpaca / Polygon / OpenBB 真实数据；
- VPS scanner 和通知；
- TradingView webhook ingestion；
- Alpaca paper account tracking；
- Lumibot paper execution adapter；
- vectorbt parameter sweeps；
- Qlib factor/ML research adapter；
- reports/signals thin UI。

## 8. Product Objects

| Object | Purpose |
|---|---|
| `StrategySpec` | 策略真源 |
| `StrategyVersion` | spec 的版本化实现 |
| `BacktestRun` | 历史测试结果 |
| `Signal` | scanner 产生的候选市场事件 |
| `ReviewCard` | LLM 生成的结构化上下文审查 |
| `TradeJournalEntry` | 用户决策和结果记录 |
| `WeeklyReview` | 周期改进总结 |

## 9. Key User Journeys

### 9.1 Create Strategy

```text
User describes a strategy idea.
Codex writes a draft StrategySpec.
System validates the spec.
Codex generates Python and Pine artifacts.
System runs backtest.
Report explains behavior and risks.
```

### 9.2 Promote Strategy

```text
User reviews report.
Spec and code pass validation.
Strategy moves from draft to approved.
User explicitly activates it for scanning.
```

### 9.3 Scan And Review Signal

```text
Runner scans active strategy.
Signal is logged.
LLM review card is generated when enabled.
User receives signal and context.
User trades manually or skips.
```

### 9.4 Journal And Improve

```text
User records action and outcome.
Codex reads reports and journal.
Weekly review proposes improvements.
New ideas become draft strategy changes.
```

## 10. Acceptance Criteria

MVP 完成条件：

1. Fresh clone 可以运行 `oc doctor`。
2. 样例 `StrategySpec` 通过 schema validation。
3. Codex 可以根据自然语言 prompt 生成 draft spec。
4. 系统可以从 spec 生成或对齐 Python 策略逻辑。
5. 系统可以从同一份 spec 生成 Pine Script。
6. 样例 backtest 生成 Markdown report。
7. scanner 生成 signal log。
8. journal entry 可以关联到 signal。
9. weekly review 可以总结 reports 和 journal。
10. 配置 API key 后，LLM review 输出 schema-valid review card。

## 11. Implementation Phases

### Phase 0: Repository Skeleton

- README；
- AGENTS.md；
- `.agents/skills`；
- `pyproject.toml`；
- CLI skeleton；
- schemas；
- sample data；
- reports and journal folders。

### Phase 1: Strategy Loop

- StrategySpec schema；
- sample strategy；
- spec validation；
- Python indicator functions；
- Python backtest/scanner；
- Pine export；
- backtest report；
- signal log；
- journal entry。

### Phase 2: Codex Workflow

- strategy-designer skill；
- python-backtest-writer skill；
- pine-exporter skill；
- signal-parity-reviewer skill；
- weekly-reviewer skill；
- AGENTS.md lifecycle and verification rules。

### Phase 3: Review And Notifications

- review card schema；
- LLM review service；
- local notification；
- weekly review command。

### Phase 4: Data And Deployment

- Alpaca/Polygon/OpenBB data adapters；
- VPS scanner；
- TradingView webhook log ingestion。

### Phase 5: Execution And Research Adapters

- Alpaca paper tracking；
- Lumibot paper execution adapter；
- vectorbt parameter research；
- Qlib factor/ML research adapter。

## 12. Operating Principles

- `StrategySpec` is the source of truth.
- Python and Pine artifacts come from the same spec.
- Signals are logged before review.
- LLM review is structured and evidence-based.
- Journal entries preserve user decisions.
- Active strategy changes use lifecycle controls.
- Broker write access is introduced through a later approval-gated adapter.
- Every feature has a CLI path before a UI path.

## 13. Documentation Standard

本文档采用以下标准：

- 先定义产品、用户和问题；
- 再定义技术架构、范围和流程；
- 用验收条件约束 MVP 完成状态；
- 把背景研究放在 Context Summary；
- 把具体实现步骤放在 Build Handoff；
- 保持文档可被新会话独立读取。

## 14. Sources

- Atlassian PRD guidance: https://www.atlassian.com/agile/product-management/requirements
- Diátaxis documentation framework: https://diataxis.fr/
- OpenAI Codex AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- OpenAI Codex Skills: https://developers.openai.com/codex/skills
- OpenAI Codex MCP: https://developers.openai.com/codex/mcp
