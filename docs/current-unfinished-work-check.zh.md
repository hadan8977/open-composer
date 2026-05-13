# Open Composer 当前未完成事项检查与执行优先级

日期：2026-05-13

## 结论

Open Composer 已经具备个人本地 AI 策略工作台 MVP 的主体：`StrategySpec`、能力注册、Python reference 回测、NautilusTrader 子集、Alpaca Paper 安全门、feature packet、Dashboard catalog、受控命令、readiness 与部署检查都已经形成基础链路。

但它还不能被标记为“能力补全完成”。接下来不应继续扩展成机构级平台，也不应优先打磨 Dashboard 外观。剩余任务必须固定为下面这条闭环：

```text
复杂数据 / LLM feature 的 PIT 可回放层
  -> NautilusTrader 回测与 paper 同构
  -> Alpaca Paper 本地服务化监控
  -> Dashboard 只接入已经真实存在的能力
  -> 全量验证、部署检查、readiness 审查
```

后续 `/goal` 不允许避重就轻地先做页面、文案或非关键重构。每完成一部分，只能更新该部分状态、验证结果和直接阻断；不得随意新增大范围需求。

## 当前仓库状态判断

- 最新已推送的 GitHub 主分支基线：`9f5e981 Complete local strategy workbench loop`。
- 当前工作区已把 PIT feature store 草稿整理成可验证实现：feature packet schema、manifest/index、Dashboard replay warning、Nautilus custom data metadata、CLI `feature write` hash 字段、Paper readiness 阻断和相关测试都已补齐。
- 本轮验证已通过：`ruff format`、`ruff check`、`pytest`、Dashboard build、`oc capability test`、`oc feature validate`、`oc deploy prepare`、`oc readiness`、`make verify`。
- `oc deploy prepare` 和 `oc readiness` 当前为 `warning ready=yes`，主要原因是 paper broker sync 建议、Dashboard token 建议和部分草稿策略 backend capability 为 `partial`；这些是当前 MVP 边界，不是阻断部署的失败。

## 基于 `/goal` 已完成的稳定能力

| 领域 | 已有能力 | 当前判断 |
|---|---|---|
| 策略源头 | `StrategySpec` 仍是策略行为源头，CLI/Dashboard 围绕 spec、version、hash 工作 | 保持 |
| Python reference | 可做确定性回测、扫描、smoke test | 保持为参考路径，不扩成完整执行引擎 |
| NautilusTrader | 已有单标的 OHLCV backtest adapter、custom data replay metadata、最小 paper 最新 bar runtime | 方向正确，但仍未完成同构闭环 |
| 数据能力 | `capabilities/registry.yaml` 已注册 sample、Alpaca、Longbridge、SEC、FRED、Alpha Vantage、GDELT | 继续强制走 registry 与 capability evaluation |
| LLM feature | 已有 feature packet、context-derived packet、PIT 校验入口 | 仍需强制 replay 链路 |
| Alpaca Paper | 已有 readiness gate、kill switch、account/orders/positions sync、monitor/monitor-loop | 仍需服务化恢复、reconcile、alert 稳定化 |
| Dashboard | 已从 mock 外观进入 catalog-driven 本地控制面，支持 command plan/run | 只能作为辅助入口，不做第二真相源 |
| 部署检查 | `oc deploy prepare`、`oc readiness`、`make verify` 已建立 | 继续作为交付门槛 |

## 本轮已完成的闭环补强

- `oc feature validate` 现在会生成 `reports/features/manifest.json`，作为 feature packet replay manifest/index。
- manifest 记录 packet 状态、source、symbol、schema version、model、input hash、prompt hash、dedupe key、行级时间戳和 feature field。
- `event_feature` schema 强制 `published_at`、`fetched_at`、`schema_version`。
- Dashboard feature packet catalog 会显示 `schema_version` 缺失、非法 timestamp、重复 dedupe key 等 replay warning。
- Nautilus custom data binding 使用统一 feature packet inspection，缺 PIT 元数据或重复 dedupe key 会标为非 complete。
- Paper readiness 会阻断未 PIT-complete 的 `llm_feature` / `feature_packet` 因子，避免不可复现的 LLM/事件因子进入 paper。
- `oc feature write` 支持 `--input-hash` 和 `--prompt-hash`。

## 固定剩余缺口

以下是后续必须完成的任务清单。除非发现直接阻断闭环、安全或可复现性的问题，不得向此表随意追加新大项。

| 顺序 | 缺口 | 必须解决的原因 | 最小验收标准 |
|---|---|---|---|
| P1-1 | LLM + 量化 replay 闭环 | LLM 不能在回测或 paper loop 中临时决定交易，否则无法复现 | LLM 输出必须先落 packet，再进入策略；执行 loop 内禁止即时调用 LLM；报告显示模型、输入、prompt/hash、schema、replay warning |
| P1-2 | NautilusTrader 同构路径 | 项目已决定不自研完整执行引擎，复杂执行语义必须靠 Nautilus 统一回测与 paper | 单标的 backtest/paper 使用同一 spec hash、version、data manifest、feature packet、backend plan 和 signal audit；差异能被报告解释 |
| P1-3 | Paper 服务化 | 个人模拟盘需要能长时间运行、恢复、同步和告警，不能只依赖一次性命令 | 本地 monitor loop 可恢复；持续同步 orders、fills、positions、account、PnL；写入 status/reconcile/alerts；所有写入仍经 explicit confirmation、readiness gate、kill switch、audit |
| P2-1 | Dashboard 本地产品化 | Dashboard 应该提高管理效率，但不能替代核心能力 | 仅接入真实 catalog 与 command service；展示 readiness、deployment、strategy workflow、feature replay、paper status、alerts；写操作继续走 plan/confirm/audit |
| P2-2 | 研究验证硬化 | 防止短样本或单数据源回测误导 | promotion 前至少支持 walk-forward、样本外、参数敏感性、成本/滑点敏感性、Alpaca/Longbridge/sample 数据差异检查 |

## 后续执行顺序

1. PIT feature store MVP 已完成本地实现和验证；后续只维护，不再扩成数据湖。
2. 下一步继续完成 LLM feature replay 闭环。
3. 再补 NautilusTrader 单标的同构路径，不新增并行执行引擎。
4. 再做 Paper 服务化，让 Alpaca Paper 本地 monitor loop 可恢复、可审计。
5. 最后根据真实后端能力复审 Dashboard，补齐必要页面和命令入口。
6. 每一阶段结束后运行完整验证并更新本文件的状态，不新增无关目标。

## 明确暂缓或不做

这些内容不是个人使用版近期目标。后续 Codex 不应把它们重新加入近期计划：

- 多用户登录、RBAC、tenant isolation、团队协作。
- Dashboard 作为唯一运行方式。
- 浏览器内完整 YAML 编辑器、复杂 diff/merge 产品。
- 真钱交易写入。
- TradingView 全量策略执行适配。
- 自研一个与 NautilusTrader 并行的完整事件驱动引擎。
- 多 broker 同时写入、云端运维平台、手机推送。
- 期权、统计套利、行业中性、多资产组合优化、机器学习 alpha 的完整机构级研究平台。
- 一次性承诺支持“99% 全部策略、因子、算法”。

如确实要新增上述范围，必须单独写明：新增原因、当前闭环阻断点、替代方案、对测试和维护成本的影响。

## 给后续 Codex 的硬性规则

1. 能力补全和闭环优先，Dashboard 只能接入已存在能力。
2. 新数据源、新事件源、新宏观源、新新闻源必须先进入 `capabilities/registry.yaml`，再运行 capability evaluation。
3. 复杂数据和 LLM 输出必须先变成 point-in-time replay data，再进入回测或执行。
4. 策略进入 paper 前必须能追溯到 spec、version/hash、data provenance、capability report、backtest report、signal log。
5. Alpaca Paper 写入必须保留 explicit confirmation、readiness gate、kill switch 和 audit。
6. NautilusTrader 是目标执行路径；Python reference 只做确定性参考和 smoke test。
7. 每次更新审查文档只能记录真实完成状态、验证结果和直接缺口；不得为了显得“全面”而扩大范围。

## 验证门槛

实现型 `/goal` 每完成一个阶段，至少运行：

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
npm --prefix dashboard run build
uv run oc capability test
uv run oc deploy prepare
uv run oc readiness
make verify
```

如果 `oc readiness` 或 `deploy prepare` 返回 `warning`，必须在交付说明中明确 warning 是否属于当前 MVP 已知边界，不能简单写“通过”。

## 调研校准

- NautilusTrader 官方文档将 adapter 分为数据、instrument 与 execution 组件，并支持 custom data 在 runtime 中路由；其高阶 backtest 路径也强调向 live trading 迁移。因此 Open Composer 应继续补 Nautilus 同构，而不是自研完整执行引擎。
- Alpaca Paper 是免费模拟交易环境，但 paper 与 live 在成交假设、滑点、市场冲击、费用、分红等方面不同；免费/基础行情也有 IEX/SIP 覆盖边界。因此 Paper 适合个人模拟盘闭环，不适合作为“真实收益证明”。
- Longbridge OpenAPI 可作为低成本美股数据源候选，但美股基础权限、历史分钟线范围、symbol 配额、限速和 OpenAPI quote 权限需要写入 provenance 与 caveat。
- Qlib、LEAN 等成熟平台说明：复杂量化/AI 策略需要数据层、模型层、回测层、执行层和审计层分离。Open Composer 的近期价值不是复制完整平台，而是用 Codex + StrategySpec + 文件审计把个人闭环做扎实。

参考资料：

- https://nautilustrader.io/docs/latest/concepts/adapters/
- https://nautilustrader.io/docs/latest/concepts/custom_data/
- https://nautilustrader.io/docs/latest/getting_started/backtest_high_level/
- https://docs.alpaca.markets/us/docs/paper-trading
- https://docs.alpaca.markets/v1.3/docs/historical-stock-data-1
- https://docs.alpaca.markets/docs/market-data-faq
- https://open.longbridge.com/docs/quote/pull/history-candlestick
- https://open.longbridge.com/docs/quote/pull/quote
- https://www.microsoft.com/en-us/research/publication/qlib-an-ai-oriented-quantitative-investment-platform/
