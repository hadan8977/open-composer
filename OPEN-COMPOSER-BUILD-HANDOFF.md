# Open Composer Build Handoff

Date: 2026-05-08

## 1. 这份文档的用途

这份文档是给下一个实现会话看的唯一入口。

它的目标是让新的 Codex 会话快速、深入、完整地理解：

- 我们到底要做什么产品；
- 为什么原来的 EvoQ 方向不适合；
- 为什么不是简单 Composer clone；
- 技术路线为什么不是 Qlib-first，也不是 Lumibot-first；
- 第一版应该先实现什么；
- 哪些能力后续再接；
- 新会话应该从哪里开始写代码。

如果本仓库其他文档和这份文档有冲突，以这份文档为准。

## 2. 一句话产品定义

Open Composer 是一个 **基于 Codex 的个人对话式策略工作台**。

它让用户用自然语言提出交易想法，Codex 把想法变成结构化策略、Python 回测、TradingView Pine Script、信号扫描、报告和复盘材料；系统只做信号提醒和审查，用户先保持手动交易。

更准确地说，Open Composer 第一版不是：

- 自动交易机器人；
- 完整 Web dashboard；
- Qlib 研究平台；
- Lumibot paper trading wrapper；
- Composer 的完整开源复刻。

它第一版是：

```text
AI 对话式策略生成
  + 5m/15m/1h/daily 信号提醒
  + Python 回测
  + TradingView Pine export
  + 信号记录
  + LLM 候选信号审查
  + 手动交易 journal
  + Codex 周期性复盘
```

## 3. 用户真实需求

用户不是专业量化团队，也不是 AI 研究员。

用户想要：

- 关注美股；
- 通过自然语言持续生成和优化策略；
- 尽可能利用 Codex/Claude Code 的能力；
- 少手动操作复杂流程；
- 不再维护一个 dashboard-first 的复杂系统；
- 最终辅助交易获利并学习；
- 先手动交易，不急着自动接 broker；
- 可以接受 5m、15m、1h、daily、weekly 等频率；
- 不追求秒级或 tick 级高频。

用户特别在意：

- Codex 和直接 LLM 的职责区别；
- Skill/MCP 是否足以约束系统；
- 是否必须 Qlib；
- 是否应该 Lumibot + Alpaca；
- 是否需要 TradingView/Pine；
- LLM 和量化系统到底怎么结合才是主流、成熟、可行的方式。

## 4. 从对话中得到的关键结论

### 4.1 EvoQ 失败点

EvoQ 的问题不是功能少，而是产品形态偏了：

- dashboard-first；
- 太技术化；
- 用户打开网页后不知道怎么配置和下一步做什么；
- 需要用户手动操作过多环节；
- 系统治理和架构复杂度压过了用户成功路径。

Open Composer 不应沿着 EvoQ 继续修。

### 4.2 Composer 值得学，但不能照搬

Composer 最值得学习的是：

```text
自然语言想法
  -> 结构化策略
  -> 插入编辑器
  -> 回测
  -> 迭代
```

但 Composer 更偏：

- 低频；
- 资产配置；
- 日频到年频调仓；
- 封闭产品和券商体验；
- 自动交易和 KYC 账户体系。

用户现在的目标更像：

```text
Composer-like 策略生成
  + Capitalise.ai-like 自然语言提醒
  + TradingView-like 多周期图表信号
  + LevelFields-like 事件理解
  + Codex-like 策略工程
```

所以第一版不是 Composer clone，而是个人版 AI signal workbench。

### 4.3 Qlib 不作为第一版地基

Qlib 是强大的 AI-oriented quantitative investment platform，适合：

- ML 因子研究；
- 横截面 alpha；
- 模型训练；
- 日频/多日预测；
- 更系统的量化 research pipeline。

但它不适合第一版作为地基，因为：

- 数据格式和 workflow 偏重；
- 不直接解决 5m/15m 手动信号；
- 不直接解决 TradingView/Pine 提醒；
- 不直接解决对话式策略结构；
- 会让新项目过早进入“研究平台”复杂度。

结论：

```text
Qlib = 后续高级 research adapter
不是 MVP core
```

### 4.4 Lumibot + Alpaca 也不作为第一版地基

之前曾建议 Lumibot + Alpaca paper，因为如果目标是：

```text
策略 -> 回测 -> dry-run -> Alpaca paper 下单
```

Lumibot 很合适。

但后来用户明确说：

- 不一定要接 API 自动交易；
- 最终更偏手动交易；
- 5m/15m 信号提醒可以接受；
- 交易接口不是第一核心；
- 信号、解释、复盘才是第一核心。

因此 Lumibot 不应第一版主导架构。

结论：

```text
Lumibot = 后续 Alpaca paper execution adapter
不是 MVP core
```

### 4.5 第一版真正核心是 StrategySpec

Open Composer 的核心不是某个库，而是统一的策略协议：

```text
StrategySpec
```

它是：

- 用户自然语言想法的结构化结果；
- Codex 生成 Python/Pine 的源头；
- 回测、扫描、报告、复盘的共同依据；
- 后续导出 Lumibot/Qlib/LEAN 的桥梁；
- 类似 Composer blocks/symphony 的开放版本。

## 5. 最终技术路线

最终技术路线：

```text
StrategySpec-first
  -> Codex repo skills
  -> Python backtest / scanner
  -> Pine Script export
  -> Python/Pine signal parity
  -> reports + signal logs + journal
  -> optional LLM review card
  -> later real data / VPS scanner
  -> later Alpaca paper tracking
  -> later Lumibot paper execution
  -> later vectorbt / Qlib / LEAN adapters
```

这条路线兼顾：

- Composer 的结构化策略生成；
- Codex 的代码工程能力；
- TradingView 的手动交易提醒体验；
- LLM 的事件和文本分析能力；
- 后续 Alpaca paper execution 路径；
- 后续 Qlib/LEAN 高级扩展路径。

## 6. 第一版架构

```text
User
  -> Codex / Claude Code
    -> AGENTS.md
    -> repo skills
    -> StrategySpec YAML
    -> Python backtest / scanner
    -> Pine Script
    -> parity report
    -> backtest report

Runtime
  -> sample data first
  -> deterministic scanner
  -> signal card
  -> optional LLM review
  -> notification
  -> manual trade
  -> journal
  -> weekly review

Adapters later
  -> Alpaca / Polygon / OpenBB data
  -> TradingView alert/webhook
  -> Lumibot + Alpaca paper
  -> vectorbt parameter sweep
  -> Qlib factor research
  -> LEAN mature deployment
```

## 7. Codex、LLM、MCP、Runner 的职责

### 7.1 Codex

Codex 是策略工程师和复盘工程师。

它负责：

- 从自然语言生成 StrategySpec；
- 写 Python 回测/扫描代码；
- 写 Pine Script；
- 写测试；
- 跑回测；
- 生成报告；
- 检查信号一致性；
- 周期性复盘 journal 和 reports；
- 提出策略改进。

Codex 不负责：

- 实时每 5 分钟临场决定交易；
- 直接下单；
- 直接改 active strategy 而不走 lifecycle；
- 作为 broker 权限持有者。

### 7.2 直接 LLM API

直接 LLM API 是运行期轻量分析器。

它负责：

- 新闻摘要；
- 财报/公告/SEC filing 摘要；
- 事件分类；
- 候选信号 review card；
- 风险解释；
- 反方观点；
- 交易前 checklist。

它不负责：

- 写代码；
- 扫描全市场；
- 下单；
- 任意调整仓位；
- 覆盖风控。

### 7.3 MCP

MCP 是工具层，不是产品核心，也不是安全边界。

可用于：

- Codex 查询 OpenBB 数据；
- Codex 查询 Alpaca paper account；
- Codex 查文档和研究资料。

不要用于：

- 直接下单；
- runtime scanner 硬依赖；
- 作为唯一权限控制。

### 7.4 Runner

Runner 是确定性执行层。

它负责：

- 加载数据；
- 计算指标；
- 扫描信号；
- 运行回测；
- 写 logs；
- 写 reports；
- 写 journal；
- 触发 LLM review。

## 8. 第一版必须实现的能力

### 8.1 StrategySpec + Schema

先定义 `StrategySpec`。

示例：

```yaml
name: qqq_pullback_15m
timeframe: 15m
universe: [QQQ, SPY]

entry:
  all:
    - "close > ema(close, 200)"
    - "rsi(close, 14) < 35"
    - "volume > sma(volume, 20)"

exit:
  any:
    - "rsi(close, 14) > 55"
    - "close < ema(close, 50)"

risk:
  max_trades_per_day: 3
  stop_loss_pct: 1.2
  take_profit_pct: 2.0

execution:
  mode: manual_signal
  signal_on: bar_close
  fill_assumption: next_bar_open
```

第一版 schema 至少覆盖：

- `name`
- `timeframe`
- `universe`
- `entry`
- `exit`
- `risk`
- `execution`
- `data_assumptions`

### 8.2 Python 回测和扫描

第一版不要做机构级大引擎。

目标是：

- 能跑 sample data；
- 能验证规则逻辑；
- 能输出信号时间点；
- 能输出简单交易记录；
- 能输出收益、回撤、胜率、交易数；
- 能给 Codex 低成本修改。

推荐：

- 用 Python + pandas 实现轻量 scanner；
- 可选接 `backtesting.py`；
- 暂不把 vectorbt 作为第一核心；
- 暂不接 Qlib。

### 8.3 Pine Script Export

Pine export 进入第一版。

原因：

- 用户最终是手动交易；
- TradingView 是自然的看图和提醒工具；
- 5m/15m 信号很适合用 TradingView 观察；
- Pine 可以让策略进入用户实际交易界面。

但必须明确：

```text
StrategySpec 是策略真源。
Pine Script 是导出物。
TradingView alert 是提醒出口，不是审计真源。
```

### 8.4 Python/Pine Signal Parity

必须建立“信号一致性”概念。

风险：

```text
Python 回测盈利
TradingView alert 实盘触发不一致
```

第一版可以先做到：

- 从同一个 StrategySpec 编译 Python 和 Pine；
- Python 输出 expected signal timestamps；
- Pine 文件生成时附带 parity checklist；
- 后续通过 TradingView alert webhook logs 和 Python scanner logs 做对比。

### 8.5 Reports

每次回测输出 Markdown report。

报告必须包括：

- 策略说明；
- 时间周期；
- 数据源；
- 样本范围；
- 信号数量；
- 交易数量；
- 胜率；
- 最大回撤；
- 关键风险；
- 是否适合 5m/15m/1h；
- 是否建议进入 approved。

### 8.6 Journal

手动交易产品必须有 journal。

每个 signal 记录：

- signal id；
- strategy version；
- 时间；
- symbol；
- signal details；
- review card；
- 用户是否交易；
- entry / exit；
- 跳过原因；
- 情绪/主观理由；
- 后续表现。

## 9. 第一版不做什么

明确不要做：

- Web dashboard；
- Qlib-first；
- Lumibot-first；
- Alpaca 自动下单；
- MCP 直接下单；
- LLM 全市场扫描；
- LLM 直接决定仓位；
- 1m/tick 高频；
- multi-agent 自动交易；
- 复杂 portfolio optimizer。

## 10. 第二阶段再做什么

第一版跑通后再做：

- Alpaca/Polygon/OpenBB data adapter；
- VPS scanner；
- 通知；
- LLM review card；
- event/news context；
- TradingView alert webhook logs；
- weekly review。

## 11. 第三阶段再做什么

如果用户开始想要 paper execution：

- 接 Alpaca paper account reader；
- 生成 dry-run order proposal；
- 加 approval file；
- 再接 Lumibot + Alpaca paper；
- 默认不自动提交订单。

Lumibot 在这里才有价值。

## 12. 第四阶段再做什么

研究增强：

- vectorbt parameter sweep；
- Qlib factor/ML research；
- OpenBB MCP research；
- stronger statistical validation；
- optional LEAN export。

Qlib 在这里才有价值。

## 13. 推荐目录结构

```text
open-composer/
  README.md
  AGENTS.md
  CLAUDE.md
  pyproject.toml
  Makefile
  .env.example

  .agents/
    skills/
      strategy-designer/SKILL.md
      python-backtest-writer/SKILL.md
      pine-exporter/SKILL.md
      signal-parity-reviewer/SKILL.md
      risk-reviewer/SKILL.md
      weekly-reviewer/SKILL.md

  .codex/
    config.example.toml
    hooks.example.json

  strategy_specs/
    drafts/
    approved/
    active/
    retired/

  schemas/
    strategy_spec.schema.json
    signal.schema.json
    review_card.schema.json
    trade_journal.schema.json
    event_feature.schema.json

  open_composer/
    cli.py
    config.py
    models/
    compiler/
      spec_to_python.py
      spec_to_pine.py
    engines/
      scanner_engine.py
      backtest_engine.py
    adapters/
      data/
        sample.py
        alpaca.py
        polygon.py
        openbb.py
      notify/
        console.py
    review/
      llm_review.py
    risk/
    journal/
    reports/

  strategies_python/
    generated/
    custom/

  strategies_pine/
    generated/

  data/
    sample/
    cache/

  reports/
    backtests/
    parity/
    scans/
    reviews/
    weekly/

  signal_logs/
  journal/
  tests/
```

## 14. CLI 草案

第一版 CLI：

```text
oc init
oc doctor
oc spec validate <path>
oc spec promote <draft> --to approved
oc compile python <spec>
oc compile pine <spec>
oc backtest <spec>
oc scan <spec>
oc parity <spec>
oc journal add --signal <id>
oc weekly-review
```

第一阶段可以先实现：

```text
oc doctor
oc spec validate
oc compile pine
oc backtest
```

## 15. Skill 设计

### 15.1 strategy-designer

输入：用户自然语言想法。  
输出：draft StrategySpec。

规则：

- 不直接写 active；
- 必须声明 timeframe、universe、entry、exit、risk；
- 不清楚时先用保守默认值并写入 assumptions；
- 必须说明策略适合什么频率。

### 15.2 python-backtest-writer

输入：StrategySpec。  
输出：Python scanner/backtest code。

规则：

- 不允许未来函数；
- signal 默认 bar close 确认；
- fill 默认 next bar open；
- 输出 signal log。

### 15.3 pine-exporter

输入：StrategySpec。  
输出：Pine Script。

规则：

- Pine 是导出物；
- 逻辑必须和 Python 来自同一 spec；
- 写清 alert 条件。

### 15.4 signal-parity-reviewer

输入：Python signal log、Pine export、后续 TradingView alert log。  
输出：parity report。

规则：

- 标记 signal mismatch；
- 标记 bar close / repaint 风险；
- 标记无法验证的 Pine 行为。

### 15.5 risk-reviewer

输入：strategy、backtest report、signal。  
输出：风险审查。

规则：

- 检查 max trades；
- 检查 macro/event risk；
- 检查 overfit；
- 检查是否适合手动执行。

### 15.6 weekly-reviewer

输入：reports、signal logs、journal。  
输出：周复盘。

规则：

- 总结有效信号；
- 总结误报；
- 总结用户跳过/执行的影响；
- 只提出 draft 改进，不直接修改 active。

## 16. AGENTS.md 应包含的规则

新项目必须有 `AGENTS.md`。

建议规则：

```text
You are building Open Composer, a personal AI-assisted strategy workbench.

Core product:
- StrategySpec is the source of truth.
- Codex generates specs, Python backtests/scanners, Pine exports, reports, and tests.
- Runtime LLM only reviews candidate signals.
- Human keeps final trading decision.

Forbidden:
- Do not implement live trading in MVP.
- Do not give MCP tools broker write access.
- Do not make Qlib or Lumibot the MVP core.
- Do not create a web dashboard first.
- Do not let LLM scan the whole market continuously.

Required:
- Every strategy must have a spec.
- Every generated strategy must have tests or validation.
- Every backtest must produce a Markdown report.
- Every signal must be logged.
- Any active strategy change must go through lifecycle.
```

## 17. MVP 验收标准

MVP 成功的标准：

1. 新用户 clone 后能运行 `oc doctor`。
2. 不配置任何 broker key 也能跑 sample strategy。
3. Codex 能根据自然语言生成 StrategySpec。
4. StrategySpec 能通过 schema 校验。
5. 系统能生成 Python backtest/scanner。
6. 系统能生成 Pine Script。
7. 系统能输出 backtest report。
8. 系统能输出 signal log。
9. 系统能记录 journal。
10. 系统能生成 weekly review。

## 18. 新实现会话的第一批任务

新会话开始后，不要再调研产品方向，先实现骨架。

建议第一批任务：

1. 建 Python 项目结构。
2. 写 `AGENTS.md`。
3. 写 `.agents/skills` skeleton。
4. 写 `schemas/strategy_spec.schema.json`。
5. 写一个 sample StrategySpec。
6. 准备小型 sample OHLCV CSV。
7. 实现 `oc doctor`。
8. 实现 `oc spec validate`。
9. 实现最小 indicator functions：SMA、EMA、RSI。
10. 实现 sample backtest runner。
11. 实现 Pine export。
12. 输出第一份 backtest report。

这批任务完成后，再考虑 LLM review、Alpaca、VPS scanner。

## 19. 关键实现提醒

- 不要先做 UI。
- 不要先接 Alpaca。
- 不要先接 Qlib。
- 不要先接 Lumibot。
- 不要先做自动交易。
- 不要让 Codex 每 5 分钟当交易员。
- 第一版先证明：自然语言策略可以变成 spec、Python、Pine、报告和 journal。

## 20. 参考资料

- Composer Create with AI: https://help.composer.trade/article/108-create-with-ai
- Capitalise.ai Smart Notifications: https://support.capitalise.ai/en/articles/3339296-smart-notifications
- TradingView Strategy Alerts: https://www.tradingview.com/support/solutions/43000481368-strategy-alerts/
- TradingView Pine Alerts: https://www.tradingview.com/pine-script-docs/concepts/alerts/
- OpenAI Codex AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- OpenAI Codex Skills: https://developers.openai.com/codex/skills
- OpenAI Codex MCP: https://developers.openai.com/codex/mcp
- OpenAI Codex Hooks: https://developers.openai.com/codex/hooks
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Alpaca Paper Trading: https://docs.alpaca.markets/docs/paper-trading
- Alpaca News: https://docs.alpaca.markets/docs/streaming-real-time-news
- Lumibot Backtesting: https://lumibot.lumiwealth.com/backtesting.how_to_backtest.html
- Lumibot Alpaca Broker: https://lumibot.lumiwealth.com/brokers.alpaca.html
- backtesting.py: https://kernc.github.io/backtesting.py/
- vectorbt: https://vectorbt.dev/
- Microsoft Qlib: https://github.com/microsoft/qlib
- QuantConnect LEAN: https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine
