#!/usr/bin/env bash
# Deploy Open Composer Remote Dashboard from the target VPS.
#
# Default behavior is apply mode: configure local remote daemon secrets, install
# systemd/Caddy templates, deploy the Vercel BFF, verify the result, and print
# the Dashboard URL plus password file path.

set -euo pipefail

APPLY=1
SKIP_SYNC=0
SKIP_VERCEL=0
TOKEN_OPTION=0
ARGS=()

usage() {
  cat <<'EOF'
Usage:
  scripts/deploy-vps.sh [options passed to oc remote bootstrap-vps]

Common options:
  --plan                 Write the VPS bootstrap plan only; do not deploy.
  --skip-sync            Do not run uv sync before bootstrap.
  --sudo                 Use sudo for systemd/Caddy installation.
  --daemon-url URL       Public HTTPS URL for the daemon.
  --vercel-project NAME  Vercel project name. Defaults to open-composer-dashboard.
  --rotate-secrets       Generate new remote/session secrets and password hash.
  --skip-vercel          Configure only the VPS daemon side.
  --no-verify            Skip deployment verification.

Environment:
  VERCEL_TOKEN           Required for apply mode unless --skip-vercel is used.

Examples:
  VERCEL_TOKEN=... scripts/deploy-vps.sh
  VERCEL_TOKEN=... scripts/deploy-vps.sh --sudo
  scripts/deploy-vps.sh --plan --public-ip 203.0.113.10
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
    --skip-vercel)
      SKIP_VERCEL=1
      ARGS+=("$1")
      shift
      ;;
    --vercel-token)
      TOKEN_OPTION=1
      ARGS+=("$1")
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --vercel-token" >&2
        exit 2
      fi
      ARGS+=("$2")
      shift 2
      ;;
    --vercel-token=*)
      TOKEN_OPTION=1
      ARGS+=("$1")
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

if [[ $APPLY -eq 1 && $SKIP_VERCEL -eq 0 && $TOKEN_OPTION -eq 0 && -z "${VERCEL_TOKEN:-}" ]]; then
  echo "VERCEL_TOKEN is required for VPS apply mode. Export it or pass --skip-vercel." >&2
  exit 2
fi

if [[ $SKIP_SYNC -eq 0 ]]; then
  echo "[1/3] Syncing Python dependencies"
  uv sync
else
  echo "[1/3] Skipping dependency sync"
fi

if [[ $APPLY -eq 1 ]]; then
  echo "[2/3] Running VPS bootstrap in apply mode"
  BOOTSTRAP=(uv run oc remote bootstrap-vps --apply)
else
  echo "[2/3] Writing VPS bootstrap plan"
  BOOTSTRAP=(uv run oc remote bootstrap-vps)
fi

"${BOOTSTRAP[@]}" "${ARGS[@]}"

echo "[3/3] Remote deployment command completed"
echo "Review reports/deployment/vps-bootstrap/plan.md for the deployment summary."
