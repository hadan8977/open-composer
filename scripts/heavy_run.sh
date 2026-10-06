#!/usr/bin/env bash
# Gate for heavy research commands on this 3.9 GB box (plan v3 review M5,
# 2026-10-06). Research agents run every heavy command through this script:
#
#   scripts/heavy_run.sh [--mem 0.8G] [--min-avail-mb 1000] [--wait-min 30] -- <command> [args ...]
#
# What it enforces, in order:
#   1. Quiet window 18:00-00:45 UTC: the paper pipeline (v1.2 plan 18:30, submit
#      19:20, backup 19:38, check 19:50, reconcile 22:40/23:30, data refresh
#      22:45, targets 00:15) owns the box. Refuses with exit 75; the caller
#      waits, or moves the job to Modal.
#   2. One research heavy job at a time: flock on /tmp/oc-heavy.lock (waits up
#      to --wait-min minutes, then exit 76).
#   3. Enough memory: waits up to --wait-min minutes for MemAvailable >=
#      --min-avail-mb, then exit 76.
#   4. A deadline: the job gets SIGTERM at 17:55 UTC (SIGKILL 60 s later), so it
#      never runs into the quiet window. Jobs must checkpoint and resume.
#   5. A memory cap: runs under scripts/run_capped.sh --mem <mem>.
#
# Exit codes: 75 quiet window or under 5 minutes left; 76 lock or memory wait
# timed out; 124 deadline reached (timeout); otherwise the command's own code.
set -euo pipefail

MEM="0.8G"
MIN_AVAIL_MB=1000
WAIT_MIN=30
while [ $# -gt 0 ]; do
    case "$1" in
        --mem) MEM="$2"; shift 2 ;;
        --min-avail-mb) MIN_AVAIL_MB="$2"; shift 2 ;;
        --wait-min) WAIT_MIN="$2"; shift 2 ;;
        --) shift; break ;;
        *) break ;;
    esac
done
if [ $# -eq 0 ]; then
    echo "usage: $0 [--mem 0.8G] [--min-avail-mb 1000] [--wait-min 30] -- <command> [args ...]" >&2
    exit 2
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK=/tmp/oc-heavy.lock

in_quiet_window() {
    local hm
    hm=$((10#$(date -u +%H%M)))
    [ "$hm" -ge 1800 ] || [ "$hm" -lt 45 ]
}

seconds_to_deadline() {
    local now deadline
    now=$(date -u +%s)
    deadline=$(date -u -d "$(date -u +%F) 17:55" +%s)
    echo $((deadline - now))
}

avail_mb() { awk '/^MemAvailable:/ {printf "%d", $2 / 1024}' /proc/meminfo; }

if in_quiet_window; then
    echo "heavy_run: 18:00-00:45 UTC is the paper-pipeline quiet window; wait until 00:45 UTC or use Modal" >&2
    exit 75
fi

exec 9>"$LOCK"
if ! flock -w $((WAIT_MIN * 60)) 9; then
    echo "heavy_run: another research heavy job held $LOCK for ${WAIT_MIN} min" >&2
    exit 76
fi

waited=0
while [ "$(avail_mb)" -lt "$MIN_AVAIL_MB" ]; do
    if [ "$waited" -ge $((WAIT_MIN * 60)) ]; then
        echo "heavy_run: MemAvailable $(avail_mb) MB < ${MIN_AVAIL_MB} MB after ${WAIT_MIN} min" >&2
        exit 76
    fi
    sleep 30
    waited=$((waited + 30))
done

if in_quiet_window; then
    echo "heavy_run: reached the 18:00 UTC quiet window while waiting" >&2
    exit 75
fi
left=$(seconds_to_deadline)
if [ "$left" -lt 300 ]; then
    echo "heavy_run: under 5 minutes before the 17:55 UTC deadline" >&2
    exit 75
fi

echo "heavy_run: start $(date -u +%H:%M:%SZ), mem cap $MEM, MemAvailable $(avail_mb) MB, deadline in ${left}s" >&2
set +e
timeout --signal=TERM --kill-after=60 "${left}s" "$REPO_DIR/scripts/run_capped.sh" --mem "$MEM" -- "$@"
rc=$?
set -e
echo "heavy_run: end $(date -u +%H:%M:%SZ), exit $rc" >&2
exit "$rc"
