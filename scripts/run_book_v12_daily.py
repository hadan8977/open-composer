"""Daily driver of book v1.2 (T-20261002-28).  Not scheduled; the crontab lines are proposals.

Modes (exactly one):

* ``--targets``  after the live data refresh: write the F1/F2 target files of decision date D
  (default: the last session of the live equity-book root).  Exit 2: the data root is not fresh to
  D (or is missing); exit 3: the generator or the target writer refused.  Re-running for a decision
  date whose target files exist is a no-op (a logged target is never rewritten).
* ``--plan``     on the execution date, 18:30-19:30 UTC: build the dry-run plans of both accounts
  with ``oc book-paper plan`` (read-only broker calls; sends nothing).
* ``--submit``   the same plans, then ``oc book-paper submit --submit`` (closing-auction orders).
  Refuses (exit 4) unless the environment variable ``OC_BOOK_V12_SUBMIT=1`` is set, which only the
  owner-approved cron entry does.  This task never sets it and never runs this mode.
* ``--reconcile`` after the evening SIP refresh (proposal: 22:45 UTC weekdays) of the execution date
  (``--execution-date``, default: today in New York): build ``reports/paper/book/prices/<D>.json``
  from the local SIP archives (``scripts/build_book_prices_file.py``; no network), then run
  ``oc book-paper reconcile --prices-file`` for both accounts (read-only broker calls: orders and
  positions).  A daily record that already exists is not rebuilt.  Exit 2: the archives hold no
  bar of D yet (the cron retries later); exit 3: no plan file of D.

Exit codes: 0 ok, 2 data not fresh, 3 targets refused, 4 submit not enabled, 5 plan/submit/reconcile
command failed, 6 another run holds the lock.  Log: ``logs/book_v12_daily.log``.  Lock:
``logs/book_v12_daily.lock``.  The script makes no broker call itself; only the ``oc book-paper``
commands of ``--plan``/``--submit``/``--reconcile`` do.
"""

from __future__ import annotations

import argparse
import fcntl
import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.book_paper import v12_targets as v12  # noqa: E402
from open_composer.book_paper.accounts import BOOK_ACCOUNTS  # noqa: E402
from open_composer.book_paper.plan import plan_path  # noqa: E402
from open_composer.book_paper.post_close import daily_path  # noqa: E402
from open_composer.book_paper.targets import (  # noqa: E402
    BookTargetError,
    latest_target_path,
    load_target_file,
    now_utc_text,
    target_path,
    write_target_file,
)
from open_composer.market_sessions import NEW_YORK  # noqa: E402
from scripts import build_book_prices_file as prices_builder  # noqa: E402

LIVE_ROOT = ROOT / "data/live/equity_book"
LOG_FILE = ROOT / "logs/book_v12_daily.log"
LOCK_FILE = ROOT / "logs/book_v12_daily.lock"
SUBMIT_ENV = "OC_BOOK_V12_SUBMIT"
EXIT_FRESH, EXIT_REFUSED, EXIT_SUBMIT_OFF, EXIT_COMMAND, EXIT_LOCKED = 2, 3, 4, 5, 6
log = logging.getLogger("book_v12_daily")


def setup_logging(path: Path = LOG_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S")
    fmt.converter = time.gmtime
    for handler in (logging.FileHandler(path), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def submit_enabled(env: dict[str, str] | None = None) -> bool:
    return (env if env is not None else os.environ).get(SUBMIT_ENV) == "1"


def run_targets(root: Path, data_root: Path, decision: date | None, variant: str | None) -> int:
    if not (data_root / "panel/_calendar.parquet").exists():
        log.error("data root %s has no calendar: not fresh", data_root)
        return EXIT_FRESH
    last = v12.last_session(data_root)
    day = decision or last
    if last < day:
        log.error("data root last session %s is before decision date %s: not fresh", last, day)
        return EXIT_FRESH
    paths = {a: target_path(root, a, day) for a in BOOK_ACCOUNTS}
    if all(p.exists() for p in paths.values()):
        log.info("targets of %s already logged: nothing to do", day)
        return 0
    try:
        chosen = variant or v12.primary_variant()
        bundle = v12.build_v12_bundle(
            day, variant=chosen, data_root=data_root, logged_at_utc=now_utc_text()
        )
        for target in bundle.targets.values():
            info = v12.summarize_target(target)
            log.info("target %s", info)
            written = write_target_file(root, target)
            log.info("wrote %s", written)
        for form, names in bundle.unpriced.items():
            if names:
                log.warning("%s: dropped without a close on D: %s", form, ", ".join(names))
    except (v12.TargetRefused, BookTargetError) as exc:
        log.error("targets refused: %s", exc)
        return EXIT_REFUSED
    return 0


def oc_command() -> list[str]:
    venv = ROOT / ".venv/bin/oc"
    return [str(venv)] if venv.exists() else ["oc"]


def run_plans(root: Path, decision: date | None, *, submit: bool) -> int:
    if decision is None:
        newest = latest_target_path(root, BOOK_ACCOUNTS[0])
        if newest is None:
            log.error("no target file for %s", BOOK_ACCOUNTS[0])
            return EXIT_REFUSED
        decision = load_target_file(newest).decision_date
    for account in BOOK_ACCOUNTS:
        if not target_path(root, account, decision).exists():
            log.error("no target file for %s on %s", account, decision)
            return EXIT_REFUSED
    for account in BOOK_ACCOUNTS:
        base = [*oc_command(), "book-paper"]
        steps = [[*base, "plan", "--account", account, "--decision-date", decision.isoformat()]]
        if submit:
            steps.append(
                [
                    *base,
                    "submit",
                    "--account",
                    account,
                    "--decision-date",
                    decision.isoformat(),
                    "--submit",
                ]
            )
        for cmd in steps:
            log.info("run: %s", " ".join(cmd))
            proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
            for line in (proc.stdout + proc.stderr).splitlines():
                log.info("  %s", line)
            if proc.returncode != 0:
                log.error("`%s` failed with exit %s", " ".join(cmd[-5:]), proc.returncode)
                return EXIT_COMMAND
    return 0


def run_reconcile(
    root: Path,
    execution_date: date,
    *,
    sip_root: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> int:
    """Prices file of the date from the local SIP archives, then reconcile both accounts."""
    runner = runner or subprocess.run  # looked up at call time (tests patch it)
    todo = [a for a in BOOK_ACCOUNTS if not daily_path(root, a, execution_date).exists()]
    if not todo:
        log.info("daily records of %s already written: nothing to do", execution_date)
        return 0
    for account in todo:
        if not plan_path(root, account, execution_date).exists():
            log.error("no plan file for %s on %s", account, execution_date)
            return EXIT_REFUSED
    try:
        path, payload = prices_builder.build_and_write(
            execution_date, root=root, sip_root=sip_root, now=datetime.now(UTC)
        )
    except prices_builder.DataNotFresh as exc:
        log.error("prices file: %s", exc)
        return EXIT_FRESH
    except prices_builder.InputsError as exc:
        log.error("prices file inputs: %s", exc)
        return EXIT_REFUSED
    log.info(prices_builder.summary_line(payload))
    log.info("prices file %s", path)
    for account in todo:
        cmd = [
            *oc_command(),
            "book-paper",
            "reconcile",
            "--account",
            account,
            "--date",
            execution_date.isoformat(),
            "--prices-file",
            str(path),
        ]
        log.info("run: %s", " ".join(cmd))
        proc = runner(cmd, cwd=root, capture_output=True, text=True, check=False)
        for line in (proc.stdout + proc.stderr).splitlines():
            log.info("  %s", line)
        if proc.returncode != 0:
            log.error("`%s` failed with exit %s", " ".join(cmd[-5:]), proc.returncode)
            return EXIT_COMMAND
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--targets", action="store_true")
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--submit", action="store_true")
    mode.add_argument("--reconcile", action="store_true")
    ap.add_argument("--execution-date", default=None, help="--reconcile; default: today (New York)")
    ap.add_argument("--sip-root", default=None, help="--reconcile; default: <root>/data/sip")
    ap.add_argument("--decision-date", default=None)
    ap.add_argument("--variant", default=None, help="default: primary variant of results.json")
    ap.add_argument("--data-root", default=None, help=f"default: {LIVE_ROOT}")
    ap.add_argument("--root", default=str(ROOT), help="project root (tests)")
    ap.add_argument("--lock-file", default=str(LOCK_FILE))
    ap.add_argument("--log-file", default=str(LOG_FILE))
    args = ap.parse_args(argv)
    if args.submit and not submit_enabled():
        print(f"refused: --submit needs {SUBMIT_ENV}=1 (set only by the owner-approved cron)")
        return EXIT_SUBMIT_OFF
    setup_logging(Path(args.log_file))
    Path(args.lock_file).parent.mkdir(parents=True, exist_ok=True)
    with open(args.lock_file, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            log.error("another book_v12_daily run holds %s", args.lock_file)
            return EXIT_LOCKED
        decision = date.fromisoformat(args.decision_date) if args.decision_date else None
        root = Path(args.root)
        if args.targets:
            data_root = Path(args.data_root) if args.data_root else LIVE_ROOT
            return run_targets(root, data_root, decision, args.variant)
        if args.reconcile:
            day = (
                date.fromisoformat(args.execution_date)
                if args.execution_date
                else datetime.now(UTC).astimezone(NEW_YORK).date()
            )
            return run_reconcile(root, day, sip_root=Path(args.sip_root) if args.sip_root else None)
        return run_plans(root, decision, submit=args.submit)


if __name__ == "__main__":
    sys.exit(main())
