#!/usr/bin/env bash
# driver: run extraction, back off on limits, stop when fetch is done and nothing is left
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
python=.venv/bin/python
if [ ! -x "$python" ]; then
  echo "t03: .venv/bin/python unavailable; next_action=repair_local_environment" >&2
  exit 1
fi
mkdir -p logs
while true; do
  out=$("$python" scripts/t03_llm_extract.py "$@" 2>&1)
  rc=$?
  echo "$(date -u +%FT%TZ) exit=$rc $out" >> logs/t03_llm.log
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 75 ]; then
    echo "$(date -u +%FT%TZ) no progress; stopped exit=$rc; next_action=inspect_failure_state_before_owner_restart" >> logs/t03_llm.log
    exit "$rc"
  fi
  # A controlled probe is one invocation, never an automatic retry loop.
  case " $* " in *" --recovery-probe "*) exit "$rc" ;; esac
  if echo "$out" | grep -q "to extract 0;" && ! pgrep -f t03_fetch_snippets >/dev/null; then break; fi
  if [ "$rc" -eq 75 ]; then
    if ! t=$("$python" -c "import json,datetime as d,math;v=json.load(open('data/features/economic_links/_llm/next_try_at.json'));assert not v.get('blocked');print(max(60,math.ceil((d.datetime.fromisoformat(v['next_try_at'])-d.datetime.now(d.timezone.utc)).total_seconds())))"); then
      echo "$(date -u +%FT%TZ) no progress; invalid retry marker; next_action=inspect_retry_marker_before_restart" >> logs/t03_llm.log
      exit 21
    fi
    sleep "$t" || exit "$?"
  else
    sleep 600 || exit "$?"
  fi
done
