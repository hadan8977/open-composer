#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${OPEN_COMPOSER_REPO_DIR:-/srv/open-composer/repo}"
cd "$REPO_DIR"

mkdir -p reports/factors
.venv/bin/oc factor decay-monitor --active-only 2>&1 | tee -a reports/factors/_cron.log
