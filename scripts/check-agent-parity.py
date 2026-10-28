"""Validate shared instructions, Claude permissions and all mirrored skill resources."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.repo_check import agent_parity_problems  # noqa: E402


def main() -> int:
    problems = agent_parity_problems(ROOT)
    if problems:
        for name, detail in problems.items():
            print(f"agent-parity: {name}: {json.dumps(detail, ensure_ascii=False)}")
        return 1
    print("agent-parity: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
