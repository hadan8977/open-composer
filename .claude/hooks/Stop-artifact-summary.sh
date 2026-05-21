#!/usr/bin/env bash
# Stop hook: summarize harness and compact research-control status.
# Reads stdin JSON and emits a human-readable session-end summary.

set -euo pipefail

python3 - <<'PYEOF'
import json
import os
from datetime import date
from pathlib import Path

_ = json.load(open(0))

root = Path(os.environ.get("OC_ROOT", "."))
spec_root = root / "strategy_specs"

if not spec_root.is_dir():
    raise SystemExit(0)

issues: list[str] = []
memories: list[str] = []

for spec_path in sorted(spec_root.glob("*/*.yaml")):
    strategy_name = spec_path.stem
    verify_report = root / "reports" / "harness" / "verify" / f"{strategy_name}.json"
    if verify_report.exists():
        try:
            report = json.loads(verify_report.read_text(encoding="utf-8"))
        except Exception:
            report = {}
        status = report.get("overall") or report.get("status", "unknown")
        artifacts = report.get("artifacts", [])
        if status == "blocked":
            blocked = [
                item.get("name", "?")
                for item in artifacts
                if not item.get("present") or not item.get("schema_ok")
            ]
            issues.append(f"  BLOCKED  {strategy_name}: artifacts={blocked}")
        elif status == "warning":
            issues.append(f"  WARNING  {strategy_name}: harness verify warning")

    memory_path = root / "reports" / "research" / "control" / f"{strategy_name}-memory.md"
    if memory_path.exists():
        memories.append(f"  MEMORY   {strategy_name}: {memory_path.as_posix()}")

source_cards_dir = root / "reports" / "harness" / "source_cards"
stale_cards: list[str] = []
if source_cards_dir.is_dir():
    for jsonl in source_cards_dir.glob("*.jsonl"):
        try:
            lines = jsonl.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in lines:
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

if issues or stale_cards or memories:
    print("\n=== Open Composer research/harness summary ===")
    if issues:
        print("Harness verify findings:")
        for issue in issues:
            print(issue)
    if memories:
        print("\nResearch control memory:")
        for memory in memories[:10]:
            print(memory)
    if stale_cards:
        print(f"\nStale source cards ({len(stale_cards)}):")
        for card in stale_cards[:10]:
            print(f"  {card}")
        if len(stale_cards) > 10:
            print(f"  ... and {len(stale_cards) - 10} more. Run: oc harness curate")
    print("==============================================\n")
PYEOF
