#!/usr/bin/env bash
# Run a heavy research job inside a memory-capped cgroup scope.
#
# Why this exists (2026-09-07/08): this box has 3.9GB RAM and 4GB swap. An
# uncapped pandas panel in run_baseline_chain.py reached 2914 MiB RSS, pushed
# free memory and swap below earlyoom's 10% trigger, and earlyoom then killed
# the *Claude Code orchestrator session* rather than the job -- repeatedly,
# five times in two days. That inversion is systemic, not bad luck:
#   * /etc/default/earlyoom passes --prefer '(^|/)(claude|codex)$', which adds
#     +300 badness to any process named claude;
#   * /usr/local/sbin/oom-auto-protect.sh gives every >=400MB process that has
#     been alive >=120s an oom_score_adj of -500, but explicitly excludes
#     claude/codex/node from that protection.
# Net effect: the runaway job was protected, the orchestrator was sacrificed
# (observed 2026-09-07 13:47:39: "claude" badness 985 at 158 MiB killed while
# a 2914 MiB python3 sat at badness 726).
#
# A cgroup MemoryMax fixes the direction of the failure: the limit is enforced
# inside this scope, so the job dies -- resumably, it checkpoints per year and
# per batch -- before system-wide pressure can build and before earlyoom has
# any reason to fire. The scope is placed in the research-capped slice, which
# oom-auto-protect.sh skips, so a capped job is never given the -500 that made
# it outrank the session.
#
# Disk (2026-10-02): the root partition also carries the owner's live service
# /opt/quantcheck, and a full disk kills it. --min-free-gb N (opt-in; research
# jobs that write data use 15, see docs/runbook-disk.zh.md) runs the policy
# cleanup once when fewer than N GB are free and refuses with exit 75 if that
# is still not enough. Without the flag nothing is refused (paper crons), but a
# warning is printed below 10 GB free.
#
# Memory budget (owner 2026-10-07: the project must always leave the owner >=500 MB free;
# config/memory-budget.json, docs/runbook-memory.zh.md). Research jobs run in
# oc-research-capped.slice, inside the project budget (oc.slice, all jobs together
# <=1.2 GB): default --mem 900M, more than 1.2G is refused (use Modal), and a job starts
# only when both the research jobs' group and the box have room for min(--mem, 500 MB)
# of actual use, waiting up to --wait-min (default 60). The check uses what running
# jobs really hold, not their caps, so small jobs run side by side and a big one waits.
# --class paper (paper-book crons)
# runs in paper-capped.slice instead: not queued, not refused, never stopped by the
# governor, no +200 OOM adjustment.
#
# Exit codes: 2 usage or over the job limit; 75 not started (disk, memory wait or
# unknown admission error). Research starts only after an admission exit of 0.
#
# Usage:
#   scripts/run_capped.sh [--mem 900M] [--swap 1G] [--class research|paper] [--wait-min N]
#                         [--min-free-gb N] -- <command> [args ...]
set -euo pipefail

MEM_MAX="900M"
SWAP_MAX="1G"
MIN_FREE_GB=""
JOB_CLASS="research"
WAIT_MIN=60
while [ $# -gt 0 ]; do
    case "$1" in
        --mem) MEM_MAX="$2"; shift 2 ;;
        --swap) SWAP_MAX="$2"; shift 2 ;;
        --min-free-gb) MIN_FREE_GB="$2"; shift 2 ;;
        --class) JOB_CLASS="$2"; shift 2 ;;
        --wait-min) WAIT_MIN="$2"; shift 2 ;;
        --) shift; break ;;
        *) break ;;
    esac
done
if [ $# -eq 0 ] || ! [[ "$JOB_CLASS" =~ ^(research|paper)$ ]] || ! [[ "$WAIT_MIN" =~ ^[0-9]+$ ]]; then
    echo "usage: $0 [--mem 900M] [--swap 1G] [--class research|paper] [--wait-min N]" \
        "[--min-free-gb N] -- <command> [args ...]" >&2
    exit 2
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUDGET=(/usr/bin/python3 "$REPO_DIR/scripts/memory_budget.py")

# --mem in MB (accepts K/M/G suffixes like systemd).
mem_mb() {
    awk -v v="$1" 'BEGIN {
        n = v + 0; u = toupper(substr(v, length(v)));
        if (u == "G") n *= 1024; else if (u == "K") n /= 1024; else if (u !~ /[0-9M]/) n = -1;
        else if (u ~ /[0-9]/) n /= 1048576;
        printf "%d", n }'
}
MEM_MB="$(mem_mb "$MEM_MAX")"
if [ "$MEM_MB" -le 0 ]; then
    echo "run_capped: cannot read --mem '$MEM_MAX'" >&2
    exit 2
fi
free_gb() { df -Pk "$REPO_DIR" | awk 'NR==2 {printf "%d", $4 * 1024 / 1e9}'; }
FREE_GB="$(free_gb)"
if [ -n "$MIN_FREE_GB" ]; then
    if ! [[ "$MIN_FREE_GB" =~ ^[0-9]+$ ]]; then
        echo "run_capped: --min-free-gb needs whole GB, got '$MIN_FREE_GB'" >&2
        exit 2
    fi
    if [ "$FREE_GB" -lt "$MIN_FREE_GB" ]; then
        echo "run_capped: ${FREE_GB} GB free < ${MIN_FREE_GB} GB; running disk_guard" >&2
        timeout 1800 "$REPO_DIR/.venv/bin/python" "$REPO_DIR/scripts/disk_guard.py" run \
            >> "$REPO_DIR/logs/disk_guard.log" 2>&1 || true
        FREE_GB="$(free_gb)"
        if [ "$FREE_GB" -lt "$MIN_FREE_GB" ]; then
            echo "run_capped: refusing, ${FREE_GB} GB free < ${MIN_FREE_GB} GB after cleanup" \
                "(docs/runbook-disk.zh.md)" >&2
            exit 75
        fi
    fi
elif [ "$FREE_GB" -lt 10 ]; then
    echo "run_capped: warning, only ${FREE_GB} GB free on the root partition" >&2
fi

if [ "$JOB_CLASS" = "paper" ]; then
    exec systemd-run --scope -q --collect \
        --slice=paper-capped \
        -p MemoryMax="$MEM_MAX" -p MemorySwapMax="$SWAP_MAX" \
        -- "$@"
fi

# Research job: limit, then wait for room.
JOB_MAX_MB="$("${BUDGET[@]}" config job_max_mb 2>/dev/null || echo 1229)"
if [ "$MEM_MB" -gt "$JOB_MAX_MB" ]; then
    echo "run_capped: --mem ${MEM_MB} MB is over the local job limit ${JOB_MAX_MB} MB" \
        "(config/memory-budget.json); run it on Modal or shrink the job" >&2
    exit 2
fi
DEADLINE=$(( $(date +%s) + WAIT_MIN * 60 ))
until reason="$("${BUDGET[@]}" admit --kind job --mem "$MEM_MB" 2>&1)"; do
    rc=$?
    if [ "$rc" -ne 2 ]; then
        echo "run_capped: refusing, memory check failed (rc=$rc): $reason" \
            "(check scripts/memory_budget.py admit; docs/runbook-memory.zh.md)" >&2
        exit 75
    fi
    if [ "$(date +%s)" -ge "$DEADLINE" ]; then
        echo "run_capped: refusing, $reason (waited ${WAIT_MIN} min; docs/runbook-memory.zh.md)" >&2
        exit 75
    fi
    echo "run_capped: waiting for memory, $reason" >&2
    sleep 30
done

# Raise our own oom_score_adj so that if system-wide pressure somehow happens
# anyway, this job is the victim rather than the orchestrator. Raising is
# always permitted; this also discards any protective adj inherited from the
# parent session.
echo 200 > /proc/self/oom_score_adj 2>/dev/null || true

exec systemd-run --scope -q --collect \
    --slice=oc-research-capped \
    -p MemoryMax="$MEM_MAX" -p MemorySwapMax="$SWAP_MAX" \
    -- "$@"
