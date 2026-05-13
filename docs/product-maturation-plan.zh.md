# Open Composer 个人使用版产品成熟化计划

日期：2026-05-13

## 产品定位

Open Composer 的近期定位是个人 AI 策略工作台，而不是多人 SaaS 或机构级量化平台。

核心分工固定如下：

- `StrategySpec` 是策略行为源头。
- Codex 负责生成、修改、审查、测试策略和报告。
- Python reference engine 是确定性参考路径和 smoke test。
- NautilusTrader 是目标事件驱动回测 / paper 同构路径。
- Alpaca Paper 是 MVP 的唯一自动化模拟盘写入通道。
- Longbridge 与 Alpaca 是优先支持的低成本美股数据源；所有 caveat 必须写入报告。
- LLM 可以参与 review、事件/新闻/宏观特征提取和策略研究，但影响交易前必须先落为可回放 feature packet。
- Dashboard 是本地可视化和受控操作面，不是第二真相源，也不是唯一运行方式。

## 成熟产品完成标准

个人使用版达到“可以流畅部署和持续使用”时，必须满足：

1. 策略从 `StrategySpec` 可追溯到 version/hash、数据来源、能力报告、回测报告、信号日志和 paper readiness。
2. 无外部凭证时，sample workflow 可完整跑通。
3. 有 Alpaca / Longbridge 凭证时，数据获取、cache、provenance、数据差异报告和 caveat 可正常产生。
4. 事件、新闻、宏观、LLM 输出全部先进入 point-in-time feature packet/store，再进入回测或 paper。
5. NautilusTrader 至少完成单标的 backtest/paper 同构路径，并能解释 Python reference 与 Nautilus 的差异。
6. Alpaca Paper 自动化必须显式确认、readiness gate、kill switch、audit，并能通过本地 monitor loop 持续同步状态。
7. Dashboard 能读取真实 catalog，展示策略、版本、回测、feature replay、paper 状态、readiness/deployment，并通过 command service 触发受控命令。
8. `make verify`、`oc deploy prepare`、`oc readiness` 是每轮交付前硬门槛。

## 优先级总览

后续计划只保留以下主线，按顺序执行。Dashboard 必须排在核心能力之后复审。

| 阶段 | 名称 | 状态 | 目标 |
|---|---|---|---|
| P0 | 范围冻结与文档约束 | 已完成本文档更新 | 防止继续扩成不必要的大平台 |
| P1 | PIT feature store MVP | 已完成本地 MVP | 支撑复杂数据、事件、新闻、宏观、LLM feature 的可回放能力 |
| P1 | LLM + 量化 replay 闭环 | 部分完成，paper gate 已补 | 禁止执行 loop 内即时调用 LLM；所有 LLM 影响先落 packet |
| P1 | NautilusTrader 同构路径 | 部分完成 | 单标的 backtest/paper 同一 spec、数据、feature、audit 链路 |
| P1 | Paper 服务化 | 部分完成 | 本地可恢复 monitor loop、同步、reconcile、alert |
| P2 | Dashboard 本地产品化 | 部分完成，需在 P1 后复审 | 只接入真实能力，提升查看和受控操作效率 |
| P2 | 研究验证硬化 | 未完成 | promotion 前增加样本外、walk-forward、敏感性和数据源比较 |

## P1：PIT Feature Store MVP

目标：把复杂数据和 LLM 产物从“可选上下文”变成“可验证、可索引、可回放”的研究输入。

已完成：

- `oc feature validate` 会生成 `reports/features/validation.json/.md` 和 `reports/features/manifest.json`。
- manifest/index 记录 `source`、`symbol`、`timestamp`、`published_at`、`fetched_at`、`dedupe_key`、`schema_version`、`model`、`input_hash`、`prompt_hash` 和 feature field。
- Dashboard catalog/html 展示 replay 状态和 warning。
- NautilusTrader custom data binding 使用同一 PIT inspection 结果。
- Paper readiness 会阻断未 PIT-complete 的 LLM/feature packet 因子。

不做：

- 大规模实时新闻平台。
- 外部数据湖。
- 付费数据供应商聚合平台。

验收：

- `oc feature validate` 能发现缺失 PIT 字段、非法时间戳、重复 dedupe key。
- 回测报告和 Dashboard 都能显示 feature packet 的完整性与 warning。
- 未通过 PIT 校验的 feature 不能被标记为 paper-ready。
- 本轮已通过 `pytest`、`ruff check`、`oc feature validate`、`oc deploy prepare`、`oc readiness`、`make verify`。

## P1：LLM + 量化 Replay 闭环

目标：让 LLM 参与的策略可复现、可审计、可回测。

必须做：

- Review 类 LLM 保持 advisory，不改变交易语义。
- 扫描机会类 LLM 只能输出结构化 feature packet。
- 组合/编排类 LLM 只能输出可版本化的候选配置或状态标签，不能直接绕过策略 spec 下单。
- 报告记录 LLM 的 model、prompt hash、input hash、输出 schema、生成时间、来源数据时间范围。
- 回测和 paper loop 只能读取已经落盘的 LLM feature。

不做：

- 在执行 loop 内实时问 LLM 买卖。
- 用自然语言结论替代结构化信号。
- 把不可复现的 LLM 输出写成通过验证的因子。

验收：

- 同一 spec、同一数据 manifest、同一 LLM feature packet 可以复跑并得到可解释结果。
- Dashboard 能区分 review-only、feature-producing、orchestration-candidate 三类 LLM 使用方式。

## P1：NautilusTrader 同构路径

目标：让 Open Composer 的主要执行语义逐步落到 NautilusTrader，而不是继续扩展自研执行引擎。

必须做：

- 单标的 OHLCV backtest 与 paper runtime 使用同一 StrategySpec hash、version、data manifest、feature packet。
- Nautilus run/report 写明 backend plan、instrument、bar type、data source、execution assumption、feature replay warning。
- Python reference 与 Nautilus 的差异进入 parity report。
- Paper runtime 仍然通过 Alpaca Paper readiness、kill switch、explicit confirmation、audit。

不做：

- 并行自研完整事件驱动引擎。
- 多 broker 写入。
- 复杂多资产 portfolio routing，直到单标的闭环稳定。

验收：

- 单标的策略可在 Python reference 和 NautilusTrader 上用同一数据集跑出可比较报告。
- paper signal 能追溯到 Nautilus plan、spec hash、version、signal id 和 broker order/audit。

## P1：Paper 服务化

目标：让个人模拟盘可以稳定、可恢复、可监控地运行。

必须做：

- 本地 monitor loop 可恢复，记录每轮 cycle。
- 持续同步 Alpaca orders、fills、positions、account、PnL。
- 生成 status、reconciliation、alerts。
- stale data、open order、缺失 snapshot、kill switch、unrealized loss 等风险进入 alert。
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

必须做：

- Overview 展示 readiness、deployment、recent runs、paper status、alerts。
- Strategy Detail 展示 version lineage、capability report、backtest/scan/report、feature replay、paper readiness。
- Paper 页面展示 account、positions、orders、reconciliation、alerts、monitor loop 状态。
- 所有写操作走 command plan、confirmation、audit。
- 保持本地单用户 token gate。

不做：

- 多用户登录、RBAC、tenant isolation。
- 浏览器内完整 YAML 编辑器。
- 直接绕过 readiness 的下单按钮。
- 把 Dashboard 做成唯一操作入口。

验收：

- Dashboard 每个关键数字都能追溯到 `reports/` 或 catalog。
- 失败态比成功态更清楚：缺凭证、缺 packet、capability partial、readiness warning 都要可见。

## P2：研究验证硬化

目标：避免短样本、单数据源和过拟合策略误导个人使用者。

必须做：

- walk-forward。
- out-of-sample。
- 参数敏感性。
- 成本/滑点敏感性。
- Alpaca / Longbridge / sample 数据源比较。

不做：

- 完整机器学习 alpha 平台。
- 机构级因子库。
- 期权和衍生品研究系统。

验收：

- 策略从 research-only 升级到 paper candidate 前，报告必须包含稳健性检查或明确缺口。

## 执行纪律

1. 每个 `/goal` 只做当前阶段闭环。
2. 不因为 Dashboard 或文档容易改，就绕开 PIT、Nautilus、Paper 这些核心缺口。
3. 文档只能更新真实状态、验证结果和直接下一步。
4. 新增范围必须说明为什么阻断个人闭环，不能用“以后可能需要”作为理由。
5. 新数据能力必须走 `capabilities/registry.yaml` 与 capability evaluation。
6. 所有实现交付必须运行测试和 readiness，并说明 warning。

## 后续 `/goal` 建议

1. 补 LLM feature replay 的剩余门控和报告表达。
2. 完成 NautilusTrader 单标的 backtest/paper parity 报告。
3. 完成 Alpaca Paper monitor 服务化。
4. 基于真实能力复审 Dashboard，再做本地产品化。
