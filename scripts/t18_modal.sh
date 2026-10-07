#!/usr/bin/env bash
# T-20261006-18 Modal jobs (engine data synced once to the oc-data volume).  Usage: scripts/t18_modal.sh <stage> [nshards]
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ST="$1"; N="${2:-1}"
DATA=(--data data/research/equity_book/panel --data data/research/equity_book/prices --data data/research/equity_book/alpha/book_v1
      --data data/research/equity_book/risk --data data/research/equity_book/etf_daily.parquet --data data/research/vix
      --data data/research/t18_library/factors --data data/research/t18_library/ind --data data/research/t18_library/merge_map.json
      --data data/research/equity_book/realism_ladder)
case "$ST" in
  tier1)    OUT=data/research/t18_library/series;  CMD=(uv run python scripts/t18_engine.py tier1 --shard '{shard}' --nshards '{nshards}'); CPU=2; MEM=5; TO=45 ;;
  tier2)    OUT=data/research/t18_library/series;  CMD=(uv run python scripts/t18_engine.py tier2); CPU=2; MEM=5; TO=30 ;;
  tier3)    OUT=data/research/t18_library/series;  CMD=(uv run python scripts/t18_engine.py tier3 --shard '{shard}' --nshards '{nshards}'); CPU=2; MEM=5; TO=90 ;;
  tier3diag) OUT=data/research/t18_library/series; CMD=(uv run python scripts/t18_engine.py tier3diag IntMom); CPU=2; MEM=5; TO=60 ;;
  lane)     OUT=reports/research/iterations/t20261006_18_library_batch1; CMD=(uv run python scripts/t18_lane.py --shard "{shard}" --nshards "{nshards}"); CPU=2; MEM=6; TO=60; DATA+=(--data data/sip/daily --data reports/research/iterations/t20261006_18_library_batch1_lane/candidate-manifest.json) ;;
  placebo)  OUT=data/research/t18_library/placebo; CMD=(uv run python scripts/t18_analyze.py placebo); CPU=2; MEM=5; TO=60 ;;
  identity) OUT=data/research/t18_library/identity_modal; CMD=(uv run python scripts/t18_engine.py identity); CPU=2; MEM=5; TO=30 ;;
  *) echo "unknown $ST"; exit 2 ;;
esac
python3 scripts/modal_run.py --job "t18-$ST" --cpu "$CPU" --memory-gib "$MEM" --timeout-min "$TO" --shards "$N" "${DATA[@]}" --out "$OUT" --fetch-to "data/research/t18_library/modal_$ST" -- "${CMD[@]}"
