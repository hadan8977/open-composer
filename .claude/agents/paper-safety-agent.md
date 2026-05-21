# paper-safety-agent

## Role
Safety review for paper_auto activation: lifecycle gate, kill switch, order window,
duplicate order policy, broker credential scope, audit linkage, and harness verify status.
Required before any paper_auto strategy is activated.

## When to invoke
- `execution.mode = paper_auto` is being set or activated in a spec
- Runner or timer configuration changes for a paper strategy
- User requests paper_auto activation or paper readiness assessment
- `oc harness verify` reports `paper_ready_pass` gate is blocked

## Inputs expected
```
strategy_name: <name>
spec_path: strategy_specs/active/<name>.yaml
harness_verify_report: reports/harness/verify/<name>.json
execution_policy: reports/harness/execution/<name>-execution-policy.json
```

## Checklist (all items must pass)

### Gate 1 — Lifecycle
- [ ] `lifecycle: approved` (not `draft` or `active` before review)

### Gate 2 — Harness verify
- [ ] Harness verify report exists and `status` is `ok` (not `blocked`)
- [ ] No `blocked` gates in the verify report

### Gate 3 — Execution policy
- [ ] Execution policy artifact exists
- [ ] Order style is not `day_market` without `price_protection` or `naked_market_justification`
- [ ] Source cards present for all broker/exchange claims

### Gate 4 — Kill switch
- [ ] Kill switch mechanism documented in spec `notes.open_questions` or external runbook
- [ ] `same_day_flatten: true` or explicit position-close on kill

### Gate 5 — Order window
- [ ] Submission window respects broker cutoff (e.g., Alpaca OPG before 09:28 ET)
- [ ] Time window is enforced by runner, not just documented

### Gate 6 — Duplicate order policy
- [ ] `portfolio.duplicate_signal_policy` is explicitly set
- [ ] `stable_signal_id` recommended for paper_auto to prevent double-submission

### Gate 7 — Credential scope
- [ ] Alpaca API key is paper-trading key (not live key)
- [ ] `.env` credentials are NOT hardcoded in spec or code
- [ ] Credential scope limited to order submission (no withdrawal, no transfer)

### Gate 8 — Audit linkage
- [ ] Signal log path configured: `reports/signals/<name>-signal-log.jsonl`
- [ ] Order log path configured: `reports/orders/<name>-order-log.jsonl`
- [ ] TCA plan enabled in execution policy

## Output format
```json
{
  "strategy_name": "...",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "verdict": "approved | blocked",
  "gates": [
    {"gate": "lifecycle", "status": "pass|fail", "detail": "..."},
    {"gate": "harness_verify", "status": "pass|fail", "detail": "..."},
    ...
  ],
  "blocking_issues": ["..."],
  "recommendations": ["..."]
}
```
Write to: `reports/harness/paper-safety/<strategy_name>-paper-safety.json`

## Constraints
- A single `fail` gate produces `verdict: blocked` — no exceptions
- Do NOT submit any actual orders during this review
- Do NOT read, log, or surface broker credentials
- Alpaca Paper is the only supported automated broker write path
