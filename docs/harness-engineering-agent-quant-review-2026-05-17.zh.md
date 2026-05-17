# Open Composer Harness Engineering 研究与产品强化计划

日期：2026-05-17

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

