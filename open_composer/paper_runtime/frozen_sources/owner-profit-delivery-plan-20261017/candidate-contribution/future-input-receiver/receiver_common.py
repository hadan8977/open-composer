"""Canonical scientific source/packet identities; no source or numerical work on import."""

import importlib.util
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
REPO = TASK.parents[4]
SHARE = REPO / "reports/research/program/share-turnover-information-20261017"
ACCOUNT = (
    REPO
    / "reports/research/program/return-line-replenishment-20261016/dia-shareholder-account-20261017"
)
spec = importlib.util.spec_from_file_location("base_receiver_accepted_common", TASK / "common.py")
accepted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accepted)
binding, load, save, verify, clean = (
    accepted.binding,
    accepted.load,
    accepted.save,
    accepted.verify,
    accepted.clean,
)
legacy, module = accepted.legacy, accepted.module
spec = importlib.util.spec_from_file_location(
    "base_receiver_accepted_output", TASK / "future-interface-repair/scheduled_base.py"
)
output = importlib.util.module_from_spec(spec)
spec.loader.exec_module(output)
SYMBOLS = output.SYMBOLS
UNITS = SYMBOLS + ["SOLV", "SOLS", "HONA"]
clock, now, calendar = output.clock, output.now, output.calendar


def canonical(path):
    p = Path(path).absolute()
    assert p.resolve() == p, "Canonical source/derived context required"
    return p


def checked(row, expected=None):
    p = canonical(row["path"])
    assert expected is None or p == canonical(expected), "Wrong canonical slot"
    verify(row)
    return p


def month_dates(month):
    from open_composer.market_sessions import us_equity_session_dates

    year, number = map(int, month.split("-"))
    first = date(year, number, 1)
    end = date(year + (number == 12), number % 12 + 1, 1) - timedelta(days=1)
    return [d.isoformat() for d in us_equity_session_dates(first, end)]


def absolute_fact_time(day):
    from open_composer.market_sessions import NEW_YORK, us_equity_session_close

    d = date.fromisoformat(day)
    close = us_equity_session_close(d)
    assert close is not None
    return datetime.combine(d, close, NEW_YORK).astimezone(UTC)
