#!/usr/bin/env bash
# T-20261006-18 stage chain: every stage goes through scripts/heavy_run.sh, retries while the gate says 75/76,
# is resumable (stages skip finished outputs) and stops on any other failure.
cd "$(dirname "${BASH_SOURCE[0]}")/.."
LOG=/tmp/t18_chain.log
run() {  # name, command...
    local name="$1"; shift
    while true; do
        echo "[$(date -u +%H:%M:%SZ)] stage $name start" >> "$LOG"
        scripts/heavy_run.sh --mem 0.8G --wait-min 20 -- "$@" >> "$LOG" 2>&1
        rc=$?
        echo "[$(date -u +%H:%M:%SZ)] stage $name rc=$rc" >> "$LOG"
        if [ $rc -eq 0 ]; then return 0; fi
        if [ $rc -eq 75 ] || [ $rc -eq 76 ] || [ $rc -eq 124 ]; then sleep 120; continue; fi
        echo "stage $name FAILED rc=$rc" >> "$LOG"; exit $rc
    done
}
for st in "$@"; do
    case "$st" in
        events)   [ -f data/research/t18_library/acct_events.parquet ] || run events uv run python scripts/t18_factors.py events ;;
        price)    run price uv run python scripts/t18_factors.py price ;;
        assemble) run assemble uv run python scripts/t18_factors.py assemble ;;
        identity) [ -f data/research/t18_library/identity.json ] || run identity uv run python scripts/t18_engine.py identity ;;
        merge_map) [ -f data/research/t18_library/merge_map.json ] || run merge_map uv run python scripts/t18_analyze.py merge_map ;;
        tier1)    run tier1 uv run python scripts/t18_engine.py tier1 ;;
        tier2)    run tier2 uv run python scripts/t18_engine.py tier2 ;;
        placebo)  [ -f data/research/t18_library/placebo/placebo_gross.json ] || run placebo uv run python scripts/t18_analyze.py placebo ;;
        tier3)    run tier3 uv run python scripts/t18_engine.py tier3 ;;
        lane)     run lane uv run python scripts/t18_lane.py ;;
        *) echo "unknown stage $st" >> "$LOG"; exit 2 ;;
    esac
done
echo "[$(date -u +%H:%M:%SZ)] chain done: $*" >> "$LOG"
