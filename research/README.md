# Research workflow

The implemented route uses Codex for lead, worker and independent review.
Role bindings live in `workflow.json`; prompts and financial files contain no
provider-specific session state. Claude can later replace any role or all roles
through a verified transport adapter. No Claude adapter or A/B is enabled now.

## Files

Each direction holds `brief.md`, `decisions.tsv`, engine-produced `results.json`,
and immutable per-round brief/result snapshots under `runs/<id>/`. Keep native
engine artifacts at versioned paths. Schemas in `schemas/` define replies and
result summaries; an agent reply references numerical evidence, not generated
profit claims. Validation checks structure and referenced files; independent
review checks the actual computation and claim. Trial counts include prior exposure, failures and actual starts through
`open_composer.lab`; see `lab/README.md` for adapters, metrics and ablations.

## Entry point

```bash
.venv/bin/python scripts/research_round.py preview
.venv/bin/python scripts/research_round.py init <direction>
.venv/bin/python scripts/research_round.py run <direction> --run-id <unique-id> \
  --timeout-seconds <wall-clock-seconds> --review-plan --follow
```

`preview` makes no model call. `init` creates templates, not authority. Real runs
require an installed non-draft root `control.json` with research enabled and no
conflicting legacy hold. The compact instruction layer is installed. The owner authorized research
restart on 2026-10-28; actual admission is recorded in `control.json`.
The runner creates no scheduler or broker action.

Fill the brief before execution. Use `--review-plan` for a new hypothesis or
material definition; omit it only for accepted unchanged scope, referencing that
acceptance in the brief. Native engine contracts/gates remain binding.

A round runs optional plan review, worker, independent result review and lead.
Plan rejection prevents execution. A blocked worker goes straight to the lead.
`--follow` consumes a concrete next brief for same-direction continue/repair
within the caller's timeout. A branch, blocked job/checkpoint, pause, process
failure or deadline returns a saved handoff. There is no default trial count,
standing agent, background polling or automatic model fallback.

Every actual start uses the existing memory admission/capped wrapper. Run records
separate requested model/settings from actual returned session/usage events;
unreported usage remains unknown. Permission is checked before each new agent.
Before deciding, the lead runs `.venv/bin/python scripts/research_usage.py --run <run-dir>`.
The helper saves one immutable `usage.json` per existing run: a shared-account
weekly-limit reading plus completed-phase token events. Repeated calls reuse
the snapshot, including unavailable readings; an interrupted attempt is unknown,
not retried. This is pacing evidence, not project billing or an automatic stop.
The RPC follows the [official account-rate-limit protocol](https://learn.chatgpt.com/docs/app-server#6-rate-limits-chatgpt).
Schema/transport success means workflow completion, not economic acceptance or
paper readiness. Source authorization governs paper work separately.

Run the complete release test suite outside a heavy numerical account run on
this shared host. The 2026-10-28 simultaneous run exhausted effective resident
headroom and stalled in swap despite per-process caps. `make test-full` limits
numeric-library threads; retain the owner reserve and existing admission checks.

`make verify` includes general slow tests but does not automatically run optional
`research_snapshot` integrations when private historical data happen to be installed.
Run `make test-research-snapshots` (or pytest with `--research-snapshots`) when the
corresponding historical code/data changes. The 26 cases cover retained equity-book
snapshots and real SIP daily/minute integrations (reader, reversal-trend state,
features/bar cycle, rolling-origin and mechanism/trial checks). Their assertions
and missing-data skips stay intact; skipped snapshots do not count as passed
parity. Synthetic/tmp-path fixtures, general slow GP tests and the six-policy/source
regression checks remain in the release suite. Legacy Longbridge/PDR source replays
and metadata-only archive-layout checks also retain their existing default behavior.

Eleven source-admission cases test the actual kernel resource profile. Portable
`make test-full` reports these as explicitly skipped; `make test-native-resource`
runs them on CPU 0 under a real 400 MiB cgroup with zero swap. Run `make verify-paper`
for a paper-runtime release so these proofs follow the portable checks serially.
This Linux host check needs the existing systemd/admission facilities, not broker
credentials or historical research readers. The remaining source reader tests
use packaged code and private synthetic metadata and run in the portable suite.

## Recovery and future handover

Inspect `run.json`, phase `process.json`, event/stderr logs and native checkpoints.
Timeout cleanup signals the local process group, including descendants after the
leader exits. Detached or remote jobs require their existing recovery/completion
route; local exit never proves a cloud job stopped. A worker with such a job must
return `blocked` plus its checkpoint path; the series will not relaunch it.

After a runner crash, a new id cannot bypass an unfinished run. The task owner
reconciles its real job/session, records the outcome in that run, and uses
`closed_after_recovery` only after actual receipt/reconciliation. This is ordinary
repair, not another owner approval. Resume a capacity-failed Codex session with
its original identity; do not replay a numerical job merely to recreate a reply.

Future Claude integration supplies command construction, event/reply normalization
and an optional provider-specific usage reader, then updates selected role bindings.
A Codex account snapshot never represents Claude capacity. Existing briefs, trial
exposure, results, checkpoints and decisions stay valid. Credentials and provider
sessions remain outside financial result files. Verify the same offline workflow
tests and an authorized small provider run before using the new adapter.

The current CLI flags were checked against installed `codex exec --help` and the
[official non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode).
`--output-schema` constrains the final agent reply; it does not validate backtest truth.
