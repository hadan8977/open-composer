#!/usr/bin/env bash
# Bulk historical scoring for T2: runs the scorer year by year, idempotently,
# and honours next_try_at.json (written on 429/quota) by sleeping until then.
# Stops when a full pass over all years scores nothing new.
set -u
cd "$(dirname "$0")/.."
export POLARS_SKIP_CPU_CHECK=1
NEXT=data/features/earnings_text_scores/next_try_at.json
LOG=logs/score_earnings_text_loop.log
pass=0
while :; do
  pass=$((pass+1)); new_total=0
  for y in 2024 2025 2026; do
    out=$(./scripts/run_capped.sh --mem 1.8G -- ./.venv/bin/python scripts/score_earnings_text.py --year "$y" 2>&1 | grep -E "done:" | tail -1)
    echo "[$(date -u +%FT%TZ)] pass=$pass year=$y $out" >> "$LOG"
    n=$(echo "$out" | sed -n 's/.*processed=\([0-9]*\).*/\1/p'); n=${n:-0}; new_total=$((new_total+n))
    if [ -f "$NEXT" ]; then
      wait_s=$(./.venv/bin/python - <<'PY'
import json,datetime as dt
t=json.load(open('data/features/earnings_text_scores/next_try_at.json'))
v=t.get('next_try_at') if isinstance(t,dict) else t
w=(dt.datetime.fromisoformat(str(v).replace('Z','+00:00'))-dt.datetime.now(dt.timezone.utc)).total_seconds()
print(int(max(60,min(w,7200))))
PY
)
      echo "[$(date -u +%FT%TZ)] rate-limited; sleeping ${wait_s}s" >> "$LOG"; sleep "$wait_s"; rm -f "$NEXT"
    fi
  done
  [ "$new_total" -eq 0 ] && { echo "[$(date -u +%FT%TZ)] nothing new; done after $pass passes" >> "$LOG"; break; }
done
