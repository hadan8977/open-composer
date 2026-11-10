#!/usr/bin/env bash
# T-20261006-15-D: resumable pipeline, every step through the heavy gate (quiet window 18:00-00:45 UTC
# returns 75, we sleep and retry). Detached: setsid nohup scripts/t15d_pipeline.sh > logs/t15d_pipeline.log 2>&1 &
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export POLARS_SKIP_CPU_CHECK=1 UV_CACHE_DIR=/tmp/open-composer-uv-cache
STEPS=(
  "series_etf|uv run python scripts/t15d_run.py series etf"
  "grid_etf|uv run python scripts/t15d_run.py grid QQQ_SPY"
)
for y in 2024 2025 2026; do
  for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
    ym="$y-$m"
    if [ "$ym" \> "2026-10" ] || [ "$ym" \< "2024-06" ]; then continue; fi
    STEPS+=("extract_$ym|uv run python scripts/t15d_extract_stock_minutes.py --months $ym")
  done
done
STEPS+=(
  "series_stock|uv run python scripts/t15d_run.py series stock"
  "grid_stock|uv run python scripts/t15d_run.py grid TOP50,TOP25,TOP10"
)
for step in "${STEPS[@]}"; do
  name="${step%%|*}"; cmd="${step#*|}"
  kills=0
  while true; do
    echo "[$(date -u +%FT%TZ)] step $name start"
    # shellcheck disable=SC2086
    scripts/heavy_run.sh --mem 0.8G -- $cmd
    rc=$?
    echo "[$(date -u +%FT%TZ)] step $name exit $rc"
    if [ "$rc" -eq 0 ]; then break; fi
    if [ "$rc" -eq 75 ] || [ "$rc" -eq 76 ]; then
      sleep 600; continue
    fi
    if [ "$rc" -eq 124 ] || [ "$rc" -eq 143 ] || [ "$rc" -eq 137 ]; then
      kills=$((kills + 1))
      if [ "$kills" -le 4 ]; then sleep 600; continue; fi
    fi
    echo "step $name failed with $rc; stopping"; exit "$rc"
  done
done
echo "[$(date -u +%FT%TZ)] pipeline done"
