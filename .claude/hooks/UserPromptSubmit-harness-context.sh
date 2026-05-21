#!/usr/bin/env bash
# UserPromptSubmit hook: inject compact harness + research-control context.
# Reads stdin JSON: {"prompt": "..."} and appends a short memory packet when
# strategy-relevant keywords are detected. It never runs backtests or shell-heavy work.

set -euo pipefail

python3 - <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

data = json.load(sys.stdin)
prompt = data.get("prompt", "")

KEYWORDS = re.compile(
    r"strategy|strategy_specs|spec|backtest|research|parameter[- ]sweep|"
    r"execution.policy|source.card|harness.verify|paper.auto|promotion",
    re.IGNORECASE,
)

if not KEYWORDS.search(prompt):
    print(json.dumps(data, ensure_ascii=False))
    sys.exit(0)

root = Path(os.environ.get("OC_ROOT", "."))


def strategy_names_from_prompt(text: str) -> list[str]:
    patterns = [
        r"strategy_specs/(?:drafts|active|approved|retired)/([a-z0-9_-]+)\.ya?ml",
        r"reports/research/control/([a-z0-9_-]+)-memory\.md",
        r"\bstrategy[/ ]([a-z0-9_-]+)",
    ]
    names: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            name = match.group(1)
            if name not in names:
                names.append(name)
    return names[:2]


def read_text(path: Path, max_chars: int = 1200) -> str | None:
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    return text[:max_chars] if text else None


context_lines: list[str] = []
names = strategy_names_from_prompt(prompt)

for strategy_name in names:
    memory_path = root / "reports" / "research" / "control" / f"{strategy_name}-memory.md"
    memory = read_text(memory_path)
    if memory:
        context_lines.append(f"Research memory for '{strategy_name}':\n{memory}")

    verify_report = root / "reports" / "harness" / "verify" / f"{strategy_name}.json"
    if verify_report.exists():
        try:
            report = json.loads(verify_report.read_text(encoding="utf-8"))
            status = report.get("overall") or report.get("status", "unknown")
            context_lines.append(f"Last harness verify for '{strategy_name}': {status}.")
        except Exception:
            pass
    else:
        context_lines.append(
            f"No harness verify report for '{strategy_name}'. Run: oc harness verify "
            f"strategy_specs/drafts/{strategy_name}.yaml"
        )

if not context_lines:
    context_lines.append(
        "Research control reminder: before strategy generation or optimization, run "
        "`oc strategy research-control <spec>` after research-report or parameter-sweep, "
        "then use the memory packet to avoid repeated failed paths."
    )

injection = "\n--- Open Composer research control (injected) ---\n"
injection += "\n".join(context_lines)
injection += "\n---"
data["prompt"] = prompt + injection
print(json.dumps(data, ensure_ascii=False))
PYEOF
