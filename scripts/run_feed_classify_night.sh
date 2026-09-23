#!/usr/bin/env bash
# Classify the bulk quant feed (scripts/harvest_feed.py) in the owner's night
# window, honouring the text endpoint's rolling 5-hour quota: classify stops
# itself on a 429 and writes the shared cool-down file; this loop sleeps until
# the cool-down ends and continues. Order: articles, then papers; repos wait
# for a keyword prefilter (the >=100-star pull is mostly general software).
# Stops at DEADLINE_UTC (HHMM, default 2330) and simply resumes on the next run.
#
#   setsid nohup scripts/run_feed_classify_night.sh >> logs/feed-classify-night.log 2>&1 &
set -u
cd "$(dirname "$0")/.."
deadline=${DEADLINE_UTC:-2330}
cool=data/features/earnings_text_scores/next_try_at.json

cooldown_seconds() {
  [ -f "$cool" ] || { echo 0; return; }
  python3 - "$cool" <<'PY'
import json, sys
from datetime import datetime, timezone
t = json.load(open(sys.argv[1])).get("next_try_at", "")
try:
    end = datetime.fromisoformat(t.replace("Z", "+00:00"))
except ValueError:
    print(0); raise SystemExit
print(max(0, int((end - datetime.now(timezone.utc)).total_seconds())))
PY
}

for corpus in articles papers; do
  while [ "$(date -u +%H%M)" -lt "$deadline" ]; do
    wait_s=$(cooldown_seconds)
    if [ "$wait_s" -gt 0 ]; then
      echo "$(date -u +%FT%TZ) cool-down ${wait_s}s"
      sleep $((wait_s + 30))
      continue
    fi
    out=$(uv run python scripts/harvest_feed.py classify --corpus "$corpus" --max-calls 100 2>&1 | tail -1)
    echo "$(date -u +%FT%TZ) $corpus: $out"
    case "$out" in
      *"nothing pending"*) break ;;
      *"no pulled items"*) break ;;
    esac
  done
done
echo "$(date -u +%FT%TZ) night run ends"
