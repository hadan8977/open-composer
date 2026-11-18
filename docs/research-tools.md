# Local research tools

Codex and Claude Code call the same project-owned CLI. No model, server, SDK,
provider credential or vector service is used by these commands:

```powershell
$researchPython = '.\.venv\Scripts\python.exe'
$direction = '<direction>'
& $researchPython scripts/research_tools.py index --prefix "research/$direction"
& $researchPython scripts/research_tools.py search '回撤 experiment_id' --task $direction --budget 2400
& $researchPython scripts/research_tools.py get '<document-id>' --task $direction --offset 0 --budget 2400
& $researchPython scripts/research_tools.py context $direction --budget 2400
& $researchPython scripts/research_tools.py status --task $direction --budget 2400
& $researchPython scripts/research_tools.py event-status "research/$direction/runs/<id>" --phase worker
& $researchPython scripts/research_tools.py checkpoint "research/$direction/runs/<id>" --phase worker
```

Text responses label the budget as **characters**. Task logs use explicit byte
budgets/ranges (`get <id> --task <direction> --byte-offset 1000 --budget 2400`).
They index only path/stat metadata, never log content; get returns `offset_unit:
bytes`. A range may split a UTF-8 character, rendered with a replacement mark. `omitted` and `next_offset` page the
text; retain the same query/document/task for the next call. Get IDs, state and source
versions remain outside the text page; search/context source IDs appear in the
paged text. `get` accepts an admitted document ID,
not an arbitrary path. Search snippets are at most 400 characters per occurrence.
Task context places the active saved run and its latest phase/session/wait state
before historical checkpoints; older admitted evidence remains in later pages.

`runtime/research-tools/knowledge.sqlite3` is a rebuildable derived view. Indexing
uses one SQLite transaction, text documents <=512 KB (task engine/stderr logs use metadata plus bounded byte
reads), explicit glob allowlists and
no symlinks. It never reads/writes old `knowledge/index.json`, archives, raw
sessions, credentials or market matrices. A removed, changed, unreadable or
now-directory source is excluded from all reads; its last cached bytes remain
for diagnosis until replaced. Reindex to refresh. An unknown SQLite schema is
rejected; remove/rebuild only this derived database when no tool is using it.

Default cross-task design reads require `visibility_partition` equal to
`public_literature` or `train_only_empirical`. Historical source-card occurrences
without an explicit partition remain unknown. Public/limited occurrences with
the same canonical URL stay separate; hidden occurrences never contribute text,
counts or ranking. A small bilingual alias table connects common account terms; Chinese
bigrams and experiment identifiers have explicit lexical coverage. Whole
mixed-result documents are restricted. Current task
artifacts without a partition are available only through explicit `--task` or
`context <direction>` recovery reads. This admits drafts for resuming that task;
it does not mark them accepted scientific evidence. Source state and path remain
visible. An explicit restricted partition also applies to task recovery reads.
Existing historical knowledge gates keep their own semantics; old build/context
now refuse an archived/symlinked index instead of writing through it.

## Waiting and checkpoints

A blocked worker can include nullable `wait` in Reply. Old Replies without `wait`
remain readable; new strict dispatch schemas request all fields. Example:

```json
{"schema_version":1,"session":"<original-session>",
 "completion_marker":"research/<direction>/runs/<id>/worker/complete.json",
 "failure_marker":"research/<direction>/runs/<id>/worker/failed.json",
 "cancel_marker":null,"process":null,"local_only":false}
```

All marker/process paths, checkpoint JSON and native snapshots belong to this run.
Checkpoint input references may point to other files inside the repository.
An optional process file holds a PID and its
start time (`process_identity.identity`); once that process is gone, or the PID
belongs to a later process, it counts as exited.
Remote completion still needs an explicit marker. A verified remote-job supervisor
exit emits one deterministic reconciliation event for the original worker session,
with remote status unknown. A bound failure marker likewise resumes that worker
once for inspection, preserving the marker and explicit failed/remote-unknown
status. Neither event establishes numerical completion or authorizes a retry;
inspect failure, remote status and saved outputs first. Unresolved quota,
authorization or resource blockers remain checkpoints. Existing event-attempt
deduplication prevents repeated resumes for an unchanged failure or exit. A local-only
process exit may be its declared completion event. Repeat marker content for the
same wait produces the same event ID.

Jobs or controllers that must outlive a worker turn require an independent capped
systemd service using the existing admission/wrapper entry points, or the worker
must remain alive until they finish. `nohup` and a unified-exec background session
do not guarantee survival after the worker exits. `scripts/modal_run.py` uses
`modal run --detach` to preserve submitted remote computation on client loss;
its local controller still owns normal result fetching and actual-cost recording.
If that controller exits, reconcile remote status, outputs and costs before
considering a new launch.

The existing research driver waits within its remaining deadline under the
original direction lock, then resumes the original worker session. The wait uses
zero model requests. Duplicate events cannot start another resume. The driver
persists observed/dispatching/received attempts and transport receipts. After a
crash it receives a saved original-session Reply or waits for the verified live
attempt. Missing dispatch evidence stays uncertain and requires reconciliation;
it never automatically resends a possibly started call. Cancel/pause/timeout stop
without worker continuation; unresolved failures keep checkpoints and do not
dispatch Lead. Ordinary legacy blocked
Replies retain their prior recovery behavior. Scientific branch/revise and final
independent Lead acceptance retain their existing contracts.

The standalone `wait <run> --phase <phase> --timeout-seconds <finite-seconds>`
observes events under the same lock; it does not dispatch or consume a worker.
Use the existing `research_round.py resume` for recovery. Do not run both drivers.

A native checkpoint may declare `kind: research_checkpoint`, `schema_version: 1`,
`session`, `inputs` (path/type and optional size/mtime_ns version), `completed`,
`remaining`, `native_resumable`, and `engine_snapshot`. Availability checks inspect
existence, types and optional versions without hashing large inputs. Only an
explicit native-resumable declaration with a readable bound snapshot is reported
as available for native resumption. Ordinary progress JSON remains evidence;
this tool does not restore an engine or infer a resumable snapshot.

## Claude Code provider boundary

The official [headless guide](https://code.claude.com/docs/en/headless) documents
`claude -p`, JSON/schema output and `--resume <session-id>`. Both agents can run
exactly the local commands above from their shell tool.

The driver implements this shape for a role with `provider: claude`
(`claude_command` in `open_composer/research/agent_workflow.py`):

```bash
env -C <repo> claude -p --output-format stream-json --verbose \
  --model <role model> --effort <role effort> --permission-mode bypassPermissions \
  --json-schema '<dispatch Reply schema>' --session-id <uuid>   # or --resume <id>
```

`env -C` keeps relative brief/run paths and the resume scope inside the
repository, because Claude stores sessions per working directory. The prompt
goes in on stdin. The schema-validated Reply arrives as `structured_output` in
the final `result` event; the driver writes it to `reply.json` and maps Claude
usage onto the Codex fields (uncached input, cache read/creation, output).
Session continuity, independence and recovery reuse the same contracts as Codex.

This wiring is covered by offline fixtures only. It has not been run against a
live Claude session here (the account's weekly quota was exhausted), so the
first owner-authorized round is the real end-to-end check; verify the installed
CLI's `--help` and `structured_output` before relying on it.

Use the official binary and normal supported
[authentication](https://code.claude.com/docs/en/authentication). `--bare` requires
API/provider authentication and skips subscription OAuth; these examples omit it.
No subscription credentials are copied into another SDK and no paid API fallback
is selected. Future provider rollout should check the installed CLI version/help
and offline contracts before owner-authorized invocation. Hosted product use has
separate [official integration terms](https://code.claude.com/docs/en/legal-and-compliance).

## Evidence index v2 (2026-11-15 MVP)

The derived index now covers the existing research stores, not only source
cards: `research/**/trials.jsonl`, `research/*/decisions.tsv`,
`reports/research/trials.jsonl`, `reports/owner/verdicts.jsonl`,
`capabilities/registry.yaml`, archive batch metadata and `intel` summaries.

```bash
.venv/bin/python scripts/research_tools.py index
.venv/bin/python scripts/research_tools.py search '<question>' --task <direction>
.venv/bin/python scripts/research_tools.py map --task <direction>
.venv/bin/python scripts/research_tools.py failures '<topic>' --task <direction>
.venv/bin/python scripts/research_tools.py status
```

- `search` returns row-level hits for claims, trial events, decisions and
  capabilities. It also reports `visible_documents`, `hidden_by_policy`,
  `index_built_at` and `zero_result_reason`; a zero result is not silently the
  same as "no knowledge".
- `failures` joins failed/interrupted trials with branch/park/revise decisions;
  `map` is a task/query-scoped view, not a project-wide static truth.
- Source cards without `visibility_partition` default to `public_literature`
  unless they carry a restricted marker. Internal records are admitted; owner
  verdicts remain owner authority.
- A changed source file is excluded from reads until reindexed; a derived
  `policy_visibility` mismatch is also excluded. The index is rebuildable and
  reports `quarantined` JSON lines instead of dropping them silently.
- `schema_version=2`; an old derived database is migrated by dropping and
  rebuilding the view. No source evidence is modified.

`tasks` lists research directions, most recently active first; use the exact
directory name for `--task`. An invalid `--task` now returns a clear error with
example names instead of a generic `ValueError`. The A/B pilot in
`research/knowledge_mvp_20261115/AB_TEST.md` found that `search` alone misses
task-local (`unknown`) artifacts; use `map --task` or `context` for those.

## Large-file policy (2026-11-15)

Do not create a single JSONL that grows without bound. The current split:

- **Source cards:** 355 per-strategy files, largest 59 rows / 66 KB. They are
  already sharded by strategy; the source-card loader (`load_source_cards`)
  expects `<strategy>.jsonl`, so do not split an existing file without updating
  the loader. Future rotation: 1,000 rows or 1 MB, with a shard manifest.
- **Trials/decisions:** one file per research direction; keep the source of
  truth there. Do not merge all directions into one ledger. The derived index
  handles cross-direction search.
- **Catalog/export:** logically partitioned by `kind + sha256(group_key) %
  shards_per_kind` under `research/knowledge_consolidation_20261115/catalog/`,
  max 2,000 rows / 1 MB, with `manifest.json` and a derived `index.sqlite3`
  (entities/shards). A source/claim/conflict component or a trial event stream
  is never split; ledger blocks are 1,000 rows. The old monolithic
  `catalog.jsonl` is removed. `catalog/conflicts/` holds duplicate/collision/
  trial-label groups with their `group_key`. Current validation: 21,574 unique
  IDs, 0 split groups, 0 SHA mismatches.
- **Duplicates/collisions/trial-label reports:** 14–325 KB; if a report grows
  past 1 MB, shard it with the same policy.
- **Index:** `runtime/research-tools/knowledge.sqlite3` is a derived,
  rebuildable view; SQLite is the right shape for it, not a human-readable log.

`failures` counts decisions whose value starts with `branch`, `park` or
`revise` (case-insensitive), so `park_pending...` is included; it uses nested
`research/**/trials.jsonl`, not only the 85 top-level files.

Source-card search/get results now include `schema_valid`, `quote` and
`locator`. A card with `schema_valid=false` or `quote=false` may be indexed for
inventory but is **not safe to cite as claim evidence**; the agent should say so
or use the source file directly. This is a warning flag, not a silent drop.

Exact source-card duplicates are collapsed in the **active read view**:
2,543 rows → 1,806 canonical assertions; 737 duplicate rows are not returned
as separate evidence. A search hit carries `canonical_id` and `usage_count`
(e.g., 29 rows of one Alpaca claim → one hit, `usage_count: 29`). Raw source
files are not deleted; `catalog/conflicts/dispositions.jsonl` records the
action (`canonicalize_active_view`, `split_stable_assertion_ids`,
`event_stream_count_once`). `status` reports `canonical_source_cards` and
`duplicate_source_rows`.
