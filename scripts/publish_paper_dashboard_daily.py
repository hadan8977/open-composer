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
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEALED_HISTORY = ROOT / "reports/paper/diagnostics/fresh-dashboard-owner-audit-20261027/history-v1/reconciled-history-v2.json"
SEALED_OVERVIEW = ROOT / "reports/paper/diagnostics/fresh-dashboard-owner-audit-20261027/overview-v1/capital-clock-v2/reconciled-overview-v2.json"
SEALED_CUTOFF = "2026-10-26T00:00:00Z"
LOG = ROOT / "logs/paper_dashboard_publish.jsonl"


def python() -> str:
    return str(ROOT / ".venv/bin/python")


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

    def execute(step: str, command: list[str]) -> None:
        result = run(step, command)
        summary["steps"].append(result)
        if result["exit_code"] != 0:
            raise RuntimeError(f"{step} failed with exit {result['exit_code']}")

    through = None
    try:
        work.mkdir(parents=True, exist_ok=True)
        # A partial/failed capture must never reuse receipts from an earlier run.
        inputs = Path(tempfile.mkdtemp(prefix="inputs-", dir=work))
        summary["inputs"] = str(inputs)
        execute(
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
                "--sealed-history",
                str(SEALED_HISTORY),
            ],
        )
        # The broker posts a paper session's equity later than the session close, so
        # publish the newest day the accounts have actually posted instead of waiting
        # forever for "today"; a growing lag is the alert condition.
        # Per account: the newest session it can value (posted daily series, or the
        # post-close live snapshot). The publishable day is the min across accounts.
        from open_composer.reports.paper_equity import account_equity_points

        available: list[date] = []
        for alias in ("legacy", "quant1", "six"):
            capture = json.loads((inputs / f"account-{alias}.json").read_text())
            evidence = account_equity_points(capture)
            if not evidence:
                raise RuntimeError(f"{alias}: no closed-session equity evidence")
            available.append(max(evidence))
        if args.day is None:
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
        execute(
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
                "--through-session",
                str(target),
            ],
        )
        through = json.loads(history.read_text())["through_session"]
        if through != str(target):
            raise RuntimeError(f"extension through_session={through} != target_session={target}")
        execute(
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
        through = json.loads(history.read_text())["through_session"]
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
    summary["through_session"] = through
    steps_ok = all(step["exit_code"] == 0 for step in summary["steps"])
    summary["ok"] = not summary.get("error") and steps_ok and through == str(target)
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
        if summary.get("error"):
            bad.append(summary["error"])
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
