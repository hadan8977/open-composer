# Open Composer Harness Engineering 研究与产品强化计划

日期：2026-05-17

## 术语说明和研究范围

本文把用户提出的 “Honest 工程” 理解为 Open Composer 需要建立的
Honest/Harness engineering：让 AI 生成、量化研究、回测评估、Dashboard 展示和远程部署
都被同一套证据、权限、状态、审计和晋升规则约束。这里的 “Honest” 不是道德宣言，而是
工程属性：系统必须诚实地区分猜测、研究结果、可复验证据、LLM 辅助贡献、paper readiness
和真实交易能力。

研究范围覆盖三类参考对象：

- Agent 工程：OpenAI Agents SDK、LangGraph、AutoGen。
- 量化产品与研究平台：QuantConnect、NautilusTrader、MLflow、Qlib、Alphalens、OpenBB。
- AI + 量化项目与论文方法：FinRL、FinGPT、Microsoft RD-Agent、MLFinLab/Lopez de Prado
  的数据泄漏、回测过拟合、deflated Sharpe ratio、purged/embargoed validation 相关方法。

这些对象不应被照搬成 Open Composer 的复杂依赖，而应转化成更轻的本地文件优先控制层：
`StrategySpec` 保持 source of truth；CLI 和 research kernel 负责生成证据；Dashboard 只读
证据和发起受控 request；Codex/Claude Code 负责执行受限任务；repo check、readiness、
promotion gate 和 harness policy 负责阻断不诚实的晋升。

## 结论

这里的 harness engineering 不是再给用户一份更长的提示词模板，而是把
LLM、Codex、Claude Code、技能插件、研究脚本、回测报告和 Dashboard 都包进
一套可执行、可恢复、可审计、可阻断的产品控制层。

Open Composer 当前已经有 harness 的几个关键零件：

- `.agents/skills/*/SKILL.md`：给 Codex 类 agent 的策略设计、回测、Pine、风险审查、周报等技能规则。
- `.claude/skills/*/SKILL.md`：Claude Code 侧的技能镜像。
- `scripts/sync-agent-skills.py`：把 `.agents/skills` 同步到 `.claude/skills`。
- `scripts/check-agent-parity.py` 和 `oc repo check --strict`：检查 Claude 规则、命令、settings、skills 镜像是否漂移。
- `reports/agent_requests/`：Dashboard/Vercel 不能执行长任务时，用文件型 request 把任务交给本地或 VPS daemon 侧 agent。
- `ResearchBrief`、`SearchSpace`、`ResearchRunIndexRecord`、`CandidateSet`、`TrialLedger`、`ResearchGateSummary`：研究内核已经开始把策略研究变成结构化证据，而不是只输出一段回测文本。

但当前 harness 还不够强。核心问题是：很多规则仍然是 agent 行为约束，尚未全部变成产品运行时不可绕过的 workflow gate。也就是说，技能插件已经能引导 Codex/Claude Code 做正确的事，但产品还没有一个统一的 `ResearchWorkflowHarness` 自动把“自然语言想法 -> spec -> search space -> candidates -> trials -> evaluation -> promotion blockers -> dashboard next action”完整执行并阻断不合格晋升。

下一步最重要的优化不是让用户输入更多，而是让产品默认生成和强制执行更多内容：

- 用户只给交易想法时，产品自动生成 `ResearchBrief`、可调参数范围、方法变体、因子变体、universe 变体和有限搜索空间。
- 只要有优化，产品强制写 `CandidateSet` 和 `TrialLedger`；没有 trial ledger 的优化结果不能进入 `research_pass`。
- 只要有 LLM/news/event/macro/alternative data，产品强制使用 point-in-time replay packets，并要求单模态 baseline、边际增益和 missing-modality robustness；否则 `llm_contribution_pass=false`。
- 只要涉及 paper readiness，产品强制检查 OOS、walk-forward、成本压力、容量/成交难易度、benchmark family、data comparison、execution reality 和 paper readiness；sample/fixture/fallback/trial-only evidence 不能过 gate。
- Dashboard 只展示证据、阻塞项、下一步动作和 agent request，不在 Vercel 执行回测、扫描、pytest、构建、写文件或 shell。

## 成熟系统给出的依据

### Agent workflow 依据

OpenAI Agents SDK 的启发是：agent 产品需要 code-first orchestration，而不是只靠
prompt。官方文档把 Agent、Handoff、Guardrail、Session、tools、sandbox 和 tracing
作为核心原语；tracing 默认记录 model calls、tool calls、handoffs、guardrails 和
custom spans。对 Open Composer 来说，这对应一个明确原则：Codex/Claude Code 可以
承担研究和代码生成，但产品必须保存结构化 run trace、tool/action boundary、guardrail
结果和可复验 artifact，而不是把 agent 最终回答当成事实。

参考：

- https://developers.openai.com/api/docs/libraries#use-the-agents-sdk
- https://developers.openai.com/tracks/building-agents#foundations-of-the-agents-sdk
- https://developers.openai.com/api/docs/guides/agents/integrations-observability#tracing

LangGraph 的核心启发是：长时间运行的 agent 不能只靠一次 prompt，而要有持久状态、可恢复执行、人工介入和可追踪执行路径。官方文档把 durable execution、human-in-the-loop、memory、debugging/trace 和 production deployment 作为核心能力。这对应 Open Composer 的要求：agent 生成策略时应该留下状态和证据，而不是只留下自然语言结论。

参考：https://docs.langchain.com/oss/python/langgraph/overview

AutoGen 的启发是：多 agent 系统需要 agent/team、工具、状态保存、human-in-the-loop、GraphFlow、logging/tracing 这些工程化对象。官方文档强调 AgentChat 的 agents、teams、多 agent pattern，以及 Core 的 event-driven、distributed、observable/debuggable 架构。对 Open Composer 来说，skills 不应该只是文件夹里的说明，而应该映射成可执行的 workflow policy、agent role 和 tool permission。

参考：

- https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/index.html
- https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/index.html
- https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/state.html

### 量化产品依据

QuantConnect Algorithm Framework 把交易策略拆成 Universe Selection、Alpha Creation、Portfolio Construction、Execution、Risk Management。它的启发是：成熟策略产品会把策略生命周期拆成稳定模块，而不是让一个函数同时做选股、信号、仓位、执行和风控。Open Composer 的 `StrategySpec` 应继续作为 source of truth，但应把 spec 内部的 signal、portfolio、execution、risk、data/evidence 约束拆成更明确的模块化 contract。

参考：https://www.quantconnect.com/docs/v1/algorithm-framework/overview

QuantConnect Reality Modeling 明确把 fill、slippage、fee、brokerage、buying power、settlement、short availability 等作为回测真实性模型。它的启发是：回测与实盘差异不应等用户问了才考虑，而应是默认 gate。Open Composer 已有成本、slippage、impact 和 NautilusTrader 方向，但还需要把成交难易度、容量、流动性、换手、订单大小占成交量、延迟/价格漂移等默认写进 promotion evidence。

参考：

- https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts
- https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/key-concepts

NautilusTrader 的启发是：event-driven backtest 和 sandbox/live 应尽量共享同一套执行语义，并且 fill model 要处理 order book、trade tick、timestamp guard、liquidity consumption 等细节。Open Composer 不应另造完整执行引擎；正确方向是保持 in-repo Python engine 作为确定性参考和 smoke test，同时把严肃执行 parity 逐步交给 NautilusTrader adapter。

参考：https://nautilustrader.io/docs/latest/concepts/backtesting/

MLflow 和 Qlib Recorder 的启发是：研究结果必须是 experiment/run/recorder/artifact，而不是散落的临时文件。MLflow 把 run 定义成一次代码执行并记录参数、指标、时间、artifact；Qlib Recorder 在 experiment 下管理多个 recorder/run。Open Composer 的 `ResearchRunIndexRecord`、`TrialLedger` 和 `reports/research/index.jsonl` 应继续向这个方向收敛。

参考：

- https://mlflow.org/docs/latest/ml/tracking/
- https://qlib.readthedocs.io/en/stable/component/recorder.html

Alphalens 的启发是：因子研究要看 forward returns、information coefficient、
quantile tearsheet、turnover 等诊断，而不是只看策略级 Sharpe。Open Composer 的因子
诊断应继续向“每个因子是否稳定、是否有单独贡献、是否只是追随某个 regime”收敛。

参考：https://alphalens.ml4trading.io/

MLFinLab 与 Lopez de Prado 系列方法的启发是：金融机器学习最危险的问题是数据泄漏、
多重试验和回测过拟合。purged/embargoed cross-validation、deflated Sharpe ratio、
probability of backtest overfitting 这类方法的价值不在于让 MVP 立刻实现完整库，而在
于给 Open Composer 设定默认 gate：不能把大量试出来的最优参数当作未经折扣的 Alpha；
不能把时间相邻、标签重叠的数据随意交叉验证；不能把只在一个回测窗口里漂亮的结果直接
推进 paper readiness。

参考：

- https://hudsonthames.org/mlfinlab/
- https://mlfinlab.readthedocs.io/
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253

### AI + 量化项目与论文依据

FinRL 的启发是：AI 交易系统需要 data layer、environment layer、agent layer 的清晰分层，
并且要把训练、验证、测试和交易分开。它适合提醒 Open Composer：即使未来支持机器学习或
强化学习，也应该先进入 research-only sandbox，保留数据切分、环境假设、reward、成本和
行动空间记录，不能让黑盒模型绕过现有 `StrategySpec` 和 paper readiness gate。

参考：

- https://finrl.readthedocs.io/
- https://arxiv.org/abs/2011.09607

FinGPT 的启发是：金融 LLM 的价值更多来自领域数据流水线、检索/微调/评估闭环和任务化
benchmark，而不是把通用 LLM 直接接到交易指令上。对 Open Composer 来说，LLM 可以用于
研究总结、事件解释、节点化判断、特征候选生成和 review card；但只要 LLM 输出要影响策略
信号，就必须先落成 point-in-time feature packet，并通过 pure quant baseline、marginal
lift 和 missing-modality robustness。

参考：

- https://github.com/AI4Finance-Foundation/FinGPT
- https://arxiv.org/abs/2306.06031

Microsoft RD-Agent 的启发是：AI for data-driven R&D 应把假设、实验、反馈和知识库做成
闭环，让 agent 自动提出实验、执行、总结并迭代。它和 Open Composer 的契合点很强：策略
研究不应该是一次生成，而应该是 `hypothesis -> experiment -> evidence -> critique ->
next action` 的可审计循环。区别是 Open Composer 必须更严格地区分 workflow success、
research evidence、LLM contribution 和 paper readiness。

参考：https://github.com/microsoft/RD-Agent

OpenBB 的启发是：现代金融研究平台通常把多源数据、标准化接口和 notebook/API workflow
放在核心位置。Open Composer 不需要复制一个完整数据终端，但应保持 `capabilities/registry.yaml`
作为数据能力入口，所有 market/event/macro/news/alternative data 先经过 capability
evaluation，再进入 replayable artifact。

参考：https://docs.openbb.co/

这些项目和论文共同指向同一个结论：AI+量化产品的“诚实”不在于模型多聪明，而在于每个
研究结论都有可追踪输入、受限工具、可复验实验、明确失败原因和不可绕过的晋升 gate。

### 参考对象到产品控制的映射

| 参考对象 | 可借鉴的成熟做法 | Open Composer 应转成的控制 |
| --- | --- | --- |
| OpenAI Agents SDK | agent、handoff、guardrail、session、tracing | `WorkflowPlan`、`StepResult`、tool boundary、guardrail evidence、run trace |
| LangGraph | durable state、human-in-loop、可恢复 graph | `ResearchWorkflowHarness`、可恢复 step、人工确认 Red action |
| AutoGen | 多 agent team、GraphFlow、tool/use state、logging | skill policy、agent request owner、expected artifacts、acceptance gates |
| QuantConnect Algorithm Framework | universe、alpha、portfolio、execution、risk 模块化 | `StrategySpec` 内部 contract 拆清 signal/portfolio/execution/risk |
| QuantConnect Reality Modeling | fill、fee、slippage、buying power、settlement | 默认成本、容量、成交难易度、流动性和执行 reality gate |
| NautilusTrader | event-driven backtest 与执行语义复用 | Python engine 做确定性参考，Nautilus adapter 做严肃执行 parity |
| MLflow/Qlib | experiment、run、recorder、artifact | `ResearchRunIndexRecord`、`TrialLedger`、`EvidenceManifest` |
| Alphalens | factor IC、forward returns、turnover、tearsheet | 因子级诊断，不只看策略级 Sharpe |
| MLFinLab/Lopez de Prado | purged CV、embargo、DSR、PBO | 默认防泄漏、防多重试验、防回测过拟合 gate |
| FinRL | data/env/agent 分层，训练/验证/测试/交易分离 | ML/RL 只能先进入 research-only sandbox |
| FinGPT | 金融数据流水线、任务化 benchmark、LLM 金融适配 | LLM 输出必须落成 replayable feature packet 才能影响信号 |
| RD-Agent | hypothesis、experiment、feedback、knowledge 闭环 | 策略研究改成 hypothesis -> experiment -> critique -> next action |
| OpenBB | 多源金融数据统一 API | `capabilities/registry.yaml` 继续作为数据能力入口 |

## 当前 harness 工程实际状态

### 已经做到

1. 技能插件已覆盖主要 agent 角色。

当前 `.agents/skills` 包含：

- `strategy-designer`
- `strategy-researcher`
- `python-backtest-writer`
- `pine-exporter`
- `signal-parity-reviewer`
- `risk-reviewer`
- `weekly-reviewer`
- `capability-evaluator`
- `nautilus-trader-adapter`

这些技能已经要求：先 draft，再 validate；可调参数必须有范围、方法变体、因子变体和 bounded search space；新增数据能力要走 capability registry；回测要有报告；信号要先 log；paper order 要显式确认；LLM/news/event/macro 必须是 point-in-time replay packets。

2. Claude Code 与 Codex 规则已有同步和漂移检查。

`.agents/skills` 是源，`.claude/skills` 是镜像。`scripts/sync-agent-skills.py` 会删除 stale skill 并复制最新 skill；`scripts/check-agent-parity.py` 会检查 `CLAUDE.md` anchor、`.claude/settings.json` 权限 anchor、`.claude/commands` 和 skills mirror。`oc repo check --strict` 已把这些纳入 repo gate。

3. Dashboard remote mode 已有安全边界。

项目规则明确：Vercel 是 password-session BFF，不运行长任务，不写项目文件，不跑回测/扫描/pytest/dashboard build/shell。长任务通过 `reports/agent_requests/` 交给 daemon/local agent。这是正确方向，因为它把浏览器和云端 BFF 从“执行面”降级成“控制面/读模型”。

4. 研究内核已有结构化雏形。

当前已经有：

- `ResearchBrief`：自动表达研究目标、假设、约束和必须回答的问题。
- `SearchSpace`：从 `StrategySpec.notes.research_design` 提取参数范围、方法变体、因子变体、universe 变体和成本假设。
- `CandidateSet` / `TrialLedger`：让参数搜索和候选选择有结构化记录。
- `ResearchRunIndexRecord`：让 Dashboard 可以索引 run、spec hash、data profile、候选数、trial 数、runtime、gate 状态和报告路径。
- `ResearchGateSummary`：开始区分 `workflow_pass`、`research_pass`、`llm_contribution_pass`、`paper_ready_pass`。

### 还没有完全做到

1. Skills 还没有被编译成产品级 policy。

现在 skills 主要约束“agent 应该怎么做”。但如果某个 CLI 流程没有显式调用这些规则，产品运行时并不会自动知道必须先做哪些步骤。因此还需要一个可机器读取的 `PolicyPack` 或 `HarnessPolicyManifest`，把技能文件中的要求转成明确的 gate：

- required inputs
- required artifacts
- allowed tools
- forbidden tools
- promotion blockers
- dashboard next actions
- CLI acceptance checks

2. 没有统一的 `ResearchWorkflowHarness` 一键流程。

当前用户仍可能需要知道应该运行 draft、validate、backtest、parameter sweep、promotion report、paper readiness 等命令。更好的方式是提供：

```bash
uv run oc strategy create-and-research --idea "..."
uv run oc strategy research-workflow strategies/foo.yaml
```

这两个命令应该自动完成：

- draft spec
- validate spec
- infer research brief
- infer search space
- evaluate capabilities
- generate candidate set
- run bounded trials
- write trial ledger
- run benchmark family
- run cost/capacity/data-quality gates
- run promotion report
- write decision card
- create next agent request if blocked

3. Dashboard 还没有完全变成 harness cockpit。

Dashboard 当前已经能读策略、报告、研究索引和部分 decision 信息，但下一步应更明确地展示：

- 当前策略卡在哪个 gate
- 为什么被阻塞
- 缺哪类证据
- 下一步应该生成哪个 agent request
- 哪些动作是 Red action，需要双重确认
- 哪些结论只能算 workflow pass，不能算 Alpha 或 paper readiness

4. LLM/Codex/Claude Code 的优势还没有被充分产品化。

LLM 的优势不应该体现在“用户提示词写得更复杂”，而应该体现在产品自动做这些事：

- 把模糊想法转成结构化研究问题。
- 自动提出多种方法变体和因子变体。
- 自动检查可能的未来函数、数据泄漏、过拟合、执行不可成交、benchmark 不公平。
- 自动把新闻、事件、宏观、文本信号转换成 replayable feature packets。
- 自动给出 blocked reason 和 next action。
- 自动写 review card，而不是直接给 paper order。

## 建议的目标架构

### 1. `HarnessPolicyManifest`

位置建议：

- `open_composer/harness/policies.py`
- `policies/harness.yaml`

作用：

- 把 AGENTS.md、skills、capabilities、remote dashboard rules 中的硬要求转成机器可读策略。
- 每条策略包含 `id`、`scope`、`required_artifacts`、`blocking_conditions`、`warning_conditions`、`next_actions`、`source_rule`。
- `oc repo check --strict` 检查策略清单存在并覆盖必要 anchors。

示例 policy：

```yaml
- id: research.requires_trial_ledger
  scope: strategy_optimization
  required_artifacts:
    - candidate_set
    - trial_ledger
    - selection_decision
  blocking_conditions:
    - optimization_without_trial_ledger
  next_actions:
    - uv run oc strategy parameter-sweep <spec>
```

### 2. `ResearchWorkflowHarness`

位置建议：

- `open_composer/harness/workflow.py`

核心对象：

- `WorkflowPlan`
- `WorkflowStep`
- `StepResult`
- `EvidenceManifest`
- `GateMatrix`
- `AutonomyBudget`
- `NextAction`

它不替代现有研究模块，而是编排现有模块。原则是：只做 orchestration、artifact validation 和 gate summary，不把 backtest/scan/execution 逻辑复制一份。

### 3. `PolicyPack` from skills

短期不要做复杂自然语言解析。更稳妥的做法是在每个 skill 增加一个 YAML front matter 或 sidecar：

```yaml
policy_pack:
  required_artifacts:
    - spec_validation
    - research_brief
    - search_space
  promotion_blockers:
    - missing_benchmark_family
    - missing_oos
```

然后 `oc harness policy-list` 展示 skill policy，`oc harness check` 检查 skill policy 与 runtime gates 是否一致。

### 4. `EvidenceManifest`

每次研究 run 都应生成一个 manifest：

```json
{
  "run_id": "...",
  "spec_hash": "...",
  "data_sources": [],
  "feature_packets": [],
  "benchmarks": [],
  "trials": [],
  "reports": [],
  "blocked_gates": [],
  "warning_gates": []
}
```

Dashboard 只读 manifest 和 report，不自己推断真相。

### 5. Dashboard harness cockpit

Dashboard 不需要变成重型交易平台，而应更像决策驾驶舱：

- Strategy card：当前 lifecycle、latest run、spec hash、gate summary。
- Evidence tab：research brief、search space、candidate set、trial ledger、benchmark family、feature packets。
- Blockers tab：每个 blocker 的证据路径和下一步命令。
- Agent Requests tab：把下一步任务写到 `reports/agent_requests/`。
- Remote safety tab：显示 Vercel/BFF/daemon 状态，但不执行长任务。

## 默认强约束清单

这些约束应该由产品默认执行，不要求用户在 prompt 里主动提出。

### 策略生成

- 必须生成 draft `StrategySpec`。
- 必须 validate spec。
- 如果任何参数可调，必须生成 bounded search space。
- 必须给出 method variants、factor variants、parameter ranges。
- 必须记录 capabilities，新增 capability 前必须跑 capability evaluation。
- 不能把单一固定参数集当成“已优化策略”。

### 回测与研究

- 必须写 backtest report。
- 必须有 benchmark family：same-symbol buy-and-hold、equal-weight universe、market proxy、sector/theme proxy、cash proxy、ex-post best symbol when available。
- 必须检查 OOS 或 walk-forward。
- 必须检查成本、slippage、market impact、容量/成交难易度。
- 必须检查 data quality、timestamp alignment、adjustment policy、feed coverage。
- 必须区分 workflow pass、research pass、LLM contribution pass、paper ready pass。

### 优化迭代

- 必须写 `CandidateSet`。
- 必须写 `TrialLedger`。
- 必须写 `SelectionDecision`，包含选择理由和 blockers。
- 选择只基于 IS 或 trial-only evidence 时，只能 warning，不能 research pass。
- 多轮优化必须保留 previous run comparison，防止“最后一次看起来最好”。

### LLM/另类数据

- LLM/news/event/macro/alternative data 不能直接影响交易，除非有 point-in-time replay packet。
- packet 必须有 `visible_at`、`published_at`、`fetched_at`、`source`、`input_hash`、`prompt_hash`。
- 必须有 pure quant baseline。
- 必须有 marginal lift。
- 必须有 missing-modality robustness。
- LLM fallback、local choice 或与 pure quant baseline 相同的信号不能标为独立 LLM Alpha。

### Paper readiness

- sample、fixture、cache fallback、trial/research-only data 不能通过 paper readiness。
- Alpaca Paper order 仍需显式命令确认和 active `paper_auto` spec。
- real-money broker write access 继续 out of scope。

### Remote Dashboard

- Vercel 只做 password-session BFF。
- Vercel 不运行 backtests、scans、pytest、dashboard builds、file writes、shell commands。
- 长任务只能写 agent request。
- Red actions 必须双重确认、audit、backup。

## 分阶段实施计划

### P0：把现有 harness 现状固化进 repo gate

目标：让 skills 和 harness 规则不再漂移。

工作：

- 增加 `oc harness check`。
- 增加 `oc harness policy-list`。
- 增加 `HarnessPolicyManifest` schema。
- `repo_check` 增加 policy manifest 检查。
- skill front matter 或 sidecar 记录 required artifacts 和 blockers。

验收：

- 删除任一 skill policy 或让 Claude skill mirror 漂移时，`oc repo check --strict` blocked。
- policy manifest 缺少 paper/LLM/research/remote gate 时 blocked。

### P1：一键研究工作流

目标：用户只输入想法或 spec，产品自动完成最小严肃研究流程。

工作：

- `oc strategy create-and-research --idea "..."`
- `oc strategy research-workflow <spec>`
- 自动生成 `ResearchBrief`、`SearchSpace`、`CandidateSet`、`TrialLedger`、`EvidenceManifest`。
- 自动生成 `SelectionDecision` 和 `DecisionCard`。

验收：

- 用户不提防过拟合、不提未来函数、不提成本，workflow 也会默认检查。
- 没有 OOS/walk-forward/cost/benchmark 时，输出 blocked，不输出 paper ready。

### P2：Dashboard harness cockpit

目标：Dashboard 不再只是展示文件，而是展示证据链、阻塞原因和下一步。

工作：

- Strategy decision card 增加 gate matrix。
- Research run view 增加 evidence manifest。
- Blockers 显示 artifact path 和 recommended agent request。
- Remote mode 增加 daemon job status 和 agent request lifecycle。

验收：

- 用户打开 Dashboard 就能看到每个策略为什么不能晋升。
- Dashboard 的下一步动作来自注册命令和 policy，不是自由文本。

### P3：Codex/Claude Code skill harness

目标：把技能插件从“说明书”升级为 agent 能稳定调用的工程接口。

工作：

- 每个 skill 增加 policy metadata。
- `oc harness skill-sync` 包装 `scripts/sync-agent-skills.py`。
- `oc harness skill-attribution` 读取近期 run，评估哪些 skill 对 blocked/resolved 有贡献。
- agent request 增加 `required_skill`、`expected_artifacts`、`acceptance_gates`。

验收：

- Dashboard 创建 agent request 时，会指定技能和产物，不只是写一段 prompt。
- Codex/Claude Code 完成任务后，产品用 expected artifacts 验收，不凭自然语言说“完成”。

### P4：高级数据与研究沙盒

目标：支持更强的另类数据、LLM 节点化策略和几何/拓扑研究，但永远研究先行。

工作：

- 把 LLM judge、event/news/macro packet、geometry features 纳入同一 `FeaturePacket`/`StrategyDAG` contract。
- 增加 node-level replay、node-level ablation、node-level missing data test。
- 几何/拓扑特征默认 `research_only`，必须通过 baseline/marginal lift/robustness 后才可进入更高 gate。

验收：

- 任何新模态先显示为 research sandbox。
- 没有 replay packet 和边际增益证据时，Dashboard 不能把它显示为 Alpha。

## 对当前问题的直接回答

1. 是否能做成更强约束？

可以，而且应该这样做。当前项目已经有规则、技能、repo gate、研究内核和 Dashboard read model 的基础。下一步不是增加用户输入，而是把这些规则编译成 runtime policy 和 workflow harness，让产品自动补全研究计划、证据清单、候选试验、阻塞判断和下一步任务。

2. 目前技能插件增强能力和引导是怎么做的？

当前做法是“文件型技能插件 + Claude 镜像 + parity/repo check”。`.agents/skills` 是 Codex 侧规则，`.claude/skills` 是 Claude Code 侧镜像，脚本负责同步和检查漂移，repo check 负责把它纳入质量门槛。这已经能减少 agent 随意发挥，但还不是完整产品 runtime harness。

3. 当前最大的缺口是什么？

最大的缺口是：skill 规则还没有成为产品命令默认执行的 gate。用户运行某个策略命令时，产品还没有统一 orchestrator 保证所有必要 artifacts 都生成、所有必要 gates 都检查、所有缺口都转成 Dashboard next action。

4. 推荐优先做什么？

优先做 P0 + P1：`HarnessPolicyManifest`、`oc harness check`、`oc harness policy-list`、`oc strategy research-workflow <spec>`。这会直接解决“不要靠用户提示词补充专业约束”的核心问题。
