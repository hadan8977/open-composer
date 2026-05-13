# Open Composer 收敛版缺口审计

日期：2026-05-13

## 审计用途

这份文档用于审查后续 `/goal` 是否偏离当前个人使用版闭环。它不是新的功能路线图，也不允许把旧计划里的所有高级能力重新塞回近期目标。

当前执行基准以两份文档为准：

- `docs/current-unfinished-work-check.zh.md`：当前完成情况与剩余缺口。
- `docs/product-maturation-plan.zh.md`：个人使用版成熟化计划。

历史调研文档仍然保留，但只能作为背景材料，不能直接当成当前实现清单。

## 总体裁定

Open Composer 近期目标是“个人可部署、可回测、可模拟盘运行、可审计”的 AI 策略工作台。

当前不需要追求：

- 机构级全策略平台；
- 复杂 Dashboard-only 操作系统；
- 多用户 SaaS；
- 全市场全数据源；
- 99% 量化算法和因子承诺。

当前必须补齐的是：

```text
复杂数据 / LLM feature replay
  -> NautilusTrader backtest / paper 同构
  -> Alpaca Paper 服务化
  -> Dashboard 真实接入
  -> 验证与 readiness
```

## 已完成的关键基础

| 领域 | 当前完成情况 |
|---|---|
| 策略源头 | `StrategySpec` 继续作为唯一行为源头，CLI 和 Dashboard 都围绕 spec、version、hash 工作。 |
| Python reference | 已能作为确定性回测、扫描和 smoke test 路径。 |
| NautilusTrader | 已有单标的 OHLCV backtest adapter、Nautilus plan、Python reference / Nautilus backend parity 报告和 custom data replay metadata。 |
| 复杂数据 | PIT feature packet、manifest/index、validation report、Dashboard warning、Paper readiness gate 已形成基础。 |
| LLM feature | backtest / scan 报告已明确只读取落盘 packet，不在执行 loop 内调用 LLM。 |
| 数据能力 | sample、Alpaca、Longbridge、SEC、FRED、Alpha Vantage、GDELT 已在 capability registry 中注册；Longbridge 仍按 trial 数据路线处理。 |
| Alpaca Paper | readiness gate、kill switch、account/orders/positions sync、reconcile、alerts、monitor、monitor-loop 已有基础。 |
| Dashboard | catalog-driven 本地工作台、静态 HTML、React bundle、runtime catalog sync、command plan/run 已有基础。 |
| 部署检查 | `oc deploy prepare`、`oc readiness`、`make verify` 已建立为交付门槛。 |

## 当前真正未完成的内容

| 优先级 | 内容 | 不能回避的原因 | 审计判断 |
|---|---|---|---|
| P1 | 复杂数据与 LLM feature 闭环 | 没有可回放 packet 和生成侧约束，LLM+量化策略无法复现 | 必须先做 |
| P1 | NautilusTrader backtest / paper 同构 | 项目已经选择 Nautilus 作为目标执行路径，不能只停留在 reference 回测 | 必须先做 |
| P1 | Paper 服务化 | 个人模拟盘需要可恢复、可同步、可告警，不能只靠一次性命令 | 必须先做 |
| P2 | Dashboard 产品化 | Dashboard 有价值，但必须基于真实后端能力，而不是替代后端能力 | P1 后做 |
| P2 | 研究验证硬化 | 参数扫描已补基线；样本外、walk-forward、成本敏感性和数据源比较仍能降低过拟合风险 | 作为策略 promotion gate，不作为平台扩张 |

## 多视角审查

### 产品视角

当前用户是个人使用者，不需要团队权限、复杂运营后台或 Dashboard-only 工作流。最重要的是策略能从生成、回测、审查、paper 到复盘形成闭环。

裁定：保留 CLI + 文件为第一操作面，Dashboard 只是提高可视化和受控操作效率。

### 量化研究视角

项目不应承诺“所有策略都支持”。正确目标是把数据 provenance、PIT feature、Nautilus 同构和研究验证门补稳，再逐步扩大策略族。

裁定：研究验证硬化必要，但不能优先级高于 LLM replay、Nautilus 和 Paper 服务化。

### 执行与风控视角

Dashboard 按钮和自动 paper 都有误操作风险。所有 paper 写入必须保留 explicit confirmation、readiness gate、kill switch 和 audit。

裁定：任何新增 paper 控制都必须走 command plan/run，不能绕过 CLI 安全门。

### 数据与 LLM 视角

事件、新闻、宏观和 LLM 输出如果不能 point-in-time 回放，就不能进入回测或 paper。LLM review 可以 advisory，但 feature-producing LLM 必须落结构化 packet。

裁定：P1-1 是后续所有复杂策略的地基。

### Dashboard 视角

Dashboard 不是第二真相源。每个数字都必须来自 `reports/`、catalog、signal logs、feature logs 或 audit。

裁定：Dashboard 产品化必须排在核心闭环之后。先显示真实失败态，再做操作便利性。

### 测试视角

每轮 `/goal` 不能只看单元测试通过，还要验证 readiness、deployment、feature validation 和 Dashboard build。warning 必须解释。

裁定：完整验证是交付条件，不是可选项。

## 禁止随意新增的近期范围

以下内容不应在当前目标中重新出现：

- 多用户 / RBAC / tenant isolation。
- 真钱交易写入。
- 完整可视化策略编辑器。
- Dashboard 作为唯一运行方式。
- TradingView 全量运行时。
- 自研完整事件驱动执行引擎。
- 多 broker 同时写入。
- 期权、统计套利、行业中性、多资产组合优化、完整 ML alpha 平台。
- 99% 策略、因子、算法支持承诺。

如果确实要新增，必须证明它直接阻断当前个人闭环，并说明替代方案和维护成本。

## 后续 `/goal` 审查清单

每次 `/goal` 开始前，先检查：

1. 本次任务是否落在 P1 或 P2 固定缺口内。
2. 是否会绕过 `StrategySpec`、capability registry、feature packet、readiness 或 audit。
3. 是否把 Dashboard 页面当成后端能力。
4. 是否新增了未注册数据源或不可回放 LLM 输出。
5. 是否引入了与 NautilusTrader 并行的完整执行逻辑。

每次 `/goal` 结束前，必须检查：

1. 文档状态只更新真实结果，不扩大目标。
2. 测试、readiness、deploy prepare、Dashboard build 已运行或明确说明未运行原因。
3. 所有 warning 都有解释。
4. 新产物能回链到 spec、version/hash、data provenance、signal、report、audit。
