#!/bin/bash
# Paseo starts every Claude agent through this wrapper
# (agents.providers.claude.command in /root/.paseo/config.json).
#
# Owner 2026-10-07: open-composer must always leave the owner >=500 MB free. Agents whose
# working directory is the open-composer repo are started inside its memory budget
# (oc.slice): top-level sessions in oc-interactive.slice, scheduled rounds and child
# agents in oc-agents.slice, which refuses a 4th live background agent. Agents of every
# other project start exactly as before. Any failure of the budget check falls back to a
# plain launch: this wrapper must never stop Paseo from starting an agent.
#
# Installed to /usr/local/sbin/paseo-claude-launch by deploy/memory/install.sh;
# rules in docs/runbook-memory.zh.md.
CLAUDE_BIN=/root/.hermes/node/bin/claude
OC_ROOT=/root/codex-test/open-composer

cwd=$(pwd -P 2>/dev/null)
case "$cwd/" in
    "$OC_ROOT"/*) ;;
    *) exec "$CLAUDE_BIN" "$@" ;;
esac
[ -n "$PASEO_AGENT_ID" ] || exec "$CLAUDE_BIN" "$@"

decision=$(timeout 10 /usr/bin/python3 "$OC_ROOT/scripts/memory_budget.py" launch-decision 2>/dev/null) \
    || decision=plain
case "$decision" in
    refuse:*)
        echo "open-composer memory budget: ${decision#refuse:} (docs/runbook-memory.zh.md)" >&2
        logger -t paseo-claude-launch "refused agent=$PASEO_AGENT_ID: ${decision#refuse:}"
        exit 75
        ;;
    oc-agents.slice | oc-interactive.slice)
        # --scope execs the command in place: same PID, same stdio, same environment.
        # BindsTo keeps the old behaviour of agents stopping with the Paseo daemon.
        exec systemd-run --scope --quiet --collect --slice="$decision" \
            --unit="oc-agent-${PASEO_AGENT_ID:0:8}-$$" \
            -p BindsTo=paseo-daemon.service -p After=paseo-daemon.service \
            -- "$CLAUDE_BIN" "$@"
        ;;
    *) exec "$CLAUDE_BIN" "$@" ;;
esac
