#!/usr/bin/env bash
# UserPromptSubmit hook: inject compact harness + research-control context.
# Emits Claude's documented additionalContext envelope, including Chinese prompts.

set -euo pipefail

payload="$(cat)"
OC_HOOK_PAYLOAD="$payload" python3 - <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

data = json.loads(os.environ.get("OC_HOOK_PAYLOAD") or "{}")
prompt = data.get("prompt", "")

KEYWORDS = re.compile(
    r"strategy|strategy_specs|spec|backtest|research|parameter[- ]sweep|"
    r"execution.policy|source.card|harness.verify|paper.auto|promotion|"
    r"策略|盈利|研究|回测|训练|优化|迭代|自主|循环|方向|任务|继续|进展",
    re.IGNORECASE,
)

if not KEYWORDS.search(prompt):
    sys.exit(0)

root = Path(os.environ.get("OC_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR") or ".")


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


context_lines: list[str] = [
    "Shared mission: read docs/research-mission.zh.md and the latest dated section "
    "of docs/current-view.zh.md. Prioritize credible near-term profit after costs; "
    "regime-specific opportunities are valid. Search the web and open primary sources "
    "FIRST; reuse existing implementations and negative experiments before compute. "
    "Routine research is delegated; do not stall on superseded per-card approvals. "
    "New background budgets and broker authorizations require explicit scope. "
    "New v3 iterations require direction-review.json, oc research direction-check, "
    "and oc research iteration validate. Do not relax frozen gates."
]
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

print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "\n".join(context_lines),
}}, ensure_ascii=False))
PYEOF
