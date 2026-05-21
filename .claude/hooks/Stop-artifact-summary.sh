#!/usr/bin/env bash
# Stop hook — summarize harness artifact status and warn on missing required
# artifacts when a Claude Code session ends.
# Reads stdin JSON: {"stop_hook_active": true, ...}
# Outputs a human-readable summary to stdout.

set -euo pipefail

python3 - <<'PYEOF'
import sys
import json
import os
from pathlib import Path

data = json.load(sys.stdin)

root = Path(os.environ.get("OC_ROOT", "."))
strategies_dir = root / "strategies"

if not strategies_dir.is_dir():
    sys.exit(0)

issues = []

for spec_path in sorted(strategies_dir.glob("*/*.yaml")):
    strategy_name = spec_path.stem
    if strategy_name != spec_path.parent.name:
        continue

    verify_report = root / "reports" / "harness" / f"{strategy_name}-harness-verify.json"
    if not verify_report.exists():
        continue

    try:
        report = json.loads(verify_report.read_text())
    except Exception:
        continue

    status = report.get("status", "unknown")
    if status == "blocked":
        blocked_gates = [
            g["name"] for g in report.get("gates", []) if g.get("status") == "blocked"
        ]
        issues.append(f"  BLOCKED  {strategy_name}: gates={blocked_gates}")
    elif status == "warning":
        warn_gates = [
            g["name"] for g in report.get("gates", []) if g.get("status") == "warning"
        ]
        issues.append(f"  WARNING  {strategy_name}: gates={warn_gates}")

# Source card staleness check
from datetime import date
source_cards_dir = root / "reports" / "harness" / "source_cards"
stale_cards = []
if source_cards_dir.is_dir():
    for jsonl in source_cards_dir.glob("*.jsonl"):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                card = json.loads(line)
                accessed = card.get("accessed_at", "")
                if accessed:
                    age = (date.today() - date.fromisoformat(accessed)).days
                    if age > 60:
                        stale_cards.append(f"{jsonl.stem}:{card.get('claim_id','?')} ({age}d)")
            except Exception:
                pass

if issues or stale_cards:
    print("\n=== Harness artifact summary (session end) ===")
    if issues:
        print("Harness verify findings:")
        for issue in issues:
            print(issue)
    if stale_cards:
        print(f"\nStale source cards ({len(stale_cards)}):")
        for card in stale_cards[:10]:
            print(f"  {card}")
        if len(stale_cards) > 10:
            print(f"  ... and {len(stale_cards) - 10} more. Run: oc harness curate")
    print("==============================================\n")

sys.exit(0)
PYEOF
