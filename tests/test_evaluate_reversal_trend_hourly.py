"""Tests for the pure orchestration logic in
scripts/evaluate_reversal_trend_hourly.py -- cell/config-hash identity,
the SPY trend-gate's no-lookahead alignment, ledger dedup scoping, and the
placebo per-symbol trade-count wiring through ``simulate_cell``. The
backtest mechanism itself (candidate generation, admission, portfolio P&L)
already has its own thorough test suite
(tests/test_reversal_trend_hourly_mechanism.py); this file only covers the
glue code this script adds on top: config_hash/cell_id construction, the
trend-gate mask builder, ``already_in_ledger``'s family-scoped dedup check,
and ``simulate_cell``'s two entry modes (real signal columns vs placebo
random-date counts). ``load_hourly_panel``/``compute_signals_by_symbol``/
``load_daily_return_series`` are thin real-data IO wrappers exercised by
actually running the script, matching the established convention
(build_hourly_bars.py's DuckDB-touching functions aren't separately unit
tested either) -- only ``load_hourly_panel``'s empty-directory error path is
covered here, mirroring reversal_trend_parity.py's guard.
"""

from __future__ import annotations

import importlib
import json

import numpy as np
import pandas as pd
import pytest

evaluate_reversal_trend_hourly = importlib.import_module("scripts.evaluate_reversal_trend_hourly")
rth = importlib.import_module("open_composer.research.regime.reversal_trend_hourly")


# ---------------------------------------------------------------------------
# cell_id / config_hash_for_cell
# ---------------------------------------------------------------------------


def test_cell_id_is_unique_across_the_18_cell_grid() -> None:
    ids = {
        evaluate_reversal_trend_hourly.cell_id(holding_bars, exit_rule, signal_set)
        for holding_bars in rth.HOLDING_BARS_GRID
        for exit_rule in rth.EXIT_RULES
        for signal_set in rth.SIGNAL_SETS
    }
    assert len(ids) == 3 * 3 * 2 == 18


def test_cell_id_is_stable_for_the_same_inputs() -> None:
    a = evaluate_reversal_trend_hourly.cell_id(13, "time_stop_or_reverse", "bull_and_recl")
    b = evaluate_reversal_trend_hourly.cell_id(13, "time_stop_or_reverse", "bull_and_recl")
    assert a == b


def test_config_hash_for_cell_is_deterministic() -> None:
    a = evaluate_reversal_trend_hourly.config_hash_for_cell(
        6, "time_stop", "bull_only", variant="real"
    )
    b = evaluate_reversal_trend_hourly.config_hash_for_cell(
        6, "time_stop", "bull_only", variant="real"
    )
    assert a == b


def test_config_hash_for_cell_differs_by_cell_parameters() -> None:
    base = evaluate_reversal_trend_hourly.config_hash_for_cell(
        6, "time_stop", "bull_only", variant="real"
    )
    diff_holding = evaluate_reversal_trend_hourly.config_hash_for_cell(
        13, "time_stop", "bull_only", variant="real"
    )
    diff_exit = evaluate_reversal_trend_hourly.config_hash_for_cell(
        6, "atr_trailing_2x", "bull_only", variant="real"
    )
    diff_signal = evaluate_reversal_trend_hourly.config_hash_for_cell(
        6, "time_stop", "bull_and_recl", variant="real"
    )
    hashes = {base, diff_holding, diff_exit, diff_signal}
    assert len(hashes) == 4


def test_config_hash_for_cell_differs_by_variant_even_with_identical_cell_params() -> None:
    real = evaluate_reversal_trend_hourly.config_hash_for_cell(
        6, "time_stop", "bull_only", variant="real"
    )
    placebo = evaluate_reversal_trend_hourly.config_hash_for_cell(
        6, "time_stop", "bull_only", variant="placebo"
    )
    trend_gate = evaluate_reversal_trend_hourly.config_hash_for_cell(
        6, "time_stop", "bull_only", variant="trend_gate"
    )
    assert len({real, placebo, trend_gate}) == 3


def test_all_18_real_cell_config_hashes_are_pairwise_distinct() -> None:
    hashes = [
        evaluate_reversal_trend_hourly.config_hash_for_cell(
            holding_bars, exit_rule, signal_set, variant="real"
        )
        for holding_bars in rth.HOLDING_BARS_GRID
        for exit_rule in rth.EXIT_RULES
        for signal_set in rth.SIGNAL_SETS
    ]
    assert len(set(hashes)) == len(hashes) == 18


# ---------------------------------------------------------------------------
# spy_trend_gate_masks
# ---------------------------------------------------------------------------


def _daily_close(dates: list[str], values: list[float]) -> pd.Series:
    index = pd.DatetimeIndex([pd.Timestamp(d, tz="America/New_York") for d in dates])
    return pd.Series(values, index=index)


def _hourly_bars_on_dates(dates: list[str]) -> pd.DataFrame:
    # Two hourly bars per date, matching the shape signals_by_symbol values
    # take (only the "timestamp" column is used by spy_trend_gate_masks).
    timestamps = []
    for d in dates:
        base = pd.Timestamp(d, tz="America/New_York").tz_convert("UTC")
        timestamps.append(base + pd.Timedelta(hours=14, minutes=30))
        timestamps.append(base + pd.Timedelta(hours=15, minutes=30))
    return pd.DataFrame({"timestamp": pd.DatetimeIndex(timestamps)})


def test_spy_trend_gate_masks_uses_yesterdays_completed_verdict_not_todays() -> None:
    # 200 constant days at 100.0 (SMA200 == 100.0, so close > sma is False
    # every day up to here) then one day at 200.0 -- the SMA on the jump day
    # itself barely moves (still ~100.5), so close(200) > sma is True *that*
    # day, but the mask must reflect *yesterday's* close-vs-sma verdict
    # (still False) on the jump day, only turning True the day after.
    dates = pd.bdate_range("2020-01-01", periods=201).strftime("%Y-%m-%d").tolist()
    values = [100.0] * 200 + [200.0]
    spy_daily_close = _daily_close(dates, values)

    jump_day = dates[200]
    day_after = pd.bdate_range(jump_day, periods=2)[1].strftime("%Y-%m-%d")
    bars = _hourly_bars_on_dates([jump_day, day_after])
    signals_by_symbol = {"XYZ": bars}

    masks = evaluate_reversal_trend_hourly.spy_trend_gate_masks(signals_by_symbol, spy_daily_close)
    mask = masks["XYZ"]
    assert mask.dtype == bool
    # bars[0], bars[1] -> jump_day; bars[2], bars[3] -> day_after
    assert not mask[0] and not mask[1], "jump day's bars must not see the jump-day close yet"


def test_spy_trend_gate_masks_true_once_sma_condition_has_had_a_day_to_settle() -> None:
    # A long uptrend: close is comfortably above its trailing 200-day SMA
    # for many days in a row, so the day-after-tomorrow's bars should read
    # True (yesterday's close was already above yesterday's SMA).
    n = 260
    dates = pd.bdate_range("2019-01-01", periods=n).strftime("%Y-%m-%d").tolist()
    values = list(np.linspace(100.0, 300.0, n))  # steadily rising
    spy_daily_close = _daily_close(dates, values)

    late_day = dates[-1]
    bars = _hourly_bars_on_dates([late_day])
    masks = evaluate_reversal_trend_hourly.spy_trend_gate_masks({"XYZ": bars}, spy_daily_close)
    assert masks["XYZ"].all()


def test_spy_trend_gate_masks_defaults_to_false_before_200_days_of_history() -> None:
    dates = pd.bdate_range("2021-01-01", periods=50).strftime("%Y-%m-%d").tolist()
    values = [100.0 + i for i in range(50)]  # rising, but SMA200 has no full window yet
    spy_daily_close = _daily_close(dates, values)
    bars = _hourly_bars_on_dates([dates[-1]])
    masks = evaluate_reversal_trend_hourly.spy_trend_gate_masks({"XYZ": bars}, spy_daily_close)
    assert not masks["XYZ"].any()


# ---------------------------------------------------------------------------
# already_in_ledger
# ---------------------------------------------------------------------------


def test_already_in_ledger_false_when_ledger_file_absent(tmp_path, monkeypatch) -> None:
    regime_gates = importlib.import_module("open_composer.research.regime.gates")
    monkeypatch.setattr(regime_gates, "LEDGER_PATH", tmp_path / "nonexistent.jsonl")
    assert not evaluate_reversal_trend_hourly.already_in_ledger("abc123", "some_family")


def test_already_in_ledger_true_when_family_and_hash_match(tmp_path, monkeypatch) -> None:
    regime_gates = importlib.import_module("open_composer.research.regime.gates")
    ledger_path = tmp_path / "experiments.jsonl"
    ledger_path.write_text(
        json.dumps({"family": "step13_recent_high_return", "config_hash": "abc123"}) + "\n"
    )
    monkeypatch.setattr(regime_gates, "LEDGER_PATH", ledger_path)
    assert evaluate_reversal_trend_hourly.already_in_ledger("abc123", "step13_recent_high_return")


def test_already_in_ledger_false_when_hash_matches_but_family_differs(
    tmp_path, monkeypatch
) -> None:
    regime_gates = importlib.import_module("open_composer.research.regime.gates")
    ledger_path = tmp_path / "experiments.jsonl"
    ledger_path.write_text(
        json.dumps({"family": "some_other_family", "config_hash": "abc123"}) + "\n"
    )
    monkeypatch.setattr(regime_gates, "LEDGER_PATH", ledger_path)
    assert not evaluate_reversal_trend_hourly.already_in_ledger(
        "abc123", "step13_recent_high_return"
    )


def test_already_in_ledger_ignores_blank_lines(tmp_path, monkeypatch) -> None:
    regime_gates = importlib.import_module("open_composer.research.regime.gates")
    ledger_path = tmp_path / "experiments.jsonl"
    ledger_path.write_text("\n" + json.dumps({"family": "fam", "config_hash": "xyz"}) + "\n\n")
    monkeypatch.setattr(regime_gates, "LEDGER_PATH", ledger_path)
    assert evaluate_reversal_trend_hourly.already_in_ledger("xyz", "fam")


# ---------------------------------------------------------------------------
# load_hourly_panel error path
# ---------------------------------------------------------------------------


def test_load_hourly_panel_raises_system_exit_when_no_parquet_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(evaluate_reversal_trend_hourly, "HOURLY_BARS_ROOT", tmp_path / "hourly")
    with pytest.raises(SystemExit):
        evaluate_reversal_trend_hourly.load_hourly_panel()


# ---------------------------------------------------------------------------
# simulate_cell: real signals vs placebo random-date counts
# ---------------------------------------------------------------------------


def _session_timestamps(n: int, *, start_date: str = "2024-01-02") -> pd.DatetimeIndex:
    """n consecutive 1h-bucket timestamps (7 per session day, at NY-local
    offsets 0/60/.../360 minutes past 09:30), converted to UTC -- the same
    construction tests/test_reversal_trend_hourly_mechanism.py uses so bar
    counts split cleanly across session days."""
    offsets = [0, 60, 120, 180, 240, 300, 360]
    out = []
    day = pd.Timestamp(start_date, tz="America/New_York")
    produced = 0
    while produced < n:
        if day.dayofweek < 5:
            for m in offsets:
                if produced >= n:
                    break
                out.append((day + pd.Timedelta(minutes=570 + m)).tz_convert("UTC"))
                produced += 1
        day = day + pd.Timedelta(days=1)
    return pd.DatetimeIndex(out)


def _synthetic_symbol_bars(n: int, *, price_start: float = 100.0) -> pd.DataFrame:
    timestamps = _session_timestamps(n)
    close = price_start + np.arange(n, dtype=float) * 0.1
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close - 0.05,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "atr": np.full(n, 1.0),
            "adx": np.full(n, 25.0),
            "f_bull": np.zeros(n, dtype=bool),
            "f_bear": np.zeros(n, dtype=bool),
            "f_recl": np.zeros(n, dtype=bool),
        }
    )


def test_simulate_cell_placebo_mode_draws_the_requested_count_per_symbol() -> None:
    signals_by_symbol = {
        "AAA": _synthetic_symbol_bars(60),
        "BBB": _synthetic_symbol_bars(60),
    }
    counts = {"AAA": 3, "BBB": 5}
    admitted = evaluate_reversal_trend_hourly.simulate_cell(
        signals_by_symbol,
        holding_bars=6,
        exit_rule="time_stop",
        signal_set="bull_only",
        placebo_counts=counts,
        placebo_seed=42,
    )
    by_symbol: dict[str, int] = {}
    for candidate in admitted:
        by_symbol[candidate.symbol] = by_symbol.get(candidate.symbol, 0) + 1
    # requested count is a *ceiling*, not a guarantee: generate_symbol_candidates
    # applies the same non-pyramiding rule to placebo draws as to real signals
    # (a random bar that falls inside an already-open hypothetical position for
    # that symbol is skipped), so two draws close enough together can collide
    # and yield fewer admitted trades than requested. All MAX_POSITIONS=10
    # capacity is unused here (well under 10 concurrent), so admit_by_capacity
    # itself drops nothing -- any shortfall is purely from that collision rule.
    assert 0 < by_symbol.get("AAA", 0) <= 3
    assert 0 < by_symbol.get("BBB", 0) <= 5


def test_simulate_cell_placebo_mode_skips_symbols_with_zero_count() -> None:
    signals_by_symbol = {
        "AAA": _synthetic_symbol_bars(60),
        "BBB": _synthetic_symbol_bars(60),
    }
    admitted = evaluate_reversal_trend_hourly.simulate_cell(
        signals_by_symbol,
        holding_bars=6,
        exit_rule="time_stop",
        signal_set="bull_only",
        placebo_counts={"AAA": 2, "BBB": 0},
        placebo_seed=7,
    )
    assert all(candidate.symbol == "AAA" for candidate in admitted)
    # 0 requested -> symbol is skipped outright (simulate_cell's `if count ==
    # 0: continue`), strictly and deterministically, unlike the >0 case above
    # which is only an upper bound under the non-pyramiding collision rule.
    assert 0 < len(admitted) <= 2


def test_simulate_cell_placebo_mode_is_reproducible_for_a_fixed_seed() -> None:
    signals_by_symbol = {"AAA": _synthetic_symbol_bars(80)}
    counts = {"AAA": 4}
    first = evaluate_reversal_trend_hourly.simulate_cell(
        signals_by_symbol,
        holding_bars=6,
        exit_rule="time_stop",
        signal_set="bull_only",
        placebo_counts=counts,
        placebo_seed=123,
    )
    second = evaluate_reversal_trend_hourly.simulate_cell(
        signals_by_symbol,
        holding_bars=6,
        exit_rule="time_stop",
        signal_set="bull_only",
        placebo_counts=counts,
        placebo_seed=123,
    )
    assert [c.entry_time for c in first] == [c.entry_time for c in second]


def test_simulate_cell_real_mode_reads_f_bull_column() -> None:
    bars = _synthetic_symbol_bars(40)
    bars.loc[10, "f_bull"] = True
    bars.loc[25, "f_bull"] = True
    admitted = evaluate_reversal_trend_hourly.simulate_cell(
        {"AAA": bars},
        holding_bars=6,
        exit_rule="time_stop",
        signal_set="bull_only",
    )
    assert len(admitted) == 2
    assert [c.entry_bar for c in admitted] == [11, 26]


def test_simulate_cell_real_mode_applies_entry_mask() -> None:
    bars = _synthetic_symbol_bars(40)
    bars.loc[10, "f_bull"] = True
    bars.loc[25, "f_bull"] = True
    mask = np.ones(40, dtype=bool)
    mask[10] = False  # trend gate off on the first signal bar
    admitted = evaluate_reversal_trend_hourly.simulate_cell(
        {"AAA": bars},
        holding_bars=6,
        exit_rule="time_stop",
        signal_set="bull_only",
        entry_masks={"AAA": mask},
    )
    assert len(admitted) == 1
    assert admitted[0].entry_bar == 26


# ---------------------------------------------------------------------------
# evaluate_admitted: thin structural check
# ---------------------------------------------------------------------------


def test_evaluate_admitted_returns_expected_keys() -> None:
    bars = _synthetic_symbol_bars(40)
    bars.loc[10, "f_bull"] = True
    admitted = evaluate_reversal_trend_hourly.simulate_cell(
        {"AAA": bars}, holding_bars=6, exit_rule="time_stop", signal_set="bull_only"
    )
    daily_close_by_symbol = {"AAA": rth.daily_last_close(bars)}
    calendar = daily_close_by_symbol["AAA"].index
    evaluated = evaluate_reversal_trend_hourly.evaluate_admitted(
        admitted, daily_close_by_symbol, calendar
    )
    assert set(evaluated) == {
        "admitted",
        "base_trades",
        "stress_trades",
        "base_portfolio",
        "stress_portfolio",
    }
    assert len(evaluated["base_trades"]) == len(admitted)
    assert len(evaluated["stress_trades"]) == len(admitted)
    # Stress costs are strictly worse (or equal, in the impossible zero-cost
    # case) than base costs for a strategy with no negative-cost trades.
    if admitted:
        assert evaluated["stress_trades"][0].cost_bps_per_side >= (
            evaluated["base_trades"][0].cost_bps_per_side
        )
