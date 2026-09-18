#!/usr/bin/env bash
# Run card H-20260918-06's placebo pass in the overnight window.
#
# The grid pass (96 cells) takes about an hour; the placebo pass is 8 family
# picks times the seed count and takes hours, so the two are separate modes and
# the placebo pass writes placebo.parquet after every cell. That means it can be
# stopped at any time and resumed, which it has to be: nothing heavy may compete
# with the 23:05-23:45 UTC paper cycle on a 3.9 GB box.
#
#   scripts/etf_pool_placebo_nightly.sh start
#   scripts/etf_pool_placebo_nightly.sh stop
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
# Split so this script's own command line never matches the pattern it greps for.
PATTERN="run_h20260918_06""_etf_pool"
SEEDS="${ETF_POOL_PLACEBO_SEEDS:-20}"

running_pids() {
  ps -eo pid=,args= | grep -F "${PATTERN}" | grep -v grep | awk '{print $1}'
}

case "${1:-}" in
  start)
    if [ -n "$(running_pids)" ]; then
      echo "[etf_pool_placebo] already running; nothing to do"
      exit 0
    fi
    if [ ! -f reports/research/iterations/h20260918_06_etf_pool/cells.parquet ]; then
      echo "[etf_pool_placebo] no cells.parquet yet; the grid pass has to finish first"
      exit 0
    fi
    echo "[etf_pool_placebo] $(date -u +%FT%TZ) start seeds=${SEEDS}" >> logs/h20260918_06_etf_pool.log
    ./scripts/run_capped.sh --mem 1.8G -- uv run python -u scripts/run_h20260918_06_etf_pool.py \
      --placebo-only --seeds "${SEEDS}" --placebo-top 0 \
      >> logs/h20260918_06_etf_pool.log 2>&1
    echo "[etf_pool_placebo] $(date -u +%FT%TZ) exit=$?" >> logs/h20260918_06_etf_pool.log
    ;;
  stop)
    pids="$(running_pids)"
    if [ -z "${pids}" ]; then
      echo "[etf_pool_placebo] not running"
      exit 0
    fi
    echo "[etf_pool_placebo] $(date -u +%FT%TZ) stop pids=${pids}" >> logs/h20260918_06_etf_pool.log
    kill ${pids} 2>/dev/null
    sleep 5
    kill -9 ${pids} 2>/dev/null
    echo "[etf_pool_placebo] stopped; placebo.parquet keeps every finished cell"
    ;;
  *)
    echo "usage: $0 start|stop" >&2
    exit 2
    ;;
esac
