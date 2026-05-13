# Open Composer 计划完成度检查与收敛版缺口审计

日期：2026-05-13

## 审查结论

本项目的近期目标应是“个人可部署、可回测、可模拟盘运行、可审计”的 AI 策略工作台，而不是一次性做成多人量化平台。

当前 `/goal` 期间已经补上大量基础设施：真实 Dashboard read model、本地 command service、paper readiness gate、Nautilus custom data replay、feature packet、readiness/deployment 报告和测试覆盖。现在最重要的不是继续横向增加页面或概念，而是把核心闭环补完。

本审计的用途是约束后续实现型 `/goal`：先补关键能力，再补 Dashboard；每次完成一部分只更新真实状态和直接缺口，不允许顺手扩大范围。

## 已完成的关键能力

| 领域 | 完成情况 |
|---|---|
| 策略源头 | `StrategySpec` 继续作为唯一行为源头，CLI 和 Dashboard 都围绕 spec/path/hash 工作。 |
| Python reference | 继续作为确定性回测和 smoke test 引擎。 |
| NautilusTrader | 单标的 OHLCV backtest adapter 已接入，feature packet / llm_feature 可作为 custom data replay；单标的 paper 最新 bar 信号 runtime 已接入 Alpaca Paper 安全门。 |
| 能力评估 | `oc spec capabilities` 可标记 Python/Pine/Nautilus/Alpaca/LLM workflow 能力边界。 |
| 数据能力 | sample、Alpaca、Longbridge、SEC、FRED、Alpha Vantage、GDELT 已在 capability registry 中注册并有 fixture 测试。 |
| LLM feature | 已有 feature packet schema、手动写入、context-derived packet、PIT 校验和 Nautilus replay metadata。 |
| Alpaca Paper | 已有 readiness gate、kill switch、account/orders/positions sync、monitor、monitor-loop 和下单前阻断。 |
| Dashboard | 已从 mock UI 变成 catalog-driven 本地控制面，支持 runtime catalog sync 和受控 command plan/run。 |
| 部署检查 | `oc readiness`、`oc deploy prepare`、`make readiness`、`make deploy-prepare` 已建立。 |
| PIT feature store | `oc feature validate` 已生成 validation report 与 manifest/index；schema、Dashboard、Nautilus custom data、Paper readiness 均接入 PIT warning / gate。 |

## 仍未完成但必须优先补的内容

| 优先级 | 内容 | 当前缺口 | 验收标准 |
|---|---|---|---|
| P0 | 任务边界收敛 | 后续执行容易继续扩大范围 | 文档明确个人使用版目标、闭环优先级、暂缓项和不可随意新增范围 |
| P1 | LLM feature 闭环 | 已阻断非 PIT-complete packet 进入 paper；仍需补更完整报告表达和生成侧约束 | LLM feature 必须先落 packet，再进入 Python/Nautilus 回测和 paper；执行 loop 内不得即时调用 LLM |
| P1 | NautilusTrader 同构路径 | 单标的最新 bar 信号 runtime 已接入；仍缺同一 spec/data/feature 下的 backtest/paper parity 证据 | paper runtime 引用 Nautilus plan、spec hash、version、data manifest、feature packet、signal audit，并经 Alpaca Paper 安全门 |
| P1 | Paper 服务化 | monitor loop、reconcile、alerts 已有基础；仍需真实 broker sync 下的恢复和告警验证 | 本地 monitor loop 可恢复，持续同步 broker orders/fills/account/positions/PnL，并写 status/reconcile/alerts |
| P2 | Dashboard 本地产品化 | 部分关键建议动作仍只是文本或 CLI 路径 | Overview/Strategy/Paper 能触发关键本地命令、显示失败态和最近产物路径 |
| P2 | 研究验证硬化 | 回测结论还缺稳健性检查 | 增加 walk-forward、样本外、参数敏感性、成本/滑点敏感性、数据源比较门 |

## 已决定暂缓的内容

以下内容不要在近期计划里反复加入，除非用户单独设新目标：

- 多用户登录、RBAC、tenant isolation、团队协作。
- Dashboard 作为唯一运行方式。
- 浏览器内完整 YAML 编辑、复杂 merge/diff。
- 真钱交易写入。
- TradingView 完整执行适配。
- 自研完整事件驱动引擎。
- 机构级全市场多资产组合平台。
- 一次性承诺支持 99% 全部量化算法和因子。

## 对计划文档的硬性约束

1. 每次审查只能更新当前已完成状态、当前阻断和下一步最小闭环。
2. 不允许因为“顺手想到”而扩大范围。
3. Dashboard 需求必须服从核心能力闭环；页面不能替代执行、数据和回放能力。
4. NautilusTrader 是目标执行路径，Python reference 是参考路径。
5. 复杂数据和 LLM 输出必须可回放、可审计、可复现。
6. Paper 写入必须保留 explicit confirmation、readiness gate、kill switch 和 audit。

## 最新验证基线口径

本轮复查已执行：

| 命令 | 结果 |
|---|---|
| `uv run ruff format .` | 通过，102 files left unchanged |
| `uv run ruff check .` | 通过 |
| `uv run pytest` | 通过，104 passed, 1 warning |
| `npm --prefix dashboard run build` | 通过 |
| `uv run oc capability test` | 通过，所有 registry fixture capability 可评估 |
| `uv run oc feature validate` | 通过，写入 validation report 与 manifest |
| `uv run oc deploy prepare` | 通过，status=`warning` ready=`yes` |
| `uv run oc readiness` | 通过，status=`warning` ready=`yes` |
| `make verify` | 通过 |

`warning` 当前来自 paper broker sync 建议、Dashboard token 建议和部分草稿策略 backend capability `partial`，属于个人 MVP 边界，不是测试失败。

下一轮实现型 goal 必须重新运行验证，不得引用旧结果。

## 后续执行顺序

1. PIT feature store MVP 已完成本地实现和验证。
2. 然后做 LLM + 量化 replay 闭环。
3. 然后做 NautilusTrader 单标的 backtest/paper 同构。
4. 然后做 Paper monitor 服务化。
5. 最后根据真实能力补 Dashboard 操作面。
