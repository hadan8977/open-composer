#!/usr/bin/env bash
# resumable loop: rerun the fetch until it finishes (it skips finished accessions)
cd "$(dirname "$0")/.." || exit 2
# Explicit recovery arguments describe a single budgeted invocation. Never
# replenish --limit by silently relaunching it after an interruption.
if [ "$#" -gt 0 ]; then
  exec scripts/run_capped.sh --mem 0.8G -- .venv/bin/python scripts/t03_fetch_snippets.py "$@" >> logs/t03_fetch.log 2>&1
fi
while true; do
  scripts/run_capped.sh --mem 0.8G -- .venv/bin/python scripts/t03_fetch_snippets.py --tag main >> logs/t03_fetch.log 2>&1
  rc=$?
  if grep -q "todo 0 of" logs/t03_fetch.log && [ "$(tail -c 300 logs/t03_fetch.log | grep -c 'todo 0 of')" -ge 1 ]; then break; fi
  [ $rc -eq 143 ] || [ $rc -eq 137 ] && sleep 30 || break
done
