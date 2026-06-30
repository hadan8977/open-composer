---
name: evidence-curator
description: >
  Periodic curation of source cards, evidence artifacts, and skill references.
  Merges duplicate source cards, flags stale sources, consolidates recurring
  lessons into skill references, removes low-value artifacts.
  Use during weekly review cycle, after every 20 strategy research runs,
  when repo check warns about source staleness, or when user requests cleanup.
---

## Inputs

- All `reports/harness/source_cards/*.jsonl` files
- `harness/source_policy.yaml` (staleness thresholds by source type)
- Any recent backtest forensics or execution reality findings

## Mandatory output

`reports/harness/curation/{YYYY-MM-DD}-evidence-curation.md`

## Step sequence

### 1. Source card audit
- Scan all `reports/harness/source_cards/*.jsonl`.
- Flag cards where `accessed_at` is older than `staleness_days` from source_policy.yaml.
- Identify duplicate cards (same URL, same claim) across strategies.
- Note cards with `source_type: unverified`.

### 2. Stale source remediation
- For each stale card: mark as `stale: true` and note the refresh date needed.
- If the claim is still actively used by a strategy in `paper_ready` or `active` lifecycle,
  escalate to `urgent_refresh`.
- If the claim is only used by `draft` or `research` strategies, mark as `scheduled_refresh`.

### 3. Deduplication
- Where two strategies share the same external claim (e.g. Alpaca OPG support),
  extract the source card into `reports/harness/source_cards/_shared.jsonl`.
- Update strategy-specific JSONL files to reference the shared card by `claim_id`.

### 4. Lesson consolidation
- Review backtest forensics reports for recurring patterns (e.g. repeated lookahead
  warnings of the same type).
- If a pattern appears in >= 3 strategies, propose a concise rule for the relevant
  skill's SKILL.md or references/ directory. Do not edit skill files unless the user
  has explicitly asked for implementation, not just curation.
- Do not add redundant lessons already in AGENTS.md or skill references.

### 5. Artifact cleanup
- Identify `reports/harness/` artifacts for strategies that no longer have a spec file.
  List them for user review before deletion (do not auto-delete).
- Flag empty or schema-violating artifact files.

## Output format (md)

```markdown
# Evidence Curation — {date}

## Source card status
- Total cards: N
- Stale: N (urgent: N, scheduled: N)
- Unverified: N
- Deduplicated: N shared cards created

## Stale cards requiring refresh
| claim_id | strategy | source_type | accessed_at | deadline |
| ...      | ...      | ...         | ...         | ...      |

## Lessons consolidated
- Added to {skill}: "{lesson summary}"

## Artifacts for user review (potential cleanup)
- {path}: strategy spec not found

## Next curation due
{date + 7 days or + 20 strategy runs}
```

## Rules

- Do not delete artifacts without explicit user confirmation.
- Do not modify active strategy specs during curation.
- Do not modify `.agents/skills` during advisory curation without explicit
  implementation approval.
- Curation output is advisory; user reviews before any structural change.
