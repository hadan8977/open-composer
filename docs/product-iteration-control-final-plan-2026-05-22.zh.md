# Open Composer 策略迭代控制最终计划

日期: 2026-05-22

适用范围: Open Composer 下一阶段产品实现

## 0. 最终结论

下一阶段最优先的产品能力不是新增更多策略模块，也不是增加 Dashboard 复杂度，而是把策略生成和优化过程本身变成可恢复、可审计、可自动继续的控制闭环。

核心目标:

```text
用户只表达目标、建议、轮数和停止条件；
Open Composer 自动决定内部步骤；
Codex / Claude Code 每一轮都带着最新证据、失败路径和最小下一步继续。
```

必须优先实现:

1. `StrategyIterationTrace`: 每轮内部步骤的结构化事件日志。
2. `FailureSnapshot`: 失败或阻塞发生时立即写入的紧凑快照。
3. `ArtifactStateScanner`: 从已有 artifacts 重建当前状态，避免新 session 丢上下文。
4. `research-control memory` 强化: 将 trace/snapshot/artifact state 压缩进 <=1KB 的下一轮控制包。
5. `iteration_controller`: 将用户的“继续优化”类指令转换为内部自动执行序列。

必须保持:

- 不新增 agent runtime。
- 不要求用户每次写专门提示词。
- 不新增第五个 pass。
- Dashboard 只读展示，不跑回测、不写文件、不下单。
- 普通 `StrategySpec` 不承载期权合约结构。

## 1. 用户交互目标

用户不应该手动选择内部工程步骤，例如:

- 做参数扫描。
- 生成研究报告。
- 修复失败测试。
- 补 artifact。
- 刷新 memory。
- 生成 target weights。
- 跑 paper readiness。

用户只需要选择:

```text
结束
继续优化 N 轮
继续直到达到目标
基于我的建议继续
查看为什么卡住
进入 paper observation / readiness 审查
```

所有内部动作由 `iteration_controller` 根据当前状态自动展开。

## 2. 保持不变的产品契约

### 2.1 四层 pass 不变

继续使用:

```text
workflow_pass
research_pass
llm_contribution_pass
paper_ready_pass
```

不新增 `paper_observation_pass` 或 `paper_order_pass`。

若需要区分观察和下单，只在 readiness 输出中使用:

```text
execution_substate:
  blocked | observation_only | order_authorized
```

### 2.2 StrategySpec 边界不变

普通 `StrategySpec` 覆盖:

- long-only 股票/ETF 策略。
- short-only 股票/ETF 策略。
- long-short 股票/ETF 策略。
- router 股票/ETF 策略。

期权不进入普通 `StrategySpec`。期权走:

```text
OptionsOverlay
OptionsSpec
```

并且 MVP 阶段:

```text
options max execution_substate = observation_only
options paper_auto = unsupported
```

### 2.3 Artifact contract 仍是控制面

所有新增制品必须能进入:

- `harness/artifact_contracts.yaml`
- `harness/risk_domains.yaml`
- promotion / paper readiness
- `open_composer/research/control.py`
- dashboard catalog

没有进入控制面的报告不算产品能力。

## 3. StrategyIterationTrace

### 3.1 目的

记录每轮策略迭代实际发生了什么，让新一轮 Codex / Claude Code 不再重新猜测:

- 上一轮做了哪些步骤。
- 哪个步骤成功、警告、阻塞或失败。
- 输入和输出 artifact 是什么。
- 哪些 blocker 必须优先处理。
- 哪些步骤耗时异常。
- 是否出现重复失败。

### 3.2 文件位置

新增:

```text
open_composer/research/iteration_trace.py
reports/research/traces/{strategy}-{run_id}.jsonl
reports/research/traces/{strategy}-latest.json
```

### 3.3 Schema

Trace event 必须用绝对时间戳，不只存 `runtime_seconds`。这样后续即使 gate 并发执行，也能重建时间线。

```json
{
  "schema_version": "1",
  "strategy_name": "qqq_pullback_15m",
  "run_id": "iter-20260522-001",
  "step_id": "step-0007",
  "parent_step_id": null,
  "step_name": "parameter_sweep",
  "event_type": "step_end",
  "status": "warning",
  "started_at": "2026-05-22T08:10:00Z",
  "ended_at": "2026-05-22T08:10:18Z",
  "input_artifacts": [],
  "output_artifacts": [
    "reports/research/qqq_pullback_15m-parameter-sweep.json"
  ],
  "blocked_items": [],
  "warning_items": ["high_pbo_proxy=0.58"],
  "metadata": {
    "candidate_count": 12
  }
}
```

字段要求:

- `run_id`: 一轮或一组连续优化的唯一 ID。
- `step_id`: 单个步骤唯一 ID。不能依赖数组序号。
- `parent_step_id`: 支持将来子步骤和并发 gate。
- `started_at` / `ended_at`: ISO 8601 UTC。
- `status`: `running | ok | warning | blocked | failed | skipped`。
- `metadata`: 只放小型结构化数据，不放完整报告。

### 3.4 Step 类型

初始支持:

```text
spec_validation
context_compile
code_generation
unit_tests
repo_check
backtest
parameter_sweep
scenario_analysis
research_report
harness_verify
promotion
paper_readiness
target_weights
rebalance_intents
research_control_update
```

其中 `scenario_analysis` 用于 alternative-data、router cost stress、short squeeze、options IV stress 等场景分析，避免不同场景覆盖同一个 research step。

### 3.5 写入规则

- 每个内部步骤开始写 `step_start`。
- 每个内部步骤结束写 `step_end`。
- 如果步骤失败，先写 trace，再触发 `FailureSnapshot`。
- trace 不存大文本、不存完整 stdout、不存完整 backtest。
- 大内容只通过 `artifact_refs` 间接引用。

## 4. FailureSnapshot

### 4.1 目的

当失败或阻塞发生时，立即捕获最小可行动上下文，避免下一轮 Codex / Claude Code 重复走错路。

FailureSnapshot 不是日志，也不是报告。它只回答:

1. 卡在哪里。
2. 为什么卡住。
3. 下一步最小动作是什么。
4. 什么不要重复。

### 4.2 文件位置

新增:

```text
open_composer/research/failure_snapshot.py
reports/research/snapshots/{strategy}-{run_id}-failure.json
reports/research/snapshots/{strategy}-latest-failure.md
```

### 4.3 触发条件

必须事件触发，不等到一轮结束再统一写。

触发:

- `unit_tests` failed。
- `repo_check` failed。
- `harness_verify` blocked / failed。
- promotion blocked。
- paper readiness blocked。
- required artifact missing。
- required artifact schema invalid。
- parameter sweep 明显退化。
- 同类 blocker 连续出现。
- scenario outputs 出现重大分歧。
- 达到迭代上限仍未改善。

### 4.4 Schema

```json
{
  "schema_version": "1",
  "strategy_name": "qqq_pullback_15m",
  "run_id": "iter-20260522-001",
  "trigger": "promotion_blocked",
  "failed_step_id": "step-0009",
  "failed_step": "promotion",
  "last_successful_step": "parameter_sweep",
  "root_blockers": [
    "walk_forward_report:missing",
    "data_source:research_cross_check_not_paper_ready"
  ],
  "next_minimal_actions": [
    "generate missing walk-forward evidence",
    "refresh research-control memory"
  ],
  "do_not_repeat": [
    "do not rerun broad parameter sweep before missing walk-forward evidence is produced"
  ],
  "artifact_refs": [
    "reports/research/qqq_pullback_15m-promotion.json"
  ],
  "created_at": "2026-05-22T08:12:00Z"
}
```

### 4.5 自动生成 `do_not_repeat`

`do_not_repeat` 不应依赖人工手写。

生成逻辑:

1. 读取同策略历史 snapshots。
2. 聚合 `failed_step + root_blockers`。
3. 如果同类失败连续出现 2 次以上，自动生成 do-not-repeat。
4. 若用户 advice 明确要求重试，则允许覆盖，但必须写入 metadata。

### 4.6 last_successful_step 回退

如果 trace 文件损坏、缺失，或当前 session 是新启动的，`last_successful_step` 不能直接为空。

应调用 `ArtifactStateScanner` 从现有 artifact 推断:

```text
spec_validation -> unit_tests -> backtest -> parameter_sweep
-> harness_verify -> promotion -> paper_readiness
```

只读文件存在性、schema 状态和 mtime，不重新运行回测。

## 5. ArtifactStateScanner

### 5.1 目的

让系统能从已有 artifacts 重建当前状态，避免依赖易过期的 memory packet。

新增:

```text
open_composer/research/artifact_state.py
```

### 5.2 输出

```json
{
  "strategy_name": "qqq_pullback_15m",
  "inferred_state": "promotion_blocked",
  "last_successful_step": "parameter_sweep",
  "latest_artifacts": {
    "parameter_sweep": "reports/research/qqq_pullback_15m-parameter-sweep.json",
    "promotion": "reports/research/qqq_pullback_15m-promotion.json"
  },
  "blocked_items": [
    "walk_forward_report:missing"
  ],
  "warning_items": [],
  "artifact_mtimes": {
    "promotion": "2026-05-22T08:11:30Z"
  }
}
```

### 5.3 使用位置

必须被以下模块复用:

- `open_composer/research/control.py`
- `open_composer/research/failure_snapshot.py`
- `open_composer/research/iteration_controller.py`
- dashboard catalog

### 5.4 原则

- 只读 artifacts。
- 不执行回测。
- 不执行测试。
- 不改策略。
- 不把推断状态当作 paper readiness，只作为上下文恢复。

## 6. Research-Control Memory 强化

### 6.1 当前定位不变

`open_composer/research/control.py` 继续是 reducer，不是执行器。

它负责读取已有证据，生成:

```text
reports/research/control/{strategy}-state.json
reports/research/control/{strategy}-memory.md
```

### 6.2 新增输入

新增读取:

- latest trace summary。
- latest failure snapshot。
- artifact state scanner 输出。
- latest test / repo-check status。
- latest promotion/readiness blockers。
- router / short / options evidence 摘要。

### 6.3 Memory packet 约束

继续保持短小，默认 <=1KB。

允许进入:

- 当前目标。
- 当前最佳候选。
- 最近失败 trigger。
- 最近 failed step。
- 当前 blockers。
- 自动生成的 do-not-repeat。
- 下一步最小动作。
- data tier / paper substate / risk-domain 限制。

禁止进入:

- 完整 trace。
- 完整 FailureSnapshot。
- 完整 backtest。
- 完整 stdout。
- 完整 research report。
- 长篇解释。

## 7. Iteration Controller

### 7.1 文件位置

新增:

```text
open_composer/research/iteration_controller.py
```

### 7.2 CLI

新增高层入口:

```text
oc strategy iterate <spec> --rounds 3
oc strategy iterate <spec> --until-objective objective.json
oc strategy iterate <spec> --advice advice.md
oc strategy iterate <spec> --review-blockers
```

这些命令是用户入口。内部仍可调用现有 backtest、sweep、promotion、readiness、repo check 等命令。

### 7.3 执行顺序

每轮:

1. 读取 `StrategySpec` / `OptionsSpec`。
2. 读取 research-control memory。
3. 读取 latest trace。
4. 读取 latest failure snapshot。
5. 运行 `ArtifactStateScanner`。
6. 编译下一轮上下文。
7. 如果测试或 repo check 失败，先修失败。
8. 如果 artifact blocked，先补 artifact。
9. 如果 promotion/readiness blocked，先处理 blocker。
10. 如果无 blocker，再做小范围策略优化。
11. 每轮最多改变一到两个关键变量。
12. 每个步骤写 trace。
13. 每个失败即时写 snapshot。
14. 每轮结束刷新 research-control memory。

### 7.4 Context 传递

首版优先使用显式参数传递:

```text
spec_path
root
run_id
```

暂不引入全局隐式上下文。只有当 controller 调用栈明显变深、重复参数显著污染函数签名时，再评估轻量 context helper。

原因:

- 显式参数更容易测试。
- 当前阶段比隐式上下文更清晰。
- 避免隐藏依赖导致 Codex/Claude Code 修改时误判。

### 7.5 Gate 并发

首版不并发化 gate。

原因:

- 当前优先问题是状态正确性，不是 gate 性能。
- 并发会增加 trace 合并复杂度。
- `step_id` / `parent_step_id` 已为未来并发预留。

后续如果 artifact checker 数量显著增加，再将独立文件读取类 gate 并发化。

## 8. 金融边界收紧

### 8.1 做空

做空继续作为普通股票/ETF 策略的方向扩展:

```text
position_direction = long_only | short_only | long_short
```

触发:

```text
short_selling risk domain
```

必须证据:

- borrow cost estimate。
- short squeeze stress。
- ex-dividend risk note。
- borrow / locate source card。

控制要求:

- 缺少证据时 promotion/readiness blocked。
- blocker 进入 FailureSnapshot 和 memory packet。
- broker adapter 不得在证据缺失时自动 short order。

### 8.2 Router

Router 不以普通信号通过作为终点，必须输出:

```text
TargetWeightSnapshot
RebalanceIntentSnapshot
RouterExecutionObservation
```

路径:

```text
open_composer/models/router_execution.py
reports/execution/{strategy}-target-weights.json
reports/execution/{strategy}-rebalance-intents.json
reports/execution/{strategy}-execution-observation.json
```

控制要求:

- target weights / rebalance intents / observation 进入 artifact contract。
- promotion/readiness 读取 router evidence。
- research-control memory 摘要 router substate 和 blockers。
- 默认 `execution_substate=observation_only`。
- 只有全部 readiness 条件满足时才允许 `order_authorized`。

### 8.3 期权

期权不进入普通 `StrategySpec`。

新增或保留独立路径:

```text
OptionsOverlay
OptionsSpec
```

Overlay evidence:

- greeks profile。
- roll schedule。
- IV stress report。
- assignment risk note。

Primary options evidence:

- contract selection log。
- expiry ladder。
- greeks profile。
- IV stress report。
- assignment risk note。

控制要求:

- options max substate 为 `observation_only`。
- options 不允许 paper_auto。
- options evidence 进入 artifact contract / risk domain / memory。

### 8.4 ScenarioContext

新增轻量场景上下文:

```text
open_composer/research/scenario_context.py
```

用途:

- router cost stress。
- alternative-data evidence。
- short squeeze stress。
- options IV stress。

原则:

- 只表达场景假设。
- 不拉外部专属数据。
- 不替代 StrategySpec。
- 同一策略不同 scenario 的输出不得互相覆盖。

建议字段:

```json
{
  "scenario_id": "liquidity_stress_01",
  "label": "liquidity stress",
  "assumptions": {
    "slippage_bps": 25,
    "spread_multiplier": 2.0
  },
  "applies_to": ["router_cost_stress"]
}
```

## 9. Artifact Contract 补强

### 9.1 Trace / Snapshot contract

新增 artifact:

```text
strategy_iteration_trace
failure_snapshot
artifact_state
```

最低 required fields:

```text
strategy_iteration_trace:
  schema_version
  strategy_name
  run_id
  step_id
  step_name
  event_type
  status
  started_at
  ended_at

failure_snapshot:
  schema_version
  strategy_name
  run_id
  trigger
  failed_step
  root_blockers
  next_minimal_actions
  do_not_repeat

artifact_state:
  strategy_name
  inferred_state
  last_successful_step
  latest_artifacts
```

### 9.2 Dependency metadata

暂不在 artifact contract 中引入复杂执行调度字段。

如果需要表达依赖关系，先使用简单 metadata:

```text
depends_on:
  - router_target_weights
```

暂不新增 `path_dependent` 作为通用 contract 字段。

原因:

- `path_dependent` 容易和金融语义混淆。
- artifact schema 校验不应承担执行调度。
- 首版只需要知道 artifact 的依赖，不需要建立复杂 DAG。

## 10. Dashboard 范围

Dashboard 只读展示新增制品:

- latest trace summary。
- latest failure snapshot。
- artifact state。
- memory packet。
- blockers / warnings。
- target weights。
- rebalance intents。
- short/router/options evidence。
- paper readiness substate。

Dashboard 不做:

- backtest。
- parameter sweep。
- pytest。
- repo check。
- file write。
- strategy mutation。
- broker order。

首版不做 SSE / delta streaming。Dashboard 数据量很小，轮询或刷新 JSON 足够。只有 paper status / P&L 变成明显实时需求后，再考虑 SSE JSON delta。

## 11. 实施顺序

### P1: Schema 与状态恢复

1. 新增 `iteration_trace.py`。
2. 新增 `failure_snapshot.py`。
3. 新增 `artifact_state.py`。
4. 新增 artifact contracts。
5. 单元测试覆盖 schema、写入、读取、状态重建。

### P2: Research-Control 接入

1. `control.py` 读取 trace summary。
2. `control.py` 读取 latest failure snapshot。
3. `control.py` 读取 artifact state。
4. memory packet 加入 blocker、do-not-repeat、next minimal action。
5. 保持 <=1KB。

### P3: Iteration Controller

1. 新增 `iteration_controller.py`。
2. 新增 `oc strategy iterate`。
3. 首版只串行执行内部步骤。
4. 每步写 trace。
5. 失败即时写 snapshot。
6. 每轮结束刷新 memory。

### P4: 金融边界接入

1. short blockers 接入 snapshot/memory。
2. router execution observation 接入 snapshot/memory。
3. options evidence 接入 snapshot/memory。
4. 新增 `ScenarioContext`，先接 router cost stress 和 alternative-data evidence。

### P5: Dashboard 只读展示

1. dashboard catalog 读取 trace/snapshot/artifact state。
2. 策略详情页显示最新 blocker 和 next action。
3. target weights / rebalance intents / readiness substate 只读展示。

### P6: 后续优化

仅当真实需要出现后再做:

- gate 并发化。
- context helper。
- SSE JSON delta。
- 更复杂的 scenario matrix。

## 12. 验收标准

### 12.1 Trace

- 每个 `oc strategy iterate` run 都生成 trace。
- 每个 step 有 `step_id`、`started_at`、`ended_at`。
- trace 可被读取并摘要进 control state。

### 12.2 Snapshot

- promotion blocked、paper readiness blocked、测试失败时立即生成 snapshot。
- snapshot 包含 root blockers、next minimal actions、do-not-repeat。
- 重复失败能自动进入 do-not-repeat。

### 12.3 Artifact State

- 删除 memory 文件后，系统仍能从 artifacts 推断 last successful step。
- artifact state 不运行回测、不修改文件。

### 12.4 Research-Control

- memory packet <=1KB。
- memory packet 包含最近 blocker 和 do-not-repeat。
- memory packet 不包含完整报告或长日志。

### 12.5 Controller

- 用户能用 `oc strategy iterate <spec> --rounds 3` 触发连续优化。
- 测试失败时优先修测试。
- artifact blocked 时优先补证据。
- 无 blocker 时才做小范围策略优化。
- 每轮最多改变一到两个关键变量。

### 12.6 金融边界

- short / router / options blockers 都能进入 snapshot 和 memory。
- options 不进入 paper_auto。
- router readiness 能区分 observation_only 和 order_authorized。

## 13. 最终裁决

采纳:

- Trace schema 使用 `started_at` / `ended_at`。
- Trace 使用 `step_id` / `parent_step_id`，为未来并发预留。
- FailureSnapshot 必须事件触发。
- `do_not_repeat` 必须可由历史失败自动生成。
- 新增 artifact-based state rebuild。
- 新增 `scenario_analysis` step。
- 新增轻量 `ScenarioContext`。

推迟:

- ContextVar / 隐式上下文。
- gate 并发化。
- Dashboard SSE / delta。
- 复杂 scenario matrix。

拒绝:

- 新 agent runtime。
- 指令级 tracing 或外部 profiler 依赖。
- 机构级 risk/pricing 平台化。
- Dashboard 获得执行权。
- 期权混入普通 `StrategySpec`。
- 新增第五个 pass。

最先做的事情只有一个:

```text
StrategyIterationTrace + FailureSnapshot + ArtifactStateScanner
```

这三个能力是 Open Composer 下一阶段自动化策略迭代的底座。没有它们，Codex / Claude Code 仍然会依赖用户提示词和临时上下文；有了它们，Open Composer 才能把“继续优化”变成稳定的产品能力。
