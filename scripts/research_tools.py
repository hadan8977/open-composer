"""Provider-neutral local research tools. No model calls, services or credentials."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.event_wait import checkpoint_status, wait_event  # noqa: E402
from open_composer.research.knowledge_tools import (  # noqa: E402
    Knowledge,
    KnowledgeSchemaError,
    safe_path,
)
from open_composer.research.tool_output import page  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in (
        "search",
        "get",
        "context",
        "index",
        "status",
        "event-status",
        "wait",
        "checkpoint",
    ):
        p = sub.add_parser(name)
        if name == "search":
            p.add_argument("query")
        if name == "get":
            p.add_argument("document_id")
            p.add_argument("--byte-offset", type=int)
        if name == "context":
            p.add_argument("task")
        elif name in ("search", "get", "status"):
            p.add_argument("--task")
        if name == "index":
            p.add_argument("--prefix", action="append")
        if name in ("event-status", "wait", "checkpoint"):
            p.add_argument("run", help="Repository-relative research/<direction>/runs/<id>")
            p.add_argument("--phase", default="worker")
        if name == "wait":
            p.add_argument("--timeout-seconds", type=float, required=True)
        if name != "index":
            p.add_argument("--offset", type=int, default=0)
            p.add_argument("--budget", type=int, default=2400)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.command in ("event-status", "wait", "checkpoint"):
        from open_composer.research.agent_workflow import (
            direction_lock,
            identifier,
            require_research,
        )

        run = safe_path(root, args.run)
        parts = Path(args.run).parts
        if len(parts) != 4 or parts[0] != "research" or parts[2] != "runs":
            raise ValueError("Expected one research run")
        identifier(args.phase)
        with direction_lock(run.parent.parent / ".round.lock"):
            state = json.loads((run / "run.json").read_text())
            if state.get("direction") != parts[1] or state.get("run_id") != parts[3]:
                raise ValueError("Saved run binding changed")
            phase = state["phases"][args.phase]
            if args.command == "wait":
                if not 0 < args.timeout_seconds <= 86400:
                    raise ValueError("Wait timeout must be finite and <=86400 seconds")
                # Observation only. Driver resume consumes the persisted event.
                result = wait_event(
                    root,
                    run,
                    phase["wait_state"],
                    time.monotonic() + args.timeout_seconds,
                    require_research,
                )
            elif args.command == "checkpoint":
                result = checkpoint_status(root, run, phase["checkpoint"], phase["session"])
            else:
                result = {
                    "run": args.run,
                    "status": state["status"],
                    "phase": args.phase,
                    "phase_status": phase.get("status"),
                    "wait": phase.get("wait_state"),
                    "checkpoint": phase.get("checkpoint_availability"),
                }
        critical = {"state": result.get("state", result.get("status"))}
        for key in ("reason", "native_resumable", "phase_status"):
            if key in result:
                critical[key] = result[key]
        if result.get("wait"):
            critical["wait_state"] = result["wait"].get("state")
            if result["wait"].get("reason"):
                critical["reason"] = result["wait"]["reason"]
        if result.get("checkpoint"):
            critical["checkpoint_state"] = result["checkpoint"].get("state")
        result = {
            **critical,
            **page(json.dumps(result, ensure_ascii=False), offset=args.offset, budget=args.budget),
        }
    else:
        knowledge = Knowledge(root)
        try:
            if args.command == "index":
                result = knowledge.index(args.prefix)
            else:
                kwargs = {"offset": args.offset, "budget": args.budget}
                if args.command == "context":
                    result = knowledge.context(args.task, **kwargs)
                elif args.command == "search":
                    result = knowledge.search(args.query, task=args.task, **kwargs)
                elif args.command == "get":
                    result = knowledge.get(
                        args.document_id, task=args.task, byte_offset=args.byte_offset, **kwargs
                    )
                else:
                    result = knowledge.status(task=args.task, **kwargs)
        finally:
            knowledge.close()
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KnowledgeSchemaError:
        print(
            json.dumps(
                {
                    "state": "schema_mismatch",
                    "action": "Rebuild only derived runtime/research-tools/knowledge.sqlite3",
                }
            )
        )
        raise SystemExit(2) from None
    except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
        print(
            json.dumps(
                {
                    "state": "unavailable",
                    "error_type": type(exc).__name__,
                    "action": "Check admitted document/run binding; index again if stale",
                }
            )
        )
        raise SystemExit(2) from None
