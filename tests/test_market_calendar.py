from __future__ import annotations

from datetime import date

from open_composer.market_calendar import expected_rth_bar_closes, us_equity_session_close


def test_us_equity_calendar_handles_holidays_early_close_and_dst() -> None:
    assert us_equity_session_close(date(2026, 7, 3)) is None
    assert len(expected_rth_bar_closes(date(2026, 11, 27))) == 6
    winter = min(expected_rth_bar_closes(date(2026, 1, 6)))
    summer = min(expected_rth_bar_closes(date(2026, 7, 2)))
    assert winter.hour == 15
    assert summer.hour == 14


def test_us_equity_calendar_expected_slots_detect_missing_and_duplicate_bars() -> None:
    expected = expected_rth_bar_closes(date(2026, 7, 2))
    assert len(expected) == 12
    missing = set(expected)
    missing.pop()
    assert missing != expected
    duplicated_input = list(expected) + [next(iter(expected))]
    assert len(duplicated_input) != len(set(duplicated_input))
