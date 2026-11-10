#!/usr/bin/env bash
# Re-run a heavy_run.sh command until it succeeds: 76 (lock/memory wait timed out) retries at once,
# 75 (quiet window) sleeps 10 minutes, anything else stops.  Jobs are restartable per month.
#   scripts/t21_intraday_ml/retry_heavy.sh <command> [args ...]
cd "$(dirname "$0")/../.."
while true; do
    scripts/heavy_run.sh --mem 0.8G -- "$@"
    rc=$?
    case $rc in
        0) exit 0 ;;
        76) echo "$(date -u +%FT%TZ) heavy_run 76, retry" ;;
        75) echo "$(date -u +%FT%TZ) heavy_run 75 (quiet window), sleep 600"; sleep 600 ;;
        *) echo "$(date -u +%FT%TZ) rc=$rc stop"; exit $rc ;;
    esac
done
