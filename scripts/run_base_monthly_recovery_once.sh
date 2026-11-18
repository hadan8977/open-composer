#!/usr/bin/env bash
# One bounded wait/fit/install child. No service, cron, retry or date roll.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT_PATH="${1:-/root/codex-test/oc-paper-recovery-20261103/research/paper_recovery_20261103/base/current-input-02/context.json}"
DECISION_PATH="$PROJECT_ROOT/reports/owner/paper-recovery-20261103/owner-date-exception.json"
OUTPUT_PATH="$PROJECT_ROOT/reports/paper/diagnostics/base-monthly-recovery-20261103/model"
FIT_TIMEOUT_SECONDS="$("$PROJECT_ROOT/.venv/bin/python" - "$DECISION_PATH" <<'PY'
import json, sys
from datetime import UTC, datetime
decision = json.load(open(sys.argv[1]))
deadline = datetime.fromisoformat(decision['actual_fit_seal_deadline'])
remaining = (deadline - datetime.now(UTC)).total_seconds()
if remaining <= 0:
    raise SystemExit('Actual fit deadline passed; no catch-up or date roll')
print(f'{remaining:.3f}')
PY
)"
cd "$PROJECT_ROOT"
exec env OPEN_COMPOSER_ROOT="$PROJECT_ROOT" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    "$PROJECT_ROOT/scripts/run_capped.sh" --mem 512M --swap 512M --wait-min 0 -- \
    timeout --signal=KILL "$FIT_TIMEOUT_SECONDS" \
    "$PROJECT_ROOT/.venv/bin/python" -m open_composer.paper_runtime.six.monthly_base_model \
    --root "$PROJECT_ROOT" --context "$CONTEXT_PATH" --owner-exception "$DECISION_PATH" \
    --output "$OUTPUT_PATH" --wait-until-cutoff --install
