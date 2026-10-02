"""Synthetic-candle tests for scripts/build_kalshi_release_uncertainty.py and
scripts/fetch_kalshi_macro.py (T-20261002-44). No network, no market data."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


build = _load("build_kalshi_release_uncertainty")
fetch = _load("fetch_kalshi_macro")
ET = ZoneInfo("America/New_York")


def candle(market: str, end_utc: str, bid=None, ask=None, last=None) -> dict:
    return {
        "market_ticker": market,
        "end_period_ts": int(datetime.fromisoformat(end_utc).timestamp()),
        "yes_bid_close": bid,
        "yes_ask_close": ask,
        "price_close": last,
    }


def test_cleaning_makes_cdf_monotone_and_keeps_the_anchor():
    raw = [0.97, 0.80, 0.90, 0.55, 0.60, 0.20, 0.30, 0.05]
    cleaned = build.clean_middle_out(raw)
    assert np.all(np.diff(cleaned) <= 1e-12)  # non-increasing in strike
    anchor = int(np.argmin(np.abs(np.asarray(raw) - 0.5)))
    assert cleaned[anchor] == pytest.approx(raw[anchor])
    assert cleaned.min() >= 0 and cleaned.max() <= 1


def test_cleaning_leaves_a_monotone_curve_unchanged():
    raw = [0.99, 0.9, 0.6, 0.3, 0.1, 0.02]
    assert build.clean_middle_out(raw) == pytest.approx(raw)


def test_pmf_sums_to_one_and_std_matches_two_point_distribution():
    # P(X > 0) = 0.5 and P(X > 1) = 0.5 -> all mass on the tails around two strikes
    strikes = [0.0, 1.0, 2.0]
    cleaned = [0.5, 0.5, 0.0]
    mids, mass = build.implied_pmf(strikes, cleaned)
    assert mass.sum() == pytest.approx(1.0)
    # bins: (<=0) mid -0.5 mass 0.5 ; (0,1] mass 0 ; (1,2] mass 0.5 at 1.5 ; (>2) mass 0
    mean, std = build.pmf_moments(mids, mass)
    assert mean == pytest.approx(0.5)
    assert std == pytest.approx(1.0)  # two points 2 apart, equal mass


def test_pmf_handles_open_tails():
    strikes = [1.0, 2.0, 3.0]
    mids, mass = build.implied_pmf(strikes, [0.9, 0.5, 0.1])
    assert mass.sum() == pytest.approx(1.0)
    assert len(mids) == len(strikes) + 1
    assert mids[0] == pytest.approx(0.5) and mids[-1] == pytest.approx(3.5)


def test_strike_price_rules():
    mid = pd.Series({"yes_bid_close": 0.40, "yes_ask_close": 0.48, "price_close": 0.9})
    assert build.strike_price(mid) == (pytest.approx(0.44), "mid")
    wide = pd.Series({"yes_bid_close": 0.10, "yes_ask_close": 0.60, "price_close": 0.30})
    assert build.strike_price(wide) == (0.30, "last_trade")
    nothing = pd.Series({"yes_bid_close": 0.0, "yes_ask_close": 1.0, "price_close": np.nan})
    assert build.strike_price(nothing) == (None, "missing")
    # a spread of exactly 0.10 still counts as a mid
    edge = pd.Series({"yes_bid_close": 0.30, "yes_ask_close": 0.40, "price_close": np.nan})
    assert build.strike_price(edge)[1] == "mid"


def test_signal_candle_never_uses_a_candle_after_1500_et_on_previous_session():
    prev = date(2026, 8, 11)  # EDT, 15:00 ET = 19:00 UTC
    end_ts = build.signal_end_ts(prev)
    assert end_ts == int(datetime(2026, 8, 11, 19, tzinfo=UTC).timestamp())
    frame = pd.DataFrame(
        [
            candle("M1", "2026-08-11T18:00:00+00:00", 0.4, 0.5),
            candle("M1", "2026-08-11T19:00:00+00:00", 0.5, 0.6),  # ends exactly at 15:00 ET: ok
            candle("M1", "2026-08-11T20:00:00+00:00", 0.9, 0.95),  # after the cutoff: never used
            candle("M2", "2026-08-11T20:00:00+00:00", 0.9, 0.95),  # only a late candle: no signal
        ]
    )
    chosen = build.signal_candles(frame, end_ts)
    assert list(chosen["market_ticker"]) == ["M1"]
    assert chosen["end_period_ts"].max() <= end_ts
    assert float(chosen.iloc[0]["yes_bid_close"]) == 0.5


def test_signal_time_is_1500_et_in_winter_too():
    assert build.signal_end_ts(date(2026, 1, 13)) == int(
        datetime(2026, 1, 13, 20, tzinfo=UTC).timestamp()
    )


def _event_candles(end: str) -> tuple[pd.DataFrame, dict[str, float]]:
    strikes = {"E-T1": 1.0, "E-T2": 2.0, "E-T3": 3.0, "E-T4": 4.0, "E-T5": 5.0}
    prices = [0.95, 0.8, 0.5, 0.2, 0.05]
    rows = [candle(t, end, p - 0.01, p + 0.01) for t, p in zip(strikes, prices, strict=True)]
    return pd.DataFrame(rows), strikes


def test_event_distribution_counts_usable_strikes_and_gives_positive_u():
    frame, strikes = _event_candles("2026-08-11T18:00:00+00:00")
    out = build.event_distribution(frame, strikes, build.signal_end_ts(date(2026, 8, 11)))
    assert out["n_usable_strikes"] == 5
    assert out["U"] > 0
    assert out["pmf_mean"] == pytest.approx(3.0, abs=0.1)


def test_missing_strikes_reduce_the_usable_count():
    frame, strikes = _event_candles("2026-08-11T18:00:00+00:00")
    frame.loc[frame["market_ticker"] == "E-T5", ["yes_bid_close", "yes_ask_close"]] = [0.0, 1.0]
    out = build.event_distribution(frame, strikes, build.signal_end_ts(date(2026, 8, 11)))
    assert out["n_usable_strikes"] == 4 and out["n_missing_price"] == 1


def _series_frame(us: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(us), freq="30D")
    return pd.DataFrame(
        {
            "series": "KXCPI",
            "event_ticker": [f"E{i:03d}" for i in range(len(us))],
            "release_date": dates,
            "U": us,
        }
    )


def test_u_rel_uses_only_prior_events_and_warmup_threshold():
    us = [1.0] * 8 + [2.0, 100.0]
    out = build.add_u_rel(_series_frame(us))
    # the first 6 events have fewer than 6 prior events: warm-up, no U_rel
    assert out["warmup"].tolist()[:6] == [True] * 6
    assert out["U_rel"].iloc[:6].isna().all()
    # event 6 has 6 prior events, all 1.0 -> U_rel = 1
    assert out["U_rel"].iloc[6] == pytest.approx(1.0)
    # event 8 (U=2.0) is judged against prior events only: median 1.0 -> 2.0
    assert out["U_rel"].iloc[8] == pytest.approx(2.0)
    # event 9 (U=100): the median of the previous 12 (1x8, 2.0) is 1.0, not affected by itself
    assert out["U_rel"].iloc[9] == pytest.approx(100.0)
    # changing the future never changes the past
    out2 = build.add_u_rel(_series_frame(us[:8] + [2.0, 5.0]))
    assert out2["U_rel"].iloc[:9].tolist()[6:] == out["U_rel"].iloc[:9].tolist()[6:]


def test_u_rel_window_is_the_previous_12_events():
    us = [10.0] * 3 + [1.0] * 12 + [1.0]
    out = build.add_u_rel(_series_frame(us))
    # for the last event the previous 12 are all 1.0 (the three 10.0 values fell out)
    assert out["median_prior_U"].iloc[-1] == pytest.approx(1.0)
    assert out["U_rel"].iloc[-1] == pytest.approx(1.0)


def test_u_rel_skips_excluded_events_without_counting_them():
    us = [1.0, 1.0, np.nan, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0]
    out = build.add_u_rel(_series_frame(us))
    assert out["n_prior_events"].iloc[8] == 7  # the NaN event is not a prior event
    assert out["U_rel"].iloc[8] == pytest.approx(2.0)


def test_day_level_dedupe_takes_the_max_u_rel():
    df = pd.DataFrame(
        {
            "series": ["KXCPI", "KXPAYROLLS", "KXGDP"],
            "release_date": pd.to_datetime(["2026-02-11", "2026-02-11", "2026-03-01"]),
            "U_rel": [0.8, 1.7, 1.1],
        }
    )
    day = build.day_level_signal(df)
    assert len(day) == 2
    assert day.set_index("release_date").loc[pd.Timestamp("2026-02-11"), "U_rel"] == 1.7
    assert day.set_index("release_date").loc[pd.Timestamp("2026-02-11"), "n_releases"] == 2


def test_build_event_row_flags_and_exclusion():
    trading = [date(2026, 8, d) for d in (10, 11, 12, 13)]
    meta = {
        "event_ticker": "KXCPI-26JUL",
        "title": "CPI in July",
        "markets": [
            {
                "ticker": f"KXCPI-26JUL-T{i}",
                "strike_type": "greater",
                "floor_strike": float(i),
                "close_time": "2026-08-12T12:25:00Z",
                "settlement_ts": "2026-08-12T13:00:00Z",
            }
            for i in range(1, 4)
        ],
    }
    candles = pd.DataFrame(
        [candle(f"KXCPI-26JUL-T{i}", "2026-08-11T18:00:00+00:00", 0.4, 0.5) for i in range(1, 4)]
    )
    row = build.build_event_row("KXCPI", meta, candles, trading)
    assert row["release_date"] == pd.Timestamp("2026-08-12")
    assert row["close_time_et_hhmm"] == "08:25"
    assert row["signal_prev_session"] == pd.Timestamp("2026-08-11")
    assert row["n_usable_strikes"] == 3 and row["excluded"] is True  # fewer than 4
    assert np.isnan(row["U"])


def test_fomc_row_is_checked_against_the_calendar():
    meta = {
        "event_ticker": "KXFED-26SEP",
        "title": "Fed meeting in Sep 2026",
        "markets": [
            {
                "ticker": f"KXFED-26SEP-T{i}",
                "strike_type": "greater",
                "floor_strike": 3.0 + 0.25 * i,
                "close_time": "2026-09-16T18:00:00Z",
                "settlement_ts": None,
            }
            for i in range(5)
        ],
    }
    row = build.build_event_row(
        "KXFED", meta, pd.DataFrame(), [date(2026, 9, 15), date(2026, 9, 16)]
    )
    assert row["is_fomc"] and row["fomc_calendar_match"] and row["fomc_title_month_match"]


# ----------------------------------------------------------------- fetch layer


def test_fetch_client_backs_off_on_429_and_gives_up_cleanly():
    calls: list[str] = []
    sleeps: list[float] = []
    responses = [(429, None), (503, None), (200, {"ok": 1})]

    def http_get(url, params):
        calls.append(url)
        return responses.pop(0)

    client = fetch.KalshiClient(http_get, sleep=sleeps.append, clock=lambda: 0.0)
    assert client.get("series/KXCPI") == {"ok": 1}
    assert len(calls) == 3
    assert [s for s in sleeps if s >= 1.0] == [1.0, 2.0]  # exponential backoff

    def always_429(url, params):
        return 429, None

    with pytest.raises(RuntimeError):
        fetch.KalshiClient(always_429, sleep=lambda s: None, clock=lambda: 0.0).get("x")


def test_fetch_client_rate_limit_spaces_requests():
    stamps = {"t": 0.0}
    waits: list[float] = []

    def http_get(url, params):
        return 200, {"a": 1}

    client = fetch.KalshiClient(
        http_get,
        sleep=lambda s: waits.append(s),
        clock=lambda: stamps["t"],
        min_interval_s=0.2,
    )
    client.get("a")
    client.get("b")  # clock did not advance -> must wait the full interval
    assert waits and waits[-1] == pytest.approx(0.2)


def test_fetch_event_routes_by_cutoff_and_checkpoints(tmp_path):
    cutoff = int(datetime(2026, 8, 3, tzinfo=UTC).timestamp())
    seen: list[str] = []

    def http_get(url, params):
        path = url.split("/trade-api/v2/")[-1] if "/trade-api/v2/" in url else url
        seen.append(path)
        if path.startswith("historical/markets/") and path.endswith("candlesticks"):
            return 200, {
                "candlesticks": [
                    {
                        "end_period_ts": 1_780_000_000,
                        "yes_bid": {"close": "0.4000"},
                        "yes_ask": {"close": "0.4500"},
                        "price": {"close": None, "previous": "0.4200"},
                        "volume": "5.00",
                        "open_interest": "9.00",
                    }
                ]
            }
        if path == "historical/markets":
            return 200, {"markets": [], "cursor": ""}
        return 200, {"candlesticks": []}

    market = {
        "ticker": "KXCPI-26MAY-T0.2",
        "event_ticker": "KXCPI-26MAY",
        "strike_type": "greater",
        "floor_strike": 0.2,
        "open_time": "2026-04-01T00:00:00Z",
        "close_time": "2026-06-10T12:25:00Z",
        "settlement_ts": "2026-06-10T13:00:00Z",
    }
    event = {"event_ticker": "KXCPI-26MAY", "title": "CPI in May", "markets": [market]}
    client = fetch.KalshiClient(http_get, sleep=lambda s: None, clock=lambda: 0.0)
    res = fetch.fetch_event(client, "KXCPI", event, cutoff, tmp_path)
    assert res["candles"] == 1
    assert any(p.startswith("historical/markets/KXCPI-26MAY-T0.2/candlesticks") for p in seen)
    assert not any(p.startswith("series/KXCPI/markets") for p in seen)
    frame = pd.read_parquet(tmp_path / "KXCPI" / "KXCPI-26MAY.parquet")
    assert frame.loc[0, "yes_ask_close"] == pytest.approx(0.45)
    assert frame.loc[0, "price_previous"] == pytest.approx(0.42)
    # a second call is a checkpoint hit and issues no request
    before = client.requests
    assert fetch.fetch_event(client, "KXCPI", event, cutoff, tmp_path)["skipped"] is True
    assert client.requests == before


def test_parse_candles_reads_both_endpoint_schemas():
    historical = {
        "end_period_ts": 1_780_000_000,
        "yes_bid": {"close": "0.4000"},
        "yes_ask": {"close": "0.4500"},
        "price": {"close": "0.4200", "previous": "0.4100"},
        "volume": "5.00",
        "open_interest": "9.00",
    }
    live = {
        "end_period_ts": 1_780_000_000,
        "yes_bid": {"close_dollars": "0.4000"},
        "yes_ask": {"close_dollars": "0.4500"},
        "price": {"close_dollars": "0.4200", "previous_dollars": "0.4100"},
        "volume_fp": "5.00",
        "open_interest_fp": "9.00",
    }
    kwargs = dict(series="KXCPI", event="E", ticker="E-T1")
    a = fetch.parse_candles([historical], endpoint="historical", **kwargs)[0]
    b = fetch.parse_candles([live], endpoint="live", **kwargs)[0]
    for key in (
        "yes_bid_close",
        "yes_ask_close",
        "price_close",
        "price_previous",
        "volume",
        "open_interest",
    ):
        assert a[key] == b[key] is not None
    assert b["yes_ask_close"] == pytest.approx(0.45)
