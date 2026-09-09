"""F1 (Step 12 Group B): ETF pullback mean reversion.

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 2. ``run_state_machine`` and ``combine_slots`` are tested with
hand-built signal/return series (no OHLC data, no SMA200 warmup, every
expected number computed by hand in the test itself) since that is where
the entry/exit/cost/timing bookkeeping actually lives; ``compute_indicators``
and the "insufficient warmup" path of ``simulate_cell_portfolio`` are
covered with small synthetic OHLC frames. No real market data.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from open_composer.research.regime import etf_pullback_mean_reversion as f1


def _dates(n: int, start: str = "2024-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n, tz="UTC")


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------


def test_wilder_rsi_approaches_100_in_a_pure_uptrend() -> None:
    close = pd.Series(range(1, 21), index=_dates(20), dtype=float)  # strictly increasing
    rsi = f1._wilder_rsi(close, period=2)
    assert rsi.iloc[-1] == pytest.approx(100.0)


def test_wilder_rsi_approaches_0_in_a_pure_downtrend() -> None:
    close = pd.Series(range(20, 0, -1), index=_dates(20), dtype=float)
    rsi = f1._wilder_rsi(close, period=2)
    assert rsi.iloc[-1] == pytest.approx(0.0)


def test_wilder_rsi_is_50_when_perfectly_flat() -> None:
    close = pd.Series([100.0] * 10, index=_dates(10))
    rsi = f1._wilder_rsi(close, period=2)
    assert rsi.iloc[-1] == pytest.approx(50.0)


def test_wilder_atr_converges_to_a_constant_true_range() -> None:
    index = _dates(20)
    close = pd.Series([100.0] * 20, index=index)
    high = close + 1.0
    low = close - 1.0
    atr = f1._wilder_atr(high, low, close, period=14)
    assert atr.iloc[-1] == pytest.approx(2.0, rel=1e-6)


def test_compute_indicators_has_expected_keys_and_length() -> None:
    index = _dates(210)
    frame = pd.DataFrame(
        {
            "open": [100.0 + 0.1 * i for i in range(210)],
            "high": [100.5 + 0.1 * i for i in range(210)],
            "low": [99.5 + 0.1 * i for i in range(210)],
            "close": [100.0 + 0.1 * i for i in range(210)],
        },
        index=index,
    )
    ind = f1.compute_indicators(frame)
    assert set(ind) == {"open", "close", "sma200", "sma5", "rsi2", "atr14", "down_streak_3"}
    assert all(len(series) == 210 for series in ind.values())
    # A steady uptrend: SMA200 warms up by row 200 (0-indexed row 199) and
    # close stays above it (an uptrend's own SMA lags behind price).
    assert bool(frame["close"].iloc[-1] > ind["sma200"].iloc[-1])


# ---------------------------------------------------------------------------
# run_state_machine
# ---------------------------------------------------------------------------

_OPEN_PRICES = [100.0 + i for i in range(10)]  # 100..109, day-over-day +1


def _bool_series(index: pd.DatetimeIndex, true_at: list[int]) -> pd.Series:
    series = pd.Series(False, index=index)
    for i in true_at:
        series.iloc[i] = True
    return series


def test_state_machine_exit_signal_closes_the_trade_with_correct_pnl_and_cost() -> None:
    index = _dates(10)
    open_ = pd.Series(_OPEN_PRICES, index=index)
    entry_signal = _bool_series(index, [1])
    exit_signal = _bool_series(index, [3])
    equity_return, active, trades = f1.run_state_machine(
        "SYM", "cellX", open_, entry_signal, exit_signal, max_hold_days=10, cost_bps_per_side=10.0
    )
    cost_rate = 0.001
    # entry signal day 1 -> fill day 2; exit signal day 3 -> fill day 4.
    assert list(active) == [False, False, False, True, True, False, False, False, False, False]
    assert equity_return.iloc[2] == pytest.approx(-cost_rate)
    open_to_open_3 = _OPEN_PRICES[3] / _OPEN_PRICES[2] - 1.0
    open_to_open_4 = _OPEN_PRICES[4] / _OPEN_PRICES[3] - 1.0
    assert equity_return.iloc[3] == pytest.approx(open_to_open_3)
    assert equity_return.iloc[4] == pytest.approx(open_to_open_4 - cost_rate)
    assert equity_return.iloc[0] == 0.0
    assert equity_return.iloc[5] == 0.0
    assert len(trades) == 1
    trade = trades[0]
    assert trade.symbol == "SYM"
    assert trade.cell_id == "cellX"
    assert trade.entry_signal_date == index[1].date().isoformat()
    assert trade.entry_fill_date == index[2].date().isoformat()
    assert trade.exit_signal_date == index[3].date().isoformat()
    assert trade.exit_fill_date == index[4].date().isoformat()
    expected_trade_return = (_OPEN_PRICES[4] / _OPEN_PRICES[2] - 1.0) - 2.0 * cost_rate
    assert trade.net_return == pytest.approx(expected_trade_return)
    assert trade.forced_close_at_sample_end is False


def test_state_machine_max_hold_days_forces_an_earlier_exit_than_the_signal() -> None:
    index = _dates(10)
    open_ = pd.Series(_OPEN_PRICES, index=index)
    entry_signal = _bool_series(index, [1])
    exit_signal = _bool_series(index, [])  # exit signal never fires -- only the cap can end it
    equity_return, active, trades = f1.run_state_machine(
        "SYM", "cellX", open_, entry_signal, exit_signal, max_hold_days=1, cost_bps_per_side=10.0
    )
    # entry fill day 2; cap of 1 forces exit fill at day 3 (one day earlier
    # than the exit-signal-driven test above).
    assert list(active) == [False, False, False, True, False, False, False, False, False, False]
    assert len(trades) == 1
    assert trades[0].exit_fill_date == index[3].date().isoformat()
    cost_rate = 0.001
    expected_trade_return = (_OPEN_PRICES[3] / _OPEN_PRICES[2] - 1.0) - 2.0 * cost_rate
    assert trades[0].net_return == pytest.approx(expected_trade_return)


def test_state_machine_force_closes_an_open_position_at_sample_end() -> None:
    index = _dates(10)
    open_ = pd.Series(_OPEN_PRICES, index=index)
    entry_signal = _bool_series(index, [6])  # fills at day 7; never exits before data ends
    exit_signal = _bool_series(index, [])
    equity_return, active, trades = f1.run_state_machine(
        "SYM", "cellX", open_, entry_signal, exit_signal, max_hold_days=100, cost_bps_per_side=10.0
    )
    assert len(trades) == 1
    trade = trades[0]
    assert trade.forced_close_at_sample_end is True
    assert trade.entry_fill_date == index[7].date().isoformat()
    assert trade.exit_fill_date == index[9].date().isoformat()  # last available day
    assert bool(active.iloc[8]) and bool(active.iloc[9])


def test_state_machine_with_no_entry_signal_never_trades() -> None:
    index = _dates(10)
    open_ = pd.Series(_OPEN_PRICES, index=index)
    flat = _bool_series(index, [])
    equity_return, active, trades = f1.run_state_machine(
        "SYM", "cellX", open_, flat, flat, max_hold_days=5, cost_bps_per_side=10.0
    )
    assert trades == []
    assert not active.any()
    assert (equity_return == 0.0).all()


# ---------------------------------------------------------------------------
# combine_slots
# ---------------------------------------------------------------------------


def test_combine_slots_blends_active_equity_and_bil_by_fixed_slot_weight() -> None:
    index = _dates(4)
    equity_by_symbol = {
        "A": pd.Series([0.0, 0.05, 0.0, 0.0], index=index),
        "B": pd.Series([0.0, 0.0, 0.02, 0.0], index=index),
    }
    active_by_symbol = {
        "A": pd.Series([False, True, False, False], index=index),
        "B": pd.Series([False, False, True, False], index=index),
    }
    bil = pd.Series([0.001, 0.001, 0.001, 0.001], index=index)
    result = f1.combine_slots(equity_by_symbol, active_by_symbol, bil, n_slots=2.0)
    assert result.iloc[0] == pytest.approx(0.001)  # both slots in BIL
    assert result.iloc[1] == pytest.approx(0.05 / 2 + 0.5 * 0.001)  # A active, B in BIL
    assert result.iloc[2] == pytest.approx(0.02 / 2 + 0.5 * 0.001)  # B active, A in BIL
    assert result.iloc[3] == pytest.approx(0.001)  # both back in BIL


# ---------------------------------------------------------------------------
# simulate_cell_portfolio (integration, short series -> SMA200 never warms up)
# ---------------------------------------------------------------------------


def _ohlc_frame(index: pd.DatetimeIndex, base: float = 100.0) -> pd.DataFrame:
    close = pd.Series([base + 0.05 * i for i in range(len(index))], index=index)
    return pd.DataFrame(
        {"open": close, "high": close + 0.2, "low": close - 0.2, "close": close}, index=index
    )


def test_simulate_cell_portfolio_with_insufficient_warmup_is_pure_bil() -> None:
    index = _dates(10)
    bars = {"AAA": _ohlc_frame(index, 100.0), "BBB": _ohlc_frame(index, 50.0)}
    bil_frame = _ohlc_frame(index, 10.0)
    params = f1.PARAMETER_SPACE[0]
    portfolio_return, trades = f1.simulate_cell_portfolio(
        "cell000", bars, bil_frame, params, cost_bps_per_side=10.0
    )
    assert trades == []  # SMA200 needs 200 rows; with 10, close>SMA200 is never true
    expected = bil_frame["open"].pct_change().fillna(0.0)
    pd.testing.assert_series_equal(portfolio_return, expected, check_names=False)


# ---------------------------------------------------------------------------
# select_cells_by_quarter / materialize_composite
# ---------------------------------------------------------------------------


def test_select_cells_by_quarter_prefers_the_higher_trailing_sharpe_cell() -> None:
    index = pd.bdate_range("2016-01-04", "2019-06-28", tz="UTC")
    n = len(index)
    good = pd.Series([0.002 if i % 2 == 0 else -0.001 for i in range(n)], index=index)
    bad = pd.Series([-0.002 if i % 2 == 0 else 0.001 for i in range(n)], index=index)
    selections = f1.select_cells_by_quarter(
        {"good": good, "bad": bad},
        warmup_complete_date=pd.Timestamp("2016-06-01", tz="UTC"),
        lookback_months=24,
    )
    assert selections  # at least one eligible quarter
    assert all(selection.selected_cell == "good" for selection in selections)
    for selection in selections:
        lookback_start = pd.Timestamp(selection.quarter_start, tz="UTC") - pd.DateOffset(months=24)
        assert lookback_start >= pd.Timestamp("2016-06-01", tz="UTC")


def test_select_cells_by_quarter_returns_nothing_before_any_quarter_is_eligible() -> None:
    index = pd.bdate_range("2016-01-04", "2019-06-28", tz="UTC")
    flat = pd.Series(0.001, index=index)
    selections = f1.select_cells_by_quarter(
        {"only": flat},
        warmup_complete_date=index.max(),  # no lookback window can start this late
        lookback_months=24,
    )
    assert selections == []


def test_materialize_composite_stitches_selected_quarters_and_filters_trades() -> None:
    index = _dates(8)
    cell_returns = {
        "cellA": pd.Series([0.01] * 4 + [0.0] * 4, index=index),
        "cellB": pd.Series([0.0] * 4 + [0.02] * 4, index=index),
    }
    in_window_trade = f1.TradeRecord(
        symbol="X",
        cell_id="cellA",
        entry_signal_date=index[0].date().isoformat(),
        entry_fill_date=index[1].date().isoformat(),
        exit_signal_date=index[1].date().isoformat(),
        exit_fill_date=index[2].date().isoformat(),
        net_return=0.01,
    )
    out_of_window_trade = f1.TradeRecord(
        symbol="X",
        cell_id="cellA",
        entry_signal_date=index[5].date().isoformat(),
        entry_fill_date=index[6].date().isoformat(),
        exit_signal_date=index[6].date().isoformat(),
        exit_fill_date=index[6].date().isoformat(),
        net_return=0.02,
    )
    forced_close_trade = f1.TradeRecord(
        symbol="X",
        cell_id="cellA",
        entry_signal_date=index[0].date().isoformat(),
        entry_fill_date=index[1].date().isoformat(),
        exit_signal_date=index[3].date().isoformat(),
        exit_fill_date=index[3].date().isoformat(),
        net_return=-0.5,
        forced_close_at_sample_end=True,
    )
    cell_trades = {"cellA": [in_window_trade, out_of_window_trade, forced_close_trade], "cellB": []}
    selection_log = [
        f1.QuarterSelection(
            quarter_start=index[0].date().isoformat(),
            quarter_end=index[3].date().isoformat(),
            selected_cell="cellA",
            trailing_daily_sharpe=1.0,
        ),
        f1.QuarterSelection(
            quarter_start=index[4].date().isoformat(),
            quarter_end=index[7].date().isoformat(),
            selected_cell="cellB",
            trailing_daily_sharpe=2.0,
        ),
    ]
    composite, trades = f1.materialize_composite(cell_returns, cell_trades, selection_log)
    assert list(composite.loc[index[0] : index[3]]) == [0.01, 0.01, 0.01, 0.01]
    assert list(composite.loc[index[4] : index[7]]) == [0.02, 0.02, 0.02, 0.02]
    assert trades == [in_window_trade]  # excludes the out-of-window and forced-close trades


def test_parameter_space_has_twelve_preregistered_cells() -> None:
    assert len(f1.PARAMETER_SPACE) == 12
    assert len({f1.cell_id(i) for i in range(len(f1.PARAMETER_SPACE))}) == 12


def test_profit_factor_and_hit_rate_can_be_computed_from_trade_net_returns() -> None:
    # Sanity link to regime.metrics: TradeRecord.net_return is exactly the
    # per-holding-period figure hit_rate/profit_factor expect.
    from open_composer.research.regime import metrics as regime_metrics

    trades = [
        f1.TradeRecord("A", "c", "d0", "d1", "d1", "d2", net_return=0.02),
        f1.TradeRecord("A", "c", "d2", "d3", "d3", "d4", net_return=-0.01),
    ]
    returns = [t.net_return for t in trades]
    assert regime_metrics.hit_rate(returns) == pytest.approx(0.5)
    assert regime_metrics.profit_factor(returns) == pytest.approx(2.0)
    assert not math.isnan(regime_metrics.profit_factor(returns))


# ---------------------------------------------------------------------------
# load_common_bars / compute_warmup_complete_date
# ---------------------------------------------------------------------------


def test_load_common_bars_pivots_and_intersects_dates() -> None:
    # AAA trades 2024-01-02..01-05; BBB is missing 01-03 (e.g. a listing gap).
    raw_frame = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "timestamp": "2024-01-02",
                "open": 1,
                "high": 2,
                "low": 0,
                "close": 1,
            },
            {
                "symbol": "AAA",
                "timestamp": "2024-01-03",
                "open": 1,
                "high": 2,
                "low": 0,
                "close": 1,
            },
            {
                "symbol": "AAA",
                "timestamp": "2024-01-04",
                "open": 1,
                "high": 2,
                "low": 0,
                "close": 1,
            },
            {
                "symbol": "BBB",
                "timestamp": "2024-01-02",
                "open": 5,
                "high": 6,
                "low": 4,
                "close": 5,
            },
            {
                "symbol": "BBB",
                "timestamp": "2024-01-04",
                "open": 5,
                "high": 6,
                "low": 4,
                "close": 5,
            },
        ]
    )
    result = f1.load_common_bars(raw_frame, ["AAA", "BBB"])
    assert set(result) == {"AAA", "BBB"}
    expected_index = pd.DatetimeIndex(["2024-01-02", "2024-01-04"])
    for frame in result.values():
        assert list(frame.index) == list(expected_index)
        assert list(frame.columns) == ["open", "high", "low", "close"]


def test_load_common_bars_raises_when_no_overlap() -> None:
    raw_frame = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "timestamp": "2024-01-02",
                "open": 1,
                "high": 2,
                "low": 0,
                "close": 1,
            },
            {
                "symbol": "BBB",
                "timestamp": "2024-02-02",
                "open": 5,
                "high": 6,
                "low": 4,
                "close": 5,
            },
        ]
    )
    with pytest.raises(ValueError):
        f1.load_common_bars(raw_frame, ["AAA", "BBB"])


def test_compute_warmup_complete_date_takes_the_latest_symbol() -> None:
    short_index = _dates(199)
    long_index = _dates(300)
    bars = {
        "SHORT_WARMUP": _ohlc_frame(long_index, 10.0),  # 300 rows -> warms up early
        "LATE_WARMUP": _ohlc_frame(long_index, 20.0),
    }
    # Force LATE_WARMUP's SMA200 to be undefined until later by truncating
    # its own first-valid-index later than SHORT_WARMUP's: build it with an
    # extra 5-row-later start so its 200th valid close lands 5 rows later.
    bars["LATE_WARMUP"] = bars["LATE_WARMUP"].iloc[5:].reindex(long_index)
    warmup_date = f1.compute_warmup_complete_date(bars)
    assert warmup_date == long_index[204]
    assert len(short_index) == 199  # sanity: not itself used, just documents the 200-row need


def test_compute_warmup_complete_date_raises_with_insufficient_history() -> None:
    bars = {"TOO_SHORT": _ohlc_frame(_dates(50))}
    with pytest.raises(ValueError):
        f1.compute_warmup_complete_date(bars)
