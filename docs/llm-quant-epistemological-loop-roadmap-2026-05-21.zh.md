# Open Composer — 认识论闭环引擎调研报告与路线图

**日期**: 2026-05-21
**前置文档**: `docs/skill-first-harness-engineering-roadmap-2026-05-20.zh.md`（P0–P6 路线图，已实施）
**关键词**: epistemological loop, hypothesis registry, experiment DAG, regime decomposition, LLM memory packet

---

## 0. 摘要（TL;DR）

P0–P6 已经把 Open Composer 建成一个**优秀的防御性系统**——它能阻止坏策略进入执行。但它**还不是一个进攻性系统**——它不能让后一个策略比前一个聪明，不能让 LLM 跨 session 积累领域知识。

用户反馈的"Codex 在长 session 中压缩上下文后重新规划、低效循环"只是**表象**。本质问题是：

> **Open Composer 当前架构是一条单向流水线（LLM 生成 → 门控 → 执行），缺少一个把回测、信号、执行偏差等反馈结构化地回流到下一次 LLM 生成上下文的闭环。LLM 每次生成都从相似的基础认知出发，而不是从已积累的实验教训出发。**

因此前一轮提出的"加一份 journal.jsonl + plan.yaml"是治标不治本——它只在 prompt 层缓和遗忘，不解决知识积累问题。本文给出基于 Harness Engineering 哲学（gate + artifact + skill）的**结构性方案**：把"假设、实验血统、制度上下文、提示溯源"统一升级为一等制品（first-class artifacts），由 gate 强制、由 skill 消费、由 CLI 暴露。这才是产品架构层面的修复。

本文给出：
- 调研：LLM 在量化研究的真实优势、结构性弱点、顶级机构的工作模式
- 架构分析：P0–P6 已覆盖什么、缺什么、为什么前述 P7–P9 方案不够
- 6 项结构性建议（按优先级排序）
- P7–P10 路线图（每阶段含制品、gate、skill、CLI、测试）

---

## 第一部分 — 调研

### 1.1 LLM 在量化研究中的**真实**优势

以下是有研究证据的优势，非营销话术：

**(a) 假设空间扩展（Hypothesis Generation at Scale）**
Alpha-GPT 在 WorldQuant 国际量化竞赛中从 4.1 万支队伍跻身前 10。其核心优势不是 alpha 本身的质量，而是**生成候选 alpha 的速度和多样性**——数分钟内提出几十个基于不同微观结构理论的候选信号，是人类研究员工作量的几十倍。
来源：[Alpha-GPT (arXiv:2308.00016)](https://arxiv.org/abs/2308.00016), [Alpha-GPT 2.0 (arXiv:2402.09746)](https://arxiv.org/abs/2402.09746)

**(b) 跨模态信息整合**
LLM 能把新闻情绪、宏观叙事、事件文本与价格结构组合为 feature packet。GPT-4 已被证明能分析表格结构数据并生成对收益有意义预测的金融信号。
来源：[GPT-Signal (arXiv:2410.18448)](https://arxiv.org/pdf/2410.18448)

**(c) 代码生成 + 迭代反馈**
多智能体代码生成（分析师 → 编码 → 测试）+ 静态分析反馈循环，能把非功能性质量问题（安全漏洞 40%→13%，可靠性警告 50%→11%）大幅压缩。
来源：[LLMLOOP (arXiv:2603.23613)](https://arxiv.org/pdf/2603.23613), [Static Analysis Feedback Loop (arXiv:2508.14419)](https://arxiv.org/pdf/2508.14419)

**(d) 自然语言 → 规范的翻译**
把人类直觉翻译为 `StrategySpec`，是 LLM 对量化领域最可靠的贡献之一。Open Composer 的 `strategy-designer` 技能已经在这层。

### 1.2 LLM 在量化研究中的**结构性**弱点

这些弱点是结构性的，**不能通过 prompt 工程解决**：

**(a) 回测数据污染（Backtest Data Contamination）**
LLM 训练数据包含大量已发表的回测、新闻、价格分析。模型天然倾向于"在已知的历史牛市时段表现好"，因为它"见过"这段历史。这比传统过拟合更危险，因为**用户无法分辨 LLM 是在推理还是在记忆**。
来源：[Evaluating LLMs in Finance Requires Explicit Bias Consideration (arXiv:2602.14233)](https://arxiv.org/html/2602.14233v1)

**(b) 高风险领域的幻觉传播**
强制不弃权的训练让 LLM 在知识边界外仍高置信度猜测。金融表格数据中的幻觉会传播到自动化系统，导致误导性分析和有缺陷的策略。
来源：[FAITH: Tabular Hallucinations in Finance (arXiv:2508.05201)](https://arxiv.org/pdf/2508.05201)

**(c) 无法进行真正的数学推理**
LLM 不能可靠验证定价公式、推导风险模型正确性、进行非平凡的统计推断。
来源：[LLM Limitations Survey (arXiv:2505.19240)](https://arxiv.org/pdf/2505.19240)

**(d) 无状态生成：不记得自己失败过**
LLM 没有长期记忆。每次对话启动时，它不知道上次生成的策略为什么失败。这是所有 "LLM + 策略生成" 产品面临的最根本的工程问题。

**(e) 迭代无保护的安全退化**
IEEE-ISTAS 2025 收录的研究发现：**没有人类干预的自动化迭代 LLM 反馈循环，与新漏洞的引入正相关**。每次迭代修复某些问题，同时可能引入新问题。在策略代码中表现为：回测修复了一个信号 bug，但同时引入了前视偏差。
来源：[Security Degradation in Iterative AI Code Generation (arXiv:2506.11022)](https://arxiv.org/html/2506.11022)

### 1.3 顶级量化机构的工作模式给我们的启示

参考 Renaissance Technologies、AQR、Man Group 的公开研究方法论：

1. **任何信号都必须通过严格统计检验，多数被丢弃**（Renaissance）。隐含要求：必须显式追踪"我们检验了什么假设，结论是什么"，否则无法管理多重检验。
2. **因子在不同制度下的行为分析是核心**（AQR、Man Group）。好的问题不是"这个策略好不好"，而是"在哪种制度下好，在哪种制度下失效，失效是模型问题还是假设问题"。
3. **Human-in-the-Loop 不是审批，而是关键分叉点的明确判断**（Alpha-GPT 2.0、DSMentor）。这些判断必须被记录并成为未来 LLM 上下文。
   来源：[DSMentor (arXiv:2505.14163)](https://arxiv.org/pdf/2505.14163)
4. **自进化课程（Self-Evolving Curriculum）把课程选择建模为非平稳多臂老虎机**。完全可以应用到量化策略的参数搜索：哪些方向历史上更有价值，应该优先继续探索。
   来源：[Self-Evolving Curriculum (arXiv:2505.14970)](https://arxiv.org/abs/2505.14970)

### 1.4 竞争格局

| 产品 | 核心定位 | 短板 |
|---|---|---|
| **QuantConnect**（MCP server + "Mia"） | 平台工具：加速实现想法 | 不帮用户判断"想法是否值得实现"，不积累跨策略知识 |
| **Numerai Signals** | 排行榜激励 + 信号汇聚（外部化质量控制） | 个人无法独立运行；信号被市场化 |
| **Alpha-GPT** | Human-in-the-Loop 学术系统 | 不处理执行现实、PIT 特征包等工程问题 |
| **Open Composer**（你） | **防御性门控 + 进攻性知识积累**（待建） | 进攻性知识积累尚未建成 |

**结论**：Open Composer 的差异化机会是把"防御性门控"（已有）和"进攻性知识积累"（待建）结合在一起的**个人量化研究引擎**——这个组合在现有竞争格局中是空白。

---

## 第二部分 — 架构分析

### 2.1 P0–P6 已覆盖什么（不能低估）

| 架构需求 | Open Composer 已有覆盖 | 强度 |
|---|---|---|
| 防止幻觉传播到执行 | PIT 特征包、`source_cards`、`pit_replay_evidence` | 强 |
| 防止回测污染 | `backtest_forensics`、`lookahead_check`、`future_leak_check` | 强 |
| 多重检验记录 | `trial_ledger`、`bounded_search_space` | 中（记录了，**未主动利用**） |
| 执行现实核查 | `execution_policy`、`execution_reality_report`、`gap_stress_report` | 强 |
| LLM 信号独立性验证 | `marginal_lift_report`、`missing_modality_robustness_report` | 中（要求存在，**未自动生成**） |
| 假设显式注册 | **无** | 缺失 |
| 实验血统链 | **无**（`trial_ledger` 是平的，无父子关系） | 缺失 |
| 反馈回流到 LLM 上下文 | **无** | 缺失 |
| 制度感知的失败分析 | **无** | 缺失 |
| 自适应搜索优先级 | **无** | 缺失 |

### 2.2 缺失的闭环

```
当前架构（单向流水线）：
  LLM 生成 → 门控验证 → 执行 → 报告
                                  └── 终点，反馈不回流

目标架构（认识论闭环引擎）：
  假设注册表 ←─────────────────────────────────────┐
       ↓                                             │
  LLM 生成（带记忆包 + 否定假设列表 + 已弃参数）       │
       ↓                                             │
  门控验证（含制度分解、提示溯源）                     │
       ↓                                             │
  执行                                                │
       ↓                                             │
  报告（按制度分解的指标 + 假设验证状态）              │
       ↓                                             │
  实验 DAG 更新 → 假设状态更新 → 记忆包再生成 ─────────┘
```

**关键原则**：每一轮循环结束，系统对市场的理解应该**比上一轮更精确**——不是更多策略，而是**更少的无效假设空间**。

### 2.3 为什么前述 P7–P9（journal + plan-of-record）不够

前一轮我提出的"加一份 journal.jsonl + plan.yaml + turn-protocol"方案，**只在 prompt 层缓和遗忘问题**——它假定"模型只要看到上次做了什么，就能正确推进"。但这个假设错了：

1. 模型即使看到 journal，也无法**结构化推理**："这次失败是因为假设错了，还是参数错了，还是执行错了"——因为没有假设层。
2. journal 是叙述性的，**不可被多重检验统计校正消费**——模型不知道自己已经在同一假设下检验过 50 次，不知道剩余的显著性预算。
3. journal 没有制度上下文——模型无法知道某次成功是因为正确还是因为运气好（碰上对的市场制度）。

修复方法不是"更好的 journal"，而是**把假设、血统、制度、预算变成结构化制品**，让 gate 强制、让 skill 消费。这才是 Harness Engineering 哲学下的正确做法。

---

## 第三部分 — 6 项核心架构建议

按优先级排序。每条都是**结构性**改进（新制品 + gate 改造 + skill 改造），不是日志或 prompt 调整。

### 建议 1：假设注册表（Hypothesis Registry）— 最高优先级

**新增制品**：`reports/research/{strategy}-hypothesis-registry.json`

```yaml
strategy_name: qqq_pullback_15m
hypotheses:
  - hypothesis_id: H001
    statement: "QQQ 15 分钟 RSI 极端值后的回归提供 1-3 根 bar 的均值回归 alpha"
    assumed_regime: ["low_volatility", "trending_up"]
    falsification_criteria:
      - "高波动制度下命中率 < 0.5"
      - "信号在样本外 OOS Sharpe < 0.3"
    evidence_status: unverified  # unverified | supporting | contradicting | rejected
    rejected_by: null
    introduced_in_trial: t_001
```

**注册到** `harness/artifact_contracts.yaml`，**强制于** `backtest-forensics` gate：
若 `evidence_status == contradicting`，必须提供 `continuation_justification`。

**为什么这是架构问题**：它**改变了 LLM 下次被调用时的 prompt 上下文**——`strategy-designer` 必须把"已否定的假设列表"注入系统提示，使 LLM 无法在相同条件下重复同样的假设。这直接解决 1.2(d) 的无状态生成问题，且零模型微调成本。

### 建议 2：实验 DAG（Experiment Lineage）

**现状**：`trial_ledger` 是平面列表。
**改造**：增加 `parent_trial_id` 和 `mutation_description` 字段，让 trials 形成 DAG。

```yaml
trials:
  - trial_id: t_003
    parent_trial_id: t_001
    mutation_description: "lookback 14 → 21"
    hypothesis_id: H001
    result: { sharpe: 0.42, hit_rate: 0.51, sample_size: 312 }
    outcome_class: marginal_improvement
```

**支持的查询**：
- "从 H001 出发，尝试了多少变体，哪些提升、哪些退步？"
- "v5 比 v3 好，是因为参数变还是逻辑变？"

**新 skill 行为**：`strategy-research-orchestrator` 在生成新 trial 前**必读 DAG**，提炼"最有价值的探索方向"。

### 建议 3：制度分解（Regime Decomposition）— 防过拟合的核心工具

**新增制品**：`reports/research/{strategy}-regime-decomposition.json`

对以下制度分别报告 Sharpe / 命中率 / 平均收益 / 样本数：
- **趋势制度**：200 日均线 above/below + VIX 分位
- **波动率制度**：高/低 VIX（历史中位数为界）
- **流动性制度**：成交量百分位

**改造** `backtest-forensics` 的 `overfit_risk` 评估：若策略在某一制度下 Sharpe 是其他制度的 2× 以上，自动触发 `regime_arb_warning`。

**为什么是核心工具**：把"策略整体失效"分解为"假设在特定制度下失效"，是顶级量化机构的标准做法（参考 1.3.2），也是比目前 forensics 更有力的过拟合检测器。

### 建议 4：LLM 记忆包（Context Memory Packet）

**新增制品**：`reports/harness/llm-memory/{strategy}-memory-packet.json`

由 `strategy-research-orchestrator` 在每次研究循环结束时生成，**格式专门设计为可直接插入 LLM 系统提示**：

```yaml
strategy_name: qqq_pullback_15m
generated_at: 2026-05-21
last_n_trials_summary:
  - { trial_id: t_005, outcome: rejected, reason: "OOS Sharpe < threshold in high_vol regime" }
  - { trial_id: t_004, outcome: rejected, reason: "lookahead in cross_section feature" }
rejected_hypotheses: [H002, H004]
abandoned_parameter_directions:
  - "lookback > 30 (degrades with stationarity loss)"
  - "threshold < 0.1 (false signal rate too high)"
top_features_so_far:
  - { feature_id: f_pullback_rsi_v2, marginal_sharpe_lift: 0.18 }
recommended_next_directions:
  - "regime-conditioned execution timing"
  - "cross-asset confirmation via SPY"
```

**改造** `strategy-designer` skill：被调用前**必须读** memory packet 并注入系统提示。

**为什么解决无状态生成**：LLM 的"记忆"在工程上不必是模型权重——可以是**结构化的外部上下文**。Anthropic 在《Building Effective Agents》中明确推荐这种模式。
来源：[Building Effective AI Agents — Anthropic](https://www.anthropic.com/research/building-effective-agents)

### 建议 5：多重检验预算（Multiple Testing Budget）

**改造** `bounded_search_space` 制品：

```yaml
testing_budget:
  planned_trials: 50
  alpha_target: 0.05
  adjusted_alpha: 0.001  # Bonferroni 校正后
  consumed_trials: 35    # 自动从 trial_ledger 统计
  remaining_budget: 15
  exhaustion_action: require_oos_validation_before_continue
```

**改造** `backtest-forensics`：当 `consumed_trials / planned_trials > 0.7` 时，自动把 `overfit_risk` 标 `high`，要求 OOS 验证才能继续。

**为什么现在的 trial_ledger 不够**：它记录了次数，但**没有把次数转化为对显著性水平的实时约束**。LLM 可能在不知道预算耗尽的情况下继续提新参数组合。

### 建议 6：自适应搜索优先级（Adaptive Search Priority）

**改造** `strategy-research-orchestrator`：从 `trial_ledger` 计算每个参数维度的**历史边际贡献**，下次搜索时优先扩展贡献最高的维度，减少已知无效维度的搜索。

不需要真正的 RL 实现——简单加权随机采样即可。每次选 trial 时生成 `search_rationale` 字段说明理由（"已尝试 8 个 lookback 变体均无显著提升，转向 threshold 维度"）。

理论基础：[Self-Evolving Curriculum (arXiv:2505.14970)](https://arxiv.org/abs/2505.14970) 的多臂老虎机课程选择。

### 建议 7（次优先）：生成可重现性追踪（Generation Provenance）

**新增制品**：`reports/harness/provenance/{strategy}-generation-provenance.json`

记录每次 LLM 调用的：`prompt_template_version`、`context_hash`、`model_id`、`temperature`、`seed`。

**为什么重要**：没有提示版本化，你无法判断 v4 比 v3 好是因为**策略逻辑改了**还是因为**提示词改了**。现有架构已对 feature_packet 做了 `prompt_hash` 追踪，把这套扩展到策略生成本身即可。

---

## 第四部分 — 路线图（P7–P10）

每个阶段：**新增制品** + **修改 gate** + **修改 skill** + **新 CLI** + **测试**。命名延续 P0–P6 的 P 序号。

### P7 — 假设层 + LLM 记忆包（建议 1 + 4）

**为什么先做这两个**：它们直接闭环 LLM 的"无状态生成"和"假设盲目重复"两个最大结构性弱点，且改动量最小、回报最高。

**新制品**:
- `reports/research/{strategy}-hypothesis-registry.json`
- `reports/harness/llm-memory/{strategy}-memory-packet.json`

**Pydantic 模型**:
- `open_composer/models/hypothesis.py`：`Hypothesis`, `HypothesisRegistry`, `EvidenceStatus` enum
- `open_composer/models/memory_packet.py`：`MemoryPacket`

**Gate 改造**:
- `backtest_forensics` gate：检查 `evidence_status == contradicting` 时要求 `continuation_justification`
- 新 gate `hypothesis_consistency`：检查每个 trial 关联到至少一个 hypothesis_id

**Skill 改造**:
- `strategy-designer/SKILL.md`：在 SKILL prompt 中明文要求"被调用前先读 memory_packet 并把已 rejected 的假设排除"
- `strategy-research-orchestrator/SKILL.md`：在循环末尾生成新版 memory_packet
- `backtest-forensics/SKILL.md`：把假设验证状态写回 registry

**新 CLI**:
- `oc research hypothesis add <strategy> --statement ... --regime ...`
- `oc research hypothesis list <strategy>`
- `oc research memory show <strategy>`（输出可粘贴的 prompt 上下文）
- `oc research memory regenerate <strategy>`

**测试**:
- `tests/test_hypothesis_registry.py`
- `tests/test_memory_packet.py`
- `tests/test_strategy_designer_consumes_memory.py`（端到端：模拟 designer 调用，验证 prompt 含 memory packet）

### P8 — 实验 DAG + 多重检验预算（建议 2 + 5）

**为什么放一起**：两者都改 `trial_ledger`，一次改造更经济。

**Schema 改造**:
- `trial_ledger`：新增 `parent_trial_id`、`mutation_description`、`hypothesis_id`、`outcome_class`
- `bounded_search_space`：新增 `testing_budget` 子结构

**Gate 改造**:
- `backtest_forensics`：消费 `testing_budget`，预算耗尽时升级 `overfit_risk`
- 新 gate `experiment_lineage`：每个新 trial 必须声明 `parent_trial_id`（除根 trial）

**Skill 改造**:
- `strategy-research-orchestrator`：选下一 trial 前读 DAG，输出 `search_rationale`
- `weekly-reviewer`：渲染 DAG 为 Markdown 树（人类可读）

**新 CLI**:
- `oc research trials tree <strategy>`（ASCII 树渲染 DAG）
- `oc research budget show <strategy>`（显示剩余预算和触发条件）
- `oc research budget set <strategy> --planned-trials 50 --alpha 0.05`

**测试**:
- `tests/test_trial_dag.py`
- `tests/test_testing_budget.py`
- `tests/test_overfit_risk_escalation.py`

### P9 — 制度分解 + 自适应搜索（建议 3 + 6）

**为什么放一起**：制度分解为自适应搜索提供条件分桶信号。

**新制品**:
- `reports/research/{strategy}-regime-decomposition.json`
- `reports/research/{strategy}-search-priority.json`（自适应搜索内部状态）

**Capability 改造**:
- `capabilities/registry.yaml`：把 VIX、200d MA 升为一等 capability，确保所有策略可分桶
- `data/sample/`：增加用于 unit test 的多制度合成数据

**Gate 改造**:
- 新 gate `regime_decomposition_required`：promotion 前必须存在 regime decomposition
- `backtest_forensics`：跨制度 Sharpe 比 > 2× 时触发 `regime_arb_warning`

**Skill 改造**:
- 新 skill `regime-analyzer`：从回测结果 + 制度标注计算分解
- `strategy-research-orchestrator`：每轮把 regime decomposition 写入 memory_packet

**新 CLI**:
- `oc research regime-decompose <strategy>`
- `oc research priority show <strategy>`

**测试**:
- `tests/test_regime_decomposition.py`
- `tests/test_regime_arb_warning.py`
- `tests/test_adaptive_search_priority.py`

### P10 — 生成可重现性（建议 7）

**新制品**:
- `reports/harness/provenance/{strategy}-generation-provenance.jsonl`

**Hook 改造**:
- `.claude/hooks/PreToolUse-llm-call-provenance.sh`：拦截 LLM 调用，记录 prompt template version + context hash

**Skill 改造**:
- 所有调用 LLM 的 skill 在 SKILL.md 中明文要求记录 provenance

**新 CLI**:
- `oc research provenance diff <strategy> <trial_a> <trial_b>`（解释 v_a 和 v_b 差异是 prompt 变化还是逻辑变化）

**测试**:
- `tests/test_generation_provenance.py`

---

## 第五部分 — 工程约束与决策点

### 5.1 与现有 Harness Engineering 哲学的契合

本路线图所有新增物**完全沿用** P0–P6 的设计语言：
- **制品 → `artifact_contracts.yaml`**：所有新制品都进契约表
- **gate → `harness/gates.py`**：所有约束都进 gate registry
- **skill → `harness/skill_manifest.yaml`**：所有行为都在 skill 中明文，由 manifest 触发
- **CLI → `open_composer/cli.py`**：所有人工干预都有命令行入口

**不引入**：新的存储层、新的服务、新的语言。延续"YAML + JSONL + Python"的简单组合。

### 5.2 Codex Cloud Code / Claude Code 协作模式

- LLM 记忆包（P7）的实际消费者是**当前 session 的 Codex/Claude**。每次 session 启动时，`.claude/hooks/UserPromptSubmit-harness-context.sh` 应**自动注入** memory_packet 的摘要（不超过 1KB），让 LLM 即使在 context 被压缩后也能从 hook 注入获取最近的失败记忆。
- Subagent 模式（已实现）+ memory_packet（P7）= 真正的"主 agent 决策 + 子 agent 执行 + 共享记忆"架构。

### 5.3 与"LLM 量化长处"的对应

| LLM 优势 | 本路线图利用方式 |
|---|---|
| 假设空间扩展 | P7 假设注册表 + P8 DAG → 让 LLM 的发散能力被结构化追踪 |
| 跨模态整合 | 已有 PIT 特征包 + P9 制度标注 → LLM 能在制度上下文中组合特征 |
| 代码生成 + 反馈 | 已有 gates + P10 provenance → 失败反馈结构化回到下次 prompt |
| NL → spec 翻译 | 已有 `strategy-designer` |

| LLM 弱点 | 本路线图防御方式 |
|---|---|
| 回测污染 | P9 制度分解（在 LLM "没见过"的制度下验证） |
| 幻觉传播 | 已有 source_cards + P10 provenance |
| 无状态生成 | P7 memory packet |
| 迭代安全退化 | P8 DAG + 预算 + P9 regime_arb_warning（迭代必须收敛证据，不只是改 bug） |
| 多重检验失控 | P8 testing budget |

### 5.4 优先级与建议时间线

- **P7（最高）**：~1 周。直接解决用户报告的核心痛点（LLM 不记得失败）。
- **P8**：~1.5 周。需小心改 `trial_ledger` schema，向后兼容已有 trial。
- **P9**：~2 周。需扩展 sample 数据集和 capability 注册。
- **P10**：~3 天。改动面小但触及 hooks 框架。

**最小可用版本**：只做 P7。它能在最小改动下让 LLM 跨 session 累积"已 rejected 假设"的记忆，已经能消除用户反馈的大部分低效循环。

---

## 第六部分 — 决策点（需要你判断）

1. **优先级**：是否接受 P7 → P8 → P9 → P10 的顺序？还是想先做 P9（制度分解，因为它防过拟合最有力）？
2. **假设的语义粒度**：每个策略 1–3 个假设？还是允许更细的子假设（H001.a、H001.b）？后者更精确但工程量大。
3. **memory packet 注入方式**：(a) hook 自动注入到每次 UserPromptSubmit；(b) skill 在被调用时显式读；(c) 两者都做。
4. **回归兼容**：现有 `trial_ledger` 是否需要批量迁移到含 `parent_trial_id` 的新格式？还是仅对 P8 之后的 trial 强制？

---

## 第七部分 — 参考文献

- [Alpha-GPT: Human-AI Interactive Alpha Mining for Quantitative Investment (arXiv:2308.00016)](https://arxiv.org/abs/2308.00016)
- [Alpha-GPT 2.0: Human-in-the-Loop AI for Quantitative Investment (arXiv:2402.09746)](https://arxiv.org/abs/2402.09746)
- [GPT-Signal: Generative AI for Semi-automated Feature Engineering (arXiv:2410.18448)](https://arxiv.org/pdf/2410.18448)
- [LLMLOOP: Improving LLM-Generated Code (arXiv:2603.23613)](https://arxiv.org/pdf/2603.23613)
- [Static Analysis as Feedback Loop (arXiv:2508.14419)](https://arxiv.org/pdf/2508.14419)
- [Security Degradation in Iterative AI Code Generation (arXiv:2506.11022)](https://arxiv.org/html/2506.11022)
- [Self-Evolving Curriculum for LLM Reasoning (arXiv:2505.14970)](https://arxiv.org/abs/2505.14970)
- [DSMentor: Data Science Agents with Curriculum Learning (arXiv:2505.14163)](https://arxiv.org/pdf/2505.14163)
- [Evaluating LLMs in Finance Requires Explicit Bias Consideration (arXiv:2602.14233)](https://arxiv.org/html/2602.14233v1)
- [FAITH: Tabular Hallucinations in Finance (arXiv:2508.05201)](https://arxiv.org/pdf/2508.05201)
- [LLM Limitations Survey (arXiv:2505.19240)](https://arxiv.org/pdf/2505.19240)
- [ACON: Optimizing Context Compression for Long-horizon LLM Agents (arXiv:2510.00615)](https://arxiv.org/abs/2510.00615)
- [Building Effective AI Agents — Anthropic](https://www.anthropic.com/research/building-effective-agents)
- [Effective context engineering for AI agents — Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Voyager: An Open-Ended Embodied Agent with LLMs (arXiv:2305.16291)](https://arxiv.org/abs/2305.16291)
- [Devin 2.0 — Cognition](https://cognition.ai/blog/devin-2)
- [QuantConnect MCP Server](https://www.quantconnect.com/mcp)
- [Numerai Signals + QuantConnect](https://docs.numer.ai/numerai-signals/signals-+-quantconnect)
