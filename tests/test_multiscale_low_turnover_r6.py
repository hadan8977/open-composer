from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from open_composer.market_calendar import us_equity_session_close
from open_composer.research.multiscale_low_turnover_r6 import (
    ALL_DAILY_SYMBOLS,
    CORE_SYMBOLS,
    R6FutureFeatureError,
    R6Panel,
    _build_benchmarks,
    _invalid_r6_result,
    _inverse_volatility_weights,
    _select_with_hold_band,
    build_daily_candidate_weights,
    build_r6_daily_features,
    reject_future_feature_control,
    simulate_daily_weights,
)


def test_hold_band_retains_existing_names_inside_exit_rank() -> None:
    ranked = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK"]

    selected = _select_with_hold_band(
        ranked,
        ["XLI", "XLK", "XLY"],
        top_n=3,
        hold_rank=5,
    )

    assert selected == ["XLI", "XLB", "XLC"]


def test_inverse_volatility_weights_respect_gross_and_symbol_caps() -> None:
    volatility = pd.Series({"XLB": 0.05, "XLC": 0.20, "XLE": 0.30})

    weights = _inverse_volatility_weights(
        ["XLB", "XLC", "XLE"],
        volatility,
        target_volatility=0.12,
    )

    assert weights.sum() <= 1.0
    assert weights.max() <= 0.4
    assert (weights >= 0.0).all()


def test_daily_simulation_lags_close_signal_until_next_open() -> None:
    sessions = (date(2026, 7, 13), date(2026, 7, 14), date(2026, 7, 15), date(2026, 7, 16))
    panel = _panel(sessions, spy_opens=[100.0, 100.0, 110.0, 121.0])
    signals = pd.DataFrame(0.0, index=sessions, columns=ALL_DAILY_SYMBOLS)
    signals.loc[sessions[0] :, "SPY"] = 1.0

    result = simulate_daily_weights(panel, signals)

    assert result.weights.loc[sessions[0], "SPY"] == 0.0
    assert result.weights.loc[sessions[1], "SPY"] == 1.0
    assert result.gross_returns.loc[sessions[0]] == 0.0
    assert result.gross_returns.loc[sessions[1]] == pytest.approx(0.10)
    assert result.turnover.sum() == pytest.approx(2.0)


def test_invalid_result_keeps_raw_metrics_out_of_authoritative_field() -> None:
    raw = {
        "candidate_id": "D06",
        "status": "completed",
        "cost_scenarios": {"10bps": {"aggregate": {"total_return_pct": 8.28}}},
    }

    result = _invalid_r6_result(
        raw,
        status="invalid_contract",
        reason_codes=["parent_rebalance_schedule_mismatch"],
    )

    assert result["status"] == "invalid_contract"
    assert result["metrics_authority"] is False
    assert result["cost_scenarios"] is None
    assert result["raw_metrics"]["cost_scenarios"] == raw["cost_scenarios"]


def test_legacy_multi_asset_simulation_witnesses_non_self_financing_accounting() -> None:
    sessions = (date(2026, 7, 13), date(2026, 7, 14), date(2026, 7, 15), date(2026, 7, 16))
    panel = _panel(sessions, spy_opens=[100.0, 100.0, 200.0, 200.0])
    panel.daily["XLB"].loc[:, "open"] = [100.0, 100.0, 100.0, 200.0]
    signals = pd.DataFrame(0.0, index=sessions, columns=ALL_DAILY_SYMBOLS)
    signals.loc[sessions[0] :, ["SPY", "XLB"]] = 0.5

    result = simulate_daily_weights(panel, signals)
    reported_gross_return = float((1.0 + result.gross_returns).prod() - 1.0)

    assert reported_gross_return == pytest.approx(1.25)
    assert reported_gross_return != pytest.approx(1.0)


def test_daily_features_are_prefix_stable_without_future_leak() -> None:
    sessions = tuple(_trading_days(date(2024, 1, 2), 330))
    full = _panel(sessions)
    prefix_sessions = sessions[:-1]
    prefix = R6Panel(
        daily={symbol: frame.loc[list(prefix_sessions)] for symbol, frame in full.daily.items()},
        intraday={},
        daily_sessions=prefix_sessions,
        intraday_sessions=(),
    )

    full_features = build_r6_daily_features(full)
    prefix_features = build_r6_daily_features(prefix)

    pd.testing.assert_frame_equal(
        full_features.raw_score.loc[list(prefix_sessions)],
        prefix_features.raw_score,
    )
    pd.testing.assert_frame_equal(
        full_features.residual_score.loc[list(prefix_sessions)],
        prefix_features.residual_score,
    )


def test_daily_candidate_weights_are_bounded_and_only_change_on_schedule() -> None:
    sessions = tuple(_trading_days(date(2024, 1, 2), 340))
    panel = _panel(sessions)
    features = build_r6_daily_features(panel)

    weights = build_daily_candidate_weights("D05", panel, features)
    active = weights.loc[features.evaluation_start :]
    changed = active.diff().abs().sum(axis=1) > 1e-12

    assert active.max().max() <= 0.4 + 1e-12
    assert active.abs().sum(axis=1).max() <= 1.0 + 1e-12
    assert changed.sum() <= int(np.ceil(len(active) / 21))


def test_static_benchmarks_broadcast_across_the_evaluation_window() -> None:
    sessions = tuple(_trading_days(date(2024, 1, 2), 340))
    panel = _panel(sessions)
    features = build_r6_daily_features(panel)

    benchmarks = _build_benchmarks(panel, features)

    assert set(benchmarks) == {
        "SPY_buy_and_hold",
        "QQQ_buy_and_hold",
        "equal_weight_sector_universe",
        "BIL_cash_proxy",
        "uninvested_cash",
        "ex_post_best_single_sector_report_only",
    }
    assert (
        benchmarks["SPY_buy_and_hold"]["cost_scenarios"]["10bps"]["aggregate"]["session_count"] > 0
    )


def test_future_feature_control_fails_closed() -> None:
    with pytest.raises(R6FutureFeatureError, match="future open is unavailable"):
        reject_future_feature_control()


def _panel(
    sessions: tuple[date, ...],
    *,
    spy_opens: list[float] | None = None,
) -> R6Panel:
    daily = {}
    length = len(sessions)
    for index, symbol in enumerate(ALL_DAILY_SYMBOLS):
        slope = 0.0002 + index * 0.00003
        periodic = 0.002 * np.sin(np.arange(length) / 7.0 + index * 0.3)
        close = 100.0 * np.cumprod(1.0 + slope + periodic)
        open_values = close * (1.0 - 0.0001)
        if symbol == "SPY" and spy_opens is not None:
            open_values = np.asarray(spy_opens, dtype=float)
            close = open_values.copy()
        daily[symbol] = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    [f"{session.isoformat()}T04:00:00Z" for session in sessions]
                ),
                "open": open_values,
                "high": np.maximum(open_values, close) * 1.001,
                "low": np.minimum(open_values, close) * 0.999,
                "close": close,
                "volume": np.full(length, 1_000_000.0 + index),
            },
            index=sessions,
        )
    return R6Panel(
        daily=daily,
        intraday={symbol: pd.DataFrame() for symbol in CORE_SYMBOLS},
        daily_sessions=sessions,
        intraday_sessions=(),
    )


def _trading_days(start: date, count: int) -> list[date]:
    output = []
    current = start
    while len(output) < count:
        if us_equity_session_close(current) is not None:
            output.append(current)
        current += timedelta(days=1)
    return output
