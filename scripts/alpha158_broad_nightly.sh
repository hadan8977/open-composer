#!/usr/bin/env bash
# Build data/features/alpha158_broad in the overnight window only.
#
# Why a window: the box has 3.9 GB total and this build holds ~1.7 GB, which
# leaves too little for the 23:05-23:45 UTC paper cycle (three rotation sleeves
# plus the existing top-50 book). earlyoom on this machine prefers killing the
# agent process, and a paper run that gets killed means no orders for the next
# open. So the build runs 00:30-21:45 UTC and is stopped before the 22:00 UTC
# archive update.
#
# Safe to stop at any time: the builder is per-year and per-symbol-batch
# resumable via data/features/alpha158_broad/_scratch, so "start" always
# continues from the last finished batch rather than recomputing.
#
#   scripts/alpha158_broad_nightly.sh start
#   scripts/alpha158_broad_nightly.sh stop
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
# Split so this script's own command line never matches the pattern it greps
# for; a self-match makes the shell kill itself (exit 144, seen twice today).
PATTERN="build_alpha158""_features"

running_pids() {
  ps -eo pid=,args= | grep -F "${PATTERN}" | grep -v grep | awk '{print $1}'
}

case "${1:-}" in
  start)
    if [ -n "$(running_pids)" ]; then
      echo "[alpha158_broad] already running; nothing to do"
      exit 0
    fi
    # Yield to card H-20260918-06's placebo pass: it is active research and this
    # table serves the demoted factor-screen line. Two 1.7 GB jobs on a 3.9 GB box
    # is how the agent gets OOM-killed.
    POOL_PATTERN="run_h20260918_06""_etf_pool"
    if ps -eo args= | grep -F "${POOL_PATTERN}" | grep -qv grep; then
      echo "[alpha158_broad] etf pool placebo pass is running; yielding"
      exit 0
    fi
    echo "[alpha158_broad] $(date -u +%FT%TZ) start" >> logs/broad_factor_build_driver.log
    ./scripts/run_capped.sh --mem 1.8G -- uv run python scripts/build_alpha158_features.py \
      --universe-root data/features/universe_broad \
      --out-dir data/features/alpha158_broad \
      --extra-daily-root data/sip-delisted/by_year \
      --memory-limit 800MB \
      >> logs/alpha158_broad.log 2>&1
    echo "[alpha158_broad] $(date -u +%FT%TZ) exit=$?" >> logs/broad_factor_build_driver.log
    ;;
  stop)
    pids="$(running_pids)"
    if [ -z "${pids}" ]; then
      echo "[alpha158_broad] not running"
      exit 0
    fi
    echo "[alpha158_broad] $(date -u +%FT%TZ) stop pids=${pids}" >> logs/broad_factor_build_driver.log
    kill ${pids} 2>/dev/null
    sleep 5
    kill -9 ${pids} 2>/dev/null
    echo "[alpha158_broad] stopped"
    ;;
  *)
    echo "usage: $0 start|stop" >&2
    exit 2
    ;;
esac
