from datetime import datetime

import pytest

from scripts.book_v12_cron_clock import due


@pytest.mark.parametrize(
    "stamp,mode,expected",
    [
        ("2026-10-30T18:30:00+00:00", "plan", True),
        ("2026-11-02T18:30:00+00:00", "plan", False),
        ("2026-11-02T19:30:00+00:00", "plan", True),
        ("2026-11-02T20:20:00+00:00", "submit", True),
        ("2026-11-02T19:20:00+00:00", "submit", False),
        ("2026-11-27T16:30:00+00:00", "plan", True),
        ("2026-11-27T17:20:00+00:00", "submit", True),
        ("2026-11-27T17:38:00+00:00", "retry", True),
        ("2026-11-27T20:20:00+00:00", "submit", False),
        ("2026-11-26T20:20:00+00:00", "submit", False),
        ("2026-11-01T19:30:00+00:00", "plan", False),
    ],
)
def test_clock_tracks_dst_early_closes_and_non_sessions(stamp, mode, expected):
    assert due(mode, datetime.fromisoformat(stamp)) is expected
