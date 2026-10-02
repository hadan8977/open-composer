"""Fake-HTTP tests for scripts/collect_prediction_markets.py (T-20261002-44)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "collect_prediction_markets.py"
spec = importlib.util.spec_from_file_location("collect_prediction_markets", SCRIPT)
assert spec and spec.loader
collect = importlib.util.module_from_spec(spec)
sys.modules["collect_prediction_markets"] = collect
spec.loader.exec_module(collect)

NOW = datetime(2026, 10, 2, 14, 0, 5, tzinfo=UTC)
WATCH = [
    {"id": "11", "group": "fed", "note": "a"},
    {"id": "22", "group": "recession", "note": "b"},
]


def kalshi_market(ticker: str, strike: float) -> dict:
    return {
        "ticker": ticker,
        "strike_type": "greater",
        "floor_strike": strike,
        "status": "active",
        "yes_bid_dollars": "0.4000",
        "yes_ask_dollars": "0.4600",
        "yes_bid_size_fp": "10.00",
        "yes_ask_size_fp": "5.00",
        "last_price_dollars": "0.4200",
        "previous_price_dollars": "0.4100",
        "volume_fp": "100.00",
        "volume_24h_fp": "12.00",
        "open_interest_fp": "50.00",
        "open_time": "2026-09-01T15:00:00Z",
        "close_time": "2026-10-14T12:25:00Z",
        "expected_expiration_time": "2026-10-14T13:56:00Z",
        "updated_time": "2026-10-02T13:59:00Z",
    }


def fake_get(fail_on: str | None = None):
    calls: list[str] = []

    def http_get(url, params, timeout):
        calls.append(url)
        if fail_on and fail_on in url:
            return 503, None
        if url.endswith("/series/KXCPI"):
            return 200, {"series": {"ticker": "KXCPI"}}
        if "/series/" in url:
            return 404, None
        if url.endswith("/events"):
            if params["series_ticker"] != "KXCPI":
                return 200, {"events": [], "cursor": ""}
            return 200, {
                "events": [
                    {
                        "event_ticker": "KXCPI-26SEP",
                        "title": "CPI in September",
                        "markets": [
                            kalshi_market("KXCPI-26SEP-T0.2", 0.2),
                            kalshi_market("KXCPI-26SEP-T0.3", 0.3),
                        ],
                    }
                ],
                "cursor": "",
            }
        if url.endswith("/markets"):
            return 200, [
                {
                    "id": "11",
                    "slug": "fed-no-change",
                    "question": "No change?",
                    "conditionId": "0xabc",
                    "outcomePrices": '["0.835", "0.165"]',
                    "clobTokenIds": '["tok-yes", "tok-no"]',
                    "bestBid": 0.83,
                    "bestAsk": 0.84,
                    "lastTradePrice": 0.83,
                    "spread": 0.01,
                    "volumeNum": 1000.0,
                    "volume24hr": 10.0,
                    "liquidityNum": 500.0,
                    "active": True,
                    "closed": False,
                    "endDate": "2026-10-29T03:59:00Z",
                    "updatedAt": "2026-10-02T13:59:30Z",
                },
                {"id": "22", "slug": "recession", "question": "Recession?", "outcomePrices": None},
            ]
        raise AssertionError(url)

    return http_get, calls


def make_http(get):
    return collect.Http(get, sleep=lambda s: None, clock=lambda: 0.0)


def test_snapshot_writes_two_dated_files_with_fetch_time(tmp_path):
    get, calls = fake_get()
    result = collect.collect_snapshot(make_http(get), tmp_path, now=NOW, watchlist=WATCH)
    k = tmp_path / "kalshi_hourly" / "date=2026-10-02" / "part-140005.parquet"
    p = tmp_path / "polymarket_hourly" / "date=2026-10-02" / "part-140005.parquet"
    assert k.exists() and p.exists()
    kdf, pdf = pd.read_parquet(k), pd.read_parquet(p)
    assert len(kdf) == 2 and kdf["fetched_at_utc"].eq("2026-10-02T14:00:05+00:00").all()
    assert kdf.loc[0, "yes_ask"] == pytest.approx(0.46)
    assert kdf.loc[0, "source_updated_time"] == "2026-10-02T13:59:00Z"
    assert len(pdf) == 2 and pdf.loc[0, "yes_price"] == pytest.approx(0.835)
    assert pdf.loc[0, "clob_yes_token_id"] == "tok-yes"
    assert pdf.loc[0, "source_updated_at"] == "2026-10-02T13:59:30Z"
    assert result["kalshi_rows"] == 2 and result["polymarket_rows"] == 2
    assert not list(tmp_path.rglob(".*.tmp"))
    assert len(calls) > 0


def test_old_files_are_never_rewritten(tmp_path):
    get, _ = fake_get()
    collect.collect_snapshot(make_http(get), tmp_path, now=NOW, watchlist=WATCH)
    first = tmp_path / "kalshi_hourly" / "date=2026-10-02" / "part-140005.parquet"
    stamp = first.stat().st_mtime_ns
    with pytest.raises(FileExistsError):
        collect.collect_snapshot(make_http(get), tmp_path, now=NOW, watchlist=WATCH)
    assert first.stat().st_mtime_ns == stamp
    # a later run in the same hour appends a new part file
    later = datetime(2026, 10, 2, 14, 30, 0, tzinfo=UTC)
    collect.collect_snapshot(make_http(get), tmp_path, now=later, watchlist=WATCH)
    assert len(list((tmp_path / "kalshi_hourly" / "date=2026-10-02").glob("part-*.parquet"))) == 2


def test_failure_writes_nothing(tmp_path):
    get, _ = fake_get(fail_on="/markets")  # Polymarket leg fails after Kalshi succeeded
    with pytest.raises(RuntimeError):
        collect.collect_snapshot(make_http(get), tmp_path, now=NOW, watchlist=WATCH)
    assert not list(tmp_path.rglob("*.parquet"))
    assert not list(tmp_path.rglob(".*.tmp"))


def test_missing_watchlist_id_fails_without_output(tmp_path):
    get, _ = fake_get()
    wl = [*WATCH, {"id": "33", "group": "x", "note": ""}]
    with pytest.raises(RuntimeError, match="33"):
        collect.collect_snapshot(make_http(get), tmp_path, now=NOW, watchlist=wl)
    assert not list(tmp_path.rglob("*.parquet"))


def test_deadline_stops_the_run():
    now = {"t": 0.0}
    get, _ = fake_get()
    http = collect.Http(get, budget_s=120.0, sleep=lambda s: None, clock=lambda: now["t"])
    http.get("https://api.elections.kalshi.com/trade-api/v2/series/KXCPI")
    now["t"] = 200.0
    with pytest.raises(TimeoutError):
        http.get("https://api.elections.kalshi.com/trade-api/v2/series/KXCPI")


def test_main_exit_code_is_nonzero_on_failure(monkeypatch, tmp_path, capsys):
    def boom(*args, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(collect, "collect_snapshot", boom)
    assert collect.main(["--out-root", str(tmp_path)]) == 1
    assert "down" in capsys.readouterr().err


def test_real_watchlist_file_is_wellformed():
    wl = collect.load_watchlist()
    ids = [m["id"] for m in wl]
    assert 10 <= len(wl) <= 20 and len(set(ids)) == len(ids)
    groups = {m["group"] for m in wl}
    assert {"recession", "government_shutdown", "midterms_2026"} <= groups
    assert any(g.startswith("fed_") for g in groups) and any(g.startswith("cpi") for g in groups)
    assert any(g.startswith("tariff") for g in groups)
