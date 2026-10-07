#!/usr/bin/env python3
"""Generic intraday paper runner (quant2): replay, live run, finish, recheck, status, authorize.

    uv run python scripts/run_intraday_runner.py replay --config <cfg> \\
        --session 2026-10-02 --out-root /tmp/oc-dryrun --report <report.md> --restart-check
    uv run python scripts/run_intraday_runner.py run --config <cfg>                  # plan only
    uv run python scripts/run_intraday_runner.py run --config <cfg> --allow-paper-orders

``run`` is safe to start from cron more than once (file lock) and after a crash (state is rebuilt
from the event log).  Orders are only submitted with ``--allow-paper-orders`` *and* a valid
authorization bound to the config hash and the account; the replay command never touches a broker.
Credentials are read by variable name from the 600 env file; nothing here prints a value.
See docs/runbook-intraday-runner.zh.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.intraday_runner.bars import session_bounds  # noqa: E402
from open_composer.intraday_runner.books import EventLog, replay  # noqa: E402
from open_composer.intraday_runner.config import (  # noqa: E402
    load_runner_config,
    write_runner_authorization,
)
from open_composer.intraday_runner.engine import runner_dir  # noqa: E402
from open_composer.intraday_runner.live import (  # noqa: E402
    build_engine,
    load_opening,
    make_alpaca_broker,
    preflight,
    run_live,
    today_et,
)
from open_composer.intraday_runner.replay import render_dryrun_report, replay_session  # noqa: E402
from open_composer.intraday_runner.reporting import finish_session, sip_recheck  # noqa: E402

RECHECK_DELAY_MINUTES = 25  # free SIP history is delayed 15 minutes


def _session(value: str | None) -> date:
    return date.fromisoformat(value) if value else today_et(datetime.now(UTC))


def cmd_replay(args: argparse.Namespace) -> int:
    config = load_runner_config(Path(args.config))
    out_root = Path(args.out_root)
    session = date.fromisoformat(args.session)
    prev_file = Path(args.prev_close_file) if args.prev_close_file else None
    result = replay_session(
        config,
        session,
        out_root,
        slippage_bps=args.slippage_bps,
        degrade_live=not args.no_degrade,
        prev_close_file=prev_file,
    )
    restart = None
    if args.restart_check:
        before = EventLog(result["engine"].event_dir / "events.jsonl").read()
        again = replay_session(
            config,
            session,
            out_root,
            slippage_bps=args.slippage_bps,
            degrade_live=not args.no_degrade,
            prev_close_file=prev_file,
        )
        after = EventLog(again["engine"].event_dir / "events.jsonl").read()

        def count(events, kind):
            return sum(1 for e in events if e["type"] == kind)

        restart = {
            "new_net_orders": count(after, "net_order") - count(before, "net_order"),
            "new_submits": len(again["broker"].submit_calls),
            "new_summary_rows": count(after, "summary") - count(before, "summary"),
        }
    text = render_dryrun_report(result, config, restart)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text, encoding="utf-8")
    print(json.dumps({"ticks": result["ticks"], "report": args.report, "restart": restart}))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    outcome = run_live(
        Path(args.config), ROOT, allow_paper_orders=args.allow_paper_orders, once=args.once
    )
    print(json.dumps(outcome, default=str))
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    config = load_runner_config(Path(args.config))
    session = _session(args.session)
    engine = build_engine(
        config,
        ROOT,
        session,
        make_alpaca_broker(config.account),
        allow_paper_orders=args.allow_paper_orders,
    )
    outcome = finish_session(engine, datetime.now(UTC))
    print(json.dumps({"report": outcome["report"], "ok": outcome["reconcile"]["ok"]}))
    return 0 if outcome["reconcile"]["ok"] else 3


def cmd_recheck(args: argparse.Namespace) -> int:
    from open_composer.intraday_runner.bars import AlpacaMinuteProvider, ArchiveMinuteProvider

    config = load_runner_config(Path(args.config))
    session = _session(args.session)
    _, close_ts = session_bounds(session)
    if datetime.now(UTC) < close_ts.to_pydatetime() + timedelta(minutes=RECHECK_DELAY_MINUTES):
        print(json.dumps({"status": "too_early_for_sip"}))
        return 0
    engine = build_engine(
        config,
        ROOT,
        session,
        make_alpaca_broker(config.account),
        allow_paper_orders=args.allow_paper_orders,
    )
    provider = (
        ArchiveMinuteProvider()
        if args.source == "archive"
        else AlpacaMinuteProvider("sip", account=config.account)
    )
    result = sip_recheck(engine, provider)
    print(json.dumps({"decisions": result.get("decisions", {}).get("decisions_differing")}))
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    """Read-only: is quant2 flat with no open orders?  Reports; never closes or cancels."""
    config = load_runner_config(Path(args.config))
    broker = make_alpaca_broker(config.account)
    result = preflight(broker, load_opening(ROOT, config, _session(args.session)))
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 3


def cmd_status(args: argparse.Namespace) -> int:
    config = load_runner_config(Path(args.config))
    session = _session(args.session)
    folder = runner_dir(ROOT, config.account) / (
        session.isoformat() + ("" if args.allow_paper_orders else "-plan")
    )
    state = replay(config, session.isoformat(), EventLog(folder / "events.jsonl"))
    print(
        json.dumps(
            {
                "session": session.isoformat(),
                "positions": {
                    k: {s: q for s, q in v.positions.items() if q} for k, v in state.subs.items()
                },
                "halts": state.halts,
                "orders": len(state.orders),
                "unresolved": [o.cid for o in state.unresolved()],
                "intents": state.intents,
            },
            indent=2,
        )
    )
    return 0


def cmd_authorize(args: argparse.Namespace) -> int:
    """Coordinator step: bind an authorization to the config hash and the paper account."""
    if not args.confirm_paper_only:
        print("refusing: --confirm-paper-only is required", file=sys.stderr)
        return 2
    config = load_runner_config(Path(args.config))
    broker = make_alpaca_broker(config.account)
    path = write_runner_authorization(
        config,
        ROOT,
        authorized_by=args.authorized_by,
        basis=args.basis,
        account_id_hash=broker.account_snapshot().id_hash,
        duration_days=args.days,
    )
    print(json.dumps({"authorization": str(path)}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("replay", "run", "finish", "recheck", "status", "authorize", "preflight"):
        p = sub.add_parser(name)
        p.add_argument("--config", required=True)
        if name == "replay":
            p.add_argument("--session", required=True)
            p.add_argument("--out-root", required=True)
            p.add_argument("--report")
            p.add_argument("--slippage-bps", type=float, default=1.0)
            p.add_argument("--no-degrade", action="store_true")
            p.add_argument(
                "--prev-close-file",
                help="JSON {symbol: unadjusted previous close}; default = last minute close",
            )
            p.add_argument("--restart-check", action="store_true")
            p.set_defaults(func=cmd_replay)
        elif name == "run":
            p.add_argument("--allow-paper-orders", action="store_true")
            p.add_argument("--once", action="store_true", help="one tick for the latest minute")
            p.set_defaults(func=cmd_run)
        elif name == "preflight":
            p.add_argument("--session")
            p.set_defaults(func=cmd_preflight)
        elif name in ("finish", "recheck", "status"):
            p.add_argument("--session")
            p.add_argument("--allow-paper-orders", action="store_true")
            if name == "recheck":
                p.add_argument("--source", choices=("alpaca", "archive"), default="alpaca")
            p.set_defaults(
                func={"finish": cmd_finish, "recheck": cmd_recheck, "status": cmd_status}[name]
            )
        else:
            p.add_argument("--authorized-by", required=True)
            p.add_argument("--basis", required=True, help="the owner's words, quoted")
            p.add_argument("--days", type=int, default=14)
            p.add_argument("--confirm-paper-only", action="store_true")
            p.set_defaults(func=cmd_authorize)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
