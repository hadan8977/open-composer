# Open Composer Dashboard 与 Strategy Console 重构方案

日期: 2026-05-22

适用范围: Open Composer 下一阶段产品交互、Dashboard、策略生成、优化迭代、模拟盘监控和通知系统重构。

## 0. 结论

Open Composer 目前的核心能力已经不只是“运行几条 CLI 命令”，而是一个由 `StrategySpec`、Harness、研究报告、gate、paper readiness、通知和远程任务组成的 AI 策略工作流。当前问题在于这些能力暴露得过于底层: 用户需要先让 Agent 理解仓库，再手动组织 Prompt、命令、报告和下一步动作。

下一阶段应把 Dashboard 重构为 **Strategy Console + Live Ops**:

- `StrategySpec` 继续作为策略行为的真相来源。
- 新增 `StrategyProject` 作为用户视角的持久策略对象。
- Dashboard 成为用户主入口，负责策略管理、策略生成、优化迭代、paper/live 监控、通知和安全确认。
- Product Service 负责状态机、任务编排、上下文编译、迭代控制和确定性 paper gate。
- Codex / Claude Code / Claude API 只作为 Worker Runtime，负责生成、修改、验证和产出结构化证据。
- 模拟盘数据直接在 Dashboard 展示；实盘相关信息仅做只读通知和事件展示，不提供真钱写入。

不应另起一个独立 UI。应保留现有 Dashboard 的视觉风格、登录、远程代理、command plan/run、通知和 catalog 基础，把其信息架构从 catalog 面板升级为 Strategy Console。

## 1. 核心问题

### 1.1 用户问题

当前用户在使用 Open Composer 时遇到的主要障碍不是底层策略能力不足，而是交互不稳定、不直观:

1. 每次新会话都要提示 Agent 阅读项目结构，用户需要承担上下文初始化成本。
2. 用户不知道应该输入什么 Prompt，也不知道当前策略处于哪个阶段。
3. 策略生成、优化、回测、证据、阻塞项、paper readiness 和通知分散在文件、CLI 和 Dashboard 的多个区域。
4. Dashboard 更像 `StrategySpec` 和报告的 catalog，不像一个可以直接推进策略生命周期的产品工作台。
5. 用户需要到第三方 broker 网站查看模拟盘状态，Open Composer 没有形成完整的实时操作视图。
6. 实盘相关事件只能依赖外部通知或第三方界面，缺少统一的只读通知流。

### 1.2 产品问题

Open Composer 已经有强 Harness，但缺少产品层对象。现在系统中已有 `StrategySpec`、research kernel、paper readiness、notification、dashboard command、remote jobs 等模块，但缺少把它们组织起来的持久状态:

- 缺少用户视角的策略项目对象。
- 缺少结构化的用户意图和交互计划。
- 缺少可配置的迭代停止标准。
- 缺少每轮优化的统一摘要。
- 缺少 Dashboard 级状态机和按钮权限模型。
- 缺少 paper/live 统一监控视图。

### 1.3 设计目标

本方案要解决的问题是:

```text
用户自然语言目标
  -> 产品层理解和确认
  -> 生成 StrategyProject
  -> 生成或更新 StrategySpec
  -> 自动运行受控研究和优化
  -> 展示证据、阻塞项和下一步动作
  -> 在 paper_ready_pass 后由用户二次确认进入模拟盘
  -> 在 Dashboard 内持续监控 paper/live 事件
```

用户不应再直接管理 Prompt、仓库上下文、内部命令和报告路径。产品负责把这些内部细节转换为清晰的状态、按钮和决策卡。

## 2. 产品设计

### 2.1 交互原则

1. **Dashboard 是用户主入口，不是第二真相源。**
   Dashboard 展示、提交计划和触发受控动作；真实状态仍写入 `projects/`、`strategy_specs/`、`reports/`、signals、orders、audit logs。

2. **StrategyProject 是用户视角的稳定对象。**
   用户管理的是 Project，不是一次性 Prompt。每个 Project 有状态、当前 spec 引用、迭代历史、证据、阻塞项和操作按钮。

3. **StrategySpec 是策略行为真相来源。**
   任何交易逻辑、参数、执行模式和数据依赖必须能回链到 `StrategySpec` 或关联 artifact。

4. **界面展示证据等级，不展示赚钱承诺。**
   UI 禁止使用“好策略”“能赚钱”“确定可用”等表述，只展示 evidence level、gate、blocker、warning 和 next action。

5. **LLM 做研究，Product Runner 做执行。**
   LLM 可以生成、优化和解释策略，但不能提交订单、绕过 gate 或切换到 `Active Paper`。

6. **所有高风险动作都有确定性 gate 和用户确认。**
   `Active Paper` 必须满足 `paper_ready_pass=true`，并要求用户二次确认。真钱 broker write 永远不在 MVP 范围内。

### 2.2 用户主导航

新的 Dashboard 主导航建议为:

| 页面 | 作用 | 取代或复用 |
|---|---|---|
| Overview | 全局健康、待处理事项、最新 paper/live 事件 | 改造现有 Monitor |
| Projects | 策略项目列表和筛选 | 改造现有 Strategies / Library |
| Build | 新策略生成入口 | 新增 |
| Iterate | 正在优化的策略和轮次控制 | 新增或并入 Projects |
| Live | 模拟盘、实盘通知、运行状态 | 强化现有 Monitor / Activity |
| Activity | 通知、审计、命令、worker 事件 | 改造现有 Activity |
| Settings | 数据源、broker、通知、远程模式、模型路由 | 新增或扩展 |

默认首屏应是 Overview 或 Projects，而不是文档说明页。用户进入后第一眼应看到:

- 有哪些策略项目。
- 哪些在生成或迭代。
- 哪些被阻塞。
- 哪些已进入 paper monitoring。
- 哪些事件需要用户确认。

### 2.3 StrategyProject 列表

Projects 页面是产品核心。列表字段建议:

| 字段 | 含义 |
|---|---|
| Project | 用户命名的策略项目 |
| State | `Idea / Draft / Validated / Researching / Iterating / Candidate / Paper-Ready Review / Active Paper / Monitoring / Retired / Blocked` |
| Thesis | 一句话策略假设 |
| Current Spec | 当前 `StrategySpec` 路径和 hash |
| Evidence | `ok / warning / blocked / unknown` |
| Gate | 四类 pass 摘要 |
| Latest Run | 最近一轮 run 和停止原因 |
| Live | paper/live 状态 |
| Next Action | 推荐动作 |

列表默认不按 Sharpe 排序。默认排序应为:

1. 需要用户确认的项目。
2. 运行中或失败的项目。
3. paper/live 有 warning 或 red alert 的项目。
4. 最近更新的项目。
5. archived/retired 项目。

### 2.4 策略详情页

每个 Project 详情页固定布局:

```text
Header
  名称 / 状态 / 更新时间 / 当前 spec / 当前 worker 状态

Summary
  Thesis
  Spec 摘要
  当前证据等级
  当前 blocker
  推荐下一步

Evidence
  Backtest
  Benchmark family
  OOS / walk-forward
  Cost sensitivity
  Execution reality
  Data capability
  LLM / alt-data contribution

Gates
  workflow_pass
  research_pass
  llm_contribution_pass
  paper_ready_pass

Iteration
  Round history
  当前 IterationPolicy
  下一轮计划
  停止原因

Live
  Paper account
  Positions
  Orders
  Signals
  Alerts
  Live notifications

Audit
  Agent requests
  Dashboard command plans
  User confirmations
  Worker logs
  Artifact links
```

详情页按钮由状态机决定，不允许全部按钮常驻。

### 2.5 状态机

状态定义:

```text
Idea
  用户输入想法，尚未生成 spec。

Draft
  已生成 StrategySpec draft，但未完成验证。

Validated
  spec validation 和 capability 初查完成。

Researching
  正在生成研究证据或首次回测。

Iterating
  正在按 IterationPolicy 优化。

Candidate
  研究阶段暂时可保留，但尚未 paper-ready。

Paper-Ready Review
  用户申请进入模拟盘前审查，运行 paper readiness 和 safety review。

Active Paper
  已通过 paper_ready_pass 且用户二次确认，允许确定性 paper runner 工作。

Monitoring
  paper 或只读 live 观察中，不一定有 active order flow。

Retired
  停用或归档，不参与运行。

Blocked
  worker、数据、gate 或状态迁移失败，需要用户处理。
```

核心转移:

```text
Idea -> Draft -> Validated -> Researching -> Iterating -> Candidate
                                                      |
                                                      v
Retired <- Monitoring <- Active Paper <- Paper-Ready Review
```

`Blocked` 是异常状态，可以从任一非终态进入。恢复时必须记录原因和恢复动作。

### 2.6 按钮权限

| 状态 | 主要按钮 |
|---|---|
| Idea | 完善需求、生成计划、开始生成、取消 |
| Draft | 验证 spec、调整需求、归档 |
| Validated | 开始研究、修改 spec、归档 |
| Researching | 查看进度、停止本轮、等待完成 |
| Iterating | 查看进度、停止迭代、调整方向 |
| Candidate | 继续优化、申请 Paper Review、停止保留、归档 |
| Paper-Ready Review | 运行 readiness、查看阻塞项、二次确认进入 paper |
| Active Paper | 查看订单、同步账户、暂停、启用 kill switch |
| Monitoring | 查看 live 状态、继续观察、退役 |
| Retired | 恢复为 Draft、归档查看 |
| Blocked | 查看错误、重试、复制诊断、归档 |

所有 red action 必须走 command plan/run、确认短语、audit log 和必要备份。

### 2.7 新策略生成流程

用户流程:

1. 用户进入 Build。
2. 输入自然语言策略需求。
3. 系统生成 `InteractionPlan` 草案。
4. UI 展示理解结果:
   - 标的 / universe
   - 时间周期
   - 策略风格
   - 风险偏好
   - 是否未来考虑 paper
   - 默认数据源
   - 默认迭代轮数
   - 已识别的不确定问题
5. 用户确认或补充。
6. 系统创建 `StrategyProject`。
7. Worker 生成 `StrategySpec draft`、验证、报告和第一轮 `RunSummary`。
8. Dashboard 刷新项目状态和下一步建议。

用户看到的是“计划确认 -> 运行进度 -> 结果摘要”，不是原始 Prompt。

### 2.8 优化迭代流程

用户流程:

1. 用户打开 Project。
2. 查看当前 thesis、spec、证据、gate、阻塞项和上一轮摘要。
3. 点击继续优化。
4. 系统根据 `IterationPolicy` 和最新 `RunSummary` 生成下一轮计划。
5. 用户可补充一句改进方向，例如“减少参数，不要扩大 universe”。
6. Worker 执行一轮优化。
7. 系统写入新的 `RunSummary`。
8. 达到停止条件时自动停止，并显示停止原因。

停止原因必须是结构化值:

- `target_met`
- `budget_exhausted`
- `no_material_improvement`
- `overfit_risk_high`
- `paper_ready_blocked_by_data_or_execution`
- `worker_failed`
- `user_stopped`

### 2.9 Live Ops 设计

Live 页面分为两部分: Paper Monitor 和 Live Notifications。

#### Paper Monitor

Paper Monitor 直接展示模拟盘状态，不要求用户跳转第三方网站:

- broker connection status
- account equity / cash / buying power / portfolio value
- active paper_auto strategies
- open orders
- filled orders
- positions
- unrealized P/L
- last signal
- last order
- reconciliation status
- alerts
- kill switch status

数据来源优先为本地 artifacts:

```text
reports/paper/status.json
reports/paper/account.json
reports/paper/positions.json
reports/paper/orders.jsonl
reports/paper/reconciliation.json
reports/paper/alerts.json
```

同步 broker 数据必须是受控动作，不能由前端直接写 broker。

#### Live Notifications

### 2.10 现状对比和改造方向

| 当前模块 | 当前定位 | 问题 | 改造后定位 |
|---|---|---|---|
| `Monitor / Overview` | paper 和系统概览 | 缺少项目级待处理事项 | 全局运行健康、用户待确认事项、paper/live 告警 |
| `Strategies / Library` | `StrategySpec` catalog | 以 spec 为中心，缺少用户项目对象 | `StrategyProject` 列表，legacy spec 作为 fallback |
| `StrategyDetail` | spec、backtest、signal、version、audit | 信息多但缺少状态机和下一步动作 | Project 详情页，固定展示 thesis、evidence、gate、iteration、live |
| `Research` | research runs 和 decision cards | 与策略项目和用户操作脱节 | Evidence 工作台，服务于 Project 的晋升和迭代决策 |
| `Activity` | signals、orders、reviews、audit | paper/live/worker/notification 混杂 | 统一事件流，支持过滤、acknowledge 和来源回链 |
| `Dashboard command` | 本地/远程受控命令 | 以底层 action 为中心 | 作为 Product Service mutation 的安全执行层 |
| `notifications` | Telegram/log 通知 | 事件类型不够覆盖 live ops | 产品层事件 inbox，Telegram/email 只订阅筛选后的事件 |
| `paper_controls` | paper 状态和 kill switch | UI 展示不够完整 | Live Ops 的 paper read model 和安全控制源 |

改造原则是渐进替换: 先让 Dashboard catalog 能读取 Project，再把旧 strategy catalog 收进 Project detail 的 Spec/Advanced tab，避免一次性破坏现有可用界面。

实盘相关内容在 MVP 中只做只读通知:

- broker alert
- order fill alert
- account warning
- strategy signal
- data source error
- paper/live divergence
- kill switch event
- system alert

通知统一进入:

```text
reports/notifications/log.jsonl
```

Telegram / email 只订阅产品层事件，不订阅 worker 内部日志。实盘通知可以展示在 Dashboard，但不触发实盘下单。

## 3. 终端产品结构设计

### 3.1 文件结构

新增产品层目录:

```text
projects/
  {project_slug}/
    project.yaml
    iteration-policy.yaml
    memory.md
    interactions/
      20260522T120000Z.yaml
    runs/
      round-001.yaml
      round-002.yaml
```

现有目录继续保留:

```text
strategy_specs/
  drafts/
  approved/
  active/
  retired/

reports/
  research/
  dashboard/
  paper/
  notifications/
  agent_requests/
```

`projects/` 不是替代 `strategy_specs/`，而是组织用户工作流和上下文。

### 3.2 四个核心 schema

#### StrategyProject

作用: 用户视角的策略项目。

关键字段:

```yaml
schema_version: 1
project_id: qqq-daily-trend
name: QQQ Daily Trend
state: Iterating
created_at: 2026-05-22T00:00:00Z
updated_at: 2026-05-22T00:00:00Z
thesis: Follow QQQ daily trend with low turnover and bounded drawdown.
current_spec_path: strategy_specs/drafts/qqq_daily_trend.yaml
current_spec_hash: abc123
iteration_policy_path: projects/qqq-daily-trend/iteration-policy.yaml
latest_run_summary_path: projects/qqq-daily-trend/runs/round-003.yaml
gate_summary:
  workflow_pass: true
  research_pass: false
  llm_contribution_pass: null
  paper_ready_pass: false
blockers:
  - walk_forward_decay
archived: false
```

#### InteractionPlan

作用: 把用户自然语言转成结构化任务。

关键字段:

```yaml
schema_version: 1
interaction_id: interact_20260522T120000Z
project_id: qqq-daily-trend
user_intent: "Build a conservative QQQ daily trend strategy."
task_type: create_strategy
normalized_objective: "Research a low-turnover QQQ daily trend-following strategy."
constraints:
  - manual_signal_until_paper_ready
  - low_turnover
assumptions:
  - use registered data capabilities only
questions:
  - "Should the strategy allow leveraged ETFs?"
confirmed_by_user: true
```

#### IterationPolicy

作用: 控制优化边界和停止条件。

关键字段:

```yaml
schema_version: 1
max_rounds: 5
max_runtime_minutes: 90
min_trade_count: 30
required_benchmarks:
  - same_symbol_buy_hold
  - equal_weight_universe
  - market_proxy
  - sector_proxy
  - cash_proxy
stop_conditions:
  - target_met
  - no_material_improvement_for_2_rounds
  - overfit_risk_high
  - paper_ready_blocked_by_data_or_execution
  - budget_exhausted
targets:
  min_oos_sharpe: 0.8
  max_drawdown_below_benchmark: true
  cost_stress_survives: true
model_routing:
  draft: balanced
  iteration: balanced
  promotion_review: deep_review
  paper_readiness: deep_review
```

#### RunSummary

作用: 每轮 worker 完成后的结构化结果。

关键字段:

```yaml
schema_version: 1
project_id: qqq-daily-trend
round: 3
status: warning
started_at: 2026-05-22T12:00:00Z
completed_at: 2026-05-22T12:40:00Z
worker_provider: codex
task_type: strategy_optimization
spec_before_hash: old123
spec_after_hash: new456
changed_paths:
  - strategy_specs/drafts/qqq_daily_trend.yaml
  - reports/research/qqq_daily_trend-round-003.json
metrics:
  sharpe: 1.1
  oos_sharpe: 0.7
  max_drawdown_pct: 8.4
  trade_count: 42
gate_summary:
  workflow_pass: true
  research_pass: false
  llm_contribution_pass: null
  paper_ready_pass: false
blockers:
  - oos_sharpe_below_target
warnings:
  - walk_forward_decay
stop_reason: null
next_recommended_action: "Reduce parameter count and retest OOS."
artifact_paths:
  report: reports/research/qqq_daily_trend-round-003.md
```

### 3.3 Dashboard read model

Dashboard 不应直接遍历复杂文件并临时推断全部状态。应扩展 catalog 生成器，把以下对象读入统一 read model:

- StrategyProject
- InteractionPlan summary
- IterationPolicy summary
- latest RunSummary
- current StrategySpec summary
- research runs
- paper status
- notification records
- audit events

建议新增或扩展:

```text
open_composer/models/project.py
open_composer/projects.py
open_composer/dashboard/catalog.py
open_composer/models/dashboard.py
```

Dashboard 前端继续读取:

```text
reports/dashboard/catalog.json
```

远程模式下 Vercel 仍只代理 API，不运行 backtest、不写文件、不执行 shell。

## 4. 实现细节

### 4.1 后端实现

#### 新增模块

建议新增:

```text
open_composer/models/project.py
open_composer/projects.py
open_composer/interaction_plans.py
open_composer/iteration_controller.py
open_composer/context_compiler.py
open_composer/live.py
```

职责:

- `models/project.py`: Pydantic schema。
- `projects.py`: CRUD、状态机、路径校验、锁。
- `interaction_plans.py`: 用户输入到结构化计划。
- `iteration_controller.py`: 轮次预算、停止条件、下一轮任务生成。
- `context_compiler.py`: 编译 worker 所需上下文。
- `live.py`: paper/live read model 聚合。

#### CLI

新增 `oc project` 命令作为 UI 和 worker 的底层接口:

```text
uv run oc project create --idea "..."
uv run oc project list
uv run oc project show <project>
uv run oc project plan <project> --message "..."
uv run oc project iterate <project>
uv run oc project stop <project>
uv run oc project archive <project>
uv run oc project live <project>
```

CLI 是备用入口和 worker 接口，不是普通用户的主入口。

#### 状态锁

同一个 Project 同时只允许一个 mutation job:

```text
projects/{project}/.lock
```

读操作不加锁。写操作必须:

1. 获取锁。
2. 读取最新 project。
3. 验证状态迁移。
4. 写 artifact。
5. 写 audit event。
6. 释放锁。

### 4.2 Worker 编排

WorkerProvider 应抽象，不绑定单一模型:

```text
codex
claude_code
claude_api
local
```

Product Service 生成 `AgentTask` 或复用 `reports/agent_requests/`:

```yaml
task_type: strategy_optimization
project_id: qqq-daily-trend
interaction_plan_path: projects/qqq-daily-trend/interactions/...
context_pack_path: projects/qqq-daily-trend/context-pack.json
expected_outputs:
  - run_summary
  - strategy_spec_diff
  - research_report
  - gate_summary
```

Worker 的输出必须结构化。自由文本只能作为说明，不能作为状态迁移依据。

### 4.3 Context Compiler

Context Compiler 解决“每次都要让 Agent 读项目”的问题。

输入:

- `AGENTS.md` 摘要和 hash。
- `CLAUDE.md` 摘要和 hash。
- `harness/risk_domains.yaml` 摘要。
- `harness/artifact_contracts.yaml` 摘要。
- `capabilities/registry.yaml` 摘要。
- 当前 `StrategyProject`。
- 当前 `StrategySpec`。
- 最新 `RunSummary`。
- `memory.md`。
- 当前 `InteractionPlan`。

原则:

- 默认注入摘要和 hash，不无脑注入全文。
- 只有当前任务需要时才附关键原文片段。
- 上下文包必须落盘，便于复现。

### 4.4 Iteration Controller

Iteration Controller 每轮开始前检查:

- 是否超过 `max_rounds`。
- 是否超过 `max_runtime_minutes`。
- 是否有正在运行的 job。
- 是否存在未解决 blocker。
- 是否满足停止条件。
- 是否缺少必需 artifact。

每轮结束后检查:

- 指标是否达到 target。
- 是否连续 N 轮无实质改善。
- 是否出现高过拟合风险。
- 是否因数据或执行阻塞 paper-ready。
- 是否需要停止或建议下一轮。

判断结果写入 `RunSummary.stop_reason` 和 `StrategyProject.blockers`。

### 4.5 Dashboard 前端实现

保留现有设计系统:

- 左侧窄导航。
- 表格优先。
- 8px 左右圆角。
- pill 按钮。
- lucide 图标。
- 绿/青/橙/粉/黑的状态色。
- 低装饰、高密度、工作台风格。

重点改造:

```text
dashboard/src/app/App.tsx
dashboard/src/app/components/sidebar.tsx
dashboard/src/app/components/library.tsx
dashboard/src/app/components/strategy-detail.tsx
dashboard/src/app/components/sections.tsx
dashboard/src/app/components/data.ts
```

建议新增:

```text
dashboard/src/app/components/project-list.tsx
dashboard/src/app/components/project-detail.tsx
dashboard/src/app/components/build-strategy.tsx
dashboard/src/app/components/iteration-panel.tsx
dashboard/src/app/components/live-ops.tsx
dashboard/src/app/components/gate-panel.tsx
dashboard/src/app/components/evidence-panel.tsx
```

现有 `Library` 可逐步替换为 `ProjectList`。旧的 `StrategySpec` catalog 保留为详情页中的 Spec tab 或 Settings/Advanced 区域。

### 4.6 Live 数据实现

#### 模拟盘

现有基础:

- `open_composer/paper_controls.py`
- `open_composer/models/paper.py`
- `open_composer/adapters/broker/alpaca_paper.py`

需要增强:

- Dashboard Live 页面读取 paper status、account、positions、orders、reconciliation、alerts。
- 增加 stale 状态: 如果 account/position 超过阈值未更新，UI 标 warning。
- 支持手动 Sync 按钮，走 command plan/run。
- 支持 kill switch enable/clear，clear 必须 red confirmation。

#### 实盘通知

MVP 只读:

- 不接真钱下单。
- 不让 LLM 自动执行。
- 只接收、记录、展示 live notification。

建议扩展通知 kind:

```text
live_broker_alert
live_order_update
live_account_warning
live_data_error
live_system_alert
paper_live_divergence
```

通知渠道:

- Dashboard activity stream。
- Telegram。
- email 后续加入。
- JSONL log 永远保留。

### 4.7 API 设计

本地 Dashboard server 增加 API:

```text
GET  /api/projects
GET  /api/projects/{id}
POST /api/projects
POST /api/projects/{id}/plan
POST /api/projects/{id}/iterate
POST /api/projects/{id}/stop
POST /api/projects/{id}/archive
GET  /api/live/paper
GET  /api/live/notifications
```

远程模式:

- Vercel 只 proxy。
- mutation API 必须转成 remote job 或 command plan。
- 红色动作要求 double confirmation。

### 4.8 测试与验收策略

后端测试:

- schema 校验: 必填字段、枚举、路径必须 workspace-relative。
- 状态机测试: 合法迁移通过，非法迁移 blocked。
- Project CRUD 测试: create/list/show/archive/import legacy spec。
- IterationPolicy 测试: round budget、runtime budget、stop condition。
- RunSummary 测试: 缺少 gate 或 artifact 时不能推进状态。
- Context Compiler 测试: 输出包含 required hash，且不会泄露无关大文件。
- Live read model 测试: paper snapshot stale、缺 account、reconciliation warning。
- Notification 测试: 产品层事件进入 log，Telegram/email 策略可 dry run。

Dashboard 测试:

- catalog fixture 包含 Project、legacy spec、paper status、notifications。
- Project list 能展示 empty、running、blocked、active paper、retired。
- Project detail 在不同状态下只显示允许按钮。
- Build 页面能生成 plan preview，不直接执行 worker。
- Live 页面能展示 stale warning 和 kill switch 状态。
- Red action 必须出现确认流程。

人工验收:

1. 新用户打开 Dashboard，不读文档也能知道下一步是 Build 还是 Projects。
2. 一个策略从 Idea 到 Candidate 的每步都有状态、artifact 和 audit。
3. 关闭浏览器后重新进入，Project 状态不丢失。
4. Worker 失败后 UI 显示可诊断错误，而不是停留在 loading。
5. `paper_ready_pass=false` 时无法进入 Active Paper。
6. 模拟盘账户、持仓、订单和告警能在 Live 页面看到。
7. 实盘通知只读展示，不出现真钱下单入口。

## 5. 分阶段计划

### P0: 方案固化和 schema

目标: 建立产品层真相来源。

任务:

- 新增 4 个 Pydantic schema。
- 新增 `projects/` 文件读写和路径校验。
- 新增状态机和状态迁移测试。
- 新增 `oc project list/show/create`。
- Dashboard catalog 读取 Project。

验收:

- 无 UI 时也能创建、读取、验证 Project。
- Project 能引用 StrategySpec。
- 状态迁移非法时被阻止。

### P1: Strategy Console MVP

目标: Dashboard 从 catalog 升级为项目工作台。

任务:

- 改造导航和首页。
- 新增 ProjectList。
- 新增 ProjectDetail。
- 显示 thesis、spec summary、gate、latest run、blockers、next action。
- 保留旧 strategy catalog 作为 advanced/spec tab。

验收:

- 用户不看 CLI 也能理解每个策略当前状态。
- 所有显示数字能回链 artifact。
- 没有 Project 的旧策略仍能降级显示。

### P2: Build + InteractionPlan

目标: 用户能从 Dashboard 创建策略。

任务:

- 新增 Build 页面。
- 用户输入自然语言。
- 生成 InteractionPlan 草案。
- 用户确认后创建 Project 和 agent request。
- Worker 完成后写 RunSummary。

验收:

- 用户不需要写 Prompt 模板。
- 每次创建都有可复查 InteractionPlan。
- 失败会进入 Blocked 并显示原因。

### P3: Iteration Controller

目标: 支持受控优化迭代。

任务:

- 实现 IterationPolicy。
- 实现 round budget 和 stop conditions。
- 实现继续优化、停止、调整方向。
- Dashboard 显示轮次历史和停止原因。

验收:

- 不能无限优化。
- 到达停止条件会自动停。
- 停止原因结构化记录。

### P4: Live Ops

目标: Dashboard 内查看模拟盘和实盘通知。

任务:

- 新增 Live 页面。
- 聚合 paper account、positions、orders、alerts。
- 增加 stale 检查。
- 增加 notification stream。
- 扩展 notification kind。

验收:

- 用户无需打开 broker 网站即可查看 paper 状态。
- 实盘通知能在 Dashboard 和 Telegram 中一致展示。
- 实盘仍然只读，不允许真钱写入。

### P5: Paper Review 与安全动作

目标: 从 Candidate 安全进入 Active Paper。

任务:

- Paper-Ready Review 页面。
- 展示 readiness blockers。
- 二次确认激活 paper。
- kill switch 操作和审计。
- paper/live divergence warning。

验收:

- `paper_ready_pass=false` 时无法进入 Active Paper。
- 激活 paper 必须有用户二次确认。
- 所有 red action 有 audit 和确认短语。

## 6. 风险思考与应对

### 6.1 UI 成为第二真相源

风险: Dashboard 如果直接保存状态，会和文件系统、StrategySpec、reports 分叉。

应对:

- Dashboard 只读 catalog 和提交 command plan。
- Project、Spec、RunSummary、paper artifacts 落盘。
- 所有 mutation 走 Product Service 和 audit。

### 6.2 LLM 误导用户

风险: LLM 可能把弱回测描述成强策略。

应对:

- UI 不展示“好策略”。
- 只展示 evidence、gate、blocker、warning。
- promotion 和 paper readiness 由 deterministic gate 决定。

### 6.3 自动优化导致过拟合

风险: 多轮参数搜索会选择偶然最优结果。

应对:

- IterationPolicy 限制轮数和时间。
- 必须记录 trial ledger。
- 必须检查 OOS、walk-forward、benchmark family、cost sensitivity。
- backtest forensics 阻塞高风险结果。

### 6.4 上下文膨胀和污染

风险: 把所有规则全文塞给 worker 会产生噪声和不稳定。

应对:

- Context Compiler 默认注入摘要和 hash。
- 任务需要时才附原文片段。
- 每次上下文包落盘，便于复现。

### 6.5 Worker 失败或输出不合格

风险: Agent 中断、输出缺文件或自由文本无法解析。

应对:

- Worker 必须输出 RunSummary。
- 缺少必需 artifact 时 Project 进入 Blocked。
- UI 显示失败阶段和可重试动作。
- 不用自由文本驱动状态迁移。

### 6.6 并发冲突

风险: 用户同时触发两轮优化，导致 spec 和 report 互相覆盖。

应对:

- Project 级写锁。
- 同一 Project 同时只能有一个 mutation job。
- 新任务排队或要求用户取消旧任务。

### 6.7 模拟盘状态陈旧

风险: 本地 paper artifacts 不是 broker 最新状态。

应对:

- Live 页面显示 snapshot age。
- 超过阈值标 warning。
- 提供受控 Sync。
- reconciliation 报告显示本地和 broker 差异。

### 6.8 实盘通知被误认为执行能力

风险: 用户以为 Dashboard 可以实盘交易。

应对:

- MVP 明确 live 是只读通知。
- UI 文案区分 paper orders 和 live notifications。
- 禁止真钱 broker write。

### 6.9 远程部署安全

风险: Vercel 或远程 UI 直接执行重任务或写文件。

应对:

- Vercel 只 proxy 和展示。
- 长任务走 VPS daemon / local runner。
- 红色动作必须 double confirmation、HMAC、audit 和 backup。

### 6.10 旧策略无 Project

风险: 现有 `StrategySpec` 没有 Project，重构后不可见。

应对:

- Dashboard 支持 legacy spec fallback。
- 提供 `oc project import-strategy <spec>`。
- 导入后创建 Project，但不改变原 spec。

### 6.11 通知噪声

风险: Telegram/email 被 worker 内部日志刷屏。

应对:

- 通知只订阅产品层事件。
- 按 severity 和 kind 配置策略。
- worker debug logs 不进入通知渠道。

### 6.12 Agent 权限边界不清

风险: Worker 越权修改 paper/live 状态。

应对:

- Worker 只产出 artifact。
- Product Service 校验 artifact 后迁移状态。
- paper activation 和 order submission 只能由确定性 runner 触发。

## 7. 下一步优化方向

1. 引入候选比较视图，横向展示参数、方法变体、OOS、benchmark delta、成本后表现和未选择原因。
2. 引入 execution reality 专页，展示 capacity、slippage stress、partial fill 风险和 paper fill calibration。
3. 引入 Data & LLM Evidence 视图，展示 capability、PIT packet、LLM marginal lift 和 missing-modality robustness。
4. 引入 project memory compaction，定期压缩 `memory.md`，避免上下文增长。
5. 引入 read model 增量更新，减少每次 Dashboard 刷新重扫全仓库的成本。
6. 引入 notification inbox 规则，支持 acknowledge、mute、digest 和 escalation。
7. 引入 paper/live divergence 检测，把模拟盘表现、信号和 broker 状态差异显式展示。

## 8. 自我 Review 与修订结论

本方案按以下检查项自审:

| 检查项 | 结论 |
|---|---|
| 是否保持 `StrategySpec` 为策略行为真相 | 通过 |
| 是否避免 Dashboard 成为第二真相源 | 通过，Dashboard 只读 catalog 和提交受控动作 |
| 是否覆盖策略管理、生成策略、优化迭代 | 通过 |
| 是否覆盖模拟盘直看 | 通过，Live Ops / Paper Monitor 明确纳入 |
| 是否覆盖实盘通知 | 通过，但限定为只读通知 |
| 是否区分 LLM 研究和确定性执行 | 通过 |
| 是否包含状态机和按钮权限 | 通过 |
| 是否包含实现路径和代码落点 | 通过 |
| 是否包含风险和应对 | 通过 |
| 是否可被自然人或 Agent 脱离上下文理解 | 通过 |

修订后的关键决定:

1. 不新建独立 UI，重构现有 Dashboard。
2. 不把 Dashboard 定义为唯一真相源，而是用户主入口。
3. 不把 WorkerProvider 绑定到单一模型。
4. 不无脑注入全文上下文，改为摘要 + hash + 必要片段。
5. 不把实盘通知扩展成实盘交易能力。
6. 不把 Sharpe 排名作为默认产品排序，而以用户待处理事项和风险状态优先。

本方案可以作为 P0-P5 的实施依据。下一步应先实现 P0 schema、状态机和 Dashboard catalog 扩展，再进入 Strategy Console UI。
