# ruff: noqa: E501, E741
"""Unit tests for the T-20261006-15-D Reversal Trend engine (synthetic data only)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t15d_engine as X  # noqa: E402


def _series(n_days: int, per_day: int, price=100.0):
    n = n_days * per_day
    day = np.repeat(np.arange(n_days), per_day).astype(np.int32)
    px = price + np.arange(
        n, dtype=float
    )  # strictly rising: open[i] = px[i], close[i] = px[i] + 0.5
    S = {
        "day": day,
        "slot": np.tile(np.arange(per_day), n_days).astype(np.int16),
        "o": px.copy(),
        "h": px + 1.0,
        "l": px - 1.0,
        "c": px + 0.5,
        "atr": np.full(n, 1.0),
    }
    for f in X.FLAGS:
        S[f] = np.zeros(n, bool)
    return S


def test_last_row_of_day():
    day = np.array([0, 0, 0, 1, 1, 2])
    assert X.last_row_of_day(day).tolist() == [2, 2, 2, 4, 4, 5]


def test_time_stop_blocking_and_marks():
    S = _series(1, 30)
    for t in (5, 8, 9, 10):
        S["f_bull"][t] = True
    tr = X.simulate(S, ("f_bull",), (), 3, intraday=False)
    # signal 5 -> entry row 6, exit at open of row 9; 8 and 9 are blocked (<= exit row), 10 enters row 11
    assert tr["e"].tolist() == [6, 11]
    assert tr["px"][0] == S["o"][9] and tr["pe"][0] == S["o"][6]
    ret = (S["o"][9] - S["o"][6]) / S["o"][6]
    assert np.isclose(tr["m_val"][tr["m_tid"] == 0].sum(), ret)
    assert tr["side"].tolist() == [1, 1]


def test_intraday_clip_to_session_close():
    S = _series(2, 10)
    S["f_bull"][7] = True  # entry row 8, 5-bar hold would end beyond the last row (9) of day 0
    tr = X.simulate(S, ("f_bull",), (), 5, intraday=True)
    assert len(tr["e"]) == 1
    assert tr["px"][0] == S["c"][9]
    assert tr["day_x"][0] == 0 and tr["slot_x"][0] == 9


def test_intraday_signal_on_last_bar_has_no_entry():
    S = _series(2, 10)
    S["f_bull"][9] = True  # fill would be the next day's first bar -> skipped when intraday
    assert len(X.simulate(S, ("f_bull",), (), 3, intraday=True)["e"]) == 0
    assert len(X.simulate(S, ("f_bull",), (), 3, intraday=False)["e"]) == 1


def test_multi_day_marks_sum_to_trade_return_and_short_side():
    S = _series(3, 7)
    S["f_bear"][5] = True  # short: entry row 6 (day 0), hold 10 bars -> exit open of row 16 (day 2)
    tr = X.simulate(S, ("f_bull",), ("f_bear",), 10, intraday=False)
    assert tr["side"].tolist() == [-1]
    assert tr["day_e"][0] == 0 and tr["day_x"][0] == 2
    ret = (S["o"][16] - S["o"][6]) / S["o"][6]
    assert np.isclose(tr["m_val"].sum(), ret)
    assert sorted(set(tr["m_day"].tolist())) == [0, 1, 2]


def test_time_stop_or_reverse_exits_on_opposite_signal():
    S = _series(1, 30)
    S["f_bull"][5] = True
    S["f_bear"][8] = True
    tr = X.simulate(S, ("f_bull",), (), 10, intraday=False, exit_rule="time_stop_or_reverse")
    assert tr["px"][0] == S["o"][9]  # decision on the close of row 8 -> fill at open of row 9


def test_atr_trailing_stop_fires_inside_bar():
    S = _series(1, 30)
    S["f_bull"][5] = True
    S["atr"][:] = 1.0
    # entry row 6: close 106.5 -> stop 104.5; row 8 crashes through the stop
    S["l"][8] = 100.0
    S["o"][8] = 108.0
    tr = X.simulate(S, ("f_bull",), (), 10, intraday=False, exit_rule="atr_trailing_2x")
    assert tr["xr"][0] == 8
    assert tr["px"][0] <= 108.0 and tr["px"][0] >= 104.0


def test_bad_session_drops_trade():
    S = _series(2, 10)
    S["f_bull"][2] = True
    bad = np.zeros(2, bool)
    bad[0] = True
    assert len(X.simulate(S, ("f_bull",), (), 3, intraday=True, bad_by_day=bad)["e"]) == 0


def test_split_adjust_detects_forward_split():
    rows = []
    for d, (px, vol) in enumerate([(100.0, 1e6), (101.0, 1e6), (10.2, 1e7), (10.4, 1e6)]):
        for m in (570, 571):
            rows.append((pd.Timestamp("2024-06-03") + pd.Timedelta(days=d), m, px, px, px, px, vol))
    df = pd.DataFrame(rows, columns=["date", "minute", "open", "high", "low", "close", "volume"])
    out, trig = X.split_adjust(df)
    assert list(trig) == [pd.Timestamp("2024-06-05")]
    assert np.isclose(out.loc[out["date"] == pd.Timestamp("2024-06-03"), "close"].iloc[0], 10.0)


def test_split_adjust_keeps_real_gap_but_flags_session():
    rows = []
    for d, px in enumerate([100.0, 100.0, 60.0, 60.0]):
        rows.append((pd.Timestamp("2024-06-03") + pd.Timedelta(days=d), 570, px, px, px, px, 1e6))
    df = pd.DataFrame(rows, columns=["date", "minute", "open", "high", "low", "close", "volume"])
    out, trig = X.split_adjust(df)
    assert len(trig) == 1
    assert out["close"].tolist() == [100.0, 100.0, 60.0, 60.0]


def test_to_hourly_has_six_hours_and_a_half_hour():
    minutes = np.arange(570, 960)
    df = pd.DataFrame(
        {
            "date": pd.Timestamp("2024-06-03"),
            "minute": minutes,
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 1.0,
        }
    )
    h = X.to_hourly(df)
    assert h["volume"].tolist() == [60, 60, 60, 60, 60, 60, 30]
    assert h["minute"].tolist()[:2] == [570, 630]
    h1 = X.to_hourly(df, phase=1)
    assert h1["volume"].tolist()[0] == 61  # the shifted anchor keeps the first minutes in bar 0


def test_chunked_indicator_matches_full_run(monkeypatch):
    rng = np.random.default_rng(3)
    n = 6000
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    o = np.r_[close[0], close[:-1]]
    h = np.maximum(o, close) * 1.0005
    l = np.minimum(o, close) * 0.9995
    full = X.run_indicator(o, h, l, close)
    monkeypatch.setattr(X, "CHUNK", 2000)
    monkeypatch.setattr(X, "WARM", 1500)
    part = X.run_indicator(o, h, l, close)
    for f in X.FLAGS:
        assert np.array_equal(full[f], part[f])
    assert full["f_bull"].sum() + full["f_bear"].sum() > 0


def test_acc_real_matches_trade_return_and_random_day_placebo_runs(monkeypatch):
    import t15d_run as R

    monkeypatch.setattr(R, "RECENT_IDX0", 0)
    S = _series(5, 20)
    S["f_bull"][[3, 45]] = True
    ctx = {"kind": "etf", "tick_cents": 1, "factor": np.ones(5)}
    monkeypatch.setattr(X, "master", lambda: pd.date_range("2024-01-01", periods=5))
    tr = X.simulate(S, ("f_bull",), (), 4, intraday=True)
    co = X.trade_costs(tr, ctx)
    rng = np.random.default_rng(1)
    acc = R.Acc(2, 5, seeds=10)
    acc.add_real(tr, co, rng)
    rbs = R.rows_by_slot(S, None, np.zeros(5, bool))
    acc.add_random_day(S, tr, co, {"H": 4, "intraday": True}, rbs, rng, np.zeros(5, bool))
    ret = sum((p - e) / e for p, e in zip(tr["px"], tr["pe"], strict=True))
    assert np.isclose(acc.g.sum(), ret / 2)
    assert acc.ent.sum() == 2
    # a rising series: every same-slot random-day long trade is a gain
    assert (acc.rd_g.sum(axis=1) > 0).all()
    assert acc.rd_n.min() == 2
    # cost: ETF round trip is roughly half spread twice + slippage + SEC fee on the sell leg
    assert (
        1.0 < (co["var_e"] + co["var_x"])[0] < 5.0
    )  # price ~100: 0.5 bp half spread per leg, +1 bp open add


def test_cluster_t_and_mde():
    sys.path.insert(0, str(ROOT / "scripts"))
    import t15d_deep as Dp

    rng = np.random.default_rng(0)
    x = rng.normal(2.0, 1.0, 400)
    day = np.repeat(np.arange(100), 4)
    t = Dp.cluster_t(day, x)
    assert t is not None and t > 10
    assert Dp.cluster_t(day[:5], x[:5]) is None
    assert abs(Dp.mde_sharpe(252) - 2.486) < 1e-9
