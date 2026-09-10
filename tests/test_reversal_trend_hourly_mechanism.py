"""Tests for open_composer.research.regime.reversal_trend_hourly.

Plan: docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md
section 2 (A3). Pure synthetic fixtures -- no real market data, no ledger,
no gate contract. This is the exit-rule/portfolio-admission/cost/daily-P&L
mechanism only; the gate-contract wiring lives in
scripts/evaluate_reversal_trend_hourly.py and is exercised by actually
running that script, matching the convention already used for
scripts/build_hourly_bars.py in this same track.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.regime import reversal_trend_hourly as rth

#: 09:30-anchored bucket start offsets within a session, matching
#: open_composer.research.bars.hourly's 6x60min + 1x30min scheme -- test
#: bars must respect real 7-bars-per-day session structure so
#: daily_last_close/trade_daily_returns/build_portfolio's NY-calendar-date
#: grouping behaves the same way it will on real data, not as a coincidence
#: of a naive continuous hourly tick sequence (which would spill across
#: midnight UTC into the "wrong" NY date after only ~10-11 bars).
_SESSION_BUCKET_OFFSET_MINUTES = (0, 60, 120, 180, 240, 300, 360)


def _session_timestamps(n: int, *, start_date: str = "2024-01-02") -> list[pd.Timestamp]:
    timestamps: list[pd.Timestamp] = []
    day_index = 0
    while len(timestamps) < n:
        session_start = (
            pd.Timestamp(start_date, tz="America/New_York") + pd.Timedelta(days=day_index)
        ).normalize() + pd.Timedelta(hours=9, minutes=30)
        for offset in _SESSION_BUCKET_OFFSET_MINUTES:
            if len(timestamps) >= n:
                break
            timestamps.append((session_start + pd.Timedelta(minutes=offset)).tz_convert("UTC"))
        day_index += 1
    return timestamps


def _bars(
    n: int,
    *,
    start_date: str = "2024-01-02",
    close_path: list[float] | None = None,
    high_extra: float = 0.5,
    low_extra: float = 0.5,
    atr: float | list[float] = 1.0,
    adx: float | list[float] = 25.0,
    bull_at: list[int] | None = None,
    bear_at: list[int] | None = None,
    recl_at: list[int] | None = None,
) -> pd.DataFrame:
    """n hourly bars in proper 7-bars-per-session-day blocks starting
    `start_date`, close_path (default: flat at 100.0) drives
    open/high/low/close; f_bull/f_bear/f_recl are False everywhere except
    the given bar indices.
    """
    if close_path is None:
        close_path = [100.0] * n
    assert len(close_path) == n
    timestamps = _session_timestamps(n, start_date=start_date)
    open_ = [close_path[0]] + close_path[:-1]
    atr_arr = [atr] * n if isinstance(atr, (int, float)) else list(atr)
    adx_arr = [adx] * n if isinstance(adx, (int, float)) else list(adx)
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": [max(o, c) + high_extra for o, c in zip(open_, close_path, strict=True)],
            "low": [min(o, c) - low_extra for o, c in zip(open_, close_path, strict=True)],
            "close": close_path,
            "atr": atr_arr,
            "adx": adx_arr,
            "f_bull": False,
            "f_bear": False,
            "f_recl": False,
        }
    )
    for i in bull_at or []:
        frame.loc[i, "f_bull"] = True
    for i in bear_at or []:
        frame.loc[i, "f_bear"] = True
    for i in recl_at or []:
        frame.loc[i, "f_recl"] = True
    return frame


# ---------------------------------------------------------------------------
# generate_symbol_candidates
# ---------------------------------------------------------------------------


def test_time_stop_entry_and_exit_bars_and_prices() -> None:
    bars = _bars(20, bull_at=[2])
    candidates = rth.generate_symbol_candidates(
        "AAA", bars, holding_bars=3, exit_rule="time_stop", signal_set="bull_only"
    )
    assert len(candidates) == 1
    c = candidates[0]
    # signal at bar 2 -> entry fills at bar 3's open; holding 3 bars means
    # the last held bar is 3+3-1=5, exit fills at bar 6's open.
    assert c.entry_bar == 3
    assert c.exit_bar == 6
    assert c.exit_reason == "time_stop"
    assert c.entry_price == pytest.approx(bars["open"].iloc[3])
    assert c.exit_price == pytest.approx(bars["open"].iloc[6])
    assert c.adx_at_entry == pytest.approx(bars["adx"].iloc[2])


def test_non_pyramiding_skips_signal_while_hypothetically_open() -> None:
    # Second bull signal at bar 4 falls inside the first trade's holding
    # window (entry=3, exit=6) -- must be skipped for this symbol.
    bars = _bars(20, bull_at=[2, 4])
    candidates = rth.generate_symbol_candidates(
        "AAA", bars, holding_bars=3, exit_rule="time_stop", signal_set="bull_only"
    )
    assert len(candidates) == 1
    # A later signal, at bar 10 (after bar 6's exit), must produce a second trade.
    bars2 = _bars(20, bull_at=[2, 10])
    candidates2 = rth.generate_symbol_candidates(
        "AAA", bars2, holding_bars=3, exit_rule="time_stop", signal_set="bull_only"
    )
    assert len(candidates2) == 2


def test_time_stop_or_reverse_exits_early_on_bear_signal() -> None:
    bars = _bars(20, bull_at=[2], bear_at=[4])
    candidates = rth.generate_symbol_candidates(
        "AAA", bars, holding_bars=10, exit_rule="time_stop_or_reverse", signal_set="bull_only"
    )
    assert len(candidates) == 1
    c = candidates[0]
    assert c.entry_bar == 3
    assert c.exit_bar == 5  # bear signal decided at bar 4, filled at bar 5's open
    assert c.exit_reason == "reverse_signal"
    assert c.exit_price == pytest.approx(bars["open"].iloc[5])


def test_time_stop_or_reverse_falls_back_to_time_stop_without_a_reverse_signal() -> None:
    bars = _bars(20, bull_at=[2])
    candidates = rth.generate_symbol_candidates(
        "AAA", bars, holding_bars=3, exit_rule="time_stop_or_reverse", signal_set="bull_only"
    )
    assert len(candidates) == 1
    assert candidates[0].exit_reason == "time_stop"
    assert candidates[0].exit_bar == 6


def test_atr_trailing_stop_breach_exits_early() -> None:
    # Entry at bar 3, price 100 -> drops sharply so the 2xATR(=2.0) trailing
    # stop (anchored at the entry-bar close, 100) is breached.
    close_path = [100.0] * 3 + [100.0, 100.0, 100.0, 95.0] + [100.0] * 13
    bars = _bars(20, close_path=close_path, atr=1.0, bull_at=[2])
    # low at bar 6 (the 95.0 close bar) must actually breach 100 - 2*1.0 = 98.
    bars.loc[6, "low"] = 90.0
    candidates = rth.generate_symbol_candidates(
        "AAA", bars, holding_bars=10, exit_rule="atr_trailing_2x", signal_set="bull_only"
    )
    assert len(candidates) == 1
    c = candidates[0]
    assert c.exit_reason == "atr_trailing_stop"
    assert c.exit_bar == 6
    # stop level (98.0) is below that bar's open (100.0), so it fills at the
    # stop level, not a worse gapped-through price.
    assert c.exit_price == pytest.approx(98.0)


def test_atr_trailing_stop_fills_at_open_when_gapped_through() -> None:
    close_path = [100.0] * 6 + [80.0] + [100.0] * 13
    bars = _bars(20, close_path=close_path, atr=1.0, bull_at=[2])
    bars.loc[6, "open"] = 80.0  # gapped down through the stop level (98.0)
    bars.loc[6, "low"] = 78.0
    candidates = rth.generate_symbol_candidates(
        "AAA", bars, holding_bars=10, exit_rule="atr_trailing_2x", signal_set="bull_only"
    )
    assert len(candidates) == 1
    assert candidates[0].exit_price == pytest.approx(80.0)


def test_atr_trailing_stop_falls_back_to_time_stop_without_a_breach() -> None:
    bars = _bars(20, atr=1.0, bull_at=[2])  # flat prices, never breaches
    candidates = rth.generate_symbol_candidates(
        "AAA", bars, holding_bars=3, exit_rule="atr_trailing_2x", signal_set="bull_only"
    )
    assert len(candidates) == 1
    assert candidates[0].exit_reason == "time_stop"
    assert candidates[0].exit_bar == 6


def test_incomplete_trade_at_data_end_is_dropped() -> None:
    bars = _bars(10, bull_at=[8])  # entry would be bar 9 (the last bar) -> no exit fill possible
    candidates = rth.generate_symbol_candidates(
        "AAA", bars, holding_bars=3, exit_rule="time_stop", signal_set="bull_only"
    )
    assert candidates == []


def test_signal_set_bull_and_recl_includes_recl_only_bars() -> None:
    bars = _bars(20, recl_at=[5])
    bull_only = rth.generate_symbol_candidates(
        "AAA", bars, holding_bars=3, exit_rule="time_stop", signal_set="bull_only"
    )
    combined = rth.generate_symbol_candidates(
        "AAA", bars, holding_bars=3, exit_rule="time_stop", signal_set="bull_and_recl"
    )
    assert bull_only == []
    assert len(combined) == 1


def test_entry_mask_filters_out_signals_e_g_trend_gate() -> None:
    bars = _bars(20, bull_at=[2, 10])
    mask = np.ones(20, dtype=bool)
    mask[2] = False  # trend gate blocks the first signal
    candidates = rth.generate_symbol_candidates(
        "AAA",
        bars,
        holding_bars=3,
        exit_rule="time_stop",
        signal_set="bull_only",
        entry_mask=mask,
    )
    assert len(candidates) == 1
    assert candidates[0].entry_bar == 11


def test_missing_required_column_raises() -> None:
    bars = _bars(5).drop(columns=["adx"])
    with pytest.raises(ValueError, match="missing required columns"):
        rth.generate_symbol_candidates(
            "AAA", bars, holding_bars=3, exit_rule="time_stop", signal_set="bull_only"
        )


# ---------------------------------------------------------------------------
# random_signal_bar_indices (placebo)
# ---------------------------------------------------------------------------


def test_random_signal_bar_indices_respects_count_bounds_and_seed() -> None:
    rng1 = np.random.default_rng(42)
    result1 = rth.random_signal_bar_indices(100, 7, rng=rng1)
    assert len(result1) == 7
    assert result1.max() <= 98  # never the last bar (index 99)
    assert len(set(result1.tolist())) == 7  # distinct

    rng2 = np.random.default_rng(42)
    result2 = rth.random_signal_bar_indices(100, 7, rng=rng2)
    np.testing.assert_array_equal(result1, result2)


def test_random_signal_bar_indices_clamps_count_to_eligible_bars() -> None:
    rng = np.random.default_rng(1)
    result = rth.random_signal_bar_indices(3, 50, rng=rng)
    assert len(result) <= 2  # only bars 0,1 eligible (n_bars-1=2 excludes bar 2)


# ---------------------------------------------------------------------------
# admit_by_capacity
# ---------------------------------------------------------------------------


def _candidate(symbol, entry_time, exit_time, adx) -> rth.TradeCandidate:
    return rth.TradeCandidate(
        symbol=symbol,
        entry_bar=0,
        entry_time=pd.Timestamp(entry_time, tz="UTC"),
        entry_price=100.0,
        exit_bar=1,
        exit_time=pd.Timestamp(exit_time, tz="UTC"),
        exit_price=101.0,
        exit_reason="time_stop",
        adx_at_entry=adx,
    )


def test_admit_by_capacity_respects_max_positions_and_adx_priority() -> None:
    # 12 candidates all entering at the same bar, exiting later -- only 10
    # slots, so the 2 lowest-ADX ones must be rejected.
    candidates = [
        _candidate(f"S{i}", "2024-01-02 15:30", "2024-01-05 15:30", adx=float(i)) for i in range(12)
    ]
    admitted = rth.admit_by_capacity(candidates, max_positions=10)
    assert len(admitted) == 10
    admitted_symbols = {c.symbol for c in admitted}
    # symbols S0, S1 have the two lowest ADX values (0.0, 1.0) -> rejected.
    assert "S0" not in admitted_symbols
    assert "S1" not in admitted_symbols
    assert "S11" in admitted_symbols


def test_admit_by_capacity_frees_slot_for_same_bar_reentry() -> None:
    # 9 long-lived fillers occupy 9 of the 10 slots for the whole window;
    # F0 is the 10th, exiting at exactly the moment LATE tries to enter.
    # Without same-bar slot-freeing, all 10 slots would already be taken
    # (9 long fillers + F0) when LATE arrives and it would be rejected.
    long_fillers = [
        _candidate(f"F{i}", "2024-01-02 15:30", "2024-01-10 15:30", adx=50.0) for i in range(1, 10)
    ]
    short_filler = _candidate("F0", "2024-01-02 15:30", "2024-01-03 10:30", adx=50.0)
    late = _candidate("LATE", "2024-01-03 10:30", "2024-01-04 15:30", adx=1.0)
    admitted = rth.admit_by_capacity([*long_fillers, short_filler, late], max_positions=10)
    admitted_symbols = {c.symbol for c in admitted}
    assert admitted_symbols == {f"F{i}" for i in range(10)} | {"LATE"}


def test_admit_by_capacity_under_capacity_admits_everyone() -> None:
    candidates = [
        _candidate(f"S{i}", "2024-01-02 15:30", "2024-01-03 15:30", adx=float(i)) for i in range(5)
    ]
    admitted = rth.admit_by_capacity(candidates, max_positions=10)
    assert len(admitted) == 5


# ---------------------------------------------------------------------------
# cost / net_return / trades_with_cost
# ---------------------------------------------------------------------------


def test_cost_bps_for_symbol_etf_vs_stock() -> None:
    assert rth.cost_bps_for_symbol("SPY") == pytest.approx(rth.ETF_COST_BPS_PER_SIDE)
    assert rth.cost_bps_for_symbol("QQQ") == pytest.approx(rth.ETF_COST_BPS_PER_SIDE)
    assert rth.cost_bps_for_symbol("AAPL") == pytest.approx(rth.STOCK_COST_BPS_PER_SIDE)


def test_cost_bps_for_symbol_stress_multiplies() -> None:
    assert rth.cost_bps_for_symbol("AAPL", stress=True) == pytest.approx(
        rth.STOCK_COST_BPS_PER_SIDE * rth.STRESS_COST_MULTIPLIER
    )
    assert rth.cost_bps_for_symbol("SPY", stress=True) == pytest.approx(
        rth.ETF_COST_BPS_PER_SIDE * rth.STRESS_COST_MULTIPLIER
    )


def test_net_return_applies_round_trip_cost() -> None:
    # entry 100 -> pay 5bp more (100.05); exit 110 -> receive 5bp less
    # (109.945); net = 109.945/100.05 - 1.
    r = rth.net_return(100.0, 110.0, cost_bps_per_side=5.0)
    expected = (110.0 * (1 - 0.0005)) / (100.0 * (1 + 0.0005)) - 1.0
    assert r == pytest.approx(expected, rel=1e-12)


def test_net_return_zero_cost_is_plain_return() -> None:
    assert rth.net_return(100.0, 110.0, cost_bps_per_side=0.0) == pytest.approx(0.10)


def test_trades_with_cost_reuses_admission_for_both_variants() -> None:
    candidates = [_candidate("AAPL", "2024-01-02 15:30", "2024-01-03 15:30", adx=20.0)]
    base = rth.trades_with_cost(candidates, stress=False)
    stress = rth.trades_with_cost(candidates, stress=True)
    assert base[0].cost_bps_per_side == pytest.approx(rth.STOCK_COST_BPS_PER_SIDE)
    assert stress[0].cost_bps_per_side == pytest.approx(
        rth.STOCK_COST_BPS_PER_SIDE * rth.STRESS_COST_MULTIPLIER
    )
    assert stress[0].net_return < base[0].net_return  # higher cost, same gross move


# ---------------------------------------------------------------------------
# daily_last_close / trade_daily_returns
# ---------------------------------------------------------------------------


def test_daily_last_close_takes_last_hourly_bar_of_each_ny_day() -> None:
    bars = _bars(14, close_path=[float(i) for i in range(14)])  # 2 sessions of 7 bars
    daily = rth.daily_last_close(bars)
    assert len(daily) == 2
    assert list(daily.values) == [6.0, 13.0]  # last close of each 7-bar day


def _trade(symbol, entry_time, entry_price, exit_time, exit_price, net_return) -> rth.Trade:
    candidate = rth.TradeCandidate(
        symbol=symbol,
        entry_bar=0,
        entry_time=pd.Timestamp(entry_time, tz="UTC"),
        entry_price=entry_price,
        exit_bar=1,
        exit_time=pd.Timestamp(exit_time, tz="UTC"),
        exit_price=exit_price,
        exit_reason="time_stop",
        adx_at_entry=25.0,
    )
    return rth.Trade(candidate=candidate, cost_bps_per_side=5.0, net_return=net_return)


def test_trade_daily_returns_single_day_collapses_to_net_return() -> None:
    daily_close = rth.daily_last_close(_bars(7))  # one NY day, 7 bars
    trade = _trade("AAA", "2024-01-02 15:30", 100.0, "2024-01-02 18:30", 103.0, net_return=0.025)
    result = rth.trade_daily_returns(daily_close, trade)
    assert len(result) == 1
    assert result.iloc[0] == pytest.approx(0.025)


def test_trade_daily_returns_multi_day_compounds_exactly_to_net_return() -> None:
    bars = _bars(21, close_path=[100.0, 101.0, 102.0] * 7)  # 3 NY days, 7 bars each
    daily_close = rth.daily_last_close(bars)
    trade = _trade("AAA", "2024-01-02 15:30", 100.0, "2024-01-04 18:30", 108.0, net_return=0.075)
    result = rth.trade_daily_returns(daily_close, trade)
    assert len(result) == 3
    compounded = float((1.0 + result).prod() - 1.0)
    assert compounded == pytest.approx(0.075, rel=1e-9)


# ---------------------------------------------------------------------------
# build_portfolio
# ---------------------------------------------------------------------------


def test_build_portfolio_single_trade_weight_drift_matches_manual_calc() -> None:
    bars = _bars(21, close_path=[100.0, 101.0, 102.0] * 7)
    daily_close = rth.daily_last_close(bars)
    trade = _trade("AAA", "2024-01-02 15:30", 100.0, "2024-01-04 18:30", 110.0, net_return=0.10)
    calendar = daily_close.index
    result = rth.build_portfolio([trade], {"AAA": daily_close}, calendar, position_weight=0.10)
    # NAV starts at 1.0; day 1 allocates 0.10 to the position, which then
    # earns whatever fraction of the 10% total return accrues that day.
    # Total NAV after the trade fully exits must be 1.0 + 0.10*0.10 (10%
    # position, 10% total trade return, rest of book flat).
    assert result.daily_returns.index.equals(calendar)
    final_nav = float((1.0 + result.daily_returns).prod())
    assert final_nav == pytest.approx(1.0 + 0.10 * 0.10, rel=1e-9)
    assert list(result.invested_day) == [True, True, True]


def test_build_portfolio_flat_days_have_zero_return_and_not_invested() -> None:
    bars = _bars(35, close_path=[100.0] * 35)  # 5 NY days, no trades at all
    daily_close = rth.daily_last_close(bars)
    calendar = daily_close.index
    result = rth.build_portfolio([], {}, calendar, position_weight=0.10)
    assert len(result.daily_returns) == 5
    assert (result.daily_returns == 0.0).all()
    assert not result.invested_day.any()


def test_build_portfolio_two_sequential_trades_reuse_the_freed_dollar_amount() -> None:
    bars = _bars(35, close_path=[100.0] * 35)
    daily_close = rth.daily_last_close(bars)
    calendar = daily_close.index
    trade1 = _trade("AAA", "2024-01-02 15:30", 100.0, "2024-01-02 18:30", 110.0, net_return=0.10)
    trade2 = _trade("BBB", "2024-01-03 15:30", 100.0, "2024-01-03 18:30", 90.0, net_return=-0.10)
    result = rth.build_portfolio(
        [trade1, trade2], {"AAA": daily_close, "BBB": daily_close}, calendar, position_weight=0.10
    )
    final_nav = float((1.0 + result.daily_returns).prod())
    # trade1 grows NAV to 1 + 0.10*0.10 = 1.01 by end of day 1; trade2 is
    # sized off *that* day-start NAV (1.01), losing 10% of 0.101 = 0.0101.
    expected = (1.0 + 0.10 * 0.10) - 0.10 * (1.0 + 0.10 * 0.10) * 0.10
    assert final_nav == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# weekly_holding_period_net_returns / rebalances_with_change_per_year
# ---------------------------------------------------------------------------


def test_weekly_holding_period_net_returns_excludes_flat_weeks() -> None:
    index = pd.date_range("2024-01-01", periods=14, freq="D", tz="America/New_York")
    returns = pd.Series([0.0] * 14, index=index)
    invested = pd.Series([False] * 14, index=index)
    returns.iloc[0] = 0.01  # one invested day in week 1
    invested.iloc[0] = True
    result = rth.PortfolioResult(trades=[], daily_returns=returns, invested_day=invested)
    weekly = rth.weekly_holding_period_net_returns(result)
    assert len(weekly) == 1  # only the week with an invested day
    assert weekly[0] == pytest.approx(0.01)


def test_rebalances_with_change_per_year_counts_distinct_weeks() -> None:
    trade1 = _trade("AAA", "2024-01-02 15:30", 100.0, "2024-01-02 18:30", 101.0, 0.01)
    # entry and exit of trade2 both fall in the same ISO week as trade1 --
    # must count as the same one changed week, not two.
    trade2 = _trade("BBB", "2024-01-03 15:30", 100.0, "2024-01-04 18:30", 101.0, 0.01)
    # a trade in a different year
    trade3 = _trade("CCC", "2025-06-10 15:30", 100.0, "2025-06-10 18:30", 101.0, 0.01)
    counts = rth.rebalances_with_change_per_year([trade1, trade2, trade3])
    assert counts == {2024: 1, 2025: 1}
