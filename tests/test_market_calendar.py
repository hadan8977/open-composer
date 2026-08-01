from __future__ import annotations

from datetime import date

import pandas as pd

from open_composer.market_calendar import (
    expected_rth_bar_closes,
    expected_us_equity_rth_bar_starts,
    us_equity_session_close,
    validate_us_equity_bar_grid,
)


def test_us_equity_calendar_handles_holidays_early_close_and_dst() -> None:
    assert us_equity_session_close(date(2026, 7, 3)) is None
    assert us_equity_session_close(date(2025, 1, 9)) is None
    assert us_equity_session_close(date(2018, 12, 5)) is None
    assert us_equity_session_close(date(2021, 6, 18)) is not None
    assert us_equity_session_close(date(2022, 6, 20)) is None
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


def test_start_labelled_grid_handles_normal_early_close_and_holiday_sessions() -> None:
    assert len(expected_us_equity_rth_bar_starts(date(2026, 7, 2), 30)) == 13
    assert len(expected_us_equity_rth_bar_starts(date(2026, 11, 27), 30)) == 7
    assert expected_us_equity_rth_bar_starts(date(2026, 7, 3), 30) == set()

    winter = min(expected_us_equity_rth_bar_starts(date(2026, 1, 6), 30))
    summer = min(expected_us_equity_rth_bar_starts(date(2026, 7, 2), 30))
    assert winter == pd.Timestamp("2026-01-06T14:30:00Z")
    assert summer == pd.Timestamp("2026-07-02T13:30:00Z")


def test_validate_us_equity_bar_grid_classifies_quality_issues() -> None:
    expected = sorted(expected_us_equity_rth_bar_starts(date(2026, 7, 2), 30))
    missing = expected[2]
    result = validate_us_equity_bar_grid(
        [
            *[timestamp for timestamp in expected if timestamp != missing],
            "2026-07-02T12:00:00Z",  # Premarket.
            "2026-07-02T14:00:00Z",  # Duplicate.
            "2026-07-02T14:15:00Z",  # In-session but off the 30m grid.
        ],
        30,
    )

    assert result["timestamp_label"] == "start"
    assert result["matched_bar_count"] == 12
    assert result["duplicate_bar_count"] == 1
    assert result["off_session_bar_count"] == 1
    assert result["off_grid_bar_count"] == 1
    assert result["missing_interior_bar_count"] == 1
    assert result["interior_expected_bar_count"] == 13
    assert result["interior_gap_rate"] == round(1 / 13, 6)
    assert result["quality_status"] == "degraded"
    assert result["aggregate_quality"]["pass"] is False
    assert result["aggregate_quality"]["duplicate_bar_count"] == 1


def test_validate_us_equity_bar_grid_accepts_bar_frame() -> None:
    frame = pd.DataFrame({"timestamp": ["2026-07-02T13:30:00Z"]})

    result = validate_us_equity_bar_grid(frame, 30)

    assert result["matched_bar_count"] == 1
    assert result["timestamp_label"] == "start"


def test_validate_us_equity_bar_grid_drops_partial_boundary_sessions_explicitly() -> None:
    first = sorted(expected_us_equity_rth_bar_starts(date(2026, 1, 5), 30))
    middle = sorted(expected_us_equity_rth_bar_starts(date(2026, 1, 6), 30))
    last = sorted(expected_us_equity_rth_bar_starts(date(2026, 1, 7), 30))

    result = validate_us_equity_bar_grid([*first[2:], *middle, *last[:-2]], 30)

    assert result["boundary_session_policy"] == "drop_partial_first_and_last"
    assert result["dropped_boundary_sessions"] == ["2026-01-05", "2026-01-07"]
    assert result["dropped_boundary_session_count"] == 2
    assert result["quality_session_count"] == 1
    assert result["missing_boundary_bar_count"] == 4
    assert result["missing_interior_bar_count"] == 0
    assert result["quality_status"] == "complete_after_boundary_drop"
    assert result["quality_pass"] is True


def test_validate_us_equity_bar_grid_rejects_holiday_and_post_early_close_bars() -> None:
    result = validate_us_equity_bar_grid(
        [
            "2026-07-03T13:30:00Z",
            "2026-11-27T14:30:00Z",
            "2026-11-27T18:00:00Z",
        ],
        30,
    )

    assert result["off_session_bar_count"] == 2
    assert result["matched_bar_count"] == 1
    assert result["timestamp_label"] == "start"


def test_validate_us_equity_bar_grid_has_stable_empty_shape() -> None:
    result = validate_us_equity_bar_grid([], 15)

    assert result["timestamp_label"] == "start"
    assert result["timeframe_minutes"] == 15
    assert result["quality_status"] == "empty"
    assert result["boundary_session_policy"] == "drop_partial_first_and_last"
    assert result["missing_interior_timestamps"] == []
    assert result["sessions"] == []
