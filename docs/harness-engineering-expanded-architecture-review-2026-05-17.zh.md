# Honest/Harness Engineering 扩展架构审查

日期：2026-05-17

## 摘要

这次扩展调研的结论不是“再引入一个框架”，而是把 Open Composer 已有的规则、skills、
research kernel、Dashboard、remote jobs 和 repo gates 升级成一套可执行的
Honest/Harness engineering control plane。

核心判断：

1. 当前项目已经有很多正确零件，但零件之间还缺统一的 runtime harness。
2. 外部成熟系统的共同点不是 prompt 更长，而是 workflow、state、artifact、trace、gate、
   approval、experiment lineage 和 execution realism 都被结构化。
3. 对 Open Composer 来说，下一步应优先做轻量本地 harness，而不是上重型 SaaS/MLOps/feature
   store，也不是让 LLM 直接交易。
4. LLM/Codex/Claude Code 的优势应体现在自动生成研究计划、补全证据链、发现缺口、写受控
   artifact、执行测试和触发下一步 request，而不是要求用户懂所有量化约束。

## 调研计划与覆盖范围

本轮扩展调研按七个维度展开，过程记录见
`docs/harness-engineering-expanded-research-log-2026-05-17.zh.md`。

| 维度 | 关注问题 | 主要参考 |
| --- | --- | --- |
| Agent harness | 状态、工具、handoff、guardrail、trace、evaluation | OpenAI Agents SDK、LangGraph、AutoGen、CrewAI、Semantic Kernel、LlamaIndex |
| Coding/research agent | agent 如何稳定改代码、做研究、被评估 | SWE-agent、SWE-bench Verified、OpenHands、PaperBench、AI Scientist、Agent Laboratory |
| Quant platform | 策略生命周期、回测/实盘一致性、执行真实性 | QuantConnect/LEAN、NautilusTrader、Backtrader、vectorbt、Zipline |
| Experiment/data governance | run、artifact、数据版本、PIT feature、数据质量 | MLflow、Qlib、DVC、Feast、Great Expectations、Evidently |
| Financial ML | 防泄漏、防过拟合、多重试验折扣、因子诊断 | MLFinLab、Lopez de Prado、White Reality Check、Hansen SPA、Alphalens |
| AI + quant | 金融 LLM、策略生成、工具调用、多 agent 金融研究 | FinRL、FinGPT、RD-Agent、TradingAgents、FinRobot、FinMCP-Bench、QuantCode-Bench |
| Risk/security/observability | 风险分层、LLM 安全、审计、trace/span | NIST AI RMF、OWASP LLM Top 10、OpenTelemetry、Phoenix、LangSmith |

## 外部系统抽象出的七类控制模式

### 1. Trace-first agent workflow

OpenAI Agents SDK 文档强调 code-first orchestration、handoff、guardrail、sandbox、tracing
和 evaluation。LangGraph、AutoGen、OpenTelemetry、LangSmith/Phoenix 也都把 agent run
视为可追踪 workflow，而不是一次性文本回答。

对 Open Composer 的含义：

- 每次 Codex/Claude Code 介入策略研究，都应生成 `AgentRunTrace`。
- Trace 记录输入 artifact、使用 skill、工具/命令、修改文件、输出 artifact、触发 gate。
- Dashboard 不应该显示“agent 说完成了”，而应显示 artifact 和 gate 结果。

OpenTelemetry GenAI semantic conventions 已经把 inference、retrieval、execute tool 等 span
类型标准化。Open Composer 不需要马上接入 OTel collector，但 `AgentRunTrace` 的字段最好兼容：
`operation`、`provider/model`、`tool.name`、`tool.input_hash`、`tool.output_hash`、`artifact.path`、
`gate.name`、`gate.status`、`error.type`。这样本地 JSONL trace 将来可以无痛接入 Phoenix、
LangSmith 或 OTel。

OpenAI Agents SDK 的 sandbox/results/human approval 文档还提示：agent 工作空间、可写目录、
pending approvals、run state 和 resume surface 都应显式建模。Open Composer 已有 remote job、
workspace lock、double confirmation 和 agent request，但还缺 agent run manifest 来表达：

- workspace snapshot 或 spec/report hash
- allowed write scopes
- pending approvals
- resumed_from request id
- final output artifact paths

PaperBench、AI Scientist、Agent Laboratory 和 SWE-bench Verified 还说明了另一个要点：研究型
agent 或 coding agent 的成果需要被拆成阶段和 rubrics。Open Composer 不应让 agent 一次性
“生成一个好策略”，而应让它依次完成 research brief、search space、candidate set、trial
ledger、factor diagnostics、promotion evidence、review card，每一步都有 artifact 和 gate。

同时，PaperBench 这类 benchmark 也提醒我们：即使先进 agent 在复杂研究复现任务上也会出现
遗漏、误读、不可复现实验和过度自信。因此 Open Composer 的默认姿态应是保守的：agent 产物
进入 evidence pipeline，而不是直接进入 Alpha/paper readiness。

### 2. Policy-as-code

当前 AGENTS.md、CLAUDE.md、SKILL.md 已有强规则，但它们主要约束 agent 行为。成熟 agent
系统会把规则转成可执行 policy、guardrail 和 approval flow。

对 Open Composer 的含义：

- 引入 `HarnessPolicyManifest`。
- skill front matter 或 sidecar 声明 required artifacts、forbidden actions、blocking conditions。
- `oc harness check` 检查 policy 覆盖 research、LLM、paper、remote、data、execution gate。

### 3. Research run as experiment

MLflow 和 Qlib 的核心模式是 experiment/run/recorder/artifact。DVC/W&B 进一步强调数据、
pipeline 和 experiment lineage。

对 Open Composer 的含义：

- `ResearchRunIndexRecord` 和 `TrialLedger` 是正确方向，但还需要 `EvidenceManifest`。
- 每个 run 应记录 spec hash、data profile、feature packets、candidate set、trials、benchmarks、
  reports、gate summary 和 runtime。
- 没有 manifest 的结果不能被 Dashboard 展示成完整证据。

`EvidenceManifest` 不应只是路径列表，还应表达 lineage graph：

```text
data ingest/cache -> dataset manifest -> feature packets -> candidate set
  -> trial ledger -> benchmark family -> promotion report -> decision card
```

这样 Dashboard 和 repo check 才能回答“这个结论到底来自哪些数据、哪些试验、哪些 gate”，而
不是只知道某个 JSON/Markdown 文件存在。

### 4. Point-in-time by construction

Feast 等 feature store 的核心价值是 point-in-time correct historical feature retrieval。
金融策略尤其不能把未来新闻、财报、宏观数据、LLM 总结泄漏进回测。

对 Open Composer 的含义：

- 现有 `FeaturePacketRow` 已包含 `visible_at/published_at/fetched_at/source/input_hash/prompt_hash`。
- 下一步要补 feature packet manifest、PIT join check、missing packet policy、packet ablation。
- LLM/news/event/macro/alternative data 不能直接影响 signal，只能通过 replayable packet。

Feast/Tecton/Hopsworks 的 point-in-time join 文档给出的工程原则是：在每个预测/回测事件时间点，
只能取当时已经可见的最新特征，不能取未来修订或未来抓取结果。Open Composer 应把这条原则
写进 factor evaluation：`visible_at <= signal_time`，并记录缺失 packet 如何处理。

### 5. Multiple-testing discount by default

MLFinLab、Lopez de Prado、White Reality Check 和 Hansen SPA 都指向同一问题：大量搜索后的最优
结果天然带有选择偏差。Quant/LLM 结合后，这个问题更严重，因为 LLM 会快速提出大量变体。

对 Open Composer 的含义：

- `TrialLedger.selection_bias_note` 是好的开始，但还不够。
- 参数搜索、因子搜索、LLM 变体搜索都应记录 trial count 和 search space。
- `research_pass` 应要求 OOS/walk-forward 和 DSR/PBO proxy warning。
- 只凭 IS 或 trial-only evidence 只能是 warning/blocked。

这里的实现不需要一开始就完整复现所有统计检验。更现实的 P0/P1 做法是先建立 proxy gate：

- 记录候选总数、有效候选数、被丢弃候选数、搜索空间来源。
- 当 trial count 超过阈值时，自动把 raw Sharpe 标为 selection-biased。
- 要求至少一个 untouched OOS 或 walk-forward fold 支撑最终选择。
- 如果只有最优结果、没有完整 trial ledger，则直接 blocked。
- 报告中同时显示 raw metric 和 selection-adjusted warning。

QuantConnect walk-forward optimization 文档还指出优化频率本身有 tradeoff：频繁优化能更贴近近期
市场，但也更容易过拟合；较低频率降低过拟合但反应更慢。因此 Open Composer 的 `SearchSpace`
和 `TrialLedger` 应记录 optimization schedule/frequency、training window、testing window 和
walk-forward selection rule，不能只记录最终参数。

### 6. Execution realism before paper readiness

QuantConnect Reality Modeling、NautilusTrader 和交易执行文献都说明：回测不是只计算价格信号，
还要考虑 fill、fee、slippage、market impact、capacity、order book/liquidity、settlement。

对 Open Composer 的含义：

- 现有 `execution_reality.py` 已有 dollar volume、bar participation、ADV participation、
  capacity curve、slippage stress。
- 下一步要把这些指标纳入 `promotion_report` 的硬 gate，而不是附属诊断。
- NautilusTrader adapter 应承担严肃 execution parity，in-repo Python engine 保持确定性参考。

NautilusTrader 的 backtesting/fill model 文档还提示：不同数据粒度下执行假设不同。L2/L3 order
book 可以用深度和 queue 模拟限价单；L1 或 bar/trade 数据只能用更粗的 slippage/fill probability
近似；是否启用 liquidity consumption 会影响同一档位流动性是否可被重复消耗。Open Composer
当前以 OHLCV deterministic engine 为参考时，必须在 `ExecutionManifest` 中明确“这是 bar-level
execution approximation”，并把需要 Nautilus parity 的策略标出来。

### 7. Financial LLM as researcher, not executor

FinGPT、FinRobot、TradingAgents、FinMCP-Bench、QuantCode-Bench、AlphaForgeBench 等材料显示：
金融 LLM 的可用方向是研究、特征生成、工具调用、策略代码生成和审查；直接输出交易动作会有
高方差、语义漂移和不可审计问题。

TradingAgents/FinRobot 这类多 agent 金融项目对角色拆分有参考价值，例如 analyst、researcher、
risk、trader 等角色。但 Open Composer 不应把“多个 agent 辩论后直接下单”作为产品路线；
它应把这些角色映射成 skill、review card、gate 和 agent request，而不是 broker action。

对 Open Composer 的含义：

- LLM 应作为 research assistant、feature proposer、event/news summarizer、review card writer。
- 如果 LLM 是 StrategyDAG 中的 node，必须 replay-only，并通过 packet/ablation/robustness。
- LLM 生成策略代码要通过语法、spec validation、backtest execution、trade presence、semantic alignment、
  risk gate，而不是靠文本“看起来合理”。

最新金融 LLM benchmark 还提供了更具体的验收顺序：

- QuantCode-Bench：先查语法，再查 backtest execution，再查是否产生交易，最后查自然语言描述、
  金融逻辑和策略行为是否一致。
- QuantEval：金融 LLM 评估不应只做知识问答，还要看数量推理和策略编码，并释放确定性回测配置。
- AlphaForgeBench：不让 LLM 连续发交易动作，而是让它生成可执行 alpha factor 和策略代码，再由
  deterministic backtester 评估，从而降低 action-level instability。
- FinMCP-Bench：金融 agent 要评估真实工具调用能力；工具选择、参数、调用顺序和结果处理都应被记录。

这与 Open Composer 当前定位高度一致：LLM 只生成/审查/解释 artifact，交易行为由 `StrategySpec`
和 deterministic engine/Nautilus adapter 复验。

这些 benchmark 多数仍是新近研究和评测集，不应被当作成熟生产产品照搬。它们的价值在于给
Open Composer 提供验收维度：可执行性、工具调用、金融语义、数量推理、行为一致性和风险约束。

因此 Open Composer 的 LLM eval 不应只问“这个策略解释是否合理”，而应分层：

- financial knowledge/reasoning：解释是否理解资产、成本、风险和数据限制。
- quantitative reasoning：指标计算、收益/风险/容量推导是否正确。
- strategy coding：生成的 StrategySpec/Python/Pine 是否可执行、语义一致、产生可解释信号。
- deterministic backtest：固定 universe、cost model、metric definitions 后是否可复验。

Alpha-GPT、LLMFactor、EvoAlpha、Hubble 等 alpha/factor discovery 方向还有一条更细的启发：
LLM 可以做搜索算子和解释器，但必须被 DSL/AST sandbox、公式相似度惩罚、family-aware selection、
RankIC/Pearson IC、多指标评分和持久 diagnostics artifact 约束。Open Composer 的几何/拓扑、
另类数据和 LLM 因子方向应沿着“研究沙盒 + 可执行 DSL + 因子诊断 + 多重试验折扣”推进。

FinRL/FinRL-Meta 的 data layer / environment layer / agent layer 分层也支持这个判断。即使未来
Open Composer 做 ML/RL，也应先把环境、reward、action space、train/test/trading period 和
market friction 写进 manifest；模型只能在 research-only sandbox 中产生候选，不直接获得
paper/live 执行权限。

RD-Agent 与 RD-Agent(Q) 对 Open Composer 更直接：它们把 data-driven R&D 做成 hypothesis、
experiment、feedback、knowledge/research loop，并在量化场景里覆盖 factor mining、model
innovation 和联合优化。Open Composer 应吸收这种循环，但保持更严格的金融安全边界：
`hypothesis -> bounded search -> experiment -> evidence -> critique -> next action`，每一步都
写 artifact 和 gate。

## 当前 Open Composer 的真实状态

### 已有控制点

| 控制点 | 当前文件/模块 | 评价 |
| --- | --- | --- |
| Agent 文本规则 | `AGENTS.md`、`CLAUDE.md`、`.agents/skills` | 规则很清晰，但还未完全机器可执行 |
| Skill mirror | `scripts/sync-agent-skills.py`、`scripts/check-agent-parity.py` | 已能防止 Claude/Codex skill 漂移 |
| Repo gate | `open_composer/repo_check.py` | 已覆盖 docs、skills、capabilities、dashboard commands |
| Research contract | `open_composer/research/contracts.py` | 已有 required checks、leakage、overfit、live gap requirements |
| Research kernel | `open_composer/research/kernel/*` | 已有 ResearchBrief、SearchSpace、CandidateSet、TrialLedger、GateSummary |
| Feature packet | `open_composer/feature_packets.py` | PIT 字段和 evidence 字段已存在 |
| StrategyDAG | `open_composer/research/strategy_dag.py` | LLM node replay-only 校验方向正确 |
| Execution reality | `open_composer/analytics/execution_reality.py` | 已有基础容量和流动性诊断 |
| Remote jobs | `open_composer/remote/jobs.py` | 已有 async job、backup、workspace lock、double confirmation |
| Agent requests | `open_composer/agent_requests.py` | 已支持 Dashboard/Vercel 把长任务交给本地/VPS agent |

### 主要缺口

1. 缺 `HarnessPolicyManifest`：文本规则没有编译成 policy-as-code。
2. 缺 `ResearchWorkflowHarness`：CLI 有很多研究命令，但没有一键编排。
3. 缺 `EvidenceManifest`：研究报告、trial、feature packet、benchmark、gate 还没有统一证据清单。
4. 缺 `AgentRunTrace`：Codex/Claude Code 执行任务没有结构化 trace artifact。
5. 缺 `PolicyAwareAgentRequest`：agent request 目前有 prompt 和 paths，但没有 required_skill、
   expected_artifacts、acceptance_gates。
6. 缺多重试验折扣 gate：已有 trial ledger，但 DSR/PBO proxy 还未统一进入 promotion。
7. 缺 LLM 策略生成验收闭环：还未把 QuantCode-Bench 式 syntax/backtest/trade/semantic alignment
   做成默认 gate。
8. 缺 Dashboard harness cockpit：Dashboard 可读证据，但还不能完整表达每个策略的 harness state。

## 建议目标架构

### 三层 harness

```text
Layer 1: Policy
  HarnessPolicyManifest
  SkillPolicyPack
  CapabilityPolicy
  RemoteActionPolicy

Layer 2: Workflow
  ResearchWorkflowHarness
  WorkflowPlan
  WorkflowStep
  StepResult
  AgentRunTrace
  EvidenceManifest

Layer 3: Surfaces
  CLI commands
  Dashboard cockpit
  reports/agent_requests
  repo/readiness/promotion gates
```

### 新增核心对象

| 对象 | 作用 |
| --- | --- |
| `HarnessPolicyManifest` | 把 AGENTS.md/skills/capabilities/remote rules 转成机器可读 policy |
| `SkillPolicyPack` | 每个 skill 声明负责范围、必需 artifact、禁止行为和验收 gate |
| `ResearchWorkflowHarness` | 编排 draft/validate/capability/backtest/factor/sweep/promotion/readiness |
| `EvidenceManifest` | 汇总一次研究 run 的所有输入、输出、数据、feature、trial、benchmark 和 gate |
| `AgentRunTrace` | 记录 Codex/Claude Code/LLM 工具使用、handoff、guardrail 和 artifact |
| `GateMatrix` | 展示 workflow/research/llm/paper/remote/security 各 gate 状态 |
| `NextActionPlan` | 把 blocker 转成下一步 CLI 命令或 agent request |

## 具体产品建议

### P0：Harness policy inventory

优先级最高，因为它把“强约束”落地为机器可读对象。

工作：

- 新增 `open_composer/harness/policies.py`。
- 新增 `policies/harness.yaml`。
- 为每个 skill 添加 policy metadata。
- 增加 `oc harness policy-list`、`oc harness check`。
- repo check 增加 policy manifest coverage。

Skill policy metadata 建议字段：

```yaml
skill_id: strategy-researcher
version: 1
allowed_tools:
  - oc.capability.list
  - oc.spec.validate
  - oc.strategy.parameter-sweep
required_artifacts:
  - research_brief
  - search_space
  - candidate_set
  - trial_ledger
forbidden_actions:
  - broker.live_write
  - direct_env_read
untrusted_inputs:
  - web
  - mcp
  - filings
  - news
acceptance_gates:
  - workflow_pass
  - research_pass
source_rules:
  - AGENTS.md
```

OWASP Agentic Skills guidance 对应的安全目标是：每个 skill 都有最小权限、输入 schema、输出 schema、
provenance、版本和 drift check。

验收：

- 缺 paper/LLM/remote/data/execution policy 时 `oc repo check --strict` blocked。
- skill 文本和 policy pack 漂移时 blocked。

### P1：One-command research workflow

工作：

- 新增 `oc strategy research-workflow <spec>`。
- 新增 `oc strategy create-and-research --idea "..."`。
- 自动执行 spec validate、capability evaluate、reference backtest、factor lab、parameter sweep、
  research report、promotion report、alt-data quality、DAG validation、paper readiness summary。
- 写 `EvidenceManifest` 和 `DecisionCard`。

验收：

- 用户不提示防过拟合、未来函数、成本、容量，workflow 也默认检查。
- 缺 OOS/walk-forward/cost/benchmark/feature packet 时 blocked。

实现形态建议参考 LangGraph checkpoints、CrewAI Flows persistence 和 LlamaIndex Workflows：
`ResearchWorkflowHarness` 应是 step/event 状态机，而不是一个长函数。每个 step 写入
`StepResult`，失败时可以 resume，不重跑已完成步骤。

建议 step：

1. `spec.validate`
2. `capability.evaluate`
3. `research_brief.build`
4. `search_space.infer`
5. `reference_backtest.run`
6. `factor_lab.run`
7. `candidate_set.build`
8. `trial_ledger.run`
9. `alt_data_quality.check`
10. `strategy_dag.validate`
11. `promotion_report.run`
12. `paper_readiness.summarize`
13. `evidence_manifest.write`
14. `decision_card.write`

每个 step 必须声明 inputs、outputs、policy_ids、can_resume、blocking_gates。

### P2：Agent request contract

工作：

- 扩展 `AgentRequest`：
  - `required_skill`
  - `expected_artifacts`
  - `acceptance_gates`
  - `source_policy_ids`
  - `risk_level`
- Codex/Claude Code 完成 request 后，必须附 result links。
- `oc agent request-complete` 校验 expected artifacts 存在。

验收：

- Dashboard 创建的 request 不只是 prompt，而是结构化任务合同。
- 自然语言“完成了”不能关闭 request。

### P3：Dashboard harness cockpit

工作：

- Strategy card 显示 latest `GateMatrix`。
- Research tab 显示 `EvidenceManifest`。
- Agent tab 显示 open/in-progress/completed requests 和 trace。
- Blocker tab 显示 next action。
- Remote tab 显示 job、backup、audit、double confirmation 状态。

验收：

- 用户打开 Dashboard 就能看到“为什么不能 paper ready”。
- Vercel 仍不执行长任务，只发 request。

当前 Dashboard 已有 `DashboardResearchReport`、`DashboardResearchRun`、`next_action`、
`evidence_strength`、`gate_summary`、`paper_readiness_status`、`llm_contribution_status`
和 Research Evidence 表。因此 P3 不是重写 Dashboard，而是扩展读取字段：

- `evidence_manifest_path`
- `gate_matrix`
- `agent_trace_paths`
- `policy_ids`
- `dataset_manifest_path`
- `execution_manifest_path`
- `next_action_plan`

这能保持 Dashboard 仍是 read model，同时把它从“报告列表”升级为 harness cockpit。

Model Cards 和 Datasheets for Datasets 对 Dashboard 也有启发：Strategy/Decision Card 不应只
展示收益指标，而应展示 intended use、not intended use、data provenance、known limitations、
validation coverage、risk warnings 和 promotion status。Open Composer 的 DecisionCard 应成为
策略的“模型卡/数据卡/证据卡”的合体。

### P4：LLM/financial-agent evaluation gates

工作：

- 引入 LLM-generated strategy gate：
  - spec validation
  - code/Pine generation validation
  - deterministic backtest execution
  - at least one trade or explicit no-trade reason
  - semantic alignment against StrategySpec
  - risk/cost/execution gate
- 引入 MCP/tool-use gate：
  - tool call trace
  - source/capability id
  - untrusted input boundary
  - output artifact schema

验收：

- LLM 策略生成不再以文本合理性作为验收。
- 金融工具调用错误不会进入 strategy evidence。

### P5：Agent evaluation and review cards

AgentBench、ToolBench、SWE-bench Verified、PaperBench 等评估材料说明：agent 的评价应以环境任务
完成、工具调用、patch/test、artifact 质量和可复验结果为主。LLM-as-judge 可以辅助解释，
但不能替代确定性 gate。

OpenAI trace grading、LangSmith/Phoenix agent eval、OpenTelemetry GenAI spans 的共同方向是：
prompt eval 不足以评估会采取行动的 agent；应做 trace-level eval。Open Composer 的 agent
eval 应检查：

- 轨迹是否走了正确 skill。
- 工具调用是否来自允许 capability。
- retry 是否改变了状态或输入。
- step 是否引用了未信任来源。
- approval decision 是否和风险级别匹配。
- 最终 artifact 是否通过 deterministic verifier。

工作：

- 增加 `AgentEvalDataset`：从历史 agent request、blocked gate、successful artifact 中抽样。
- 增加 `oc harness eval-agent-runs`：评估 agent 是否按 policy 生成 expected artifacts。
- Review card 增加“LLM review is advisory”标记和 artifact links。
- 把 agent 失败模式记录为分类：
  - missing artifact
  - wrong tool/source
  - untrusted input followed as instruction
  - future data leakage
  - no test run
  - natural-language-only completion

验收：

- 任何 agent request 不能只凭 LLM 评语关闭。
- Agent 质量评估使用 artifact/test/gate 为主，LLM review 为辅。

### P6：MCP/tool security boundary

MCP 官方 security best practices、OWASP LLM Top 10、OWASP Agentic Skills Top 10 和 MCP tool
poisoning 研究共同说明：外部工具描述、外部文档、MCP server、news、filings、网页内容都可能
成为间接 prompt injection 或 tool poisoning 的载体。Open Composer 现有 AGENTS.md 已要求
把外部 docs/MCP/news/filings/LLM text 当作 untrusted reader input，这个方向需要产品化。

工作：

- `AgentRunTrace` 记录每个外部 source/tool 的 identity、capability id、权限范围和输出 schema。
- MCP/tool 输出只能进入结构化 artifact，不允许直接作为 strategy writer 指令。
- `EvidenceManifest` 标注每个 artifact 的 trusted/untrusted boundary。
- `HarnessPolicyManifest` 增加 least-privilege tool policy。
- Dashboard 对外部来源证据显示 source、timestamp、hash、capability id 和风险标签。

验收：

- 任一外部 tool/source 不能直接触发 file write、paper order 或 dashboard command。
- 未登记 capability id 的外部工具输出不能进入 research/promotion evidence。
- agent request 如果引用外部来源，必须有 untrusted-reader boundary 记录。

### P7：Dataset and execution manifests

Feast、DVC、Great Expectations、QuantConnect Reality Modeling、NautilusTrader 和市场冲击文献
共同说明：策略证据不仅是 signals 和 returns，还包括数据版本、PIT 状态、复权/公司行动、
流动性、容量和执行假设。

工作：

- 新增 `DatasetManifest`：
  - provider/feed
  - timeframe
  - symbol/universe
  - start/end
  - row count
  - adjustment policy
  - corporate action policy
  - signal price policy
  - execution price policy
  - cache/fallback/sample/trial marker
  - fetched_at/hash
- 新增 `ExecutionManifest`：
  - fill assumption
  - commission/slippage/impact model
  - fee model status
  - buying power model status
  - settlement model status
  - order validation/brokerage model status
  - bar participation
  - ADV participation
  - capacity curve
  - liquidity warnings
  - Nautilus parity status
- `EvidenceManifest` 引用两者。

验收：

- 没有 DatasetManifest 的 run 不能 research_pass。
- 没有 ExecutionManifest 的 run 不能 paper_ready_pass。
- sample/fallback/trial data 在 manifest 中自动阻断 paper readiness。

QuantConnect 的 data normalization/corporate actions 文档和 Alpaca/Polygon 等市场数据文档还提示
一个常见错误：信号计算可能需要复权连续价格，但实际执行和持仓调整发生在 raw/corporate-action
event 语义下。因此 DatasetManifest 应明确区分：

- signal price policy：用于计算指标/因子的价格如何复权。
- execution price policy：用于成交、滑点、仓位和现金流的价格/事件如何处理。
- corporate-action event policy：split、dividend、symbol change、delisting 是否作为事件重放。

这能减少“回测漂亮但实盘错位”的问题。

## 本地模块落点

| 建议对象 | 优先落点 | 复用现有模块 |
| --- | --- | --- |
| `HarnessPolicyManifest` | `open_composer/harness/policies.py`、`policies/harness.yaml` | `repo_check.py`、AGENTS/skills |
| `SkillPolicyPack` | `.agents/skills/*/policy.yaml` 或 SKILL front matter | `scripts/sync-agent-skills.py`、`check-agent-parity.py` |
| `ResearchWorkflowHarness` | `open_composer/harness/workflow.py` | `research_report.py`、`promotion.py`、`parameter_sweep.py` |
| `EvidenceManifest` | `open_composer/harness/evidence.py` | `ResearchArtifactWriter`、`ResearchRunIndexRecord` |
| `AgentRunTrace` | `open_composer/harness/trace.py` | `agent_requests.py`、remote jobs、dashboard commands |
| `GateMatrix` | `open_composer/harness/gates.py` | `ResearchGateSummary`、`paper_readiness.py` |
| `NextActionPlan` | `open_composer/harness/actions.py` | Dashboard command plans、agent requests |
| `LLMStrategyEval` | `open_composer/harness/llm_eval.py` | spec validate、backtest、Pine export、review cards |

## DataQualityExpectation

Great Expectations 和 Evidently 的价值不在于 Open Composer 立刻引入重型依赖，而在于把数据质量
检查产品化。建议轻量实现：

- required columns: `timestamp/open/high/low/close/volume`
- monotonic timestamp
- duplicate timestamp count
- null/zero/negative price checks
- volume missing/zero checks
- timezone status
- market-hours coverage
- split/dividend/corporate-action gaps
- provider/cache/fallback/sample marker
- data drift warning against previous run

这些 expectation 应写入 `DatasetManifest`，并被 `EvidenceManifest` 引用。

## EvaluationBundle 指标分组

Alphalens、Pyfolio、Empyrical、QuantConnect 和 Open Composer 现有 analytics 模块共同说明：
策略评估不能只看 Sharpe。建议未来 `EvaluationBundle` 至少分组记录：

| 分组 | 指标/证据 |
| --- | --- |
| Returns | total return、annualized return、monthly/rolling return、benchmark alpha |
| Risk | max drawdown、volatility、downside deviation、tail loss、exposure |
| Risk-adjusted | Sharpe、Sortino、Calmar、alpha/beta、information ratio |
| Trade behavior | signal count、trade count、win/loss、holding period、turnover |
| Factor | rank IC、rolling IC、forward returns、quantile spread、factor turnover、correlation |
| Execution | slippage stress、bar/ADV participation、capacity curve、liquidity warnings |
| Robustness | OOS、walk-forward、cost grid、blind test、regime sensitivity |
| LLM/alt data | PIT status、baseline、marginal lift、missing-modality robustness、node ablation |
| Evidence | dataset manifest、feature packet manifest、trial ledger、benchmark family、gate matrix |

Dashboard 应默认展示分组状态和 blockers，而不是把所有指标平铺。

## 差距优先级

| 优先级 | 差距 | 为什么现在做 |
| --- | --- | --- |
| P0 | Policy-as-code | 没有机器可读 policy，强规则仍依赖 agent 自觉 |
| P0 | EvidenceManifest | 没有统一证据清单，Dashboard 和 gate 难以一致 |
| P1 | ResearchWorkflowHarness | 命令分散，用户仍需知道专业流程 |
| P1 | PolicyAwareAgentRequest | Dashboard request 仍像 prompt，不像任务合同 |
| P2 | Multiple-testing gate | LLM 会放大搜索空间，必须默认折扣 |
| P2 | LLM strategy eval gate | 策略生成不能只靠文本审查 |
| P3 | Dashboard cockpit | UI 需要展示证据链和 blocker，而不是只是报告列表 |
| P3 | AgentRunTrace | 后续 agent 质量评估和 debug 需要 trace |

## 默认强约束清单

这些约束应由产品默认执行，而不是靠用户 prompt。

- 策略必须先 draft，再 validate。
- 可调参数必须生成 bounded search space。
- 优化必须有 CandidateSet、TrialLedger、SelectionDecision。
- 研究 run 必须有 EvidenceManifest。
- 回测必须有 report。
- promotion 必须有 OOS/walk-forward/cost/benchmark/execution/data checks。
- LLM/另类数据必须有 point-in-time feature packet。
- LLM contribution 必须有 pure quant baseline、marginal lift、missing-modality robustness。
- sample/fixture/fallback/trial-only data 不能 paper ready。
- paper_auto 仍需 explicit command confirmation。
- real-money broker write access 继续 out of scope。
- Dashboard/Vercel 不执行长任务。
- external docs/MCP/news/filings/LLM text 均视为 untrusted reader input。

## 不建议做的事

- 不直接把 Open Composer 改成 LangGraph/AutoGen/CrewAI 项目；可以吸收模式，但不引入复杂依赖。
- 不引入完整 MLflow/W&B/DVC/Feast 栈；先做文件型 manifest 和 lineage。
- 不复制 QuantConnect/LEAN；继续 Python deterministic engine + NautilusTrader adapter。
- 不让 LLM 直接参与 live/paper order 决策；LLM 先做 research/review/feature packet。
- 不把几何/拓扑/物理类特征直接宣传成 Alpha；继续 research-only sandbox。
- 不把机构级金融 agent 平台的合规/多租户/云审计复杂度搬进 MVP；个人 workbench 先保留
  file-first、本地证据和明确 gate。

## 下一步实施顺序

1. `HarnessPolicyManifest` + `oc harness check`。
2. `EvidenceManifest` + research report writer 统一写入。
3. `oc strategy research-workflow <spec>`。
4. `AgentRequest` 增加 expected artifacts / gates。
5. Dashboard 增加 GateMatrix/Manifest/NextAction。
6. DSR/PBO proxy 和 multiple-testing discount gate。
7. LLM generated strategy gate 和 MCP tool-use trace。

这个顺序的理由是：先有 policy 和 evidence，再谈自动化；先能阻断错误晋升，再提升 Dashboard
和 LLM 体验。

## 参考链接

### Agent / coding / research agent

- OpenAI Agents SDK docs: https://developers.openai.com/api/docs/guides/agents
- OpenAI Agents SDK tracing: https://developers.openai.com/api/docs/guides/agents/integrations-observability#tracing
- LangGraph docs: https://docs.langchain.com/oss/python/langgraph/overview
- AutoGen docs: https://microsoft.github.io/autogen/stable/
- CrewAI Flows docs: https://docs.crewai.com/concepts/flows
- Semantic Kernel docs: https://learn.microsoft.com/semantic-kernel/
- LlamaIndex Workflows docs: https://docs.llamaindex.ai/
- SWE-agent paper: https://arxiv.org/abs/2405.15793
- SWE-bench Verified: https://www.swebench.com/
- OpenHands docs: https://docs.all-hands.dev/
- PaperBench: https://openai.com/index/paperbench/
- AI Scientist: https://arxiv.org/abs/2408.06292
- Agent Laboratory: https://arxiv.org/abs/2501.04227

### Quant / execution / experiment systems

- QuantConnect Algorithm Framework: https://www.quantconnect.com/docs/v1/algorithm-framework/overview
- QuantConnect Reality Modeling: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts
- NautilusTrader backtesting: https://nautilustrader.io/docs/latest/concepts/backtesting/
- MLflow Tracking: https://mlflow.org/docs/latest/ml/tracking/
- Qlib Recorder: https://qlib.readthedocs.io/en/stable/component/recorder.html
- DVC docs: https://dvc.org/doc
- Feast docs: https://docs.feast.dev/
- Great Expectations docs: https://docs.greatexpectations.io/
- Alphalens docs: https://alphalens.ml4trading.io/

### Financial ML / AI + quant / risk

- FinRL paper: https://arxiv.org/abs/2011.09607
- FinGPT paper: https://arxiv.org/abs/2306.06031
- RD-Agent: https://github.com/microsoft/RD-Agent
- RD-Agent paper: https://arxiv.org/abs/2505.14738
- RD-Agent(Q) paper: https://arxiv.org/abs/2505.15155
- TradingAgents paper: https://arxiv.org/abs/2412.20138
- Alpha-GPT paper: https://arxiv.org/abs/2308.00016
- LLMFactor paper: https://arxiv.org/abs/2406.10811
- Deflated Sharpe Ratio: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
- Probability of Backtest Overfitting: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
- OWASP Top 10 for LLM Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- OpenTelemetry traces: https://opentelemetry.io/docs/concepts/signals/traces/
