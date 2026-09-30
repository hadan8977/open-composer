from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import run_t20260930_15_quote_check as q


def _ns(day: str, hh: int, mm: int, ss: float = 0.0) -> int:
    return q.et_to_utc_ns(day, hh, mm) + int(ss * 1e9)


def _quote(day: str, ss: float, bid: float, ask: float, hh: int = 15, mm: int = 29) -> dict:
    ns = _ns(day, hh, mm, ss)
    ts = pd.Timestamp(ns, unit="ns").strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return {"t": ts, "bp": bid, "ap": ask}


def test_sample_days_reproducible_and_shared() -> None:
    days = pd.bdate_range("2024-01-08", "2026-09-29")
    a = q.sample_days(list(days) + list(days))  # duplicates are removed
    b = q.sample_days(list(reversed(list(days))))
    assert a == b and len(a) == q.N_DAYS == len(set(a))
    assert a == sorted(a)
    expect = np.random.default_rng(20260930).choice(
        np.asarray([str(d.date()) for d in days]), 30, replace=False
    )
    assert set(a) == set(expect.tolist())


def test_et_to_utc_handles_daylight_saving() -> None:
    ns_summer = q.et_to_utc_ns("2024-07-01", 15, 30)
    ns_winter = q.et_to_utc_ns("2024-01-08", 15, 30)
    assert pd.Timestamp(ns_summer, unit="ns").hour == 19  # EDT = UTC-4
    assert pd.Timestamp(ns_winter, unit="ns").hour == 20  # EST = UTC-5


def test_last_valid_quote_drops_crossed_locked_and_keeps_latest() -> None:
    day = "2024-07-01"
    end = _ns(day, 15, 30)
    start = end - 5_000_000_000
    state: dict = {}
    quotes = {
        "AAA": [
            _quote(day, 58.0, 9.99, 10.01),  # 15:29:58 valid
            _quote(day, 59.0, 10.02, 10.01),  # crossed
            _quote(day, 59.5, 10.00, 10.00),  # locked
            _quote(day, 59.7, 0.0, 10.01),  # zero bid
        ],
        "BBB": [_quote(day, 50.0, 5.0, 5.02)],  # outside the 5 s window
        "CCC": [_quote(day, 59.0, 3.0, 3.02), _quote(day, 59.9, 3.01, 3.03)],
    }
    q.update_last_valid(state, quotes, start, end)
    assert state["AAA"][:2] == (9.99, 10.01)
    assert "BBB" not in state
    assert state["CCC"][:2] == (3.01, 3.03)


def test_window_end_is_exclusive_and_60s_relaxation() -> None:
    day = "2024-07-01"
    end = _ns(day, 15, 30)
    at_t = {"t": pd.Timestamp(end, unit="ns").strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "bp": 1, "ap": 2}
    early = _quote(day, 30.0, 4.0, 4.02)  # 30 s before T
    s5: dict = {}
    q.update_last_valid(s5, {"X": [early, at_t]}, end - 5_000_000_000, end)
    assert "X" not in s5  # the quote at exactly T is excluded, the early one is outside 5 s
    s60: dict = {}
    q.update_last_valid(s60, {"X": [early, at_t]}, end - 60_000_000_000, end)
    assert s60["X"][:2] == (4.0, 4.02)


def test_quotes_for_uses_60s_pass_only_for_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(q, "QUOTE_CACHE", tmp_path)
    day = "2024-07-01"
    end = _ns(day, 15, 30)

    class Sess:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def get_url(self, url: str, params: dict) -> dict:
            self.calls.append(dict(params))
            width = (end - pd.Timestamp(params["start"]).value) // 1_000_000_000
            data = {"AAA": [_quote(day, 59.0, 9.0, 9.1)]}
            if width >= 60:
                data["BBB"] = [_quote(day, 20.0, 5.0, 5.1)]
            return {"quotes": data, "next_page_token": None}

    sess = Sess()
    out = q.quotes_for(sess, day, 15, 30, ["BBB", "AAA"]).set_index("symbol")
    assert out.loc["AAA", "window_s"] == 5 and out.loc["BBB", "window_s"] == 60
    assert out.loc["BBB", "bid"] == 5.0
    assert len(sess.calls) == 2 and sess.calls[1]["symbols"] == "BBB"
    n = len(sess.calls)
    q.quotes_for(sess, day, 15, 30, ["BBB", "AAA"])  # served from the cache
    assert len(sess.calls) == n


def test_leg_returns_signs_toy_close_period() -> None:
    p = np.array([100.0])
    close = np.array([101.0])
    bid, ask = np.array([99.9]), np.array([100.1])
    tl, el = q.leg_returns("C", "long", p, close, bid, ask)
    ts, es = q.leg_returns("C", "short", p, close, bid, ask)
    assert np.isclose(tl[0], 0.01) and np.isclose(el[0], 101 / 100.1 - 1)
    assert np.isclose(ts[0], -0.01) and np.isclose(es[0], -(101 / 99.9 - 1))
    # the gap is positive for both legs when the last trade sits mid-spread
    assert (tl - el)[0] > 0 and (ts - es)[0] > 0
    # trade at the ask -> long gap 0; trade at the bid -> short gap 0
    tl0, el0 = q.leg_returns("C", "long", ask, close, bid, ask)
    ts0, es0 = q.leg_returns("C", "short", bid, close, bid, ask)
    assert np.isclose(tl0 - el0, 0.0) and np.isclose(ts0 - es0, 0.0)


def test_leg_returns_signs_toy_open_period() -> None:
    p = np.array([50.0])
    op = np.array([49.0])
    bid, ask = np.array([49.95]), np.array([50.05])
    tl, el = q.leg_returns("O", "long", p, op, bid, ask)
    ts, es = q.leg_returns("O", "short", p, op, bid, ask)
    assert np.isclose(tl[0], 50 / 49 - 1) and np.isclose(el[0], 49.95 / 49 - 1)
    assert np.isclose(ts[0], -(50 / 49 - 1)) and np.isclose(es[0], -(50.05 / 49 - 1))
    assert np.isclose((tl - el)[0], 0.05 / 49) and np.isclose((ts - es)[0], 0.05 / 49)
    # gap in bp is (p - bid)/open for the long and (ask - p)/open for the short
    assert np.isclose(((tl - el) + (ts - es))[0], (ask - bid)[0] / 49)


def test_position_and_half_spread() -> None:
    bid, ask = np.array([9.0]), np.array([11.0])
    assert np.isclose(q.spread_position(np.array([10.0]), bid, ask)[0], 0.5)
    assert np.isclose(q.spread_position(np.array([11.0]), bid, ask)[0], 1.0)
    assert np.isclose(q.half_spread(bid, ask)[0], 0.1)


def test_day_mean_is_mean_of_day_means() -> None:
    v = np.array([1.0, 3.0, 10.0, np.nan])
    d = np.array(["a", "a", "b", "b"])
    m, n = q.day_mean(v, d)
    assert n == 2 and np.isclose(m, (2.0 + 10.0) / 2)


def test_a2_tier_boundaries() -> None:
    ok = {"t_nw": 5.0, "beat": 1.0}
    # closed when m - s - 8 < 0, marginal exactly at 0
    assert q.a2_tier(10.0, 2.0 + 1e-9, **ok) == "closed"
    assert q.a2_tier(10.0, 2.0, **ok) == "marginal"
    # pass exactly at m - 2s - 16 == 0 (m=20, s=2 -> 20-4-16=0; also m-s-8=10>=0)
    assert q.a2_tier(20.0, 2.0, **ok) == "pass"
    assert q.a2_tier(19.999, 2.0, **ok) == "marginal"
    # t and placebo thresholds close the cell whatever the margin
    assert q.a2_tier(50.0, 0.0, t_nw=1.99, beat=1.0) == "closed"
    assert q.a2_tier(50.0, 0.0, t_nw=2.0, beat=0.89) == "closed"
    assert q.a2_tier(50.0, 0.0, t_nw=2.0, beat=0.90) == "pass"
    # negative s (favourable) is allowed
    assert q.a2_tier(10.0, -1.0, **ok) == "marginal"


def test_rescale_quotes_puts_raw_quotes_on_adjusted_basis() -> None:
    fr = pd.DataFrame(
        {
            "close": [33.0, 50.0, 10.0],
            "raw_close": [66.0, 50.0, np.nan],  # 2:1 split, no split, no raw close
            "bid": [69.0, 49.9, 9.9],
            "ask": [69.2, 50.1, 10.1],
        }
    )
    out = q.rescale_quotes(fr, "bid", "ask")
    assert np.allclose(out["bid"].iloc[:2], [34.5, 49.9])
    assert np.allclose(out["ask"].iloc[:2], [34.6, 50.1])
    assert np.isnan(out["bid"].iloc[2]) and np.isnan(out["adj_factor"].iloc[2])


def test_fetch_raw_closes_caches_and_marks_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(q, "QUOTE_CACHE", tmp_path)

    class Sess:
        n = 0

        def get_url(self, url: str, params: dict) -> dict:
            Sess.n += 1
            assert params["adjustment"] == "raw" and params["feed"] == "sip"
            return {"bars": {"AAA": [{"t": "2024-02-01T05:00:00Z", "c": 66.0}]}}

    out = q.fetch_raw_closes(Sess(), "2024-02-01", ["BBB", "AAA"]).set_index("symbol")
    assert out.loc["AAA", "raw_close"] == 66.0 and np.isnan(out.loc["BBB", "raw_close"])
    q.fetch_raw_closes(Sess(), "2024-02-01", ["BBB", "AAA"])
    assert Sess.n == 1


def test_basis_offset_flags_needs_stable_offset() -> None:
    n = 4
    df = pd.DataFrame(
        {
            "symbol": ["A"] * n + ["B"] * n + ["C"] * 2,
            "p": [99.0] * n + [100.0, 100.1, 99.9, 100.05] + [90.0, 90.0],
            "bid_entry": [99.9] * n + [99.95] * n + [99.9] * 2,
            "ask_entry": [100.1] * n + [100.05] * n + [100.1] * 2,
        }
    )
    fl = q.basis_offset_flags(df, "p")
    assert fl[:n].all() and not fl[n : 2 * n].any()  # A: stable -1% offset; B: noise
    assert not fl[2 * n :].any()  # C: too few rows to assess
