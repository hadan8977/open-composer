#!/usr/bin/env bash
# One exact invocation. The finite launcher admits/preallocates every local log
# and terminal record before memory/native entry; no unguarded shell redirects.
set -euo pipefail
cd /root/codex-test/open-composer
export PATH=/root/.hermes/node/bin:/root/.local/bin:/usr/local/bin:/usr/bin:/bin
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
exec .venv/bin/python -m open_composer.intraday_runner.current_initialization_launcher \
  --root /root/codex-test/open-composer --job "${1:?exact job required}" --sha256 "${2:?exact SHA required}"
