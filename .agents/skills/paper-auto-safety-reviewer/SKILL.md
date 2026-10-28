---
name: paper-auto-safety-reviewer
description: >
  Review paper_auto activation or runner/timer changes for lifecycle, kill switch,
  order window, duplicate guards, paper credentials, audit linkage and harness
  verification. Required before any paper_auto strategy is activated.
---

# Paper-auto safety review

Read the StrategySpec, `uv run --no-sync oc harness verify <spec>` output and `uv run --no-sync oc paper readiness <spec>` report. Check the following before activation; verification actions themselves stay within existing authorization and production-isolation rules in [AGENTS.md](../../../AGENTS.md).

| Area | Required evidence |
|---|---|
| Lifecycle | `paper_ready` or `active`; promotion report has `promotion_pass=true`, readiness has `paper_ready_pass=true`. |
| Harness | Verify exits 0; result is at `reports/harness/verify/{strategy}.json`. List blocking artifacts otherwise. |
| Kill switch | Documented in spec/runner; enable/disable paths are verified. Stopping the local paper loop does not require a network or database. |
| Window and duplicates | Explicit order window, no submission outside it, and a guard against existing open/duplicate orders. |
| Credentials | Paper-only scope, no secrets in version control/artifacts, `.env` ignored. |
| Audit | Log signals before submission. Orders link `signal_id`, `spec_version`, `spec_hash`, `execution_policy_id`; retain order logs at least 90 days. |
| Execution | Supported broker order type/TIF, source-linked policy, and gap/spread filters or explicit justified waivers. |

Kill-switch commands:

```text
uv run --no-sync oc paper kill-switch --enable --reason "<reason>"
uv run --no-sync oc paper kill-switch --disable --reason "<reason>"
```

Write `reports/harness/paper/{strategy}-paper-safety-review.json`:

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

Any failed required check means `overall: blocked`; draft/research lifecycle, failed harness or unverified kill switch cannot pass. This review is evidence, not new order authority. See [paper_safety_review](../../../harness/artifact_contracts.yaml) and [paper_auto rules](../../../harness/risk_domains.yaml).
