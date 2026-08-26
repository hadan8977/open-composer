from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

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


def expected_rth_bar_closes(day: date, timeframe_minutes: int = 30) -> set[pd.Timestamp]:
    _validate_timeframe_minutes(timeframe_minutes)
    close = us_equity_session_close(day)
    if close is None:
        return set()
    current = datetime.combine(day, time(10, 0), tzinfo=NEW_YORK)
    end = datetime.combine(day, close, tzinfo=NEW_YORK)
    result = set()
    while current < end:
        result.add(pd.Timestamp(current).tz_convert("UTC"))
        current += timedelta(minutes=timeframe_minutes)
    return result


def expected_us_equity_rth_bar_starts(day: date, timeframe_minutes: int = 30) -> set[pd.Timestamp]:
    """Return the start-labelled RTH grid for one US-equity session."""
    _validate_timeframe_minutes(timeframe_minutes)
    close = us_equity_session_close(day)
    if close is None:
        return set()
    current = datetime.combine(day, time(9, 30), tzinfo=NEW_YORK)
    end = datetime.combine(day, close, tzinfo=NEW_YORK)
    result = set()
    while current < end:
        result.add(pd.Timestamp(current).tz_convert("UTC"))
        current += timedelta(minutes=timeframe_minutes)
    return result


def validate_us_equity_bar_grid(
    timestamps: Iterable[object] | pd.Series | pd.Index | pd.DataFrame,
    timeframe_minutes: int = 30,
) -> dict[str, Any]:
    """Classify timestamps against the start-labelled US-equity RTH grid.

    Partial first and last sessions are dropped from quality evaluation. Missing
    slots in the retained sessions are interior bars; all other missing slots are
    boundary bars and do not contribute to the interior gap rate.
    """
    _validate_timeframe_minutes(timeframe_minutes)
    observed = _coerce_timestamps(timestamps)
    if not observed:
        return _empty_grid_result(timeframe_minutes)

    counts = Counter(observed)
    unique_observed = sorted(counts)
    first_day = unique_observed[0].tz_convert(NEW_YORK).date()
    last_day = unique_observed[-1].tz_convert(NEW_YORK).date()
    expected_by_day: dict[date, set[pd.Timestamp]] = {}
    day = first_day
    while day <= last_day:
        expected = expected_us_equity_rth_bar_starts(day, timeframe_minutes)
        if expected:
            expected_by_day[day] = expected
        day += timedelta(days=1)

    expected_slots = sorted(slot for slots in expected_by_day.values() for slot in slots)
    expected_set = set(expected_slots)
    matched = sorted(expected_set.intersection(unique_observed))
    off_session: list[pd.Timestamp] = []
    off_grid: list[pd.Timestamp] = []
    for timestamp in unique_observed:
        if timestamp in expected_set:
            continue
        if _is_in_us_equity_rth(timestamp):
            off_grid.append(timestamp)
        else:
            off_session.append(timestamp)

    missing = expected_set.difference(matched)
    dropped_boundary_sessions: set[date] = set()
    if matched:
        first_matched_day = matched[0].tz_convert(NEW_YORK).date()
        last_matched_day = matched[-1].tz_convert(NEW_YORK).date()
        first_session_slots = expected_by_day[first_matched_day]
        last_session_slots = expected_by_day[last_matched_day]
        if matched[0] > min(first_session_slots):
            dropped_boundary_sessions.add(first_matched_day)
        if matched[-1] < max(last_session_slots):
            dropped_boundary_sessions.add(last_matched_day)
        quality_session_days = {
            session_day
            for session_day in expected_by_day
            if first_matched_day <= session_day <= last_matched_day
            and session_day not in dropped_boundary_sessions
        }
        interior_expected = {
            slot for session_day in quality_session_days for slot in expected_by_day[session_day]
        }
    else:
        interior_expected = set()
    missing_interior = sorted(missing.intersection(interior_expected))
    missing_boundary = sorted(missing.difference(interior_expected))
    duplicate_timestamps = sorted(timestamp for timestamp, count in counts.items() if count > 1)
    duplicate_bar_count = sum(count - 1 for count in counts.values() if count > 1)
    off_session_bar_count = sum(counts[timestamp] for timestamp in off_session)
    off_grid_bar_count = sum(counts[timestamp] for timestamp in off_grid)
    interior_expected_count = len(interior_expected)
    interior_gap_rate = (
        len(missing_interior) / interior_expected_count if interior_expected_count else 0.0
    )
    expected_count = len(expected_set)
    grid_coverage_ratio = len(matched) / expected_count if expected_count else 0.0
    interior_coverage_ratio = 1.0 - interior_gap_rate if interior_expected_count else 0.0
    has_quality_issue = bool(
        duplicate_bar_count or off_session_bar_count or off_grid_bar_count or missing_interior
    )
    if not matched or not interior_expected:
        quality_status = "invalid"
    elif has_quality_issue:
        quality_status = "degraded"
    elif dropped_boundary_sessions:
        quality_status = "complete_after_boundary_drop"
    else:
        quality_status = "complete"
    quality_pass = quality_status in {"complete", "complete_after_boundary_drop"}

    sessions = []
    matched_set = set(matched)
    missing_interior_set = set(missing_interior)
    for session_day, session_slots in sorted(expected_by_day.items()):
        session_matched = session_slots.intersection(matched_set)
        sessions.append(
            {
                "session_date": session_day.isoformat(),
                "session_close": us_equity_session_close(session_day).isoformat(),
                "dropped_by_boundary_policy": session_day in dropped_boundary_sessions,
                "expected_bar_count": len(session_slots),
                "matched_bar_count": len(session_matched),
                "missing_interior_bar_count": len(session_slots.intersection(missing_interior_set)),
                "missing_boundary_bar_count": len(session_slots.intersection(missing_boundary)),
            }
        )

    return {
        "timestamp_label": "start",
        "timezone": str(NEW_YORK),
        "boundary_session_policy": "drop_partial_first_and_last",
        "timeframe_minutes": timeframe_minutes,
        "observed_bar_count": len(observed),
        "unique_timestamp_count": len(unique_observed),
        "expected_bar_count": expected_count,
        "interior_expected_bar_count": interior_expected_count,
        "matched_bar_count": len(matched),
        "duplicate_bar_count": duplicate_bar_count,
        "off_session_bar_count": off_session_bar_count,
        "off_grid_bar_count": off_grid_bar_count,
        "missing_bar_count": len(missing),
        "missing_interior_bar_count": len(missing_interior),
        "missing_boundary_bar_count": len(missing_boundary),
        "observed_session_count": len(
            {timestamp.tz_convert(NEW_YORK).date() for timestamp in matched}
        ),
        "expected_session_count": len(expected_by_day),
        "quality_session_count": len(
            {timestamp.tz_convert(NEW_YORK).date() for timestamp in interior_expected}
        ),
        "dropped_boundary_session_count": len(dropped_boundary_sessions),
        "dropped_boundary_sessions": [
            session_day.isoformat() for session_day in sorted(dropped_boundary_sessions)
        ],
        "grid_coverage_ratio": round(grid_coverage_ratio, 6),
        "interior_coverage_ratio": round(interior_coverage_ratio, 6),
        "interior_gap_rate": round(interior_gap_rate, 6),
        "quality_status": quality_status,
        "quality_pass": quality_pass,
        "aggregate_quality": {
            "status": quality_status,
            "pass": quality_pass,
            "boundary_session_policy": "drop_partial_first_and_last",
            "quality_session_count": len(
                {timestamp.tz_convert(NEW_YORK).date() for timestamp in interior_expected}
            ),
            "dropped_boundary_session_count": len(dropped_boundary_sessions),
            "duplicate_bar_count": duplicate_bar_count,
            "off_session_bar_count": off_session_bar_count,
            "off_grid_bar_count": off_grid_bar_count,
            "missing_interior_bar_count": len(missing_interior),
            "grid_coverage_ratio": round(grid_coverage_ratio, 6),
            "interior_coverage_ratio": round(interior_coverage_ratio, 6),
            "interior_gap_rate": round(interior_gap_rate, 6),
        },
        "duplicate_timestamps": _iso_timestamps(duplicate_timestamps),
        "off_session_timestamps": _iso_timestamps(off_session),
        "off_grid_timestamps": _iso_timestamps(off_grid),
        "missing_interior_timestamps": _iso_timestamps(missing_interior),
        "missing_boundary_timestamps": _iso_timestamps(missing_boundary),
        "sessions": sessions,
    }


def _empty_grid_result(timeframe_minutes: int) -> dict[str, Any]:
    return {
        "timestamp_label": "start",
        "timezone": str(NEW_YORK),
        "boundary_session_policy": "drop_partial_first_and_last",
        "timeframe_minutes": timeframe_minutes,
        "observed_bar_count": 0,
        "unique_timestamp_count": 0,
        "expected_bar_count": 0,
        "interior_expected_bar_count": 0,
        "matched_bar_count": 0,
        "duplicate_bar_count": 0,
        "off_session_bar_count": 0,
        "off_grid_bar_count": 0,
        "missing_bar_count": 0,
        "missing_interior_bar_count": 0,
        "missing_boundary_bar_count": 0,
        "observed_session_count": 0,
        "expected_session_count": 0,
        "quality_session_count": 0,
        "dropped_boundary_session_count": 0,
        "dropped_boundary_sessions": [],
        "grid_coverage_ratio": 0.0,
        "interior_coverage_ratio": 0.0,
        "interior_gap_rate": 0.0,
        "quality_status": "empty",
        "quality_pass": False,
        "aggregate_quality": {
            "status": "empty",
            "pass": False,
            "boundary_session_policy": "drop_partial_first_and_last",
            "quality_session_count": 0,
            "dropped_boundary_session_count": 0,
            "duplicate_bar_count": 0,
            "off_session_bar_count": 0,
            "off_grid_bar_count": 0,
            "missing_interior_bar_count": 0,
            "grid_coverage_ratio": 0.0,
            "interior_coverage_ratio": 0.0,
            "interior_gap_rate": 0.0,
        },
        "duplicate_timestamps": [],
        "off_session_timestamps": [],
        "off_grid_timestamps": [],
        "missing_interior_timestamps": [],
        "missing_boundary_timestamps": [],
        "sessions": [],
    }


def _coerce_timestamps(
    timestamps: Iterable[object] | pd.Series | pd.Index | pd.DataFrame,
) -> list[pd.Timestamp]:
    if isinstance(timestamps, pd.DataFrame):
        if "timestamp" not in timestamps.columns:
            raise ValueError("bar frame must contain a timestamp column")
        values = list(timestamps["timestamp"])
    else:
        values = list(timestamps)
    if not values:
        return []
    parsed = pd.to_datetime(values, utc=True, errors="raise")
    if pd.isna(parsed).any():
        raise ValueError("timestamps must not contain missing values")
    return [pd.Timestamp(timestamp) for timestamp in parsed]


def _is_in_us_equity_rth(timestamp: pd.Timestamp) -> bool:
    local = timestamp.tz_convert(NEW_YORK)
    close = us_equity_session_close(local.date())
    return close is not None and time(9, 30) <= local.time().replace(tzinfo=None) < close


def _iso_timestamps(timestamps: Iterable[pd.Timestamp]) -> list[str]:
    return [timestamp.isoformat() for timestamp in timestamps]


def _validate_timeframe_minutes(timeframe_minutes: int) -> None:
    if isinstance(timeframe_minutes, bool) or not isinstance(timeframe_minutes, int):
        raise ValueError("timeframe_minutes must be a positive integer")
    if timeframe_minutes <= 0:
        raise ValueError("timeframe_minutes must be a positive integer")


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
