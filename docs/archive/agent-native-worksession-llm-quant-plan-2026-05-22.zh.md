# Open Composer Agent 原生策略会话与 LLM+量化计划

日期：2026-05-22

## 1. 核心问题

Open Composer 的核心要求不是“让产品替代 Codex / Claude Code 规划每一步”，而是让产品提供一个可靠、安全、可恢复的策略工作台，充分释放 Codex / Claude Code 的长上下文、读写代码、运行工具、自我修复和持续研究能力。

当前结构已经有 `StrategyProject`、artifact state、run ledger、feature packet、promotion gate 和 Dashboard 证据面板，但仍存在两个关键偏差：

1. **策略没有被产品化为长期 AI 工作会话。**  
   当前 Dashboard 的“继续优化”会生成新的 `reports/agent_requests/*.json`。这保证任务可恢复，但没有保证一个策略持续绑定同一个 Codex / Claude Code session，也没有把 session queue、trace、checkpoint 和上下文包作为产品对象。

2. **LLM+量化策略有安全边界，但缺少完整生成和优化闭环。**  
   当前系统能识别 `llm_feature`、`feature_packet`、news/event/macro capability，并要求 PIT packet、marginal lift 和 missing-modality evidence。但产品更像是在“检查 LLM 因子是否合规”，还没有顺滑支持“设计 LLM 因子、优化 prompt、物化历史特征、回测 replay、验证边际贡献、持续迭代”。

## 2. 严格 Review 结论

### 2.1 Gemini 报告中成立的部分

- `1KB memory` 不能作为主上下文。它只能是 control hint，不足以发挥 256k / 1M 上下文 agent 的优势。
- 静态 iteration step 如果变成强制流程，会削弱 Codex / Claude Code 自主规划、自我修复和临场调整能力。
- 当前 `agent_request` 更像一次性工单，不像长期 strategy work session。
- LLM 因子如果只能读取旧 JSONL，而没有 prompt trial / feature materialization / replay 的闭环，就无法真正优化 LLM 因子本身。
- 纯 YAML expression 对复杂策略表达力有限，应允许更强的 Python strategy module / SDK 扩展。

### 2.2 Gemini 报告中过度或需要修正的部分

- **不能废除 deterministic gates。**  
  promotion、paper readiness、paper_auto、真实 broker 写入边界必须由确定性 gate 控制。AI 可以提出豁免理由，但不能绕过 gate 自动晋级。

- **不能让 live LLM call 直接进入 backtest loop。**  
  直接在回测循环里调用 LLM 会导致不可复现、成本不可控、延迟不稳定和未来泄漏风险。正确做法是：agent 可以在研究阶段运行 LLM feature materialization，把历史输入按 prompt/model/input hash 生成 PIT feature packets；backtest 只做确定性 replay。

- **不能把 StrategySpec 直接替换成任意 Python。**  
  Codex / Claude Code 擅长写 Python，但产品仍需要 StrategySpec 作为审计 manifest：声明 universe、data、execution、risk、capabilities、LLM factor、paper boundary 和 Python module 引用。复杂逻辑可以进 Python strategy module，但必须被 StrategySpec 引用和约束。

- **不能把所有 blocker 都变成软建议。**  
  研究阶段可以允许 warning 和 AI 解释；paper readiness 阶段必须严格。需要区分 exploration blocker、research blocker、paper blocker，而不是简单取消门禁。

## 3. 产品原则

1. **Agent 主导研究，产品守住边界。**  
   Codex / Claude Code 负责计划、代码、实验、修复和解释；产品负责状态、证据、审计、恢复和安全 gate。

2. **一个策略优先一个长期工作会话。**  
   用户不是在提交孤立任务，而是在同一个 Strategy Work Session 中持续推进。

3. **长上下文要被利用，但不能无差别塞满。**  
   使用分层上下文：短 control memory、标准 context pack、完整 artifact 路径、活跃 session 上下文。

4. **LLM+量化是一等策略类型。**  
   不把 LLM 只当 review card。产品必须支持 LLM/news/event/macro factor 的生成、prompt 优化、PIT materialization、replay backtest 和边际贡献验证。

5. **回测必须可复现。**  
   Live LLM inference 可以生成 feature packets，但确定性 backtest 和 promotion 只能读取已落盘、带 PIT 元数据的 packets。

## 4. 目标架构

### 4.1 StrategyWorkSession

新增产品对象：

```yaml
schema_version: 1
project_id: qqq-momentum
primary_agent: codex
session_id: codex-session-...
status: active | idle | lost | archived
worktree_path: .
queue_path: projects/qqq-momentum/session/queue.jsonl
trace_path: projects/qqq-momentum/session/trace.jsonl
context_pack_path: projects/qqq-momentum/session/context-pack.md
checkpoint_path: projects/qqq-momentum/session/checkpoint.md
last_seen_at: 2026-05-22T00:00:00Z
last_context_pack_hash: sha256:...
```

Dashboard 的“继续优化 / 调整方向 / 停止 / 生成 LLM 因子证据”都写入同一个 session queue。只在 session 丢失、过期或用户主动切换 agent 时，才用 context pack 启动恢复会话。

### 4.2 分层 Memory

保留 `1KB memory`，但降级为 control hint：

| 层级 | 默认大小 | 用途 |
|---|---:|---|
| control memory | 1KB-2KB | 强约束摘要：别重复什么、当前 blocker、下一步最小动作 |
| context pack | 32KB，最大 128KB | 当前策略会话主上下文：最近轮次、指标趋势、失败路径、关键 artifact 摘要 |
| active session context | Codex / Claude Code 原生上下文 | 保留连续推理、尝试路径和自我修复过程 |
| full artifacts | 文件路径引用 | 需要时由 agent 按路径读取，不全文塞入 prompt |

### 4.3 Agent Sandbox Tools

产品不再用硬编码 step 替代 agent 规划，而是提供工具边界：

- `read_project_state`
- `write_session_trace`
- `write_run_ledger`
- `run_spec_validate`
- `run_backtest`
- `run_feature_materialization`
- `run_promotion_check`
- `run_repo_check`
- `request_human_confirmation`

Codex / Claude Code 在 session 中自主决定调用顺序。产品只要求关键结果落盘，并在 promotion / paper 阶段执行确定性 gate。

### 4.4 LLM+Quant Strategy Types

新增策略类型标签：

```yaml
strategy_kind:
  pure_quant
  quant_with_llm_review
  quant_with_llm_factor
  quant_with_alt_data_factor
  llm_router_meta_selection
```

`StrategySpec` 仍是源头，但增加 LLM factor manifest：

```yaml
llm_factors:
  news_regime_score:
    input_view: news_window_v1
    prompt_template_path: prompts/news_regime_score.md
    model: configured_default
    output_schema:
      score: float
      confidence: float
      rationale: string
    cache_policy:
      key: [symbol, visible_at, input_hash, prompt_hash, model]
      mode: materialize_then_replay
```

### 4.5 LLM Feature Materialization

LLM+量化策略的正确闭环：

1. Agent 设计或修改 prompt。
2. 系统计算 `prompt_hash`。
3. 系统构造 point-in-time input windows。
4. `oc feature materialize` 对历史窗口调用 LLM，写入 feature packets。
5. backtest 只从 packets replay，不在 loop 中 live call。
6. promotion 比较 quant baseline、LLM factor version、missing modality fallback。

这允许 Codex / Claude Code 优化 prompt，同时保留可复现性。

### 4.6 Python Strategy Module / SDK Extension

对复杂策略新增受控 Python module：

```yaml
strategy_module:
  path: strategies_py/qqq_momentum.py
  class_name: Strategy
  interface_version: 1
  allowed_imports_profile: research
```

约束：

- StrategySpec 仍声明 universe、data、execution、risk、capabilities、paper mode。
- Python module 只表达复杂 signal / routing / feature transform。
- promotion 前必须通过 module contract test、deterministic smoke backtest、artifact contract 和 expression / import safety check。
- paper_auto 不允许未审查 module 直接下单。

## 5. 交互设计

### 5.1 Dashboard 策略详情页新增 Session 区

显示：

- 当前 StrategyWorkSession 状态。
- 绑定 agent：Codex / Claude Code。
- session 是否 active、idle、lost。
- 当前 queue 中的用户指令。
- 最近 trace step。
- 最近 checkpoint。
- context pack 大小和更新时间。

主要按钮：

- `继续当前会话`
- `追加方向`
- `生成 LLM 因子证据`
- `重建 context pack`
- `恢复新 session`
- `停止会话`

### 5.2 Build 页面新增策略类型选择

创建策略时明确选择：

- 纯量化策略
- 量化 + LLM review
- 量化 + LLM/news/event/macro factor
- Router + LLM meta-selection

如果选择 LLM+量化，Build 页面必须提示：

- 需要 PIT feature packets。
- 需要 quant baseline。
- 需要 marginal lift。
- paper readiness 不接受 live-only LLM 判断。

### 5.3 Iteration 页面变成 Session 操作台

用户不再只看到“Round 1/2/3”，而是看到：

- Agent 当前在做什么。
- 本轮改了哪些变量或 prompt。
- 指标趋势是否改善。
- LLM factor 是否重新 materialize。
- 哪些 blocker 是 soft warning，哪些是 paper hard gate。

## 6. 实施计划

### P0：修正产品语义

- 明确 `1KB memory` 只是 control hint。
- 文档中把 `agent_request` 标为 legacy / compatibility path。
- Dashboard 文案从“继续优化任务”改为“继续策略会话”。

### P1：StrategyWorkSession MVP

- 新增 `open_composer/models/work_session.py`。
- 新增 `projects/{project}/session/session.yaml`。
- 新增 `queue.jsonl`、`trace.jsonl`、`checkpoint.md`。
- `oc project continue` 写 session queue，不再只写一次性 request。
- `reports/agent_requests/` 保留为外部 agent 兼容出口。

### P2：Context Pack Builder

- 新增 `projects/{project}/session/context-pack.md`。
- 默认 32KB，上限 128KB。
- 包含：
  - project summary
  - current spec summary
  - latest N run ledger
  - metric trend
  - blockers and warnings
  - LLM factor prompt / packet status
  - artifact path index
  - do_not_repeat
- session 恢复时优先读取 context pack。

### P3：Agent Backend Adapter

- 新增 `AgentBackend` 接口：
  - `start_session`
  - `send_instruction`
  - `status`
  - `checkpoint`
  - `recover`
- 先支持 `manual_file_queue`，再接 `codex_cli` / `claude_code_cli`。
- 如果无法可靠控制真实 Codex session，产品必须如实显示 `manual queue`，不能假装绑定成功。

### P4：LLM Factor Manifest

- 扩展 StrategySpec：
  - `strategy_kind`
  - `llm_factors`
  - `strategy_module`
- 增加 schema 校验：
  - LLM factor 必须声明 input_view、prompt_template、output_schema、cache_policy。
  - paper path 必须有 PIT packets 和 marginal lift。

### P5：Feature Materialization Pipeline

- 新增 `oc feature materialize <strategy>`。
- 新增 artifact：
  - `reports/features/{strategy}/{factor}/packets.jsonl`
  - `reports/features/{strategy}/{factor}/materialization-run.json`
  - `reports/features/{strategy}/{factor}/prompt-trial-ledger.jsonl`
- cache key：`symbol + visible_at + input_hash + prompt_hash + model`。
- backtest 只读取 materialized packets。

### P6：LLM+Quant Evaluation Loop

- 新增 `oc research llm-factor-eval <strategy>`。
- 自动生成：
  - quant baseline
  - LLM factor variant
  - missing modality fallback
  - marginal lift report
  - robustness report
- Dashboard Alt/LLM Evidence 面板展示这些结果。

### P7：Python Strategy Module MVP

- 新增 `strategies_py/`。
- 定义最小 SDK interface。
- StrategySpec 引用 module。
- 新增 module contract test。
- paper_auto 前必须通过 module safety gate。

## 7. 风险与应对

| 风险 | 应对 |
|---|---|
| Agent 自主规划跑偏 | 产品只放开研究流程；promotion/paper/order 仍由确定性 gate 控制 |
| 长上下文塞太多噪声 | context pack 有大小上限，完整 artifact 只给路径 |
| Codex session 丢失 | checkpoint + context pack 恢复新 session |
| LLM feature 成本过高 | materialization 按 hash 缓存；改 prompt 才重算 |
| Live LLM 回测不可复现 | 禁止 backtest loop live call；先 materialize，再 replay |
| Prompt 过拟合 | prompt trial ledger、holdout、blind test、missing modality robustness |
| Python module 引入任意代码风险 | allowed imports、contract test、sandbox、paper gate |
| Dashboard 变成执行引擎 | Dashboard 只写 session queue 和展示状态，长任务由 local/VPS agent 执行 |

## 8. 不做什么

- 不删除 StrategySpec。
- 不把 live LLM call 放进 deterministic backtest loop。
- 不取消 promotion / paper readiness gate。
- 不把 1KB memory 当作主上下文。
- 不继续把每次优化都设计成孤立 agent request。
- 不为了 SDK-first 放弃文件审计和 artifact contracts。

## 9. 完成标准

完成后，产品应满足：

- 用户创建一个策略后，能看到并持续使用该策略自己的 AI work session。
- Codex / Claude Code 能在同一策略 session 中连续读取、修改、回测、修复和总结。
- session 丢失后能通过 context pack 恢复，而不是只靠 1KB memory。
- LLM+量化策略能完整跑通：prompt 设计、PIT materialization、replay backtest、baseline 对比、marginal lift、robustness。
- Dashboard 展示的是 session 状态、证据状态和下一步动作，而不是一次性任务列表。
- paper readiness 仍由确定性证据决定，LLM 不能自行越权。
