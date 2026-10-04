"""Synthetic tests for scripts/build_pm_midterm_data.py (T-20261004-53)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_pm_midterm_data.py"
spec = importlib.util.spec_from_file_location("build_pm_midterm_data", SCRIPT)
assert spec and spec.loader
bd = importlib.util.module_from_spec(spec)
sys.modules["build_pm_midterm_data"] = bd
spec.loader.exec_module(bd)


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, params=None, *, allow_404=False):
        self.calls.append((url, dict(params or {})))
        return self.routes(url, params or {})


def test_cut_epoch_follows_dst() -> None:
    # 16:00 EDT = 20:00 UTC; 16:00 EST = 21:00 UTC
    summer = pd.Timestamp(bd.cut_epoch(date(2026, 7, 1)), unit="s", tz="UTC")
    winter = pd.Timestamp(bd.cut_epoch(date(2026, 12, 1)), unit="s", tz="UTC")
    assert summer.hour == 20
    assert winter.hour == 21


def test_windows_cover_range_without_gaps_and_stay_within_14_days() -> None:
    w = bd.windows(0, 40 * 86400)
    assert w[0][0] == 0 and w[-1][1] == 40 * 86400
    assert all(hi - lo <= 14 * 86400 for lo, hi in w)
    assert all(w[i][1] == w[i + 1][0] for i in range(len(w) - 1))


def test_daily_at_cut_uses_last_point_at_or_before_cut_and_skips_before_first() -> None:
    d1, d2, d3 = date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)
    c1, c2 = bd.cut_epoch(d1), bd.cut_epoch(d2)
    pts = [(c1 - 3600, 0.40), (c1, 0.42), (c1 + 1, 0.99), (c2 + 3600, 0.50)]
    out = bd.daily_at_cut(pts, [date(2026, 9, 28), d1, d2, d3])
    assert list(out["session"].dt.date) == [d1, d2, d3]
    # the point exactly at the cut counts, the one a second later does not
    assert out["price"].tolist() == [0.42, 0.99, 0.50]
    assert out["age_hours"].iloc[0] == 0.0


def test_fetch_poly_history_dedups_and_falls_back_to_finer_fidelity() -> None:
    def routes(url, params):
        if params["fidelity"] == 60 and params["startTs"] == 0:
            return {"history": []}
        return {
            "history": [
                {"t": params["startTs"] + 5, "p": 0.3},
                {"t": params["startTs"] + 5, "p": 0.3},
            ]
        }

    http = FakeHttp(routes)
    pts = bd.fetch_poly_history(http, "tok", 0, 20 * 86400)
    assert [p[0] for p in pts] == sorted({p[0] for p in pts})
    fidelities = [c[1]["fidelity"] for c in http.calls]
    assert fidelities[:2] == [60, 10]  # first window empty at 60, retried at 10


def test_fetch_kalshi_hourly_skips_null_closes() -> None:
    def routes(url, params):
        return {
            "candlesticks": [
                {"end_period_ts": 100, "price": {"close_dollars": "0.0860"}},
                {"end_period_ts": 200, "price": {"close_dollars": None}},
                {"end_period_ts": 300, "price": {}},
            ]
        }

    pts = bd.fetch_kalshi_hourly(FakeHttp(routes), "CONTROLH", "CONTROLH-2026-R", 0, 86400)
    assert pts == [(100, 0.086)]


def _event(tags, markets):
    return {"id": "e", "title": "t", "tags": [{"slug": s} for s in tags], "markets": markets}


def _market(i, volume, token):
    return {"id": i, "question": f"q{i}", "volumeNum": volume, "clobTokenIds": f'["{token}", "x"]'}


def test_placebo_candidates_filter_political_and_order_by_volume() -> None:
    events = [
        _event(["sports", "nfl"], [_market(1, 10, "a"), _market(2, 500, "b")]),
        _event(["sports", "politics"], [_market(3, 9999, "c")]),
        _event(["crypto"], [_market(4, 100, "d")]),
        _event(["weather"], [_market(5, 777, "e")]),
    ]
    out = bd.placebo_candidates(events)
    assert [r["market_id"] for r in out] == [2, 4, 1]


def test_select_placebo_takes_first_candidate_alive_on_80_percent() -> None:
    window = bd.sessions_between(date(2026, 1, 5), date(2026, 3, 31))
    first, last = bd.cut_epoch(window[0]) - 1000, bd.cut_epoch(window[-1])
    short_start = bd.cut_epoch(window[int(len(window) * 0.5)])

    def routes(url, params):
        tok = params["market"]
        if tok == "b":  # starts at half the window: 50 percent alive, rejected
            return {"history": [{"t": short_start, "p": 0.5}, {"t": last, "p": 0.5}]}
        return {"history": [{"t": first, "p": 0.5}, {"t": last, "p": 0.6}]}

    events = [
        _event(["sports"], [_market(2, 500, "b")]),
        _event(["crypto"], [_market(4, 100, "d")]),
    ]
    chosen, log = bd.select_placebo(FakeHttp(routes), window, events)
    assert chosen["market_id"] == 4
    assert [r["market_id"] for r in log] == [2, 4]
    assert log[0]["alive_coverage"] < 0.8 <= log[1]["alive_coverage"]


def test_alive_coverage_ends_with_history() -> None:
    window = bd.sessions_between(date(2026, 1, 5), date(2026, 1, 30))
    half = bd.cut_epoch(window[len(window) // 2])
    cov = bd.alive_coverage([(bd.cut_epoch(window[0]) - 10, 0.5), (half, 0.5)], window)
    assert 0.5 <= cov <= 0.6
    assert bd.alive_coverage([], window) == 0.0


def test_signal_start_index_and_polymarket_rule() -> None:
    assert bd.signal_start_index(200) == 61
    assert bd.signal_start_index(61) is None
    d = {
        "polymarket_house_r": pd.DataFrame({"a": range(130)}),
        "polymarket_senate_r": pd.DataFrame({"a": range(50)}),
    }
    rule = bd.polymarket_rule(d)
    assert rule["markets_used"] == ["polymarket_house_r"] and rule["fallback_applied"] is True


def test_asset_coverage_drops_assets_below_80_percent() -> None:
    window = bd.sessions_between(date(2026, 1, 5), date(2026, 2, 27))
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in window])
    bars = {"SPY": pd.Series(1.0, index=idx), "DJT": pd.Series(1.0, index=idx[: len(idx) // 2])}
    rep, kept = bd.asset_coverage(bars, window)
    assert "SPY" in kept and "DJT" not in kept
    assert rep["QQQ"]["sessions_with_bar"] == 0 and rep["DJT"]["kept"] is False


def test_listed_span_prefilter_skips_markets_that_ended_early() -> None:
    window = bd.sessions_between(date(2026, 1, 5), date(2026, 3, 31))
    ended = {"start": "2025-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"}
    alive = {"start": "2025-01-01T00:00:00Z", "end": "2026-12-31T00:00:00Z"}
    unknown = {"start": None, "end": None}
    assert not bd.listed_span_covers(ended, window)
    assert bd.listed_span_covers(alive, window) and bd.listed_span_covers(unknown, window)
