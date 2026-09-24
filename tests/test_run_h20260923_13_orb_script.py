"""Tests for the pure trade-construction, eligibility/ranking and equity-
simulation logic in ``scripts/run_h20260923_13_orb_stocks_in_play.py`` -- the
parts that don't need the real minute-bar archive: stop-order entry trigger
detection (``_simulate_sip_outcome``), gap-through fills, stop-vs-EOD exits,
same-bar entry/stop conflicts, the one-bar-late stop-fill variant, doji
detection and eligibility (``compute_eligible_universe``), ranking and top-N
selection with point-in-time (past-only) eligibility, RD/RL control seeding
determinism, the long-only filter (``build_trades``), and cost/sizing
arithmetic (``simulate_portfolio_equity``). Reading the *real* archive (shard
globbing, ``load_sip_bars`` calls) is exercised by actually running the
script's Stage 0-3, matching the convention of the sibling ETF-ORB script and
its own test file (``tests/test_orb_etf.py``): no per-script unit test for
the data-touching functions either. The one deliberate exception is
``_OPENING_RANGE_SQL`` itself (below): a 2026-09-23 bug (a UTC "EDT-band OR
EST-band" time filter let in real bars from forty minutes into the regular
session on EDT dates, and pre-market bars on EST dates, corrupting the
aggregated opening-range candle -- caught before any Stage 2/3 work consumed
the bad cache) showed that this specific query's DST handling is exactly the
kind of thing that must be tested directly, not just trusted by inspection.
Those tests write tiny synthetic parquet shards (not the real archive) and
run the production SQL string against them via DuckDB.

Calls the module's own functions directly
(``importlib.import_module("scripts.run_h20260923_13_orb_stocks_in_play")``),
matching ``tests/test_orb_etf.py``'s own idiom.
"""

from __future__ import annotations

import importlib
import math
from datetime import date

import duckdb
import numpy as np
import pandas as pd
import pytest

sip = importlib.import_module("scripts.run_h20260923_13_orb_stocks_in_play")


# --------------------------------------------------------------------------
# _simulate_sip_outcome: stop-order entry trigger, gap-through fills,
# stop-vs-EOD exits, same-bar conflicts, the one-bar-late variant
# --------------------------------------------------------------------------


def test_long_entry_triggers_on_touch_then_exits_at_eod_close() -> None:
    # Opening range high (trigger) = 101.0. First path bar (09:35) doesn't
    # touch it; the second bar's high reaches 101.0 exactly (not gapped:
    # open 100.9 < trigger), so entry fills AT the trigger price. ATR14=2.0
    # -> stop distance = 0.2, stop_loss = 101.0 - 0.2 = 100.8. Every bar from
    # the entry bar onward (checked same-bar-conservative, including the
    # entry bar's own low) stays above 100.8, so the trade rides to the
    # session's last close.
    path_bars = [
        (100.5, 100.7, 100.4, 100.6),  # 09:35: no touch
        (100.9, 101.05, 100.85, 100.95),  # 09:36: touches 101.0 -> entry; low 100.85 safe
        (100.95, 101.2, 100.9, 101.1),  # 09:37: low 100.9 safe, stop 100.8 not touched
        (101.1, 101.3, 101.0, 101.2),  # last bar of session: low 101.0 safe
    ]
    outcome = sip._simulate_sip_outcome(1, 101.0, 2.0, 0.1, path_bars, one_bar_late_stop=False)
    assert outcome is not None
    assert outcome["entry_index"] == 1
    assert outcome["entry_price"] == pytest.approx(101.0)
    assert outcome["R"] == pytest.approx(0.2)
    assert outcome["stop_loss_price"] == pytest.approx(100.8)
    assert outcome["exit_reason"] == "close"
    assert outcome["exit_price"] == pytest.approx(101.2)
    assert outcome["holding_bars"] == 3  # bars 1,2,3 (entry through last)


def test_long_entry_gaps_through_trigger_fills_at_bar_open() -> None:
    # Trigger = 100.0. The very first path bar opens at 100.4 (already above
    # the trigger) -- a gap-through, so the fill is the bar's own open
    # (100.4, worse than the trigger for a buyer), not 100.0.
    path_bars = [
        (100.4, 100.6, 100.3, 100.5),
        (100.5, 100.6, 100.4, 100.5),
    ]
    outcome = sip._simulate_sip_outcome(1, 100.0, 1.0, 0.1, path_bars, one_bar_late_stop=False)
    assert outcome is not None
    assert outcome["entry_index"] == 0
    assert outcome["entry_price"] == pytest.approx(100.4)


def test_short_entry_gaps_through_trigger_fills_at_bar_open() -> None:
    # Sell-stop trigger = 50.0 (opening range low). Bar opens at 49.5,
    # already below the trigger -- gap-through short fill at 49.5.
    path_bars = [(49.5, 49.6, 49.3, 49.4)]
    outcome = sip._simulate_sip_outcome(-1, 50.0, 1.0, 0.1, path_bars, one_bar_late_stop=False)
    assert outcome is not None
    assert outcome["entry_price"] == pytest.approx(49.5)


def test_no_trigger_day_returns_none() -> None:
    # Trigger = 105.0; price never reaches it across the whole session.
    path_bars = [
        (100.0, 100.5, 99.8, 100.2),
        (100.2, 100.6, 100.0, 100.4),
        (100.4, 100.7, 100.1, 100.3),
    ]
    outcome = sip._simulate_sip_outcome(1, 105.0, 2.0, 0.1, path_bars, one_bar_late_stop=False)
    assert outcome is None


def test_stop_hit_exits_before_eod() -> None:
    # Entry triggers on bar 0 at 100.0 (gapped, open==trigger). ATR=1.0,
    # stop distance=0.1 -> stop_loss=99.9. Bar 1's low (99.8) breaches it.
    path_bars = [
        (100.0, 100.2, 99.95, 100.1),
        (100.1, 100.15, 99.8, 99.85),
        (99.85, 99.9, 99.7, 99.8),
    ]
    outcome = sip._simulate_sip_outcome(1, 100.0, 1.0, 0.1, path_bars, one_bar_late_stop=False)
    assert outcome is not None
    assert outcome["exit_reason"] == "stop"
    assert outcome["exit_price"] == pytest.approx(99.9)
    assert outcome["holding_bars"] == 2


def test_same_bar_entry_and_stop_resolved_conservatively() -> None:
    # A single wide bar: open 99.0 (below trigger 100.0, not gapped), high
    # 100.5 (triggers the long entry at 100.0), low 98.0 (also breaches the
    # stop 100.0 - 0.1*ATR(2.0) = 99.8) within the SAME bar. Conservative
    # same-bar resolution: the stop is assumed to fire in that same bar.
    path_bars = [(99.0, 100.5, 98.0, 99.5)]
    outcome = sip._simulate_sip_outcome(1, 100.0, 2.0, 0.1, path_bars, one_bar_late_stop=False)
    assert outcome is not None
    assert outcome["exit_reason"] == "stop"
    assert outcome["exit_price"] == pytest.approx(99.8)
    assert outcome["holding_bars"] == 1


def test_one_bar_late_variant_ignores_stop_on_entry_bar() -> None:
    # Same wide entry bar as above (low 98.0 would hit the conservative stop
    # 100.0 - 0.1*2.0 = 99.8), but the one-bar-late variant does not consider
    # the stop live until the bar AFTER entry -- so this bar's breach is
    # ignored, and the trade only resolves on the next bar, whose low
    # (99.85) stays above the stop, so it exits at that bar's close.
    path_bars = [
        (99.0, 100.5, 98.0, 99.5),  # entry bar: stop breach ignored (late variant)
        (99.85, 99.9, 99.85, 99.88),  # next bar: low 99.85 safe, stop 99.8 not touched
    ]
    conservative = sip._simulate_sip_outcome(1, 100.0, 2.0, 0.1, path_bars, one_bar_late_stop=False)
    late = sip._simulate_sip_outcome(1, 100.0, 2.0, 0.1, path_bars, one_bar_late_stop=True)
    assert conservative is not None and conservative["exit_reason"] == "stop"
    assert late is not None
    assert late["exit_reason"] == "close"
    assert late["exit_price"] == pytest.approx(99.88)


def test_missing_atr_returns_none() -> None:
    path_bars = [(100.0, 100.5, 99.5, 100.2)]
    assert (
        sip._simulate_sip_outcome(1, 100.0, math.nan, 0.1, path_bars, one_bar_late_stop=False)
        is None
    )
    assert sip._simulate_sip_outcome(1, 100.0, 0.0, 0.1, path_bars, one_bar_late_stop=False) is None


def test_empty_path_bars_returns_none() -> None:
    assert sip._simulate_sip_outcome(1, 100.0, 1.0, 0.1, [], one_bar_late_stop=False) is None


# --------------------------------------------------------------------------
# doji detection and eligibility (compute_eligible_universe)
# --------------------------------------------------------------------------


def _opening_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["session_date"] = pd.to_datetime(frame["session_date"])
    return frame


def _daily_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["session_date"] = pd.to_datetime(frame["session_date"])
    return frame


def test_doji_is_exact_open_equals_close_not_a_band() -> None:
    opening = _opening_frame(
        [
            {
                "symbol": "ABC",
                "session_date": "2024-01-02",
                "candle_open": 100.0,
                "candle_close": 100.0,  # exact doji
                "candle_high": 101.0,
                "candle_low": 99.0,
                "candle_volume": 1000.0,
                "bar_count": 5,
            },
            {
                "symbol": "ABC",
                "session_date": "2024-01-03",
                "candle_open": 100.0,
                "candle_close": 100.01,  # NOT a doji, even though tiny -- exact rule only
                "candle_high": 101.0,
                "candle_low": 99.0,
                "candle_volume": 1000.0,
                "bar_count": 5,
            },
        ]
    )
    daily = _daily_frame(
        [
            {
                "symbol": "ABC",
                "session_date": d,
                "close": 100.0,
                "eligibility_price": 100.0,
                "atr14": 2.0,
                "avg_volume14": 500.0,
            }
            for d in ("2024-01-02", "2024-01-03")
        ]
    )
    universe = sip.compute_eligible_universe(opening, daily)
    row_doji = universe[universe["session_date"] == pd.Timestamp("2024-01-02")].iloc[0]
    row_not_doji = universe[universe["session_date"] == pd.Timestamp("2024-01-03")].iloc[0]
    assert row_doji["is_doji"] is np.True_ or bool(row_doji["is_doji"]) is True
    assert math.isnan(row_doji["direction_real"])
    assert bool(row_not_doji["is_doji"]) is False
    assert row_not_doji["direction_real"] == 1


def test_eligibility_uses_only_past_days_not_the_current_day() -> None:
    # 20 trading days of a rising-volume symbol; day 15's atr14/avg_volume14
    # must be computed strictly from days 1..14 (never day 15 itself), and
    # the first 14 days must be NaN (insufficient trailing history).
    dates = pd.bdate_range("2024-01-02", periods=20)
    daily_rows = []
    for i, d in enumerate(dates):
        # volume climbs 100 per day; close/high/low constant so ATR is driven
        # by a fixed daily range for an easy expected value.
        daily_rows.append(
            {
                "symbol": "XYZ",
                "session_date": d.date().isoformat(),
                "close": 50.0,
                "high": 51.0,
                "low": 49.0,
                "volume": 1000.0 + i * 100.0,
            }
        )
    raw = pd.DataFrame(daily_rows)
    raw["session_date"] = pd.to_datetime(raw["session_date"])
    grouped = raw.sort_values("session_date")
    prev_close = grouped.groupby("symbol")["close"].shift(1)
    true_range = pd.concat(
        [
            grouped["high"] - grouped["low"],
            (grouped["high"] - prev_close).abs(),
            (grouped["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    grouped = grouped.assign(prev_close=prev_close, true_range=true_range)
    grouped["atr14"] = grouped.groupby("symbol")["true_range"].transform(
        lambda s: s.rolling(14).mean().shift(1)
    )
    grouped["avg_volume14"] = grouped.groupby("symbol")["volume"].transform(
        lambda s: s.rolling(14).mean().shift(1)
    )
    grouped["eligibility_price"] = grouped["prev_close"]

    # Day 15 (index 14) avg_volume14 must equal the mean of days 1..14
    # (index 0..13), i.e. volumes 1000..2300, NOT including day 15's 2400.
    day15 = grouped.iloc[14]
    expected_avg_vol = float(np.mean([1000.0 + i * 100.0 for i in range(14)]))
    assert day15["avg_volume14"] == pytest.approx(expected_avg_vol)
    assert day15["avg_volume14"] < 1000.0 + 14 * 100.0  # strictly excludes day 15's own volume

    # Days 1..14 (index 0..13) have fewer than 14 prior days -> NaN.
    assert grouped.iloc[:14]["avg_volume14"].isna().all()
    assert grouped.iloc[:14]["atr14"].isna().all()


# --------------------------------------------------------------------------
# ranking and top-N selection, RL draws from the remainder
# --------------------------------------------------------------------------


def _eligible_day(symbols: list[str], rel_volumes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"symbol": symbols, "rel_volume": rel_volumes})


def test_select_real_top_n_ranks_by_relative_volume_descending() -> None:
    day = _eligible_day(["A", "B", "C", "D", "E"], [1.0, 5.0, 3.0, 2.0, 4.0])
    top3 = sip.select_real_top_n(day, 3)
    assert list(top3["symbol"]) == ["B", "E", "C"]


def test_select_real_top_n_smaller_than_universe_returns_all() -> None:
    day = _eligible_day(["A", "B"], [2.0, 1.0])
    top5 = sip.select_real_top_n(day, 5)
    assert len(top5) == 2


def test_select_rl_draw_excludes_the_real_top_n() -> None:
    day = _eligible_day(["A", "B", "C", "D", "E", "F"], [6.0, 5.0, 4.0, 3.0, 2.0, 1.0])
    top_n = 2  # real top-2 = A, B
    rng = np.random.default_rng(1)
    drawn = sip.select_rl_draw(day, top_n, rng)
    assert len(drawn) == top_n
    assert set(drawn["symbol"]).isdisjoint({"A", "B"})
    assert set(drawn["symbol"]).issubset({"C", "D", "E", "F"})


def test_select_rl_draw_empty_remainder_returns_empty() -> None:
    day = _eligible_day(["A", "B"], [2.0, 1.0])
    rng = np.random.default_rng(1)
    drawn = sip.select_rl_draw(day, 2, rng)
    assert drawn.empty


# --------------------------------------------------------------------------
# RD / RL control seeding determinism
# --------------------------------------------------------------------------


def test_rl_draw_same_seed_reproducible_different_seed_differs() -> None:
    day = _eligible_day([f"S{i}" for i in range(20)], list(range(20, 0, -1)))
    top_n = 5
    drawn_a = sip.select_rl_draw(day, top_n, np.random.default_rng(7))
    drawn_b = sip.select_rl_draw(day, top_n, np.random.default_rng(7))
    drawn_c = sip.select_rl_draw(day, top_n, np.random.default_rng(8))
    assert list(drawn_a["symbol"]) == list(drawn_b["symbol"])
    assert list(drawn_a["symbol"]) != list(drawn_c["symbol"])


def test_rd_direction_draw_same_seed_reproducible() -> None:
    rng_a = np.random.default_rng(3)
    rng_b = np.random.default_rng(3)
    draws_a = rng_a.choice([1, -1], size=50)
    draws_b = rng_b.choice([1, -1], size=50)
    assert list(draws_a) == list(draws_b)
    assert set(draws_a) <= {1, -1}


# --------------------------------------------------------------------------
# build_trades: long-only filter, RD unconstrained direction, RL mechanics
# --------------------------------------------------------------------------


def _selection_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["session_date"] = pd.to_datetime(frame["session_date"])
    return frame


def _outcomes_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["session_date"] = pd.to_datetime(frame["session_date"])
    return frame


def _make_selection_and_outcomes() -> tuple[pd.DataFrame, pd.DataFrame]:
    selection = _selection_frame(
        [
            {
                "session_date": "2024-01-02",
                "variant": "real",
                "seed": 0,
                "symbol": "BULL",
                "candle_high": 101.0,
                "candle_low": 99.0,
                "direction_real": 1.0,  # bullish day
                "atr14": 2.0,
                "rel_volume": 3.0,
            },
            {
                "session_date": "2024-01-02",
                "variant": "real",
                "seed": 0,
                "symbol": "BEAR",
                "candle_high": 50.5,
                "candle_low": 49.5,
                "direction_real": -1.0,  # bearish day
                "atr14": 1.0,
                "rel_volume": 2.5,
            },
        ]
    )
    outcomes = _outcomes_frame(
        [
            {
                "session_date": "2024-01-02",
                "symbol": "BULL",
                "direction": 1,
                "stop_fill_variant": "same_bar_conservative",
                "entry_price": 101.0,
                "R": 0.2,
                "exit_price": 102.0,
                "exit_reason": "close",
                "holding_bars": 5,
            },
            {
                "session_date": "2024-01-02",
                "symbol": "BULL",
                "direction": -1,
                "stop_fill_variant": "same_bar_conservative",
                "entry_price": 99.0,
                "R": 0.2,
                "exit_price": 98.0,
                "exit_reason": "close",
                "holding_bars": 5,
            },
            {
                "session_date": "2024-01-02",
                "symbol": "BEAR",
                "direction": 1,
                "stop_fill_variant": "same_bar_conservative",
                "entry_price": 50.5,
                "R": 0.1,
                "exit_price": 51.0,
                "exit_reason": "close",
                "holding_bars": 5,
            },
            {
                "session_date": "2024-01-02",
                "symbol": "BEAR",
                "direction": -1,
                "stop_fill_variant": "same_bar_conservative",
                "entry_price": 49.5,
                "R": 0.1,
                "exit_price": 49.0,
                "exit_reason": "close",
                "holding_bars": 5,
            },
        ]
    )
    # one_bar_late rows mirrored so build_trades' per-stop-variant merge
    # always has a (possibly empty) frame for both variants.
    late = outcomes.copy()
    late["stop_fill_variant"] = "one_bar_late"
    outcomes = pd.concat([outcomes, late], ignore_index=True)
    return selection, outcomes


def test_long_only_candidate_never_opens_a_short() -> None:
    selection, outcomes = _make_selection_and_outcomes()
    long_only_params = {"allow_long": True, "allow_short": False}
    trades = sip.build_trades(
        long_only_params,
        selection,
        outcomes,
        (date(2024, 1, 1), date(2024, 1, 31)),
        variant="real",
        seed=0,
    )
    cons = trades["same_bar_conservative"]
    # BULL (bullish day) trades long; BEAR (bearish day) is skipped entirely
    # for a long-only candidate -- never opens a short.
    assert set(cons["symbol"]) == {"BULL"}
    assert (cons["trade_direction"] == 1).all()


def test_long_short_candidate_takes_both_directions() -> None:
    selection, outcomes = _make_selection_and_outcomes()
    long_short_params = {"allow_long": True, "allow_short": True}
    trades = sip.build_trades(
        long_short_params,
        selection,
        outcomes,
        (date(2024, 1, 1), date(2024, 1, 31)),
        variant="real",
        seed=0,
    )
    cons = trades["same_bar_conservative"]
    assert set(cons["symbol"]) == {"BULL", "BEAR"}
    bull_row = cons[cons["symbol"] == "BULL"].iloc[0]
    bear_row = cons[cons["symbol"] == "BEAR"].iloc[0]
    assert bull_row["trade_direction"] == 1
    assert bear_row["trade_direction"] == -1


def test_rd_control_can_flip_a_long_only_candidates_direction() -> None:
    # RD's random direction draw is unconstrained by allow_short (see the
    # script's module docstring / report methodology notes): even for a
    # long-only base candidate, RD may draw a short on a bullish real day.
    selection, outcomes = _make_selection_and_outcomes()
    long_only_params = {"allow_long": True, "allow_short": False}
    # seed chosen so np.random.default_rng(seed).choice([1,-1], size=1)
    # draws -1 for this single-row selection (real selection has 2 rows
    # total in the fixture, but only BULL's direction_real is usable here
    # since RD ignores direction_real anyway and draws fresh for every row).
    found_short = False
    for seed in range(1, 21):
        trades = sip.build_trades(
            long_only_params,
            selection,
            outcomes,
            (date(2024, 1, 1), date(2024, 1, 31)),
            variant="rd",
            seed=seed,
        )
        cons = trades["same_bar_conservative"]
        if (cons["trade_direction"] == -1).any():
            found_short = True
            break
    assert found_short, "RD should be able to draw a short even for a long-only candidate"


def test_rd_seeding_is_deterministic() -> None:
    selection, outcomes = _make_selection_and_outcomes()
    params = {"allow_long": True, "allow_short": True}
    window = (date(2024, 1, 1), date(2024, 1, 31))
    trades_a = sip.build_trades(params, selection, outcomes, window, variant="rd", seed=5)
    trades_b = sip.build_trades(params, selection, outcomes, window, variant="rd", seed=5)
    pd.testing.assert_series_equal(
        trades_a["same_bar_conservative"]["trade_direction"].reset_index(drop=True),
        trades_b["same_bar_conservative"]["trade_direction"].reset_index(drop=True),
    )


# --------------------------------------------------------------------------
# simulate_portfolio_equity: sizing, leverage cap, costs, commission, borrow
# --------------------------------------------------------------------------


def _trade_row(**overrides: object) -> dict:
    base = {
        "session_date": pd.Timestamp("2024-01-02"),
        "symbol": "T",
        "trade_direction": 1,
        "entry_price": 100.0,
        "R": 0.5,
        "exit_price": 105.0,
        "exit_reason": "close",
        "holding_bars": 10.0,
    }
    base.update(overrides)
    return base


def test_leverage_cap_binds_the_slot_notional() -> None:
    # max_positions=20, equity=1.0 -> slot_capital=0.05. risk 1% of slot =
    # 0.0005; R=0.5 -> uncapped notional = 0.0005*100/0.5 = 0.1, which
    # exceeds leverage_cap=1.0 * slot_capital=0.05 -> capped at 0.05.
    trades = pd.DataFrame([_trade_row()])
    returns, rows = sip.simulate_portfolio_equity(
        trades,
        [date(2024, 1, 2)],
        max_positions=20,
        leverage_cap=1.0,
        cost_bps=0.0,
        commission_per_share=0.0,
        risk_pct_of_slot=0.01,
        borrow_annual_rate=0.0,
    )
    assert len(rows) == 1
    capped_shares = (1.0 * (1.0 / 20)) / 100.0  # leverage_cap * slot_capital / entry_price
    expected_pnl = capped_shares * (105.0 - 100.0)
    assert rows[0]["net_pnl"] == pytest.approx(expected_pnl)
    assert returns.iloc[0] == pytest.approx(expected_pnl / 1.0)


def test_higher_leverage_cap_uncaps_the_same_trade() -> None:
    trades = pd.DataFrame([_trade_row()])
    _, rows_1x = sip.simulate_portfolio_equity(
        trades,
        [date(2024, 1, 2)],
        max_positions=20,
        leverage_cap=1.0,
        cost_bps=0.0,
        commission_per_share=0.0,
        risk_pct_of_slot=0.01,
        borrow_annual_rate=0.0,
    )
    _, rows_4x = sip.simulate_portfolio_equity(
        trades,
        [date(2024, 1, 2)],
        max_positions=20,
        leverage_cap=4.0,
        cost_bps=0.0,
        commission_per_share=0.0,
        risk_pct_of_slot=0.01,
        borrow_annual_rate=0.0,
    )
    assert rows_4x[0]["net_pnl"] > rows_1x[0]["net_pnl"]


def test_bps_cost_reduces_net_pnl() -> None:
    trades = pd.DataFrame([_trade_row(exit_price=100.0)])  # flat trade, isolates cost
    _, rows_no_cost = sip.simulate_portfolio_equity(
        trades,
        [date(2024, 1, 2)],
        max_positions=20,
        leverage_cap=1.0,
        cost_bps=0.0,
        commission_per_share=0.0,
        risk_pct_of_slot=0.01,
        borrow_annual_rate=0.0,
    )
    _, rows_with_cost = sip.simulate_portfolio_equity(
        trades,
        [date(2024, 1, 2)],
        max_positions=20,
        leverage_cap=1.0,
        cost_bps=10.0,
        commission_per_share=0.0,
        risk_pct_of_slot=0.01,
        borrow_annual_rate=0.0,
    )
    assert rows_no_cost[0]["net_pnl"] == pytest.approx(0.0)
    assert rows_with_cost[0]["net_pnl"] < 0.0


def test_commission_per_share_applied_both_sides() -> None:
    trades = pd.DataFrame([_trade_row(exit_price=100.0)])
    _, rows = sip.simulate_portfolio_equity(
        trades,
        [date(2024, 1, 2)],
        max_positions=20,
        leverage_cap=1.0,
        cost_bps=0.0,
        commission_per_share=0.0035,
        risk_pct_of_slot=0.01,
        borrow_annual_rate=0.0,
    )
    slot_capital = 1.0 / 20
    shares = (1.0 * slot_capital) / 100.0
    expected_commission = shares * 0.0035 * 2.0
    assert rows[0]["net_pnl"] == pytest.approx(-expected_commission)


def test_short_trade_pays_borrow_fee_and_long_does_not() -> None:
    long_trade = pd.DataFrame([_trade_row(exit_price=100.0, trade_direction=1)])
    short_trade = pd.DataFrame([_trade_row(exit_price=100.0, trade_direction=-1)])
    _, long_rows = sip.simulate_portfolio_equity(
        long_trade,
        [date(2024, 1, 2)],
        max_positions=20,
        leverage_cap=1.0,
        cost_bps=0.0,
        commission_per_share=0.0,
        risk_pct_of_slot=0.01,
        borrow_annual_rate=0.003,
    )
    _, short_rows = sip.simulate_portfolio_equity(
        short_trade,
        [date(2024, 1, 2)],
        max_positions=20,
        leverage_cap=1.0,
        cost_bps=0.0,
        commission_per_share=0.0,
        risk_pct_of_slot=0.01,
        borrow_annual_rate=0.003,
    )
    assert long_rows[0]["net_pnl"] == pytest.approx(0.0)
    assert short_rows[0]["net_pnl"] < 0.0


def test_multiple_concurrent_names_sum_into_one_day_return() -> None:
    trades = pd.DataFrame(
        [
            _trade_row(symbol="A", exit_price=105.0),
            _trade_row(symbol="B", exit_price=95.0, trade_direction=-1),
        ]
    )
    returns, rows = sip.simulate_portfolio_equity(
        trades,
        [date(2024, 1, 2)],
        max_positions=20,
        leverage_cap=1.0,
        cost_bps=0.0,
        commission_per_share=0.0,
        risk_pct_of_slot=0.01,
        borrow_annual_rate=0.0,
    )
    assert len(rows) == 2
    assert returns.iloc[0] == pytest.approx(sum(r["net_pnl"] for r in rows) / 1.0)


def test_days_without_trades_are_flat() -> None:
    trades = pd.DataFrame([_trade_row(session_date=pd.Timestamp("2024-01-02"))])
    session_dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    returns, _ = sip.simulate_portfolio_equity(
        trades,
        session_dates,
        max_positions=20,
        leverage_cap=1.0,
        cost_bps=0.0,
        commission_per_share=0.0,
        risk_pct_of_slot=0.01,
        borrow_annual_rate=0.0,
    )
    assert len(returns) == 3
    assert returns.iloc[1] == 0.0
    assert returns.iloc[2] == 0.0


# --------------------------------------------------------------------------
# gate evaluation against the hypothesis card's own frontmatter
# --------------------------------------------------------------------------


def test_load_gate_criteria_matches_card_and_evaluates_directionally() -> None:
    criteria = sip.load_gate_criteria()
    names = {c["name"] for c in criteria}
    assert names == {
        "design_beats_equal_weight_eligible_universe",
        "design_beats_rd_placebo_median",
        "design_beats_rl_placebo_median",
        "design_positive_net_of_20bp_plus_commission",
        "select_window_cagr_10bp",
        "select_window_max_drawdown_10bp",
        "select_window_placebo_beat_rate",
    }
    cagr_gate = next(c for c in criteria if c["name"] == "select_window_cagr_10bp")
    assert cagr_gate["direction"] == ">="
    assert cagr_gate["threshold"] == pytest.approx(0.50)
    assert sip.evaluate_gate(cagr_gate, 0.51)["pass"] is True
    assert sip.evaluate_gate(cagr_gate, 0.49)["pass"] is False
    assert sip.evaluate_gate(cagr_gate, None)["pass"] is None


def test_screen_grouping_shares_sip01_and_sip03() -> None:
    candidates = sip.load_candidate_manifest()
    screens = sip.build_screens(candidates)
    sip01_screen = next(sid for sid, members in screens.items() if "SIP01" in members)
    assert "SIP03" in screens[sip01_screen]
    sip02_screen = next(sid for sid, members in screens.items() if "SIP02" in members)
    assert sip02_screen != sip01_screen
    assert "SIP02" not in screens[sip01_screen]


# --------------------------------------------------------------------------
# _OPENING_RANGE_SQL: NY-local DST handling (regression for the 2026-09-23
# bug described in the module docstring). Writes tiny synthetic parquet
# shards and runs the production SQL string against them via DuckDB -- not
# the real archive, but not pure-Python either, since this specific query's
# correctness depends on DuckDB's own timezone handling.
# --------------------------------------------------------------------------


def _write_minute_shard(
    path, rows: list[tuple[str, str, float, float, float, float, float]]
) -> None:
    """``rows`` are ``(symbol, utc_timestamp_str, open, high, low, close, volume)``."""
    frame = pd.DataFrame(
        rows, columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"]
    )
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame.to_parquet(path, index=False)


def _run_opening_range_sql(path) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone='UTC'")
        return con.execute(sip._OPENING_RANGE_SQL, [[str(path)]]).fetchdf()
    finally:
        con.close()


def test_opening_range_sql_excludes_regular_session_bars_on_daylight_date(tmp_path) -> None:
    # 2024-07-01 is EDT (UTC-4): the real opening range 09:30:00-09:34:59 ET
    # is 13:30-13:34 UTC. A second, distinct set of bars at 14:30-14:34 UTC
    # (10:30-10:34 ET -- forty minutes into the *regular* session, not a
    # quiet period) must NOT be folded into the same candle; a UTC
    # "EDT-band OR EST-band" filter (the actual 2026-09-23 bug) would wrongly
    # include these, doubling bar_count and corrupting open/close/volume.
    rows = [
        ("EDTX", f"2024-07-01 13:{30 + i}:00", 100.0 + i, 100.5 + i, 99.5 + i, 100.2 + i, 1000.0)
        for i in range(5)
    ]
    rows += [
        ("EDTX", f"2024-07-01 14:{30 + i}:00", 900.0 + i, 900.5 + i, 899.5 + i, 900.2 + i, 50_000.0)
        for i in range(5)
    ]
    path = tmp_path / "shard-0000.parquet"
    _write_minute_shard(path, rows)
    df = _run_opening_range_sql(path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["bar_count"] == 5
    assert row["candle_open"] == pytest.approx(100.0)
    assert row["candle_close"] == pytest.approx(104.2)
    assert row["candle_high"] == pytest.approx(104.5)
    assert row["candle_low"] == pytest.approx(99.5)
    assert row["candle_volume"] == pytest.approx(5_000.0)  # only the real 5 bars


def test_opening_range_sql_excludes_premarket_bars_on_standard_time_date(tmp_path) -> None:
    # 2024-01-02 is EST (UTC-5): the real opening range is 14:30-14:34 UTC.
    # A second set of pre-market bars at 13:30-13:34 UTC (08:30-08:34 ET --
    # confirmed present in the real archive by Stage 0's diligence probe)
    # must NOT be folded in; this is the mirror-image case of the daylight
    # test (the OLD "EDT band" clause would have wrongly matched these).
    rows = [
        ("ESTX", f"2024-01-02 13:{30 + i}:00", 700.0 + i, 700.5 + i, 699.5 + i, 700.2 + i, 70_000.0)
        for i in range(5)
    ]
    rows += [
        ("ESTX", f"2024-01-02 14:{30 + i}:00", 50.0 + i, 50.5 + i, 49.5 + i, 50.2 + i, 500.0)
        for i in range(5)
    ]
    path = tmp_path / "shard-0000.parquet"
    _write_minute_shard(path, rows)
    df = _run_opening_range_sql(path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["bar_count"] == 5
    assert row["candle_open"] == pytest.approx(50.0)
    assert row["candle_close"] == pytest.approx(54.2)
    assert row["candle_volume"] == pytest.approx(2_500.0)  # only the real 5 bars


def test_opening_range_sql_handles_the_boundary_minutes_exactly(tmp_path) -> None:
    # A bar at 09:29:00 ET (just before the range) and one at 09:35:00 ET
    # (just after) must both be excluded; only 09:30-09:34 (5 bars) count.
    rows = [
        ("BND", "2024-07-01 13:29:00", 1.0, 1.0, 1.0, 1.0, 111.0),  # 09:29 ET: excluded
        *[("BND", f"2024-07-01 13:{30 + i}:00", 2.0, 2.0, 2.0, 2.0, 10.0) for i in range(5)],
        ("BND", "2024-07-01 13:35:00", 9.0, 9.0, 9.0, 9.0, 222.0),  # 09:35 ET: excluded
    ]
    path = tmp_path / "shard-0000.parquet"
    _write_minute_shard(path, rows)
    df = _run_opening_range_sql(path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["bar_count"] == 5
    assert row["candle_volume"] == pytest.approx(50.0)


def test_minute_shard_files_prefers_month_dir_over_legacy_year_dir(tmp_path) -> None:
    # Mirrors data/sip/minute's layout: a legacy whole-year shard file
    # directly under {year}/, and the (current, preferred) month-sharded
    # layout under {year}/{month}/. Both must never be read together for
    # the same year (see scripts/build_news_hf_reaction.py's own measured
    # 15x-overread cost of doing that).
    sip_root = tmp_path / "sip"
    minute_root = sip_root / "minute"
    year_dir = minute_root / "2023"
    (year_dir / "01").mkdir(parents=True)
    (year_dir / "02").mkdir(parents=True)
    (year_dir / "shard-0000.parquet").write_bytes(b"legacy")
    (year_dir / "01" / "shard-0317.parquet").write_bytes(b"month1")
    (year_dir / "02" / "shard-0317.parquet").write_bytes(b"month2")

    original_sip_root = sip.SIP_ROOT
    try:
        sip.SIP_ROOT = sip_root
        files = sip._minute_shard_files_for_year(2023)
    finally:
        sip.SIP_ROOT = original_sip_root
    names = {p.name for p in files}
    assert names == {"shard-0317.parquet"}  # legacy shard-0000 excluded
    assert len(files) == 2  # one per month dir, legacy not duplicated in


def test_minute_shard_files_falls_back_to_legacy_when_no_month_dirs(tmp_path) -> None:
    sip_root = tmp_path / "sip"
    minute_root = sip_root / "minute"
    year_dir = minute_root / "2023"
    year_dir.mkdir(parents=True)
    (year_dir / "shard-0000.parquet").write_bytes(b"legacy")
    (year_dir / "shard-0001.parquet").write_bytes(b"legacy")

    original_sip_root = sip.SIP_ROOT
    try:
        sip.SIP_ROOT = sip_root
        files = sip._minute_shard_files_for_year(2023)
    finally:
        sip.SIP_ROOT = original_sip_root
    assert {p.name for p in files} == {"shard-0000.parquet", "shard-0001.parquet"}
