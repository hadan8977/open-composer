"""Run one finite research round. No schedules or paper operations are installed."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.agent_workflow import (  # noqa: E402
    Reply,
    Results,
    codex_command,
    identifier,
    run_round,
    run_series,
)


def main() -> int:
    def interrupted(signum, _frame):
        raise InterruptedError(f"Runner received signal {signum}; inspect saved job state")

    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("direction")
    run = sub.add_parser("run")
    run.add_argument("direction")
    run.add_argument("--run-id", required=True)
    run.add_argument("--timeout-seconds", required=True, type=float)
    run.add_argument("--review", choices=("reuse", "plan", "result", "both"), default="reuse")
    run.add_argument("--review-plan", action="store_true", help="Also review the plan before work")
    run.add_argument(
        "--review-result", action="store_true", help="Also review the completed result"
    )
    run.add_argument(
        "--follow",
        action="store_true",
        help="Follow concrete authorized briefs across directions within the timeout",
    )
    recover = sub.add_parser("resume", help="Resume saved phases and the original research series")
    recover.add_argument("direction")
    recover.add_argument(
        "--run-id", required=True, help="Original round id, or series id with --follow"
    )
    recover.add_argument("--timeout-seconds", required=True, type=float)
    recover.add_argument(
        "--follow", action="store_true", help="Resume the original series and continue"
    )
    sub.add_parser("preview")
    sub.add_parser("schemas")
    args = parser.parse_args()
    if args.command == "init":
        task = ROOT / "research" / identifier(args.direction)
        task.mkdir(exist_ok=False)
        for name in ("brief.md", "decisions.tsv"):
            (task / name).write_bytes((ROOT / "research/templates" / name).read_bytes())
        print(task.relative_to(ROOT))
    elif args.command == "schemas":
        print(
            json.dumps(
                {"reply": Reply.model_json_schema(), "results": Results.model_json_schema()},
                indent=2,
            )
        )
    elif args.command == "preview":
        config = json.loads((ROOT / "research/workflow.json").read_text())
        print(
            json.dumps(
                {
                    role: codex_command(ROOT, spec, Path("reply.json"), Path("reply.schema.json"))
                    for role, spec in config["roles"].items()
                },
                indent=2,
            )
        )
    else:
        runner = run_series if args.follow else run_round
        result = runner(
            ROOT,
            args.direction,
            args.run_id,
            args.timeout_seconds,
            review_plan=getattr(args, "review_plan", False)
            or getattr(args, "review", "reuse") in ("plan", "both"),
            review_result=getattr(args, "review_result", False)
            or getattr(args, "review", "reuse") in ("result", "both"),
            resume=args.command == "resume",
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
