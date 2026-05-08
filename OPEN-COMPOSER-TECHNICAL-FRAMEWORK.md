# Open Composer 技术框架

Date: 2026-05-08

## 1. 目的

这份文档回答 Open Composer 到底要如何实现。

它补充产品 MVP 文档没有展开的部分：

- Codex 具体怎么用；
- Skill 放在哪里，负责什么；
- MCP 怎么接；
- 量化后端用什么；
- 回测怎么跑；
- Alpaca 怎么接；
- Qlib 是否必须；
- LLM API 在哪里调用；
- 系统是在本地跑、VPS 跑，还是上传到某个平台跑。

## 2. 深层意图

这个项目真正要解决的问题不是“选哪个库”，而是：

> 如何让一个非专业用户通过对话驱动 Codex，持续生成、测试、扫描、审查和复盘策略，同时避免做成脆弱的自动交易机器人？

因此需要分层：

```text
Codex workbench layer
  -> 产品规则和 skills
  -> 量化后端
  -> 数据 adapters
  -> 回测和扫描 runners
  -> LLM review service
  -> 审计存储
  -> 可选 broker / paper adapters
```

## 3. 总体架构

```text
User
  -> Codex / Claude Code
    -> AGENTS.md + repo skills
    -> strategy spec
    -> Python strategy code
    -> tests and backtests

Runtime CLI
  -> data adapter
  -> indicator engine
  -> backtest engine
  -> scan engine
  -> risk engine
  -> LLM review service
  -> journal and reports

External adapters
  -> Alpaca market data / paper account
  -> OpenBB data tools
  -> optional Financial Datasets / SEC / news
  -> optional TradingView export
  -> optional Qlib research adapter
```

核心原则：

```text
Codex 构建和改进系统。
Runner 执行确定性流程。
LLM 只在候选信号后审查上下文。
用户决定是否交易。
```

## 4. 推荐目录结构

```text
open-composer/
  README.md
  AGENTS.md
  pyproject.toml
  Makefile
  .env.example

  .agents/
    skills/
      strategy-designer/SKILL.md
      backtest-reviewer/SKILL.md
      signal-reviewer/SKILL.md
      risk-reviewer/SKILL.md
      weekly-reviewer/SKILL.md

  .codex/
    config.example.toml
    hooks.example.json

  schemas/
    strategy_spec.schema.json
    signal.schema.json
    review_card.schema.json
    event_feature.schema.json
    trade_journal.schema.json

  strategy_specs/
    drafts/
    approved/
    active/
    retired/

  open_composer/
    cli.py
    config.py
    models/
    data/
    indicators/
    strategies/
    backtest/
    scan/
    risk/
    review/
    journal/
    adapters/
      alpaca/
      openbb/
      qlib/
      tradingview/

  data/
    sample/
    cache/

  reports/
    backtests/
    scans/
    reviews/
    weekly/

  journal/
    trades/
    decisions/

  tests/
    fixtures/
```

## 5. 哪些可以直接做，哪些依赖外部接入

### 5.1 不需要外部 key 就能做

- 项目结构；
- `AGENTS.md`；
- repo skills；
- strategy spec schema；
- sample data；
- data loader；
- indicator engine；
- backtest runner；
- sample data scan runner；
- Markdown / JSON reports；
- SQLite audit store；
- journal；
- 基于本地 reports 的 weekly review。

这些足够验证产品核心闭环。

### 5.2 需要 OpenAI key 或兼容 LLM provider

- structured review card；
- 文本事件提取；
- 新闻/财报/SEC 摘要；
- 自动 weekly natural-language analysis。

Codex 本身是策略工程入口，runtime LLM review 是另一个独立层。

### 5.3 需要 Alpaca

- 美股/ETF 行情；
- paper account reader；
- paper positions / orders 展示；
- 可选 paper order adapter。

Alpaca 不是 MVP 的必需项。sample data MVP 可以先不接 Alpaca。

### 5.4 需要 MCP 配置

- Codex 通过 OpenBB 做金融数据查询；
- Codex 通过 Alpaca MCP 检查 paper account；
- Codex 通过其他 MCP 做研究。

MCP 不应该成为 core scanner 的硬依赖。scanner 应该调用稳定的 provider adapter。

### 5.5 后续才需要的 adapter

- Qlib factor research adapter；
- vectorbt parameter sweep adapter；
- QuantConnect / LEAN export；
- TradingView / Pine export；
- automated paper execution。

这个分阶段设计能避免一开始就陷入大型框架集成。

## 6. Codex 层

### 6.1 AGENTS.md

`AGENTS.md` 是 Codex 的项目级规则文件。

它应该定义：

- 产品目标；
- 策略生命周期；
- 禁止动作；
- 必须运行的验证；
- 报告要求；
- 数据假设；
- no live trading policy；
- active strategy 修改规则；
- secrets 处理规则。

OpenAI Codex 文档说明，`AGENTS.md` 用于给 Codex 提供项目指导，并按范围合并指导规则。这适合作为 Open Composer 的第一层约束。

### 6.2 Repo Skills

Open Composer 应该在仓库里提供 skills：

```text
.agents/skills/
```

每个 skill 是一个工作流说明和可选脚本/参考资料。

MVP skills：

1. `strategy-designer`
   - 将自然语言变成 strategy spec；
   - 只在必要时追问；
   - 只能写 draft，不直接写 active。

2. `backtest-reviewer`
   - 审查回测假设；
   - 检查 lookahead risk；
   - 检查样本量和指标。

3. `signal-reviewer`
   - 审查候选信号；
   - 确保 review card schema 被使用。

4. `risk-reviewer`
   - 检查 exposure、stop、invalidation、news risk、event conflict。

5. `weekly-reviewer`
   - 读取 journal 和 reports；
   - 输出策略和行为改进建议。

注意：Skill 是工作流约束，不是硬安全边界。硬约束来自 schema、runner、测试、权限隔离和人工确认。

### 6.3 Codex Hooks

hooks 可以做辅助防线：

- 阻止 live order 命令；
- 修改 active strategy 时提醒；
- 策略变更后提示运行 tests/backtest；
- 阻止提交 secrets。

hooks 不能当成唯一安全边界。

## 7. MCP 层

MCP 是给 Codex 接工具和数据的方式，不是产品 runtime 的核心。

MVP 用法：

- OpenBB MCP 用于金融数据探索；
- Alpaca MCP 只读检查 paper account；
- docs/search MCP 用于研究。

边界：

```text
MCP 可以帮助 Codex 查数据和理解上下文。
MCP 不应该默认执行交易。
```

Codex 支持 MCP，并可通过项目配置示例提供安全默认值。

### 7.1 OpenBB MCP

OpenBB MCP 适合：

- 查询行情和基本面；
- 查询宏观或经济数据；
- 做研究探索；
- 辅助 Codex 理解金融上下文。

但 runtime scanner 不应该依赖 MCP。scanner 应该用 provider adapter。

### 7.2 Alpaca MCP

Alpaca MCP 很有用，也有风险，因为它可能涉及：

- market data；
- account / positions；
- orders；
- portfolio。

MVP 规则：

- 只使用 paper key；
- 默认只读；
- 禁用 order create / replace / cancel；
- 确定性 runner 用 Alpaca SDK/data adapter；
- MCP 只用于 Codex-side research 和 account inspection。

## 8. 量化后端

Open Composer 需要一个量化后端，但第一版应当小而清晰。

它至少包括：

- data loading；
- bar normalization；
- indicator calculation；
- strategy evaluation；
- backtest execution；
- scan execution；
- risk checks；
- report generation。

建议接口：

```text
DataProvider
IndicatorEngine
StrategyRunner
BacktestEngine
ScanEngine
RiskEngine
ReportWriter
```

这样可以避免被某一个框架锁死。

## 9. 回测框架选择

### 9.1 MVP 默认选择

第一版用简单内部 engine 或 `backtesting.py`。

原因：

- 容易读；
- 容易让 Codex 修改；
- 足够支持规则型策略；
- 比 Qlib 轻；
- 更适合 15m / 1h 的 manual signal 策略。

### 9.2 vectorbt adapter

后续加 vectorbt，用于：

- 批量参数扫描；
- 快速向量化研究；
- 多策略对比。

它适合研究加速，但不是第一条闭环的必要条件。

### 9.3 Qlib adapter

Qlib 不应作为 MVP 底座。

Qlib 更适合：

- 因子研究；
- ML 模型；
- daily / multi-day prediction；
- 更正式的数据和模型 pipeline；
- 后续更专业的量化研究。

推荐关系：

```text
Open Composer StrategySpec
  -> internal runner
  -> optional Qlib adapter later
```

这样既保留 Qlib 的能力，又不让第一版复杂度失控。

## 10. 数据层

MVP 数据层要简单、可审计。

推荐：

- sample data 用于无 key 启动；
- Parquet/CSV 保存 OHLCV bars；
- SQLite 保存 metadata 和审计状态；
- provider adapters 接真实数据。

数据来源分层：

1. Sample provider
   - 无 API key；
   - 用于 onboarding、测试和 demo。

2. Alpaca provider
   - 美股/ETF 行情；
   - paper account context；
   - 适合 manual trading workflow。

3. OpenBB provider
   - 研究数据；
   - 宏观、基本面、新闻等。

4. Event/news provider
   - Alpaca news、OpenBB、RSS、Financial Datasets、SEC 等；
   - 统一转成 `EventFeature`。

## 11. Alpaca 集成

Alpaca 不是策略运行平台。

策略 runner 运行在：

- 用户电脑；
- VPS；
- 或其他定时环境。

Alpaca 提供：

- market data；
- paper account；
- paper order API；
- account / positions 状态；
- 模拟交易 dashboard。

MVP 阶段：

```text
Phase 1: 不需要 Alpaca，sample data 先跑通
Phase 2: Alpaca data adapter
Phase 3: Alpaca paper account reader
Phase 4: optional paper order adapter，默认关闭
```

如果要做 5m/15m 扫描，电脑或 VPS 必须持续运行。Alpaca 不会替你托管 Python 策略。

## 12. LLM Runtime 层

runtime LLM 和 Codex 分开。

Codex 负责工程任务：

- 写策略；
- 写测试；
- 跑回测；
- 改代码；
- 写报告；
- 做周复盘。

直接 LLM API 负责运行期结构化任务：

- event extraction；
- headline summary；
- SEC filing summary；
- candidate signal review；
- risk card generation。

LLM 输出必须使用结构化 schema，例如 `ReviewCard` 和 `EventFeature`。

LLM 不负责：

- position sizing；
- 下单；
- 覆盖风控；
- 全市场连续扫描。

## 13. CLI 命令

建议 CLI：

```text
oc init
oc doctor
oc spec validate <path>
oc strategy new <name>
oc backtest <strategy>
oc scan <strategy>
oc review-signal <signal-id>
oc journal add <signal-id>
oc weekly-review
oc data fetch --provider alpaca --symbols QQQ,SPY --timeframe 15m
```

Codex 可以调用这些命令完成策略开发，用户也可以直接调用。

## 14. 运行和部署

MVP 运行方式：

- 本地电脑用于早期测试；
- cron / APScheduler 用于定时扫描；
- VPS 用于稳定 5m/15m 扫描；
- GitHub Actions 只适合低频 review，不适合精确日内扫描。

注意：

- 如果电脑关机，本地 scanner 会停止；
- 如果想稳定 15m 扫描，建议 VPS；
- manual trading 场景下，通知质量比极低延迟更重要。

## 15. 安全模型

安全要分层：

1. 默认没有 live trading key。
2. broker write adapter 默认关闭。
3. MCP order tools 默认禁用。
4. 策略生命周期：draft -> approved -> active -> retired。
5. active strategy 修改必须明确确认。
6. LLM 输出必须 schema 校验。
7. runner 执行风险规则。
8. journal 记录所有决策。

不要只靠 prompt 保证安全。

## 16. MVP 构建顺序

### Step 1: Skeleton

- Python package；
- CLI；
- config；
- sample data；
- schemas；
- `AGENTS.md`；
- repo skills。

### Step 2: Quant Core

- data loader；
- indicator engine；
- simple strategy runner；
- backtest；
- report writer。

### Step 3: Codex Workflow

- `strategy-designer` skill；
- `backtest-reviewer` skill；
- required validation commands；
- generated strategy tests。

### Step 4: Scanner

- active strategy registry；
- bar-close scan；
- signal output；
- local notification。

### Step 5: LLM Review

- review card schema；
- OpenAI structured output；
- event feature cache。

### Step 6: Adapters

- Alpaca data provider；
- Alpaca paper account reader；
- OpenBB MCP config；
- optional Qlib adapter later。

## 17. 参考来源

- OpenAI Codex skills: https://developers.openai.com/codex/skills
- OpenAI Codex MCP: https://developers.openai.com/codex/mcp
- OpenAI Codex hooks: https://developers.openai.com/codex/hooks
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Alpaca paper trading: https://docs.alpaca.markets/docs/paper-trading
- Alpaca MCP server: https://docs.alpaca.markets/docs/alpaca-mcp-server
- OpenBB MCP: https://docs.openbb.co/odp/python/extensions/interface/openbb-mcp
- Microsoft Qlib: https://github.com/microsoft/qlib
- backtesting.py: https://kernc.github.io/backtesting.py/
- vectorbt: https://vectorbt.dev/
