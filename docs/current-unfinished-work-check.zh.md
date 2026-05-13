# Open Composer 当前检查结果与剩余缺口

日期：2026-05-13

## 结论

这份文档是后续 `/goal` 的当前执行检查表。它覆盖当前已经完成的能力、还没有闭合的关键缺口，以及不应该再被随意加入近期目标的内容。

Open Composer 现在已经不是单纯的设计稿。它已经具备个人本地 AI 策略工作台的主体：`StrategySpec`、能力注册、Python reference 回测、NautilusTrader 单标的 backtest 子集、backend parity 报告、backtest data sanity gate、Alpaca Paper 安全门、PIT feature packet、Dashboard catalog、受控命令、readiness 与部署检查。

但它还不能被标记为“能力补全完成”。剩余工作必须收敛到下面这条个人使用版闭环：

```text
复杂数据 / LLM feature 可回放
  -> NautilusTrader backtest / paper 同构证据
  -> Alpaca Paper 本地服务化
  -> Dashboard 接入真实能力
  -> 验证、部署检查、readiness 审查
```

后续 `/goal` 不应先做外观、宽泛平台能力、机构级研究系统或非必要重构。每完成一部分，只能更新真实状态、验证结果和直接阻断；不得为了“更完整”随意追加新大项。

## 当前基线

- 当前本地 `main` 基线已经包含 README benchmark 删除、参数扫描、backend parity、feature replay 和 backtest data sanity gate。
- 本文档只记录当前真实状态和剩余缺口；不作为扩大近期目标的入口。
- 上一轮实现型验证曾覆盖 `ruff`、`pytest`、Dashboard build、`oc capability test`、`oc feature validate`、`oc deploy prepare`、`oc readiness` 和 `make verify`；每轮交付必须重新运行，不能直接复用旧结果。

## 已完成能力

| 领域 | 当前状态 | 判断 |
|---|---|---|
| 策略源头 | `StrategySpec` 仍是策略行为源头，版本、hash、run、signal、paper 产物都围绕 spec 回链 | 保持 |
| Python reference | 可做确定性回测、扫描、smoke test 和语义回归 | 保持为参考路径，不扩展成完整执行引擎 |
| NautilusTrader | 已有单标的 OHLCV backtest adapter；当策略使用 `nautilus_trader` 且环境可用时，会生成 Nautilus plan、运行 Nautilus backtest，并写 Python reference / Nautilus backend parity 报告 | 继续补 paper 同构和运行证据 |
| 回测可信度 | Backtest report 已有 `Data Sanity` section；Python reference 与 Nautilus backtest 都会标注 evidence level、sample/fallback/fixture、短样本、低交易数、异常年化/Sharpe 和零费用假设 | 保持为展示和 promotion 的前置警告，不替代样本外验证 |
| 复杂数据 | 已有 feature packet schema、`oc feature validate`、manifest/index、PIT warning、Dashboard catalog 展示和 Paper readiness gate | 继续补生成侧约束和执行链路证据 |
| LLM feature | backtest / scan 报告会写明只读取已保存 feature packet，不在执行 loop 内调用 LLM | 继续补 LLM feature 从生成到 promotion 的闭环 |
| 数据源 | sample、Alpaca、Longbridge、SEC、FRED、Alpha Vantage、GDELT 已进入 capability registry；Alpaca / Longbridge 可做数据差异报告 | Longbridge 仍是低成本 trial 路线，不是全市场数据已解决 |
| Alpaca Paper | 已有 readiness gate、kill switch、account/orders/positions sync、reconcile、alerts、monitor、monitor-loop 和下单前阻断 | 继续补本地服务化恢复和真实 broker sync 下的稳定验证 |
| Dashboard | 已从 mock UI 进入 catalog-driven 本地工作台，支持 runtime catalog sync 和受控 command plan/run | 只能作为辅助入口，不做第二真相源 |
| 部署检查 | `oc deploy prepare`、`oc readiness`、`make verify` 已建立 | 继续作为交付门槛 |

## 必须优先补的缺口

下面是固定剩余缺口。除非发现直接阻断个人闭环、安全或可复现性的问题，不得向此表新增大项。

| 顺序 | 缺口 | 当前状态 | 最小验收标准 |
|---|---|---|---|
| P1-1 | 复杂数据与 LLM feature 闭环 | PIT packet、manifest、feature replay 报告和 readiness gate 已有；仍缺从 LLM / 事件 / 新闻 / 宏观生成端到策略 promotion 的强约束 | 任何会影响交易的 LLM / 事件 / 新闻 / 宏观输出必须先落 packet；报告显示 model、input hash、prompt hash、schema、source、timestamp、warning；执行 loop 内禁止即时调用 LLM |
| P1-2 | NautilusTrader backtest / paper 同构 | 单标的 backtest adapter 与 backend parity 报告已补；仍缺 paper runtime 与 backtest 使用同一 spec、version、data、feature、backend plan 的完整证据 | active `nautilus_trader` 策略的 paper cycle 能回链到 Nautilus plan、spec hash、version、data manifest、feature packet、signal audit，并经过 Alpaca Paper 安全门 |
| P1-3 | Paper 服务化 | monitor、monitor-loop、reconcile、alerts 已有命令级基础；仍缺长时间本地运行、恢复、错误重试和真实 broker sync 下的稳定验证 | 本地 monitor loop 可恢复；持续同步 orders、fills、positions、account、PnL；写入 status/reconcile/alerts；所有写入仍经 explicit confirmation、readiness gate、kill switch、audit |
| P2-1 | Dashboard 产品化 | catalog、静态 HTML、React bundle 和 command service 已有；仍有一些关键动作和失败态没有形成完整产品路径 | Overview/Strategy/Paper 只展示真实 catalog 和 reports；能触发关键受控命令；清楚显示 readiness、deployment、feature replay、paper status、alerts 和最近产物路径 |
| P2-2 | 研究验证硬化 | 通用参数扫描、backtest data sanity gate 和最小 promotion report 已补，并已接入 paper readiness；不是当前第一阻断，但策略升入 paper 前仍需要更稳健的研究证据 | 继续把 promotion report 结果通过 Dashboard 展示并保持最小闭环，不要把它扩展成完整机构级研究平台 |

## 后续执行顺序

1. 完成复杂数据与 LLM feature 闭环：先保证可回放、可审计、可阻断。
2. 完成 NautilusTrader 单标的 backtest / paper 同构证据：不新增并行执行引擎。
3. 完成 Alpaca Paper 本地服务化：让 monitor loop、sync、reconcile、alerts 可以可靠恢复。
4. 基于真实后端能力复审 Dashboard，再补必要页面和命令入口。
5. 补策略 promotion 需要的研究验证硬化，但只作为质量门，不作为下一阶段平台扩张。
6. 每一阶段结束后运行完整验证并更新本文件的真实状态。

## 明确暂缓或不做

这些内容不是个人使用版近期目标。后续 Codex 不应把它们重新加入近期计划：

- 多用户登录、RBAC、tenant isolation、团队协作。
- Dashboard 作为唯一运行方式。
- 浏览器内完整 YAML 编辑器、复杂 diff/merge 产品。
- 真钱 broker 写入。
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
8. 旧的宽泛规划文档只作为历史调研材料；当前执行以本文档和 `docs/product-maturation-plan.zh.md` 为准。

## 验证门槛

实现型 `/goal` 每完成一个阶段，至少运行：

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
npm --prefix dashboard run build
uv run oc capability test
uv run oc feature validate
uv run oc deploy prepare
uv run oc readiness
make verify
```

如果 `oc readiness` 或 `oc deploy prepare` 返回 `warning`，必须在交付说明中明确 warning 是否属于当前个人版已知边界，不能简单写“通过”。

## 调研校准

- NautilusTrader 的 backtest 文档强调 `BacktestEngine` 处理历史数据流，并有 high-level / low-level 两级 API；adapter 文档也强调数据和执行适配器的边界。因此 Open Composer 应继续补 Nautilus 同构，而不是自研完整执行引擎。
- Alpaca Paper 是模拟交易环境，且 Alpaca 明确区分 IEX 与 SIP 数据。Paper 适合个人模拟盘闭环，不适合作为真实收益证明。
- Longbridge OpenAPI 历史 K 线需要基础行情权限，美股默认 Nasdaq Basic，并有月度 symbol 配额和权限边界。它适合作为低成本 trial 数据源，但不能被写成全市场高质量数据已解决。
- Qlib、LEAN 等成熟平台说明：复杂量化 / AI 策略需要数据层、模型层、回测层、执行层和审计层分离。Open Composer 的近期价值是用 Codex + StrategySpec + 文件审计把个人闭环做扎实。

参考资料：

- https://nautilustrader.io/docs/latest/concepts/backtesting/
- https://nautilustrader.io/docs/latest/developer_guide/adapters/
- https://docs.alpaca.markets/docs/trading/paper-trading/
- https://docs.alpaca.markets/docs/market-data-faq
- https://open.longbridge.com/docs/quote/pull/history-candlestick
- https://www.quantconnect.com/docs/
- https://www.microsoft.com/en-us/research/publication/qlib-an-ai-oriented-quantitative-investment-platform/
