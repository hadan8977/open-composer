#!/usr/bin/env bash
# Phase 1 of T-20261006-22 inside one Modal container: rebuild the feature store (70 s), run the
# identity checks, the 24 main cells on the recent and stress windows (3 processes), the spec
# selection, offsets, robustness, whole-share, attribution and correlation.
set -euo pipefail
export T22_RESULTS=data/research/t22_results
mkdir -p "$T22_RESULTS"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run python scripts/t22_build.py
uv run python scripts/t22_checks.py --out "$T22_RESULTS/checks.json"
pids=()
for U in 500 1000 3000; do
  uv run python scripts/t22_run.py --universe $U --resid ind pca --L 5 21 --H 1 5 --exec open --tag A > "$T22_RESULTS/log_A_$U.txt" 2>&1 &
  pids+=($!)
done
for p in "${pids[@]}"; do wait "$p"; done
cat "$T22_RESULTS"/log_A_*.txt | grep "R_U" || true
pids=()
for U in 500 1000 3000; do
  uv run python scripts/t22_run.py --universe $U --resid ind pca --L 5 21 --H 1 5 --exec open --start 2017-09-29 --end 2023-08-31 --tag B > "$T22_RESULTS/log_B_$U.txt" 2>&1 &
  pids+=($!)
done
for p in "${pids[@]}"; do wait "$p"; done
uv run python scripts/t22_stage2.py select
(uv run python scripts/t22_stage2.py offsets --window recent; uv run python scripts/t22_stage2.py offsets --window stress) > "$T22_RESULTS/log_offsets.txt" 2>&1 &
p1=$!
uv run python scripts/t22_stage2.py robust > "$T22_RESULTS/log_robust.txt" 2>&1 &
p2=$!
uv run python scripts/t22_stage2.py share > "$T22_RESULTS/log_share.txt" 2>&1 &
p3=$!
uv run python scripts/t22_stage2.py attrib > "$T22_RESULTS/log_attrib.txt" 2>&1 &
p4=$!
for p in $p1 $p2 $p3 $p4; do wait "$p"; done
uv run python scripts/t22_stage2.py corr
echo phase1 done
