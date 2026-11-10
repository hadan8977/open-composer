"""Report recorded input bindings that no longer verify at their stated path.

Every paper/science receipt binds a file by ``{path, bytes, sha256}``. The
integrity checks resolve the path before hashing, so a file that an ops cleanup
moved to an archive mount and replaced with a symlink fails the binding even
when the bytes are identical -- which is exactly what blocked the H5 paper
target on 2026-11-05..2026-11-09 after ``disk-half-recovery-20261103``.

Read-only: this walks JSON receipts, re-hashes the bound paths and prints what
does not verify. It never writes, fetches or publishes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

DEFAULT_ROOTS = (
    "reports/research/program/owner-profit-delivery-plan-20261017",
    "reports/research/program/paper-launch-20min-20261021",
    "reports/research/program/dlsa-real-market-continuation-20261014",
    "reports/research/program/return-line-replenishment-20261016",
    "reports/paper",
    "runtime/paper",
)
MAX_JSON_BYTES = 8_388_608


def bindings(node, repo: Path, out: list[dict]) -> None:
    if isinstance(node, dict):
        path = node.get("path")
        if (
            isinstance(path, str)
            and path.startswith(str(repo))
            and isinstance(node.get("sha256"), str)
            and isinstance(node.get("bytes"), int)
        ):
            out.append(node)
        for value in node.values():
            bindings(value, repo, out)
    elif isinstance(node, list):
        for value in node:
            bindings(value, repo, out)


def scan(root: Path, roots: tuple[str, ...]) -> tuple[list[dict], int, int]:
    seen: dict[str, dict] = {}
    receipts = 0
    repo = root.resolve()
    for relative in roots:
        base = root / relative
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in {"__pycache__"}]
            for name in filenames:
                if not name.endswith(".json"):
                    continue
                path = Path(dirpath) / name
                try:
                    if path.stat().st_size > MAX_JSON_BYTES:
                        continue
                    node = json.loads(path.read_text())
                except (OSError, ValueError, UnicodeDecodeError):
                    continue
                receipts += 1
                found: list[dict] = []
                bindings(node, repo, found)
                for row in found:
                    seen.setdefault(row["path"], row)
    problems = []
    for path, row in seen.items():
        target = Path(path)
        if not target.exists():
            problems.append(dict(binding=row, problem="missing"))
            continue
        link = os.readlink(target) if target.is_symlink() else None
        try:
            raw = target.read_bytes()
        except OSError as exc:
            problems.append(dict(binding=row, problem=f"unreadable: {exc}"))
            continue
        if link is not None:
            problems.append(dict(binding=row, problem="symlink", target=link))
        elif len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            problems.append(dict(binding=row, problem="content changed"))
    return problems, len(seen), receipts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    problems, bindings_seen, receipts = scan(args.root.resolve(), DEFAULT_ROOTS)
    summary = dict(
        receipts_read=receipts,
        bound_paths=bindings_seen,
        problems=len(problems),
        symlink=sum(1 for p in problems if p["problem"] == "symlink"),
        missing=sum(1 for p in problems if p["problem"] == "missing"),
        changed=sum(1 for p in problems if p["problem"].startswith("content")),
    )
    print(json.dumps(summary, indent=1))
    for row in problems[: args.limit]:
        print(f"- {row['problem']:14s} {row['binding']['path']}")
        if row.get("target"):
            print(f"    -> {row['target']}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(dict(summary=summary, problems=problems), indent=1) + "\n")
        print(f"written {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
