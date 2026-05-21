#!/usr/bin/env bash
# PreToolUse hook — block broker write calls unless harness verify is current.
# Triggered before any tool execution. Reads tool name + input from stdin as
# JSON: {"tool_name": "...", "tool_input": {...}}.
# Exits 0 to allow, non-zero to block.

set -euo pipefail

python3 - <<'PYEOF'
import sys
import json
import os
from pathlib import Path

data = json.load(sys.stdin)
tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {})

# Only inspect Bash tool calls that look like paper order submission
if tool_name != "Bash":
    sys.exit(0)

command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""

PAPER_PATTERNS = [
    "alpaca",
    "submit_order",
    "place_order",
    "paper_auto",
    "oc paper",
    "broker_submit",
]

if not any(p in command.lower() for p in PAPER_PATTERNS):
    sys.exit(0)

# Looks like a paper order write — require harness verify artifact
root = Path(os.environ.get("OC_ROOT", "."))

# Try to extract a strategy name from the command
import re
name_match = re.search(r"strategies/([a-z0-9_-]+)/", command) or re.search(
    r"\b(oc\s+paper\s+(?:submit|run)\s+)([a-z0-9_-]+)", command
)

if name_match:
    strategy_name = name_match.group(name_match.lastindex or 1)
    verify_report = root / "reports" / "harness" / f"{strategy_name}-harness-verify.json"
    if not verify_report.exists():
        print(
            f"[paper-write-guard] BLOCKED: no harness verify report for '{strategy_name}'.\n"
            f"Run 'oc harness verify {strategy_name}' first.",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        report = json.loads(verify_report.read_text())
        status = report.get("status", "unknown")
        if status not in ("ok", "warning"):
            print(
                f"[paper-write-guard] BLOCKED: harness verify status is '{status}' for '{strategy_name}'.\n"
                "Resolve all blocking findings before paper submission.",
                file=sys.stderr,
            )
            sys.exit(1)
    except Exception as exc:
        print(f"[paper-write-guard] WARNING: could not parse verify report: {exc}", file=sys.stderr)
        # Don't block on parse error — just warn
        sys.exit(0)
else:
    # Could not identify strategy — warn but don't hard-block
    print(
        "[paper-write-guard] WARNING: detected possible paper order submission but could not "
        "identify strategy name. Ensure 'oc harness verify <strategy>' has been run.",
        file=sys.stderr,
    )

sys.exit(0)
PYEOF
