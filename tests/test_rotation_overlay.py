"""Volatility-target overlay and sleeve equity for ``etf_rotation_portfolio``.

The overlay must reproduce the research engine that froze the 2026-09-23
renewal rules (``scripts/run_h20260922_05_salvage.py``), so the core test
builds one synthetic panel on real market sessions and checks, session by
session, that the paper adapter's next-session decision equals the research
schedule. The real-archive version of the same check is
``scripts/check_rotation_overlay_parity.py``.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.adapters.execution.rotation_overlay import (
    apply_multiplier,
    boost_window,
    decide_overlay,
    sleeve_equity_curve,
    vol_scale_schedule,
)
from open_composer.adapters.execution.rotation_target_weights import replay_books
from open_composer.market_calendar import us_equity_session_dates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260922_05_salvage as research  # noqa: E402

MENU = ["TQQQ", "SOXL", "UPRO", "USD", "TECL"]


def _synthetic_panel(seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    sessions = us_equity_session_dates(date(2023, 1, 3), date(2025, 6, 30))
    rng = np.random.default_rng(seed)
    n = len(sessions)
    paths: dict[str, np.ndarray] = {}
    for i, symbol in enumerate(MENU):
        drift = 0.0006 + 0.0003 * i
        paths[symbol] = 50.0 * np.exp(np.cumsum(rng.normal(drift, 0.035, n)))
    paths["SHY"] = 80.0 * np.exp(np.cumsum(rng.normal(0.0001, 0.001, n)))
    # QQQ trends up with sharp two-week pullbacks, so the dip signal fires.
    shocks = rng.normal(0.0008, 0.011, n)
    for start in range(260, n, 90):
        shocks[start : start + 6] -= 0.012
    paths["QQQ"] = 300.0 * np.exp(np.cumsum(shocks))
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in sessions])
    close = pd.DataFrame(paths, index=index)
    gaps = pd.DataFrame(rng.normal(0.0, 0.004, close.shape), index=index, columns=close.columns)
    open_ = close.shift(1).fillna(close) * (1.0 + gaps)
    return close, open_


def _series(close: pd.DataFrame) -> dict[str, tuple[list[date], dict[date, float]]]:
    out = {}
    for symbol in close.columns:
        days = [d.date() for d in close.index]
        out[symbol] = (days, dict(zip(days, close[symbol].astype(float), strict=True)))
    return out


def test_next_session_decision_matches_the_research_schedule() -> None:
    close, open_ = _synthetic_panel()
    leg_open, leg_close = research.legs(close, open_)
    r_weights, r_signals = research.sleeve_weights(close, "s3")
    gross, _ = research.simulate(r_weights, leg_open, leg_close, np.ones(len(close)), 0.0)
    boost = research.boost_window(research.dip_signal(close), 10)
    r_sched = research.vol_scale(close.index, r_signals, gross, 0.40, boost, 0.60)
    assert boost.sum() > 0, "fixture must exercise the dip boost"

    series = _series(close)
    days = [d.date() for d in close.index]
    book_cols = sorted([*MENU, "SHY"])
    kwargs = dict(
        menu=MENU,
        cash_symbol="SHY",
        lookbacks=[63],
        top_n=2,
        rebalance="monthly_last_session",
        absolute_momentum_filter=True,
        # The research engine needs only the 63-session lookback.
        min_history_sessions=64,
        unfilled_slot_policy="renormalize_survivors",
    )
    compared = boost_sessions = 0
    for i in range(300, len(days) - 1):
        sessions = days[: i + 1]
        weights, signals = replay_books(series, sessions, **kwargs)
        decision = decide_overlay(
            sessions,
            weights,
            close.iloc[: i + 1][book_cols].set_axis(sessions),
            open_.iloc[: i + 1][book_cols].set_axis(sessions),
            signals,
            base_target=0.40,
            realized_vol_sessions=21,
            dip_close=pd.Series(close["QQQ"].to_numpy()[: i + 1], index=sessions),
            boost_target=0.60,
            hold_sessions=10,
        )
        assert decision.multiplier == pytest.approx(r_sched[i + 1], abs=1e-12), days[i]
        ext, _ = replay_books(series, [*sessions, days[i + 1]], **kwargs)
        live_book = {s: w for s, w in ext.iloc[-1].items() if w > 0}
        research_book = {s: w for s, w in r_weights.iloc[i + 1].items() if w > 0}
        assert live_book == pytest.approx(research_book), days[i]
        compared += 1
        boost_sessions += int(decision.boost_active)
    assert compared > 300
    assert boost_sessions > 0


def test_schedule_only_moves_at_rebalance_and_boost_toggles() -> None:
    realized = np.full(12, 0.8)
    boost = np.zeros(12, dtype=bool)
    boost[6:9] = True
    sched, last = vol_scale_schedule(12, [2], realized, 0.4, boost, 0.6)
    assert sched[:3].tolist() == [1.0, 1.0, 1.0]
    assert sched[3:6] == pytest.approx([0.5, 0.5, 0.5])
    assert sched[6:9] == pytest.approx([0.75, 0.75, 0.75])
    assert sched[9:] == pytest.approx([0.5, 0.5, 0.5])
    assert last.tolist() == [-1, -1, -1, 3, 3, 3, 6, 6, 6, 9, 9, 9]


def test_multiplier_never_levers_and_moves_the_rest_to_cash() -> None:
    sched, _ = vol_scale_schedule(4, [0], np.array([0.1, 0.1, 0.1, 0.1]), 0.4)
    assert sched.max() == 1.0
    scaled = apply_multiplier({"SOXL": 0.5, "TECL": 0.5, "SHY": 0.0}, 0.6, "SHY")
    assert scaled == pytest.approx({"SOXL": 0.3, "TECL": 0.3, "SHY": 0.4})
    assert sum(scaled.values()) == pytest.approx(1.0)


def test_boost_is_live_from_the_session_after_the_firing_close() -> None:
    sig = np.zeros(8, dtype=bool)
    sig[2] = True
    assert boost_window(sig, 3).tolist() == [0, 0, 0, 1, 1, 1, 0, 0]


def test_sleeve_equity_marks_the_ledger_at_each_close() -> None:
    days = [date(2026, 9, d) for d in (18, 21, 22, 23)]
    closes = pd.DataFrame(
        {"UPRO": [150.0, 151.0, 160.0, 140.0], "SHY": [81.0, 81.0, 81.1, 81.2]}, index=days
    )
    fills = [
        {"session": "2026-09-21", "symbol": "UPRO", "side": "buy", "filled_qty": 99.0,
         "filled_avg_price": 149.86},
        {"session": "2026-09-23", "symbol": "UPRO", "side": "sell", "filled_qty": 20.0,
         "filled_avg_price": 141.0},
        {"session": "2026-09-23", "symbol": "SHY", "side": "buy", "filled_qty": 38.0,
         "filled_avg_price": 81.2},
        {"session": "2026-09-22", "symbol": "TECL", "side": "buy", "filled_qty": 0.0,
         "filled_avg_price": None, "status": "expired"},
    ]  # fmt: skip
    curve = sleeve_equity_curve(fills, closes, 15_000.0)
    cash_after_buy = 15_000.0 - 99 * 149.86
    assert list(curve.index) == days[1:]
    assert curve[days[1]] == pytest.approx(cash_after_buy + 99 * 151.0)
    assert curve[days[2]] == pytest.approx(cash_after_buy + 99 * 160.0)
    cash_end = cash_after_buy + 20 * 141.0 - 38 * 81.2
    assert curve[days[3]] == pytest.approx(cash_end + 79 * 140.0 + 38 * 81.2)
    assert sleeve_equity_curve([], closes, 15_000.0).empty


def test_sleeve_equity_fails_closed_without_a_mark() -> None:
    closes = pd.DataFrame({"SHY": [81.0]}, index=[date(2026, 9, 21)])
    fills = [
        {"session": "2026-09-21", "symbol": "UPRO", "side": "buy", "filled_qty": 1.0,
         "filled_avg_price": 150.0},
    ]  # fmt: skip
    with pytest.raises(ValueError, match="no close to mark"):
        sleeve_equity_curve(fills, closes, 15_000.0)
