#!/usr/bin/env bash
# Install the open-composer memory budget (owner 2026-10-07: always leave the owner
# >=500 MB free). Idempotent; every replaced system file is backed up first to
# /root/backups/memory-budget/<UTC stamp>/. Rules: docs/runbook-memory.zh.md.
#
#   deploy/memory/install.sh            # units, governor, OOM scripts, earlyoom, maintenance
#   deploy/memory/install.sh --paseo    # also point Paseo's claude provider at the wrapper
#                                       # (takes effect when the Paseo daemon restarts)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/root/backups/memory-budget/$STAMP"
mkdir -p "$BACKUP"

backup() { [ -e "$1" ] && cp -a "$1" "$BACKUP/$(echo "$1" | tr / _)" || true; }
put() {  # put SRC DEST MODE
    if [ -e "$2" ] && cmp -s "$1" "$2"; then return 0; fi
    backup "$2"
    install -D -m "$3" "$1" "$2"
    echo "installed $2"
}

for f in "$HERE"/systemd/*.slice "$HERE"/systemd/*.service; do
    put "$f" "/etc/systemd/system/$(basename "$f")" 0644
done
for d in "$HERE"/systemd/*.d; do
    for f in "$d"/*.conf; do
        put "$f" "/etc/systemd/system/$(basename "$d")/$(basename "$f")" 0644
    done
done
put "$HERE/paseo-claude-launch.sh" /usr/local/sbin/paseo-claude-launch 0755
put "$HERE/claude-orchestrator-protect.sh" /usr/local/sbin/claude-orchestrator-protect.sh 0755
put "$HERE/oom-auto-protect.sh" /usr/local/sbin/oom-auto-protect.sh 0755
put "$HERE/paseo_memory_maintenance.py" /root/.paseo/bin/paseo_memory_maintenance.py 0755
earlyoom_changed=0
if ! cmp -s "$HERE/earlyoom.default" /etc/default/earlyoom; then
    put "$HERE/earlyoom.default" /etc/default/earlyoom 0644
    earlyoom_changed=1
fi

systemctl daemon-reload
systemctl start oc.slice oc-interactive.slice oc-agents.slice oc-research.slice \
    oc-research-capped.slice paper-capped.slice
systemctl enable --now oc-memory-governor.service
systemctl restart oc-memory-governor.service
# Owner 2026-10-08 doubled the limits (6 agents, 2.4 GB jobs): compress idle memory in
# RAM (zswap) and add a second 4 GB swap file, so the extra agents fit and swap never
# runs out again (2026-10-08 01:53 "Free swap = 4kB" ended every Paseo session).
systemctl enable --now oc-zswap.service
if ! swapon --show=NAME --noheadings | grep -qx /swapfile2; then
    if [ ! -f /swapfile2 ]; then
        fallocate -l 4G /swapfile2
    fi
    chmod 600 /swapfile2
    mkswap /swapfile2 >/dev/null
    swapon /swapfile2
    echo "swap: /swapfile2 on"
fi
if ! grep -qE '^/swapfile2[[:space:]]' /etc/fstab; then
    backup /etc/fstab
    echo '/swapfile2 swap swap defaults 0 0' >> /etc/fstab
    echo "fstab: /swapfile2 added"
fi
# The cockpit moves into oc.slice only on restart (read-only service, safe to restart).
pid="$(systemctl show quant.service -p MainPID --value)"
if [ "${pid:-0}" != 0 ] && ! grep -q '/oc\.slice/' "/proc/$pid/cgroup" 2>/dev/null; then
    systemctl restart quant.service
fi
[ "$earlyoom_changed" = 1 ] && systemctl restart earlyoom.service

if [ "${1:-}" = "--paseo" ]; then
    cfg=/root/.paseo/config.json
    backup "$cfg"
    python3 - "$cfg" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
claude = data.setdefault("agents", {}).setdefault("providers", {}).setdefault("claude", {})
want = {"mode": "replace", "argv": ["/usr/local/sbin/paseo-claude-launch"]}
if claude.get("command") != want:
    claude["command"] = want
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    import os
    os.chmod(tmp, os.stat(path).st_mode)
    os.replace(tmp, path)
    print("paseo: claude provider now launches through /usr/local/sbin/paseo-claude-launch")
else:
    print("paseo: already configured")
PY
fi
echo "backups (if any): $BACKUP"
