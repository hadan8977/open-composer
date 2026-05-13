# Open Composer 项目与 GitHub 仓库审查

创建日期：2026-05-12  
更新日期：2026-05-13

## 审查范围

- 本地项目：`/root/codex-test/open-composer`
- GitHub 远端：`https://github.com/zhoucehuang-arch/open-composer.git`
- 最新本地基线：`bfa29a1 Add backend parity and feature replay reports`
- 本次更新性质：文档审查与后续 `/goal` 执行约束优化

注意：2026-05-13 的当前执行范围已经收敛。本文保留项目级审查结论；后续实现型 `/goal` 的实时缺口以 `docs/current-unfinished-work-check.zh.md` 和 `docs/product-maturation-plan.zh.md` 为准。

## 总体判断

Open Composer 已经从设计稿阶段进入可运行的个人本地 AI 策略工作台阶段。核心能力已包括：

- `StrategySpec` 源头。
- capability registry。
- Python reference 回测/扫描。
- NautilusTrader 单标的 backtest、custom data replay 子集和 backend parity 报告。
- Pine 兼容子集导出。
- feature packet / LLM feature 基础。
- Alpaca Paper readiness、kill switch、audit。
- Dashboard catalog、command plan/run。
- `oc readiness`、`oc deploy prepare`、`make verify`。

现在最重要的不是继续堆功能，而是把关键闭环补齐。后续优化必须围绕：

1. 复杂数据 / LLM feature replay 的生成侧约束和 promotion gate。
2. NautilusTrader backtest 与 paper 同构证据。
3. Alpaca Paper 服务化。
4. Dashboard 接入真实能力。

## 当前稳定能力

| 领域 | 当前状态 | 结论 |
|---|---|---|
| 源头 | `StrategySpec` 仍是策略行为唯一真相源 | 保持 |
| 数据 | sample、Alpaca、Longbridge、SEC、FRED、Alpha Vantage、GDELT 已通过 capability registry 管理 | 新能力必须先注册和评估 |
| 回测 | Python reference 可作为确定性基线；NautilusTrader 已有单标的 backtest 子集和 backend parity 报告 | 继续做 paper 同构，不自研完整执行引擎 |
| Pine | 只导出确定性兼容子集 | 保持兼容导出定位 |
| LLM | review 是 advisory；feature 必须先落 packet | 需要强制 replay 门控 |
| Paper | Alpaca Paper 受 readiness、kill switch、显式确认和 audit 门控 | 继续排除真钱写入 |
| Dashboard | React/static HTML 读取 catalog；写操作走 command plan/run | 不做第二真相源 |
| 部署 | `make deploy-prepare`、`make verify`、`make readiness` 是主要入口 | 保持为交付门槛 |

## 本轮 PIT feature store 审查结果

本轮 PIT 相关草稿已经整理成实现：

- 收紧 `event_feature` schema 的 point-in-time 字段。
- `oc feature write` 增加 input/prompt hash。
- Dashboard feature packet 展示 replay warning。
- Nautilus custom data metadata 纳入 schema/version 与 timestamp warning。
- `oc feature validate` 生成 `reports/features/manifest.json`，作为 replay manifest/index。
- Paper readiness 阻断未 PIT-complete 的 `llm_feature` / `feature_packet` 因子。
- 测试覆盖 feature validation、Dashboard catalog、strategy capability expansion。

上一轮实现型验证基线：

- `uv run ruff format .`：通过。
- `uv run ruff check .`：通过。
- `uv run pytest`：104 passed, 1 warning。
- `npm --prefix dashboard run build`：通过。
- `uv run oc capability test`：通过。
- `uv run oc feature validate`：通过，写入 validation report 与 manifest。
- `uv run oc deploy prepare`：status=`warning` ready=`yes`。
- `uv run oc readiness`：status=`warning` ready=`yes`。
- `make verify`：通过。

当前 warning 属于个人版已知边界：paper broker sync 建议、Dashboard token 建议和部分草稿策略 backend capability `partial`。

## 固定缺口与优先级

| 顺序 | 缺口 | 为什么优先 | Done 标准 |
|---|---|---|---|
| 1 | 复杂数据 / LLM feature replay | LLM+量化必须可审计，不能在执行时即时问模型 | LLM / 事件 / 新闻 / 宏观输出先落 packet；回测/paper 只读 packet；报告显示 replay 元数据和 warning |
| 2 | NautilusTrader 同构 | 这是目标执行路径，避免继续扩展自研引擎 | 单标的 paper cycle 与 backtest 使用同一 spec、version、data manifest、feature packet、backend plan、signal audit |
| 3 | Paper 服务化 | 个人模拟盘需要稳定运行和恢复 | 本地 monitor loop、status、reconcile、alerts、broker sync、kill switch、audit 全链路 |
| 4 | Dashboard 产品化 | 提升日常使用效率，但必须服从真实后端能力 | Overview/Strategy/Paper 展示真实 catalog 与失败态；写操作继续 plan/confirm/audit |

## 不再加入近期计划的内容

以下不是个人使用版近期目标：

- 多用户 SaaS、RBAC、tenant isolation。
- Dashboard 作为唯一运行方式。
- 浏览器内完整 YAML 编辑器。
- 真钱 broker 写入。
- TradingView 全量策略执行适配。
- 自研完整事件驱动执行引擎。
- 机构级全资产、多资产组合、完整 ML alpha 平台。
- 一次性承诺支持全部量化策略、因子和算法。

新增范围只有在直接阻断个人闭环、安全、可复现性或测试验证时才允许提出，并且必须写明新增原因、替代方案和成本。

## 部署与使用路径

无外部凭证的本地 smoke test：

```bash
cp .env.example .env
cp .codex/config.example.toml .codex/config.toml
make bootstrap
uv run oc doctor
make deploy-prepare
make verify
make readiness
```

有 Alpaca Paper 凭证时，先保持 `ALPACA_PAPER=true`，再运行：

```bash
uv run oc paper readiness <strategy-name>
uv run oc paper monitor --sync-broker
uv run oc readiness
```

Dashboard 本地使用：

```bash
make dashboard-build
OPEN_COMPOSER_DASHBOARD_TOKEN=<local-token> make dashboard-serve
```

## 调研依据

本审查参考以下资料校准产品边界：

- NautilusTrader：adapter/custom data/backtest-to-live 方向适合作为事件驱动执行核；Open Composer 不应再扩展并行完整执行引擎。
  - https://nautilustrader.io/docs/latest/concepts/adapters/
  - https://nautilustrader.io/docs/latest/concepts/custom_data/
  - https://nautilustrader.io/docs/latest/getting_started/backtest_high_level/
- Alpaca：Paper Trading 适合作为模拟交易环境；市场数据免费/基础层有 IEX/SIP 覆盖边界，报告必须保留 caveat。
  - https://docs.alpaca.markets/us/docs/paper-trading
  - https://docs.alpaca.markets/docs/market-data-faq
  - https://docs.alpaca.markets/v1.3/docs/historical-stock-data-1
- Longbridge：OpenAPI 历史 K 线、quote 权限、分钟线范围、配额和限速需要记录到 provenance；适合低成本候选，但不能写成完整美股研究数据已解决。
  - https://open.longbridge.com/docs/quote/pull/history-candlestick
  - https://open.longbridge.com/docs/quote/pull/quote
- Qlib / LEAN：成熟平台说明复杂量化需要数据、模型、回测、执行、审计分层。Open Composer 的近期优势是 Codex + StrategySpec + 文件审计的个人闭环。
  - https://www.microsoft.com/en-us/research/publication/qlib-an-ai-oriented-quantitative-investment-platform/
  - https://www.quantconnect.com/docs/v2/writing-algorithms/research-guide/backtesting

## 验证要求

下一轮实现型 `/goal` 完成任一阶段后，至少运行：

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

如果结果为 `warning` 而不是完全 clean，必须说明 warning 对当前个人版边界是否可接受。不能只写“已通过”。

## 最终审查结论

项目方向正确：用 NautilusTrader 承接事件驱动执行，用 Python reference 做确定性基线，用 PIT feature packet 承接复杂数据和 LLM feature，用 Alpaca Paper 做个人模拟盘闭环，用 Dashboard 做本地观察和受控操作面。

后续所有实现必须先补关键闭环，再补 Dashboard。不能因为页面、文档或轻量命令更容易完成，就绕开 PIT、LLM replay、Nautilus parity 和 Paper 服务化这些真正阻碍产品可用性的缺口。
