---
name: strategy-research-orchestrator
description: >
  Orchestrates the full research workflow for an Open Composer strategy:
  spec validation → harness plan → capability evaluation → source research →
  search space → trials → benchmark family → backtest forensics →
  execution reality → promotion report → paper readiness.
  Use when the user gives a trading idea, requests strategy creation or
  optimization, asks for paper ready, or requests professional review.
---

## Inputs

- Natural-language idea OR existing StrategySpec YAML path
- Desired lifecycle stage (draft / research / promotion / paper_ready)

## Mandatory outputs

- `reports/harness/plans/{strategy}.json` — harness plan with detected risk domains
- `reports/research/{strategy}-research-brief.json` — research brief and search space
- `reports/research/{strategy}-evidence-manifest.json` — artifact checklist

## Step sequence

1. **Draft spec** — `uv run oc strategy draft --idea "<idea>"` or load existing spec.
2. **Validate spec** — `uv run oc spec validate <spec>`. Fix any schema errors before proceeding.
3. **Harness plan** — `uv run oc harness plan <spec>`. Read detected risk domains and required skills. Do not skip this step.
4. **Capability evaluation** — `uv run oc capability evaluate <spec>`. Flag trial or sample capabilities.
5. **Source research** — invoke `source-researcher` for every risk domain that requires source cards. Do not proceed past research without source cards for unstable external claims.
6. **Bounded search space** — if spec has adjustable parameters, define `parameters` ranges before running sweep.
7. **Trials and candidate set** — run `uv run oc strategy parameter-sweep <spec>` and write trial ledger.
8. **Benchmark family** — compare against benchmark proxies (SPY, QQQ, sector ETFs as appropriate).
9. **Backtest forensics** — invoke `backtest-forensics` skill. Required for any optimized strategy and at promotion stage.
10. **Execution reality review** — invoke `execution-reality-reviewer` if `daily_open_execution`, `leveraged_etf`, or `paper_auto` domain is active.
11. **Promotion report** — `uv run oc strategy promotion-report <spec>`.
12. **Paper readiness** — `uv run oc paper readiness <spec>` only if lifecycle or user requests paper automation.

## Gate rules

- Do not skip source research when risk domain requires it.
- Do not skip execution reality review when daily_open_execution or paper_auto is active.
- Do not recommend paper_auto activation unless `oc harness verify <spec>` passes.
- Label `workflow_pass`, `research_pass`, `llm_contribution_pass`, `paper_ready_pass` separately in every summary.
- Never enable real-money broker writes.

## References

- `harness/risk_domains.yaml` — risk domain definitions and required skills
- `harness/artifact_contracts.yaml` — artifact required fields
- `harness/skill_manifest.yaml` — skill trigger index
- `AGENTS.md` — project-level rules
