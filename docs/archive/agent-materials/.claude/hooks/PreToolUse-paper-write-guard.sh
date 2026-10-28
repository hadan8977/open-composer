#!/usr/bin/env bash
# PreToolUse hook: block broker writes unless the current harness verify passed.
# Reads stdin JSON: {"tool_name": "...", "tool_input": {...}}.

set -euo pipefail

python3 - <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

data = json.load(sys.stdin)
tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {})

if tool_name != "Bash":
    sys.exit(0)

command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
lower = command.lower()

paper_patterns = [
    "alpaca",
    "submit_order",
    "place_order",
    "paper_auto",
    "oc paper",
    "broker_submit",
]

if not any(pattern in lower for pattern in paper_patterns):
    sys.exit(0)

root = Path(os.environ.get("OC_ROOT", "."))
name_match = re.search(
    r"strategy_specs/(?:drafts|active|approved|retired)/([a-z0-9_-]+)\.ya?ml",
    command,
    re.IGNORECASE,
) or re.search(r"\boc\s+paper\s+(?:submit|run)\s+([a-z0-9_-]+)", command, re.IGNORECASE)

if not name_match:
    print(
        "[paper-write-guard] WARNING: detected possible paper order submission but could not "
        "identify strategy name. Ensure `oc harness verify <spec>` has been run.",
        file=sys.stderr,
    )
    sys.exit(0)

strategy_name = name_match.group(1)
verify_report = root / "reports" / "harness" / "verify" / f"{strategy_name}.json"
if not verify_report.exists():
    print(
        f"[paper-write-guard] BLOCKED: no harness verify report for '{strategy_name}'.\n"
        f"Run `oc harness verify strategy_specs/active/{strategy_name}.yaml` first.",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    report = json.loads(verify_report.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"[paper-write-guard] WARNING: could not parse verify report: {exc}", file=sys.stderr)
    sys.exit(0)

status = report.get("overall") or report.get("status", "unknown")
if status not in ("ok", "warning"):
    print(
        f"[paper-write-guard] BLOCKED: harness verify status is '{status}' for "
        f"'{strategy_name}'. Resolve blocking findings before paper submission.",
        file=sys.stderr,
    )
    sys.exit(1)

sys.exit(0)
PYEOF
