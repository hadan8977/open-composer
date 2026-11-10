"""Publish the paper dashboard projection once per closed session, unattended.

The site's six-pool overview and history are *published* artifacts, not live
reads: without this, the page freezes on the last manual publication (it sat on
2026-10-26 for two weeks). The chain is the same three steps used on 2026-11-09:

1. ``capture_paper_forward_inputs.py``  - read-only broker/price receipts;
2. ``extend_paper_projection_forward.py`` - carry the sealed 2026-10-27 books
   forward with owned fills and raw closes (recomputed from the sealed base each
   run, so re-runs are idempotent and no incremental state can drift);
3. ``publish_paper_forward_projection.py`` - validate and atomically switch both
   config bindings.

Failure is loud: the JSON summary is appended to ``logs/paper_dashboard_publish.jsonl``
and an e-mail alert goes to the owner channel. Exit 0 only when the published
``through_session`` is the newest closed session.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEALED_HISTORY = ROOT / "reports/paper/diagnostics/fresh-dashboard-owner-audit-20261027/history-v1/reconciled-history-v2.json"
SEALED_OVERVIEW = ROOT / "reports/paper/diagnostics/fresh-dashboard-owner-audit-20261027/overview-v1/capital-clock-v2/reconciled-overview-v2.json"
SEALED_CUTOFF = "2026-10-26T00:00:00Z"
LOG = ROOT / "logs/paper_dashboard_publish.jsonl"


def python() -> str:
    return str(ROOT / ".venv/bin/python")


def symbols(sealed: dict) -> list[str]:
    names: set[str] = set()
    for row in sealed["histories"]:
        if row.get("kind") != "trading_component":
            continue
        for point in row["points"]:
            names.update((point.get("quantity") or {}).keys())
    for path in (ROOT / "reports/paper/rehearsal").glob("*-fills.jsonl"):
        for line in path.read_text().splitlines():
            if line.strip():
                names.add(str(json.loads(line)["symbol"]).upper())
    positions = ROOT / "reports/paper/positions.json"
    if positions.exists():
        for row in json.loads(positions.read_text()).get("positions") or []:
            names.add(str(row["symbol"]).upper())
    state = ROOT / "runtime/paper/six/runtime-state.json"
    if state.exists():
        for book in json.loads(state.read_text())["books"].values():
            for symbol, lots in (book.get("cashbook") or {}).get("lots", {}).items():
                if lots:
                    names.add(str(symbol).upper())
    return sorted(names)


def run(step: str, command: list[str]) -> dict:
    started = datetime.now(UTC)
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    return dict(
        step=step,
        command=[" ".join(command)],
        exit_code=proc.returncode,
        seconds=round((datetime.now(UTC) - started).total_seconds(), 1),
        stdout_tail=proc.stdout[-1200:],
        stderr_tail=proc.stderr[-1200:],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--day",
        help="closed session to publish (default: newest session the broker has actually posted)",
    )
    parser.add_argument("--keep-inputs", action="store_true")
    args = parser.parse_args()
    from open_composer.cockpit.data.paper_books import latest_completed_session
    from open_composer.market_sessions import us_equity_session_dates

    now = datetime.now(UTC)
    newest_closed = latest_completed_session(now)
    target = date.fromisoformat(args.day) if args.day else newest_closed
    work = ROOT / f"reports/paper/diagnostics/forward-projection-{target}"
    inputs, history, overview = work / "inputs", work / "history.json", work / "overview.json"
    sealed = json.loads(SEALED_HISTORY.read_text())
    lag_sessions = 0
    summary = dict(
        at=now.isoformat(),
        mode="publish_daily",
        target_session=str(target),
        inputs=str(inputs),
        steps=[],
        through_session=None,
        ok=False,
    )
    symbols_list = symbols(sealed)
    summary["symbols"] = len(symbols_list)
    work.mkdir(parents=True, exist_ok=True)
    (work / "symbols.json").write_text(json.dumps(symbols_list))
    summary["steps"].append(
        run(
            "capture",
            [
                python(),
                "scripts/capture_paper_forward_inputs.py",
                "--out",
                str(inputs),
                "--after",
                SEALED_CUTOFF,
                "--bars-start",
                "2026-09-01",
                "--bars-end",
                (target + timedelta(days=1)).isoformat(),
                "--symbols",
                str(work / "symbols.json"),
            ],
        )
    )
    # The broker posts a paper session's equity later than the session close, so
    # publish the newest day the accounts have actually posted instead of waiting
    # forever for "today"; a growing lag is the alert condition.
    # Per account: the newest session it can value (posted daily series, or the
    # post-close live snapshot). The publishable day is the min across accounts.
    available: list[date] = []
    for alias in ("legacy", "quant1", "six"):
        capture = json.loads((inputs / f"account-{alias}.json").read_text())
        stamps = capture["portfolio_history"].get("timestamp") or []
        equity = capture["portfolio_history"].get("equity") or []
        days = [
            datetime.fromtimestamp(stamp, UTC)
            .astimezone(__import__("zoneinfo").ZoneInfo("America/New_York"))
            .date()
            for stamp, value in zip(stamps, equity, strict=True)
            if float(value or 0) > 0
        ]
        candidates = [max(days)] if days else []
        # the live snapshot closes a session the daily series has not posted yet
        if float((capture.get("account") or {}).get("equity") or 0) > 0:
            candidates.append(
                latest_completed_session(
                    datetime.fromisoformat(str(capture["captured_at"]).replace("Z", "+00:00"))
                )
            )
        if candidates:
            available.append(max(candidates))
    if args.day is None and available:
        target = min([*available, target])
    summary["target_session"] = str(target)
    lag_sessions = len(
        [
            d
            for d in us_equity_session_dates(target, newest_closed)
            if d > target
        ]
    )
    summary["lag_sessions"] = lag_sessions
    summary["newest_closed"] = str(newest_closed)
    summary["steps"].append(
        run(
            "extend",
            [
                python(),
                "scripts/extend_paper_projection_forward.py",
                "--sealed-history",
                str(SEALED_HISTORY),
                "--inputs",
                str(inputs),
                "--output",
                str(history),
            ],
        )
    )
    summary["steps"].append(
        run(
            "publish",
            [
                python(),
                "scripts/publish_paper_forward_projection.py",
                "--sealed-overview",
                str(SEALED_OVERVIEW),
                "--history",
                str(history),
                "--inputs",
                str(inputs),
                "--overview-output",
                str(overview),
            ],
        )
    )
    through = None
    try:
        through = json.loads(history.read_text())["through_session"]
    except (OSError, ValueError, KeyError):
        pass
    summary["through_session"] = through
    steps_ok = all(step["exit_code"] == 0 for step in summary["steps"])
    summary["ok"] = steps_ok and through == str(target)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as stream:
        stream.write(json.dumps(summary, default=str) + "\n")
    print(json.dumps({k: summary[k] for k in ("target_session", "through_session", "ok", "steps")}, default=str)[:1500])
    summary["lag_sessions"] = lag_sessions
    if not summary["ok"] or lag_sessions >= 2:
        sys.path.insert(0, str(ROOT / "scripts"))
        from paper_watchdog import notify

        bad = [
            f"{s['step']}: exit={s['exit_code']} {s['stderr_tail'][-300:]}"
            for s in summary["steps"]
            if s["exit_code"] != 0
        ]
        if not summary["ok"] and not bad:
            bad = [f"through_session={through} != target_session={target}"]
        notify(
            "Paper dashboard publish failed",
            "\n".join(
                [
                    f"target_session={target}",
                    f"through_session={through}",
                    *bad,
                    f"log={LOG}",
                ]
            ),
            severity="red",
        )
    return 0 if summary["ok"] and lag_sessions < 2 else 2


if __name__ == "__main__":
    raise SystemExit(main())
