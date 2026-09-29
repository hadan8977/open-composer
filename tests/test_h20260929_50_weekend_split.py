from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_h20260929_50_weekend_split as m  # noqa: E402


def _bars(times: list[pd.Timestamp], opens: list[float], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"open_time_utc": times, "open": opens, "close": closes})


def test_window_ends_at_monday_midnight_utc_and_uses_no_later_bar() -> None:
    monday = date(2026, 3, 9)  # DST already in force in the US
    start, last_open, end = m.weekend_window(monday)
    assert end == pd.Timestamp("2026-03-09 00:00", tz="UTC")
    assert last_open == pd.Timestamp("2026-03-08 23:45", tz="UTC")
    assert start == pd.Timestamp("2026-03-06 21:00", tz="UTC")
    # a poisoned Monday 00:00 UTC bar (and later) must not change W
    t_start = start
    t_last = last_open
    good = _bars([t_start, t_last], [100.0, 0.0], [0.0, 90.0])
    poisoned = _bars(
        [t_start, t_last, end, end + timedelta(minutes=15)],
        [100.0, 0.0, 1.0, 1.0],
        [0.0, 90.0, 5000.0, 5000.0],
    )
    assert m.weekend_return(good, monday) == m.weekend_return(poisoned, monday)
    assert abs(m.weekend_return(good, monday) - (-0.10)) < 1e-12
    series = m.weekend_returns_series(poisoned, [monday])
    assert abs(series.iloc[0] - (-0.10)) < 1e-12


def test_window_start_handles_dst() -> None:
    # Friday 2026-03-13 is EDT (16:00 ET = 20:00 UTC); Friday 2026-03-06 is EST (21:00 UTC)
    assert m.weekend_window(date(2026, 3, 16))[0] == pd.Timestamp("2026-03-13 20:00", tz="UTC")
    assert m.weekend_window(date(2026, 3, 9))[0] == pd.Timestamp("2026-03-06 21:00", tz="UTC")


def test_missing_endpoint_gives_nan() -> None:
    monday = date(2026, 3, 9)
    start, _, _ = m.weekend_window(monday)
    bars = _bars([start], [100.0], [100.0])
    assert np.isnan(m.weekend_return(bars, monday))


def test_holiday_monday_rolls_to_next_trading_day_and_is_flagged() -> None:
    # 2026-09-07 (Monday) is Labor Day: no bar; week of 09-14 is normal.
    days = [
        date(2026, 9, 3),
        date(2026, 9, 4),
        date(2026, 9, 8),
        date(2026, 9, 9),
        date(2026, 9, 10),
        date(2026, 9, 11),
        date(2026, 9, 14),
        date(2026, 9, 15),
        date(2026, 9, 16),
    ]
    weeks = m.monday_samples(days)
    labor = weeks[weeks.calendar_monday == date(2026, 9, 7)].iloc[0]
    assert labor.target == date(2026, 9, 8)
    assert bool(labor.holiday_monday)
    assert labor.prev == date(2026, 9, 4)
    assert labor.next == date(2026, 9, 9)
    normal = weeks[weeks.calendar_monday == date(2026, 9, 14)].iloc[0]
    assert normal.target == date(2026, 9, 14)
    assert not bool(normal.holiday_monday)
    # W for the holiday week still ends at the calendar Monday 00:00 UTC
    assert m.weekend_window(labor.calendar_monday)[2] == pd.Timestamp("2026-09-07", tz="UTC")


def test_shuffle_is_reproducible_and_seed_sensitive() -> None:
    a = m.shuffle_indices(50)
    b = m.shuffle_indices(50)
    assert np.array_equal(a, b)
    assert a.shape == (m.N_SHUFFLES, 50)
    assert all(sorted(row) == list(range(50)) for row in a[:5])
    c = m.shuffle_indices(50, seed=1)
    assert not np.array_equal(a, c)


def test_welch_matches_scipy_and_perm_vectorization() -> None:
    from scipy import stats

    rng = np.random.default_rng(3)
    r = rng.normal(size=80)
    w = rng.normal(size=80)
    a = w < 0
    diff, t, na, nb = m.welch(r[a], r[~a])
    ref = stats.ttest_ind(r[a], r[~a], equal_var=False)
    assert abs(t - ref.statistic) < 1e-9
    assert na + nb == 80
    assert abs(diff - (r[a].mean() - r[~a].mean())) < 1e-12
    tp = m.welch_perms(r, np.stack([a, ~a]))
    assert abs(tp[0] - t) < 1e-9 and abs(tp[1] + t) < 1e-9


def test_placebo_percentile_of_planted_signal_is_high() -> None:
    rng = np.random.default_rng(11)
    w = rng.normal(size=400)
    r = np.where(w < 0, -30.0, 0.0) + rng.normal(scale=20.0, size=400)
    _, t, _, _ = m.welch(r[w < 0], r[w >= 0])
    stats_ = m.placebo_stats(w, r, 0.0, abs(t))
    assert stats_["placebo_share_below"] > 0.99
    assert abs(t) > stats_["placebo_p90_abs_t"]
