# mom_minute_r1 Methodology Audit

Date: 2026-07-11

Verdict: `blocked`; `methodology_invalid=true`.

This audit supersedes the evidentiary interpretation of the original
`mom_minute_r1` evaluation, decision record, trial ledger, and forensics report.
Those files remain unchanged as historical artifacts, but their return, Sharpe,
drawdown, fold, and ranking values must not be used for research promotion, ML
entry, paper readiness, or strategy selection.

## P0 Findings

1. The specs declare bar-close decisions with next-bar-open fills, while the
   research implementation applies the current close decision to the current
   close-to-next-close return. This includes an unavailable price interval.
2. The reported folds are chronological slices of one already-selected full
   sample result. They are not walk-forward or stitched OOS evidence and have no
   training selection, purge, or embargo.
3. The 1h materialization is UTC-clock resampled rather than anchored to each
   US regular session at 09:30 America/New_York. Open/overnight interpretations
   are therefore invalid.
4. The forensics report declares lookahead and future-leak checks passed without
   testing the actual fill alignment.
5. The benchmark family is incomplete and missing timestamps are treated as
   zero returns, which can distort comparisons.
6. The `atr_trail` label describes a rolling ATR trend filter, not a stateful
   trailing stop.

## Affected Claims

- The former best P1 observation (`88.93%` total return, `1.33` Sharpe) is
  withdrawn as valid evidence.
- P1 and P3 remain `blocked`, not `pivot` candidates supported by performance.
- `workflow_pass` only means the old command produced artifacts. It does not
  imply `research_pass`, `paper_ready_pass`, or an ML-entry condition.

## Required Remediation

Use the Step 9.R plan: session-aware aggregation, next-open execution, complete
aligned benchmarks, development/validation selection, and an untouched final
lockbox. Run only the fixed nine-combination P1 round; do not expand a failed
search and do not train ML before a non-ML lockbox candidate passes.

