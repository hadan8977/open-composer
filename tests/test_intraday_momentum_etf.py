from __future__ import annotations

import pandas as pd
import pytest

from open_composer.research.kernel.mechanisms.intraday_momentum_etf import (
    PARAMETER_SPACE,
    daily_intraday_momentum_returns,
)


def _session_bars(day: str, opens_highs_lows_closes: list[tuple[float, float, float, float]]):
    """Five-minute RTH bars (13:30..) for one session, from explicit OHLC tuples."""
    timestamps = pd.date_range(
        f"{day} 13:30", periods=len(opens_highs_lows_closes), freq="5min", tz="UTC"
    )
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [row[0] for row in opens_highs_lows_closes],
            "high": [row[1] for row in opens_highs_lows_closes],
            "low": [row[2] for row in opens_highs_lows_closes],
            "close": [row[3] for row in opens_highs_lows_closes],
        }
    )


def _flat_session(day: str, level: float, bars: int = 6) -> pd.DataFrame:
    return _session_bars(day, [(level, level, level, level)] * bars)


def _breakout_session(
    day: str, open_price: float, breakout_price: float, bars: int = 6
) -> pd.DataFrame:
    rows = [(open_price, open_price, open_price, open_price)]
    rows += [(breakout_price, breakout_price, breakout_price, breakout_price)] * (bars - 1)
    return _session_bars(day, rows)


def test_parameter_space_has_eighteen_combinations() -> None:
    assert len(PARAMETER_SPACE) == 18
    assert len({tuple(sorted(p.items())) for p in PARAMETER_SPACE}) == 18


def test_warmup_sessions_are_excluded_not_zero_filled() -> None:
    # 10 flat warm-up sessions with true_range=0 -> noise_band stays 0 or NaN
    # for lookback_sessions=3 until enough history accumulates.
    frames = [_flat_session(f"2026-08-{3 + i:02d}", 100.0) for i in range(3)]
    combined = pd.concat(frames, ignore_index=True)
    with pytest.raises(ValueError, match="trailing history"):
        daily_intraday_momentum_returns(
            combined,
            {"noise_multiplier": 1.0, "lookback_sessions": 3, "use_trailing_stop": False},
        )


def test_no_trade_days_are_recorded_as_zero() -> None:
    # Build enough history (true_range > 0) then one final flat (no-breakout) day.
    frames = [
        _session_bars(f"2026-08-{3 + i:02d}", [(100.0, 101.0, 99.0, 100.0)] * 4) for i in range(4)
    ]
    frames.append(_flat_session("2026-08-10", 100.0, bars=4))
    combined = pd.concat(frames, ignore_index=True)
    series = daily_intraday_momentum_returns(
        combined,
        {"noise_multiplier": 5.0, "lookback_sessions": 4, "use_trailing_stop": False},
    )
    # First 4 sessions are warm-up (no prior history yet); only the 5th is scored,
    # and a huge noise_multiplier guarantees no breakout -- so it is 0.0, present.
    assert len(series) == 1
    assert series.iloc[0] == 0.0


def test_a_clean_breakout_earns_the_move_minus_round_trip_cost() -> None:
    frames = [
        _session_bars(f"2026-08-{3 + i:02d}", [(100.0, 102.0, 98.0, 100.0)] * 4) for i in range(4)
    ]
    # True range for warm-up sessions is 4.0; noise_multiplier=0.5 -> band = 2.0.
    frames.append(_breakout_session("2026-08-10", open_price=100.0, breakout_price=103.0))
    combined = pd.concat(frames, ignore_index=True)
    series = daily_intraday_momentum_returns(
        combined,
        {
            "noise_multiplier": 0.5,
            "lookback_sessions": 4,
            "use_trailing_stop": False,
            "cost_bps_per_side": 3.0,
        },
    )
    assert len(series) == 1
    # Entry at 103 (first bar clearing 100+2=102), exit at session close (103):
    # flat move, so return is exactly -round_trip_cost.
    expected = 0.0 - 2 * 3.0 / 10_000.0
    assert series.iloc[0] == pytest.approx(expected)


def test_trailing_stop_exits_before_giving_back_the_whole_move() -> None:
    frames = [
        _session_bars(f"2026-08-{3 + i:02d}", [(100.0, 104.0, 96.0, 100.0)] * 4) for i in range(4)
    ]
    # True range 8.0, noise_multiplier=0.5 -> band=4.0, breakout level=104.
    # Session: open 100, breakout to 106 (entry), peak 106, then fades to 100.
    fade_session = _session_bars(
        "2026-08-10",
        [
            (100.0, 100.0, 100.0, 100.0),
            (106.0, 106.0, 106.0, 106.0),  # entry here (>= 104)
            (106.0, 106.0, 106.0, 106.0),  # peak
            (100.0, 100.0, 100.0, 100.0),  # trailing stop should fire (band*0.5=2 given back)
            (90.0, 90.0, 90.0, 90.0),
        ],
    )
    combined = pd.concat([*frames, fade_session], ignore_index=True)
    stopped = daily_intraday_momentum_returns(
        combined,
        {
            "noise_multiplier": 0.5,
            "lookback_sessions": 4,
            "use_trailing_stop": True,
            "trailing_stop_fraction": 0.5,
            "cost_bps_per_side": 0.0,
        },
    )
    held = daily_intraday_momentum_returns(
        combined,
        {
            "noise_multiplier": 0.5,
            "lookback_sessions": 4,
            "use_trailing_stop": False,
            "cost_bps_per_side": 0.0,
        },
    )
    # Held to close realizes the final 90 print; the trailing stop must do
    # meaningfully better since it exits near the 106 peak instead.
    assert stopped.iloc[0] > held.iloc[0]
    assert held.iloc[0] == pytest.approx(90.0 / 106.0 - 1.0)


def test_only_information_up_to_and_including_the_current_bar_is_used() -> None:
    # A future spike placed only in the LAST bar of the session must not be
    # visible to the entry decision made on an earlier bar.
    frames = [
        _session_bars(f"2026-08-{3 + i:02d}", [(100.0, 101.0, 99.0, 100.0)] * 4) for i in range(4)
    ]
    session = _session_bars(
        "2026-08-10",
        [
            (100.0, 100.0, 100.0, 100.0),
            (100.0, 100.0, 100.0, 100.0),  # never reaches the breakout level here
            (100.0, 100.0, 100.0, 100.0),
            (999.0, 999.0, 999.0, 999.0),  # future spike in the final bar only
        ],
    )
    combined = pd.concat([*frames, session], ignore_index=True)
    series = daily_intraday_momentum_returns(
        combined,
        {"noise_multiplier": 50.0, "lookback_sessions": 4, "use_trailing_stop": False},
    )
    # A band of 50x true range (1.0) = 50 is never cleared until the final bar,
    # at which point entry and exit are the same bar -- net return is exactly
    # -round_trip_cost, not the (999/100-1) move a look-ahead bug would produce.
    assert series.iloc[0] == pytest.approx(-2 * 3.0 / 10_000.0)
