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
# Usage:
#   scripts/run_capped.sh [--mem 1.8G] [--swap 1G] [--min-free-gb N] -- <command> [args ...]
set -euo pipefail

MEM_MAX="1.8G"
SWAP_MAX="1G"
MIN_FREE_GB=""
while [ $# -gt 0 ]; do
    case "$1" in
        --mem) MEM_MAX="$2"; shift 2 ;;
        --swap) SWAP_MAX="$2"; shift 2 ;;
        --min-free-gb) MIN_FREE_GB="$2"; shift 2 ;;
        --) shift; break ;;
        *) break ;;
    esac
done
if [ $# -eq 0 ]; then
    echo "usage: $0 [--mem 1.8G] [--swap 1G] [--min-free-gb N] -- <command> [args ...]" >&2
    exit 2
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

# Raise our own oom_score_adj so that if system-wide pressure somehow happens
# anyway, this job is the victim rather than the orchestrator. Raising is
# always permitted; this also discards any protective adj inherited from the
# parent session.
echo 200 > /proc/self/oom_score_adj 2>/dev/null || true

exec systemd-run --scope -q --collect \
    --slice=research-capped \
    -p MemoryMax="$MEM_MAX" -p MemorySwapMax="$SWAP_MAX" \
    -- "$@"
