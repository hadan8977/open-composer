# Disk operations

Disk maintenance is centralized and deliberately light. Research tasks need no disk registration, scan or cleanup step. `scripts/disk_guard.py` uses [config/disk-policy.yaml](../config/disk-policy.yaml); it must not clean the owner's other projects or live services sharing the root partition.

## Automatic maintenance

Hourly at minute 17, cron runs:

```bash
nice -n 19 ionice -c3 .venv/bin/python scripts/disk_guard.py run
```

Below 80% usage, it reads filesystem usage and exits without a directory scan. At 80% it cleans caches, disposable `/tmp/open-composer-scratch` entries older than seven days, then explicitly registered expired backups; it stops at 75%. Only at 90% may it archive minute-data years at least two years old and replace local directories with links into `/mnt/gdrive`. Current and previous calendar years stay local. `/tmp/open-composer-disk-guard.lock` prevents overlap.

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
paper dependencies, unique checkpoints and explicitly retained HF evidence stay
local. Age alone never triggers research artifact deletion; this adds no job or
schedule to hourly maintenance.
