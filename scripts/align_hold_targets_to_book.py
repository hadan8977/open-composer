"""Align each paper book's instruction action with the book it is meant to hold.

``six_paper_service.operate`` skips any book whose instruction says
``portfolio_action: "hold"``. That flag is derived from target-vs-previous-target
equality, not from the book, so a rebalance that never executed stays "hold"
forever and the book never converges. On 2026-11-10 that left BASE on its
October roster, H5 (and both H5 children) flat, and the two composite parents
untouched.

This walks the live targets, resolves the instruction that actually governs each
book (the parent's ``children`` entry for composites), compares it with the
book's real lots at the target's own reference marks, and flips only the books
that are materially off target. Backups and a before/after receipt are written
beside the targets; no order, capital or stop changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHILDREN = ("S1", "S2", "S3", "C2", "BASE", "H5")
CHILD_CAPITAL = {
    "MULTI_EQUAL": dict(zip(CHILDREN, (3333.34, 3333.34, 3333.33, 3333.33, 3333.33, 3333.33), strict=True)),
    "MULTI_HIERARCHICAL": dict(zip(CHILDREN, (1666.67, 1666.67, 1666.66, 5000.0, 5000.0, 5000.0), strict=True)),
}
PARENTS = tuple(CHILD_CAPITAL)
POLICY_CAPITAL = 20000.0
TOLERANCE = 0.02


def digest(path: Path) -> dict:
    raw = path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str) + "\n")
    os.replace(tmp, path)


def lots(state: dict, book: str) -> dict[str, float]:
    rows = state["books"][book]["cashbook"]["lots"]
    return {
        symbol: sum(float(lot["quantity"]) for lot in items)
        for symbol, items in rows.items()
        if sum(float(lot["quantity"]) for lot in items)
    }


def books_of(policy: str, target: dict) -> list[tuple[str, dict, float]]:
    """(book id, the instruction governing it, that book's capital)."""
    if policy in PARENTS:
        by_name = {row["name"]: row for row in target["children"]}
        return [(f"{policy}/{name}", by_name[name], CHILD_CAPITAL[policy][name]) for name in CHILDREN]
    return [(policy, target, POLICY_CAPITAL)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    targets_dir = root / "runtime/paper/six/targets"
    state = json.loads((root / "runtime/paper/six/runtime-state.json").read_text())
    bedroom = root / "reports/paper/diagnostics/target-action-alignment-20261110"
    backup = bedroom / "predecessor-targets"
    now = datetime.now(UTC).isoformat()
    receipt = dict(schema_version=1, at_utc=now, books=[], changed_targets=[])
    for path in sorted(targets_dir.glob("*.json")):
        policy = path.stem
        target = json.loads(path.read_text())
        marks = target.get("reference_marks") or {}
        dirty = False
        for book, instruction, capital in books_of(policy, target):
            held = lots(state, book)
            weights = dict(zip(instruction.get("symbols") or [], instruction.get("weights") or []))
            gaps = {}
            for symbol in set(weights) | set(held):
                want = float(weights.get(symbol, 0.0)) * capital
                have = held.get(symbol, 0.0) * float(marks.get(symbol, 0.0))
                if abs(want - have) > max(TOLERANCE * capital, 1.0):
                    gaps[symbol] = dict(want=round(want, 2), have=round(have, 2))
            action = instruction.get("portfolio_action")
            after = action
            if gaps and action == "hold":
                instruction["portfolio_action"] = "rebalance"
                after = "rebalance"
                dirty = True
            receipt["books"].append(
                dict(book=book, capital=capital, action_before=action, action_after=after,
                     off_target=sorted(gaps), gaps=gaps)
            )
            print(
                f"{book:26s} action {str(action):9s} -> {after:9s} capital={capital:9.2f} "
                f"off={len(gaps):2d}"
            )
        if dirty:
            if args.execute:
                backup.mkdir(parents=True, exist_ok=True)
                before = digest(path)
                if not (backup / path.name).exists():
                    (backup / path.name).write_bytes(path.read_bytes())
                target["action_alignment"] = dict(
                    at_utc=now,
                    reason=(
                        "book materially off target while the instruction said hold; operate() "
                        "would skip the rebalance the target already implies"
                    ),
                )
                atomic_write(path, target)
                receipt["changed_targets"].append(
                    dict(policy=policy, before=before, after=digest(path))
                )
                print(f"  wrote {path}")
            else:
                print(f"  would write {path}")
    if args.execute and receipt["changed_targets"]:
        bedroom.mkdir(parents=True, exist_ok=True)
        atomic_write(bedroom / "receipt.json", receipt)
        print(f"receipt: {bedroom / 'receipt.json'}")
    elif not args.execute:
        print("dry run; pass --execute to write")
    else:
        print("nothing to change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
