# Research artifact archive

This operator maintains cold research payloads through the existing disk guard,
`gdrive` uploader, `rclone` verification and read-only `/mnt/gdrive` mount. It adds
classification and durable local discovery, not another transfer service. There
is no scheduler, remote sync, remote deletion, expiry, or automatic age-based
release. Drive objects are retained indefinitely.

The owner authorized old research artifact classification and archiving on
2026-10-23. A task-specific selection still identifies exactly which completed or
closed material is cold. An old modification date alone does not authorize an
archive. A failed experiment remains a failed experiment after archiving.

## Storage tiers

| Tier | Meaning | Local handling |
| --- | --- | --- |
| Hot | Active work, paper dependencies, unique checkpoints, explicitly retained evidence | Keep local |
| Warm | Possible near-term dependency or pending final acceptance | Keep local until a task-specific decision |
| Cold | Explicitly selected completed or closed task payload with frozen completion evidence | Upload, verify, then optionally replace with an archive link |

Only regular, single-link binary files under `reports/research/program` and
`reports/research/iterations` can enter this operator. The policy additionally
protects current Martin/paper/CASH paths, explicitly local-retained artifacts,
checkpoint paths, credentials, and the existing disk guard's protected roots.
Directory payloads, symlink sources or ancestors, arbitrary roots and live uses
are refused. Scientific reports, code, frozen contracts and summaries remain
local. ZIP member names receive an additional credentials-name check; this does
not certify opaque binary packages as free of secrets. The selecting owner must
establish that packages contain authorized research material.

On 2026-11-03 the owner authorized verified cold migration of completed HF large
payloads, superseding its earlier blanket local hold. The policy no longer blocks
the entire HF tree by name. Active inputs, unique checkpoints, code, conclusions,
manifests, ledgers and small models retain their existing local protection; exact
task-specific selections and all native verification requirements still apply.

Runtime dependencies include indirect refresh and consumer-binding inputs. The
ready-unit manifest alone is insufficient: for example,
`refresh_equity_book_live.py` binds current-year `intraday_daily` before rebuilding
daily features. Keep such inputs local even when their modification dates are old;
review the complete producer entrypoint before treating a copied feature as cold.

## Prepare and inspect

Run from the repository root:

```bash
.venv/bin/python scripts/research_artifact_archive.py prepare \
  --selection reports/ops/whole-host-disk-cleanup-20261023/followup/archive-selection.json
```

The selection contains `recommended_first_batch` groups. Each group provides
`id`, `category`, optional `task_id`, a `completion` value beginning with
`accept`, `summary_zh`, `authoritative_evidence` paths, and exact `files[].path`.
Preparation also checks any source inode, size or mtime included by the selector.
Pending-review alternatives in `optional_second_batch` are not admitted.

Preparation reads local files, hashes SHA-256 and MD5 in one streaming pass, and
freezes device/inode/size/mtime/link count plus all completion-evidence identities
and hashes. It creates an immutable batch under
`reports/research/archive/batches/<batch-id>.json` and prints its path. It uploads
nothing and does not copy or alter any payload. Review that concrete batch before
execution. Each category/task/date namespace ends in a content hash:

```text
archive/open-composer/research/v1/<category>/<task>/<YYYY-MM>/<SHA256>/<original-filename>
```

The original basename is preserved because the existing native uploader and
`rclone check` compare the exact file against its remote parent. Different source
versions with equal sizes remain distinct if their hashes differ.

## Execute, release, and resume

```bash
# Upload and verify, retaining the local originals.
.venv/bin/python scripts/research_artifact_archive.py execute --batch BATCH_PATH

# Also replace each verified unchanged source with its readable Drive mount link.
.venv/bin/python scripts/research_artifact_archive.py execute --batch BATCH_PATH --release
```

Both commands take the same `/tmp/open-composer-disk-guard.lock` used by hourly
maintenance. Payloads upload directly from their existing paths with
`disk_guard.upload_and_verify(Item(verify="hash"))`; no second local archive is
built. Existing content-addressed objects are checked rather than overwritten.
Remote ID, byte size, and a matching MD5 or SHA-256 are mandatory; a contradictory
available hash fails verification. Google Drive normally supplies MD5. The
catalog retains the independent local SHA-256 as well.

Before release, the operator rechecks source bytes, completion evidence, source
identity and active process use. The real mount must be available and the exact
target must have the expected size. It writes and fsyncs a local recovery event
containing the original path, remote object ID, hashes and restore command before
atomically replacing the source with a prepared link. It also appends to the
existing disk ledger. A failed upload/check, changed file/evidence, active task
or unavailable mount leaves the original regular file in place and records
`retained_retryable`. Exit code 2 identifies a retained item needing attention.

Rerun the same command to resume. It reuses a verified existing remote object;
it never treats an arbitrary source symlink as completed work. An interruption
after replacement but before the final event is recoverable from the durable
`release_intent` event, exact link target and renewed remote metadata checks.
Changing policy requires preparing a new batch. Catalog rebuilding remains
possible for historical batches after policy updates.

The global maintenance lock coordinates cleanup operators, not all possible
research writers. Selection must therefore target inactive, closed scopes;
process/identity checks are practical additional protections, not a general
transactional filesystem or protection against a malicious concurrent writer.

## Local searchable index and legacy discovery

```bash
.venv/bin/python scripts/research_artifact_archive.py catalog
.venv/bin/python scripts/research_artifact_archive.py legacy-scan
.venv/bin/python scripts/research_artifact_archive.py backup-catalog
```

The ordinary catalog reads local immutable batches and events. Outputs are:

- `reports/research/archive/catalog.json`, `.csv`, and a standalone searchable `.html`.
- `reports/research/archive/tasks/<task>/summary.md`, with Chinese summaries,
  actual outcome, original and remote paths, ID, hashes, status and restore command.
- `reports/research/archive/events.jsonl`, the append-only recovery/audit index.

`legacy-scan` walks local `reports/research` directory entries without following
symlinks or opening/statting remote targets. Existing archive links under
`/mnt/gdrive/archive/open-composer` enter `legacy-catalog.json` and
`legacy-task-summaries.json`. Matching historical disk-ledger receipt fields are
included when present. These entries are clearly marked as historical link-only
or historical link-plus-receipt evidence; they are **not newly reverified**.
Existing Drive directories are not reorganized or reuploaded. Legacy grouping
preserves original task paths and does not invent missing scientific conclusions.
Original paths listed in this operator's immutable batches are excluded from
legacy discovery: their links remain in the managed catalog instead of being
counted again as historical archives. This exclusion reads only local batch
metadata and does not follow source links.

`backup-catalog` writes one small metadata-only tar under local `_snapshots/`,
excluding prior snapshots and all original payloads. It copies that snapshot via
the same native hash verifier to the immutable `_catalog/` namespace on Drive,
then requires remote ID/size/hash agreement. It never releases the local snapshot
or deletes anything remotely. `catalog-backup-latest.json` and each snapshot's
receipt contain its SHA-256, Drive ID/path and download command. Run this explicit
command after a substantive archive batch or legacy discovery; no timer is added.
To recover the catalog, download the snapshot to a new local directory, verify its
SHA-256, inspect tar member names, and extract only to that new directory before
reconciling the saved batches/events with the current local index.

## Restore one payload

The per-item catalog stores a `restore_download_command` argument list, also
rendered as a shell command in the task summary. It downloads to a sibling
`<original-path>.restore-local`, never through the read-only link. First check
that sufficient local space is available. Then:

1. Run that exact `gdrive download ... --local ...restore-local` command.
2. Run `sha256sum -- /absolute/path.restore-local` and compare the full digest
   against the catalog's SHA-256. A size-only check is insufficient.
3. Confirm that the original is still the expected archive link and no current
   process is using the file. Replace that link with the verified local sibling
   using `os.replace` or an equivalent same-directory atomic rename.
4. Record the restoration in the existing disk ledger. Keep the remote object
   and original archive receipt permanently.

Restoring bytes does not reset exposure, trial counts, historical failures or
frozen criteria, and does not create permission for a new research run.
