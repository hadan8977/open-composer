#!/usr/bin/env bash
# Install the nightly cron entries for the three H-20260918-05 ETF rotation
# sleeves. Idempotent: every line carries a marker and is replaced on reinstall.
#
# Card: reports/research/hypotheses/H-20260918-05-recent-window-etf-menu.md
#
# Server timezone is UTC. The SIP daily archive updates at 22:00 UTC, after the
# 20:00 UTC regular close, so a 23:0x signal run sees the session that just
# closed. Day market orders submitted after the close are queued by Alpaca and
# execute at the next 09:30 America/New_York open.
#
# Ordering matters. Reconciliation must run BEFORE the next submission, because
# each sleeve plans against its own fill ledger (execution_policy.position_scope
# = strategy_ledger) and the planner refuses to submit while an earlier session
# is unreconciled. Reconcile lands at 14:0x UTC, after the open; submission at
# 23:3x UTC, after the close.
#
# Existing entries this schedule deliberately avoids: 22:00 archive update,
# 22:30 freshness, 23:00 model-ranking observation, 23:15 and 23:30 the
# us_recent_high_return_top50 cycle and rehearsal, 14:00 its reconciliation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENVPREP="export PATH=\"\$HOME/.local/bin:\$PATH\" && export UV_CACHE_DIR=/tmp/open-composer-uv-cache"
CAPPED="./scripts/run_capped.sh --mem 1.8G --"

SLEEVES=(
  "us_etf_sector_rotation_252_top2_weekly"
  "us_etf_growth_rotation_blend_top2_monthly"
  "us_etf_levered_rotation_63_top2_monthly"
)
SIGNAL_MIN=(5 7 9)
SUBMIT_MIN=(35 40 45)
RECONCILE_MIN=(5 7 9)

tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT
crontab -l 2>/dev/null | grep -vF "# open-composer rotation sleeve" > "${tmp}" || true

for i in "${!SLEEVES[@]}"; do
  name="${SLEEVES[$i]}"
  spec="strategy_specs/drafts/${name}.yaml"
  marker="# open-composer rotation sleeve ${name}"
  printf '%s\n' \
    "${RECONCILE_MIN[$i]} 14 * * 1-5 cd ${ROOT} && ${ENVPREP} && uv run oc paper rehearsal-reconcile ${spec} >> logs/rotation_${name}.log 2>&1 ${marker} reconcile" \
    "${SIGNAL_MIN[$i]} 23 * * 1-5 cd ${ROOT} && ${ENVPREP} && ${CAPPED} uv run python scripts/run_daily_paper_cycle.py --strategy ${name} --spec ${spec} >> logs/rotation_${name}.log 2>&1 ${marker} signal" \
    "${SUBMIT_MIN[$i]} 23 * * 1-5 cd ${ROOT} && ${ENVPREP} && ${CAPPED} uv run oc paper rehearsal-run ${spec} --allow-paper-orders >> logs/rotation_${name}.log 2>&1 ${marker} submit" \
    >> "${tmp}"
done

printf '%s\n' \
  "12 23 * * 1-5 cd ${ROOT} && ${ENVPREP} && ${CAPPED} uv run python scripts/log_rotation_baselines.py >> logs/rotation_baselines.log 2>&1 # open-composer rotation sleeve baselines" \
  >> "${tmp}"

crontab "${tmp}"
echo "installed rotation sleeve cron entries:"
crontab -l | grep -F "# open-composer rotation sleeve" | sed 's/^/  /'
