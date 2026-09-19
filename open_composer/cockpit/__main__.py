"""Slim entrypoint for the long-running cockpit server.

``oc cockpit serve`` works, but it pays for the whole Typer app: ``open_composer.cli``
imports alpaca-py, duckdb, lightgbm, nautilus-trader, openai, pandas and
scikit-learn at module scope for the other subcommand groups, ~135MB resident
before a single cockpit line runs. The cockpit itself costs ~47MB. That gap is
irrelevant for a one-shot command and expensive for a 24/7 daemon on a 3.9GB
box whose OOM killer prefers the agent sessions, so the systemd/service path
uses this module instead:

    python -m open_composer.cockpit [--host 127.0.0.1] [--port 8770]
    oc-cockpit [--host 127.0.0.1] [--port 8770]

Only argparse, uvicorn and the cockpit app are imported here. The wildcard-host
refusal is duplicated from ``oc cockpit serve`` on purpose: the rule has to hold
on whichever path is used, and this one is the path a service unit will take.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

UNSAFE_HOSTS = frozenset({"0.0.0.0", "::", "[::]", "*"})  # noqa: S104 - listed to refuse them

_REFUSAL = (
    "Refusing to bind {host!r}. The cockpit has no application-level authentication by "
    "design -- keep --host 127.0.0.1 and put Cloudflare Access in front of it for remote "
    "access (see AGENTS.md and docs/plan-step-18-readonly-cockpit-2026-09-19.zh.md)."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oc-cockpit",
        description="Serve the read-only Open Composer cockpit (GET/HEAD routes only).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host; must stay loopback.")
    parser.add_argument("--port", type=int, default=8770, help="Bind port.")
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.host in UNSAFE_HOSTS:
        print(_REFUSAL.format(host=args.host), file=sys.stderr)
        return 1

    import uvicorn

    from open_composer.cockpit.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level=args.log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
