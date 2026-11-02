# Research workflow

One finite worker owns a complete economic question: preparation, implementation,
informative variants, repairs and interpretation. A fresh Lead inspects raw costed
results and dispatches the next question. Scope, stopping and startup rules live in
`AGENTS.md`; roles in `workflow.json`. Numerical evidence is provider-neutral;
only Codex transport is implemented. Claude A/B requires owner instruction.

## Run and recover

```bash
.venv/bin/python scripts/research_round.py init <direction>
.venv/bin/python scripts/research_round.py run <direction> --run-id <id> \
  --timeout-seconds <finite-envelope> --review reuse --follow
.venv/bin/python scripts/research_round.py resume <direction> --run-id <id> \
  --timeout-seconds <finite-envelope> --follow
```

Each direction holds a brief <=1000 bytes, `decisions.tsv`, engine-written
`results.json`, native evidence and run snapshots. The worker returns `Reply`;
numerical code writes `Results`. Schemas live in `schemas/`. Reuse the
[shared calculation and batch entry points](lab/README.md).

`--review reuse` uses accepted scope and fresh Lead checks. Use `plan` for new or
material science, `result` for required separate decisive-result/paper reception,
or `both`. A new directory or same-semantics repair needs no new economic review.
Retain native contracts without multiplying ordinary preparation into peer rounds.

Lead supplies concrete `next_brief` and `next_review`. `--follow` consumes continue,
repair, branch and park-with-next decisions across `research/` directions inside
the invocation's time envelope. Park without another brief ends the series.
No standing coordinator, scheduler or agent message chain is created.

On interruption, inspect `run.json`, saved process identities, events and native
checkpoints. Resume the original session and useful jobs; local exit does not
prove remote termination. Locks reject duplicate drivers. Completed phases are
reused; changed upstream results get a fresh downstream Lead. Reconcile actual
jobs before closing a checkpoint. Preserve quota exhaustion, provider faults,
owner pauses and resource failures as their actual causes.

Capacity failures allow two bounded waits/retries in the known session. Quota and
authentication failures do not. Malformed Reply allows one correction from saved
artifacts only, without numerical work. These repairs retain failed-attempt logs;
manual recovery remains manual. Already-running drivers do not hot-load changes.

## Results

The done-when is the complete economic comparison. Model work includes fitted
weights, predictions and matched costed accounts where applicable. Record dollar
profit, risks, costs, all selectable starts and seen-window status. A checkpoint
states completed and remaining work; preparation cannot finish the question.

Optional engine `counts` distinguish comparisons, accounts, fits, variants and
paper candidates. `counts_artifact` points to their actual source. Tests, fixtures,
transport success and saved-result imports are not economic conclusions. Missing
counts or usage stay unknown. An executed comparison may still be rejected.

The runner records all-phase research token/time, including failed attempts and
Lead, and one current board row per round. Cached input is already included in
input tokens. Lead reads `scripts/research_usage.py --run <Run>` once for shared
account pacing; account percentages are not project cost. Use ordinary research
results to assess throughput, excluding one-time restructuring and its checks.
No extra efficiency acceptance gate or payback study is needed.

Use affected checks for an identified code/science/accounting defect. Paper
releases retain their worktree, review and integration requirements. Resource,
provider and order authority come from `docs/rules.md` and the actual authorization.
