# Open Composer Golden Path：no-context Codex 量化审查入口

日期：2026-05-13

## 用途

这份文档是无上下文的 no-context Codex 进入仓库时优先阅读的起始审查文档。它不替代 `AGENTS.md`，而是把当前产品定位、真实能力、近期主线、禁止扩张范围和验证门槛收敛成一个入口。

若本文与旧的宽泛计划冲突，以本文、`AGENTS.md` 和 README 为准。历史审查只作背景材料，不得直接变成近期实现清单。

## 产品裁定

Open Composer 当前定位是个人 AI 策略工作台，不是多人 SaaS、机构级全策略平台、Dashboard-only 产品或真金交易系统。

固定分工如下：

- `StrategySpec` 是策略行为源头。
- Codex 负责生成、修改、审查、测试策略和报告。
- Python reference engine 是确定性参考路径和 smoke test。
- NautilusTrader 是目标事件驱动回测 / paper 同构路径。
- Alpaca Paper 是当前唯一自动化模拟盘写入通道。
- `capabilities/registry.yaml` 是数据、事件、宏观和新闻源进入策略依赖的入口。
- 事件、新闻、宏观和 LLM 输出影响交易前，必须先落为 point-in-time feature packet。
- Dashboard 是本地读模型和受控操作面，不是第二真相源。

## 当前仓库事实

本次重新审查读取了 README、`AGENTS.md`、当前产品文档、CLI、Makefile、capability registry、strategy specs、核心测试和 paper / promotion / Dashboard 实现。当前事实如下：

| 领域 | 当前状态 | 审查裁定 |
|---|---|---|
| 入口文档 | README 已有 Quick Start、Workflow、Codex Control Surface、Data、Research、Paper、Dashboard 和 Project Docs | 需要把本文标为 no-context Codex 起点 |
| 策略源头 | `StrategySpec`、版本、hash、报告、信号和 paper 产物围绕 spec 回链 | 保持 |
| 样例闭环 | `qqq_pullback_15m.yaml` 和 sample data 可支撑无凭证 smoke workflow | 必须持续可运行 |
| 能力注册 | sample、Alpaca、Longbridge、SEC、FRED、Alpha Vantage、GDELT 已注册 | 新 required capability 先评估再使用 |
| 复杂数据 | feature packet validation、manifest、Dashboard 展示和 paper readiness gate 已存在 | 继续补生成侧强约束 |
| 回测可信度 | data sanity、buy-and-hold、Alpha、promotion report 已有 | 不能把 sample / fixture 结果当 benchmark |
| NautilusTrader | 单标的 backtest adapter、plan、backend parity 与 paper plan 基础已存在 | 继续补 paper 同构证据 |
| Alpaca Paper | readiness、kill switch、sync、reconcile、alerts、monitor loop 已存在 | 继续补稳定恢复和真实 sync 验证 |
| Dashboard | catalog、React bundle、runtime sync、command plan/run 已存在 | 只接真实产物和受控命令 |
| 验证门 | `uv run ruff format .`、`uv run ruff check .`、`uv run pytest`、`make verify`、deploy/readiness 已建立 | 每轮交付重新跑，不复用旧结论 |

## Golden Path

后续 no-context Codex 应按这条路径理解和执行项目：

```text
Idea
  -> draft StrategySpec
  -> capability check
  -> spec validation
  -> deterministic Python backtest / scan
  -> data sanity + buy-and-hold + Alpha report
  -> parameter-sweep when parameters are adjustable
  -> promotion-report
  -> PIT feature packet validation when complex data or LLM is used
  -> NautilusTrader backend parity where supported
  -> paper readiness
  -> Alpaca Paper command gate
  -> Dashboard catalog/readiness view
  -> journal / weekly review
```

核心命令：

```bash
uv run oc repo check
uv run oc capability test
uv run oc spec validate strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc spec capabilities strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc backtest strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc strategy parameter-sweep strategy_specs/drafts/qqq_pullback_15m.yaml --param costs.slippage_bps=0,5
uv run oc strategy promotion-report strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc strategy leverage-research strategy_specs/drafts/qqq_pullback_15m.yaml --max-candidates 4
uv run oc strategy exposure-switch strategy_specs/drafts/qqq_pullback_15m.yaml --max-candidates 4
uv run oc feature validate
uv run oc deploy prepare
uv run oc readiness
make verify
```

`uv run oc repo check` 是本次新增的仓库一致性门，检查 README 的 no-context Codex 入口、当前治理文档、repo skills、capability registry、样例策略输入、Dashboard 受控命令模型和 `make verify` 绑定关系。

## 近期计划

这不是新扩张路线，而是对当前文档的执行收敛。

| 顺序 | 计划 | 动作 | 验收 |
|---|---|---|---|
| P0 | 入口收敛 | README Project Docs 明确把本文标为 no-context Codex 起点；`oc repo check` 纳入验证 | 新 Codex 第一眼看到唯一当前主线 |
| P0 | 文档精简 | `docs/` 只保留入口、部署、本地 setup 和必要集成文档 | `oc repo check` 阻断历史文档重新堆回当前文档目录 |
| P1 | 复杂数据 / LLM feature 闭环 | 生成侧必须先写 PIT packet；报告显示 model、input hash、prompt hash、schema、source、timestamp、warning | 未 PIT-complete 的 feature 不能 paper-ready |
| P1 | NautilusTrader paper 同构 | paper cycle 回链 spec hash、version、data manifest、feature packet、backend plan、signal audit | Python / Nautilus / paper 差异可解释 |
| P1 | Paper 服务化 | monitor loop 记录 cycle、恢复状态、sync 错误、stale snapshot、open order、PnL alert | 写入仍经 readiness、kill switch、显式确认 |
| P2 | Dashboard 本地产品化 | Overview / Strategy / Paper 只展示真实 catalog、reports、logs、audit 和 next action | 每个关键数字可追溯到文件产物 |
| P2 | 研究验证硬化 | promotion report 继续强化 OOS、walk-forward、成本敏感性、数据比较和参数稳定性 | paper candidate 不依赖单次最优结果 |

## 本次执行

本次根据用户要求和产品定位，执行以下最小闭环：

1. 重新审查 README、当前文档、CLI、Makefile、capability registry、测试和关键实现。
2. 补齐缺失的 `docs/product-golden-path-codex-quant-review-2026-05-13.zh.md`。
3. 更新 README Project Docs，把本文标为 no-context Codex 起始审查文档。
4. 新增 `oc repo check`，把入口文档和控制面收进本地验证。
5. 把 `repo-check` 接入 `make verify`。
6. 补测试覆盖 repo check 的通过路径、README 缺入口阻断和 CLI 报告写入。
7. 按 `AGENTS.md` 运行格式、检查和测试。
8. 把 `make verify` 扩展为本地闭环门：repo、capability、deploy、Dashboard、feature、readiness 一起跑。
9. 清理过期和重复审查文档，避免 README 和 docs 目录继续提供多条互相竞争的路线。

## 明确不做

- 不引入 financial-services 的商业 MCP、managed-agent 云部署、Office / Excel / PPT 交付链。
- 不把投行、基金管理、KYC、财富管理能力变成近期路线。
- 不做真金 broker 写入。
- 不把 Dashboard 做成第二真相源或唯一操作入口。
- 不自研一个与 NautilusTrader 并行的完整事件驱动执行引擎。
- 不把 sample、fixture、fallback、短样本或参数扫描最优结果当市场收益证明。

## 后续 Codex 检查清单

开始任务前：

- 是否先读 `AGENTS.md`、本文和 README。
- 是否落在 P1 / P2 固定缺口内。
- 是否会绕过 `StrategySpec`、`capabilities/registry.yaml`、feature packet、readiness 或 audit。
- 是否把旧历史计划误当当前路线。

结束任务前：

- 文档是否只记录真实状态和直接缺口。
- 是否运行 `uv run oc repo check`。
- 是否运行 `uv run ruff format .`、`uv run ruff check .`、`uv run pytest`。
- 是否运行 `make verify`，并解释 readiness / deploy / feature / Dashboard warning。
- 新产物是否能回链到 spec、version/hash、data provenance、signal、report 或 audit。
