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
# Usage:
#   scripts/run_capped.sh [--mem 1.8G] [--swap 1G] -- <command> [args ...]
set -euo pipefail

MEM_MAX="1.8G"
SWAP_MAX="1G"
while [ $# -gt 0 ]; do
    case "$1" in
        --mem) MEM_MAX="$2"; shift 2 ;;
        --swap) SWAP_MAX="$2"; shift 2 ;;
        --) shift; break ;;
        *) break ;;
    esac
done
if [ $# -eq 0 ]; then
    echo "usage: $0 [--mem 1.8G] [--swap 1G] -- <command> [args ...]" >&2
    exit 2
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
