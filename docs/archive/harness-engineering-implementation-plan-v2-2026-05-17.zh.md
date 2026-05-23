# Harness Engineering 实施计划（修订版 v2）

**日期**：2026-05-17
**作者**：Claude Code (Opus)
**关系**：取代 `harness-engineering-implementation-plan-2026-05-17.zh.md`（v1，Sonnet）

v1 整理了 Codex 报告并加了量化阈值，但接受了 Codex 的"5 层架构"框架，没有质疑根本设计。
本修订做三件事：(1) 指出 Codex 提案中的根本问题；(2) 指出 v1 没看到的 4 个具体代码 bug；(3) 用更简单的 2 概念架构替换 5 层方案。

---

## 一、根本问题：Codex 在用错误的参照系

### 1.1 Open Composer 不是 LangGraph 类系统

Codex 的三份报告反复援引 OpenAI Agents SDK、LangGraph、AutoGen 的设计模式，提出 `WorkflowPlan`、`AgentRunTrace`（OTel 兼容）、`StateMachine` 等概念。这些都是**运行时 agent 编排框架**的产物——它们解决的问题是"agent 在框架内部运行，框架需要追踪、暂停、恢复"。

**Open Composer 的实际情况完全不同**：
- Codex 和 Claude Code 在**框架外部**运行（IDE/CLI 进程里），而不是被 Open Composer 调起
- Agent 通过编辑文件和运行 CLI 命令与系统交互
- 系统不能"打断"agent，也不需要"恢复"agent
- Agent 完成工作后离开，系统只看到文件状态的变化

引用 LangGraph 设计是范畴错误。Open Composer 的 harness **不是 agent 运行时**，而是**agent 工作产物的验证层**——更接近 `pre-commit` 钩子或 CI 系统，而不是 workflow engine。

### 1.2 Codex 同时提出 5 个抽象，让"通过/失败"概念已经过度膨胀

我自己读 `promotion.py` 时发现，系统当前已经有 **5 套相互重叠的"门控"抽象**：

| # | 抽象 | 位置 | 概念 |
|---|------|------|------|
| 1 | `PromotionCheck` | `promotion.py:35` | 11 个晋升检查 |
| 2 | `FivePassChecks` | `promotion.py:43` | workflow/research/llm/paper/code 五通过 |
| 3 | `GateResult` | `kernel/gates.py` | research_report 用的门控 |
| 4 | `ResearchContract.required_checks` | `contracts.py:19` | 证据要求清单 |
| 5 | `MetricSummary` | `kernel/metrics.py` | 各维度指标聚合 |

**Codex 提案要再加 2 个**（`HarnessPolicyManifest`、`EvidenceManifest`），让总数变成 7。

这不是缺乏抽象的问题，是**抽象过载**的问题。正确的方向是**合并和删除**，不是再加层。

### 1.3 Codex 在重新创造 CLAUDE.md / AGENTS.md

Codex 提案的 `HarnessPolicyManifest` 是要把 CLAUDE.md/AGENTS.md/skills 文件中的规则"编译"成 YAML。但这等于**再造一份事实真相**：现在有 CLAUDE.md 说一套，AGENTS.md 说一套，skills 文件说一套，将来还要 policies/harness.yaml 说一套。

agent 看哪一份？人维护哪一份？它们漂移了怎么办？`oc repo check --strict` 已经在做漂移检查，但加一个新源只会让漂移面增大。

正确方向：**让现有的 CLAUDE.md / AGENTS.md 本身可以被机器解析**（用 `<!-- gate: gate_name -->` 这类语义化锚点），而不是创造平行版本。

---

## 二、从代码中独立发现的 4 个 Bug（v1 没看到）

### Bug A：`benchmark_family.market_proxy` 永远是 "missing"

```python
# promotion.py:706-720
market = {
    "status": "missing",
    "proxy": None,
    "note": "market proxy such as SPY or QQQ has not been attached to this report",
}
sector = {
    "status": "missing",
    "proxy": None,
    "note": "sector/theme proxy or basket has not been attached to this report",
}
```

`market_proxy` 和 `sector_theme_proxy` 是 dict literal 硬编码 `"missing"`，根本没有读取数据/计算逻辑。这意味着**任何策略的 `benchmark_family` 都不可能是 ok**，永远是 warning（因为 missing 列表非空）。

**影响**：与 v1 发现的 `leakage_defaults` 永远 ok 是同类型 bug。系统有多个"装样子"的门控。

**根因**：这些 dict literal 是占位符，等待"将来实现 SPY/QQQ 自动比对"，但没有 TODO，没有 issue 跟踪，没有测试断言其行为。这是**死代码假装是活代码**。

### Bug B：`research_pass` 把 warning 当 failure，必然永远 fail

```python
# promotion.py:1026-1028
research_failures = sorted(
    name for name in research_gate_names if name in blocked or name in warning
)
```

`research_failures` 同时包含 `blocked` 和 `warning` 检查。结合 Bug A 让 `benchmark_family` 永远是 warning，**任何策略的 `research_pass` 都不可能是 pass**。

加上现实里 `execution_reality` 也容易触发参与率/成交量警告，五通过中的 `research_pass` 实际上是个永远红的灯。系统失去了五通过的诊断价值——所有策略看起来都没通过研究门。

### Bug C：`code_correctness_pass` 名不副实

```python
# promotion.py:1074
def _code_correctness_pass(spec: StrategySpec) -> tuple[FivePassStatus, str]:
    expressions = [...]
    for expression in expressions:
        # 只检查表达式安全（不能用 eval/import 等）
```

`code_correctness_pass` 实际上只做了**表达式安全检查**（AST 白名单），与"代码正确性"无关。代码正确性应该是 lint + type + test 都通过——这套已经在 `make check` 里有了，但没有接入这个五通过。

**影响**：这个门给人"已经检查了"的虚假安全感，实际只是 expression sandbox。

### Bug D：`strategy_versions.register_strategy_version` 只在 drafter 调用一次

```python
# 全代码库只有 drafter.py:42 调用 register_strategy_version
```

`strategy_versions.py` 6 个模块 import 了它（只用 `strategy_content_hash`），但只有 `drafter.py` 调用了 `register_strategy_version`。这意味着**修改一个 draft spec 不会自动生成新版本**——版本只在初次起草时记录。

**影响**：研究迭代的核心需求是"我调了参数，结果更好了还是更差了？"——这需要**前后版本对比**。当前实现没有这个能力，因为版本记录不完整。

---

## 三、关于 v1（Sonnet）方案的批评

v1 方案虽然加了量化阈值（DSR/PBO/Bailey-de Prado），但仍然接受了 Codex 的 5 层架构框架：

```
Layer 1: Policy (HarnessPolicyManifest)
Layer 2: Evidence (EvidenceManifest)
Layer 3: Workflow (ResearchWorkflowHarness)
Layer 4: Trace (AgentRunTrace, OTel-compat)
Layer 5: Surfaces (Cockpit, GateMatrix)
```

**问题**：
1. 5 层加在已有 5 个"通过/失败"抽象之上，让总抽象数变成 10
2. `AgentRunTrace` OTel 兼容是企业模式，对个人工作台过度工程
3. `WorkflowHarness` 作为状态机类替代了简单的"按需运行所需 gate"模式
4. 没有质疑 Codex 的提案，只是补充了量化阈值

v1 的有用部分（保留）：
- 4 个 P0 修复（leakage 硬编码、strategy_dag 未接入、DSR 未计算、WalkForwardSlice 碎片化）
- DSR/PBO 量化阈值与公式（学术上正确）
- Feast PIT 双时间戳设计（与 Open Composer 现有 published_at/fetched_at 一致）
- QuantConnect 执行现实参数（验证了 Codex 实现合理）

---

## 四、修订后的最小架构：两个概念

放弃 5 层。最小可用 harness 只需要 **2 个一等公民**：

### 4.1 Gates（断言函数）

```python
# open_composer/harness/gates.py
GateFn = Callable[[StrategySpec, Path], GateResult]

@dataclass(frozen=True)
class GateResult:
    name: str
    status: Literal["pass", "warning", "blocked", "not_applicable"]
    reason: str                          # 一句话人类可读
    evidence_paths: list[str]            # 相对路径
    metrics: dict[str, Any] = field(default_factory=dict)
    gate_version: int = 1                # 改门控逻辑时递增

GATE_REGISTRY: dict[str, GateFn] = {}    # 全局注册表

def gate(name: str, version: int = 1):
    """装饰器：注册一个 gate function。"""
    def wrap(fn: GateFn) -> GateFn:
        GATE_REGISTRY[name] = fn
        return fn
    return wrap
```

每个 gate 是**纯函数**：拿到 spec 和 root，返回 `GateResult`。没有继承、没有状态、没有 mixin、没有 builder。

将 `promotion.py` 里的 11 个检查、`research_report.py` 里的 7 个 checklist 项、`paper_readiness.py` 里的 11 个门控统一改为 gate function，**用一个注册表替代当前 5 套抽象**。

```python
# 示例
@gate("leakage_defaults", version=2)
def check_leakage(spec: StrategySpec, root: Path) -> GateResult:
    ok = (spec.execution.signal_on == "bar_close"
          and spec.execution.fill_assumption == "next_bar_open")
    return GateResult(
        name="leakage_defaults",
        status="pass" if ok else "blocked",
        reason=f"signal_on={spec.execution.signal_on}, fill={spec.execution.fill_assumption}",
        evidence_paths=[],
        metrics={"signal_on": spec.execution.signal_on,
                 "fill_assumption": spec.execution.fill_assumption},
    )
```

**Gate 与 Lifecycle stage 的关系**用配置文件（不是 manifest）声明：

```python
# open_composer/harness/stages.py
STAGE_REQUIREMENTS: dict[str, list[str]] = {
    "spec_draft":         ["spec_validation", "capability_check"],
    "researching":        ["leakage_defaults", "reference_backtest",
                           "factor_lab", "execution_reality"],
    "candidate_selected": ["parameter_sweep_trial_ledger", "dsr_proxy",
                           "oos_evidence"],
    "promotion_pending":  ["walk_forward", "benchmark_family",
                           "cost_sensitivity"],
    "paper_ready":        ["paper_readiness_all_11_gates",
                           "alternative_data_pit"],
}
```

这是 Python 不是 YAML。理由：CLAUDE.md/AGENTS.md 是给人和 agent 看的规则，Python 字典是给运行时看的依赖图。**用 dict + dict.get() 表达比 YAML + Pydantic + loader 简单得多**。

### 4.2 Runs（JSONL 追加日志）

```python
# reports/_harness_runs.jsonl 单文件 append-only
{
  "run_id": "uuid",
  "strategy_name": "qqq_pullback_15m",
  "spec_hash": "abc123...",
  "gate_name": "leakage_defaults",
  "gate_version": 2,
  "status": "pass",
  "reason": "...",
  "started_at": "2026-05-17T15:00:00Z",
  "completed_at": "2026-05-17T15:00:01Z",
  "evidence_paths": [...],
  "metrics": {...},
  "agent": "claude_code",         # 或 "codex", "manual", "cli"
  "cli_command": "oc strategy advance qqq_pullback_15m.yaml"
}
```

这就是 Codex 提案的 `EvidenceManifest` + `AgentRunTrace` 的合并 + 极简版。

**Evidence Manifest 是查询，不是存储**：

```python
def evidence_for(strategy_name: str, spec_hash: str | None = None) -> dict[str, GateResult]:
    """读 _harness_runs.jsonl，按 (strategy, spec_hash, gate_name) 取最新一条。"""
```

**Agent activity 是查询**：

```python
def recent_agent_activity(strategy: str | None = None, n: int = 20) -> list[Run]:
    """读最后 n 条，可按 strategy 过滤。"""
```

**Trace 是同一份数据**：每条 run 已经含有 agent、command、spec_hash、artifacts——这就是 trace。不需要 OTel span_id/parent_span_id（除非将来接外部 collector，那时再加）。

### 4.3 三个 CLI 命令

```bash
oc harness check <spec>                    # 跑当前 stage 应跑的所有 gate
oc strategy advance <spec> [--apply]       # 检查能否进入下一 stage，列出阻断项和 next command
oc strategy diff <spec> --vs <hash>        # 对比当前 spec 与历史版本的 gate metrics 差异
```

`oc strategy research-workflow`、`oc harness policy-list`、`oc harness evidence`、`oc harness trace-list` 等命令**都不需要单独存在**：

- `research-workflow` = `advance` 在 researching → candidate_selected → promotion_pending 上循环
- `policy-list` = `python -c "from open_composer.harness.gates import GATE_REGISTRY; print(...)"` 一行
- `evidence` = `advance --json` 的一部分
- `trace-list` = `tail reports/_harness_runs.jsonl`

**少即是多**：1 个核心命令（`advance`）+ 2 个查询命令 替代 7 个新命令。

---

## 五、修订后的执行计划

### Phase 0：修复 + 合并（最优先，1-2 个会话）

**修复**：
| # | 文件 | 修复 |
|---|------|------|
| F1 | `research_report.py:306` | `leakage_defaults` 实际读取 `spec.execution.signal_on/fill_assumption` |
| F2 | `promotion.py:706` | 删掉 `market_proxy` / `sector_theme_proxy` 的硬编码占位；要么实际实现，要么删除这两个键（不要"装样子") |
| F3 | `parameter_sweep.py:629` | 实现 Bailey-de Prado DSR 代理公式（计算 `E[max SR]` 并返回 `computed_dsr`） |
| F4 | `promotion.py:1074` | `_code_correctness_pass` 重命名为 `_expression_safety_pass`，或扩展为真实代码正确性检查（接 ruff + pytest 状态） |
| F5 | `promotion.py:1026` | `research_failures` 只看 `blocked`，不看 `warning`（否则 research_pass 永远 fail） |
| F6 | 各研究模块 CLI 入口 | 在 `oc strategy *` 命令开始时调用 `register_strategy_version`，保证每次研究迭代都有版本 |

**合并**：
| # | 操作 |
|---|------|
| C1 | 用 `GateResult` 替代 `PromotionCheck`，让 `promotion.py` 返回 `list[GateResult]` |
| C2 | 删除 `FivePassChecks`，让 5 通过状态从 gate 列表派生（`workflow_pass = all(g.status == "pass" for g in workflow_gates)`） |
| C3 | 删除 `ResearchContract.required_checks`（与 GATE_REGISTRY 重复），保留 `leakage_requirements` 等 metadata 用作文档 |

**验收**：所有现有测试通过；`reports/research/*-promotion.json` 字段结构未变（向后兼容），但内部抽象统一。

### Phase 1：Gate 注册表（核心 harness）

**交付物**：
1. `open_composer/harness/__init__.py` — 包入口
2. `open_composer/harness/gates.py` — `GateResult` + `gate()` 装饰器 + `GATE_REGISTRY`
3. `open_composer/harness/stages.py` — `STAGE_REQUIREMENTS` dict + `gates_for_stage()`
4. 把现有 11 个 `_*_check` 函数 + 11 个 `paper_readiness_*` 检查函数注册到 `GATE_REGISTRY`
5. `open_composer/cli.py` — `oc harness check <spec>`
6. `tests/test_harness_gates.py`

**关键约束**：**不引入新的 Pydantic model，不引入 YAML manifest，不引入 loader**。GATE_REGISTRY 就是一个 module-level dict。

**验收**：
- `oc harness check <spec>` 输出所有 gate 的 status 表
- 删除任何 gate 后，repo_check 检测到 STAGE_REQUIREMENTS 引用了未注册 gate

### Phase 2：Runs 日志 + 查询

**交付物**：
1. `open_composer/harness/runs.py` — `append_run()` + `query_runs()` + `evidence_for()`
2. 修改所有 gate 调用路径，运行后自动 `append_run`
3. `oc strategy advance <spec>` — 跑当前 stage 应过 gate，列出 blockers 和 next command
4. `tests/test_harness_runs.py`

**`advance` 命令的输出示例**：
```
Strategy: qqq_pullback_15m  |  Current stage: researching  |  Target: candidate_selected

Required gates for advancement:
  ✅ parameter_sweep_trial_ledger    (last run 2026-05-17 14:00, pass)
  ❌ dsr_proxy                       MISSING — never run for current spec_hash
  ❌ oos_evidence                    MISSING

Next command:
  uv run oc strategy parameter-sweep strategy_specs/drafts/qqq_pullback_15m.yaml \
    --param risk.stop_loss_pct=0.8,1.0,1.2 --max-candidates 27

After that:
  uv run oc strategy blind-test strategy_specs/drafts/qqq_pullback_15m.yaml
```

**验收**：
- 一个新策略从 draft 到 paper_ready 只需要重复 `oc strategy advance --apply` 直到无 blockers
- 没有阻断时，命令打印"Ready to advance to <next_stage>"

### Phase 3：版本对比

**交付物**：
1. `open_composer/cli.py` — `oc strategy diff <spec> --vs <hash>`
2. `open_composer/harness/diff.py` — 拉取两个 spec_hash 的 gate metrics，输出差异表
3. `tests/test_harness_diff.py`

**示例输出**：
```
qqq_pullback_15m
  vs spec_hash abc123 (2 days ago)

Gate                | Before  | After   | Delta
--------------------|---------|---------|----------
backtest.sharpe     | 1.21    | 1.18    | -0.03 ⚠
factor_lab.rank_ic  | 0.082   | 0.091   | +0.009
dsr_proxy           | 0.15    | -0.02   | -0.17 ❌
execution_reality   | warning | pass    | improved

Verdict: research_pass status REGRESSED (dsr_proxy went negative)
```

**这是 Codex 没提到、v1 没提到、但研究流程最缺的能力**。

### Phase 4：CLAUDE.md/AGENTS.md 锚点（Policy as Markdown）

**不创建** `policies/harness.yaml`。改为：

在 `CLAUDE.md` / `AGENTS.md` / `.agents/skills/*/SKILL.md` 里加 HTML 注释锚点：

```markdown
- Real-money broker writes are out of scope. <!-- gate: real_money_blocked -->
- LLM features must be PIT packets. <!-- gate: llm_pit_required -->
```

`open_composer/harness/policy_audit.py`：
1. 扫描所有 .md 文件提取 `<!-- gate: NAME -->` 锚点
2. 比对 `GATE_REGISTRY` 中是否存在同名 gate
3. 在 `oc repo check --strict` 中验证 100% 覆盖

这样 **CLAUDE.md/AGENTS.md 本身就是 policy manifest**，不需要平行文件。

### Phase 5：Dashboard 一个新视图

**不做全面 cockpit 改造**。只加一个东西：

每个策略卡片底部加 "Next Action" 区域，调用 `GET /api/dashboard/next-action/<spec>` 返回：

```json
{
  "strategy": "qqq_pullback_15m",
  "current_stage": "researching",
  "blockers": ["dsr_proxy: missing"],
  "next_command": "uv run oc strategy parameter-sweep ...",
  "estimated_steps_remaining": 4
}
```

后端只是 `oc strategy advance <spec> --json` 的包装。

---

## 六、不做的事（明确列表）

| 不做 | 理由 |
|------|------|
| `HarnessPolicyManifest` YAML | CLAUDE.md/AGENTS.md 加锚点就够，不要平行真相 |
| `ResearchWorkflowHarness` 状态机类 | `advance` 命令 + `STAGE_REQUIREMENTS` dict 就够 |
| `AgentRunTrace` 独立模型 | 单一 `_harness_runs.jsonl` 同时是 trace |
| OTel span_id/parent_span_id 字段 | 个人工作台用不到，需要时再加 |
| `EvidenceManifest` Pydantic 模型 | 是 `_harness_runs.jsonl` 的查询视图，不是存储 |
| `oc harness policy-list/evidence/trace-list` 命令 | 1 行 Python 或 `tail` 就能查 |
| Dashboard cockpit / GateMatrix / DecisionCard 三视图 | 一个 "Next Action" 区就够 |
| `SkillPolicyPack` YAML front-matter | 加复杂度无新能力 |
| 五通过抽象 | 是 GATE_REGISTRY 的派生视图，不是独立概念 |
| `ResearchContract.required_checks` 字段 | 与 GATE_REGISTRY 重复 |

---

## 七、与 Codex 报告的关系

**保留 Codex 的核心洞察**：规则需要从文本变成运行时门控。

**拒绝 Codex 的实现路径**：5 层架构是 LangGraph 范式，不适合 file-first CLI 工作台。

**用更简单的方式实现同一目标**：2 个概念（Gates + Runs）+ 1 个核心命令（`advance`）+ CLAUDE.md 锚点 = 同样达到"规则机器可验证"。

Codex 报告里的具体技术内容仍然有用（防泄漏要求、PIT 包字段、执行现实建模、5 通过分类标签），都可以作为**具体 gate 的实现细节**，而不是新抽象层。

---

## 八、关键量化阈值（沿用 v1）

这些是经过外部学术调研验证的，**作为 gate 内部的判定值**继续使用：

| Gate | 阈值 |
|------|------|
| `dsr_proxy` | `pass: DSR > 0; warning: -0.1 < DSR <= 0; blocked: DSR <= -0.1` |
| `pbo` (when CPCV available) | `pass: PBO < 0.10; blocked: PBO >= 0.20` |
| `oos_degradation` | `pass: OOS/IS Sharpe ratio > 0.5; warning: 0.3-0.5; blocked: < 0.3` |
| `walk_forward` | `pass: ≥ 3 folds 都为正; warning: 部分正; blocked: 多数负` |
| `execution_reality.bar_participation` | 当前实现合理（>5% 警告，>10% 阻断） |

---

## 九、优先级

```
立即（Phase 0，1-2 天）:
  F1-F6 bug 修复 + C1-C3 抽象合并

短期（Phase 1-2，1 周）:
  Gate 注册表 + oc strategy advance

中期（Phase 3，3-5 天）:
  oc strategy diff（版本对比，最重要的研究能力补全）

长期（Phase 4-5，按需）:
  CLAUDE.md 锚点 policy audit
  Dashboard Next Action 区
```

---

## 十、给读者的判断建议

**如果只能做一件事**：Phase 0 的 6 个 bug 修复 + 3 个抽象合并。
理由：当前系统的"门控装样子"问题（leakage 永远 ok、benchmark_family 永远 warning、research_pass 永远 fail、DSR 永远 None）让所有结果都不可信。修这些比加任何新抽象都重要。

**如果还能做一件事**：`oc strategy advance`。
理由：用户当前需要记忆"先 backtest 再 parameter-sweep 再 promotion-report"的专业流程。`advance` 把这个流程变成自动推进，是 Codex 提案的 `ResearchWorkflowHarness` 的最小可用形态。

**如果还能做一件事**：`oc strategy diff`。
理由：研究的本质是迭代。当前没有任何机制告诉用户"这次改动让指标变好了还是变差了"。这是策略研究的核心循环缺失。

剩下的（policy manifest、agent trace、dashboard cockpit）**可以无限期推迟**，不影响系统可信度和可用性。

---

*本修订版基于独立阅读 promotion.py（1209 行）、research_report.py、strategy_dag.py 后形成的判断，不是对 Codex 报告的复述。批评 Codex 是为了让其有用的部分能落地，而不是否定其调研价值。*
