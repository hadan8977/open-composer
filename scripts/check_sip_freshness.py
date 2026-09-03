"""Report how far behind the local SIP archive is, and fail when it is too far.

An archive that stops updating does not announce itself. Every backtest keeps
running, every number keeps looking reasonable, and the only symptom is that the
last bar quietly recedes into the past. That is exactly how the retired IEX cache
came to sit at 2026-08-04 while still being used, so this check exists to make
staleness loud rather than silent.

The reference point is the last *completed* US equity session from
``open_composer.market_calendar``, so holidays and weekends do not read as drift.
Today is never required to be present: the session may still be open, and the
fetcher embargoes the most recent minutes anyway.

Exit code is the verdict, so a scheduler can act on it: 0 fresh, 1 stale.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from open_composer.adapters.data.sip_parquet import (
    SUPPORTED_FREQUENCIES,
    SipParquetError,
    default_sip_root,
    load_sip_bars,
)
from open_composer.config import project_root
from open_composer.market_calendar import us_equity_session_dates
from open_composer.notifications import dispatch_notification

#: A daily bar for yesterday's session may legitimately not be published yet, so
#: one session of slack is normal and two is not.
DEFAULT_MAX_STALE_SESSIONS = 2
#: Liquid, continuously listed, and in every shard layout this repo has used.
PROBE_SYMBOL = "QQQ"


def last_completed_session(today: date) -> date:
    """The most recent US equity session strictly before ``today``."""
    sessions = us_equity_session_dates(today - timedelta(days=30), today)
    earlier = [session for session in sessions if session < today]
    if not earlier:
        raise RuntimeError("no US equity session found in the trailing 30 days")
    return earlier[-1]


def sessions_behind(last_bar: date, reference: date) -> int:
    """Count trading sessions between ``last_bar`` and ``reference``."""
    if last_bar >= reference:
        return 0
    sessions = us_equity_session_dates(last_bar, reference)
    return max(len([s for s in sessions if s > last_bar]), 0)


#: Only the trailing window is probed. A freshness check that scans the whole
#: archive costs minutes on the minute tape, and a check nobody is willing to
#: wait for is a check that never runs.
PROBE_WINDOW_DAYS = 120


def archive_status(frequency: str, *, today: date, symbol: str = PROBE_SYMBOL) -> dict:
    reference = last_completed_session(today)
    start = today - timedelta(days=PROBE_WINDOW_DAYS)
    try:
        frame = load_sip_bars(symbol, frequency=frequency, start=start.isoformat())
    except SipParquetError as exc:
        # No rows in the trailing window at all is itself the answer: the archive
        # is at least PROBE_WINDOW_DAYS behind.
        return {
            "frequency": frequency,
            "available": True,
            "probe_symbol": symbol,
            "last_bar": None,
            "last_completed_session": reference.isoformat(),
            "sessions_behind": sessions_behind(start, reference),
            "detail": str(exc),
        }
    last_bar = pd.Timestamp(frame["timestamp"].max()).tz_convert("UTC").date()
    return {
        "frequency": frequency,
        "available": True,
        "probe_symbol": symbol,
        "last_bar": last_bar.isoformat(),
        "last_completed_session": reference.isoformat(),
        "sessions_behind": sessions_behind(last_bar, reference),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-stale-sessions", type=int, default=DEFAULT_MAX_STALE_SESSIONS)
    parser.add_argument("--frequency", choices=[*SUPPORTED_FREQUENCIES, "all"], default="all")
    parser.add_argument("--today", default=None, help="Override the reference date (ISO-8601).")
    parser.add_argument(
        "--notify-on-stale",
        action="store_true",
        help="Dispatch a system_alert notification (Telegram + log) when any archive is stale.",
    )
    args = parser.parse_args()

    today = date.fromisoformat(args.today) if args.today else datetime.now(UTC).date()
    frequencies = SUPPORTED_FREQUENCIES if args.frequency == "all" else (args.frequency,)

    reports = []
    stale = []
    for frequency in frequencies:
        if not (default_sip_root() / frequency).is_dir():
            continue
        report = archive_status(frequency, today=today)
        reports.append(report)
        if report.get("available") and report["sessions_behind"] > args.max_stale_sessions:
            stale.append(report)

    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "max_stale_sessions": args.max_stale_sessions,
        "archives": reports,
        "stale": [item["frequency"] for item in stale],
    }
    print(json.dumps(payload, indent=2))
    for item in stale:
        print(
            f"STALE: SIP {item['frequency']} last bar {item['last_bar']} is "
            f"{item['sessions_behind']} session(s) behind {item['last_completed_session']}; "
            f"run scripts/fetch_sip_universe.py to top it up",
            file=sys.stderr,
        )
    if stale and args.notify_on_stale:
        detail = "; ".join(
            f"{item['frequency']}: last bar {item['last_bar']} is "
            f"{item['sessions_behind']} session(s) behind {item['last_completed_session']}"
            for item in stale
        )
        dispatch_notification(
            kind="system_alert",
            severity="warn",
            title=f"SIP archive stale: {', '.join(item['frequency'] for item in stale)}",
            body=detail,
            metadata={"source": "check_sip_freshness.py", "stale": payload["stale"]},
            root=project_root(),
        )
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
