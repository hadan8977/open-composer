# Research workflow

Use one finite worker for a complete economic question, including preparation,
implementation, variants, ordinary repairs and interpretation. A fresh Lead reads
actual results and chooses the next economic task. Default: worker -> Lead.
Independent review joins at the requested scientific or final-result boundary;
do not turn each preparation step into a new round.

Pure Codex bindings live in `workflow.json`. Briefs, numerical results, trial
ledgers and decisions are provider-neutral. Claude can replace roles after a
transport adapter is implemented and verified; A/B remains off.

## Run

```bash
.venv/bin/python scripts/research_round.py preview
.venv/bin/python scripts/research_round.py init <direction>
.venv/bin/python scripts/research_round.py run <direction> --run-id <unique-id> \
  --timeout-seconds <wall-clock-envelope> --review reuse --follow
```

Each direction holds a brief <=1000 bytes, `decisions.tsv`, engine-written
`results.json`, native evidence and immutable run snapshots. Reference existing
scientific contracts. Reuse `open_composer.lab` and the [shared adapters](lab/README.md);
count all selectable starts and preserve seen-data exposure. A failed recipe does
not refute a mechanism; explain the next distinguishing change or stopping reason.

`--review reuse` uses accepted scope and the independent Lead's actual checks.
Use `plan` for a new hypothesis or material scientific definition, `result` for
decisive independent result/paper review, or `both`. Compatibility flags
`--review-plan` and `--review-result` remain available. A new directory, ordinary
repair or routine variant inside accepted scope does not itself require plan
review. Existing native scientific/input/model acceptances remain applicable.

The Lead's `next_review` selects the next brief's review boundary. `--follow`
consumes concrete continue/repair/branch and park-with-next briefs, including
another direction under `research/`. Park with another task retires only that
branch; park without a next brief ends the series. Genuine blocks, checkpoints,
pauses, process failures, exhausted quota and caller deadlines preserve recovery
state. No standing agent, quota manager, polling or new scheduler is created.

Installed research authority, existing memory admission and capped execution
apply to actual starts. Research permission never creates broker, device or paid
provider authority. Keep paper and real-money decisions separate.

## Results and efficiency

Agents return `Reply`; numerical code writes `Results` with original artifacts.
Schemas live in `schemas/`. Optional `counts` separates executed economic comparisons,
financial accounts, model fits, variants, paper candidates and diagnostic steps.
Populate from actual engine/fit/trial evidence; `counts_artifact` references the
existing engine JSON carrying these counts. Missing counts stay unknown.
Code, tests, transport and environment success are not economic conclusions.
Even a completed engine comparison can later be rejected. Board execution counts
do not count accepted conclusions: confirm those through existing independent
result reception. Automatic accepted-conclusion totals remain unknown.

The runner summarizes phase usage in `run.json` and the compact board row,
including Lead and failed/interrupted attempts. Retries retain their original
runs: assess total task cost, not only a successful last attempt. Input tokens
already include cached tokens. Missing usage remains unknown. Lead reads one
shared-account snapshot with `scripts/research_usage.py`; completion refreshes
token totals without another quota query. Account percentages are pacing context,
not project-attributed cost or dollars.

Done-when refers to the whole economic comparison. Model tasks include optimized
weights, predictions and matched costed accounts where relevant. Checkpoints name
completed work and remaining computation; preparation alone does not finish a
study. Assess throughput over actual research days, showing task depth, failed
work and owner interventions.

## Recovery and handover

Inspect `run.json`, process identities, event logs and native checkpoints. Record
the actual cause: quota exhaustion, provider fault, owner pause, timeout or an
input/resource defect. Oct 28 stopped because quota was exhausted per the owner;
a handoff record alone does not diagnose that cause.

Resume the original failed model session and existing numerical jobs when viable.
Local process exit does not prove remote termination. Reconcile unfinished work
before a new start; never replay accepted roots merely to recreate a reply. Use
`closed_after_recovery` only after reconciling actual jobs and outputs. Ordinary
recovery reuses scientific acceptance. Old quota-manager prose is not authority.

Future Claude integration supplies command construction, reply/event normalization
and its usage reader. Financial evidence and checkpoints do not change with the
provider. Retain real account authorization and paid/provider limits.

Use existing affected formatting/lint/checks for code changes. Do not create a new
test suite or run full release checks for each experiment. Production releases
retain applicable `make verify-paper` checks; historical snapshot checks remain
available when that code changes. One pytest process at a time; avoid competing
with a heavy financial/model job on this shared host.
