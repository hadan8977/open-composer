"""US equity exchange session dates, standard library only.

Split out of ``open_composer.market_calendar`` (2026-09-30) so that memory-bound
processes -- the read-only cockpit has a 150MB RSS budget -- can ask "was this a
trading day?" without importing pandas, which ``market_calendar`` needs for its
bar-grid validators. ``market_calendar`` re-exports everything defined here, so
existing imports keep working unchanged.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def us_equity_session_close(day: date) -> time | None:
    if day.weekday() >= 5 or day in _holidays(day.year):
        return None
    return time(13, 0) if day in _early_closes(day.year) else time(16, 0)


def us_equity_session_dates(start: date, end: date) -> tuple[date, ...]:
    """Return exchange session dates for the inclusive calendar-date interval."""
    if not isinstance(start, date) or isinstance(start, datetime):
        raise TypeError("start must be a date")
    if not isinstance(end, date) or isinstance(end, datetime):
        raise TypeError("end must be a date")
    if start > end:
        raise ValueError("start must be on or before end")
    sessions: list[date] = []
    day = start
    while day <= end:
        if us_equity_session_close(day) is not None:
            sessions.append(day)
        day += timedelta(days=1)
    return tuple(sessions)


def next_us_equity_session(day: date) -> date:
    candidate = day + timedelta(days=1)
    while us_equity_session_close(candidate) is None:
        candidate += timedelta(days=1)
    return candidate


def previous_us_equity_session(day: date) -> date:
    candidate = day - timedelta(days=1)
    while us_equity_session_close(candidate) is None:
        candidate -= timedelta(days=1)
    return candidate


def _holidays(year: int) -> set[date]:
    regular_holidays = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _good_friday(year),
        _last_weekday(year, 5, 0),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed(date(year, 12, 25)),
    }
    if year >= 2022:
        regular_holidays.add(_observed(date(year, 6, 19)))
    return regular_holidays | _special_closures(year)


def _special_closures(year: int) -> set[date]:
    closures = {
        # National Day of Mourning for former President George H. W. Bush.
        date(2018, 12, 5),
        # National Day of Mourning for former President Jimmy Carter.
        date(2025, 1, 9),
    }
    return {day for day in closures if day.year == year}


def _early_closes(year: int) -> set[date]:
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    candidates = {thanksgiving + timedelta(days=1)}
    july_fourth = date(year, 7, 4)
    if july_fourth.weekday() in {1, 2, 3, 4}:
        candidates.add(july_fourth - timedelta(days=1))
    christmas_eve = date(year, 12, 24)
    if christmas_eve.weekday() < 5:
        candidates.add(christmas_eve)
    return {day for day in candidates if day.weekday() < 5 and day not in _holidays(year)}


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    day = date(year, month, 1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day + timedelta(weeks=occurrence - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    day = next_month - timedelta(days=1)
    while day.weekday() != weekday:
        day -= timedelta(days=1)
    return day


def _good_friday(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    weekday_offset = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday_offset) // 451
    month = (h + weekday_offset - 7 * m + 114) // 31
    day = (h + weekday_offset - 7 * m + 114) % 31 + 1
    return date(year, month, day) - timedelta(days=2)
