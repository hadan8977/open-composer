# Open Composer 下一步产品优化计划（严格 Review 后执行版）

日期: 2026-05-22

适用范围: Strategy Console 已落地后的下一阶段产品优化。

## 0. 结论

下一步只补一个轻量的策略迭代控制闭环:

```text
从 artifacts 恢复 Project 状态
-> 生成下一轮可执行请求
-> worker 完成研究/优化
-> Product API 验证产物
-> Dashboard 显示状态、阻塞项和下一步
```

这不是新 agent runtime，也不是复杂 Dashboard，更不是机构级风险系统。核心目标是:

- 用户不需要每次重新解释项目结构。
- 用户能看到策略卡在哪里、为什么卡住、下一步做什么。
- Codex / Claude Code 每轮拿到短小、准确、可行动的上下文。
- 策略进入 paper 前，必须受 Factor Quality、Execution Reality、Alt/LLM Evidence 和 paper readiness 约束。

## 1. 严格 Review 裁决

| 项目 | 是否必要 | 是否已做 | 可行性 | 与核心目标关系 | 裁决 |
|---|---|---|---|---|---|
| Project Artifact State | 必要 | 未做；Dashboard catalog 会间接读部分 reports，但没有 Project 级状态文件 | 高 | 直接解决“新会话/新 worker 不知道当前状态” | P1 必做 |
| Project Run Ledger | 必要，但必须轻量 | 已有 `StrategyProjectRun`、`project run-append`、changed_paths/spec 对账；缺 step 和 blocker 摘要 | 高 | 解决每轮结果不可追踪、重复失败不可见 | P1 增量扩展，不新建复杂 trace/snapshot 系统 |
| IterationController MVP | 必要 | 部分已做: Dashboard Continue 会创建普通 agent request；没有确定性 plan/context 编译 | 中高 | 把“继续优化”从自由 prompt 变成产品流程 | P2 必做，但只做计划和 request |
| 三条证据轨道驱动控制流 | 必要 | Project Evidence、Dashboard 展示、部分 report 解析已做；尚未驱动下一步动作 | 高 | 直接对应策略质量、执行难度、LLM/另类数据贡献 | P3 必做 |
| 金融边界小模型 | 条件必要 | `RouterExecutionObservation` 已存在；short/options 边界已有基础；`RiskContext`/`ExposureSummary` 未做 | 中 | 防止 short/router/options 混进错误模型 | P4 条件做，避免平台化 |
| Dashboard Project Detail 增强 | 必要，但只是读模型增强 | 已有 Project Detail、Evidence 面板、操作按钮 | 高 | 让用户看懂状态和下一步 | P5 增量做 |
| 复杂 trace/snapshot 独立体系 | 暂不必要 | 未做 | 中 | 当前会过重 | 拒绝；先放进 Run Ledger |
| 外部 agent runtime | 不必要 | 未做 | 低收益 | 偏离产品定位 | 拒绝 |
| CPU profiler / 性能追踪系统 | 不必要 | 未做 | 低收益 | 不解决策略迭代问题 | 拒绝 |
| 重型 BI/workspace Dashboard | 不必要 | 未做 | 中低 | 当前数据量不需要 | 拒绝 |
| 机构级 pricing/risk 依赖 | 不必要 | 未做 | 低 | 超出个人工作台定位 | 拒绝 |
| 复杂模型路由 / 自动预算模型 / 复杂通知策略 | 不必要 | 未做或只有轻量基础 | 中 | 与当前核心痛点弱相关 | 拒绝 |

最终优先级:

```text
P1 Artifact State + Run Ledger
P2 IterationController MVP
P3 Evidence Tracks 接入控制流
P4 金融边界按需接入
P5 Dashboard Project Detail 增强
```

## 2. 当前问题

### 2.1 迭代上下文仍不稳定

已有:

- `StrategyProject`
- `context.md`
- `agent_requests`
- `project run-append`

但下一轮 worker 仍可能不知道:

- 上一轮实际做了哪些步骤。
- 哪些 artifact 已经存在。
- 哪些 blocker 已经重复出现。
- 现在应该补证据、修失败，还是继续优化参数。

### 2.2 Project 状态和研究产物没有稳定对账

Dashboard 能展示 Project 和 Evidence 状态，但 Project 状态还不能稳定地从 reports、gates、latest run 中恢复。

需要一个确定性、只读、可测试的状态恢复层，而不是依赖 worker 自报或当前对话记忆。

### 2.3 三条证据轨道还没有驱动迭代动作

已有:

- Factor Quality
- Execution Reality
- Alt/LLM Evidence

但它们目前更像展示状态，还没有成为 controller 判断“下一步做什么”的核心输入。

### 2.4 金融对象边界需要继续收紧

必须保持:

- short 是股票/ETF 持仓方向和风险域问题。
- router 是目标权重、再平衡意图和执行观察问题。
- options 不能混入普通 `StrategySpec`。
- execution intent 不能等同 broker order。

这部分只做边界和证据，不做机构级定价系统。

## 3. 必做能力

### 3.1 Project Artifact State

新增轻量状态扫描器:

```text
open_composer/research/artifact_state.py
projects/{project}/artifact-state.json
reports/research/state/{strategy}-artifact-state.json
```

作用:

- 只读已有文件。
- 扫描 StrategySpec、latest run、promotion、paper readiness、Factor Lab、Execution Reality、Alt/LLM Evidence。
- 推断当前 Project 的 `last_successful_step`、`blocked_items`、`warning_items`、`latest_artifacts`。
- 给 `context.md`、Dashboard、IterationController 复用。

不做:

- 不运行 backtest。
- 不运行 pytest。
- 不改 StrategySpec。
- 不把推断状态当 paper readiness。

最小字段:

```yaml
schema_version: 1
project_id: qqq-pullback-15m
strategy_name: qqq_pullback_15m
current_spec_path: strategy_specs/drafts/qqq_pullback_15m.yaml
last_successful_step: parameter_sweep
latest_artifacts:
  promotion: reports/research/qqq_pullback_15m-promotion.json
evidence_status:
  factor_quality: warning
  execution_reality: blocked
  alt_llm_evidence: not_applicable
blocked_items:
  - execution_reality:missing_capacity_stress
warning_items: []
generated_at: "2026-05-22T08:12:00Z"
```

### 3.2 Project Run Ledger

复用现有 `StrategyProjectRun`，增量增加两个结构，不新增独立复杂 trace/snapshot 文件体系。

新增模型:

```text
ProjectStepEvent
ProjectBlockerSummary
```

新增字段:

```yaml
step_events:
  - step_name: artifact_state_scan
    status: ok
    started_at: "2026-05-22T08:10:00Z"
    ended_at: "2026-05-22T08:10:03Z"
    output_artifacts:
      - projects/qqq-pullback-15m/artifact-state.json
    blocked_items: []
    warning_items: []
blocker_summary:
  trigger: promotion_blocked
  failed_step: promotion
  root_blockers:
    - walk_forward_report:missing
  next_minimal_actions:
    - generate missing walk-forward evidence
  do_not_repeat:
    - do not rerun broad parameter sweep before walk-forward evidence exists
```

规则:

- `step_events` 只记录少量结构化事实，不写 stdout，不写长报告。
- `blocker_summary` 只在 failed、blocked 或重复退化时写。
- 同类 blocker 连续出现两轮以上，自动进入 `do_not_repeat`。
- Product API 继续验证 `changed_paths` 是否存在、spec 是否可加载、worker gate claim 是否可信。

CLI 增量:

```text
oc project run-append <project> --summary-json <path>
```

原因: 复杂字段不适合全部塞进命令行参数。保留现有简单参数，同时允许 worker 用 JSON/YAML summary 回写完整结构。

### 3.3 IterationController MVP

新增:

```text
open_composer/research/iteration_controller.py
oc project iterate <project_id> --rounds 3
oc project iterate <project_id> --advice advice.md
```

首版只做计划和请求，不直接调用模型改策略。

它做:

1. 读取 `project.yaml`。
2. 运行 `ArtifactStateScanner`。
3. 读取 latest run ledger。
4. 汇总 blocker 和 `do_not_repeat`。
5. 生成新的 `context.md`。
6. 生成下一轮 step plan。
7. 创建 `reports/agent_requests/{id}.json`。
8. 更新 Project `next_action`。

它不做:

- 不新增 agent runtime。
- 不直接调用 LLM。
- 不自动大范围参数搜索。
- 不自动 paper order。
- 不自动跨越 paper readiness。
- 不运行 pytest/backtest；只在需要时生成对应 agent request。

决策顺序:

```text
known repo/test failure
-> missing or invalid artifact
-> evidence blocker
-> promotion/readiness blocker
-> small strategy optimization
```

每轮最多改变一到两个关键变量。

### 3.4 三条证据轨道驱动下一步动作

三条 evidence 不单独做重页面，只进入:

- Project Evidence
- ArtifactState
- Run Ledger
- `context.md`
- Dashboard Project Detail

#### Factor Quality

需要支持:

- IC / RankIC。
- 分位收益。
- 因子相关性。
- 因子稳定性。
- 覆盖率和缺失率。

规则:

- 无显式因子时为 `not_applicable`。
- 有自定义因子但缺 Factor Lab 时，不能直接进入 paper-ready。
- 高相关、低稳定、低样本进入 blocker 或 warning。

#### Execution Reality

需要支持:

- 滑点压力。
- 成交量和容量。
- spread / cost proxy。
- 开盘跳空。
- partial fill。
- order style 对比。

规则:

- open execution、leveraged ETF、paper_auto、router rebalance 必须触发。
- 缺 execution evidence 时，不允许 `paper_ready_pass=true`。
- 成本压力下收益消失或容量不足时，下一步优先补执行证据，不继续盲目调参。

#### Alt/LLM Evidence

需要支持:

- point-in-time packet: `visible_at`、`published_at`、`fetched_at`、source、input hash、prompt hash。
- single-modality baseline。
- marginal lift。
- missing-modality robustness。
- 与纯量化 baseline 的信号差异。

规则:

- 无 LLM/news/event/macro/alternative-data 依赖时为 `not_applicable`。
- PIT 元数据不完整时不能进入 paper readiness。
- 边际贡献不足或信号等同纯量化 baseline 时，`llm_contribution_pass=false`。

### 3.5 金融边界接入

必须克制。这里不是新平台，只是让 Project 状态能正确表达金融边界。

已有基础:

- `RouterExecutionObservation` 已存在。
- short / options / router 的部分风险域和 artifacts 已存在。

需要做:

- short blockers 进入 ArtifactState 和 Run Ledger。
- router target weights / rebalance intents / execution observation 进入 ArtifactState。
- options evidence 进入 ArtifactState，但保持 observation-only。

可选小模型:

```text
RiskContext
ExposureSummary
```

只有当现有 report/gate 字段无法一致表达 short/router/options 暴露时才新增。若可以直接复用现有 artifacts，就不新增模型。

边界:

- short 进入普通 `StrategySpec.position_direction`，并触发 `short_selling` risk domain。
- router 必须输出 target weights / rebalance intents / execution observation。
- options 走 `OptionsOverlay` / `OptionsSpec`，MVP 只允许 research / observation，不允许 `paper_auto`。
- execution intent 不是 broker order。paper order 仍由确定性 Product Runner 和用户确认控制。

## 4. Dashboard 需要怎么改

Dashboard 不新增复杂 workspace，不引入重型 BI 表格组件。

只增强 Project Detail:

- 显示 latest artifact state。
- 显示 latest run ledger。
- 显示 blocker summary。
- 显示 `do_not_repeat`。
- 显示 next minimal action。
- 显示三条 evidence 的状态、artifact path 和 blockers。

按钮保持少量:

- Continue iteration。
- Stop。
- Archive。
- Request paper review。
- Refresh catalog。

Dashboard 仍不能:

- 直接写 StrategySpec。
- 跑 backtest。
- 跑 pytest。
- 跑 parameter sweep。
- 下 broker order。
- 处理真钱交易。

## 5. 实施顺序

### P1: Artifact State + Run Ledger

目标: Project 状态可恢复，每轮结果可追踪。

任务:

1. 新增 `artifact_state.py`。
2. 写 `projects/{project}/artifact-state.json`。
3. 扩展 `StrategyProjectRun`，加入 `step_events` 和 `blocker_summary`。
4. `project run-append` 支持 `--summary-json` 并验证新增字段。
5. 单元测试覆盖缺文件、坏 schema、blocked evidence、重复 blocker。

验收:

- 删除 `context.md` 后，仍可从 artifacts 重建 Project 当前状态。
- worker 回写缺失路径时，Project 自动 blocked。
- 重复 blocker 能进入 `do_not_repeat`。

### P2: IterationController MVP

目标: “继续优化”不再只是一个自由 prompt，而是可恢复的产品流程。

任务:

1. 新增 `iteration_controller.py`。
2. 新增 `oc project iterate`。
3. controller 生成 step plan。
4. controller 刷新 `context.md`。
5. controller 创建 `agent_request`。
6. Dashboard Continue 调用 controller，而不是直接写普通 agent request。

验收:

- 用户从 Dashboard 点 Continue 后，生成的 request 带有 artifact state、latest blocker、next minimal action。
- 有 blocker 时优先补 blocker。
- 无 blocker 时才进入小范围策略优化。

### P3: Evidence Tracks 接入控制流

目标: 三条证据轨道能决定下一轮动作。

任务:

1. ArtifactState 扫描 Factor Quality、Execution Reality、Alt/LLM Evidence。
2. Run Ledger 写入 evidence blocker。
3. `context.md` 摘要三条 evidence 状态。
4. Controller 根据 evidence blocker 生成补证据任务。
5. Dashboard Project Evidence 显示 next minimal action。

验收:

- 缺 Factor Lab 时不会继续盲目优化参数。
- 缺 Execution Reality 时不会进入 paper-ready。
- 缺 PIT / marginal lift / robustness 时不会把 LLM/另类数据当独立 Alpha。

### P4: 金融边界接入

目标: short/router/options 的证据要求进入 Project 控制面。

任务:

1. short risk blockers 进入 ArtifactState 和 Run Ledger。
2. router target weights / rebalance intents / execution observation 进入 ArtifactState。
3. options evidence 进入 ArtifactState，但保持 observation-only。
4. 评估是否需要 `RiskContext` / `ExposureSummary`；能复用现有 artifacts 就不新增。

验收:

- short 缺 borrow / squeeze / ex-dividend 证据时 blocked。
- router 能显示 observation_only / order_authorized 子状态。
- options 不会进入 paper_auto。

### P5: Dashboard Project Detail 增强

目标: 用户不用打开多个 reports 文件也能知道策略状态。

任务:

1. Project Detail 显示 artifact state。
2. Project Detail 显示 latest run ledger。
3. Project Detail 显示 blocker summary 和 `do_not_repeat`。
4. Evidence 面板显示 artifact path、blocker、next action。

验收:

- 用户能在一个 Project 页面看清: 当前状态、阻塞项、证据缺口、下一步动作。
- 页面不展示“好策略/能赚钱”，只展示证据、状态和限制。

## 6. 明确不做

- 不引入外部 agent runtime。
- 不引入 CPU profiler 或性能追踪系统。
- 不引入重型表格引擎或复杂 Dashboard workspace。
- 不引入机构级 pricing/risk 依赖。
- 不做复杂模型路由。
- 不做自动预算模型。
- 不做复杂通知策略。
- 不新增第五个 pass。
- 不让 Dashboard 浏览器端执行长任务。
- 不把 options 塞进普通 `StrategySpec`。

## 7. 最终验收标准

产品层验收:

- 用户可以创建 Project、点击 Continue，并得到一条包含明确上下文的 agent request。
- 用户能在 Dashboard 看懂为什么 blocked、下一步做什么、哪些事情不要重复。
- Project 状态可以从 artifacts 恢复，不依赖当前对话。

研究层验收:

- StrategySpec 仍是策略行为真相来源。
- Factor Quality、Execution Reality、Alt/LLM Evidence 的 unknown/blocked 不会被当作 pass。
- worker 自报不会直接决定 paper readiness。

安全层验收:

- paper order 仍需要 deterministic gate 和用户确认。
- real-money broker write 仍然 out of scope。
- Dashboard 和 Vercel 不执行 backtest、pytest、file write 或 broker order。

实现层验收:

- 文档、CLI、Product API、Dashboard read model 使用同一套 Project 状态字段。
- 新增字段有单元测试。
- `uv run ruff format .`、`uv run ruff check .`、`uv run pytest` 在代码实现阶段通过。
