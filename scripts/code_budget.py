"""Keep agent-written infrastructure from growing unnoticed.

Default (git pre-commit): fail when the staged Python in open_composer/,
scripts/ or tests/ exceeds config/code-budget.json; lower the budget when
code was deleted. Raise a budget only by editing that file in the commit.

--hook (Codex/Claude Stop hook): once per turn, ask the agent to re-read its
uncommitted diff when it grew the code, added tests or added hash/receipt
logic. Research code under research/ is the product and is not counted.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGET = ROOT / "config/code-budget.json"
AREAS = ("open_composer", "scripts", "tests")
SKIP = "open_composer/paper_runtime/frozen_sources/"
HEADROOM = 300
DEFENSIVE = re.compile(r"hashlib|sha256|fingerprint|receipt|manifest|checksum", re.I)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def area(path: str) -> str | None:
    if not path.endswith(".py") or path.startswith(SKIP):
        return None
    top = path.split("/", 1)[0]
    return top if top in AREAS else None


def staged_totals() -> dict[str, int]:
    totals = dict.fromkeys(AREAS, 0)
    for line in git("grep", "--cached", "-c", "-e", "", "--", *AREAS).splitlines():
        path, _, count = line.rpartition(":")
        if name := area(path):
            totals[name] += int(count)
    return totals


def check_commit() -> int:
    budget = json.loads(BUDGET.read_text(encoding="utf-8"))
    totals = staged_totals()
    over = {k: (v, budget[k]) for k, v in totals.items() if v > budget[k]}
    if over:
        for name, (lines, limit) in over.items():
            print(f"code budget: {name}/ has {lines} lines, budget {limit}.", file=sys.stderr)
        print(
            "Remove code first (defensive checks, fallbacks, tests the change did not need).\n"
            "If the growth is the deliverable, raise config/code-budget.json in this commit "
            "and say why in the commit message.",
            file=sys.stderr,
        )
        return 1
    lowered = {k: min(budget[k], v + HEADROOM) for k, v in totals.items()}
    if lowered != budget:
        BUDGET.write_text(json.dumps(lowered, indent=2) + "\n", encoding="utf-8")
        git("add", str(BUDGET.relative_to(ROOT)))
    return 0


def turn_review() -> int:
    event = json.loads(sys.stdin.read() or "{}")
    if event.get("stop_hook_active"):
        return 0
    added = removed = tests = 0
    for line in git("diff", "HEAD", "--numstat", "--", *AREAS).splitlines():
        plus, minus, path = line.split("\t", 2)
        if area(path) and plus != "-":
            added, removed = added + int(plus), removed + int(minus)
            tests += int(plus) if path.startswith("tests/") else 0
    patch = git("diff", "HEAD", "-U0", "--", *AREAS, ":(exclude)scripts/code_budget.py")
    new_files = git("ls-files", "--others", "--exclude-standard", "--", *AREAS).split()
    for path in filter(area, new_files):
        if path == "scripts/code_budget.py":
            continue
        text = (ROOT / path).read_text(encoding="utf-8", errors="ignore")
        count = text.count("\n")
        added += count
        tests += count if path.startswith("tests/") else 0
        patch += "".join("+" + row + "\n" for row in text.splitlines())
    hits = [row[1:].strip()[:80] for row in patch.splitlines() if row.startswith("+") and DEFENSIVE.search(row)]
    if added - removed <= 80 and tests <= 40 and not hits:
        return 0
    reason = (
        f"Before finishing, re-read your uncommitted diff: open_composer/scripts/tests "
        f"+{added}/-{removed} lines, tests +{tests}."
        + (f" New hash/receipt/manifest lines: {hits[:3]}." if hits else "")
        + " Delete defensive checks, fallbacks, hash/receipt/manifest logic and tests the "
        "request did not need (AGENTS.md, Code). Then finish; for any large addition that "
        "remains, say in one sentence why it is needed."
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(turn_review() if "--hook" in sys.argv else check_commit())
