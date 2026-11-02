# Autonomous research: compatibility runbook

The old alternating lead/execution research schedules are retired. Do not restart them or use their old model, lock, pause or per-round quota rules. Current work uses [Research workflow](../research/README.md), current role configuration and actual task authority. Historical instructions remain in the consolidation before snapshot.

## 1. Start or continue a task

Read current permission and the relevant task state. Reuse its owner, approved science, inputs, checkpoints and cumulative ledger. Use `research/README.md` and `scripts/research_round.py` for finite Codex rounds; reuse accepted scientific scope for ordinary repairs. No mandatory autonomous-preflight round or heartbeat is introduced by this page.

## 5. Compute and budgets

Prefer the owner's Hadan worker for suitable high-memory work only after fresh readiness and the Windows contract checks. Use [the Windows runbook](runbook-windows-compute.zh.md); calendar availability alone is not permission or readiness.

For the existing authorized Modal fallback, run the actual budget check before launch:

```bash
python3 scripts/modal_budget.py check --job <name> --cpu <cores> --memory-gib <GiB> --timeout-min <minutes> [--gpu T4]
```

The runtime resources and timeout must match the admission. Retain actual failed, in-flight and unknown consumption; do not duplicate reservations or reset a ledger on retry. New paid limits/providers require owner approval. Use the live ledger and `scripts/modal_budget.py status`, not an old dollar balance printed in a report.

Local jobs follow [the memory runbook](runbook-memory.zh.md) and existing capped execution. Ordinary recovery uses the task's remaining total allocation; technical estimates do not create a new per-file approval process.

## 6. Reporting

[Owner reporting](owner-reporting.zh.md) and `config/owner-reporting.json` define the existing report cadence and routes. Do not change schedules, send extra mail or revive old research rounds as part of a task handoff.
