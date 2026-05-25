#!/usr/bin/env bash
# Deploy Open Composer Dashboard from the target VPS.
#
# Default behavior is apply mode: build the Dashboard, configure auth, install
# the local systemd service, and verify the result. Public access should use
# Cloudflare Tunnel + Access unless you intentionally pass the legacy Caddy
# token mode options.

set -euo pipefail

APPLY=1
SKIP_SYNC=0
ARGS=()

usage() {
  cat <<'EOF'
Usage:
  scripts/deploy-vps.sh [options passed to oc dashboard deploy-vps]

Common options:
  --plan                 Write the VPS bootstrap plan only; do not deploy.
  --skip-sync            Do not run uv sync before bootstrap.
  --sudo                 Use sudo for systemd/Caddy installation.
  --dashboard-url URL    Public HTTPS URL for the Dashboard.
  --public-ip IP         VPS public IPv4; creates https://<ip>.nip.io.
  --cloudflare-access    Use Cloudflare Tunnel + Access; skips Caddy.
  --cloudflare-team-domain URL
                         Cloudflare Access team domain.
  --cloudflare-aud AUD   Cloudflare Access application AUD tag.
  --allowed-emails CSV   Comma-separated Access email allowlist.
  --rotate-token         Generate a new Dashboard API token.
  --no-verify            Skip deployment verification.

Environment:
  OPEN_COMPOSER_DASHBOARD_TOKEN  Optional; generated when missing.
  OC_CLOUDFLARE_ACCESS_TEAM_DOMAIN / OC_CLOUDFLARE_ACCESS_AUD /
  OC_DASHBOARD_ALLOWED_EMAILS       Used with --cloudflare-access.

Examples:
  scripts/deploy-vps.sh --cloudflare-access --dashboard-url https://dashboard.example.com
  scripts/deploy-vps.sh --plan --public-ip 203.0.113.10
  scripts/deploy-vps.sh --sudo --dashboard-url https://dashboard.example.com
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --plan|--dry-run)
      APPLY=0
      shift
      ;;
    --apply)
      APPLY=1
      shift
      ;;
    --skip-sync)
      SKIP_SYNC=1
      shift
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/open-composer-uv-cache}"
export NPM_CONFIG_CACHE="${NPM_CONFIG_CACHE:-/tmp/open-composer-npm-cache}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/." >&2
  exit 1
fi

if [[ $SKIP_SYNC -eq 0 ]]; then
  echo "[1/3] Syncing Python dependencies"
  uv sync
else
  echo "[1/3] Skipping dependency sync"
fi

if [[ $APPLY -eq 1 ]]; then
  echo "[2/3] Running VPS Dashboard deploy in apply mode"
  BOOTSTRAP=(uv run oc dashboard deploy-vps --apply)
else
  echo "[2/3] Writing VPS Dashboard deploy plan"
  BOOTSTRAP=(uv run oc dashboard deploy-vps)
fi

"${BOOTSTRAP[@]}" "${ARGS[@]}"

echo "[3/3] VPS Dashboard deployment command completed"
echo "Review reports/deployment/vps-dashboard/plan.md for the deployment summary."
