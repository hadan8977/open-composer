#!/usr/bin/env bash
# Stop the Open Composer Remote Dashboard on a VPS.

set -euo pipefail

SERVICE_NAME="open-composer-remote.service"
CADDY_SERVICE="caddy.service"
CADDYFILE="/etc/caddy/Caddyfile"
CADDY_DISABLED_BACKUP="/etc/caddy/Caddyfile.open-composer-disabled"
USE_SUDO=0
REMOVE_SYSTEMD=0
DISABLE_CADDY=0
REMOVE_CADDYFILE=0
FORCE_CADDY=0

usage() {
  cat <<'EOF'
Usage:
  scripts/stop-remote-dashboard.sh [options]

Options:
  --sudo              Run system and file operations through sudo.
  --remove-systemd    Remove /etc/systemd/system/open-composer-remote.service.
  --disable-caddy     Stop and disable caddy.service after safety checks.
  --remove-caddyfile  Move /etc/caddy/Caddyfile to a disabled backup after safety checks.
  --force-caddy       Skip the Open Composer Caddyfile safety check.

Examples:
  scripts/stop-remote-dashboard.sh
  scripts/stop-remote-dashboard.sh --remove-systemd --disable-caddy --remove-caddyfile
  scripts/stop-remote-dashboard.sh --sudo --remove-systemd --disable-caddy
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --sudo)
      USE_SUDO=1
      shift
      ;;
    --remove-systemd)
      REMOVE_SYSTEMD=1
      shift
      ;;
    --disable-caddy)
      DISABLE_CADDY=1
      shift
      ;;
    --remove-caddyfile)
      REMOVE_CADDYFILE=1
      shift
      ;;
    --force-caddy)
      FORCE_CADDY=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

run_system() {
  if [[ $USE_SUDO -eq 1 ]]; then
    sudo "$@"
  else
    "$@"
  fi
}

service_exists() {
  systemctl cat "$1" >/dev/null 2>&1
}

caddyfile_is_open_composer() {
  [[ -f "$CADDYFILE" ]] && grep -q "reverse_proxy 127.0.0.1:8787" "$CADDYFILE"
}

echo "[1/4] Stopping remote daemon"
if service_exists "$SERVICE_NAME"; then
  run_system systemctl disable --now "$SERVICE_NAME"
else
  echo "service not found: $SERVICE_NAME"
fi

echo "[2/4] Cleaning systemd unit"
if [[ $REMOVE_SYSTEMD -eq 1 ]]; then
  if [[ $USE_SUDO -eq 1 ]]; then
    sudo rm -f "/etc/systemd/system/$SERVICE_NAME"
  else
    rm -f "/etc/systemd/system/$SERVICE_NAME"
  fi
  run_system systemctl daemon-reload
else
  echo "systemd unit left in place; pass --remove-systemd to delete it"
fi

echo "[3/4] Handling Caddy"
if [[ $DISABLE_CADDY -eq 1 || $REMOVE_CADDYFILE -eq 1 ]]; then
  if [[ $FORCE_CADDY -eq 0 ]] && ! caddyfile_is_open_composer; then
    echo "Caddyfile does not look like an Open Composer-only proxy; skipping Caddy changes."
    echo "Pass --force-caddy only after confirming Caddy is not serving anything else."
  else
    if [[ $DISABLE_CADDY -eq 1 ]]; then
      run_system systemctl disable --now "$CADDY_SERVICE"
    fi
    if [[ $REMOVE_CADDYFILE -eq 1 && -f "$CADDYFILE" ]]; then
      if [[ $USE_SUDO -eq 1 ]]; then
        sudo mv "$CADDYFILE" "$CADDY_DISABLED_BACKUP"
      else
        mv "$CADDYFILE" "$CADDY_DISABLED_BACKUP"
      fi
      echo "moved $CADDYFILE to $CADDY_DISABLED_BACKUP"
    fi
  fi
else
  echo "Caddy left unchanged; pass --disable-caddy if it only serves Open Composer."
fi

echo "[4/4] Current state"
systemctl is-active "$SERVICE_NAME" "$CADDY_SERVICE" || true
if command -v ss >/dev/null 2>&1; then
  ss -tlnp | grep -E ':(8787|8443|80)\b' || true
fi
