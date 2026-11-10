# Local research tools

Codex and Claude Code call the same project-owned CLI. No model, server, SDK,
provider credential or vector service is used by these commands:

```bash
.venv/bin/python scripts/research_tools.py index --prefix research/<direction>
.venv/bin/python scripts/research_tools.py search '回撤 experiment_id' --task <direction> --budget 2400
.venv/bin/python scripts/research_tools.py get <document-id> --task <direction> --offset 0 --budget 2400
.venv/bin/python scripts/research_tools.py context <direction> --budget 2400
.venv/bin/python scripts/research_tools.py status --task <direction> --budget 2400
.venv/bin/python scripts/research_tools.py event-status research/<direction>/runs/<id> --phase worker
.venv/bin/python scripts/research_tools.py checkpoint research/<direction>/runs/<id> --phase worker
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

All marker/process paths belong to this run. An optional process file contains a
captured Linux PID, boot ID, start ticks and pgid. Keep its original identity:
PID/wall-clock legacy records are unknown, never upgraded from today's process.
Launcher exit needs an explicit completion marker for remote jobs. A local-only
process exit may be its declared completion event. Markers are <=64 KiB; repeat
content for the same wait produces the same event ID.

The existing research driver waits within its remaining deadline under the
original direction lock, then resumes the original worker session. The wait uses
zero model requests. Duplicate events cannot start another resume. The driver
persists observed/dispatching/received attempts and transport receipts. After a
crash it receives a saved original-session Reply or waits for the verified live
attempt. Missing dispatch evidence stays uncertain and requires reconciliation;
it never automatically resends a possibly started call. Cancel/failure/pause/
timeout keep the checkpoint and do not dispatch Lead. Ordinary legacy blocked
Replies retain their prior recovery behavior. Scientific branch/revise and final
independent Lead acceptance retain their existing contracts.

The standalone `wait <run> --phase <phase> --timeout-seconds <finite-seconds>`
observes events under the same lock; it does not dispatch or consume a worker.
Use the existing `research_round.py resume` for recovery. Do not run both drivers.

A native checkpoint may declare `kind: research_checkpoint`, `schema_version: 1`,
`session`, `inputs` (path/type and optional size/mtime_ns version), `completed`,
`remaining`, `native_resumable`, and `engine_snapshot`. Availability checks inspect
readability, types and optional versions without hashing large inputs. Only an
explicit native-resumable declaration with a readable bound snapshot is reported
as available for native resumption. Ordinary progress JSON remains evidence;
this tool does not restore an engine or infer a resumable snapshot.

## Claude Code boundary (offline compatibility only)

The official [headless guide](https://code.claude.com/docs/en/headless) documents
`claude -p`, JSON/schema output and `--resume <session-id>`. Both agents can run
exactly the local commands above from their shell tool. A future owner-authorized
Claude task can use this official CLI shape:

```bash
claude -p 'Use .venv/bin/python scripts/research_tools.py context <direction> --budget 2400; report the source IDs.' --output-format json
claude -p 'Continue the saved task using the project tools.' --resume '<saved-session-id>' --output-format json
```

Use `--json-schema '<JSON schema>'` with JSON output when structured output is
needed; check `structured_output` exists before receiving it, and preserve the
returned `session_id`. The project driver still implements Codex only. The
fixtures check shared local tool arguments and documented Claude envelope/flags;
they do not establish a deployed Claude driver or a real Claude session.

Use the official binary and normal supported
[authentication](https://code.claude.com/docs/en/authentication). `--bare` requires
API/provider authentication and skips subscription OAuth; these examples omit it.
No subscription credentials are copied into another SDK and no paid API fallback
is selected. Future provider rollout should check the installed CLI version/help
and offline contracts before owner-authorized invocation. Hosted product use has
separate [official integration terms](https://code.claude.com/docs/en/legal-and-compliance).
