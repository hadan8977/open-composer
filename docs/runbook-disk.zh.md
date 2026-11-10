# Disk operations

Disk maintenance is centralized and deliberately light. Research tasks need no disk registration, scan or cleanup step. `scripts/disk_guard.py` uses [config/disk-policy.yaml](../config/disk-policy.yaml); it must not clean the owner's other projects or live services sharing the root partition.

## Automatic maintenance

Hourly at minute 17, cron runs:

```bash
nice -n 19 ionice -c3 .venv/bin/python scripts/disk_guard.py run
```

Below 80% usage, it reads filesystem usage, refreshes lightweight status and exits without a directory scan. Status includes ordinary available space as a percentage of filesystem total, separately from reserved/unavailable blocks. The 50% ordinary-available goal yields `below_capacity_goal` below that level even when emergency cleanup is not due; this lightweight warning does not add scans or broaden deletion permissions. At 80% it cleans caches, disposable `/tmp/open-composer-scratch` entries older than seven days, then explicitly registered expired backups; it stops at 75%. Only at 90% may it archive minute-data years at least two years old and replace local directories with links into `/mnt/gdrive`. Current and previous calendar years stay local. `/tmp/open-composer-disk-guard.lock` prevents overlap.

Each action appends to `reports/ops/disk-ledger.jsonl`. Lightweight status is at `reports/ops/disk-status.json`; logs are at `logs/disk_guard.log`. A full directory scan is on demand. Remaining usage at or above 90% returns exit code 3 for interactive handling; more disk or deletion of still-used data needs an owner decision.

## Deletion and archive contracts

- Direct deletion is limited to configured allowed roots (repository `data/` and `/tmp`). Cache purges use their configured tools. Protected paths and ancestors containing them cannot be deleted. The policy includes `/opt`, `/etc`, `/var/lib`, `/root/.config`, `/root/backup`, `/root/.claude`, `/root/.paseo`, research/live equity-book snapshots, `data/live/backup-refresh` (Drive pointer containers), `data/sip/daily`, `data/sec`, irreplaceable `data/options` snapshots and `/tmp/claude-0`.
- Never follow or delete symlinks. Skip paths containing an active process's working directory or open files.
- Backups are archived file-for-file to `archive/open-composer/...` on Drive before deletion. `rclone check --one-way` must exit 0 and report exactly `0 differences found`. A held task must be `done` or `cancelled`; open tasks retain their backups. Verification failures preserve local copies.
- Generic names such as `backup-*` are report-only. Automatic backup actions require an explicit policy entry; a name or age does not establish permission. Research evidence, models and ledgers stay outside disposable scratch.
- Project scratch age uses the newest modification time anywhere in the subtree. Never age-delete `claude-*`, system directories, sockets, locks or the uv cache; the exact keep/archive patterns live in the configuration.
- Use the guard for managed deletion; do not bypass the existing project restriction on `rm -rf`. Every deletion/archive remains auditable in the ledger.

## Inspect and restore

```bash
.venv/bin/python scripts/disk_guard.py status
.venv/bin/python scripts/disk_guard.py run --all --dry-run
```

`scripts/run_capped.sh --min-free-gb N` remains optional; it is not a new research prerequisite.

Restore an archived backup with `gdrive download archive/open-composer/<path> --local <target>` (which checks local space), or read `/mnt/gdrive/archive/open-composer/<path>`. For a warm minute-data year, replace its link with a local download using `gdrive download datasets/sip/minute/<year> --local data/sip/minute/<year>` after confirming room.

Drive reads consume local cache space: `/root/.cache/rclone` can use 20 GB, evicted after one idle hour. Include that space when planning a large historical read. `data/sip-hist` is a link to `/mnt/gdrive/datasets/sip-hist`; its consumers include `scripts/cache_minute_panel.py`, `scripts/build_intraday_daily_features.py` and `open_composer/research/features/intraday_daily.py`.

## Research artifact archive

For explicitly selected completed or closed research payloads, use the manual
operator documented in [research-artifact-archive.md](research-artifact-archive.md).
It shares the existing disk guard lock, uploader and ledger, verifies immutable
Drive objects before releasing local bytes, and keeps a searchable local index
and task summaries under `reports/research/archive/`. Active research inputs,
paper dependencies, unique checkpoints and explicitly retained evidence stay
local. Age alone never triggers research artifact deletion; this adds no job or
schedule to hourly maintenance.

The 2026-11-03 owner decision supersedes the blanket local hold on completed HF
payloads. Its code, reports, manifests, ledgers and small models remain local;
completed large inputs and trajectories require exact selection and verified
permanent archival. A possible future rerun alone does not require local storage.

`watch` now includes Hadan releases and the shared work/finance roots. This is
reporting only. Hadan deployment growth requires retiring noncurrent/nonprevious
build environments through the existing encrypted archive route after checking
fixed references and live readers; hourly cache purging cannot recover those
bytes. Keep both current releases and all active paper/Martin dependencies.

Private old sessions, account-bearing inputs and complete inactive project copies
use the separate permanent encrypted Restic v2 repository recorded in
`reports/ops/disk-half-recovery-20261103/private/`. The original `vps-backup`
repository, password file, ACLs and retention remain unchanged. Verify all remote
encrypted object identities, sizes and hashes before releasing local sources.
An archived directory keeps a local restore instruction and invalid `.git` guard;
an old database path must fail clearly until restored, never become an empty DB.

For subsequent maintenance, reuse the existing on-demand `status` entry to
compare release/work roots with the saved 2026-11-03 inode inventory; keep the
hourly path free of directory sweeps. `df` available / filesystem total must be
at least 50% for this recovery acceptance; the cleaner's 75% stop threshold is
an emergency cache policy, not evidence that this capacity goal was maintained.
At a completed maintenance batch, use the existing research `catalog` entry for
public payloads and retain the private encrypted restore indexes separately.
Retire unused Hadan environments after checking current/previous and fixed/live
references, rather than expecting repeated cache purges to remove deployments.
The publishing code and currently running releases are unchanged by this task.

The independent encrypted repository is permanent; its local staging may be
removed after exact remote object identity, size and hash acceptance. Before
reusing its task operator, hydrate that same existing repository and verify it;
never initialize a fresh repository over the permanent remote namespace. The
operator now rejects missing staging or a different pinned repository config.
These are maintenance actions through existing entries, not research-worker
steps, a new timer, or an automatic deletion policy for other projects.

The 2026-11-04 completion keeps closed HF economic pervariant trade-ledger
content offline in `hf-factor-return/local-ledgers/`, not in disposable cache.
This protected directory contains the lossless archive, original member hashes,
permissions/times and an explicit restore helper. Cold JSON origins must fail
clearly until restored; central trial/production ledgers and current consumers
remain ordinary local files. Do not archive this local evidence copy.

For subsequent bulk task mirrors, set the native per-job `_config.Transfers` to
1 (the finite task adapter is `reports/ops/disk-half-recovery-20261103/native_task_upload.py`).
Keep the original bandwidth timetable and global rclone service configuration.
A capped submitting process does not cap the existing rclone daemon's live
upload buffers: sixteen 64 MiB chunks can consume roughly one GiB there. Admit
new transfer work against actual daemon memory and the existing 500 MiB floor;
finish current atomic transfers before yielding resources. Avoid another whole
repository mirror/check per small batch when one verified batch can cover it.

Before releasing scientific inputs, inspect the current consumer's complete
producer/default/fallback/fit/account/report chain. A completed producer, old
mtime, or one scan without an open descriptor does not establish that its inputs
are unused. The current Martin closure is recorded with 645 paths and 38 original
manifests; its 133 required original files were received locally at their exact
hashes before numerical continuation. This adds no research-worker registration
step or standing coordinator.
