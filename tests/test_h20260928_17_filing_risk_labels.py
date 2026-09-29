"""Point-in-time join test for T-20260928-17's risk_score feature build.

A filing's score must only affect a forward return that starts strictly
after the filing became visible -- the entry day is the first trading day
AFTER the filing's attributed trading day, never the same day or earlier.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

build17 = importlib.import_module("scripts.build_h20260928_17_filing_risk_labels_feature")


def _trading_days(dates: list[str]) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") for d in dates])


def test_entry_day_is_strictly_after_attributed_day() -> None:
    trading_days = _trading_days(["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-06"])
    prices = pd.DataFrame(
        {
            "symbol": ["AAPL"] * 4,
            "timestamp": trading_days,
            "open": [10.0, 11.0, 12.0, 13.0],
            "close": [10.5, 11.5, 12.5, 13.5],
        }
    )
    panel = pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "quarter": ["2026Q2"],
            "risk_score": [0.7],
            # visible before 2026-04-01's 16:00 ET close -> attributed to 2026-04-01
            "visible_at": [pd.Timestamp("2026-04-01T14:00:00Z")],
        }
    )
    trading_days_by_ticker = {"AAPL": trading_days}
    # Use HORIZON=1 for this test via monkeypatch-free direct call: patch module HORIZON.
    original_horizon = build17.HORIZON
    build17.HORIZON = 1
    try:
        out = build17.attach_forward_return(panel, prices, trading_days_by_ticker)
    finally:
        build17.HORIZON = original_horizon
    assert len(out) == 1
    row = out.iloc[0]
    # attributed_day must be 2026-04-01 (visible before close); entry_day must
    # be the NEXT trading day (2026-04-02), never 2026-04-01 itself.
    assert row["attributed_day"] == pd.Timestamp("2026-04-01")
    assert row["entry_day"] == pd.Timestamp("2026-04-02")
    assert row["entry_day"] > row["attributed_day"]


def test_visible_after_close_pushes_entry_two_days_out() -> None:
    trading_days = _trading_days(["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-06"])
    prices = pd.DataFrame(
        {
            "symbol": ["AAPL"] * 4,
            "timestamp": trading_days,
            "open": [10.0, 11.0, 12.0, 13.0],
            "close": [10.5, 11.5, 12.5, 13.5],
        }
    )
    panel = pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "quarter": ["2026Q2"],
            "risk_score": [0.7],
            # visible AFTER 2026-04-01's 16:00 ET close -> attributed to 2026-04-02
            "visible_at": [pd.Timestamp("2026-04-01T21:00:00Z")],
        }
    )
    trading_days_by_ticker = {"AAPL": trading_days}
    original_horizon = build17.HORIZON
    build17.HORIZON = 1
    try:
        out = build17.attach_forward_return(panel, prices, trading_days_by_ticker)
    finally:
        build17.HORIZON = original_horizon
    assert len(out) == 1
    row = out.iloc[0]
    assert row["attributed_day"] == pd.Timestamp("2026-04-02")
    # entry must be the trading day AFTER 2026-04-02, i.e. 2026-04-03 -- not
    # 2026-04-02 itself, which is what a naive same-day attribution would give.
    assert row["entry_day"] == pd.Timestamp("2026-04-03")


def test_reduce_to_one_per_ticker_quarter_keeps_last() -> None:
    items = pd.DataFrame(
        {
            "ticker": ["AAPL", "AAPL"],
            "quarter": ["2026Q2", "2026Q2"],
            "risk_score": [0.2, 0.9],
            "acceptance_utc": pd.to_datetime(
                ["2026-04-05T12:00:00Z", "2026-06-20T12:00:00Z"], utc=True
            ),
            "visible_at": pd.to_datetime(
                ["2026-04-05T12:15:00Z", "2026-06-20T12:15:00Z"], utc=True
            ),
        }
    )
    reduced = build17.reduce_to_one_per_ticker_quarter(items)
    assert len(reduced) == 1
    assert reduced.iloc[0]["risk_score"] == 0.9
