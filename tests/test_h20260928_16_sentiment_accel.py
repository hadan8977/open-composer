"""Point-in-time join test for T-20260928-16's sent_accel feature build.

A score whose `visible_at` is after trading day t's 16:00 ET session-close
cutoff must not appear in the feature computed as of the close of day t.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

build = importlib.import_module("scripts.build_h20260928_16_sentiment_accel_feature")


def _trading_days(dates: list[str]) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") for d in dates])


def test_item_visible_after_session_close_attributed_to_next_day() -> None:
    trading_days = _trading_days(["2026-04-01", "2026-04-02", "2026-04-03"])
    # 2026-04-01 16:00 ET is 2026-04-01 20:00 UTC (EDT, UTC-4). An item
    # visible at 20:30 UTC (after the 16:00 ET close) must attribute to the
    # NEXT trading day (2026-04-02), not the same day.
    visible_at = pd.Series([pd.Timestamp("2026-04-01T20:30:00Z")])
    attributed = build.attribute_trading_day(visible_at, trading_days)
    assert attributed.iloc[0] == pd.Timestamp("2026-04-02")


def test_item_visible_before_session_close_attributed_to_same_day() -> None:
    trading_days = _trading_days(["2026-04-01", "2026-04-02", "2026-04-03"])
    # 2026-04-01 15:00 ET = 19:00 UTC, before the 16:00 ET close.
    visible_at = pd.Series([pd.Timestamp("2026-04-01T19:00:00Z")])
    attributed = build.attribute_trading_day(visible_at, trading_days)
    assert attributed.iloc[0] == pd.Timestamp("2026-04-01")


def test_feature_at_t_excludes_item_visible_after_t() -> None:
    """The decisive PIT check: build the daily raw_pol grid for two items --
    one visible on day 1 (before close), one visible on day 3 (after day 1's
    close) -- and confirm day 1's feature value does not include the item
    that only becomes visible on day 3."""
    trading_days = _trading_days(["2026-04-01", "2026-04-02", "2026-04-03"])
    tickers = ["AAPL"]
    items = pd.DataFrame(
        {
            "ticker": ["AAPL", "AAPL"],
            "polarity": [1.0, -1.0],
            "magnitude": [1.0, 1.0],
            # item A: visible well before day-1 close -> attributed to day 1
            "visible_at": pd.to_datetime(
                ["2026-04-01T14:00:00Z", "2026-04-03T14:00:00Z"], utc=True
            ),
        }
    )
    grid = build.build_daily_raw_pol(items, trading_days, tickers)
    day1 = pd.Timestamp("2026-04-01")
    day3 = pd.Timestamp("2026-04-03")
    # Day 1's feature must equal item A's raw_pol alone (+1.0*1.0 = 1.0), not
    # an average that includes item B's -1.0 (which would give 0.0).
    assert grid.loc[day1, "AAPL"] == 1.0
    # Item B only shows up once it is actually visible, on day 3.
    assert grid.loc[day3, "AAPL"] == -1.0


def test_coverage_mask_true_only_after_item_visible() -> None:
    trading_days = _trading_days(["2026-04-01", "2026-04-02", "2026-04-03"])
    tickers = ["AAPL", "MSFT"]
    items = pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "polarity": [0.5],
            "magnitude": [0.5],
            "visible_at": pd.to_datetime(["2026-04-03T14:00:00Z"], utc=True),
        }
    )
    coverage = build.build_coverage_mask(items, trading_days, tickers)
    day1 = pd.Timestamp("2026-04-01")
    day3 = pd.Timestamp("2026-04-03")
    assert coverage.loc[day1, "AAPL"] is False or coverage.loc[day1, "AAPL"] == False  # noqa: E712
    assert coverage.loc[day3, "AAPL"] == True  # noqa: E712
    assert coverage.loc[day3, "MSFT"] == False  # noqa: E712
