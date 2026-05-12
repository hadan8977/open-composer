# Open Composer 当前检查结果与个人使用版优先级审查

日期：2026-05-12

## 结论

当前项目已经不是“只有设计稿”的阶段，而是一个可运行的个人 AI 策略工作台 MVP：CLI、文件、报告、Dashboard read model、NautilusTrader 单标的回测、Alpaca Paper 安全门、feature packet 回放入口和部署前 readiness 都已经接上。

但它还不能声明为“能力补全完成”。剩余工作必须围绕闭环能力推进，而不是继续扩展一个复杂的机构级平台。对个人使用场景，近期目标应收敛为：

1. 策略能由 Codex 生成、验证、回测、扫描、记录信号，并明确能力边界。
2. NautilusTrader 成为主要事件驱动执行路径，先完成单标的 backtest/paper 同构，再扩展多标的。
3. 事件、新闻、宏观、LLM feature 必须进入 point-in-time feature packet，并可在 Python 与 Nautilus 回放。
4. Alpaca Paper 能以可恢复的本地服务方式运行、同步、监控和告警。
5. Dashboard 作为本地可视化控制面，辅助查看和触发受控命令；不是唯一操作入口，也不做多人 SaaS。
6. 每轮审查只能收敛和校准这些目标，不允许随意新增大范围功能，除非发现直接阻断闭环的问题。

## 基于 `/goal` 已形成的主要改动

| 领域 | 已落地改动 | 当前判断 |
|---|---|---|
| Dashboard read model | React Dashboard 改为读取 `reports/dashboard/catalog.json`，新增运行时 `/api/dashboard/catalog` 同步，静态 HTML 也读取 catalog | 已具备个人本地查看能力 |
| Dashboard command service | 新增 `open_composer/dashboard/commands.py`、`server.py`、`models/dashboard_command.py`，支持 command-plan / command-run / audit | 已具备本地受控命令基础 |
| 策略生命周期命令 | Dashboard/CLI 支持 draft、validate、capabilities refresh、workflow verify、backtest rerun、scan rerun、approve、activate、disable | 已具备基础闭环入口 |
| Paper 安全门 | 新增 `paper_readiness.py`、activation gate、自动下单前 readiness 阻断、kill switch、sync account/orders、monitor sync | 已具备安全基础；服务化未完成 |
| NautilusTrader | 单标的 OHLCV backtest adapter、backend plan、feature packet / llm_feature custom data replay、Dashboard 展示 replay metadata、Nautilus paper 最新 bar 信号 runtime | 单标的 backtest/paper 最小闭环可用；多资产和更完整订单生命周期未完成 |
| 复杂数据 / LLM feature | 新增 feature packet schema 收紧、`feature write`、`feature from-context`、PIT 校验、context-capable 自动落 packet | replay 入口可用；统一 live feature store 未完成 |
| readiness / deployment | 新增 `oc readiness`、`oc deploy prepare`、`make readiness`、`make deploy-prepare`，报告进入 Dashboard catalog | 部署前检查可用 |
| 测试覆盖 | 新增 dashboard command/server、deployment/readiness、feature validation、paper readiness 等测试 | 覆盖显著增强 |

## 本次审查执行的检查

| 命令 | 结果 | 说明 |
|---|---|---|
| `git status --short` | 有大量 modified / untracked | 当前包含 `/goal` 期间的本地改动。 |
| `uv run oc capability test` | 通过 | registry 中 sample、Alpaca、Longbridge、SEC、FRED、Alpha Vantage、GDELT fixtures 均可评估。 |
| `uv run oc dashboard catalog` | 通过 | 当前 catalog：3 strategies、3 versions、1 run、0 signals、0 reviews、9 audit events；readiness/deployment 为 warning。 |
| `uv run oc readiness` | 通过 | status=`warning`，ready=`yes`；主要 warning 是部分策略 backend capability 为 partial。 |

说明：沙箱中 `uv` 默认 cache 路径只读，本次使用 `UV_CACHE_DIR=/tmp/uv-cache` 执行检查。

## 调研依据

本轮重新查阅了以下资料，用来校准“个人使用版”优先级：

- NautilusTrader 官方文档：Adapters 由 `DataClient` 与 `ExecutionClient` 接入数据和交易场所；Custom Data 能通过正常 runtime、persistence、query pipeline 路由；High-Level Backtest API 的策略/actor/执行算法可向 live trading 迁移。结论：继续补 Nautilus 同构执行是正确方向，不应再自研完整执行引擎。
  - https://nautilustrader.io/docs/latest/concepts/adapters/
  - https://nautilustrader.io/docs/latest/concepts/custom_data/
  - https://nautilustrader.io/docs/latest/getting_started/backtest_high_level/
- Alpaca 官方文档：Paper trading 免费、可用于实时模拟；订单有完整生命周期；free market data 主要是 IEX，SIP 需要订阅，IEX 只代表单一交易所。结论：Alpaca Paper 适合作为个人模拟盘执行通道，但数据 caveat 必须写入报告。
  - https://docs.alpaca.markets/docs/paper-trading
  - https://docs.alpaca.markets/docs/trading/orders/
  - https://docs.alpaca.markets/docs/market-data-faq
  - https://docs.alpaca.markets/v1.4.2/docs/historical-stock-data-1
- Longbridge 官方文档：历史 K 线有 Basic 权限、按账户等级每月 100-3000 个标的配额；美股默认 Nasdaq Basic；美股分钟历史从 2023-12-04 起；接口限速 60 次 / 30 秒。结论：Longbridge 可作为低成本美股数据源之一，但必须做 coverage、quota、delay 和 adjustment caveat。
  - https://open.longbridge.com/docs/quote/pull/history-candlestick
  - https://open.longbridge.com/docs/quote/pull/candlestick
- Qlib / QuantConnect LEAN 资料：Qlib 更偏 AI-oriented quant research workflow；LEAN 是成熟多资产 research/backtest/live 平台。结论：可借鉴其数据、模型、组合、执行分层，但近期不应改造成另一套 Qlib/LEAN；Open Composer 的价值是 Codex 驱动的 spec、报告、审查和个人操作闭环。
  - https://qlib.readthedocs.io/en/stable/introduction/introduction.html
  - https://www.microsoft.com/en-us/research/publication/qlib-an-ai-oriented-quantitative-investment-platform/
  - https://www.quantconnect.com/docs/research/backtesting

## 当前完成度

### 已经足够支撑个人 MVP 的部分

- `StrategySpec` 作为策略源头。
- draft -> validate -> capability report -> backtest -> scan -> paper readiness 的基础链路。
- Python reference engine 作为确定性参考。
- NautilusTrader 单标的 OHLCV backtest 子集。
- feature packet / llm_feature 的可回放输入入口。
- Alpaca Paper 安全门、kill switch、同步和监控命令。
- Dashboard 本地 read model、Strategy/Paper command center、runtime catalog sync。
- `oc deploy prepare` / `oc readiness` / `make verify` 这类部署检查入口。

### 仍必须补齐的关键缺口

| 优先级 | 缺口 | 为什么必须做 | 成功标准 |
|---|---|---|---|
| P0 | 固定任务边界和优先级 | 后续执行容易把个人产品扩大成机构级平台 | 文档明确闭环优先、暂缓项和不可随意新增范围 |
| P1 | NautilusTrader paper runtime | 单标的最新 bar 信号 runtime 已补；仍缺多资产 routing 和更完整订单生命周期同构 | paper run 复用 Nautilus paper plan、spec hash、version、signal audit，并仍走 Alpaca Paper 安全门 |
| P1 | PIT feature store | 事件/新闻/宏观/LLM feature 不能只做 advisory | 数据进入统一 packet/store，含 source、published_at、fetched_at、dedupe_key、schema_version、model/prompt hash |
| P1 | LLM feature replay 闭环 | LLM+量化策略必须可回测、可复现 | LLM 输出先落 feature packet，再被 Python/Nautilus 回放，禁止在执行 loop 内即时调用 LLM |
| P1 | Paper 服务化 | 现在仍偏手动命令，长时间模拟盘不够稳 | 本地 monitor loop 可恢复，持续同步 orders/account/positions，产出 status/reconcile/alerts |
| P2 | Dashboard 产品化 | 需要更流畅地查看和触发本地操作 | 保持本地单用户，补齐 Overview/Strategy/Paper 的关键操作和失败态，不做多人权限系统 |
| P2 | 研究验证硬化 | 防止回测结果误导 | 增加 walk-forward、样本外、参数敏感性、数据源比较前置门 |

## 近期明确不做的内容

这些不是现在的目标，后续 Codex 不应把它们加入近期计划：

- 多用户、团队协作、tenant isolation、复杂 RBAC。
- 浏览器内完整 YAML 编辑器、复杂 diff/merge 产品。
- 真钱实盘写入。
- TradingView 全量策略执行适配。
- 自研一个与 NautilusTrader 并行的完整事件驱动引擎。
- 一次性覆盖“99% 全部主流策略/因子/算法”。
- 期权、统计套利、机器学习 alpha、行业中性、多资产组合优化的完整机构级研究平台。

如果后续确实需要新增上述范围，必须在新文档中明确说明新增原因、阻断点和取舍，不能在普通审查中顺手扩大范围。

## 给后续 Codex 的执行规则

1. 能力补全和闭环优先，Dashboard 只是辅助入口；不要为了做页面而绕开核心能力。
2. 每次完成一部分后，只允许更新该部分状态和直接相关缺口，不允许随意新增大目标。
3. 任何策略能力进入 paper 前，必须能追溯到 spec、version/hash、data provenance、capability report、backtest/report、signal log。
4. 复杂数据和 LLM 输出必须先变成 point-in-time replay data，再进入回测或执行。
5. Alpaca Paper 写入必须继续显式确认、readiness gate、kill switch 和 audit。
6. NautilusTrader 是目标执行路径；Python engine 是参考和 smoke test，不再扩展成并行完整执行引擎。
7. 每个阶段完成时至少运行：`make verify`、`uv run oc deploy prepare`、`uv run oc readiness`，并说明 warning 是否是可接受边界。

## 后续 goal 建议

1. **PIT feature store MVP**
   - 目标：把事件/新闻/宏观/LLM feature 统一为可验证、可回放、可索引的数据层。
   - 不做：实时新闻大规模采集平台。
2. **Paper monitor 服务化**
   - 目标：本地可恢复 monitor loop，稳定同步账户、订单、持仓、PnL、告警。
   - 不做：云端运维平台。
3. **Dashboard 本地产品化**
   - 目标：把 readiness/deployment/paper/strategy workflow 的关键操作接到本地 Dashboard，并展示失败态。
   - 不做：多用户权限、远程 SaaS。

## 最终判断

当前项目可以作为个人使用的本地 AI 策略工作台继续迭代。真正阻碍“直接流畅部署和使用所有功能”的不是 Dashboard 是否足够复杂，而是 PIT feature store、LLM feature replay、Paper 服务化和严格验证闭环还没有完全补齐。

后续所有计划都应围绕这些闭环推进。
