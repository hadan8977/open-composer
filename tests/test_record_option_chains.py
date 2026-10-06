"""T-20261005-33: option-chain recorder (no network; fake client)."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "record_option_chains.py"
spec = importlib.util.spec_from_file_location("record_option_chains", SCRIPT)
rec = importlib.util.module_from_spec(spec)
sys.modules["record_option_chains"] = rec
spec.loader.exec_module(rec)


def weekdays(start: date, end: date, holidays: set[date] = frozenset()) -> set[date]:
    days = set()
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in holidays:
            days.add(d)
        d += timedelta(days=1)
    return days


def test_window_edt_and_est():
    # 2026-10-06 is EDT (UTC-4): 15:45 ET = 19:45 UTC; 20:45 UTC = 16:45 ET.
    assert rec.in_snapshot_window(datetime(2026, 10, 6, 19, 45, tzinfo=UTC))
    assert not rec.in_snapshot_window(datetime(2026, 10, 6, 20, 45, tzinfo=UTC))
    # 2026-12-08 is EST (UTC-5): 15:45 ET = 20:45 UTC; 19:45 UTC = 14:45 ET.
    assert rec.in_snapshot_window(datetime(2026, 12, 8, 20, 45, tzinfo=UTC))
    assert not rec.in_snapshot_window(datetime(2026, 12, 8, 19, 45, tzinfo=UTC))
    # day after the DST end (2026-11-01): same rule, 20:40 UTC = 15:40 ET
    assert rec.in_snapshot_window(datetime(2026, 11, 2, 20, 40, tzinfo=UTC))
    assert not rec.in_snapshot_window(datetime(2026, 11, 2, 19, 40, tzinfo=UTC))


def test_should_run_rules():
    days = weekdays(date(2026, 10, 1), date(2026, 10, 31))
    inside = datetime(2026, 10, 6, 19, 45, tzinfo=UTC)
    outside = datetime(2026, 10, 6, 14, 0, tzinfo=UTC)
    sat = datetime(2026, 10, 10, 19, 45, tzinfo=UTC)
    kw = {"trading_days": days}
    assert rec.should_run(inside, force_now=False, existing_run_kind=None, **kw)[0]
    assert not rec.should_run(outside, force_now=False, existing_run_kind=None, **kw)[0]
    assert not rec.should_run(sat, force_now=False, existing_run_kind=None, **kw)[0]
    assert not rec.should_run(sat, force_now=True, existing_run_kind=None, **kw)[0]
    # manual flag skips the window but needs a trading day
    assert rec.should_run(outside, force_now=True, existing_run_kind=None, **kw)[0]
    # scheduled data is never overwritten by manual and not repeated by scheduled
    assert not rec.should_run(outside, force_now=True, existing_run_kind="scheduled", **kw)[0]
    assert not rec.should_run(inside, force_now=False, existing_run_kind="scheduled", **kw)[0]
    # scheduled replaces manual; manual replaces manual
    assert rec.should_run(inside, force_now=False, existing_run_kind="manual", **kw) == (
        True,
        "scheduled_replaces_manual",
    )
    assert rec.should_run(outside, force_now=True, existing_run_kind="manual", **kw)[0]


def test_third_friday_and_monthly_selection():
    assert rec.third_friday(2026, 10) == date(2026, 10, 16)
    days = weekdays(date(2026, 10, 1), date(2027, 3, 31))
    # 2026-10-06: Oct expiry is 10 days away (<20) -> Nov 20 and Dec 18
    assert rec.select_stock_expiries(date(2026, 10, 6), days) == (
        date(2026, 11, 20),
        date(2026, 12, 18),
    )
    # exactly 20 days to go counts
    assert rec.select_stock_expiries(date(2026, 9, 26), days)[0] == date(2026, 10, 16)
    # year rollover
    assert rec.select_stock_expiries(date(2026, 12, 10), days) == (
        date(2027, 1, 15),
        date(2027, 2, 19),
    )


def test_monthly_expiry_holiday_rolls_back():
    # 2027-04-16 is a Friday; pretend it is a market holiday
    days = weekdays(date(2027, 4, 1), date(2027, 4, 30), holidays={date(2027, 4, 16)})
    assert rec.monthly_expiry(2027, 4, days) == date(2027, 4, 15)


def test_strike_bounds():
    assert rec.strike_bounds(100.0, 0.20) == (80.0, 120.0)
    assert rec.strike_bounds(333.33, 0.25) == (250.0, 416.66)


def snap(bid, ask, iv, delta, volume=10):
    return {
        "latestQuote": {"bp": bid, "ap": ask, "bs": 5, "as": 6, "bx": "A", "ax": "B", "t": "q"},
        "latestTrade": {"p": (bid + ask) / 2, "s": 1, "t": "tt"},
        "dailyBar": {"v": volume},
        "impliedVolatility": iv,
        "greeks": {"delta": delta, "gamma": 0.1, "theta": -0.1, "vega": 0.2, "rho": 0.0},
    }


def make_chain(expiry: date, ivs: dict, trade_date=date(2026, 10, 6), price=100.0):
    """ivs: {(strike, 'C'/'P'): (iv, delta)}"""
    snaps = {}
    for (strike, cp), (iv, delta) in ivs.items():
        sym = f"ABC{expiry:%y%m%d}{cp}{int(strike * 1000):08d}"
        snaps[sym] = snap(1.0, 1.2, iv, delta)
    return rec.parse_snapshot_rows(
        snaps,
        underlying="ABC",
        price=price,
        price_ts="p",
        snapshot_ts="2026-10-06T14:00:00.000+00:00",
        trade_date=trade_date,
    )


def test_parse_snapshot_rows():
    rows = make_chain(date(2026, 11, 20), {(102.5, "C"): (0.3, 0.4)})
    assert len(rows) == 1
    r = rows[0]
    assert r["contract"] == "ABC261120C00102500"
    assert r["strike"] == 102.5 and r["type"] == "call" and r["expiration"] == "2026-11-20"
    assert r["iv"] == 0.3 and r["delta"] == 0.4 and r["day_volume"] == 10
    assert r["snapshot_ts_utc"].endswith("+00:00") and set(r) == set(rec.ROW_COLUMNS)
    assert (
        rec.parse_snapshot_rows(
            {"junk": {}},
            underlying="X",
            price=1,
            price_ts="",
            snapshot_ts="",
            trade_date=date(2026, 10, 6),
        )
        == []
    )


def test_interpolate_iv_30d():
    assert rec.interpolate_iv_30d([(20, 0.30), (40, 0.30)]) == (pytest.approx(0.30), "interp")
    iv, method = rec.interpolate_iv_30d([(25, 0.2), (45, 0.3)])
    assert method == "interp" and iv == pytest.approx(0.2424, abs=1e-3)
    assert rec.interpolate_iv_30d([(35, 0.2), (45, 0.3)]) == (0.2, "nearest_flat")  # not bracketed
    iv, method = rec.interpolate_iv_30d([(35, float("nan")), (45, 0.3)])
    assert (iv, method) == (0.3, "nearest_flat")
    iv, method = rec.interpolate_iv_30d([(0, 0.3)])
    assert pd.isna(iv) and method == "none"


def test_derive_iv_points():
    e1, e2 = date(2026, 10, 30), date(2026, 11, 20)  # dte 24 and 45 from 2026-10-06
    ivs1 = {
        (95.0, "P"): (0.34, -0.25),
        (100.0, "C"): (0.30, 0.52),
        (100.0, "P"): (0.32, -0.48),
        (105.0, "C"): (0.28, 0.26),
    }
    ivs2 = {(100.0, "C"): (0.27, 0.5), (100.0, "P"): (0.29, -0.5)}
    frame = pd.DataFrame(make_chain(e1, ivs1) + make_chain(e2, ivs2))
    out = rec.derive_iv_points(frame, "stock_chains").set_index("expiration")
    a = out.loc["2026-10-30"]
    assert a["dte"] == 24 and a["atm_strike"] == 100.0
    assert a["atm_call_iv"] == 0.30 and a["atm_put_iv"] == 0.32
    assert a["atm_iv"] == pytest.approx(0.31)
    assert a["call25_iv"] == 0.28 and a["put25_iv"] == 0.34
    assert out.loc["2026-11-20", "call25_iv"] != out.loc["2026-11-20", "call25_iv"]  # NaN: no 25d
    assert a["atm_iv_30d"] == out.loc["2026-11-20", "atm_iv_30d"]
    assert a["atm_iv_30d_method"] == "interp"
    assert 0.28 < a["atm_iv_30d"] < 0.31
    assert (out["source"] == "stock_chains").all()


class FakeClient:
    """Serves calendar-free snapshots; counts requests; no network."""

    def __init__(self, with_options=("AAA", "BBB", "SPY", "QQQ", "IWM")):
        self.requests = 0
        self.n_429 = 0
        self.errors = []
        self.with_options = set(with_options)
        self.calls = []

    def get_json(self, url, params=None, max_retries=7):
        self.requests += 1
        self.calls.append((url, dict(params or {})))
        if url.endswith("/v2/stocks/snapshots"):
            return {
                s: {"latestTrade": {"p": 100.0, "t": "pt"}} for s in params["symbols"].split(",")
            }
        symbol = url.rsplit("/", 1)[1]
        if symbol not in self.with_options:
            return {"snapshots": {}}
        lo, hi = params["strike_price_gte"], params["strike_price_lte"]
        if "expiration_date" in params:
            expiries = [date.fromisoformat(params["expiration_date"])]
        else:
            lo_d = date.fromisoformat(params["expiration_date_gte"])
            hi_d = date.fromisoformat(params["expiration_date_lte"])
            weekly = [date(2026, 10, 9), date(2026, 10, 16), date(2026, 10, 23), date(2026, 10, 30)]
            expiries = [d for d in weekly if lo_d <= d <= hi_d]
            if symbol == "BBB" and hi_d < date(2026, 11, 10):
                expiries = []  # BBB has no weekly/other expiry in the front window
        snaps = {}
        for expiry in expiries:
            for strike in (80.0, 100.0, 110.0, 130.0):
                if lo <= strike <= hi:
                    for cp, delta in (("C", 0.5), ("P", -0.5)):
                        sym = f"{symbol}{expiry:%y%m%d}{cp}{int(strike * 1000):08d}"
                        snaps[sym] = snap(1.0, 1.1, 0.3, delta)
        return {"snapshots": snaps}


def universe():
    return {
        "top_stocks": ["AAA"],
        "stock_chain_candidates": ["AAA", "NOOPT", "BBB"],
        "stock_chain_target": 2,
        "daily_last_date": "2026-10-05",
    }


def run(root, kind="manual", client=None):
    days = weekdays(date(2026, 10, 1), date(2027, 1, 31))
    return rec.run_snapshot(
        client or FakeClient(),
        root=root,
        trade_date=date(2026, 10, 6),
        trading_days=days,
        run_kind=kind,
        universe=universe(),
        log=lambda _m: None,
    )


def test_run_snapshot_writes_four_kinds_and_filters(tmp_path):
    client = FakeClient()
    manifest = run(tmp_path, client=client)
    day = "date=2026-10-06"
    chains = sorted(p.name for p in (tmp_path / "chains" / day).glob("*.parquet"))
    assert chains == ["AAA.parquet", "IWM.parquet", "QQQ.parquet", "SPY.parquet"]
    spy = pd.read_parquet(tmp_path / "chains" / day / "SPY.parquet")
    assert set(spy["strike"]) == {80.0, 100.0, 110.0}  # +-20% of 100 keeps 80..120
    stock = pd.read_parquet(tmp_path / "stock_chains" / day / "part.parquet")
    assert set(stock["underlying"]) == {"AAA", "BBB"}  # NOOPT skipped, target 2 reached
    assert set(stock["expiration"]) == {"2026-10-30", "2026-11-20", "2026-12-18"}
    roles = stock.groupby("expiration")["expiry_role"].agg(lambda s: set(s)).to_dict()
    assert roles == {"2026-10-30": {"front"}, "2026-11-20": {"m1"}, "2026-12-18": {"m2"}}
    assert set(stock.loc[stock["expiry_role"] == "front", "underlying"]) == {"AAA"}  # BBB none
    assert set(stock["strike"]) == {80.0, 100.0, 110.0}  # +-25% keeps 75..125
    iv = pd.read_parquet(tmp_path / "iv_points" / day / "part.parquet")
    assert len(iv) > 0 and {"chains", "stock_chains"} == set(iv["source"])
    assert stock["snapshot_ts_utc"].notna().all()
    man = json.loads((tmp_path / "chains" / day / "_manifest.json").read_text())
    assert man["run_kind"] == "manual" and man["row_counts"]["stock_chains"] == len(stock)
    assert man["requests"] == client.requests and "NOOPT:no_options" in man["skipped"]
    assert man["front_expiry"]["fetched"] and man["front_expiry"]["found"] == 1
    assert man["front_expiry"]["no_expiry_symbols"] == ["BBB"]
    iv_stock = iv[iv["source"] == "stock_chains"]
    aaa = iv_stock[iv_stock["underlying"] == "AAA"]
    assert set(aaa["atm_iv_30d_method"]) == {"interp"}  # front (24d) + m1 (45d) bracket 30d
    bbb = iv_stock[iv_stock["underlying"] == "BBB"]
    assert set(bbb["atm_iv_30d_method"]) == {"nearest_flat"}
    assert manifest["day_size_mb"] > 0
    assert not list(tmp_path.glob(".staging_*"))
    assert rec.read_manifest(tmp_path, date(2026, 10, 6))["run_kind"] == "manual"


def test_scheduled_replaces_manual_atomically(tmp_path):
    run(tmp_path, kind="manual")
    stale = tmp_path / "chains" / "date=2026-10-06" / "STALE.parquet"
    stale.write_text("x")
    run(tmp_path, kind="scheduled")
    day = tmp_path / "chains" / "date=2026-10-06"
    assert not stale.exists()  # whole day replaced
    assert json.loads((day / "_manifest.json").read_text())["run_kind"] == "scheduled"
    assert not list((tmp_path / "chains").glob("_replaced_*"))


def test_merge_vix_term_appends_only_new_closed_days():
    def f(col, vals):
        return pd.DataFrame({"date": list(vals), col: list(vals.values())})

    fresh = {
        "vix": f("vix", {"2026-10-02": 16.0, "2026-10-05": 15.5, "2026-10-06": 15.0}),
        "vix3m": f("vix3m", {"2026-10-02": 18.0, "2026-10-05": 18.5}),
        "vix9d": f("vix9d", {"2026-10-02": 14.0, "2026-10-05": 13.0}),
    }
    first = rec.merge_vix_term(None, fresh, date(2026, 10, 6), "t1")
    assert list(first["date"]) == ["2026-10-02", "2026-10-05"]  # today excluded
    fresh["vix"].loc[fresh["vix"]["date"] == "2026-10-02", "vix"] = 99.0  # stored rows are final
    second = rec.merge_vix_term(first, fresh, date(2026, 10, 7), "t2")
    assert list(second["date"]) == ["2026-10-02", "2026-10-05", "2026-10-06"]
    assert second.loc[0, "vix"] == 16.0 and second.loc[0, "fetched_utc"] == "t1"
    assert second.loc[2, "fetched_utc"] == "t2" and pd.isna(second.loc[2, "vix3m"])


def test_parse_cboe_csv():
    text = "DATE,OPEN,HIGH,LOW,CLOSE\n10/05/2026,1,2,0.5,15.52\n"
    out = rec.parse_cboe_csv(text, "vix")
    assert out.to_dict("records") == [{"date": "2026-10-05", "vix": 15.52}]


def test_rank_universe_dollar_volume_and_eligibility():
    ts = pd.date_range("2026-09-01", periods=25, freq="B", tz="UTC")
    rows = []
    for sym, px, vol in (
        ("BIG", 100, 1000),
        ("MID", 10, 1000),
        ("ETF", 1000, 10**6),
        ("NEW", 500, 10**6),
    ):
        for i, t in enumerate(ts):
            if sym == "NEW" and i < 20:
                continue  # only 5 sessions: below min_days
            rows.append({"symbol": sym, "timestamp": t, "close": px, "volume": vol})
    ranked = rec.rank_universe(pd.DataFrame(rows), {"BIG", "MID", "NEW"})
    assert ranked == ["BIG", "MID"]


def test_rate_limited_client_paces_and_backs_off():
    sleeps = []
    clock = {"t": 0.0}

    def fake_sleep(s):
        sleeps.append(s)
        clock["t"] += s

    client = rec.RateLimitedClient(
        {"X-Test": "1"}, max_per_minute=150, sleep=fake_sleep, clock=lambda: clock["t"]
    )

    class Resp:
        def __init__(self, code):
            self.status_code, self.headers = code, {}

        def json(self):
            return {"ok": 1}

    codes = [429, 429, 200]
    client._session.get = lambda url, params=None, timeout=0: Resp(codes.pop(0))
    assert client.get_json("https://example.invalid/x") == {"ok": 1}
    assert client.n_429 == 2 and client.requests == 3
    assert 1 in sleeps and 2 in sleeps  # exponential back-off 2**attempt


def _row(expiration):
    return {"expiration": expiration, "contract": f"x{expiration}"}


def test_select_front_rows():
    td = date(2026, 10, 6)
    rows = [_row("2026-10-09"), _row("2026-10-16"), _row("2026-10-30"), _row("2026-10-30")]
    # weekly present: the largest DTE below 30 wins (10-30 is 24 days out)
    chosen = rec.select_front_rows(rows, td)
    assert {r["expiration"] for r in chosen} == {"2026-10-30"} and len(chosen) == 2
    assert {r["expiry_role"] for r in chosen} == {"front"}
    # DTE 30 is excluded (must be < 30), DTE 7 included
    assert rec.select_front_rows([_row("2026-11-05")], td) == []
    assert [r["expiration"] for r in rec.select_front_rows([_row("2026-10-13")], td)] == [
        "2026-10-13"
    ]
    # only expiries under 7 days: nothing selected
    assert rec.select_front_rows([_row("2026-10-07"), _row("2026-10-12")], td) == []


def test_front_expiry_needed_only_when_m1_is_30_days_out():
    td = date(2026, 10, 6)
    assert rec.front_expiry_needed(date(2026, 11, 20), td)  # 45 days
    assert rec.front_expiry_needed(date(2026, 11, 5), td)  # exactly 30
    assert not rec.front_expiry_needed(date(2026, 10, 30), td)  # 24: m1+m2 bracket 30d


def test_front_not_fetched_when_m1_under_30_days(tmp_path):
    days = weekdays(date(2026, 10, 1), date(2027, 1, 31))
    manifest = rec.run_snapshot(
        FakeClient(),
        root=tmp_path,
        trade_date=date(2026, 9, 24),  # m1 = Oct 16 (22 days) -> m1 + m2 bracket 30 days
        trading_days=days,
        run_kind="manual",
        universe=universe(),
        log=lambda _m: None,
    )
    assert manifest["stock_expiries"][0] == "2026-10-16"
    assert manifest["front_expiry"]["fetched"] is False
    stock = pd.read_parquet(tmp_path / "stock_chains" / "date=2026-09-24" / "part.parquet")
    assert set(stock["expiry_role"]) == {"m1", "m2"}
