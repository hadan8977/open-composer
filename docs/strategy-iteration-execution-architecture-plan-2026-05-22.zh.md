# Open Composer 策略迭代与执行观察闭环架构计划

日期: 2026-05-22

适用范围: Open Composer main 分支下一阶段产品结构规划

关联前置:

- `docs/skill-first-harness-engineering-roadmap-2026-05-20.zh.md`
- `docs/llm-quant-epistemological-loop-roadmap-2026-05-21.zh.md`
- `AGENTS.md`
- `CLAUDE.md`
- `harness/risk_domains.yaml`
- `harness/artifact_contracts.yaml`
- `open_composer/research/control.py`

## 0. 结论

Open Composer 下一阶段不应该继续堆叠独立命令、独立报告或提示词模板。正确方向是把策略生成和优化迭代收束为一个可审计的产品闭环:

```text
StrategySpec / OptionsSpec
  -> risk domain
  -> required evidence artifacts
  -> promotion / paper readiness
  -> research-control memory
  -> 下一轮最小必要优化
```

核心目标不是让用户管理“参数扫描、研究报告、修测试、生成 target weights”等内部步骤，而是让 Codex / Claude Code 在 VPS 或本地 worktree 中按照 Open Composer 的结构自动执行这些步骤。用户只需要控制目标、建议、继续轮数和停止条件。

本计划的主线是:

1. 补齐 router 策略从 research 到 execution observation 的闭环。
2. 支持做空，但必须进入普通 `StrategySpec` 的风险域和证据 gate。
3. 支持期权研究，但期权不混入普通 `StrategySpec`，且不进入自动 paper 下单。
4. 所有新增能力必须进入 `harness/artifact_contracts.yaml`、`harness/risk_domains.yaml`、promotion/readiness 和 research-control memory。
5. 不新增第五个 pass。继续保持 `workflow_pass / research_pass / llm_contribution_pass / paper_ready_pass` 四层契约。

## 1. 产品定位

Open Composer 是个人 AI 策略工作台，不是通用量化平台，也不是自研 agent 替代品。

### 1.1 用户负责

- 给出策略想法。
- 设定优化目标。
- 提供主观建议。
- 决定继续、停止、转向或进入 paper 审查。

### 1.2 系统负责

- 生成和维护 `StrategySpec` 或独立 `OptionsSpec`。
- 调用 Codex / Claude Code 执行代码和文件工作。
- 运行验证、回测、参数扫描、target-weight 映射、证据生成和测试。
- 把所有关键判断落成 artifact。
- 用 harness gate 阻止证据不足的 promotion 或 paper readiness。
- 用 research-control memory 把失败路径、有效组合、阻塞项和下一步建议带入下一轮。

### 1.3 Codex / Claude Code 的定位

Codex 和 Claude Code 是底层执行者。Open Composer 不重写一个更弱的原生 agent，而是提供:

- 任务结构。
- 上下文编译。
- artifact contract。
- harness gate。
- safety guard。
- iteration memory。
- VPS 远程任务控制面。

## 2. 不变的产品契约

### 2.1 StrategySpec 仍是普通股票/ETF 策略源头

普通股票、ETF、router、做空和 long-short 策略仍以 `StrategySpec` 为源头。任何行为变更都必须能追溯到 spec 或 spec 关联 artifact。

### 2.2 Options 不混入普通 StrategySpec

期权不应直接塞进普通 `StrategySpec`。期权需要到期日、strike、Delta、Theta、Vega、IV、合约选择、展期、指派风险和多腿结构。它应有独立的 overlay 或 spec 路径。

### 2.3 四层 pass 不变

当前 pass 契约保持不变:

- `workflow_pass`
- `research_pass`
- `llm_contribution_pass`
- `paper_ready_pass`

不得新增 `paper_observation_pass` 或 `paper_order_pass`。如果需要区分观察和下单，在 readiness 输出中使用:

```text
execution_substate: blocked | observation_only | order_authorized
```

`paper_ready_pass` 仍是 paper readiness 的唯一布尔判断。

### 2.4 Vercel 和 Dashboard 不跑重任务

Dashboard 可以展示状态、提交任务请求和显示结果。Vercel 不运行 backtest、scan、pytest、dashboard build、文件写入或 shell。长任务交给 VPS daemon / local runner / Codex / Claude Code。

## 3. 目标架构

```text
用户目标 / 建议 / 停止条件
  -> Open Composer task controller
  -> context compiler
       - StrategySpec / OptionsSpec
       - research-control memory
       - harness verify
       - promotion/readiness status
       - recent artifacts
  -> Codex / Claude Code on VPS or local worktree
  -> CLI + files
  -> artifacts
  -> harness / promotion / readiness
  -> research-control memory refresh
  -> user checkpoint
```

重要原则:

- 用户不管理内部工具步骤。
- 内部步骤必须可复现、可审计、可 gate。
- 每轮优化只改变一到两个关键变量，除非用户明确要求重构方向。
- 不把单因子失败升级为全局 factor blacklist。
- 不把 research-only 数据升级为 paper-ready evidence。

## 4. Router 执行观察闭环

### 4.1 当前问题

main 分支已经有多个 router research 模块，也已有部分 target-weight 映射:

- beta target weights
- hybrid target weights
- core beta satellite target snapshot
- paper runner 中的部分 target-weight 处理

但这些能力还没有完全统一为一个产品级执行观察闭环。典型问题是: research 报告证明了某个 router 值得继续研究，但系统没有稳定产出统一的目标权重、再平衡意图、成本压力、数据证据和 observation readiness。

### 4.2 目标

router 策略必须从“研究结果”推进到“可观察的执行意图”，但默认不下单。

新增或统一模型:

```text
TargetWeightSnapshot
RebalanceIntent
RouterExecutionObservation
```

建议位置:

```text
open_composer/models/router_execution.py
open_composer/adapters/execution/router_target_weights.py
```

统一输出:

```text
reports/execution/{strategy}-target-weights.json
reports/execution/{strategy}-rebalance-intents.json
reports/execution/{strategy}-execution-observation.json
```

### 4.3 Artifact contract

新增 artifact:

```text
router_target_weights
router_rebalance_intents
router_execution_observation
router_cost_stress
router_data_evidence
router_validation
```

这些 artifact 必须登记在 `harness/artifact_contracts.yaml`，并绑定到对应 risk domain。否则它们只是报告，不是产品控制面。

### 4.4 Risk domain

新增或扩展:

```yaml
router_strategy:
  triggers:
    portfolio_modes:
      - beta_exposure_router
      - hybrid_adaptive_router
      - adaptive_intraday_internal_router
      - core_satellite_router
      - core_beta_satellite_router
  required_artifacts:
    - router_target_weights
    - router_rebalance_intents
    - router_cost_stress
    - router_data_evidence
    - router_validation
```

触发器必须窄，不能误伤普通单标的策略。

### 4.5 Core-beta-satellite 补齐

`core_beta_satellite_router` 应补齐:

- target-weight artifact 输出。
- rebalance-intent artifact 输出。
- observation-only runtime。
- promotion 对这些 artifact 的读取。
- research-control memory 对这些 artifact 的摘要。

### 4.6 Observation 和 order authorization

router 策略进入 paper 前应区分:

```text
execution_substate=observation_only
```

和:

```text
execution_substate=order_authorized
```

但这不是第五个 pass。`paper_ready_pass` 仍由 readiness 和 safety artifact 决定。

## 5. 做空支持

### 5.1 定位

做空属于普通股票/ETF `StrategySpec` 能力，可以进入主线。它不是期权那样的独立 spec 类型。

但做空必须有独立 risk domain。不能只用负仓位把它塞进现有 backtest。

### 5.2 StrategySpec schema

新增字段:

```yaml
position_direction: long_only | short_only | long_short
```

默认:

```yaml
position_direction: long_only
```

### 5.3 Risk domain

新增:

```yaml
short_selling:
  triggers:
    position_direction: [short_only, long_short]
  required_skills:
    - source-researcher
    - backtest-forensics
    - execution-reality-reviewer
  required_artifacts:
    - short_sale_source_cards
    - borrow_cost_estimate
    - short_squeeze_stress
    - ex_dividend_risk_note
    - short_exposure_policy
  blocking_rules:
    - id: short_requires_borrow_and_rule_evidence
      blocks: research_pass
    - id: short_paper_ready_requires_squeeze_and_dividend_stress
      blocks: paper_ready_pass
```

### 5.4 Required artifacts

```text
reports/harness/source_cards/{strategy}.jsonl
reports/research/{strategy}-borrow-cost-estimate.json
reports/research/{strategy}-short-squeeze-stress.json
reports/research/{strategy}-ex-dividend-risk-note.md
reports/harness/execution/{strategy}-short-exposure-policy.json
```

### 5.5 Execution boundary

Backtest 层可以支持负仓位、short entry、cover exit、borrow cost 和 squeeze stress。

Paper 层必须先验证:

- broker paper shorting 是否支持。
- shortable 字段或 borrow availability 是否可得。
- order side 和限制规则。
- hard-to-borrow / easy-to-borrow 信息是否可靠。
- 分红和 corporate action 风险如何处理。

Alpaca Paper 是否支持某些做空行为必须通过 source card 记录，不能靠记忆或猜测。

## 6. 期权支持

### 6.1 总原则

期权支持要有，但不能破坏普通 `StrategySpec`。期权分两类:

1. `OptionsOverlay`: 依附于普通股票/ETF 策略的叠加层。
2. `OptionsSpec`: 独立期权策略。

两类都不进入自动 paper 下单。当前阶段最多到:

```text
execution_substate=observation_only
paper_ready_pass=false
```

### 6.2 OptionsOverlay

适用:

- protective put
- covered call
- collar
- simple hedge overlay

示例:

```yaml
overlay_version: 1
name: qqq_protective_put_overlay
instrument_type: options_overlay
base_strategy: strategy_specs/active/qqq_router.yaml
overlay_type: protective_put
expiry_target: monthly
delta_target: -0.25
max_premium_pct: 1.0
lifecycle: draft
```

新增 risk domain:

```yaml
options_overlay:
  triggers:
    instrument_type: [options_overlay]
  required_artifacts:
    - options_chain_source_cards
    - greeks_profile
    - roll_schedule
    - iv_stress_report
    - overlay_cost_report
    - assignment_risk_note
```

### 6.3 OptionsSpec

独立期权策略使用独立目录:

```text
strategy_specs/options/{name}.yaml
```

示例:

```yaml
spec_version: 1
name: spx_put_spread_weekly
instrument_type: options
underlying: SPX
strategy_type: put_spread
expiry_target: weekly
delta_target_long: -0.30
delta_target_short: -0.15
max_position_pct: 0.05
lifecycle: draft
```

新增 risk domain:

```yaml
options_primary:
  triggers:
    instrument_type: [options]
    required_capability_kinds: [options_chain]
  required_artifacts:
    - options_chain_source_cards
    - greeks_profile
    - contract_selection_log
    - expiry_ladder
    - iv_stress_report
    - assignment_risk_note
  blocking_rules:
    - id: options_no_paper_auto
      blocks: paper_ready_pass
```

### 6.4 Data capability

`capabilities/registry.yaml` 新增:

```yaml
options_chain:
  kind: options_chain
  status: trial
  strict_behavior: research_only
```

期权数据默认不 paper-ready。可以研究、回放、观察，但不自动下单。

## 7. 数据证据分层

### 7.1 不替换 capability.status

现有 `capability.status` 保留:

- `approved`
- `trial`
- `workflow_only`

`paper_ready_timeframes` 继续表示数据源资质。

### 7.2 新增 acquisition tier

新增正交字段:

```text
evidence.acquisition_tier
```

可选值:

```text
sample_smoke
fixture_replay
cached_live
research_cross_check
cross_source_verified
paper_ready_live
```

含义:

- `capability.status` 表示数据源资质。
- `acquisition_tier` 表示本次证据的获取方式和可信层级。

approved 数据源也可能只生成 fixture replay 证据。trial 数据源也可以做 research cross-check，但不能自动支撑 paper readiness。

### 7.3 Yahoo / Stooq / Alpha Vantage OHLCV

这些源可以作为研究交叉验证源，但默认不是 paper-ready:

- Yahoo: research cross-check。
- Stooq: daily research cross-check。
- Alpha Vantage OHLCV: daily adjusted research cross-check。

promotion 和 paper readiness 必须明确展示这些限制。

## 8. Alternative Data Evidence

### 8.1 当前基础

main 已有:

- `llm_or_news_signal` risk domain。
- `feature_packet_schema`。
- `pit_replay_evidence`。
- `marginal_lift_report`。
- `missing_modality_robustness_report`。
- `alt_data_quality.py`。
- `hybrid_news_evidence.py`。

### 8.2 改造方向

新增通用模块:

```text
open_composer/research/alternative_data_evidence.py
```

统一生成:

```text
reports/research/{strategy}-pit-replay.json
reports/research/{strategy}-marginal-lift.json
reports/research/{strategy}-modality-robustness.json
```

如果 LLM/news/macro/event 没有实际影响交易逻辑，必须标记:

```text
advisory_only
```

此时不应强行阻塞普通策略，也不能声称独立 LLM alpha。

## 9. ResearchDesign

### 9.1 目的

让 Codex / Claude Code 生成策略时先明确研究设计，而不是直接追逐回测结果。

### 9.2 Schema

在 `open_composer/models/strategy_spec.py` 增加:

```text
ResearchDesign
```

字段:

```text
parameter_space
candidate_budget
selection_objective
anti_overfit_notes
validation_plan
```

### 9.3 Gate policy

draft 阶段可以 warning，promotion 阶段必须纳入 gate。

不要要求用户手写这些字段。`strategy draft` 和 strategy-designer 应自动生成初稿。

## 10. Promotion / Readiness 接入

### 10.1 Promotion

`open_composer/research/promotion.py` 应读取:

- router target weights。
- router rebalance intents。
- router cost stress。
- router data evidence。
- router validation。
- short-selling evidence。
- research design。
- acquisition tier。
- alternative-data evidence。

### 10.2 Paper readiness

`open_composer/paper_readiness.py` 应增加:

```text
execution_substate
```

规则:

- 普通 long-only 可按现有路径进入 `order_authorized`。
- short / long-short 只有在 short evidence 和 broker source cards 齐全时才可能进入 `order_authorized`。
- router 可以先进入 `observation_only`。
- options overlay / options primary 永远不进入 `order_authorized`，除非未来另有明确产品决策。

## 11. Research Control 接入

`open_composer/research/control.py` 必须读取新增证据，并在 memory packet 中携带最小必要信息:

- 当前有效 target-weight 结构。
- 最近失败的 router 参数或权重组合。
- cost stress 阻塞项。
- data acquisition tier。
- short-selling 阻塞项。
- options overlay / options spec 的 observation 限制。
- research design 的 selection objective。
- 下一轮最小必要 action。

Memory packet 仍然保持短小。它不是全量报告，也不是知识库。

## 12. CLI 与 Agent 边界

CLI 是内部执行入口，不是用户交互菜单。建议第一版新增或统一为:

```bash
uv run oc strategy target-weights <spec>
uv run oc strategy router-cost-stress <spec>
uv run oc strategy data-evidence <spec>
uv run oc strategy alt-data-evidence <spec>
uv run oc strategy short-risk <spec>
uv run oc options overlay-report <overlay>
uv run oc options research-report <options-spec>
```

用户界面不应暴露这些为主要按钮。用户层只应看到:

- 继续优化。
- 继续 N 轮。
- 继续直到目标。
- 基于我的建议继续。
- 结束并总结。

Agent skill 更新只编辑:

```text
.agents/skills/*
```

然后运行:

```bash
uv run python scripts/sync-agent-skills.py
```

不得手动维护第二套 `.claude/skills/`。

## 13. 分阶段实施计划

### P1: Router execution artifact foundation

目标:

- 建立 `TargetWeightSnapshot`、`RebalanceIntent`、`RouterExecutionObservation`。
- 统一 beta/hybrid 现有 target-weight 输出。
- 不改变下单行为。

验收:

- 现有 beta/hybrid target-weight 测试通过。
- 新 artifact schema 可被 harness verify 读取。

### P2: Harness contracts for router and short-selling

目标:

- 新增 router artifacts。
- 新增 short-selling artifacts。
- 新增或扩展 `router_strategy`、`short_selling` risk domain。

验收:

- `oc harness plan <spec>` 能正确触发 router/short domain。
- `oc harness verify <spec>` 能发现缺失 artifact。

### P3: Data acquisition tier

目标:

- 保留 capability status。
- 增加 acquisition tier。
- promotion/readiness 显示 tier 限制。

验收:

- sample/fixture/cache/research_cross_check 不会被误判为 paper-ready evidence。

### P4: Core-beta-satellite observation loop

目标:

- core-beta-satellite 输出 target weights 和 rebalance intents。
- paper runtime 支持 observation-only。

验收:

- 生成 observation artifact。
- 不触发 broker order。

### P5: Router evidence

目标:

- 生成 router cost stress。
- 生成 router data evidence。
- 生成 router validation。

验收:

- promotion 能读取并总结这些证据。
- 缺失时 research/pass 或 paper readiness 按规则阻塞。

### P6: Short-selling minimum viable support

目标:

- `StrategySpec.position_direction`。
- backtest 支持 short-only / long-short 语义。
- short risk artifacts。
- broker paper short 只在 source card 和 readiness 齐全后允许。

验收:

- long-only 行为不回归。
- short domain 正确触发。
- paper order path 默认 blocked。

### P7: ResearchDesign

目标:

- drafter 自动生成 research design。
- parameter sweep、promotion 和 research-control 消费该字段。

验收:

- 新 draft spec 有 research design。
- promotion 能解释 selection objective 和 anti-overfit plan。

### P8: Alternative-data evidence generalization

目标:

- 把 hybrid-only news evidence 泛化。
- 统一 PIT replay、marginal lift、missing modality robustness。

验收:

- 没有实际交易影响时输出 `advisory_only`。
- 有交易影响时进入 `llm_or_news_signal` gate。

### P9: Promotion/readiness/research-control integration

目标:

- promotion、paper readiness、research control 都能读取新增证据。
- memory packet 保持短小但包含下一轮关键控制信息。

验收:

- Codex / Claude 下一轮能看到失败路径和阻塞项。
- 不需要用户重复提示内部流程。

### P10: OptionsOverlay

目标:

- 支持期权叠加层 research / observation。
- 不支持自动下单。

验收:

- overlay artifacts 完整。
- `execution_substate=observation_only`。
- `paper_ready_pass=false`，除非未来产品边界改变。

### P11: OptionsSpec

目标:

- 独立 options spec 类型。
- 独立 research report。
- 独立 risk domain。

验收:

- 普通 StrategySpec 不受污染。
- options 不触发 paper_auto。

### P12: Dashboard read model

目标:

- 展示 target weights。
- 展示 rebalance intents。
- 展示 short risk。
- 展示 options overlay/spec observation 状态。
- 展示 data evidence tier。

验收:

- Dashboard 只读 artifact 和提交 command plan。
- 不运行 backtest、pytest、写文件或下单。

## 14. 严格 Review

### 14.1 产品定位 review

| 检查项 | 结论 |
|---|---|
| 是否仍是个人 AI 策略工作台 | 通过 |
| 是否避免自研弱 agent 替代 Codex/Claude | 通过 |
| 是否把用户交互保持在目标、建议、继续/停止层 | 通过 |
| 是否避免把内部命令暴露为主交互 | 通过 |

### 14.2 架构一致性 review

| 检查项 | 结论 |
|---|---|
| StrategySpec 仍是普通股票/ETF 策略源头 | 通过 |
| Options 使用 overlay/spec 独立路径 | 通过 |
| 所有关键证据进入 artifact contract | 通过 |
| 风险域触发器保持窄触发 | 通过 |
| promotion/readiness/research-control 都接入新增证据 | 通过 |

### 14.3 4-pass 契约 review

| 检查项 | 结论 |
|---|---|
| 未新增第五个 pass | 通过 |
| observation/order 差异用 execution_substate 表达 | 通过 |
| paper_ready_pass 仍是唯一 readiness 布尔 | 通过 |
| workflow_pass 不被误当成 paper readiness | 通过 |

### 14.4 Safety review

| 检查项 | 结论 |
|---|---|
| real-money broker writes 仍不支持 | 通过 |
| short paper order 默认需要专项 evidence | 通过 |
| options 永不默认 paper_auto | 通过 |
| Dashboard/Vercel 不执行重任务 | 通过 |
| 需要联网确认的 broker/order/source 信息落 source card | 通过 |

### 14.5 迭代效率 review

| 检查项 | 结论 |
|---|---|
| research-control 能携带新增证据摘要 | 通过 |
| 每轮优化仍应小步改变 | 通过 |
| 失败路径不会只留在聊天记录里 | 通过 |
| 不把单因子失败全局封杀 | 通过 |
| 不让报告数量替代产品控制 | 通过 |

### 14.6 实施风险

| 风险 | 缓解 |
|---|---|
| Router schema 抽象过早导致大改 | 先适配 beta/hybrid/core-beta 三个现有实现，再抽共享模型 |
| acquisition tier 与 capability status 混淆 | 文档和 schema 中明确两者正交 |
| short-selling 被实现成负仓位捷径 | 必须通过 short_selling risk domain 和 artifacts |
| options 污染普通 StrategySpec | 独立 OptionsOverlay / OptionsSpec |
| skill mirror 不一致 | 只改 `.agents/skills`，用 sync 脚本同步 |
| CLI 面继续膨胀 | CLI 只作为内部执行入口，用户层保持 optimize session 语义 |

## 15. 不做事项

- 不恢复旧 worktree、旧 stash、旧报告、旧 cache 或旧 signal logs。
- 不把 Yahoo/Stooq/Alpha Vantage OHLCV 标成 paper-ready。
- 不让 options 进入自动 paper order。
- 不把 router evidence 做成只读报告而不进 harness。
- 不新增第五个 pass。
- 不把 research-control 扩成大型知识库。
- 不为某一个策略硬编码产品主线。

## 16. 最终验收标准

当本计划完成后，用户应能发出类似:

```text
继续优化 nasdaq_core_beta_satellite_router_daily，目标是提高稳定性并保持低过拟合。
```

系统内部自动完成:

- 读取 research memory。
- 检查 harness risk domains。
- 补齐或更新 target weights / rebalance intents。
- 运行 router cost/data/validation evidence。
- 检查 short/options/data/alt-data 风险。
- 刷新 promotion/readiness。
- 刷新 research-control memory。
- 给用户一个“继续 / 继续 N 轮 / 基于建议继续 / 结束”的结果摘要。

用户不需要知道或手动管理这些内部步骤。

