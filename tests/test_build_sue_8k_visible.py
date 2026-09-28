"""Tests for scripts/build_sue_8k_visible.py.

Synthetic data only -- no network, no real archive data. Covers the two
things T-20260928-14's reopen condition lives or dies on: the after-close
cutoff (an 8-K accepted after the 16:00 ET close is not usable until the
next session) and the nearest-preceding-8-K join (a sue_eps event is matched
to the closest 8-K/2.02 filing at or before its old filing-date visible_at,
within the lookback window, and dropped if none exists).
"""

from __future__ import annotations

import importlib
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

builder = importlib.import_module("scripts.build_sue_8k_visible")

ET = "America/New_York"


def _et(day: str, hhmm: str) -> pd.Timestamp:
    return pd.Timestamp(f"{day} {hhmm}:00", tz=ET).tz_convert("UTC")


# --------------------------------------------------------------- cutoff rule


def test_before_close_same_session():
    """Accepted at 10:00 ET on a trading day -> usable that same session."""
    ts = _et("2024-05-01", "10:00")
    assert builder.usable_session_for_acceptance(ts) == date(2024, 5, 1)


def test_after_close_next_session():
    """A surprise announced after close on day t is not in the signal until t+1."""
    ts = _et("2024-05-01", "20:00")
    assert builder.usable_session_for_acceptance(ts) == date(2024, 5, 2)


def test_exactly_at_close_same_session():
    """Right at the 16:00 close boundary counts as usable that session."""
    ts = _et("2024-05-01", "16:00")
    assert builder.usable_session_for_acceptance(ts) == date(2024, 5, 1)


def test_one_second_after_close_next_session():
    ts = pd.Timestamp("2024-05-01 16:00:01", tz=ET).tz_convert("UTC")
    assert builder.usable_session_for_acceptance(ts) == date(2024, 5, 2)


def test_weekend_rolls_to_monday():
    """Accepted Saturday -> usable the following Monday (a real trading day)."""
    ts = _et("2024-05-04", "09:00")  # Saturday
    assert builder.usable_session_for_acceptance(ts) == date(2024, 5, 6)  # Monday


def test_early_close_day_cutoff():
    """On a half-day (13:00 close, e.g. day before Independence Day), the
    cutoff is 13:00 not 16:00."""
    ts_before = _et("2024-07-03", "12:30")
    ts_after = _et("2024-07-03", "13:30")
    assert builder.usable_session_for_acceptance(ts_before) == date(2024, 7, 3)
    assert builder.usable_session_for_acceptance(ts_after) == date(2024, 7, 5)


# --------------------------------------------------------------- join logic


def test_join_matches_nearest_preceding_8k_within_window():
    left = pd.DataFrame(
        {
            "symbol": ["ABC"],
            "cik": [1],
            "trade_date": [pd.Timestamp("2024-05-20")],
            "sue_eps": [2.5],
        }
    )
    right = pd.DataFrame(
        {
            "cik": [1, 1],
            "usable_session": [pd.Timestamp("2024-05-01"), pd.Timestamp("2024-02-01")],
        }
    )
    out = builder.build_join(left, right)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["symbol"] == "ABC"
    assert row["trade_date"] == pd.Timestamp("2024-05-01")
    assert row["value"] == 2.5


def test_join_drops_row_with_no_match_in_window():
    left = pd.DataFrame(
        {
            "symbol": ["ABC"],
            "cik": [1],
            "trade_date": [pd.Timestamp("2024-05-20")],
            "sue_eps": [2.5],
        }
    )
    right = pd.DataFrame(
        {
            "cik": [1],
            "usable_session": [pd.Timestamp("2024-01-01")],  # 140 days before, outside 65d window
        }
    )
    out = builder.build_join(left, right)
    assert len(out) == 0


def test_join_drops_row_with_no_preceding_8k():
    """A right-table event only AFTER the left row's old visible_at must not match."""
    left = pd.DataFrame(
        {
            "symbol": ["ABC"],
            "cik": [1],
            "trade_date": [pd.Timestamp("2024-05-01")],
            "sue_eps": [2.5],
        }
    )
    right = pd.DataFrame(
        {
            "cik": [1],
            "usable_session": [pd.Timestamp("2024-05-10")],  # after, not before
        }
    )
    out = builder.build_join(left, right)
    assert len(out) == 0


def test_join_respects_cik_grouping():
    """A close-in-time 8-K for a DIFFERENT cik must not match."""
    left = pd.DataFrame(
        {
            "symbol": ["ABC"],
            "cik": [1],
            "trade_date": [pd.Timestamp("2024-05-20")],
            "sue_eps": [2.5],
        }
    )
    right = pd.DataFrame(
        {
            "cik": [2],
            "usable_session": [pd.Timestamp("2024-05-01")],
        }
    )
    out = builder.build_join(left, right)
    assert len(out) == 0
