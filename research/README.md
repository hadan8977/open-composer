# Research workflow

One finite worker owns a complete economic question: preparation, implementation,
informative variants, repairs and interpretation. A fresh Lead inspects raw costed
results and dispatches the next question. Scope, stopping and startup rules live in
`AGENTS.md`; roles in `workflow.json`. Numerical evidence is provider-neutral.
Codex, Claude and pi transports are implemented; provider and model are per role
and routine to update. `preview` shows the resulting command without dispatching.
Read `control.json` for current switches; source authorizations prevail.
Installed role effort applies to direction decisions and execution alike.

Local evidence: `scripts/research_tools.py search/get/context/index/status` uses
one provider-neutral CLI; bounded output, visibility and event/checkpoint usage:
[local tools](../docs/research-tools.md). Use explicit task recovery context for
your own drafts; default cross-task design search excludes unknown/restricted work.

## Run and recover

```powershell
$direction = '<direction>'
$runId = '<run-id>'
& .\.venv\Scripts\python.exe scripts\research_round.py preview
& .\.venv\Scripts\python.exe scripts\research_round.py init $direction
& .\.venv\Scripts\python.exe scripts\research_round.py run $direction --run-id $runId --timeout-seconds 86400 --review reuse --follow
& .\.venv\Scripts\python.exe scripts\research_round.py resume $direction --run-id $runId --timeout-seconds 86400 --follow
```

Each direction holds `brief.md` <=1000 bytes, `decisions.tsv`, engine-written
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

Worker waits for useful numerical jobs and completes interpretation in its finite
envelope. A blocked worker with a structured `wait` lets the driver wait without model calls
and resume that session within its deadline. Other blocked workers stop before Lead;
resume the same run/session
after reconciling its jobs. Waiting and resource checkpoints do not dispatch Lead.
Only a necessary material-science decision routes a blocked worker to Lead:
`decision=branch/revise`, a concrete `next_brief`, and `next_review=plan/both`.
Normal completed results still receive fresh Lead and any required result review.
New invocations, including resumed sessions, use installed role effort while
retaining the original provider/model. Running processes keep their launch settings.

Capacity failures allow two bounded waits/retries in the known session. Quota and
authentication failures do not. Malformed Reply allows one correction from saved
artifacts only, without numerical work. These repairs retain failed-attempt logs;
manual recovery remains manual. Already-running drivers do not hot-load changes.

Preserve healthy live/completed jobs and reconcile uncertain remote work first.
For confirmed terminal failures with no recoverable output/state, the complete
worker may make a bounded same-scope retry after correcting the cause, within
existing resource authority. Keep failed starts/costs and frozen science; this
does not permit quota/authentication retries or restarting a healthy batch.

## Continuous series (24h finite)


Research on the owner's current setup runs on native Windows; the VPS serves
paper/strategy/website runtime only. Use the same driver and finite envelope:

```powershell
Set-Location C:\OpenComposer\repo
& .venv\Scripts\python.exe -u scripts\research_round.py run <direction> `
  --run-id <series-id> --timeout-seconds 86400 --review reuse --follow
```

The Windows driver applies the native Job/lock/admission boundary to each phase.
Use accepted scope and reconcile saved work before resuming. The former VPS
launch is retained in `reports/ops/research-continuity-20261110.json` and the pre-prune Git tag.

- One finite series; Lead/Worker chain within the 24h envelope.
- A plan review `revise`, a park without next brief, or the deadline ends the
  series; report the actual status and reason. Do not auto-edit science. After
  a `revise`, fix the brief in the same direction and start a new run id there;
  never open a suffixed copy of the direction (…b, …c).
- Do not create a custom supervisor, timer, scheduler or standing agent chain.
- `resume ... --timeout-seconds 86400 --follow` recovers an interrupted series.

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
No extra efficiency acceptance gate or payback study is needed. A completed Lead
sets `round_class` and `accepted_conclusions`; run efficiency reads them, so
accepted conclusions per token become measurable.

Use affected checks for an identified code/science/accounting defect. Paper
releases retain their worktree, review and integration requirements. Resource,
provider and order authority come from `docs/rules.md` and the actual authorization.
