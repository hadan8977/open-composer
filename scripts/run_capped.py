"""Run one command in a memory-capped Windows Job Object (Linux uses run_capped.sh).

`run_capped.py [--root R] [--mem 900M] [--wait-min N] -- command ...` waits up to N
minutes for memory headroom (exit 75 if refused), then returns the command's exit
code. `run_capped.py admit --kind agent` exits 2 when a new agent may not start.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.platform_runtime import admission, capped_process  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--mem", default="900M")
    parser.add_argument("--wait-min", type=int, default=0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == ["admit", "--kind", "agent"]:
        state = admission(args.root)
        if state["admitted"]:
            print("admit: ok")
            return 0
        print(
            f"refuse: headroom {state['available_mb']} MB < "
            f"{state['required_mb']} MB for a new agent",
            file=sys.stderr,
        )
        return 2
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Specify a command after --")
    deadline = time.monotonic() + args.wait_min * 60
    while True:
        try:
            process = capped_process(command, root=args.root, mem=args.mem)
            break
        except MemoryError:
            if time.monotonic() >= deadline:
                print("run_capped: memory admission refused", file=sys.stderr)
                return 75
            time.sleep(1)
    with process:
        return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
