#!/bin/bash
# OOM victim order for Claude/Codex agent processes; runs every 30 s from
# claude-orchestrator-protect.timer. Source: deploy/memory/claude-orchestrator-protect.sh.
#
# Owner 2026-10-07: open-composer must yield to the owner's other projects. Until then this
# script gave every open-composer claude -500, so the owner's other sessions (for example
# /root/finance) were earlyoom's first victims. Now, by cgroup:
#   * agents outside oc.slice (other projects, the owner's own conversations): -500
#   * open-composer top-level sessions (oc-interactive.slice):                 -300
#   * open-composer background agents (oc-agents.slice):                          0
# Research jobs give themselves +200 (scripts/run_capped.sh). Memory pressure inside
# oc.slice is handled by the kernel and oc-memory-governor before earlyoom is involved.
for pid in $(pgrep -x 'claude|codex' 2>/dev/null); do
    cg=$(cat "/proc/$pid/cgroup" 2>/dev/null) || continue
    case "$cg" in
        */oc.slice/oc-interactive.slice/*) want=-300 ;;
        */oc.slice/*) want=0 ;;
        *) want=-500 ;;
    esac
    adj_file="/proc/$pid/oom_score_adj"
    [ -w "$adj_file" ] || continue
    [ "$(cat "$adj_file" 2>/dev/null)" = "$want" ] && continue
    if echo "$want" > "$adj_file" 2>/dev/null; then
        logger -t claude-orchestrator-protect "pid=$pid adj=$want cgroup=${cg#0::}"
    fi
done
