# Local research tools

Run these from the repository root on Windows. The local index reads admitted evidence without a model call.

```powershell
$python = '.\.venv\Scripts\python.exe'
$task = '<direction>'
& $python scripts/research_tools.py tasks
& $python scripts/research_tools.py index --prefix "research/$task"
& $python scripts/research_tools.py map --task $task
& $python scripts/research_tools.py failures '<topic>' --task $task
& $python scripts/research_tools.py search '<claim or experiment>' --task $task --budget 2400
& $python scripts/research_tools.py get '<document-id>' --task $task --offset 0 --budget 2400
& $python scripts/research_tools.py context $task --budget 2400
& $python scripts/research_tools.py status --task $task --budget 2400
```

Use the exact direction from `tasks`. Text budgets are characters. Continue with `next_offset` when `omitted` is true. Logs are indexed by metadata and read in bounded byte ranges with `--byte-offset`. A range can split a UTF-8 character. `get` takes an admitted document ID.

The rebuildable index at `runtime/research-tools/knowledge.sqlite3` covers claims, trials, decisions, owner verdicts, capabilities and archive metadata. Check source state, visibility and the index timestamp. Changed sources disappear from reads until reindexed. `status` reports quarantined rows and duplicate source cards. Keep raw cards sharded by strategy and trial ledgers by direction. The derived [catalog](../research/knowledge_consolidation_20261115/) holds cross-direction entities, shards and conflict dispositions.

Design search respects evidence partitions. Use scoped `map` or `context` for the current task’s drafts and checkpoints. Restricted evidence and withheld result tables stay outside the executing agents’ inputs. A source card needs a verified claim and locator. Repeated occurrences share a canonical ID. Cumulative trials, decisions and owner authority retain their original sources.

## Waiting and checkpoints

For a supported lab adapter, write the approved `experiment.json` under the current Worker phase. Return `blocked` with its repository-relative forward-slash path as `checkpoint`, `decision=none`, `wait=null`, and `next_review=reuse`. The driver validates the spec before launching the capped child. It binds the process identity and phase-local `batch-results.json`, waits within its deadline under the direction lock, then resumes the original Worker. Leave the driver unattended through terminal reception. Worker, Lead and implementer issue zero requests while the batch is pending.

On completion the Worker calls `agent_workflow.validate_results(root, packet_path, direction)` and returns the packet path in `results`. A fresh Lead receives the bounded packet and follows linked native evidence as needed. Keep full ledgers on disk. Use the [workflow](../research/README.md) for the decisive-review modes and the accepted A3 example.

Other authorized jobs can declare a structured `wait` bound to the session, run-local markers and process identity. The driver persists terminal events and dispatch receipts, deduplicates unchanged events and reuses completed phases. A local exit can complete a local-only wait. For a remote controller exit, reconcile remote status, outputs and costs. The existing Modal launcher uses `modal run --detach`; its controller normally fetches results and records actual cost.

For recovery, inspect `run.json`, process identities, failure markers and native snapshots. A healthy job continues. An unrecoverable terminal failure can receive a bounded same-scope repair with failed exposure retained. Preserve quota, authentication, owner and resource stops. The driver permits two bounded capacity retries and one Reply-only correction from saved artifacts. Scientific branch/revise requires a concrete next brief and plan review. Unresolved job checkpoints stop before Lead.

```powershell
$run = "research/$task/runs/<id>"
& $python scripts/research_tools.py event-status $run --phase worker
& $python scripts/research_tools.py checkpoint $run --phase worker
& $python scripts/research_round.py resume $task --run-id <id> --timeout-seconds 86400 --follow
```

Use the standalone `research_tools.py wait <run> --phase <phase> --timeout-seconds <seconds>` only for observation under the same lock. The driver owns session resumption. An engine checkpoint can declare `kind=research_checkpoint`, session, inputs, completed and remaining work, `native_resumable` and a bound engine snapshot. An unresolved dispatch stays uncertain until reconciled.

## Provider and usage records

`research/workflow.json` selects the installed provider, model, effort and prompt for each role. Codex, Claude and pi use the same Reply and Results contracts. Resumes preserve the original session, provider and model. The Claude adapter runs the official headless CLI from the repo with structured output and session resumption; its offline fixtures cover the transport. [Headless CLI](https://code.claude.com/docs/en/headless) · [Authentication](https://code.claude.com/docs/en/authentication)

Use `scripts/research_usage.py --run <run>` for shared account pacing. For measured throughput include queueing, all attempts, waits and independent reception. Count distinct native responses across resumed sessions, include cached tokens in total input and report uncached input separately. Missing usage stays unknown. Bill the shared build once.
