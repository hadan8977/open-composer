"""Tests for open_composer.research.features.reversal_trend_daily.

Track P's own tests/test_reversal_trend_port.py already exhaustively covers
the state machine's branches (crossover/dwell/arm/expire/lock/cooldown) at
the ``_run_state_machine`` level and against real SPY data -- this file does
not re-derive that coverage. It tests what is unique to this module: the
derived columns this wrapper adds on top of ``compute_reversal_trend``
(macd_hist_slope, atr_ext_ema20, the ratio columns, and the "bars since last
True" counters, including that they reset at symbol boundaries), the exact
column list/dtype/continuous-vs-signal split the plan specifies, and the
DuckDB-backed build wrapper. The real-SPY-data test at the bottom is the one
genuine state-machine-branch check here: it cross-verifies this module's
rt_bull_signal/rt_recl_signal/rt_bear_signal/rt_recs_signal and
rt_bars_since_bull_or_recl columns against compute_reversal_trend's own
f_bull/f_recl/f_bear/f_recs output on a multi-year real price path that is
known (from Track P's own test) to pass through every branch at least once.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.adapters.data.sip_parquet import default_sip_root, load_sip_bars
from open_composer.research.features.reversal_trend_daily import (
    REVERSAL_TREND_COLUMNS,
    REVERSAL_TREND_CONTINUOUS_COLUMNS,
    REVERSAL_TREND_SIGNAL_COLUMNS,
    _bars_since_last_true,
    _bars_since_last_true_by_symbol,
    build_reversal_trend_features,
    compute_reversal_trend_daily,
)
from open_composer.research.pine_port.reversal_trend import compute_reversal_trend


def _synthetic_ohlcv(symbol: str, n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-04", periods=n)
    price = 50.0
    rows = []
    for date in dates:
        price *= 1.0 + rng.normal(0.0002, 0.02)
        rows.append(
            {
                "symbol": symbol,
                "trade_date": date,
                "open": price,
                "high": price * 1.012,
                "low": price * 0.988,
                "close": price,
                "volume": 500_000.0,
            }
        )
    return pd.DataFrame(rows)


def test_bars_since_last_true_matches_hand_traced_example() -> None:
    cond = np.array([False, False, True, False, False, True, True, False], dtype=bool)
    # idx:                0      1     2     3      4     5     6     7
    expected = [np.nan, np.nan, 0.0, 1.0, 2.0, 0.0, 0.0, 1.0]
    result = _bars_since_last_true(cond)
    np.testing.assert_allclose(result, expected, equal_nan=True)


def test_bars_since_last_true_by_symbol_resets_at_symbol_boundary() -> None:
    frame = pd.DataFrame({"symbol": ["AAA", "AAA", "AAA", "BBB", "BBB", "BBB"]})
    cond = pd.Series([False, True, False, False, False, True])
    result = _bars_since_last_true_by_symbol(frame, cond)
    # AAA: event at position 1 (local idx 1) -> [nan, 0, 1]
    # BBB: event at local idx 2 -> [nan, nan, 0], not "3 bars since AAA's event".
    expected = [np.nan, 0.0, 1.0, np.nan, np.nan, 0.0]
    np.testing.assert_allclose(result.to_numpy(), expected, equal_nan=True)


def test_column_list_dtype_and_signal_continuous_partition() -> None:
    bars = pd.concat(
        [_synthetic_ohlcv("AAA", 260, seed=1), _synthetic_ohlcv("BBB", 260, seed=2)],
        ignore_index=True,
    )
    result = compute_reversal_trend_daily(bars)

    assert list(result.columns) == ["symbol", "trade_date", *REVERSAL_TREND_COLUMNS]
    assert len(REVERSAL_TREND_COLUMNS) == 25
    for column in REVERSAL_TREND_COLUMNS:
        assert result[column].dtype == np.float32, column

    assert set(REVERSAL_TREND_SIGNAL_COLUMNS) == {
        "rt_bull_signal",
        "rt_recl_signal",
        "rt_bear_signal",
        "rt_recs_signal",
    }
    assert set(REVERSAL_TREND_CONTINUOUS_COLUMNS) | set(REVERSAL_TREND_SIGNAL_COLUMNS) == set(
        REVERSAL_TREND_COLUMNS
    )
    assert not set(REVERSAL_TREND_CONTINUOUS_COLUMNS) & set(REVERSAL_TREND_SIGNAL_COLUMNS)
    assert len(REVERSAL_TREND_CONTINUOUS_COLUMNS) == 21


def test_derived_ratios_and_slope_match_computed_frame_directly() -> None:
    bars = _synthetic_ohlcv("AAA", 260, seed=3)
    result = compute_reversal_trend_daily(bars)

    working = bars.copy()
    working["timestamp"] = working["trade_date"]
    computed = compute_reversal_trend(working)

    np.testing.assert_allclose(
        result["rt_close_over_ema20"].to_numpy(),
        (computed["close"] / computed["ema_fast"]).to_numpy(),
        rtol=1e-5,
    )
    np.testing.assert_allclose(
        result["rt_ema50_over_ema200"].to_numpy(),
        (computed["ema_mid"] / computed["ema_slow"]).to_numpy(),
        rtol=1e-5,
    )
    expected_slope = computed["macd_hist"].diff().to_numpy()
    np.testing.assert_allclose(
        result["rt_macd_hist_slope"].to_numpy(), expected_slope, rtol=1e-3, atol=1e-6
    )
    # bar 0's slope is undefined (diff() has no prior bar).
    assert np.isnan(result["rt_macd_hist_slope"].iloc[0])


def test_atr_ext_ema20_is_nan_not_inf_when_atr_is_zero() -> None:
    # A perfectly flat price series drives true range (and therefore ATR,
    # once warmed up) to exactly 0 -- rt_atr_ext_ema20 must come out NaN via
    # the atr > 0 guard, not +/-inf or a fabricated 0/0 division result.
    n = 60
    dates = pd.bdate_range("2021-01-04", periods=n)
    flat = pd.DataFrame(
        {
            "symbol": "FLAT",
            "trade_date": dates,
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "close": 10.0,
            "volume": 1_000.0,
        }
    )
    result = compute_reversal_trend_daily(flat)
    working = flat.copy()
    working["timestamp"] = working["trade_date"]
    atr = compute_reversal_trend(working)["atr"]
    assert (atr.iloc[20:] == 0.0).all(), "expected ATR to have converged to exactly 0"
    assert result["rt_atr_ext_ema20"].iloc[20:].isna().all()
    assert not np.isinf(result["rt_atr_ext_ema20"].to_numpy()).any()


def test_build_reversal_trend_features_end_to_end_from_parquet(tmp_path: Path) -> None:
    bars = pd.concat(
        [_synthetic_ohlcv("AAA", 260, seed=4), _synthetic_ohlcv("BBB", 260, seed=5)],
        ignore_index=True,
    )
    frame = bars.rename(columns={"trade_date": "timestamp"})
    path = tmp_path / "2021.parquet"
    frame.to_parquet(path, index=False)

    result = build_reversal_trend_features([str(path)], ["aaa", "bbb"], memory_limit="512MB")
    assert list(result.columns) == ["symbol", "trade_date", *REVERSAL_TREND_COLUMNS]
    assert set(result["symbol"].unique()) == {"AAA", "BBB"}
    assert len(result) == 520


def test_build_reversal_trend_features_empty_universe_returns_empty_typed_frame(
    tmp_path: Path,
) -> None:
    empty_glob = str(tmp_path / "*.parquet")
    result = build_reversal_trend_features(empty_glob, [])
    assert list(result.columns) == ["symbol", "trade_date", *REVERSAL_TREND_COLUMNS]
    assert len(result) == 0


@pytest.mark.skipif(
    not (default_sip_root() / "daily").is_dir(),
    reason="local SIP daily archive (data/sip/daily) is not present",
)
def test_real_spy_data_signal_and_bars_since_columns_match_compute_reversal_trend() -> None:
    """The one genuine state-machine-branch check in this file: on a real,
    multi-year price path that Track P's own test already established fires
    every one of the four signals at least once, this module's signal and
    bars-since-event columns must exactly reproduce compute_reversal_trend's
    own f_bull/f_recl/f_bear/f_recs, branch by branch (arm, fire, cooldown,
    re-fire), not just on average.
    """
    frame = load_sip_bars("SPY", frequency="daily", start="2018-01-01", end="2025-06-30")
    frame = frame.copy()
    frame["trade_date"] = pd.to_datetime(frame["timestamp"]).dt.tz_localize(None).dt.normalize()

    result = compute_reversal_trend_daily(frame)
    working = frame.copy()
    working["timestamp"] = working["trade_date"]
    computed = compute_reversal_trend(working)

    assert len(result) == len(computed)
    for signal_column, raw_column in (
        ("rt_bull_signal", "f_bull"),
        ("rt_recl_signal", "f_recl"),
        ("rt_bear_signal", "f_bear"),
        ("rt_recs_signal", "f_recs"),
    ):
        np.testing.assert_array_equal(
            result[signal_column].to_numpy(), computed[raw_column].to_numpy().astype(np.float32)
        )
        assert result[signal_column].sum() > 0, f"expected at least one {signal_column} event"

    bull_or_recl = (computed["f_bull"] | computed["f_recl"]).to_numpy()
    fire_positions = np.flatnonzero(bull_or_recl)
    assert len(fire_positions) > 1, "need at least two events to check both reset and increment"
    # On every fire bar, bars-since must be exactly 0; on the bar right after
    # a fire (as long as it's strictly before the *next* fire), it must be 1.
    bars_since = result["rt_bars_since_bull_or_recl"].to_numpy()
    assert (bars_since[fire_positions] == 0.0).all()
    for position in fire_positions:
        next_bar = position + 1
        if next_bar < len(bars_since) and not bull_or_recl[next_bar]:
            assert bars_since[next_bar] == 1.0
    assert np.isnan(bars_since[: fire_positions[0]]).all()
