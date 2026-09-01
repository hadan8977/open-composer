#!/bin/bash
# Supervises a fetch_sip_universe.py run: restarts it if it stalls or dies, and
# stops for good once the fetcher writes its _COMPLETE_ marker.
#
# The fetcher is resumable (it skips shards already on disk), so a restart is
# always safe and never re-downloads finished work.
#
# usage: fetch_watchdog.sh <kind> <start_year> <end_year> <logfile>
set -uo pipefail
KIND="$1"; START="$2"; END="$3"; LOG="$4"
cd /root/codex-test/open-composer
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=/tmp/open-composer-uv-cache

MARKER="data/sip/${KIND}/_COMPLETE_${START}_${END}.json"
STALL_SECONDS=900          # no new parquet in 15 min => treat as stalled
MEM_FLOOR_MB=250           # pause rather than push the box into swap death
PATTERN="fetch_sip_universe.py --kind ${KIND} --start-year ${START}"

log() { echo "[watchdog $(date '+%H:%M:%S')] $*" >> "$LOG"; }

while true; do
  if [ -f "$MARKER" ]; then
    log "COMPLETE marker present -> watchdog exiting"
    exit 0
  fi

  if ! pgrep -f "$PATTERN" > /dev/null; then
    free_mb=$(free -m | awk '/^Mem:/{print $7}')
    if [ "$free_mb" -lt "$MEM_FLOOR_MB" ]; then
      log "only ${free_mb}MB available, waiting before (re)start"
      sleep 120; continue
    fi
    log "fetcher not running -> starting ${KIND} ${START}-${END}"
    nohup uv run python scripts/fetch_sip_universe.py \
      --kind "$KIND" --start-year "$START" --end-year "$END" --out data/sip >> "$LOG" 2>&1 &
    sleep 60; continue
  fi

  newest=$(find "data/sip/${KIND}" -name '*.parquet' -printf '%T@\n' 2>/dev/null | sort -rn | head -1)
  if [ -n "$newest" ]; then
    age=$(( $(date +%s) - ${newest%.*} ))
    if [ "$age" -gt "$STALL_SECONDS" ]; then
      log "no new shard for ${age}s -> killing stalled fetcher (resume will skip done shards)"
      pkill -f "$PATTERN"
      sleep 20
    fi
  fi
  sleep 60
done
