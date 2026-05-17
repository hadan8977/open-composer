# Harness Engineering 扩展调研日志

日期：2026-05-17

## 目标

本日志用于记录扩展调研范围、调研计划、来源矩阵和学习问题。它不是最终架构结论，而是
支撑 `docs/harness-engineering-agent-quant-review-2026-05-17.zh.md` 后续扩展的过程证据。

用户明确要求：不要过早给结论，至少投入 1 小时调研工作量。因此本次扩展调研以“覆盖足够
多的外部系统和论文，并把它们映射回 Open Composer 的工程约束”为目标。

## 调研计划

### 阶段 1：本地项目基线复核

目标：确认 Open Composer 当前已经有的控制点，避免外部调研脱离实际项目。

检查对象：

- `.agents/skills` / `.claude/skills`
- `scripts/sync-agent-skills.py`
- `scripts/check-agent-parity.py`
- `open_composer/repo_check.py`
- `open_composer/research/kernel/*`
- `open_composer/research/contracts.py`
- `open_composer/feature_packets.py`
- `open_composer/research/strategy_dag.py`
- `open_composer/analytics/execution_reality.py`
- `open_composer/remote/jobs.py`
- `open_composer/agent_requests.py`

本地初步事实：

- 现有项目已有 skill mirror、repo gate、feature packet、StrategyDAG、ResearchContract、
  TrialLedger、ResearchRunIndex、execution reality 和 remote job controls。
- 最大缺口仍是：这些控制点没有被统一编排成不可绕过的 runtime harness。

### 阶段 2：Agent harness 与 coding-agent 工程

调研问题：

- 成熟 agent 框架如何表达状态、工具边界、handoff、guardrail、human-in-loop、trace？
- 多 agent 系统如何避免自然语言接力导致的错误级联？
- coding agent 的评估为什么不能只看最终回答，而要看任务分解、补丁、测试和验收？

来源候选：

- OpenAI Agents SDK
- LangGraph
- AutoGen
- CrewAI Flows
- Semantic Kernel Process/Agent Framework
- LlamaIndex Workflows
- DSPy
- SWE-agent / SWE-bench Verified / OpenHands
- MetaGPT / ChatDev / CAMEL / Mixture-of-Agents
- PaperBench / Agent Laboratory / AI Scientist

需要抽取的控制模式：

- `WorkflowPlan`
- `StepResult`
- `AgentRunTrace`
- `ToolBoundary`
- `HandoffContract`
- `GuardrailResult`
- `HumanApproval`
- `ExpectedArtifacts`
- `AcceptanceGate`

### 阶段 3：量化研究平台与回测真实性

调研问题：

- 成熟量化平台如何拆分 strategy lifecycle？
- 如何处理回测与实盘差异、成交难易度、成本、滑点、流动性和容量？
- 如何处理 research 环境、backtest 环境、live/paper 环境之间的语义一致性？

来源候选：

- QuantConnect Algorithm Framework / LEAN
- QuantConnect Reality Modeling
- NautilusTrader
- Backtrader
- vectorbt
- Zipline Reloaded
- backtesting.py
- Alpaca Market Data / corporate action / adjustment / asof docs
- QuantRocket point-in-time data docs

需要抽取的控制模式：

- `StrategySpec` 模块化 contract
- `ExecutionRealityGate`
- `CapacityCurve`
- `CostSensitivityGrid`
- `DataAdjustmentPolicy`
- `CorporateActionPolicy`
- `BacktestPaperParity`
- `NoParallelExecutionEngine`

### 阶段 4：MLOps、实验追踪与数据治理

调研问题：

- 研究 run、artifact、参数、指标、数据版本如何被记录？
- point-in-time features 如何避免训练/回测中的未来函数？
- 数据质量和数据漂移如何在策略研究中成为默认 gate？

来源候选：

- MLflow Tracking
- Qlib Recorder
- DVC
- Weights & Biases
- Feast feature store / point-in-time joins
- Great Expectations
- Evidently AI
- Model Cards
- Datasheets for Datasets

需要抽取的控制模式：

- `ExperimentRun`
- `EvidenceManifest`
- `DatasetManifest`
- `FeaturePacketManifest`
- `PointInTimeJoinCheck`
- `DataQualityExpectation`
- `RunLineage`
- `ArtifactRegistry`

### 阶段 5：金融 ML、防过拟合和因子研究

调研问题：

- 如何防止数据泄漏、多重试验和回测过拟合？
- 因子研究除了 Sharpe 还应看什么？
- LLM 生成策略时应如何默认折扣“试出来”的结果？

来源候选：

- MLFinLab / Lopez de Prado
- Deflated Sharpe Ratio
- Probability of Backtest Overfitting
- Purged/Embargoed cross-validation
- White Reality Check
- Hansen SPA test
- Alphalens
- Pyfolio / Empyrical

需要抽取的控制模式：

- `PurgedEmbargoConfig`
- `MultipleTestingDiscount`
- `DeflatedSharpeOrProxy`
- `PBOOrProxy`
- `FactorIC`
- `ForwardReturns`
- `QuantileTurnover`
- `FactorCorrelation`
- `SelectionBiasNote`

### 阶段 6：AI + 量化、金融 LLM 与研究 agent

调研问题：

- LLM 更适合作为交易执行 agent，还是作为量化研究员/审查员？
- 金融 LLM 如何处理检索、工具、事件、新闻、财报和另类数据？
- 多智能体交易论文的结果应如何被产品保守吸收？

来源候选：

- FinRL
- FinGPT
- FinRobot
- TradingAgents
- FinAgent / FinAgentBench
- FinMCP-Bench
- AlphaForgeBench
- QuantCode-Bench
- QuantEval
- Large Language Model Agent in Financial Trading surveys

需要抽取的控制模式：

- `LLMAsResearcherNotExecutor`
- `ReplayableFeaturePacket`
- `SingleModalityBaseline`
- `MarginalLift`
- `MissingModalityRobustness`
- `NodeLevelAblation`
- `FinancialToolUseTrace`
- `ExecutableStrategyValidation`

### 阶段 7：AI 风险、安全、可观测性与远程控制面

调研问题：

- Agent 系统如何处理风险分类、human approval、审计和回滚？
- LLM 应用有哪些常见安全风险需要直接反映到 Open Composer？
- 可观测性如何从日志升级为 span/trace/evaluation？

来源候选：

- NIST AI RMF
- OWASP Top 10 for LLM Applications
- OpenTelemetry traces/spans
- Arize Phoenix / LangSmith
- OpenAI agent tracing/evals

需要抽取的控制模式：

- `RiskTier`
- `RedActionDoubleConfirmation`
- `PromptInjectionBoundary`
- `UntrustedSourceReader`
- `TraceSpan`
- `AuditEvent`
- `RollbackManifest`
- `AgentEvalDataset`

## 初步来源矩阵

| 领域 | 来源 | 初步价值 |
| --- | --- | --- |
| OpenAI agent 工程 | OpenAI Agents SDK docs | code-first orchestration、guardrails、sandbox、tracing、evals |
| Agent 状态图 | LangGraph | durable execution、state graph、human-in-loop |
| 多 agent | AutoGen | agent/team、tool use、state、logging、GraphFlow |
| 多 agent SOP | MetaGPT | SOP、人类流程、角色、交接件 |
| 软件开发 agent | ChatDev | 设计/编码/测试/文档流水线与互审 |
| 研究 agent 评估 | PaperBench | 研究复现需要细粒度 rubrics，不靠最终文本 |
| 量化平台 | QuantConnect/LEAN | research/backtest/live、算法框架、模块化 |
| 执行真实性 | QuantConnect Reality Modeling | fill/slippage/fee/buying power 等模型 |
| 事件驱动执行 | NautilusTrader | execution parity、fill model、order book/liquidity |
| 实验追踪 | MLflow | run/params/metrics/artifacts |
| 研究记录 | Qlib Recorder | experiment/recorder/run 管理 |
| 数据版本 | DVC | 数据和 pipeline versioning |
| PIT feature | Feast | historical feature retrieval point-in-time joins |
| 数据质量 | Great Expectations | expectations/validation/checkpoints |
| 因子研究 | Alphalens | IC、quantiles、turnover、forward returns |
| 防过拟合 | MLFinLab/Lopez de Prado | purged CV、DSR、PBO、多重试验 |
| AI 交易研究 | FinRL | data/env/agent layer、训练/验证/测试分离 |
| 金融 LLM | FinGPT | 金融数据流水线和任务评估 |
| AI R&D agent | RD-Agent | hypothesis-experiment-feedback 闭环 |
| LLM 策略生成评估 | QuantCode-Bench / AlphaForgeBench | 交易策略生成要看可执行性、金融语义和行为 |
| 金融工具调用 | FinMCP-Bench | MCP/financial tool-use benchmark |
| 风险治理 | NIST AI RMF | govern/map/measure/manage |
| LLM 安全 | OWASP LLM Top 10 | prompt injection、tool misuse、insecure output |
| 可观测性 | OpenTelemetry | traces/spans/events |

## 已筛选的高价值依据与采用理由

### Agent / Coding Agent

- OpenAI Agents SDK：采用。它直接覆盖 agent、handoff、guardrail、sandbox、tracing、evaluation，
  与 Open Composer 的 Codex/Claude Code 工作流最相关。
- LangGraph：采用。它强调 durable execution、state、human-in-loop，适合作为
  `ResearchWorkflowHarness` 的状态机参考。
- AutoGen：采用。它强调多 agent team、GraphFlow、logging，适合指导 skill owner 和
  agent request contract。
- CrewAI Flows / Semantic Kernel / LlamaIndex Workflows：部分采用。它们都强调 workflow
  比单 agent prompt 更稳定，但不必引入为依赖。
- SWE-agent / SWE-bench Verified / OpenHands：采用为评估思想。它们说明 coding-agent 要看
  patch、test、repo state 和 task success，不只看自然语言总结。
- MetaGPT / ChatDev / CAMEL：部分采用。它们对角色/SOP 有启发，但金融交易场景不能照搬
  多 agent 辩论式流程。
- PaperBench / AI Scientist / Agent Laboratory：采用为 research-agent 验收参考。它们说明
  研究类 agent 需要细粒度 rubrics 和复现实验。

### Quant / Backtest / Execution

- QuantConnect Algorithm Framework / LEAN：采用。它提供 universe、alpha、portfolio、
  execution、risk 的模块化拆分。
- QuantConnect Reality Modeling：强采用。它把 fill、slippage、fee、brokerage、buying
  power、settlement、short availability、capacity 都放进回测真实性模型。
- NautilusTrader：强采用。项目 AGENTS.md 已明确它是 intended path，外部文档也支持用
  event-driven fill model 解决执行 parity。
- Backtrader / vectorbt / Zipline Reloaded / backtesting.py：参考。它们提供不同复杂度的回测
  API，但 Open Composer 不应再引入一个并行执行引擎。
- Almgren-Chriss / square-root market impact：采用为成本和容量建模方向，不要求 P0 完整实现。

### MLOps / Data Governance

- MLflow / Qlib Recorder：强采用。它们与 `ResearchRunIndexRecord`、`TrialLedger` 和
  artifact manifest 直接对应。
- DVC / W&B：参考。适合数据版本和实验管理思想，但不适合当前 file-first MVP 直接引入。
- Feast / Tecton / Hopsworks：采用 point-in-time 思想。Open Composer 不需要完整 feature
  store，但必须把 feature packet 做到 PIT by construction。
- Great Expectations / Evidently：采用数据质量和 drift 检查思想，短期转化为
  `DataQualityExpectation` 和 `DataDriftWarning`。
- Model Cards / Datasheets for Datasets：采用文档结构思想，转化为 Strategy Card、
  DatasetManifest 和 FeaturePacketManifest。

### Financial ML / Factor Research

- Alphalens / Pyfolio / Empyrical：强采用。它们说明因子研究和绩效评估不能只看 Sharpe。
- MLFinLab / Lopez de Prado：强采用。purged CV、embargo、DSR、PBO、多重试验折扣应成为
  Open Composer 研究 gate。
- White Reality Check / Hansen SPA：采用为“多策略比较后必须折扣”的理论依据。

### AI + Quant / Financial LLM

- FinRL / FinRL-X：采用。data/env/agent 分层和 research-live consistency 对 ML/RL 路线有价值。
- FinGPT：采用。金融 LLM 的核心是数据流水线、任务化评估和金融适配，不是直接下单。
- RD-Agent：强采用。hypothesis-experiment-feedback loop 与策略迭代高度契合。
- TradingAgents / FinRobot：参考。多智能体金融分析有启发，但不能让多 agent 讨论绕过硬 gate。
- FinMCP-Bench：采用。金融工具调用准确率可以转成 MCP/tool-use harness gate。
- QuantCode-Bench / AlphaForgeBench / QuantEval：采用。它们说明 LLM 生成量化策略要检查
  语法、可执行性、有交易、金融语义、回测行为和风险约束。

### Risk / Security / Observability

- NIST AI RMF：采用。Govern/Map/Measure/Manage 可映射为 policy、capability mapping、
  gate measurement 和 blocked-action management。
- OWASP LLM Top 10 / MCP Top 10：强采用。Open Composer 必须继续把外部 docs、MCP、news、
  filings、LLM text 当作不可信 reader input。
- OWASP Agentic Skills Top 10：强采用。它直接覆盖 SKILL.md/agent skill 层的风险，尤其是
  tool orchestration、skill supply chain、poor scanning 和 over-broad privileges。
- MCP security / tool poisoning 研究：强采用。外部 MCP server、tool description 和 resource
  output 都可能携带间接 prompt injection 或 permission confusion。
- OpenTelemetry：采用。trace/span 模型适合实现 `AgentRunTrace` 和 `WorkflowStepTrace`。
- Phoenix / LangSmith：参考。适合 LLM trace/eval UX，但当前不引入 SaaS 依赖。

安全侧归纳：

- Least Agency：每个 agent/skill/tool 只能获得完成当前 step 所需的最小权限。
- Strong Observability：每个 state transition、tool call、file write、gate decision 都需要日志。
- Human approval：Red action 必须双重确认，且确认短语不能由 LLM 自己生成。
- Untrusted source boundary：外部内容只能作为 reader input，不能直接变成 writer instruction。
- Tool output validation：MCP/tool 输出必须通过 schema 和 capability id 才能进入证据链。
- Skill supply chain：skill 变更必须同步到 Claude mirror 并通过 repo check；未来还应有 policy diff。

## 暂缓采纳的方向

- 直接引入重型 MLOps 平台：与 Open Composer 当前 file-first、personal workbench 定位不符。
- 直接让 LLM 做实时交易执行：与现有安全规则和金融 LLM benchmark 风险不符。
- 复制完整 QuantConnect/LEAN：项目已选择 Python deterministic engine + NautilusTrader adapter 方向。
- 复制完整 feature store：当前更适合先做 replayable feature packet 和 manifest。

## 读后归纳：七类可迁移模式

### 1. Agent trace-first

OpenAI Agents SDK、LangGraph、AutoGen、OpenTelemetry、LangSmith/Phoenix 的共同点是：
agent run 需要被记录成 trace，而不是被压缩成一句“完成了”。对 Open Composer 来说，
每次 agent/codex/cloud-code 介入策略研究都应产生 `AgentRunTrace`：

- 输入：idea/spec/report/feature packet/agent request。
- 工具：读取哪些文件、运行哪些命令、写了哪些 artifact。
- handoff：由哪个 skill 或 agent role 接手。
- guardrail：哪些 gate 被触发、哪些被阻断。
- 输出：结构化 artifact 路径，而不是自然语言承诺。

### 2. Policy-as-code

AGENTS.md、CLAUDE.md 和 SKILL.md 现在是文本规则。LangGraph/AutoGen/OpenAI Agents SDK
说明成熟 agent 产品需要把规则变成可执行对象。Open Composer 应把文本规则提炼为
`HarnessPolicyManifest`：

- policy id
- scope
- required artifacts
- forbidden actions
- blocking conditions
- next actions
- owning skill
- verification command

### 3. Research run as experiment

MLflow、Qlib、W&B、DVC 的共同点是：每一次试验都要记录参数、指标、数据、artifact 和
lineage。Open Composer 已有 `ResearchRunIndexRecord` 和 `TrialLedger`，但还应补
`EvidenceManifest` 和 `DatasetManifest`，让 Dashboard 和 repo check 能看到完整证据链。

### 4. Point-in-time by construction

Feast、Tecton、Hopsworks、金融 feature store 文档的核心不是“有更多数据”，而是 historical
feature retrieval 必须 point-in-time correct。Open Composer 已有 feature packet 的
`visible_at/published_at/fetched_at/input_hash/prompt_hash`，下一步应补：

- feature packet manifest
- PIT join check
- missing packet policy
- replay window policy
- feature packet ablation

### 5. Multiple-testing discount by default

MLFinLab、Lopez de Prado、White Reality Check、Hansen SPA 的共同点是：大量试验后的最好
结果不能按原始 Sharpe 解读。Open Composer 当前已记录 trial ledger 和 selection note，
下一步应把多重试验折扣写成 gate：

- trial count threshold
- DSR/PBO proxy warning
- OOS/walk-forward minimum
- selection decision cannot be paper-ready if only IS evidence exists

### 6. Execution realism before paper readiness

QuantConnect Reality Modeling、NautilusTrader、Backtrader/vectorbt/Zipline 等系统都把
broker model、slippage、commission、fill、order book 或 event-driven semantics 看成回测
可信度的一部分。Open Composer 已有 execution reality 和 cost grid，下一步应把这些纳入
统一 promotion gate：

- bar participation
- ADV participation
- capacity curve
- slippage stress
- next-bar fill assumption
- Nautilus parity status

### 7. Financial LLM as researcher, not executor

FinGPT、FinRobot、TradingAgents、FinMCP-Bench、QuantCode-Bench 等材料都说明金融 LLM 的
价值在于研究、数据处理、工具调用、策略生成和审查，但其输出必须经过可执行性和回测语义
验证。Open Composer 应把 LLM 设定为：

- research assistant
- feature proposer
- event/news summarizer
- review card writer
- node-level judge in replay-only DAG

而不是：

- live executor
- broker writer
- unlogged backtest participant
- unverified alpha source
