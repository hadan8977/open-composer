#!/usr/bin/env bash
# Phase 3 (exploratory cells E1-E3 of contract.md section 17) in one Modal container.
set -euo pipefail
export T22_RESULTS=data/research/t22_results3
mkdir -p "$T22_RESULTS"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run python scripts/t22_build.py > "$T22_RESULTS/log_build.txt" 2>&1
cp data/research/t22_sel/selected.json "$T22_RESULTS/selected.json"
uv run python scripts/t22_ml.py --model ridge --exec close --tag E1a_ridge_close > "$T22_RESULTS/log_E1a.txt" 2>&1 &
p1=$!
uv run python scripts/t22_ml.py --model lgbm --exec close --tag E1b_lgbm_close > "$T22_RESULTS/log_E1b.txt" 2>&1 &
p2=$!
uv run python scripts/t22_ml.py --model lgbm --u 1000 --tag E2a_lgbm_U1000 > "$T22_RESULTS/log_E2a.txt" 2>&1 &
p3=$!
uv run python scripts/t22_ml.py --model lgbm --u 3000 --tag E2b_lgbm_U3000 > "$T22_RESULTS/log_E2b.txt" 2>&1 &
p4=$!
uv run python scripts/t22_ml.py --model lgbm --H 10 --tag E3_lgbm_H10 > "$T22_RESULTS/log_E3.txt" 2>&1 &
p5=$!
for p in $p1 $p2 $p3 $p4 $p5; do wait "$p"; done
echo phase3 done
