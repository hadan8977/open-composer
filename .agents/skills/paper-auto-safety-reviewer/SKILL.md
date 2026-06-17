---
name: paper-auto-safety-reviewer
description: >
  Safety review for paper_auto activation: lifecycle gate, kill switch,
  order window, duplicate order policy, broker credential scope, audit linkage,
  and harness verify status. Required before any paper_auto strategy is activated.
  Use when execution.mode=paper_auto is being set or activated, or when
  runner/timer configuration changes.
---

## Inputs

- StrategySpec (lifecycle, execution, broker)
- `oc harness verify <spec>` output
- Paper readiness report from `oc paper readiness <spec>`

## Mandatory output

`reports/harness/paper/{strategy}-paper-safety-review.json`

## Safety checklist

### Lifecycle gate
- [ ] `spec.lifecycle` is `paper_ready` or `active`. Strategies in `draft` or `research` cannot activate paper_auto.
- [ ] Promotion report exists and `promotion_pass = true`.
- [ ] Paper readiness report exists and `paper_ready_pass = true`.

### Harness verify
- [ ] `oc harness verify <spec>` exits 0. If non-zero, list blocking artifacts.
- [ ] Verify output written to `reports/harness/verify/{strategy}.json`.

### Kill switch
- [ ] Kill switch documented in spec or runner config.
- [ ] `uv run oc paper kill-switch --enable --reason "<reason>"` and
  `uv run oc paper kill-switch --disable --reason "<reason>"` are tested and operational.
- [ ] Kill switch does not require database access or network to stop local paper loop.

### Order window
- [ ] Order window is defined (e.g. market open ± 5 min, or specific auction window).
- [ ] Runner does not submit orders outside the defined window.
- [ ] Duplicate order guard: runner checks for existing open order before submitting.

### Broker credential scope
- [ ] Credentials are paper-trading scoped only. No live broker write permission.
- [ ] Credentials are not in version-controlled files or artifacts.
- [ ] `.env` file is gitignored.

### Audit linkage
- [ ] Every paper order references `signal_id`, `spec_version`, `spec_hash`, `execution_policy_id`.
- [ ] Signal log is written before order submission (not after).
- [ ] Order log is retained for at least 90 days.

### Execution policy
- [ ] `execution_policy` artifact is present and references source cards.
- [ ] Recommended order type is supported by broker (per source cards).
- [ ] Gap filter and spread filter are configured or explicitly waived with justification.

## Output schema (json)

```json
{
  "strategy_name": "...",
  "reviewed_at": "YYYY-MM-DD",
  "lifecycle_status": "paper_ready | active",
  "harness_verify_pass": true,
  "kill_switch_verified": true,
  "order_window": "09:28-09:32 ET",
  "duplicate_order_policy": "skip if open order exists",
  "credential_scope": "paper_only",
  "signal_order_linkage": true,
  "execution_policy_id": "loo_open_guard_v1",
  "source_card_ids": ["alpaca_opg_support", "nasdaq_opening_auction"],
  "overall": "approved | blocked",
  "blocking_items": []
}
```

## Blocking rules

- `overall: blocked` if any checklist item fails.
- `overall: blocked` if harness_verify_pass = false.
- Do not approve paper_auto if lifecycle is draft or research.
- Do not approve paper_auto if kill_switch_verified = false.

## Rules this skill does NOT cover

- Real-money broker write access (out of scope for all Open Composer work).
- Dashboard remote execution of paper orders (covered by AGENTS.md remote command rules).

## References

- `harness/artifact_contracts.yaml` — paper_safety_review schema
- `harness/risk_domains.yaml` — paper_auto blocking rules
- `AGENTS.md` — project-level paper automation and remote command rules
