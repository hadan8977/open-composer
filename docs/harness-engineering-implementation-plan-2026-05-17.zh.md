# Harness Engineering 实施计划

**日期**：2026-05-17  
**作者**：Claude Code（评审 + 设计）  
**基于**：Codex harness-engineering-agent-quant-review、expanded-architecture-review、expanded-research-log 三份调研报告；外部联网调研（Agentproof/2025、Bailey-de Prado DSR/PBO、QuantConnect Reality Modeling、RD-Agent-Q NeurIPS 2025、Feast PIT、OpenAI Agents SDK Tracing）

---

## 一、对 Codex 本轮工作的评估

### 1.1 做得好的部分

| 模块 | 评价 |
|------|------|
| `research/kernel/` (7 个子模块) | 方向正确——把共享数据结构从各研究模块中提取出来。`ResearchBrief`、`SearchSpace`、`TrialLedger`、`CandidateSet`、`EvaluationBundle`、`ResearchArtifactWriter` 均有实际使用价值。 |
| `research/contracts.py` | 把证据清单从散文规则变成了可序列化的 Pydantic 对象，是正确方向。 |
| `research/factor_lab.py` | IC/RankIC/滚动 IC/分位数收益/相关矩阵覆盖完整，阈值（HIGH_FACTOR_CORRELATION=0.9, LOW_COVERAGE_PCT=80）合理。 |
| `analytics/execution_reality.py` | Bar 参与率/ADV 参与率/容量曲线/滑点压力建模保守合理，门控阈值（BAR_PARTICIPATION_BLOCK_PCT=10%）合适。 |
| `research/strategy_dag.py` | 强制 `llm_judge` 节点声明 `packet_path`/`packet_field`，在架构层阻止了无 PIT 包的 LLM 节点——这是核心安全边界的正确实现。 |
| `research/research_report.py` | 一键串联 6 个子评估，生成统一报告 + 索引记录，是工作流规范化的良好起点。 |
| `cache.py` + `oc cache status/clean` | 实用，保护 git 跟踪文件不被误删，dry-run 默认安全。 |
| `analytics/trade_metrics.py` | 简洁，exposure_pct 和 turnover_ratio 是重要的交易强度指标。 |
| 新增 CLI 命令 (`factor-lab`, `geometry-features`, `research-report`, `dag-validate`) | 暴露了正确的产品界面。 |

### 1.2 需要修复的问题

**P0 — 逻辑错误或遗漏（影响系统可信度）**

**问题 1：`leakage_defaults` 门控永远通过**

```python
# research_report.py:306 — 硬编码 ok，从不检查规格配置
{
    "name": "leakage_defaults",
    "status": "ok",   # ← 无论 spec 如何，永远是 ok
    "evidence": "bar-close signals, next-bar-open fills, visible_at feature replay",
}
```

`StrategySpec.execution` 有 `signal_on: Literal["bar_close"]` 和 `fill_assumption: Literal["next_bar_open"]`，应实际读取并验证。

**修复方向**：
```python
def _check_leakage(spec) -> dict:
    ok = (
        spec.execution.signal_on == "bar_close"
        and spec.execution.fill_assumption == "next_bar_open"
    )
    return {
        "name": "leakage_defaults",
        "status": "ok" if ok else "blocked",
        "evidence": {
            "signal_on": spec.execution.signal_on,
            "fill_assumption": spec.execution.fill_assumption,
        },
    }
```

**问题 2：`strategy_dag` 验证未接入 research pipeline**

`research/strategy_dag.py` 实现了完整的 DAG 验证，但 `research_report.py` 和 `promotion.py` 均未调用它。如果策略有 DAG 文件，会被静默跳过。

**修复方向**：在 `research_report.py` 的 `build_strategy_research_report` 中：
```python
# 如果 strategy_specs/ 目录下存在同名 dag.yaml，则自动验证
dag_path = spec_path.parent / f"{spec.name}-dag.yaml"
if dag_path.exists():
    dag_result = validate_strategy_dag(dag_path)
    # 纳入 evaluation_bundle.alternative_data
```

**问题 3：`WalkForwardSlice` 碎片化**

`kernel/windows.py` 定义了 `WalkForwardSlice` 基类，但 5 个研究模块各自定义了独立变体：
- `rotation.py`: `WalkForwardSlice`（同名但独立）
- `exposure_switch.py`: `ExposureSwitchWalkForwardSlice`
- `market_timing.py`: `TimingWalkForwardSlice`
- `leverage.py`: `LeverageWalkForwardSlice`
- `intraday_daily_rotation.py`: `IntradayWalkForwardSlice`

这些变体无法通过统一接口汇总到 `EvaluationBundle`，Dashboard 也无法一致地展示走步验证结果。

**修复方向**：让各模块的结果 dataclass 包含 `walk_forward_slices: list[WalkForwardSlice]`（使用 kernel 版本），或在序列化时转换为统一格式。

**问题 4：DSR/PBO 只记录输入，从不计算**

```python
# parameter_sweep.py:629
"dsr_inputs": {
    "computed_dsr": None,
    "computed_pbo": None,
    "note": "DSR/PBO proxy inputs are recorded; full DSR/PBO is not computed yet.",
}
```

多次参数搜索后选出"最佳"参数时，观察到的 Sharpe 比率是从分布右尾采样的，实际 Sharpe 更低。这不是可选优化——缺少 DSR 折扣会导致对参数搜索结果的系统性高估。

**修复方向**（Bailey-de Prado 简化公式）：
```python
import math
from scipy.stats import norm  # or simple approximation

def dsr_proxy(observed_sharpe: float, n_trials: int, sharpe_std: float = 0.0) -> float:
    """Deflated Sharpe Ratio proxy. Bailey & de Prado (2014)."""
    if n_trials <= 1:
        return observed_sharpe
    # Expected maximum SR across N independent trials
    gamma_e = 0.5772  # Euler-Mascheroni constant
    expected_max = (1 - gamma_e) * norm.ppf(1 - 1/n_trials) + gamma_e * norm.ppf(1 - 1/(n_trials * math.e))
    dsr = observed_sharpe - expected_max * (1 + sharpe_std**2 / 2)
    return round(dsr, 4)
```

**P1 — 架构缺口（core harness 全部缺失）**

以下 Codex 报告中识别的核心 harness 组件均未实现：

| 组件 | 状态 | 影响 |
|------|------|------|
| `HarnessPolicyManifest` | ❌ 未实现 | 规则停留在文本，无法机器验证 |
| `ResearchWorkflowHarness` | ❌ 未实现 | 用户仍需知道专业流程顺序 |
| `EvidenceManifest` | ❌ 未实现 | 无统一证据追踪，Dashboard 和 gate 不一致 |
| `AgentRunTrace` | ❌ 未实现 | 无法审计 Codex/Claude 做了什么 |
| `oc harness check` | ❌ 未实现 | 无法验证 harness 覆盖完整性 |
| Skill policy metadata | ❌ 未实现 | 技能约束无法机器读取 |
| Dashboard harness cockpit | ❌ 未实现 | Dashboard 是数据浏览器，不是决策工作台 |

---

## 二、Harness Engineering 整体架构设计

### 2.1 核心原则

**Codex 调研报告的核心洞察**是：现有规则是"agent 行为约束"（CLAUDE.md 散文 + AGENTS.md 散文），尚未成为"产品运行时不可绕过的 workflow gate"。

Harness engineering 的目标是**让规则变成数据，让数据驱动门控**：

```
AGENTS.md / CLAUDE.md / Skills
       ↓ 编译
HarnessPolicyManifest (YAML)
       ↓ 驱动
ResearchWorkflowHarness (状态机)
       ↓ 生成
EvidenceManifest (每策略追踪)
       ↓ 被
AgentRunTrace (每次 agent 介入) 引用
       ↓ 全部进入
Dashboard Harness Cockpit (决策工作台)
```

### 2.2 五层架构

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 5: Surfaces (CLI + Dashboard + Agent Requests)       │
│  oc harness check/policy-list/evidence/trace-list           │
│  oc strategy research-workflow                              │
│  Dashboard: GateMatrix / EvidenceProgress / DecisionCard    │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Trace (审计层)                                    │
│  AgentRunTrace  WorkflowStepTrace  MutationRecord           │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Workflow (编排层)                                  │
│  ResearchWorkflowHarness  WorkflowPlan  WorkflowStage       │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Evidence (证据层)                                 │
│  EvidenceManifest  EvidenceItem  DatasetManifest            │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Policy (规则层)                                   │
│  HarnessPolicyManifest  SkillPolicyPack  GatePolicy         │
└─────────────────────────────────────────────────────────────┘
         ↑ 全部以 StrategySpec 为源头，File-first
```

### 2.3 文件结构

```
open_composer/
└── harness/
    ├── __init__.py            # 统一导出
    ├── policy.py              # HarnessPolicyManifest + loader
    ├── evidence.py            # EvidenceManifest + EvidenceItem
    ├── workflow.py            # ResearchWorkflowHarness + WorkflowStage
    ├── trace.py               # AgentRunTrace + WorkflowStepTrace
    └── gate_registry.py       # 统一门控注册表

policies/
└── harness.yaml               # 机器可读的 policy 规范（主要配置文件）

.agents/skills/
└── */SKILL.md                 # 各技能文件增加 policy: 元数据前置块
```

### 2.4 Layer 1：Policy 层详细设计

**`policies/harness.yaml`** — 机器可读的规则规范：

```yaml
version: "1.0"
generated_from: ["AGENTS.md", "CLAUDE.md", ".agents/skills/"]

# 工作流阶段及其进入条件
workflow_stages:
  spec_draft:
    required_gates: [spec_validation, capability_check]
    optional_gates: []
  researching:
    required_gates: [research_contract, reference_backtest, factor_lab, execution_reality]
    blocked_by: [leakage_detected, data_quality_blocked]
  candidate_selected:
    required_gates: [parameter_sweep_with_trial_ledger, oos_evidence, cost_sensitivity]
    required_evidence: [trial_count_ge_5, dsr_proxy_positive, oos_slice_present]
  promotion_pending:
    required_gates: [walk_forward, benchmark_family, promotion_report_ok]
    blocked_by: [sample_fixture_fallback, trial_only_evidence]
  paper_ready:
    required_gates: [paper_readiness_11_gates, execution_mode_paper_auto]
    blocked_by: [kill_switch_enabled, feature_packet_incomplete]

# 研究控制
research_controls:
  max_unbounded_parameters: 0          # 所有参数必须有界
  trial_discount_required: true        # DSR 代理必须计算
  pit_features_required: true          # LLM 特征必须有 PIT 包
  dsr_proxy_threshold: 0.0             # DSR 代理必须 > 0
  min_trial_count_for_sweep: 5         # 至少 5 次 trial 才能选出候选
  walk_forward_min_folds: 3            # 走步验证至少 3 折
  oos_min_ratio: 0.2                   # OOS 至少占总样本 20%

# LLM 控制
llm_controls:
  advisory_only: true                  # LLM 不做执行决策
  structured_output_required: true     # 结构化输出，不接受自由文本
  pit_packet_required: true            # llm_judge 节点必须有 packet_path
  no_live_calls_in_backtest: true      # 回测内禁止实时 LLM 调用
  contribution_tracking_required: true # 必须追踪 LLM 贡献度

# Paper trading 控制
paper_controls:
  alpaca_paper_only: true
  kill_switch_clears_all: true
  explicit_confirmation_required: true
  real_money_out_of_scope: true

# 数据控制
data_controls:
  sample_fixture_fallback_blocks_paper: true
  trial_only_evidence_blocks_promotion: true
  provider_must_be_in_registry: true
```

**`open_composer/harness/policy.py`** — Policy 模型：

```python
class GatePolicy(BaseModel):
    required_gates: list[str]
    optional_gates: list[str] = []
    blocked_by: list[str] = []
    required_evidence: list[str] = []

class HarnessPolicyManifest(BaseModel):
    version: str
    generated_from: list[str]
    workflow_stages: dict[str, GatePolicy]
    research_controls: dict[str, Any]
    llm_controls: dict[str, Any]
    paper_controls: dict[str, Any]
    data_controls: dict[str, Any]

def load_policy_manifest(root: Path | None = None) -> HarnessPolicyManifest: ...
def check_policy_coverage(manifest: HarnessPolicyManifest, root: Path) -> PolicyCheckResult: ...
```

**Skill 文件新增 `policy:` 前置块**（以 `strategy-researcher` 为例）：

```markdown
---
name: strategy-researcher
description: End-to-end research workflow
policy:
  required_workflow_stage_before: spec_draft
  produces_stages: [researching, candidate_selected]
  required_gates_on_entry:
    - spec_validation
    - capability_check
  required_artifacts:
    - research_contract
    - reference_backtest
    - factor_lab
    - trial_ledger
  blocks_if_missing:
    - dsr_proxy
    - oos_slice
  llm_contribution_tracking: required_if_llm_features
---
```

### 2.5 Layer 2：Evidence 层详细设计

**核心思想**：每个策略维护一个 append-only 的证据清单。每次产生研究 artifact 就追加一条记录。状态是从清单推导出来的，不是存储的。

```python
class EvidenceItem(BaseModel):
    name: str                        # "backtest", "factor_lab", "oos_test" 等
    status: Literal["ok", "warning", "blocked", "missing"]
    artifact_path: str | None        # 相对路径
    artifact_hash: str | None        # 内容哈希（检测变化）
    produced_at: datetime
    produced_by: str                 # "codex", "claude_code", "manual", "cli"
    spec_hash: str                   # 对应的规格版本
    gate_results: list[GateResult]   # 通过/失败的门控
    lineage: list[str]               # 依赖的其他 artifact 路径

class EvidenceManifest(BaseModel):
    strategy_name: str
    spec_hash: str
    created_at: datetime
    updated_at: datetime
    # 核心证据项
    research_contract: EvidenceItem | None
    reference_backtest: EvidenceItem | None
    factor_lab: EvidenceItem | None
    execution_reality: EvidenceItem | None
    oos_test: EvidenceItem | None
    walk_forward: EvidenceItem | None
    cost_sensitivity: EvidenceItem | None
    benchmark_family: EvidenceItem | None
    alternative_data_quality: EvidenceItem | None
    strategy_dag: EvidenceItem | None
    promotion_report: EvidenceItem | None
    paper_readiness: EvidenceItem | None
    # 特征包（每个因子一条）
    feature_packets: dict[str, EvidenceItem]
    # 推导状态
    @property
    def research_complete(self) -> bool: ...
    @property
    def promotion_ready(self) -> bool: ...
    @property
    def paper_ready(self) -> bool: ...
    @property
    def blockers(self) -> list[str]: ...
    @property
    def next_required_actions(self) -> list[str]: ...
```

**持久化**：每策略一个文件，路径 `reports/evidence/{strategy_name}-evidence-manifest.json`。

**`ResearchArtifactWriter` 扩展**：每次写 artifact 同时追加到 evidence manifest。

### 2.6 Layer 3：Workflow 层详细设计

**核心思想**：研究流程是有明确阶段的状态机。每个阶段有入口条件和出口条件。`ResearchWorkflowHarness` 是这个状态机的执行器。

```python
class WorkflowStage(str, Enum):
    SPEC_DRAFT = "spec_draft"
    RESEARCHING = "researching"
    CANDIDATE_SELECTED = "candidate_selected"
    PROMOTION_PENDING = "promotion_pending"
    PAPER_READY = "paper_ready"
    ACTIVE = "active"
    RETIRED = "retired"

class WorkflowStep(BaseModel):
    name: str
    stage: WorkflowStage
    command: str                     # e.g. "oc strategy factor-lab"
    required: bool
    status: Literal["pending", "running", "done", "blocked", "skipped"]
    artifact_path: str | None
    duration_seconds: float | None
    gate_result: GateResult | None

class WorkflowPlan(BaseModel):
    strategy_name: str
    current_stage: WorkflowStage
    target_stage: WorkflowStage
    steps: list[WorkflowStep]
    blockers: list[str]
    estimated_steps_remaining: int
    evidence_manifest_path: str

class ResearchWorkflowHarness:
    def plan(self, spec_path: Path, target: WorkflowStage | None = None) -> WorkflowPlan:
        """从当前证据状态推导下一步计划。"""
        ...

    def advance(self, spec_path: Path) -> WorkflowPlan:
        """执行下一个待完成步骤，写 artifact，更新 evidence manifest。"""
        ...

    def check_stage_gates(self, spec_path: Path, stage: WorkflowStage) -> GateSummary:
        """检查是否满足进入某阶段的条件。"""
        ...

    def full_research_pipeline(self, spec_path: Path) -> WorkflowPlan:
        """一键执行：从当前状态到 candidate_selected 的完整研究。"""
        # 等价于: research_contract → backtest → factor_lab → parameter_sweep
        #         → oos_test → cost_sensitivity → benchmark_family → research_report
        ...
```

**新 CLI 命令**：

```bash
# 查看策略当前研究阶段和下一步
oc strategy research-workflow strategy_specs/drafts/qqq_pullback_15m.yaml

# 一键执行完整研究 pipeline（自动跳过已完成步骤）
oc strategy research-workflow strategy_specs/drafts/qqq_pullback_15m.yaml --run

# 只生成计划，不执行
oc strategy research-workflow strategy_specs/drafts/qqq_pullback_15m.yaml --plan-only
```

### 2.7 Layer 4：Trace 层详细设计

**核心思想**：每次 Codex/Claude Code/用户 CLI 介入策略研究时，生成一条结构化追踪记录。这不是 debug 日志，是**研究审计轨迹**。

```python
class ArtifactRef(BaseModel):
    path: str
    content_hash: str
    role: Literal["consumed", "produced", "mutated"]

class StrategyMutation(BaseModel):
    field_path: str                  # e.g. "risk.stop_loss_pct"
    old_value: Any
    new_value: Any
    reason: str

class AgentRunTrace(BaseModel):
    trace_id: str                    # 唯一 ID
    agent_type: Literal["codex", "claude_code", "manual_cli", "automated"]
    session_id: str | None
    strategy_name: str | None
    skill_used: str | None           # 使用了哪个技能
    command_used: str | None         # 使用了哪个 CLI 命令
    policy_version: str              # harness.yaml 版本
    started_at: datetime
    completed_at: datetime | None
    workflow_stage_before: str | None
    workflow_stage_after: str | None
    gates_checked: list[GateResult]
    artifacts: list[ArtifactRef]
    strategy_mutations: list[StrategyMutation]
    warnings: list[str]
    status: Literal["completed", "blocked", "failed", "partial"]
    # OTel 兼容字段（便于未来集成）
    span_id: str | None = None
    parent_span_id: str | None = None
```

**持久化**：`reports/traces/agent-runs.jsonl`（全局 append-only）。

**自动发射**：通过 CLI hook（`before_command`/`after_command`）或 `ResearchArtifactWriter` 拦截器实现，无需每个命令手动写 trace。

### 2.8 Layer 5：Dashboard Harness Cockpit

**当前 Dashboard 是数据浏览器，需要升级为决策工作台。** 核心新增三个视图：

**① Evidence Progress 视图（每策略）**

```
Strategy: qqq_pullback_15m  |  Stage: researching  |  Target: candidate_selected

Evidence Checklist:
  ✅ research_contract       2026-05-17 14:23
  ✅ reference_backtest      Sharpe=1.2, alpha=+3.1%
  ✅ factor_lab              2 factors, IC=0.08, stable
  ⚠️ execution_reality      avg_dv=$45M, bar_participation=3.2% [warning]
  ❌ oos_test                MISSING — run: oc strategy blind-test
  ❌ walk_forward            MISSING — run: oc strategy exposure-switch --walk-forward-folds 3
  ❌ cost_sensitivity        MISSING — run: oc strategy cost-grid
  ❌ dsr_proxy               MISSING — requires parameter_sweep with ≥5 trials

Next action: oc strategy blind-test strategy_specs/drafts/qqq_pullback_15m.yaml
```

**② Gate Matrix 视图（多策略汇总）**

```
Strategy              | spec | contract | backtest | factor | exec | oos | walk | paper
qqq_pullback_15m      |  ✅  |    ✅    |    ✅    |   ✅   |  ⚠️  |  ❌  |  ❌  |  ❌
spy_momentum_daily    |  ✅  |    ✅    |    ✅    |   ⚠️   |  ✅   |  ✅  |  ✅  |  ❌
```

**③ Agent Activity 视图（审计时间线）**

```
2026-05-17 15:53  claude_code  strategy-researcher  qqq_pullback_15m
  Produced: research_report, factor_lab_report, research_contract
  Gates: factor_lab=ok, execution_reality=warning, oos_test=missing
  Stage: spec_draft → researching

2026-05-17 14:21  codex         python-backtest-writer  qqq_pullback_15m
  Produced: reference_backtest_report, signal_log
  Stage: (no change)
```

---

## 三、具体实施计划

### Phase 0：修复现有代码问题（优先级最高）

| # | 文件 | 问题 | 修复内容 |
|---|------|------|---------|
| F1 | `research/research_report.py:306` | `leakage_defaults` 永远通过 | 读取 `spec.execution.signal_on` 和 `fill_assumption` 做实际验证 |
| F2 | `research/research_report.py` | Strategy DAG 未接入 | 检查是否存在 `{spec.name}-dag.yaml`，若存在则调用 `validate_strategy_dag` 并纳入 `alt_data` gate |
| F3 | `research/parameter_sweep.py:629` | DSR 只记录不计算 | 实现 Bailey-de Prado DSR 代理公式，至少给出 `-` vs `+` 的判断 |
| F4 | 5 个研究模块 | `WalkForwardSlice` 碎片化 | 为各模块定义的变体添加 `to_kernel_slice()` 转换方法，使其可序列化为统一格式 |
| F5 | `research/kernel/windows.py` | `WalkForwardSlice` 未被使用 | 在 `kernel/__init__.py` 导出，并在 `EvaluationBundle.walk_forward` 中使用 |

验收：`make check` 通过，`uv run pytest tests/test_research_contract_and_dag.py tests/test_factor_lab.py` 全绿。

### Phase 1：Policy 层（核心 harness 基础）

**交付物**：
1. `policies/harness.yaml` — 机器可读的 policy 规范
2. `open_composer/harness/policy.py` — `HarnessPolicyManifest` + `load_policy_manifest()` + `check_policy_coverage()`
3. `.agents/skills/*/SKILL.md` — 9 个技能文件增加 `policy:` 元数据前置块
4. `open_composer/cli.py` — `harness_app` 子命令组，包含 `oc harness check` 和 `oc harness policy-list`
5. `open_composer/repo_check.py` — 增加 policy 覆盖验证
6. `tests/test_harness_policy.py`

**验收标准**：
- `oc harness check` 输出 policy 覆盖报告，无 MISSING 项
- `oc harness policy-list` 列出所有 gates 和对应 skill/CLI 覆盖
- `repo_check --strict` 包含 policy manifest 验证

### Phase 2：Evidence 层

**交付物**：
1. `open_composer/harness/evidence.py` — `EvidenceManifest` + `EvidenceItem` + `update_evidence_manifest()`
2. 更新 `research/kernel/artifacts.py` — `ResearchArtifactWriter.json()` 同时写 evidence manifest
3. 更新 `research/research_report.py` — `build_strategy_research_report` 写 evidence manifest
4. `open_composer/cli.py` — `oc harness evidence <spec>` 命令
5. 更新 `dashboard/catalog.py` — 读取并包含 evidence manifest 数据
6. `tests/test_harness_evidence.py`

**验收标准**：
- 每次运行 `oc strategy research-report` 后 `reports/evidence/{name}-evidence-manifest.json` 更新
- `oc harness evidence <spec>` 输出带状态的证据清单
- Dashboard catalog 包含 `evidence_manifest` 字段

### Phase 3：Workflow Harness

**交付物**：
1. `open_composer/harness/workflow.py` — `ResearchWorkflowHarness` + `WorkflowStage` + `WorkflowPlan`
2. `open_composer/cli.py` — `oc strategy research-workflow <spec> [--run] [--plan-only]`
3. `open_composer/harness/gate_registry.py` — 统一门控注册表（消除各模块重复的 gate 逻辑）
4. `tests/test_harness_workflow.py`

**验收标准**：
- `oc strategy research-workflow <spec> --plan-only` 输出带状态的研究计划
- `oc strategy research-workflow <spec> --run` 从当前阶段自动执行下一步
- 缺少必要 evidence 时阻断晋升并给出明确的 next action

### Phase 4：Trace 层

**交付物**：
1. `open_composer/harness/trace.py` — `AgentRunTrace` + `emit_trace()`
2. `open_composer/cli.py` — trace hook 在研究命令前后自动发射 trace
3. `open_composer/cli.py` — `oc harness trace-list [--strategy] [--last-n]`
4. 更新 `dashboard/catalog.py` — 读取 agent traces
5. `tests/test_harness_trace.py`

**验收标准**：
- 每次运行研究命令后 `reports/traces/agent-runs.jsonl` 有新记录
- `oc harness trace-list --strategy qqq_pullback_15m` 输出最近 N 条 trace
- Dashboard 的 agent activity 视图可用

### Phase 5：Dashboard Harness Cockpit

**交付物**：
1. `dashboard/src/app/components/evidence-progress.tsx` — Evidence Progress 视图
2. `dashboard/src/app/components/gate-matrix.tsx` — Gate Matrix 汇总
3. `dashboard/src/app/components/agent-activity.tsx` — Agent Activity 时间线
4. 更新 `dashboard/src/app/App.tsx` — 新增 Research 主视图

**验收标准**：
- 每个策略可看到证据清单进度和下一步 action
- Gate Matrix 一屏显示所有策略的通过/失败/缺失状态
- Agent Activity 展示最近 20 条 trace 记录

---

## 四、不做什么（Codex 报告明确的边界）

以下来自 Codex 调研报告的禁区必须坚守：

| 不做 | 理由 |
|------|------|
| 直接接入 LangGraph / AutoGen | 重量级依赖，不符合 file-first 定位；状态机自己实现足够 |
| 引入完整 MLOps 栈（MLflow server） | 个人工作台不需要 experiment tracking 服务；JSONL artifacts 已足够 |
| 复制 QuantConnect 的完整 Reality Modeling | bar-level OHLCV 流动性模型已足够；order book 级别超出当前数据能力 |
| 引入 Feast / Hopsworks 特征存储 | PIT 包 JSONL 是等效的轻量实现；引入特征存储会带来运维负担 |
| LLM 实时交易执行 | 所有 LLM 输入必须先成为 PIT 特征包，永远不允许直接驱动订单 |
| 完整 DSR/PBO 统计框架 | Bailey-de Prado 代理公式就足够给出 pass/fail 信号 |
| 自动 LLM 策略生成流水线 | LLM 是研究辅助，策略生成需要人工审查和规格验证 |

---

## 五、优先级总结

```
立即修复（Phase 0）:
  F1 leakage_defaults 永远通过  ← 影响报告可信度
  F2 strategy_dag 未接入        ← 功能完整性漏洞
  F3 DSR 代理计算               ← 防过拟合的核心缺失

短期实现（Phase 1-2，1-2 周）:
  Policy 层：harness.yaml + HarnessPolicyManifest + oc harness check
  Evidence 层：EvidenceManifest + 自动写入 + oc harness evidence

中期实现（Phase 3-4，2-4 周）:
  Workflow Harness：一键研究流程 + 阶段门控
  Trace 层：自动审计 + agent activity

后续迭代（Phase 5）:
  Dashboard Harness Cockpit：Evidence Progress + Gate Matrix + Agent Activity
```

---

## 六、验收标准（整体）

以下命令序列能完整走通，且每步输出有意义的结构化结果：

```bash
# 1. 检查 harness 覆盖
uv run oc harness check

# 2. 列出策略当前研究状态和证据清单
uv run oc harness evidence strategy_specs/drafts/qqq_pullback_15m.yaml

# 3. 一键执行完整研究（自动跳过已完成步骤）
uv run oc strategy research-workflow strategy_specs/drafts/qqq_pullback_15m.yaml --run

# 4. 查看最近 agent 活动
uv run oc harness trace-list --strategy qqq_pullback_15m --last-n 5

# 5. 全面验证
make verify
```

最终目标：一个量化研究者坐下来，不需要记忆任何专业流程，只需运行 `oc strategy research-workflow <spec>`，系统自动告诉他下一步该做什么，已有哪些证据，什么门控还未通过，什么是阻断晋升的具体原因。

---

---

## 七、外部调研补充：关键量化阈值与架构参考

### 7.1 Policy-as-Code 最新方法（2024-2025）

**Agentproof（arxiv:2603.20356，MIT 开源）** — 2025 年最重要的 agent 约束工程工作：
- 从 LangGraph/CrewAI/AutoGen 工作流图中自动提取节点依赖图
- 把人写的 temporal policy（LTL 安全片段）编译为确定性有限自动机（DFA）
- 对所有可能路径做**静态验证**（不需要实际执行），5,000 节点以下毫秒级
- 发现：27% 的 benchmark 工作流有死路/不可达节点；55% 在实施人工门控策略时违规
- **对 Open Composer 的意义**：`ResearchWorkflowHarness` 的阶段转换规则应能用类似 LTL 形式表达，`oc harness check` 做等价的静态验证

**OpenAI Agents SDK Tracing（2025）**：内置 tracing 捕获 LLM 生成、工具调用、handoff、guardrail 事件。Guardrail 是附加在 agent 上的类型化输入/输出验证器，返回 pass/fail + reason。这是最轻量的 Python-first 实现参考。

**关键约束**：`AgentRunTrace` 的字段设计应兼容 OpenTelemetry span 模型（`trace_id`, `span_id`, `parent_span_id`），便于未来集成外部 trace 收集器。

### 7.2 防过拟合量化阈值（学术共识 2024-2025）

晋升所需的最小证据集（**这些是门控阈值，不是建议**）：

| 指标 | 阈值 | 方法 | 来源 |
|------|------|------|------|
| Deflated Sharpe Ratio (DSR) | **> 0** | Bailey-de Prado 公式 | J. Stat. Finance 2016 |
| Probability of Backtest Overfitting (PBO) | **< 0.10** | Combinatorial Purged CV | MLFinLab |
| OOS Sharpe 降级比 | **> 0.5 × IS Sharpe** | 走步验证 | 2025 walk-forward 框架 |
| 最小走步折叠数 | **≥ 3 folds** | Anchored walk-forward | 行业共识 |
| OOS 最小占比 | **≥ 20% 总样本** | 任何分割方法 | 行业共识 |

**CPCV 优于 k-fold 和 walk-forward**：2024 年 ScienceDirect 论文对比了多种交叉验证方法，在合成受控环境中 CPCV 的 PBO 估计最准确。Open Composer 当前用的走步验证（walk-forward）可以升级为 CPCV，但走步验证作为最低标准是可接受的。

**DSR 计算公式（Bailey & de Prado，可实现为 Python）**：
```
SR*    = 观察到的最佳 Sharpe（来自参数搜索）
N      = 独立试验次数（TrialLedger.trial_count）
σ(SR)  = 各试验 Sharpe 的标准差
T      = 样本长度（bars）

期望最大 SR:  E[max SR] ≈ (1 - γ)Φ⁻¹(1 - 1/N) + γΦ⁻¹(1 - 1/(N·e))
DSR 代理:  SR* - E[max SR] × (1 + σ²(SR)/2)

DSR > 0 意味着观察到的最佳 Sharpe 超过了从随机搜索中期望得到的最大值
```

### 7.3 PIT 特征完整性（Feast 最佳实践）

每个特征记录必须包含**两个时间戳**（这是 Feast 设计的核心洞察，Open Composer 的 feature packet 已有 `published_at` 和 `visible_at`，方向正确）：

```
event_timestamp   ← 事实发生时间（如：财报公告时间 16:05）
created_timestamp ← 数据入库时间（如：数据管道摄入时间 18:30）
effective_time    = max(event_timestamp, created_timestamp + pipeline_latency)
```

**看穿未来的隐患**：如果把 `event_timestamp` 设为财报发布日，但实际数据只在两天后才可得，就存在隐式前视。`created_timestamp`（即 Open Composer 的 `fetched_at`）的存在正是为了审计这种差异。

**Open Composer 的 feature packet 字段映射**：
- `published_at` ≈ Feast 的 `event_timestamp`（事实发生时间）
- `fetched_at` ≈ Feast 的 `created_timestamp`（数据摄入时间）
- `visible_at = max(published_at, fetched_at)` ≈ Feast 的有效可用时间

当前设计**正确**，但缺少 `publication_lag_minutes` 字段（估计的发布-摄入延迟）和 LLM 特征的 `training_cutoff` 字段。

### 7.4 Financial LLM 安全边界（2024-2025 共识）

**安全使用（结构化、有界、可审计）**：
- 结构化因子候选生成：LLM 提出 alpha 因子表达式字符串 → 回测引擎确定性评估（RD-Agent-Q 模式）
- 叙事信号摘要：把文本转为结构化情感向量 → 成为 PIT 特征包 → 不直接驱动交易
- 参数建议：LLM 生成超参数候选 → 有界搜索空间 → 回测验证
- 结构化审查：LLM 对策略报告按评分规则评分（有明确通过/失败标准的 review card）

**不安全使用（直接执行路径，禁止）**：
- LLM 直接生成订单级信号
- LLM 设置仓位大小或风险限额
- 使用预训练 LLM 对历史股票表现的"记忆"作为特征（**时间泄漏**：模型权重隐式编码了训练截止日期之后的事件）
- LLM 评估自己的输出（无独立确定性验证器）

**RD-Agent-Q（NeurIPS 2025，微软）的关键架构**：
- LLM 从不接触原始 OHLCV 数据，只接触 schema 级别信息
- 知识森林（knowledge forest）避免重复测试已知无效的想法
- 代码生成 → 静态分析 → 回测 → 结果反馈给 LLM（全闭环，LLM 是研究者，不是执行者）

### 7.5 执行现实性建模（QuantConnect 参考）

**OHLCV bar 级别的最佳实践**：

| 参数 | 推荐默认值 | 触发警告 | 触发阻断 |
|------|-----------|---------|---------|
| 单 bar 成交量占比 | ≤ 1% 日成交量 | > 2.5% | > 10% |
| ADV 参与率 | ≤ 5% | > 10% | > 20% |
| 滑点模型 | VolumeShareSlippageModel | - | - |
| priceImpact 系数 | 0.1 | > 0.3 | - |
| 容量估计公式 | `volumeLimit × avg_daily_volume × price × trading_days` | - | - |

**每份回测报告应记录（与规格 hash 一起存储）**：
```yaml
fill_model: "next_bar_open"
slippage_model: "VolumeShareSlippageModel"
volume_limit_pct: 1.0
price_impact_coeff: 0.1
capacity_estimate_usd: <computed>
max_bar_participation_pct: <measured>
```

Open Composer 当前的 `ExecutionRealityMetrics` 阈值（BAR_PARTICIPATION_BLOCK_PCT=10%，ADV_PARTICIPATION_WARNING_PCT=10%）与 QuantConnect 文档吻合，**当前实现是合理的**。

### 7.6 参考链接

- [Agentproof: Static Verification of Agent Workflow Graphs](https://arxiv.org/html/2603.20356v1)
- [AgentGuard: Runtime Verification of AI Agents](https://arxiv.org/html/2509.23864v1)
- [Deflated Sharpe Ratio — Bailey/Lopez de Prado](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- [Probability of Backtest Overfitting — Bailey et al.](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
- [Feast Point-in-Time Joins](https://docs.feast.dev/getting-started/concepts/point-in-time-joins)
- [RD-Agent-Quant (NeurIPS 2025)](https://arxiv.org/html/2505.15155v2)
- [Walk-Forward Framework (Dec 2025)](https://arxiv.org/html/2512.12924v1)
- [QuantConnect Reality Modeling](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts)
- [OpenAI Agents SDK — Tracing](https://openai.github.io/openai-agents-python/tracing/)

---

*此文档是实施计划，不是 Codex 执行指令。执行前应先完成 Phase 0 的 bug 修复，再按阶段推进。*
