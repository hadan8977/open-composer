#!/usr/bin/env bash
# Phase 2 of T-20261006-22 in one Modal container: rebuild the store, copy the phase-1 selection, then in
# parallel: 100-seed placebos (net and gross), the reproduction-anchor diagnostic, ridge and LightGBM rankers.
set -euo pipefail
export T22_RESULTS=data/research/t22_results2
mkdir -p "$T22_RESULTS"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run python scripts/t22_build.py > "$T22_RESULTS/log_build.txt" 2>&1
cp data/research/t22_sel/selected.json "$T22_RESULTS/selected.json"
uv run python scripts/t22_stage2.py placebo --n 100 > "$T22_RESULTS/log_placebo.txt" 2>&1 &
p1=$!
uv run python scripts/t22_run.py --universe 1000 --resid ind --L 1 --H 1 --exec open --start 2017-09-29 --end 2026-09-15 --tag anchor > "$T22_RESULTS/log_anchor.txt" 2>&1 &
p2=$!
OMP_NUM_THREADS=1 uv run python scripts/t22_ml.py --model ridge > "$T22_RESULTS/log_ridge.txt" 2>&1 &
p3=$!
OMP_NUM_THREADS=1 uv run python scripts/t22_ml.py --model lgbm > "$T22_RESULTS/log_lgbm.txt" 2>&1 &
p4=$!
for p in $p1 $p2 $p3 $p4; do wait "$p"; done
echo phase2 done
