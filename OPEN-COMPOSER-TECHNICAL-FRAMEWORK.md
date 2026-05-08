# Open Composer 技术框架

Date: 2026-05-08

## 1. 最终技术结论

Open Composer 不应该 Qlib-first，也不应该 Lumibot-first。

最合适的技术路线是：

```text
StrategySpec-first
  -> Codex repo skills
  -> Python backtest / scanner
  -> Pine Script export
  -> signal card + journal
  -> optional LLM review
  -> later Alpaca data / VPS scanner
  -> later Lumibot + Alpaca paper execution
  -> later vectorbt / Qlib / LEAN adapters
```

原因很直接：

- 你当前最核心的产品目标是 **对话式策略生成 + 5m/15m/1h 信号提醒 + 手动交易复盘**。
- 这不是 Qlib 最擅长的 ML/factor research 场景。
- 也不是 Lumibot 最擅长的 backtest-to-paper/live execution 场景。
- 更接近 Composer + Capitalise.ai + TradingView 的组合：自然语言生成策略、验证策略、生成提醒、人工决策。

所以第一版应该以 **策略结构和信号一致性** 为核心，而不是以 broker runtime 为核心。

## 2. 为什么不是 Lumibot-first

之前“Lumibot + Alpaca paper”这个建议是合理的，但它适用于另一个目标：

```text
生成策略 -> 回测 -> dry-run -> Alpaca paper 下单
```

如果第一版就要做 paper execution，Lumibot 确实比纯自研脚本更合适，因为它提供 backtesting、broker 接入和从回测到 live/paper 的迁移路径。

但你后来把目标收敛成：

```text
AI 对话式策略生成
  + 5m/15m/1h 信号提醒
  + 手动交易
  + LLM/事件审查
  + 复盘
```

在这个目标下，Lumibot-first 会带来几个问题：

- 它会把第一版重心拉向 broker runtime；
- 会过早处理 order、broker、paper/live parity；
- 对 TradingView/Pine 这种手动交易提醒体验帮助有限；
- 对“策略 DSL / spec / 信号一致性 / 复盘”这些产品核心不是最短路径。

因此 Lumibot 应该作为 **Phase 3 paper execution adapter**，而不是 Phase 1 的产品地基。

## 3. 技术路线对比

| 路线 | 适合什么 | 不适合什么 | 在 Open Composer 中的位置 |
|---|---|---|---|
| StrategySpec-first | Composer-like 策略结构、版本、审计、导出 | 不能单独运行，必须配 runner/compiler | 产品核心 |
| Python backtesting.py / simple scanner | 快速验证规则型策略、生成信号、Codex 易修改 | 大规模参数扫描、成熟 broker runtime | Phase 1 主执行层 |
| TradingView / Pine export | 手动交易提醒、图表观察、bar-close signal | 不是策略真源，版本和 alert 管理有限 | Phase 1/2 必做导出层 |
| vectorbt | 大量参数扫描、快速批量研究 | paper/live runtime、事件驱动执行 | Phase 4 research adapter |
| Lumibot + Alpaca | paper execution、broker runtime、从 backtest 到 paper/live | 第一版手动信号产品会显得重 | Phase 3 execution adapter |
| Qlib | ML 因子、横截面 alpha、模型训练 | 5m/15m 手动信号、Composer-like UX | Phase 5 research backend |
| LEAN / QuantConnect | 成熟事件驱动引擎、多资产、复杂执行 | 个人 MVP 过重 | 后期成熟部署选项 |
| Alpaca-only scripts | 快速接 paper/data | 容易变散，缺少统一 spec 和回测一致性 | 只做 adapter |
| MCP tools | 给 Codex 查数据、查账户、查文档 | 不应作为安全边界或 runtime 核心 | 辅助工具层 |

## 4. 参考产品给出的方向

### 4.1 Composer

Composer 的关键不是“用哪个后端”，而是：

```text
自然语言 -> 策略结构 -> 插入编辑器 -> 回测
```

Open Composer 应该学习这个结构化策略体验，而不是直接模仿它的券商闭环。

### 4.2 Capitalise.ai

Capitalise.ai 的 Smart Notifications 说明了一个很重要的方向：

```text
自然语言条件 -> 市场/新闻/技术条件监控 -> 只提醒，不交易
```

这和你的第一版目标非常接近。

### 4.3 TradingView

TradingView 适合承担手动交易场景里的提醒和图表层。

但 TradingView strategy alert 的一个关键限制是：创建 alert 后，TradingView 服务器运行的是当时策略的一个副本，图表里的后续改动不会自动影响 alert。因此 Open Composer 不能把 TradingView 当策略真源。

正确做法是：

```text
StrategySpec 是真源
  -> Python 回测/扫描
  -> Pine export
  -> 对比 Python 和 Pine 信号一致性
  -> TradingView 只作为提醒/图表出口
```

## 5. 最终架构

```text
User conversation
  -> Codex
    -> AGENTS.md
    -> repo skills
    -> StrategySpec YAML
    -> Python strategy/backtest code
    -> Pine Script export
    -> signal parity check
    -> reports

Runtime
  -> local/VPS scanner
  -> market data adapter
  -> deterministic signal
  -> optional LLM review sidecar
  -> notification
  -> manual trade
  -> journal
  -> weekly Codex review

Optional adapters
  -> Alpaca data / paper account
  -> Lumibot paper execution
  -> vectorbt research
  -> Qlib ML/factor research
  -> LEAN mature deployment
```

关键原则：

1. `StrategySpec` 是策略真源。
2. Codex 先生成 spec，再生成代码。
3. Python backtest/scanner 和 Pine export 必须能对齐信号。
4. TradingView 可以提醒，但不能成为唯一策略来源。
5. Alpaca 提供数据和 paper account，不托管策略。
6. Lumibot 只在需要 paper execution 时前移。
7. Qlib 只在需要 ML/factor research 时引入。

## 6. 推荐目录结构

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
      alpaca-paper-operator/SKILL.md

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
      spec_to_lumibot.py
    engines/
      backtesting_py_engine.py
      scanner_engine.py
      vectorbt_engine.py
      lumibot_engine.py
      qlib_engine.py
    adapters/
      data/
        sample.py
        alpaca.py
        polygon.py
        openbb.py
      broker/
        alpaca_paper.py
      notify/
        console.py
        telegram.py
    review/
      llm_review.py
      event_features.py
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

## 7. 核心产物：StrategySpec

`StrategySpec` 是 Open Composer 的核心资产。

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
```

Codex 的主要任务：

1. 根据对话生成 spec。
2. 根据 spec 生成 Python 回测/扫描代码。
3. 根据 spec 生成 Pine Script。
4. 对比 Python 和 Pine 的信号是否一致。
5. 生成回测报告和适用频率判断。
6. 将策略推进到 approved 或 active，但必须经用户确认。

## 8. 第一版必须做什么

### 8.1 Spec + Schema

必须先做：

- strategy spec；
- schema validation；
- lifecycle：draft -> approved -> active -> retired。

这是产品核心。

### 8.2 Python Backtest / Scanner

第一版用 `backtesting.py` 或轻量 scanner。

目标不是做最完美的机构级回测，而是：

- 能跑 sample data；
- 能验证策略逻辑；
- 能输出交易和信号；
- 能让 Codex 低成本修改；
- 能和 Pine export 做信号一致性检查。

### 8.3 Pine Export

Pine export 应该进入第一版。

原因：

- 你最终是手动交易；
- TradingView 是最自然的观察和提醒入口；
- 5m/15m 策略用 TradingView 看图和 alert 很方便；
- Pine export 能让策略从代码世界进入交易者日常界面。

但要明确：

- Pine 不是策略真源；
- alert 不是审计真源；
- StrategySpec 和本地 reports 才是真源。

### 8.4 Signal Parity

必须做 Python/Pine 信号一致性检查。

否则会出现：

```text
Python 回测看起来有效
TradingView 实盘提醒却不一致
```

第一版至少要输出：

- Python signal timestamps；
- Pine-equivalent signal timestamps；
- mismatch report。

### 8.5 Journal + Weekly Review

手动交易产品必须有 journal。

每个信号要记录：

- 是否交易；
- 是否跳过；
- 跳过原因；
- 交易结果；
- 情绪和环境；
- 后续复盘。

## 9. 第二版再做什么

### 9.1 Real Data / VPS Scanner

当 sample data 和 Pine export 跑通后，再接：

- Alpaca data；
- Polygon data；
- OpenBB data；
- VPS scheduler；
- notification。

如果电脑关机，本地 scanner 就停止。稳定 5m/15m 扫描需要 VPS。

### 9.2 LLM Review

LLM review 只在候选信号后运行：

```text
deterministic signal
  -> fetch event context
  -> structured review card
  -> user manual decision
```

LLM 不做全市场扫描，不做每根 bar 交易决策。

### 9.3 Alpaca Paper Record

Alpaca paper 可以先做记录和 dry-run，不一定下单。

推荐顺序：

```text
paper account reader
  -> dry-run proposed order
  -> approval file
  -> optional paper order
```

## 10. Lumibot 的正确位置

Lumibot 是重要的，但不是第一版主轴。

应该在以下条件成立时引入：

- 用户真的想把策略从 signal-only 推到 paper execution；
- 需要 backtest 和 broker-connected runtime 更一致；
- 需要 Alpaca paper order；
- 策略已经通过 Python/Pine/manual review 验证。

引入方式：

```text
StrategySpec
  -> spec_to_lumibot.py
  -> Lumibot strategy
  -> Alpaca paper broker
  -> dry-run first
  -> optional paper order
```

这保留了之前 Lumibot + Alpaca 的价值，但不会让它过早主导产品结构。

## 11. Qlib 的正确位置

Qlib 不适合第一版。

它适合：

- ML 因子研究；
- 横截面 alpha；
- 日频/多日预测；
- 模型训练；
- 更系统化的 research pipeline。

当 Open Composer 进入“从策略规则扩展到因子挖掘”阶段，再接 Qlib。

## 12. LEAN 的正确位置

LEAN / QuantConnect 是成熟但重的路线。

适合：

- 复杂事件驱动；
- 多资产；
- 期权；
- 更严肃的 live deployment；
- 更成熟的 broker/data 生态。

不适合个人 MVP 起步。

## 13. MCP 的正确位置

MCP 是 Codex 的外部工具层，不是 runtime 核心。

可以用：

- OpenBB MCP 查数据；
- Alpaca MCP 查看 paper account；
- docs/search MCP 做研究。

不要用：

- MCP 直接下单；
- MCP 作为安全边界；
- MCP 作为 scanner 运行时依赖。

## 14. 阶段路线

### Phase 0: 文档和骨架

- `AGENTS.md`
- `.agents/skills`
- `StrategySpec` schema
- sample data
- CLI skeleton
- reports/journal directories

### Phase 1: Composer-lite 核心

- 自然语言 -> StrategySpec；
- StrategySpec -> Python backtest；
- StrategySpec -> Pine Script；
- Python/Pine signal parity report；
- 回测报告；
- journal。

这阶段不需要 Alpaca、不需要 Qlib、不需要 Lumibot。

### Phase 2: 真实信号系统

- Alpaca/Polygon data adapter；
- VPS scanner；
- notification；
- LLM review card；
- event/news context。

### Phase 3: Alpaca Paper / Lumibot

- Lumibot adapter；
- Alpaca paper account reader；
- dry-run order proposal；
- approval-gated paper order。

### Phase 4: Research 扩展

- vectorbt parameter sweep；
- Qlib factor/ML research；
- OpenBB research MCP；
- stronger statistical validation。

### Phase 5: 成熟部署

- optional LEAN export；
- thin UI；
- multi-strategy portfolio view；
- better data retention and monitoring。

## 15. 最终技术选择

第一版写成：

```text
Product Core:
  StrategySpec + Codex Skills + CLI + reports + journal

First Execution Layer:
  Python backtesting/scanner + Pine export

Manual Trading Surface:
  TradingView alerts + local/VPS notification

AI Layer:
  Codex for strategy engineering
  LLM API for structured signal/event review

Data:
  sample data first
  Alpaca/Polygon/OpenBB later

Paper Execution:
  Lumibot + Alpaca later

Advanced Research:
  vectorbt first
  Qlib later
  LEAN much later
```

这条路线最符合当前产品：

- 像 Composer 一样有结构化策略；
- 像 Capitalise.ai 一样可以提醒而不交易；
- 像 TradingView 一样适合手动看图；
- 用 Codex 生成和维护代码；
- 保留 Lumibot/Alpaca paper 路径；
- 保留 Qlib/LEAN 高级路径。

## 16. 参考来源

- Composer Create with AI: https://help.composer.trade/article/108-create-with-ai
- Capitalise.ai Smart Notifications: https://support.capitalise.ai/en/articles/3339296-smart-notifications
- TradingView Strategy Alerts: https://www.tradingview.com/support/solutions/43000481368-strategy-alerts/
- OpenAI Codex AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- OpenAI Codex Skills: https://developers.openai.com/codex/skills
- OpenAI Codex MCP: https://developers.openai.com/codex/mcp
- OpenAI Codex Hooks: https://developers.openai.com/codex/hooks
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Lumibot Backtesting: https://lumibot.lumiwealth.com/backtesting.how_to_backtest.html
- Lumibot Alpaca broker: https://lumibot.lumiwealth.com/brokers.alpaca.html
- Alpaca Paper Trading: https://docs.alpaca.markets/docs/paper-trading
- vectorbt: https://vectorbt.dev/
- backtesting.py: https://kernc.github.io/backtesting.py/
- Microsoft Qlib: https://github.com/microsoft/qlib
- QuantConnect LEAN: https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine
