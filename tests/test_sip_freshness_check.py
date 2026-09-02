"""Staleness must be loud, not silent."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_sip_freshness import (  # noqa: E402
    last_completed_session,
    sessions_behind,
)


def test_weekends_and_holidays_do_not_read_as_drift() -> None:
    # 2026-01-01 is a market holiday and 2026-01-03/04 is a weekend, so the last
    # completed session before Monday 2026-01-05 is Friday 2026-01-02.
    assert last_completed_session(date(2026, 1, 5)) == date(2026, 1, 2)


def test_an_archive_current_to_the_last_session_is_zero_behind() -> None:
    reference = last_completed_session(date(2026, 9, 2))
    assert sessions_behind(reference, reference) == 0


def test_a_bar_ahead_of_the_reference_is_not_negative() -> None:
    assert sessions_behind(date(2026, 9, 10), date(2026, 9, 2)) == 0


def test_sessions_behind_counts_trading_days_not_calendar_days() -> None:
    # Friday 2026-01-02 to Monday 2026-01-05 is three calendar days but one session.
    assert sessions_behind(date(2026, 1, 2), date(2026, 1, 5)) == 1


def test_a_long_gap_is_reported_in_sessions() -> None:
    behind = sessions_behind(date(2026, 8, 4), date(2026, 9, 1))
    # Four weeks of trading days, not 28.
    assert 15 <= behind <= 22
