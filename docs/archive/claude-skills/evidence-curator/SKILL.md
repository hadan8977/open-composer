---
name: evidence-curator
description: >
  Curate source cards, evidence artifacts and skill references when stale or
  duplicate evidence, recurring findings or a requested review justify it.
  Merge duplicate claims, flag stale evidence and propose recurring lessons.
---

# Evidence curation

Audit `reports/harness/source_cards/*.jsonl` against [source-policy staleness thresholds](../../../harness/source_policy.yaml), recent forensics and execution findings. Identify identical URL/claim pairs, unverified claims, empty/schema-invalid artifacts and artifacts without a remaining strategy spec.

Mark stale cards `stale: true` with the needed refresh date. Claims used by `paper_ready`/`active` strategies need `urgent_refresh`; draft/research claims use `scheduled_refresh`. Shared claims can move to `reports/harness/source_cards/_shared.jsonl`, with strategy files referencing their `claim_id`; preserve provenance and frozen evidence bindings.

Record a reusable lesson when the evidence warrants it, without a fixed recurrence quota. Update self-imposed guidance within current authority; changing live specifications or deleting bound artifacts remains a separate scope. Preserve provenance and recoverability, and do not treat orphan status alone as permission to delete.

Write `reports/harness/curation/{YYYY-MM-DD}-evidence-curation.md` with:

- Counts of total, stale (urgent/scheduled), unverified and deduplicated cards.
- A stale-claim table: `claim_id`, strategy, `source_type`, `accessed_at`, deadline.
- Lessons proposed or implemented within explicit scope, with their destination.
- Potential artifact cleanup and the reason for each item.
- A useful next review trigger, if one is needed; do not create another timer or run-count quota.

Do not treat a curation report as approval for unrelated structural changes.
