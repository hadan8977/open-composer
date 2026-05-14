# Open Composer 个人使用版成熟化计划

日期：2026-05-13

## 产品定位

Open Composer 的近期定位是个人 AI 策略工作台，不是多人 SaaS、机构级量化平台或 Dashboard-only 产品。

固定分工如下：

- `StrategySpec` 是策略行为源头。
- Codex 负责生成、修改、审查、测试策略和报告。
- Python reference engine 是确定性参考路径和 smoke test。
- NautilusTrader 是目标事件驱动回测 / paper 同构路径。
- Alpaca Paper 是当前唯一自动化模拟盘写入通道。
- Longbridge 与 Alpaca 是优先支持的低成本美股数据源，但所有 caveat 必须写入报告。
- 事件、新闻、宏观和 LLM 输出影响交易前，必须先落为 point-in-time feature packet。
- Dashboard 是本地可视化和受控操作面，不是第二真相源，也不是唯一运行方式。

## 成熟产品完成标准

个人使用版达到“可以流畅部署和持续使用”时，必须满足：

1. 策略从 `StrategySpec` 可追溯到 version/hash、数据来源、能力报告、回测报告、信号日志和 paper readiness。
2. 无外部凭证时，sample workflow 可完整跑通。
3. 有 Alpaca / Longbridge 凭证时，数据获取、cache、provenance、数据差异报告和 caveat 可正常产生。
4. 事件、新闻、宏观、LLM 输出全部先进入 point-in-time feature packet/store，再进入回测或 paper。
5. NautilusTrader 完成单标的 backtest / paper 同构路径，并能解释 Python reference 与 Nautilus 的差异。
6. Alpaca Paper 自动化必须显式确认、readiness gate、kill switch、audit，并能通过本地 monitor loop 持续同步状态。
7. Dashboard 能读取真实 catalog，展示策略、版本、回测、feature replay、paper 状态、readiness/deployment，并通过 command service 触发受控命令。
8. `make verify`、`oc deploy prepare`、`oc readiness` 是每轮交付前硬门槛。

## 优先级总览

后续计划只保留以下主线，按顺序执行。Dashboard 必须排在核心能力之后复审。

| 阶段 | 名称 | 状态 | 目标 |
|---|---|---|---|
| P0 | 范围冻结与文档约束 | 已完成 | 防止继续扩成不必要的大平台 |
| P1 | PIT feature store 基线 | 已完成本地基线 | 支撑复杂数据、事件、新闻、宏观、LLM feature 的可回放能力 |
| P1 | 复杂数据与 LLM feature 闭环 | 部分完成 | 让 feature-producing LLM 和外部事件数据从生成、校验、报告到 paper gate 都可复现 |
| P1 | NautilusTrader 同构路径 | 部分完成 | 从已完成的 backtest parity 扩展到 paper runtime 同构证据 |
| P1 | Paper 服务化 | 部分完成 | 本地可恢复 monitor loop、broker sync、reconcile、alert |
| P2 | Dashboard 本地产品化 | 部分完成，需在 P1 后复审 | 只接入真实能力，提升查看和受控操作效率 |
| P2 | 研究验证硬化 | 参数扫描、promotion report、leverage research、exposure switch research 已补基线 | 策略 promotion 前增加样本外、walk-forward、成本敏感性、数据源比较和风险暴露检查 |

## P1：复杂数据与 LLM Feature 闭环

目标：让事件、新闻、宏观和 LLM 产物从“临时上下文”变成“可验证、可索引、可回放”的策略输入。

已完成：

- `oc feature validate` 会生成 `reports/features/validation.json/.md` 和 `reports/features/manifest.json`。
- manifest/index 记录 source、symbol、timestamp、published_at、fetched_at、dedupe_key、schema_version、model、input_hash、prompt_hash 和 feature field。
- Dashboard catalog/html 展示 replay 状态和 warning。
- NautilusTrader custom data binding 使用同一 PIT inspection 结果。
- Paper readiness 会阻断未 PIT-complete 的 LLM/feature packet 因子。
- backtest / scan 报告会写明执行仅读取保存的 feature packet，不在执行 loop 内调用 LLM。

下一步必须做：

- 生成侧强约束：LLM、新闻、事件、宏观特征必须先写入 packet，再被 StrategySpec 引用。
- promotion gate：策略升入 paper 前必须检查 feature packet 的 PIT 完整性和 capability 状态。
- 报告表达：每个 LLM / feature factor 都显示 model、input hash、prompt hash、source、schema、时间范围和 warning。

不做：

- 大规模实时新闻平台。
- 外部数据湖。
- 付费数据供应商聚合平台。
- 执行 loop 内实时问 LLM 买卖。

验收：

- 同一 spec、同一数据 manifest、同一 feature packet 可以复跑并得到可解释结果。
- 未通过 PIT 校验的 feature 不能被标记为 paper-ready。
- Dashboard 能区分 review-only、feature-producing、orchestration-candidate 三类 LLM 使用方式。

## P1：NautilusTrader 同构路径

目标：让 Open Composer 的主要执行语义逐步落到 NautilusTrader，而不是继续扩展自研执行引擎。

已完成：

- 单标的 OHLCV Nautilus backtest adapter。
- Nautilus backtest plan 写入。
- 当 Nautilus 可用且策略适配时，会同时运行 Python reference 与 Nautilus backtest，并写 backend parity report。
- backtest report、signal log 和 Dashboard catalog 能回链 backend、version、spec hash 和 backend plan。

下一步必须做：

- active `nautilus_trader` 策略的 paper runtime 与 backtest 使用同一 spec hash、version、data manifest、feature packet 和 backend plan。
- paper signal 能追溯到 Nautilus plan、signal id、audit 和 broker order。
- 差异报告说明 Python reference、Nautilus backtest、paper runtime 的语义差异和已知边界。

不做：

- 并行自研完整事件驱动引擎。
- 多 broker 写入。
- 复杂多资产 portfolio routing，直到单标的闭环稳定。

验收：

- 单标的策略可在 Python reference 和 NautilusTrader 上用同一数据集跑出可比较报告。
- paper cycle 可证明它使用的是同一 StrategySpec、version/hash、data/feature replay 和安全门。

## P1：Paper 服务化

目标：让个人模拟盘可以稳定、可恢复、可监控地运行。

已完成：

- Alpaca Paper readiness gate。
- kill switch。
- account/orders/positions sync。
- reconciliation。
- alerts。
- `oc paper monitor` 和 `oc paper monitor-loop`。
- Dashboard summary 可读取 paper status、alerts 和 monitor 产物。

下一步必须做：

- 本地 monitor loop 可恢复，记录每轮 cycle 和最近健康状态。
- broker sync 失败、网络错误、缺失 snapshot、stale data、open order、unrealized loss 等状态进入 alert。
- Dashboard Paper 页只调用受控 command，显示最近同步时间、错误、路径和下一步动作。

不做：

- 云端运维平台。
- 手机推送。
- 多账户权限系统。
- 真钱交易写入。

验收：

- monitor loop 中断后可继续，不破坏已有 audit。
- broker 写入仍受 explicit confirmation、readiness gate、kill switch 控制。

## P2：Dashboard 本地产品化

Dashboard 的完善必须在 P1 能力完成后再复审。它的职责是显示真实状态、减少手工命令出错，而不是替代 CLI 或生成第二套业务逻辑。

已完成：

- catalog-driven Dashboard。
- 静态 HTML 输出。
- React Dashboard bundle。
- runtime catalog sync。
- command plan/run。
- 本地 token gate。

下一步必须做：

- Overview 展示 readiness、deployment、recent runs、paper status、alerts。
- Strategy Detail 展示 version lineage、capability report、backtest/scan/report、feature replay、paper readiness。
- Paper 页面展示 account、positions、orders、reconciliation、alerts、monitor loop 状态。
- 所有写操作走 command plan、confirmation、audit。
- 缺凭证、缺 packet、capability partial、readiness warning 等失败态必须比成功态更清楚。

不做：

- 多用户登录、RBAC、tenant isolation。
- 浏览器内完整 YAML 编辑器。
- 直接绕过 readiness 的下单按钮。
- 把 Dashboard 做成唯一操作入口。

验收：

- Dashboard 每个关键数字都能追溯到 `reports/`、catalog、signal log、feature log 或 audit。
- Dashboard 上的操作都能在 CLI 中找到同源命令和审计记录。

## P2：研究验证硬化

目标：避免短样本、单数据源和过拟合策略误导个人使用者。

这部分重要，但不是当前第一阻断。它应该作为“策略从 research-only 升级到 paper candidate”的质量门，而不是扩展成机构级研究平台。

已完成：

- 通用参数扫描基线：`oc strategy parameter-sweep` 可以一次性跑多组 `entry`、`exit`、`risk`、`costs`、`factors` 参数组合。
- 参数扫描会生成 ranked JSON / Markdown 报告，并默认只写 top draft specs。
- 候选策略强制为 draft/manual，不会直接进入 paper。
- `oc strategy promotion-report` 会输出 full-window、out-of-sample、walk-forward、cost sensitivity 和 data comparison 的最小 promotion gate，并已接入 paper readiness。
- `oc strategy leverage-research` 会把杠杆暴露与未杠杆 buy-and-hold 对照，报告 OOS Alpha、Sharpe、drawdown expansion 和 walk-forward 结果。
- `oc strategy exposure-switch` 会研究 point-in-time 动态仓位切换，显式声明每根 bar 的暴露只使用上一根 bar close 已知指标，并输出 OOS / walk-forward / drawdown gate。

下一步必须做：

- 把 promotion、leverage 和 exposure-switch 结果在 Dashboard 中更直接地聚合展示。
- 对数据源比较缺失的策略给出更清晰的 next action。
- 继续补充真实 Alpaca / Longbridge 数据窗口下的验证样例，不把 sample fallback 当市场证据。

不做：

- 完整机器学习 alpha 平台。
- 机构级因子库。
- 期权和衍生品研究系统。

验收：

- 策略从 research-only 升级到 paper candidate 前，报告必须包含稳健性检查或明确缺口。

## 执行纪律

1. 每个 `/goal` 只做当前阶段闭环。
2. 不因为 Dashboard 或文档容易改，就绕开复杂数据、LLM replay、Nautilus、Paper 这些核心缺口。
3. 文档只能更新真实状态、验证结果和直接下一步。
4. 新增范围必须说明为什么阻断个人闭环，不能用“以后可能需要”作为理由。
5. 新数据能力必须走 `capabilities/registry.yaml` 与 capability evaluation。
6. 所有实现交付必须运行测试和 readiness，并说明 warning。

## 后续 `/goal` 建议

1. 补复杂数据与 LLM feature replay 的生成侧约束、promotion gate 和报告表达。
2. 完成 NautilusTrader 单标的 backtest / paper 同构证据。
3. 完成 Alpaca Paper monitor 服务化。
4. 基于真实能力复审 Dashboard，再做本地产品化。
