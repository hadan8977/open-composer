# Open Composer Dashboard 与 Strategy Console 轻量重构方案

日期: 2026-05-22

适用范围: Open Composer 下一阶段产品交互、Dashboard、策略生成、策略迭代、模拟盘查看和实盘只读通知。

## 0. 结论

Open Composer 不需要马上扩张成一个完整的多服务交易平台。当前最重要的问题是: 底层 Harness 和策略研究能力已经存在，但用户仍要直接面对 Prompt、仓库结构、CLI、报告路径和 Agent 上下文。

下一阶段应把现有 Dashboard 轻量升级为 **Strategy Console**:

- Dashboard 是用户主入口。
- `StrategySpec` 仍是策略行为真相来源。
- 新增一个轻量 `StrategyProject`，把用户看到的策略、当前 spec、状态、最近运行、阻塞项和下一步动作组织起来。
- 策略生成和优化仍通过现有 `reports/agent_requests/`、CLI、Harness、reports 和 worker 完成，不新建重型执行平台。
- 模拟盘状态直接在 Dashboard 查看。
- 实盘相关内容只作为只读通知流展示，不做真钱下单。
- Worker 输出必须被确定性校验，不能只信 Agent 自报。

本方案的原则是: **先做一个能用、清晰、可审计的轻量闭环，再按真实使用痛点逐步硬化。**

## 1. 核心问题

### 1.1 用户的核心诉求

用户需要的是一个可持续使用的 AI 策略工作台:

1. 打开 Dashboard 就知道有哪些策略、当前状态、下一步该做什么。
2. 能用自然语言或模板生成策略，而不是每次先教 Agent 读仓库。
3. 能让策略继续优化，系统按默认规则跑到停止条件，再通知用户。
4. 能直接查看模拟盘账户、订单、持仓和运行状态。
5. 能看到实盘相关通知，但不让产品具备真钱写入能力。
6. 能保持策略研究的严谨性，避免把弱回测、样本数据或 Agent 自报当成可交易证据。

### 1.2 当前产品问题

现有系统已经有不少能力:

- `StrategySpec`
- Harness 和 risk domains
- research reports
- paper readiness
- Dashboard catalog
- dashboard command plan/run
- paper controls
- notifications
- remote job 基础

但这些能力缺少一个用户视角的组织层。结果是:

- 策略只是分散在 `strategy_specs/` 和 `reports/` 中的文件。
- Dashboard 更像 catalog，不像工作台。
- 生成、优化、审查、paper 监控之间缺少统一流程。
- 用户需要自己组织 Prompt 和下一步动作。
- Worker 产出缺少产品层对账。

### 1.3 本轮重构的边界

本轮不做:

- 不做完整多租户或团队 SaaS。
- 不做真钱 broker write。
- 不做复杂模型路由。
- 不做独立大型 Product Service。
- 不重写现有 Harness、paper runner 或 Dashboard 技术栈。

本轮要做:

- 轻量 Project 层。
- Dashboard Strategy Console。
- Build / Iterate 基础交互。
- Worker 输出对账。
- Paper Monitor 和通知流。
- 最小必要的状态机和停止条件。

## 2. 产品设计

### 2.1 产品层对象

只新增一个核心对象: `StrategyProject`。

`StrategyProject` 是用户视角的策略项目。它不替代 `StrategySpec`，只负责把用户关心的信息组织起来:

- 这个策略叫什么。
- 当前处于什么状态。
- 当前引用哪个 `StrategySpec`。
- 最近一轮做了什么。
- gate 和 blocker 是什么。
- 下一步建议是什么。
- 是否进入 paper/live 观察。

为避免产品过重，`InteractionPlan`、`IterationPolicy`、`RunSummary` 不需要在 P0 独立成三个复杂 schema。它们先作为 `StrategyProject` 下的轻量嵌套字段或小文件存在，后续复杂度真的上来后再拆分。

建议目录:

```text
projects/
  {project_slug}/
    project.yaml
    memory.md
    runs/
      round-001.yaml
      round-002.yaml
```

最小 `project.yaml`:

```yaml
schema_version: 1
project_id: qqq-daily-trend
name: QQQ Daily Trend
state: iterating
thesis: Follow QQQ daily trend with low turnover and bounded drawdown.
current_spec_path: strategy_specs/drafts/qqq_daily_trend.yaml
latest_run_path: projects/qqq-daily-trend/runs/round-002.yaml
gate_summary:
  workflow_pass: true
  research_pass: false
  llm_contribution_pass: null
  paper_ready_pass: false
blockers:
  - walk_forward_decay
next_action: continue_iteration
iteration:
  max_rounds: 5
  current_round: 2
  mode: auto_continue_until_stop
  stop_reason: null
paper:
  status: not_requested
archived: false
```

最小 `runs/round-xxx.yaml`:

```yaml
schema_version: 1
round: 2
status: warning
task_type: strategy_optimization
worker_provider: codex
changed_paths:
  - strategy_specs/drafts/qqq_daily_trend.yaml
  - reports/research/qqq_daily_trend-round-002.md
worker_claim:
  gate_summary:
    workflow_pass: true
    research_pass: true
    paper_ready_pass: false
verified:
  gate_summary:
    workflow_pass: true
    research_pass: false
    paper_ready_pass: false
  artifact_check: warning
  mismatch: true
metrics:
  sharpe: 1.1
  oos_sharpe: 0.7
  trade_count: 42
blockers:
  - worker_self_report_mismatch
  - oos_sharpe_below_target
next_action: reduce_parameter_count_and_retest
```

### 2.2 状态机

保持状态机简单:

```text
idea -> draft -> researching -> iterating -> candidate -> paper_review -> active_paper
                                                |
                                                v
                                             retired
```

任何状态都可以进入:

```text
blocked
```

状态含义:

| 状态 | 含义 |
|---|---|
| `idea` | 用户输入想法，尚未生成 spec |
| `draft` | 已有 draft spec，尚未形成证据 |
| `researching` | 正在生成首次研究证据 |
| `iterating` | 正在优化 |
| `candidate` | 暂时值得保留，但未 paper-ready |
| `paper_review` | 正在做 paper readiness |
| `active_paper` | 已通过 gate 并经用户确认 |
| `retired` | 已停用 |
| `blocked` | 需要用户处理 |

先不要引入 `Validated`、`Monitoring` 等额外状态。验证和监控可以作为字段展示，而不是一开始就变成状态。

### 2.3 Dashboard 信息架构

保留现有 Dashboard 风格，重排信息架构:

| 页面 | P0/P1 定位 |
|---|---|
| Overview | 待处理项目、paper 状态、最新通知 |
| Projects | 策略项目列表，替代当前以 spec 为中心的 Library |
| Build | 新建策略，支持模板和自然语言 |
| Live | 模拟盘状态和实盘只读通知 |
| Activity | 命令、通知、审计、worker 事件 |
| Settings | broker、通知、远程连接、默认 worker |

可以不单独做 `Iterate` 页面。迭代入口放在 Project detail 中，避免导航过多。

### 2.4 Project 列表

Projects 页面字段:

| 字段 | 含义 |
|---|---|
| Project | 策略项目名称 |
| State | 当前状态 |
| Thesis | 策略假设 |
| Spec | 当前 spec |
| Gates | 四类 pass 摘要 |
| Latest Run | 最近轮次 |
| Blocker | 当前最重要阻塞 |
| Next Action | 推荐动作 |

默认排序:

1. blocked / 需要用户确认。
2. active paper 有告警。
3. running / iterating。
4. candidate。
5. draft / retired。

不要默认按 Sharpe 排序，避免用户被单一指标误导。

### 2.5 Project 详情页

详情页只做 5 个区域:

```text
Summary
  thesis / current spec / state / next action

Evidence
  latest metrics / benchmark / OOS / blocker / source artifact

Iteration
  current round / max rounds / stop reason / continue or stop

Live
  paper status / signals / orders / notifications

Audit
  command plans / agent requests / changed paths
```

不要一开始拆太多 tab。复杂 evidence view、factor lab、execution reality 专页可以后续再做。

### 2.6 Build 交互

Build 页面支持两种入口:

1. Starter templates。
2. 自然语言输入。

Starter templates 先保留 3 个，避免产品显得过重:

| 模板 | 默认方向 |
|---|---|
| QQQ 趋势 / 动量 | QQQ 单标的趋势或动量策略 |
| 行业 / 主题轮动 | ETF 或股票池轮动 |
| 股债 / 风险切换 | SPY/QQQ/TLT 等风险配置 |

创建流程:

```text
输入或选模板
  -> 确定性规则判断是否足够明确
  -> 明确则直接创建 Project
  -> 模糊则最多追问 1-2 个问题
  -> 创建 agent request
  -> worker 生成 spec 和首轮报告
  -> Dashboard 展示结果
```

不强制每次展示完整 `InteractionPlan` 让用户确认。计划作为审计记录保存即可。

### 2.7 Iterate 交互

默认支持异步运行:

```yaml
iteration:
  max_rounds: 5
  mode: auto_continue_until_stop
  stop_conditions:
    - target_met
    - max_rounds_reached
    - no_material_improvement
    - overfit_risk_high
    - data_or_execution_blocked
    - worker_failed
```

用户可以:

- 继续优化。
- 输入一句调整方向。
- 停止并保留当前版本。
- 归档。
- 申请 paper review。

每轮结束后通知用户，但默认不要求用户守在页面前逐轮确认。用户可以随时手动停止。

### 2.8 Live 交互

Live 页面 P0/P1 只做两件事:

1. Paper Monitor。
2. Live Notifications。

Paper Monitor 展示:

- paper account snapshot。
- active paper strategies。
- open / filled orders。
- positions。
- kill switch。
- reconciliation / alerts。
- stale warning。

Live Notifications 展示:

- paper event。
- broker alert。
- live account warning。
- signal。
- data error。
- system alert。

实盘通知只读展示，不提供真钱下单入口。

## 3. 实现方案

### 3.1 最小代码改动面

优先改这些文件:

```text
open_composer/models/project.py       # 新增轻量 Pydantic model
open_composer/projects.py             # 新增 Project 读写和状态更新
open_composer/agent_requests.py       # 复用现有 agent request，不重造 job 系统
open_composer/dashboard/catalog.py    # 读取 projects/ 和 paper/live 摘要
open_composer/models/dashboard.py     # 增加 DashboardProject / summary 字段
dashboard/src/app/App.tsx             # 导航重排
dashboard/src/app/components/library.tsx 或 project-list.tsx
dashboard/src/app/components/strategy-detail.tsx 或 project-detail.tsx
dashboard/src/app/components/sections.tsx
```

暂不新增独立 FastAPI Product Service。现有 Dashboard server、Vercel proxy、remote jobs 和 command plan/run 先继续复用。

### 3.2 Project 读写

`projects.py` 先提供最小函数:

```text
create_project(...)
list_projects(...)
load_project(...)
write_project(...)
append_project_run(...)
update_project_state(...)
import_legacy_strategy(...)
```

路径规则:

- 所有路径必须 workspace-relative。
- Project 只能引用 workspace 内的 spec 和 reports。
- legacy `StrategySpec` 没有 Project 时，Dashboard 仍降级展示。

### 3.3 Worker 与对账

Worker 仍通过现有 `reports/agent_requests/` 或 CLI 触发。

Worker 完成后，Product 层必须做轻量对账:

1. `changed_paths` 是否存在。
2. spec 是否能加载。
3. validation / harness report 是否存在。
4. gate summary 是否来自确定性报告。
5. Worker 自报和 verified 结果不一致时，把 Project 标为 `blocked`。

不需要第一版就实现完整 `oc_harness_verify()` 新框架。如果现有报告中已有 gate，就读取现有报告；没有 gate 时显示 `unknown` 或 `blocked`，不能误显示 ready。

### 3.4 迭代控制

P0/P1 不做复杂后台调度器。先实现:

- `max_rounds`
- `current_round`
- `mode`
- `stop_conditions`
- `stop_reason`
- `user_requested_stop`

取消机制先轻量化:

- 用户点停止时，在 `project.yaml` 写 `user_requested_stop: true`。
- Worker 或下一轮启动前检查该字段。
- 不做独立 heartbeat watcher，除非实际出现 orphan job 问题。

成本预算先轻量化:

- 文档中保留 `cost_estimate_usd` 可选字段。
- 不在 P0/P1 强制接入 token 统计。
- 等真实 API 成本成为问题时再加入硬预算。

Memory 压缩先轻量化:

- `memory.md` 只保存最近结论和关键 blocker。
- 超过建议长度时标 warning。
- 不在 P0/P1 引入自动语义压缩。

### 3.5 Context Pack

不要把 Context Compiler 做成复杂系统。先生成一个简单 Markdown context:

```text
projects/{project}/context.md
```

包含:

- AGENTS/CLAUDE 规则摘要和 hash。
- 当前 project。
- 当前 spec 路径。
- 最新 run 摘要。
- 本轮任务。

这样已经能解决“每次要让 Agent 重新读项目”的问题。

### 3.6 Dashboard UI

保留现有视觉风格:

- 左侧导航。
- 表格优先。
- 高信息密度。
- pill 按钮。
- 8px 左右圆角。
- lucide 图标。
- 不做营销 hero。

UI 首轮只需要完成:

- Overview 显示待处理事项。
- Projects 列表。
- Project 详情。
- Build 入口。
- Live paper/notification 摘要。

复杂图表、candidate compare、factor lab、execution reality 专页全部后移。

## 4. 分阶段计划

### P0: 备份与轻量 Project 层

目标: 不破坏现有工作流，建立用户视角对象。

任务:

- 完成项目备份。
- 新增 `StrategyProject` model。
- 新增 `projects.py` 读写。
- Dashboard catalog 读取 Project。
- legacy spec fallback。

验收:

- 没有 Project 的旧策略仍能显示。
- 有 Project 的策略能展示状态、spec、blocker、next action。
- 不影响现有 tests 和 Dashboard catalog。

### P1: Strategy Console UI

目标: Dashboard 变成用户能直接使用的工作台。

任务:

- 导航重排为 Overview / Projects / Build / Live / Activity / Settings。
- Projects 列表替代旧 Library 的主入口。
- Project detail 展示 Summary / Evidence / Iteration / Live / Audit。
- 旧 StrategySpec catalog 放到 advanced 或 fallback。

验收:

- 用户打开 Dashboard 能知道每个策略下一步。
- 状态和数据都能回链本地 artifact。
- 页面不过度复杂。

### P2: Build + Agent Request

目标: 用户能从 Dashboard 创建策略。

任务:

- Build 页面支持 3 个模板和自然语言输入。
- 确定性 fast/clarify 判断。
- 创建 Project。
- 创建 `reports/agent_requests/`。
- Worker 完成后写 Project run 摘要。

验收:

- 明确输入不需要强制确认。
- 模糊输入最多追问 1-2 个问题。
- 创建结果可审计。

### P3: Iterate MVP

目标: 支持低摩擦、受控的策略优化。

任务:

- 支持 continue / stop / archive / request paper review。
- 支持 `max_rounds` 和基本 stop conditions。
- 支持 `user_requested_stop`。
- 支持 Worker 输出轻量对账。
- 支持 round complete / blocked 通知。

验收:

- 用户不需要守着页面逐轮操作。
- Worker 漏产物或自报不一致时不会误晋升。
- 不引入复杂调度器也能跑通 1-5 轮优化。

### P4: Live MVP

目标: 不跳转第三方网站也能看模拟盘状态。

任务:

- Live 页面读取 paper status、account、positions、orders、alerts。
- 显示 stale warning。
- 显示 notification log。
- 保持实盘只读。

验收:

- 用户能在 Dashboard 看 paper 状态。
- 实盘通知不产生真钱操作入口。

### P5: 可靠性硬化

只有当 P0-P4 真实使用后暴露出问题，再实现:

- lock TTL / heartbeat。
- orphan job watcher。
- 硬成本预算。
- 自动 memory compaction。
- 更细的 context compiler。
- prompt caching。
- candidate compare。
- execution reality 专页。
- factor / LLM evidence 专页。

## 5. 风险与应对

### 5.1 产品过重

风险: 一次性引入太多 schema、API、服务和状态机会拖慢开发，并让 Dashboard 更难用。

应对:

- P0 只新增 `StrategyProject`。
- 其他对象先做嵌套字段或小文件。
- Product Service 先不独立成新服务。
- 复杂能力放到 P5 hardening。

### 5.2 Dashboard 成为第二真相源

风险: UI 保存策略语义，和 `StrategySpec` 分叉。

应对:

- `StrategySpec` 仍是策略行为真相。
- Dashboard 只展示和触发受控动作。
- Project 只保存用户视角状态和 artifact 引用。

### 5.3 Agent 自报不可靠

风险: Worker 说通过了，但实际漏跑验证或 artifact 不存在。

应对:

- 轻量对账必须进入 P3。
- 缺 artifact 或 gate 来源不确定时，状态显示 `blocked` 或 `unknown`。
- 不把 Worker 自报直接写成 paper-ready。

### 5.4 自动迭代过拟合

风险: 多轮优化追逐回测指标。

应对:

- 默认 `max_rounds=5`。
- 默认 stop condition 包含 no material improvement 和 overfit risk。
- `research_pass` 和 `paper_ready_pass` 继续由 Harness / readiness 决定。

### 5.5 用户仍不知道怎么开始

风险: 自然语言输入框仍让新用户困惑。

应对:

- Build 首屏提供 3 个模板。
- 输入足够明确时直接跑。
- 模糊时只追问 1-2 个问题。

### 5.6 慢任务体验差

风险: 用户不能一直看着每轮研究。

应对:

- 默认异步自动跑到停止条件。
- 通过 Dashboard / Telegram 通知完成或阻塞。
- 用户可随时 stop。

### 5.7 Paper / live 边界混淆

风险: 用户误以为 live 通知等于实盘交易能力。

应对:

- Live Notifications 明确只读。
- 只有 paper runner 可以在 gate 和确认后提交 paper order。
- MVP 不提供真钱 broker write。

### 5.8 现有未提交改动和迁移风险

风险: 当前工作区已有策略清理改动，重构时容易混入不相关变更。

应对:

- 已创建项目级备份。
- 每次提交只提交当前任务相关文件。
- P0 开始前先确认是否要提交或暂存现有策略清理改动。

## 6. 当前备份

本次轻量化审核前已创建本地备份:

```text
backup_dir: /root/codex-test/open-composer-backups/open-composer-20260522T092216Z
archive: /root/codex-test/open-composer-backups/open-composer-20260522T092216Z/open-composer-20260522T092216Z.tar.gz
sha256: beae44c388917e526496d327e233de5f94970df81acb9e4566880919bd79d19b
head: 01fbead6cc3287f37f6798717ed775c72dbb34a7
dirty_count: 42
```

备份包含当前 working tree、`.git`、dirty status 和 diff patch；排除了可再生成的虚拟环境、node_modules 和缓存目录。

## 7. 轻量化 Review 结论

原 v2 方案方向正确，但实现面偏重。主要过重处:

- 四个顶层 schema 同时落地。
- 独立 Product Service 概念过早。
- 完整锁 TTL / heartbeat / watcher 过早。
- 硬成本预算和 token tracking 过早。
- 自动语义 memory compaction 过早。
- 过多 Dashboard tab 和后续 evidence 专页。

轻量化后的优先级:

1. 先让 Dashboard 管理 StrategyProject。
2. 再让用户能从 Dashboard 创建策略。
3. 再让用户能异步迭代，并看到 verified blocker。
4. 再接入 paper/live 查看。
5. 最后按真实使用痛点做可靠性硬化。

这样既满足核心要求，又避免产品在第一轮重构中变得过重。

## 8. 核心要求覆盖表

| 核心要求 | 轻量方案如何满足 |
|---|---|
| 策略管理 | `StrategyProject` + Projects 页面，统一展示状态、spec、blocker、next action |
| 生成策略 | Build 页面，3 个模板 + 自然语言输入 + agent request |
| 优化迭代 | Project detail 中的 Iterate 区域，支持 continue / stop / archive / paper review |
| 用户不用重复解释项目结构 | `projects/{project}/context.md` 为 worker 提供最小上下文 |
| 模拟盘直看 | Live 页面读取 paper artifacts 和状态 |
| 实盘通知 | Live Notifications 只读展示 notification log |
| 不做真钱交易 | MVP 明确禁止真钱 broker write |
| 保持研究严谨 | `StrategySpec` 仍是真相；gate 由 Harness/readiness 决定；Worker 产物要对账 |
| 避免过重 | 只新增一个核心 schema，其他能力嵌入或后移 |
| 保持效率 | 复用现有 Dashboard、agent_requests、reports、paper_controls、notifications |

## 9. 开工前检查

进入 P0 前先做三件事:

1. 确认当前策略清理相关未提交改动是否要提交、暂存或继续保留。
2. 确认本备份可用，必要时再做一次更新备份。
3. 从 `StrategyProject` 和 Dashboard catalog 扩展开始，不先做独立服务或复杂调度器。
