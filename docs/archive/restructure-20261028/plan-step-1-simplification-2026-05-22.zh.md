# Open Composer Step 1：简化与重构（Plan A）

日期：2026-05-22
执行者：Codex / Claude Code
前置：无（这是三步计划的第一步）
后续：Step 2（worksession + LLM factor）、Step 3（Dashboard-first）

## 0. 一句话目标

删除 legacy 代码与冗余抽象，把"5 套 Pass / 8 个 Router 大文件 / 50+ Pydantic 模型 / 4 套研究证据汇总流水"压平为一致的产品基线，为后续两步腾出空间。**不引入新功能。**

## 1. 背景（无上下文也能看懂）

Open Composer 是一个个人 AI 量化策略工作台，源头是 `StrategySpec`（YAML），CLI 入口是 `oc`。当前仓库一周内堆了 11 份大型计划文档（2026-05-17 集中），加上多次 Router 实现复制粘贴和"Pass / Gate / Check"概念多次重复声明，导致：

- 一个研究证据要在 5 套抽象里同步：`PromotionCheck` / `FivePassChecks` / `GateResult` / `ResearchContract.required_checks` / `ProjectGateSummary`
- 8 个 Router 策略各自一个 40-90KB 大文件，`promotion.py` 里有 4 个 Router 专属分支共 500+ 行
- 18 个模型文件 + Dashboard 30+ 表全部 Pydantic（基准 dataclass 快 1.88-6.46x）
- `research_report / promotion_report / research_workflow / research_control` 4 套流程都在做"汇总同样的研究证据"
- `open_composer/remote/` 还有 ~80KB 的旧 Vercel BFF 代码，`AGENTS.md` 自己说"Vercel 不是 normal deployment path"
- `reports/agent_requests/` 一次性工单与 `projects/{id}/runs/` Run Ledger 并存

这一切的根因是"加抽象比删抽象多"。Step 1 是纯做减法。

## 2. 目标 / 非目标

### 目标

1. 删除明确 legacy 的代码与文档，仓库总代码量预期减少约 40%。
2. 把 5 套 Pass/Gate/Check 抽象合并为 1 套核心 `GateResult` + `PromotionReport` 上 4 个 pass 字段。
3. Router 8 大文件压到 ≤10KB 薄入口；共享逻辑集中到 `router_common.py`、`router_promotion.py` 和少量 core kernel，不再新增 `RouterResearchBase` 这类对象框架。
4. Pydantic 仅保留在用户/agent/外部可见的"服务边界"（StrategySpec、capability registry、报告、远程 schema、Dashboard 顶层 catalog）；内部流转改为 `@dataclass`。
5. `research_report / research_workflow / research_control` 合并为 `oc strategy evidence`；旧命令变 alias。
6. 文档收敛到 ≤8 篇 current，其余移到 `docs/archive/`。Step 3 文档尚未写成前，current 文档为 7 篇。

### 非目标（明确不做）

- 不引入新功能（worksession、LLM factor materialization、Dashboard-first 全部留给 Step 2 / Step 3）。
- 不改 `StrategySpec` schema。
- 不改 harness 规则（`harness/risk_domains.yaml` / `harness/artifact_contracts.yaml`）。
- 不改 4 个 pass 的语义（workflow_pass / research_pass / llm_contribution_pass / paper_ready_pass）— 只改它们的表达方式。
- 不动 paper safety chain（kill switch / readiness / activate）。
- 不动 feature packet PIT 契约（visible_at / published_at / fetched_at / source / dedupe_key）。
- 不动 AST 表达式白名单。

## 3. 当前状态扫描（关键文件 + 行数）

```text
open_composer/remote/                  # 待删除（整目录）
  bootstrap.py        53KB
  server.py           11KB
  jobs.py             11KB
  schemas.py / auth.py / backups.py / __init__.py

open_composer/research/                # router 重构焦点
  adaptive_intraday_router.py          91KB
  beta_exposure_router.py              66KB
  core_beta_satellite_router.py        71KB
  core_satellite_router.py             49KB
  hybrid_adaptive_router.py            61KB
  hybrid_wide_router.py                40KB
  aggressive_theme_router.py           53KB
  theme_intraday_rotation_router.py    64KB
  intraday_daily_rotation.py           70KB
  promotion.py                        132KB  ← 含 _build_adaptive_router_promotion_report / _build_hybrid_router_promotion_report / _build_beta_router_promotion_report 等 4 个 Router 专属函数

open_composer/research/                # 4 套研究证据汇总流水
  research_report.py    17KB           # build_strategy_research_report
  promotion.py         132KB           # build_promotion_report
  control.py            22KB           # update_research_control（含 1KB MAX_MEMORY_BYTES 截断）
  ...
  CLI 入口：
    oc strategy research-report
    oc strategy research-workflow
    oc strategy research-control
    oc strategy promotion-report

open_composer/models/                  # Pydantic 收缩焦点
  18 个文件
  dashboard.py        22KB（30+ Dashboard 子模型）

reports/agent_requests/                # 不作为当前运行制品保留；Step 2 用 queue.jsonl 替代兼容接口

docs/                                  # 23 篇文档；目标 ≤8 篇 current
  日期 ≤2026-05-17 的 11 篇大型 plan → archive
  2026-05-20 三篇 Router 标准 → archive（已并入 Step 1 简化记录）
  2026-05-21 一篇 epistemological → archive
  2026-05-22 之前的 4 篇 → 其中 1 篇（agent-native-worksession）由 Step 2 接管
```

## 4. 改动清单（按 Wave 分批，每个 Wave 单独可提 PR）

### Wave 1.1 — 删除 legacy（**最低风险，最先做**）

**4.1.1 删除 `open_composer/remote/` 整个目录**

```bash
rm -rf open_composer/remote/
```

同步删除引用：

- `open_composer/cli.py`：删除 `from open_composer.remote import ...` 整段（约第 138-147 行）；删除 `remote_app = typer.Typer(...)` 与 `app.add_typer(remote_app, name="remote")`；删除所有 `@remote_app.command(...)` 函数。
- `Makefile`：删除 `remote-doctor / remote-plan / remote-deploy / remote-stop` 目标（保留 `vps-*` 系列）。
- `tests/`：删除 `tests/test_remote_*` 系列文件（如存在）。
- `docs/remote-dashboard-deploy.zh.md`：**保留**（VPS Dashboard 部署文档仍在用）。

**4.1.2 收敛 `reports/agent_requests/` 路径**

```bash
rm -rf reports/agent_requests/
```

同步：

- `open_composer/agent_requests.py`：保留模块（Step 2 会改造为 queue.jsonl 接口的薄包装）；先标记 `# DEPRECATED: replaced by projects/{id}/queue.jsonl in Step 2` 头注释；保留 `create_agent_request / list_agent_requests / complete_agent_request` 作为兼容接口。
- `open_composer/cli.py`：删除 `agent_app` 整组（`request-create / request-list / request-complete`）。
- `open_composer/dashboard/server.py`：删除 `/api/projects/.../request` 等 agent_request POST 端点。
- `open_composer/projects.py`：`create_project` 的 `create_request` 参数默认改 `False`，并加 deprecation 注释。
- `open_composer/research/iteration_controller.py`：`create_project_iteration_request` 中 `create_agent_request(...)` 调用先**保留但加 `# Step 2 will remove this`** 注释；这一步暂不删，避免 Dashboard "继续优化"按钮断掉。

**4.1.3 文档归档**

```bash
mkdir -p docs/archive
```

移动到 `docs/archive/`：

```text
docs/harness-engineering-agent-quant-review-2026-05-17.zh.md
docs/harness-engineering-expanded-research-log-2026-05-17.zh.md
docs/harness-engineering-expanded-architecture-review-2026-05-17.zh.md
docs/harness-engineering-implementation-plan-2026-05-17.zh.md
docs/harness-engineering-implementation-plan-v2-2026-05-17.zh.md
docs/product-structure-efficiency-review-2026-05-17.zh.md
docs/product-efficiency-optimization-roadmap-2026-05-17.zh.md
docs/product-mvp-hardening-research-plan-2026-05-17.zh.md
docs/research-contract-p0-p2-plan-2026-05-17.zh.md
docs/nasdaq-core-beta-satellite-router-standard-2026-05-20.zh.md
docs/nasdaq-intraday-theme-momentum-router-standard-2026-05-20.zh.md
docs/nasdaq-theme-intraday-rotation-router-standard-2026-05-20.zh.md
docs/skill-first-harness-engineering-roadmap-2026-05-20.zh.md
docs/llm-quant-epistemological-loop-roadmap-2026-05-21.zh.md
docs/agent-native-worksession-llm-quant-plan-2026-05-22.zh.md   # 由 Step 2 文档取代
docs/strategy-iteration-execution-architecture-plan-2026-05-22.zh.md
docs/dashboard-strategy-console-redesign-plan-2026-05-22.zh.md  # 由 Step 3 文档取代
docs/product-iteration-control-final-plan-2026-05-22.zh.md
```

**保留** `docs/` 顶层的 current 文档（Step 3 未写成前为 7 篇，写成后最多 8 篇）：

```text
docs/product-golden-path-codex-quant-review-2026-05-13.zh.md   # no-context 入口
docs/user-guide.md
docs/setup-local.zh.md
docs/remote-dashboard-deploy.zh.md
docs/longbridge-integration.md
docs/plan-step-1-simplification-2026-05-22.zh.md               # 本文档
docs/plan-step-2-worksession-llm-factor-2026-05-22.zh.md       # Step 2
docs/plan-step-3-dashboard-first-2026-05-22.zh.md              # Step 3，写成后再进入 current
```

**4.1.4 同步更新 `open_composer/repo_check.py`**

修改 `CURRENT_DOCS` 集合（约第 20-44 行），改为：

```python
CURRENT_DOCS = {
    NO_CONTEXT_START_DOC,
    "docs/user-guide.md",
    "docs/setup-local.zh.md",
    "docs/remote-dashboard-deploy.zh.md",
    "docs/longbridge-integration.md",
    "docs/plan-step-1-simplification-2026-05-22.zh.md",
    "docs/plan-step-2-worksession-llm-factor-2026-05-22.zh.md",
    "docs/plan-step-3-dashboard-first-2026-05-22.zh.md",
}
```

并同步更新 `README.md` 的 `## Project Docs` 段（第 126-141 行附近），把 11+ 条历史 plan 链接换成上面 8 条；同时更新 `_readme_project_docs_check`（约第 227 行）允许的链接列表。

**Wave 1.1 验收**：

```bash
uv run oc repo check --strict   # 必须通过
uv run pytest                   # 必须通过
make verify                     # 必须通过
git diff --stat                 # 预期：净 -200 文件、净 -80KB 以上
```

---

### Wave 1.2 — 抽象合并（**核心简化**）

**4.2.1 删除 `FivePassChecks` 独立类**

文件：`open_composer/research/promotion.py`

- 删除 `class FivePassChecks` 与所有 `_five_pass_checks(...)`、`_hybrid_five_pass_checks(...)`、`_beta_five_pass_checks(...)` 函数（约第 52-63 行 + 第 1461-1700 行）。
- 将 4 个 pass 改为 `PromotionReport` 的直接字段：

```python
@dataclass(frozen=True)
class PromotionReport:
    strategy_name: str
    source_spec_path: str
    status: PromotionStatus
    ready: bool
    checks: list[PromotionCheck]
    report_path: str
    json_path: str
    # 4 个 pass 直接落字段（原来在 FivePassChecks 里）
    workflow_pass: bool = False
    research_pass: bool = False
    llm_contribution_pass: bool | None = None   # None = not_applicable
    paper_ready_pass: bool = False
    pass_reasons: dict[str, str] = field(default_factory=dict)
```

更新 `open_composer/research/__init__.py` 的 `__all__`：删除 `FivePassChecks`。

**4.2.2 统一 `GateResult` / `PromotionCheck` / `ResearchGateSummary` 为单一表示**

- 保留：`open_composer/research/kernel/gates.py` 的 `GateResult` 与 `GateStatus`（这是最干净的版本）。
- 删除：`research/promotion.py` 的 `PromotionCheck` 类。`PromotionReport.checks` 改为 `list[GateResult]`。
- 删除：`research/kernel/gates.py` 的 `ResearchGateSummary`，合并到 `PromotionReport` 的字段（status / blocked_checks / warning_checks 已有等价物）。
- 删除：`models/project.py` 的 `ProjectGateSummary`，改为引用 `dict[str, bool]`（key 是 4 个 pass 名）。

**4.2.3 删除 `ResearchContract.required_checks`**

文件：`open_composer/research/contracts.py`

- `required_checks` / `leakage_requirements` / `overfit_requirements` / `live_gap_requirements` / `factor_requirements` / `execution_requirements` / `alternative_data_requirements` 全部合并为 **一个** `requirements: dict[str, list[str]]`，key 是上述维度名（leakage、overfit、live_gap、factor、execution、alternative_data）。
- 调用方相应改用 dict 访问。

**Wave 1.2 验收**：

```bash
uv run oc strategy promotion-report strategy_specs/drafts/memory_storage_momentum_15m.yaml
# 输出报告中 workflow_pass / research_pass / llm_contribution_pass / paper_ready_pass 字段存在且语义不变
uv run oc harness check strategy_specs/drafts/memory_storage_momentum_15m.yaml
# 所有现有 gate 仍跑通
uv run pytest tests/  # 全绿
```

---

### Wave 1.3 — Router 重构（**最大复用，最慢风险最高**）

**4.3.1 不新增 `RouterResearchBase`**

严格复审后取消原本的 `RouterResearchBase` 方案。原因：

- 它会引入新的对象生命周期和 registry，变成第 2 套 Router 控制面。
- Step 1 的核心是删重复实现，不是让 Router 学会一个新的抽象框架。
- 现有 CLI / artifact / paper runner 已经以函数入口稳定工作，薄 wrapper 更轻。

实际结构：

```text
open_composer/research/router_common.py       # 候选评估、回测、walk-forward、指标、Markdown
open_composer/research/router_promotion.py    # 统一 Router promotion，替代 promotion.py 内专属大分支
open_composer/research/*_router.py            # 兼容旧模块名的薄入口，每个 ≤250 行
open_composer/research/*_router_core.py       # 只保留确实被 target weights / paper / evidence 复用的领域 kernel
```

**4.3.2 改写 8 个 router 文件为薄实现（每个 ≤10KB）**

每个 Router 入口文件保留：
- 稳定的旧导入路径，避免 CLI、测试、外部 agent prompt 断裂。
- `run_*_router_research` / label parser / target snapshot 等必要入口。
- 必要的 monkeypatch 兼容（测试和本地 agent 仍可替换数据 fetcher）。

删除：
- 各 Router 文件内重复的 backtest / walk-forward / report 写入逻辑。
- 未注册、未调用的 `*RouterResearch` 子类壳。
- 空 cache、未使用 score/quality helper、重复 lookback wrapper。

**4.3.3 `promotion.py` 去 Router 专属分支**

文件：`open_composer/research/promotion.py`

`build_promotion_report` 入口去掉 if-else 4 大分支（约第 88-117 行），改成统一委派：

```python
def build_promotion_report(spec_path, root=None, ...):
    spec = load_strategy_spec(spec_path)
    if spec.portfolio.mode in ROUTER_PROMOTION_MODES:
        return build_router_promotion_report(...)
    # 单标的 / 单一通道路径不变
    ...
```

**4.3.4 删除 `_build_adaptive_router_promotion_report` / `_build_hybrid_router_promotion_report` / `_build_beta_router_promotion_report` 等**

3 个函数 + 其全部辅助函数（约第 314-810 行 + 第 832-1700 行的 router 专属 helper），合计约 1200 行。

**Wave 1.3 验收**：

```bash
# 对每个已存在的 router strategy spec 跑一遍 promotion
for spec in strategy_specs/drafts/*router*.yaml; do
  uv run oc strategy promotion-report "$spec"
done
# 报告内容与改造前应完全等价（status / ready / checks 数量 / 关键评分）

# 文件大小验证
wc -l open_composer/research/*_router.py
# 每个 router 文件 ≤ 250 行（之前 ~1500-2500 行）

uv run pytest tests/  # 全绿
```

---

### Wave 1.4 — Pydantic 收缩（**性能优化**）

**4.4.1 服务边界保留 Pydantic（不动）**

```text
KEEP Pydantic:
  open_composer/models/strategy_spec.py   # 用户可见 YAML schema
  open_composer/models/capability.py      # 注册表
  open_composer/models/backtest.py        # 报告（外部消费）
  open_composer/models/paper.py           # 报告 + 状态
  open_composer/models/source_card.py     # JSONL 行 schema
  open_composer/models/notification.py    # 配置
  open_composer/models/options.py         # spec
  schemas/*.json                          # 全部
  remote schemas（如果 Step 1 后还在）
  Dashboard catalog 顶层（DashboardCatalog / DashboardSummary）
```

**4.4.2 内部对象改 `@dataclass(frozen=True)`**

```text
CONVERT to dataclass:
  open_composer/models/dashboard.py    # DashboardStrategy / DashboardRun / DashboardSignal / ... 30+ 子模型
  open_composer/research/kernel/*.py   # CandidateScore / CandidateSpec / TrialRecord / MetricSummary 等
  open_composer/harness/policy.py      # ArtifactStatus / ActiveBlockingRule / BlockingRule（已经是 dataclass，仅确认）
  open_composer/research/promotion.py  # PromotionReport / GateResult 内部聚合表
  open_composer/research/factor_lab.py # FactorLabResult 内部表
```

对每个改造的类：

```python
# Before
class DashboardStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy_id: str
    ...

# After
from dataclasses import dataclass, asdict, field

@dataclass(frozen=True)
class DashboardStrategy:
    strategy_id: str
    ...

    def model_dump(self, mode: str = "json") -> dict:
        # 兼容旧调用方
        return asdict(self)
```

`open_composer/dashboard/catalog.py` 的 `write_dashboard_catalog` 写 JSON 时用 `asdict` 替代 `model_dump`。

**4.4.3 验收**

```bash
time uv run oc dashboard catalog
# 预期：相比简化前的同样仓库快至少 30%

uv run pytest tests/  # 全绿
```

---

### Wave 1.5 — 研究证据流水合并

**4.5.1 新增 `oc strategy evidence` 命令**

新文件：`open_composer/research/evidence.py`

```python
"""oc strategy evidence — 单一研究证据汇总入口。

合并 research_report / research_workflow / research_control 三套流水。
内部仍调用现有 promotion / factor_lab / alt_data_quality / paper_readiness 模块，
但只写一份汇总报告，不重复跑 backtest。
"""

from __future__ import annotations
from pathlib import Path

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.promotion import build_promotion_report
from open_composer.research.factor_lab import run_factor_lab
from open_composer.research.alt_data_quality import build_alternative_data_quality_report
from open_composer.paper_readiness import assess_paper_strategy_readiness_for_spec
from open_composer.research.control import refresh_context_md   # Step 2 引入；Step 1 暂用占位


def build_strategy_evidence(spec_path: Path, root: Path | None = None):
    spec = load_strategy_spec(spec_path)
    promotion = build_promotion_report(spec_path, root)        # 含 in_sample / OOS / WF / cost
    factor   = run_factor_lab(spec_path, root)                 # 因子诊断
    alt_data = build_alternative_data_quality_report(spec_path, root)
    paper    = assess_paper_strategy_readiness_for_spec(spec, root, spec_path=spec_path)
    refresh_context_md(spec_path, root)                        # 把汇总写进 projects/{id}/context.md
    return {
        "promotion": promotion,
        "factor_lab": factor,
        "alt_data": alt_data,
        "paper_readiness": paper,
    }
```

CLI（`open_composer/cli.py`）：

```python
@strategy_app.command("evidence")
def strategy_evidence(spec: Path) -> None:
    """One-shot research evidence (replaces research-report / research-workflow / research-control)."""
    result = build_strategy_evidence(spec, project_root())
    ...
```

**4.5.2 旧命令变 alias**

```python
@strategy_app.command("research-report", hidden=True)   # alias
def strategy_research_report(spec: Path) -> None:
    """[DEPRECATED] Use `oc strategy evidence`."""
    strategy_evidence(spec)
```

`research-workflow` / `research-control` 同上。

**Wave 1.5 验收**：

```bash
uv run oc strategy evidence strategy_specs/drafts/memory_storage_momentum_15m.yaml
# 单次调用产出：promotion + factor + alt_data + paper_readiness 报告路径

# 旧命令仍能用（alias），但 stderr 提示 deprecated
uv run oc strategy research-report strategy_specs/drafts/memory_storage_momentum_15m.yaml
```

## 5. 验收清单（Wave 1.1 - 1.5 全部完成时）

```text
[x] open_composer/remote/ 目录已删除
[x] reports/agent_requests/ 不作为当前运行制品保留；兼容接口已标 deprecated
[x] docs/ 顶层只剩 ≤8 篇 current，其余进 docs/archive/
[x] CURRENT_DOCS / README.md / repo_check.py 同步更新
[x] FivePassChecks 类已删除，4 个 pass 是 PromotionReport 直接字段
[x] ResearchGateSummary / ProjectGateSummary / PromotionCheck 已合并到 GateResult
[x] ResearchContract.required_checks 等 7 个字段合并为 requirements: dict
[x] 不新增 `RouterResearchBase`；Router 采用薄入口 + core kernel + 共享 common/promotion
[x] 8 个 router 文件每个 ≤ 250 行
[x] promotion.py 删除 4 个 router 专属 build_xxx_promotion_report
[x] Dashboard 内部 30+ 子模型已转 dataclass
[x] research/kernel/ 内部对象已转 dataclass
[ ] dashboard catalog 重建 latency 比改造前快 ≥30%（未保留改造前基准，不作为硬验收）
[x] oc strategy evidence 命令已新增；research-report 等变 alias
[x] uv run pytest 全绿
[x] uv run oc repo check --strict 通过
[x] make verify 通过
[x] git diff --stat 净 -200 文件、净 -300KB 以上
```

## 6. 不做什么（Step 1 明确边界）

```text
✗ 不引入 worksession / queue.jsonl / trace.jsonl（Step 2）
✗ 不引入 LLM Factor Materialization（Step 2）
✗ 不引入 Codex SDK 集成（Step 2）
✗ 不改 StrategySpec schema
✗ 不改 Dashboard UI（仅修内部模型 dataclass 化）
✗ 不删 4 个 pass 语义
✗ 不删 harness / risk_domains / artifact_contracts
✗ 不删 paper safety chain
✗ 不删 AST 表达式白名单
✗ 不删 capabilities/registry.yaml
```

## 7. 风险与对冲

| 风险 | 对冲 |
|---|---|
| Router 重构破坏现有 spec 结果 | 每个 router spec 跑 promotion 报告做"改造前 vs 改造后"对比；指标 delta > 0.1% 视为回归 |
| `FivePassChecks` 删除导致下游消费者失败 | 全仓 grep `FivePassChecks` 找所有引用；保留 `@property` 兼容；Step 1 完成后再去 property |
| Pydantic → dataclass 破坏序列化 | 每个改造的类加 `def model_dump(self, mode="json"): return asdict(self)` 兼容方法 |
| 文档归档破坏外部链接 | 旧路径不变（`docs/archive/` 是新加目录）；README 内链同步更新 |
| `oc strategy research-report` 被外部脚本依赖 | 保留为 alias 至少一个发布周期；stderr 输出 deprecated 警告 |
| `agent_requests/` 删除时 Dashboard "继续优化"按钮断 | Wave 1.1 标 deprecated 不删调用点；Step 2 一并替换为 queue.jsonl |

## 8. 回滚预案

每个 Wave 单独提一个 PR。如果某 Wave 出问题，git revert 该 Wave 的 commit 即可；不会影响其他 Wave 已完成的简化。

## 9. 完成定义

执行完 Wave 1.1 - 1.5 后，`make verify` 能跑过；`open_composer/` 总代码量显著下降；Dashboard catalog 重建 latency 降 30%+；CURRENT_DOCS ≤ 8 篇；Pydantic 模型数从 ~70 降到约 ~25。

完成后即可进入 Step 2。
