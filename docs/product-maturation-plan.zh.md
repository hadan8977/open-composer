# Open Composer 个人使用版产品成熟化计划

日期：2026-05-12

## 定位

Open Composer 的近期定位是个人 AI 策略工作台：

- Codex 负责生成、修改、审查、测试策略和报告。
- `StrategySpec` 是策略行为源头。
- Python reference engine 是确定性参考路径。
- NautilusTrader 是目标事件驱动执行路径。
- Alpaca Paper 是 MVP 的唯一自动化模拟盘写入通道。
- Dashboard 是本地可视化和受控操作面，不是唯一操作方式。

近期不做多人 SaaS、不做真金实盘写入、不做全量 TradingView 执行适配，也不自研完整事件驱动引擎。

## 成熟产品完成标准

个人使用版达到“可流畅部署和使用”需要满足以下标准：

1. 任何策略都能从 `StrategySpec` 追溯到版本/hash、数据来源、能力报告、回测报告、信号日志和 paper readiness。
2. 本地无外部凭证时，sample workflow 能完整跑通。
3. 有 Alpaca / Longbridge 凭证时，行情获取、数据 caveat、比较报告和 paper 安全门能正常工作。
4. NautilusTrader 至少完成单标的 backtest/paper 同构路径。
5. 事件、新闻、宏观、LLM 输出必须先落 point-in-time feature packet，再进入回测或执行。
6. Alpaca Paper 自动化必须显式确认、readiness gate、kill switch、audit。
7. Dashboard 能读取真实 read model，展示策略、版本、回测、paper 状态、readiness/deployment，并触发受控本地命令。
8. `make verify`、`oc deploy prepare`、`oc readiness` 能作为每轮交付前的硬门槛。

## 优先级计划

### P0：任务边界收敛

状态：已由本文档定义。

目标：

- 明确个人使用版目标。
- 明确能力补全和闭环优先。
- 明确 Dashboard 是辅助控制面，不是唯一运行入口。
- 明确暂缓项，避免后续审查随意扩大范围。

验收：

- 后续 Codex 能按本文档判断优先级。
- 每次完成一部分后，只更新真实状态和直接相关缺口。
- 不把多用户、真钱交易、机构级研究平台等内容加入近期目标。

### P1：NautilusTrader paper runtime MVP

状态：单标的最新 bar 信号 runtime 已完成；多资产和完整订单生命周期同构仍未完成。

已完成：

- paper runtime 复用 Nautilus plan，而不是只停留在 handoff plan。
- 保留 Alpaca Paper 作为唯一 broker 写入通道。
- 保留 paper readiness、kill switch、explicit confirmation、audit。
- 记录 spec hash、version id、backend plan、signal id、order id。

下一步：

- 等 Paper 服务化阶段继续补订单生命周期、失败恢复和持续同步。
- 多标的组合 routing 暂缓到个人单标的闭环稳定之后。

暂不做：

- 真钱 live。
- 多 broker。
- 复杂多资产 portfolio routing。

### P1：Point-in-time feature store MVP

状态：部分完成。

已完成：

- feature packet schema。
- `oc feature write`、`oc feature from-context`。
- feature packet validation。
- Nautilus custom data replay metadata。

下一步：

- 建立统一 feature packet index / manifest。
- 所有 event/news/macro/LLM feature 记录 source、published_at、fetched_at、dedupe_key、schema_version。
- LLM feature 记录 model、prompt hash、input hash、output schema version。
- Python reference 与 Nautilus 回放同一 packet。

暂不做：

- 大规模实时新闻平台。
- 复杂外部数据湖。

### P1：LLM + 量化闭环

状态：部分完成。

目标：

- LLM review 保持 advisory。
- LLM feature 必须先转为可回放 packet。
- 禁止在 backtest/paper execution loop 内临时调用 LLM 决定交易。
- Dashboard 显示 LLM feature 的来源、时间、模型和 replay 状态。

### P1：Paper monitor 服务化

状态：部分完成。

已完成：

- paper status。
- kill switch。
- orders/account/positions sync。
- monitor / monitor-loop。
- stale snapshot warning。

下一步：

- monitor loop 可恢复。
- 持续同步 orders、fills、positions、account、PnL。
- 失败重试和告警写入本地报告。
- Dashboard Paper 页显示最近同步时间、错误、open orders、positions、PnL 和下一步动作。

暂不做：

- 云端守护进程。
- 手机推送。
- 多账户权限系统。

### P2：Dashboard 本地产品化

状态：部分完成。

已完成：

- catalog-driven React Dashboard。
- static HTML Dashboard。
- runtime catalog sync。
- command plan/run。
- Strategy/Paper 部分命令入口。

下一步：

- Overview 显示 readiness/deployment 的真实下一步，并能触发对应本地 command。
- Strategy Detail 强化 workflow verify、capability、backtest、scan、paper readiness 的失败态展示。
- Paper 页强化 monitor/sync/kill switch 的状态与结果路径。
- 保持本地单用户 token gate。

暂不做：

- 多用户登录。
- RBAC。
- 浏览器内完整策略 YAML 编辑器。
- 直接下单按钮。

### P2：研究验证硬化

状态：未完成。

下一步：

- walk-forward。
- out-of-sample。
- 参数敏感性。
- 成本/滑点敏感性。
- Alpaca/Longbridge/sample 数据比较前置门。

暂不做：

- 机构级因子平台。
- 完整机器学习 alpha pipeline。
- 期权/波动率完整研究系统。

## 执行纪律

1. 每个阶段只做该阶段闭环，不扩展无关功能。
2. 文档只记录真实状态和直接下一步，不随意新增大目标。
3. 代码改动必须有测试或明确验证命令。
4. Dashboard 写操作必须走 command plan、confirmation、audit。
5. 真钱交易写入不进入 MVP。
6. 新能力进入策略前，必须经过 capability registry 和 capability evaluation。

## 给后续 goal 的建议

后续 goal 应按以下顺序推进：

1. Point-in-time feature store MVP。
2. LLM + 量化 replay 闭环。
3. Paper monitor 服务化。
4. Dashboard 本地产品化。

每个 goal 只做对应闭环，不顺手新增大型范围。
