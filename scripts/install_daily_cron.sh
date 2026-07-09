#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARKER="# open-composer daily paper cycle"
COMMAND="cd ${ROOT} && uv run python scripts/run_daily_paper_cycle.py"

# Server timezone is expected to be UTC. 13:45 UTC is 09:45 America/New_York
# during daylight saving time and runs after the regular-session open.
CRON_LINE="45 13 * * 1-5 ${COMMAND} ${MARKER}"

tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT

crontab -l 2>/dev/null | grep -vF "${MARKER}" > "${tmp}" || true
printf '%s\n' "${CRON_LINE}" >> "${tmp}"
crontab "${tmp}"
printf 'installed: %s\n' "${CRON_LINE}"
