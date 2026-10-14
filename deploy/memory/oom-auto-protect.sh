#!/bin/bash
# Auto-protect large, sustained processes from earlyoom / the kernel OOM killer
# by giving them a negative oom_score_adj directly (bypasses earlyoom's
# name-based --avoid/--prefer regex, which can't tell apart generic names
# like "python3"). Protection is per-PID and expires automatically when the
# process exits — nothing to clean up, no config to grow over time.
#
# Anything that stays above THRESHOLD_KB RSS for MIN_UPTIME_S seconds gets
# protected, except EXCLUDE_REGEX (the paseo chat agent processes, which are
# meant to be earlyoom's sacrificial pool via --prefer).

THRESHOLD_KB=409600
MIN_UPTIME_S=120
PROTECT_SCORE=-500
EXCLUDE_REGEX='^(claude|codex|node)$'

ps -eo pid=,rss=,etimes=,comm= 2>/dev/null | while read -r pid rss etimes comm; do
    [[ "$comm" =~ $EXCLUDE_REGEX ]] && continue
    [ -n "$rss" ] && [ "$rss" -ge "$THRESHOLD_KB" ] || continue
    [ -n "$etimes" ] && [ "$etimes" -ge "$MIN_UPTIME_S" ] || continue

    # Never protect a job that is already running under an explicit cgroup
    # memory cap (scripts/run_capped.sh puts those in research-capped.slice).
    # Such jobs are checkpointed and meant to be the victim: protecting them
    # is what let a 2914 MiB research job outrank the Claude Code orchestrator
    # on 2026-09-07 and get the orchestrator killed instead. Added 2026-09-08.
    grep -q 'research-capped' "/proc/$pid/cgroup" 2>/dev/null && continue

    # Nor anything inside the open-composer memory budget (oc.slice: agents, their
    # pytest/modal/scripts, the cockpit). The kernel and oc-memory-governor manage
    # pressure there; a -500 would make the project outrank the owner's other work
    # (owner 2026-10-07). Source: deploy/memory/oom-auto-protect.sh.
    grep -q '/oc\.slice/' "/proc/$pid/cgroup" 2>/dev/null && continue

    adj_file="/proc/$pid/oom_score_adj"
    [ -w "$adj_file" ] || continue
    current=$(cat "$adj_file" 2>/dev/null)
    [ "$current" = "$PROTECT_SCORE" ] && continue

    if echo "$PROTECT_SCORE" > "$adj_file" 2>/dev/null; then
        logger -t oom-auto-protect "protected pid=$pid comm=$comm rss=${rss}KB uptime=${etimes}s"
    fi
done
