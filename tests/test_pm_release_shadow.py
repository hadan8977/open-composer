"""Tests for scripts/pm_release_shadow.py (T-20261002-45): fake Kalshi client, fake SIP frames.
No network and no market data."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


shadow = _load("pm_release_shadow")

STRIKES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
# P(X > k): a spread-out distribution around 0.3-0.4
PRICES = [0.95, 0.80, 0.55, 0.20, 0.05, 0.01]
WIDE_PRICES = [0.90, 0.80, 0.60, 0.40, 0.20, 0.10]


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def ts(text: str) -> int:
    return int(utc(text).timestamp())


def candle(end: str, price: float) -> dict:
    return {
        "end_period_ts": ts(end),
        "yes_bid": {"close_dollars": f"{price - 0.01:.4f}"},
        "yes_ask": {"close_dollars": f"{price + 0.01:.4f}"},
        "price": {"close_dollars": f"{price:.4f}"},
    }


class FakeClient:
    """Serves one event per series; candles may include ones after the signal instant."""

    def __init__(self, events: dict[str, dict], candles: dict[str, list[dict]]):
        self.events = events  # series -> event dict
        self.candles = candles  # market ticker -> candle list
        self.requested: list[str] = []

    def get(self, path: str, params: dict | None = None):
        self.requested.append(path)
        if path == "historical/cutoff":
            return {"market_settled_ts": "2026-06-01T00:00:00Z"}
        if path.startswith("historical/markets/"):
            return {"candlesticks": []}
        if path.startswith("series/") and "/markets/" in path:
            ticker = path.split("/markets/")[1].split("/")[0]
            return {"candlesticks": self.candles.get(ticker, [])}
        if path.startswith("series/"):
            return {"series": {}} if path.split("/")[1] in self.events else None
        if path == "events":
            event = self.events.get(params["series_ticker"])
            return {"events": [event] if event else [], "cursor": ""}
        raise AssertionError(path)


def make_event(series: str, name: str, close: str, strikes=STRIKES) -> dict:
    return {
        "event_ticker": name,
        "title": name,
        "markets": [
            {
                "ticker": f"{name}-T{k}",
                "event_ticker": name,
                "strike_type": "greater",
                "floor_strike": k,
                "open_time": "2026-09-01T00:00:00Z",
                "close_time": close,
                "status": "active",
            }
            for k in strikes
        ],
    }


def fixture_client(series="KXCPI", name="KXCPI-26SEP", close="2026-10-14T12:25:00Z", *, prices):
    event = make_event(series, name, close)
    candles = {
        f"{name}-T{k}": [candle("2026-10-13T18:00:00", p), candle("2026-10-13T20:00:00", 0.5)]
        for k, p in zip(STRIKES, prices, strict=True)
    }
    return FakeClient({series: event}, candles)


@pytest.fixture
def history(tmp_path, monkeypatch):
    rows = []
    for i in range(10):  # 10 earlier events, U = 0.1 each
        rows.append(
            {
                "series": "KXCPI",
                "release_date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=30 * i),
                "event_ticker": f"KXCPI-OLD{i}",
                "U": 0.1,
            }
        )
    rows.append(  # a LATER event that must never enter the median
        {
            "series": "KXCPI",
            "release_date": pd.Timestamp("2027-06-01"),
            "event_ticker": "KXCPI-FUTURE",
            "U": 9.0,
        }
    )
    for i in range(10):
        rows.append(
            {
                "series": "KXFED",
                "release_date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=30 * i),
                "event_ticker": f"KXFED-OLD{i}",
                "U": 0.05,
            }
        )
    path = tmp_path / "ru.parquet"
    pd.DataFrame(rows).to_parquet(path)
    monkeypatch.setattr(shadow, "RELEASE_UNCERTAINTY", path)
    return path


# ------------------------------------------------------------------ calendar and window


def test_nyse_calendar_known_closures():
    assert not shadow.is_session(date(2026, 11, 26))  # Thanksgiving
    assert not shadow.is_session(date(2026, 4, 3))  # Good Friday
    assert not shadow.is_session(date(2026, 7, 3))  # July 4 observed on Friday
    assert not shadow.is_session(date(2026, 6, 19))  # Juneteenth
    assert shadow.is_session(date(2026, 12, 31))
    assert shadow.is_session(date(2027, 12, 31))  # New Year's Day on Saturday: not observed
    assert shadow.next_session(date(2026, 10, 2)) == date(2026, 10, 5)
    assert shadow.next_session(date(2026, 11, 25)) == date(2026, 11, 27)


@pytest.mark.parametrize(
    "now,expected",
    [
        ("2026-10-13T19:10:00", True),  # 15:10 EDT
        ("2026-10-13T20:10:00", False),  # 16:10 EDT
        ("2026-10-13T18:59:00", False),  # 14:59 EDT
        ("2026-10-13T19:50:00", False),  # 15:50 EDT is already outside
        ("2026-12-08T20:10:00", True),  # 15:10 EST
        ("2026-12-08T19:10:00", False),  # 14:10 EST
        ("2026-10-10T19:10:00", False),  # a Saturday
    ],
)
def test_window_guard(now, expected):
    ok, _, _ = shadow.window_status(utc(now))
    assert ok is expected


def test_window_targets_next_session_across_weekend_and_holiday():
    assert shadow.window_status(utc("2026-10-02T19:10:00"))[1] == date(2026, 10, 5)
    assert shadow.window_status(utc("2026-11-25T20:10:00"))[1] == date(2026, 11, 27)


def test_outside_window_writes_nothing_and_never_calls_the_api(tmp_path, history):
    client = fixture_client(prices=PRICES)
    result = shadow.run_signal(utc("2026-10-13T20:10:00"), client, tmp_path, log=lambda m: None)
    assert result["status"] == "outside_window" and result["wrote"] == 0
    assert client.requested == []
    assert not (tmp_path / "signals.jsonl").exists()


# ----------------------------------------------------------------------------- signal


def run(client, tmp_path, now="2026-10-13T19:10:00"):
    return shadow.run_signal(utc(now), client, tmp_path, commit="abc123", log=lambda m: None)


def test_signal_logs_events_and_day_without_using_later_candles(tmp_path, history):
    result = run(fixture_client(prices=PRICES), tmp_path)
    assert result["status"] == "logged"
    rows = [json.loads(x) for x in (tmp_path / "signals.jsonl").read_text().splitlines()]
    event, day = rows
    assert event["record_type"] == "event" and day["record_type"] == "day"
    assert event["n_usable_strikes"] == 6 and event["code_commit"] == "abc123"
    assert event["release_date"] == "2026-10-14" and event["signal_end_utc"].startswith(
        "2026-10-13T19:00"
    )
    # the 20:00 UTC candle (price 0.5 on every strike) lies after 15:00 ET and must not be used
    flat = shadow.bk.event_distribution(
        pd.DataFrame(
            [
                {
                    "market_ticker": f"m{i}",
                    "end_period_ts": ts("2026-10-13T18:00:00"),
                    "yes_bid_close": p - 0.01,
                    "yes_ask_close": p + 0.01,
                    "price_close": p,
                }
                for i, p in enumerate(PRICES)
            ]
        ),
        {f"m{i}": k for i, k in enumerate(STRIKES)},
        ts("2026-10-13T19:00:00"),
    )
    assert event["U"] == pytest.approx(flat["U"])
    assert event["pmf_mean"] == pytest.approx(flat["pmf_mean"])
    assert day["day_U_rel"] == pytest.approx(event["U_rel"]) and day["would_hold"] is True


def test_u_rel_uses_only_prior_events(tmp_path, history):
    run(fixture_client(prices=PRICES), tmp_path)
    event = json.loads((tmp_path / "signals.jsonl").read_text().splitlines()[0])
    # median of the ten earlier events is 0.1; the 2027 row (U = 9) is later and is ignored
    assert event["median_prior_U"] == pytest.approx(0.1)
    assert event["n_prior_events"] == 10
    assert event["U_rel"] == pytest.approx(event["U"] / 0.1)


def test_earlier_forward_rows_enter_the_history(tmp_path, history):
    forward = [
        {
            "record_type": "event",
            "series": "KXCPI",
            "release_date": "2026-09-30",
            "event_ticker": "KXCPI-FWD",
            "U": 0.3,
        }
    ]
    hist = shadow.history_frame("KXCPI", date(2026, 10, 14), forward)
    assert "KXCPI-FWD" in set(hist["event_ticker"]) and "KXCPI-FUTURE" not in set(
        hist["event_ticker"]
    )
    out = shadow.u_rel_for("KXCPI", date(2026, 10, 14), "KXCPI-NEW", 0.2, hist)
    assert out["n_prior_events"] == 11
    assert out["median_prior_U"] == pytest.approx(0.1)  # median of ten 0.1 and one 0.3


def test_signal_is_idempotent(tmp_path, history):
    run(fixture_client(prices=PRICES), tmp_path)
    before = (tmp_path / "signals.jsonl").read_text()
    again = run(fixture_client(prices=PRICES), tmp_path)
    assert again["status"] == "already_logged" and again["wrote"] == 0
    assert (tmp_path / "signals.jsonl").read_text() == before
    assert before.endswith("\n") and len(before.splitlines()) == 2


def test_fomc_day_is_not_would_hold_even_with_high_u_rel(tmp_path, history):
    client = fixture_client(
        series="KXFED", name="KXFED-26OCT", close="2026-10-28T17:55:00Z", prices=WIDE_PRICES
    )
    client.candles = {
        f"KXFED-26OCT-T{k}": [candle("2026-10-27T18:00:00", p)]
        for k, p in zip(STRIKES, WIDE_PRICES, strict=True)
    }
    run(client, tmp_path, now="2026-10-27T19:10:00")
    event, day = [json.loads(x) for x in (tmp_path / "signals.jsonl").read_text().splitlines()]
    assert event["is_fomc"] is True and day["fomc_day"] is True
    assert day["day_U_rel"] is not None and day["day_U_rel"] > 1
    assert day["would_hold"] is False and day["would_hold_incl_fomc"] is True


def test_cpi_on_an_fomc_decision_day_is_an_fomc_day(tmp_path, history):
    client = fixture_client(close="2026-10-28T12:25:00Z", prices=PRICES)
    client.candles = {
        f"KXCPI-26SEP-T{k}": [candle("2026-10-27T18:00:00", p)]
        for k, p in zip(STRIKES, WIDE_PRICES, strict=True)
    }
    run(client, tmp_path, now="2026-10-27T19:10:00")
    day = json.loads((tmp_path / "signals.jsonl").read_text().splitlines()[-1])
    assert day["fomc_day"] is True and day["would_hold"] is False


def test_thin_event_is_logged_but_has_no_signal(tmp_path, history):
    client = fixture_client(prices=PRICES)
    client.candles = {k: v for k, v in client.candles.items() if k.endswith(("T0.1", "T0.2"))}
    run(client, tmp_path)
    event, day = [json.loads(x) for x in (tmp_path / "signals.jsonl").read_text().splitlines()]
    assert event["excluded"] is True and event["U"] is None and event["U_rel"] is None
    assert day["day_U_rel"] is None and day["would_hold"] is False


def test_no_event_for_the_release_day_writes_nothing(tmp_path, history):
    client = fixture_client(close="2026-10-20T12:25:00Z", prices=PRICES)
    result = run(client, tmp_path)
    assert result["status"] == "no_event"
    assert not (tmp_path / "signals.jsonl").exists()


# ---------------------------------------------------------------------------- realize


def sip_frames() -> dict[str, pd.DataFrame]:
    idx = pd.to_datetime(["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15"])
    base = {
        "SPY": ([100.0, 100.0, 101.0, 102.0], [100.0, 100.0, 102.0, 103.0]),
        "QQQ": ([200.0, 200.0, 202.0, 204.0], [200.0, 200.0, 206.0, 208.0]),
        "IWM": ([50.0, 50.0, 49.0, 50.0], [50.0, 50.0, 49.5, 50.0]),
        "BIL": ([91.0, 91.0, 91.0, 91.0], [91.0, 91.0, 91.05, 91.1]),
    }
    return {s: pd.DataFrame({"open": o, "close": c}, index=idx) for s, (o, c) in base.items()}


def write_day(out_dir: Path, release: str, u_rel: float, *, fomc=False):
    out_dir.mkdir(parents=True, exist_ok=True)
    row = {
        "record_type": "day",
        "release_date": release,
        "day_U_rel": u_rel,
        "fomc_day": fomc,
        "would_hold": u_rel > 1 and not fomc,
    }
    with (out_dir / "signals.jsonl").open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def test_realize_maps_previous_close_to_release_day(tmp_path):
    write_day(tmp_path, "2026-10-14", 1.3)
    shadow.run_realize(sip_frames(), tmp_path, now=utc("2026-10-15T00:00:00"), commit="abc")
    (row,) = [json.loads(x) for x in (tmp_path / "realized.jsonl").read_text().splitlines()]
    assert row["prev_session"] == "2026-10-13"
    assert row["QQQ_R_cc"] == pytest.approx(206.0 / 200.0 - 1)  # close(T) / close(T-1)
    assert row["QQQ_R_co"] == pytest.approx(202.0 / 200.0 - 1)  # open(T) / close(T-1)
    assert row["BIL_R_cc"] == pytest.approx(91.05 / 91.0 - 1)
    assert row["QQQ_R_cc_ex"] == pytest.approx((206.0 / 200.0 - 1) - (91.05 / 91.0 - 1))
    assert row["IWM_R_co_ex"] == pytest.approx((49.0 / 50.0 - 1) - (91.0 / 91.0 - 1))


def test_realize_skips_done_and_future_days(tmp_path):
    write_day(tmp_path, "2026-10-14", 1.3)
    write_day(tmp_path, "2026-10-20", 0.8)  # after the last SIP bar
    frames = sip_frames()
    shadow.run_realize(frames, tmp_path, now=utc("2026-10-15T00:00:00"), log=lambda m: None)
    shadow.run_realize(frames, tmp_path, now=utc("2026-10-15T00:00:00"), log=lambda m: None)
    rows = (tmp_path / "realized.jsonl").read_text().splitlines()
    assert len(rows) == 1 and json.loads(rows[0])["release_date"] == "2026-10-14"


# ---------------------------------------------------------------------------- summary


def test_summary_counts_d_and_days_needed(tmp_path):
    write_day(tmp_path, "2026-10-14", 1.3)  # would_hold
    write_day(tmp_path, "2026-10-15", 0.8)  # not
    write_day(tmp_path, "2026-10-13", 2.0, fomc=True)  # FOMC day: outside the primary count
    realized = [
        {"release_date": "2026-10-14", "QQQ_R_cc_ex": 0.010},
        {"release_date": "2026-10-15", "QQQ_R_cc_ex": -0.002},
        {"release_date": "2026-10-13", "QQQ_R_cc_ex": 0.050},
    ]
    (tmp_path / "realized.jsonl").write_text("".join(json.dumps(r) + "\n" for r in realized))
    s = shadow.summarize(tmp_path)
    assert s["label"] == "forward_only_no_decision"
    assert s["forward_non_fomc_release_days"] == 2 and s["fomc_days"] == 1
    assert s["days_still_needed"] == 58
    assert s["D_QQQ_R_cc_ex_bp"] == pytest.approx(120.0)
    assert "forward_only_no_decision" in shadow.format_summary(s)


def test_summary_without_data(tmp_path):
    s = shadow.summarize(tmp_path)
    assert s["forward_non_fomc_release_days"] == 0 and s["D_QQQ_R_cc_ex_bp"] is None
    assert s["days_still_needed"] == 60
