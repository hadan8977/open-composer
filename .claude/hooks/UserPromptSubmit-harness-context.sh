#!/usr/bin/env bash
# UserPromptSubmit hook — inject harness context when a strategy task is detected.
# Reads the incoming prompt from stdin (JSON: {"prompt": "..."}) and appends
# a brief reminder about the harness artifact contract when strategy-relevant
# keywords are detected. Does NOT run backtests or shell-heavy work.

set -euo pipefail

python3 - <<'PYEOF'
import sys
import json
import re
import os
from pathlib import Path

data = json.load(sys.stdin)
prompt = data.get("prompt", "")

KEYWORDS = re.compile(
    r"strategy|spec|backtest|execution.policy|source.card|harness.verify|paper.auto|promotion",
    re.IGNORECASE,
)

if not KEYWORDS.search(prompt):
    print(json.dumps(data))
    sys.exit(0)

root = Path(os.environ.get("OC_ROOT", "."))

# Best-effort: extract a strategy name from the prompt
name_match = re.search(r"\bstrategies/([a-z0-9_-]+)/", prompt) or re.search(
    r"strategy[/ ]([a-z0-9_-]+)", prompt, re.IGNORECASE
)
context_lines = []

if name_match:
    strategy_name = name_match.group(1)
    verify_report = root / "reports" / "harness" / f"{strategy_name}-harness-verify.json"
    if verify_report.exists():
        try:
            report = json.loads(verify_report.read_text())
            status = report.get("status", "unknown")
            context_lines.append(f"Last harness verify for '{strategy_name}': {status}.")
        except Exception:
            pass
    else:
        context_lines.append(
            f"No harness verify report for '{strategy_name}' — run: oc harness verify {strategy_name}"
        )

if not context_lines:
    context_lines.append(
        "Reminder: run 'oc harness verify <strategy>' before promotion or paper submission."
    )

injection = "\n--- Harness context (injected by hook) ---\n" + "\n".join(context_lines) + "\n---"
data["prompt"] = prompt + injection
print(json.dumps(data))
PYEOF
