# Memory operations

Budget against [config/memory-budget.json](../config/memory-budget.json), never the host's total RAM. Preserve about 500 MiB of available memory for the owner's other projects, conversations and proxy services. This is a sustained reserve: brief dips are possible; the governor responds to duration as well as size.

## Budget and admission

The configuration uses MB to mean MiB. Current limits are:

| Item | Limit or behavior |
|---|---|
| Owner reserve / governor target | 500 / 650 MiB available |
| Project hard RAM cap | `oc.slice`: `MemoryMax=2200M` |
| Project soft RAM range | `MemoryHigh=900M` to `2000M`, adjusted to other workloads |
| Project swap | 3 GiB |
| Research jobs combined | 2458 MiB (`2.4G`), still subject to the parent project cap |
| Local job default / maximum | `900M` / `2.4G` |
| Live background agents, including children | At most 6, subject to actual runtime slots and memory admission |
| Agent start headroom | 200 MiB above the reserve |
| Job start headroom | `min(requested memory, 200 MiB)` above the reserve and within research capacity, measured by actual usage |
| pytest | One process for this repository at a time |

Use these existing entry points when the relevant work is authorized:

```bash
python3 scripts/memory_budget.py status
python3 scripts/memory_budget.py admit --kind agent
scripts/run_capped.sh --mem 900M -- <command>
```

An admission failure is a reason to wait or release an idle agent, not bypass the cap. `run_capped.sh` waits up to `--wait-min` (default 60 minutes); timeout exits 75, invalid/over-limit requests exit 2. Research jobs get OOM adjustment +200. Large data reads also belong inside this wrapper, rather than directly sharing the interactive session's allowance. For heavier work, use the already-authorized remote route described in [the Windows runbook](runbook-windows-compute.zh.md); fallback compute still needs its existing budget admission.

## Enforcement and services

| Group/service | Role |
|---|---|
| `oc-interactive.slice` | Top-level project Paseo sessions; `MemoryLow=350M`. |
| `oc-agents.slice` | Background agents and descendants, including MCP clients and temporary commands. |
| `oc-research.slice/oc-research-capped.slice` | One scope per capped research job; group RAM `2.4G`, swap `2G`, below `oc.slice`. |
| `quant.service` | Read-only Cockpit; `MemoryMax=300M`. |
| `paper.slice/paper-capped.slice` | Paper jobs, outside the research/project budget. Research yields memory to them. |
| `oc-memory-governor.service` | Five-second sampling; `OOMScoreAdjust=-900`, `MemoryMax=60M`, automatic restart. |
| `oc-zswap.service` | zstd/zsmalloc compression; pool at most 25% of RAM, charged to the owning cgroup. |

Below 650 MiB available, the governor lowers project `MemoryHigh` by the shortfall, down to 900 MiB. Above 950 MiB, it relaxes the limit by 100 MiB per tick, up to 2000 MiB. Below the 500 MiB reserve for 30 seconds, it stops the newest research job. Native checkpoints are therefore important; a stop is not proof that a particular job saved successfully.

`/swapfile` and `/swapfile2` provide 4 GiB each, with zswap in front. Compression makes idle agents cheaper; it does not increase physical RAM or remove the parent cap. Six simultaneously busy agents plus a large job can still slow down.

The Paseo Claude provider in `/root/.paseo/config.json` uses `/usr/local/sbin/paseo-claude-launch` (source: `deploy/memory/paseo-claude-launch.sh`). It only groups sessions whose working directory is inside this repository. `paseo.parent-agent-id` or `paseo.schedule-id` identifies background agents; others are interactive. It uses `systemd-run --scope` and `BindsTo=paseo-daemon.service`. A seventh background agent exits 75 and logs under `paseo-claude-launch`; interactive sessions pass. An internal wrapper-check error falls back to normal launch, so inspect `uncapped_project_agents` rather than assuming enforcement succeeded.

`scripts/round_limit_gate.py` pauses relevant scheduled rounds after five minutes of insufficient headroom or a full agent count, and resumes only plans it paused. It does not restore manually paused plans or admit retired rounds. pytest serializes through `/tmp/open-composer-pytest.lock`; `OC_PYTEST_LOCK_WAIT` defaults to 3600 seconds. Choose tests proportionate to the affected behavior; documentation changes do not need pytest.

## Reduce idle memory and avoid host-wide OOM

`/root/.paseo/bin/paseo_memory_maintenance.py` runs hourly (source: `deploy/memory/paseo_memory_maintenance.py`). It archives background agents after two idle hours and top-level sessions after 24, then reaps only their own cgroup processes after ten minutes. `memory.keep=true` preserves a needed agent. The maintenance service has a 20-minute timeout.

Claude's shared gdrive MCP endpoint in `~/.claude.json` is `http://127.0.0.1:5573/mcp`, served by `gdrive-mcp-http.service`; separate stdio clients per agent add avoidable resident memory. This is a deployment fact, not a requirement to install a connector for unrelated work.

OOM preference is research jobs (+200), background project agents (0), project interactive sessions (-300), then other owner sessions (-500). `claude-orchestrator-protect.sh` sets scores by cgroup; `oom-auto-protect.sh` excludes large project processes from protection. earlyoom chooses by actual size without the old `--prefer claude` bias, and excludes infrastructure such as Hermes, Cloudflare, proxies, rclone, quantcheck, Paseo and sshd. The Paseo drop-in `deploy/memory/systemd/paseo-daemon.service.d/50-oom-policy.conf` sets `OOMPolicy=continue`, so one child OOM does not stop all sessions.

Modal's local client (`scripts/modal_run.py`) runs under `run_capped.sh --mem 1G`. Shards in `scripts/modal_app.py` write `<log-name>/shard_<i>.tar.gz` to volume `oc-out`; download one at a time to temporary files, unpack, then remove the returned remote copy. Returning all shard payloads as function results can make the client buffer the entire set despite sequential retrieval.

## Paper jobs and manual recovery

Every command feeding paper orders must use `--class paper`, including commands assembled inside scripts and generated cron lines. Paper jobs do not queue behind research admission and are not stopped by the research governor. Check all callers when changing a shared wrapper: crontab, `scripts/refresh_equity_book_live.py`, `scripts/install_rotation_sleeve_cron.sh`, `scripts/refresh_insider_features_for_paper.sh` and `open_composer/execution/schedule.py` are relevant examples. `tests/test_run_capped_callers.py` checks constructed commands.

A long, already-authorized manual paper refresh should run as a transient service, so archiving the interactive session does not kill it. Use the same command chain as the installed cron entry:

```bash
systemd-run --unit=oc-<name>-manual-$(date -u +%Y%m%dT%H%M) --slice=paper-capped \
  --working-directory=/root/codex-test/open-composer \
  --setenv=HOME=/root --setenv=PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  --setenv=UV_CACHE_DIR=/tmp/open-composer-uv-cache \
  -p MemoryMax=2.4G -p MemorySwapMax=2G \
  /bin/bash -c '<same command chain as crontab>'
```

Inspect `systemctl status oc-<name>-manual-...`, `journalctl -u oc-<name>-manual-...`, and the usual cron log. A short task can use `scripts/run_capped.sh --class paper --mem <N> -- <command>`, but that scope follows the session lifetime.

Known operational limit: full feature-invariance comparisons (`scripts/check_feature_invariance.py`) have used 1.6-2.1 GiB. They can temporarily breach the reserve even outside the project cgroup. Chunked comparison is the intended repair; paper-path code changes require an isolated worktree and interactive review/merge under [AGENTS.md](../AGENTS.md). Do not apply a shared-tree fix to an active paper chain.

## Inspect, install and recover

| Evidence | Location or command |
|---|---|
| Current budget, headroom, agents | `python3 scripts/memory_budget.py status` |
| Governor status, actions, hourly minima | `logs/memory/governor-status.json`, `logs/memory/governor.log`, `logs/memory/hourly.jsonl` |
| Group membership | `systemd-cgls /oc.slice` |
| Refused launches | `journalctl -t paseo-claude-launch` |
| Wrapper health | `paseo_wrapper_configured=true`, `uncapped_project_agents=0` in status |
| Compression/swap | `swapon --show`, `/proc/meminfo`, status fields `zswap_pool_mb` and `zswapped_mb` |
| Coarse historical memory | `sar -r -f /var/log/sysstat/saDD` |

Hourly `ticks_below_reserve` counts five-second samples below the reserve; interpret duration rather than treating a single dip as sustained failure.

The governor rereads `config/memory-budget.json` each tick. Changing a hard limit also requires the matching file in `deploy/memory/systemd/` and `deploy/memory/install.sh`. Installation is idempotent and backs up replaced system files under `/root/backups/memory-budget/`. After an upgrade breaks the provider wrapper, the established repair is `deploy/memory/install.sh --paseo` then `paseo daemon reload`, within maintenance authority.

For an authorized rollback: remove Claude's `command` override from `/root/.paseo/config.json`, run `paseo daemon reload`, stop the governor with `systemctl disable --now oc-memory-governor`, and restore the backed-up system files. Disable compression with `systemctl disable --now oc-zswap`. Removing `/swapfile2` requires enough free RAM/swap to receive its pages before `swapoff /swapfile2` and removal of its fstab entry. These are maintenance procedures, not automatic research actions.
