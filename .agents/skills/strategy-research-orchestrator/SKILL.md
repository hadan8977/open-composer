---
name: strategy-research-orchestrator
description: >
  Coordinate strategy research, optimization, promotion and paper readiness
  using applicable native gates. Adapt to the research object and lifecycle;
  components and method maintenance need no unrelated strategy or deployment.
---

# Strategy research tools and routing

Use [idea-to-paper](../idea-to-paper/SKILL.md) to frame an economic question, [research workflow](../../../research/README.md) for team continuity, and [the review standard](../../../docs/research-plan-review-standard.zh.md) for acceptance. Reuse the existing complete task, evidence and cumulative budgets.

| Purpose | Native entry or specialist |
|---|---|
| Strategy behavior | Draft/load a StrategySpec; `uv run --no-sync oc spec validate <spec>` before strategy code/Pine. |
| Risk-dependent artifacts | `uv run --no-sync oc harness plan <spec>`; read its detected domains and requirements. |
| Required inputs | `uv run --no-sync oc spec capabilities <spec> --json`; [data review](../data-capability-reviewer/SKILL.md). Use [capability-evaluator](../capability-evaluator/SKILL.md) for registry/fixture hygiene. |
| Unstable external claims | [source-researcher](../source-researcher/SKILL.md). |
| Economic admission | `uv run --no-sync oc research direction-check <path>` and `uv run --no-sync oc research iteration validate <iter_id>`; apply campaign and knowledge gates where the contract requires them. |
| Bounded candidate evaluation | Registered search and trial accounting; `uv run --no-sync oc strategy parameter-sweep <spec>` only for an admitted search. |
| Refresh evidence | `uv run --no-sync oc strategy evidence <spec>` after relevant artifact changes; do not use the deprecated hidden `research-control` path. |
| Optimized strategy validity | [backtest-forensics](../backtest-forensics/SKILL.md). |
| Daily-open, leveraged-ETF or paper-auto execution | [execution-reality-reviewer](../execution-reality-reviewer/SKILL.md). |
| Lifecycle assessment | `uv run --no-sync oc strategy promotion-report <spec>` or `uv run --no-sync oc paper readiness <spec>` when applicable. |
| Paper activation | `uv run --no-sync oc harness verify <spec>` and [paper-auto-safety-reviewer](../paper-auto-safety-reviewer/SKILL.md), within effective order authorization. |

The table is a reference, not a mandatory sequence. Dependent computation requires its actual input and economic admission; bounded preparation can resolve gaps without an empty StrategySpec.

Use native outputs where consumers require them: `reports/harness/plans/{strategy}.json`, research briefs/evidence manifests under `reports/research/`, and existing task state under `reports/research/control/`. [Risk domains](../../../harness/risk_domains.yaml), [artifact contracts](../../../harness/artifact_contracts.yaml), and [skill routing](../../../harness/skill_manifest.yaml) define the actual consumer requirements. Preserve frozen definitions, seen OOS and cumulative exposure; a harness pass does not grant resource or order permission.

Deliver results through [owner reporting](../../../docs/owner-reporting.zh.md). Components may have different useful endpoints; do not create a second execution engine, fixed role hierarchy or deployment requirement for them.
