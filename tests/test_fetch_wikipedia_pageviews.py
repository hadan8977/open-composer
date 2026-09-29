from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import polars as pl
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "fetch_wikipedia_pageviews",
    Path(__file__).resolve().parents[1] / "scripts" / "fetch_wikipedia_pageviews.py",
)
assert _SPEC and _SPEC.loader
fw = importlib.util.module_from_spec(_SPEC)
sys.modules["fetch_wikipedia_pageviews"] = fw
_SPEC.loader.exec_module(fw)

WIKITEXT = """intro
{| class="wikitable sortable" id="constituents"
|-
![[Ticker symbol|Symbol]]
! Security !! GICS Sector
|-
|| {{NyseSymbol|MMM}}
|| [[3M]]
|| Industrials
|-
|| {{NasdaqSymbol|AMD}}
|| [[AMD|Advanced Micro Devices]]
|| Information Technology
|-
|| {{NyseSymbol|BRK.B}}
|| [[Berkshire Hathaway]]
|| Financials
|-
|| {{NasdaqSymbol|GOOG}}
|| [[Alphabet Inc.#History|Alphabet (C)]]
|| Communication
|-
|| {{NyseSymbol|MMM}}
|| [[3M]]
|| duplicate ticker row
|}
after table
"""


class FakeResp:
    def __init__(self, status: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, script: list[FakeResp]):
        self.script = list(script)
        self.calls: list[tuple[str, dict | None]] = []
        self.headers: dict = {}

    def get(self, url: str, params: dict | None = None, timeout: int = 0):
        self.calls.append((url, params))
        return self.script.pop(0)


def _client(script: list[FakeResp]):
    sleeps: list[float] = []
    ticks = iter(range(0, 10_000))
    client = fw.Client(
        session=FakeSession(script),
        sleep=sleeps.append,
        clock=lambda: float(next(ticks)),
        min_interval=0.0,
    )
    return client, sleeps


def test_parse_constituents_extracts_ticker_title_and_dedups() -> None:
    rows = fw.parse_constituents(WIKITEXT)
    assert rows == [
        ("MMM", "3M"),
        ("AMD", "AMD"),
        ("BRK.B", "Berkshire Hathaway"),
        ("GOOG", "Alphabet Inc."),
    ]


def test_parse_constituents_requires_table() -> None:
    with pytest.raises(ValueError):
        fw.parse_constituents("no table here")


def test_parse_pageviews_maps_timestamps_and_empty() -> None:
    frame = fw.parse_pageviews(
        {
            "items": [
                {"timestamp": "2024010200", "views": 20},
                {"timestamp": "2024010100", "views": 10},
            ]
        }
    )
    assert frame["views"].to_list() == [10, 20]
    assert frame["date"].dt.strftime("%Y-%m-%d").to_list() == ["2024-01-01", "2024-01-02"]
    assert fw.parse_pageviews({}).height == 0


def test_backoff_on_429_and_5xx_then_success() -> None:
    client, sleeps = _client([FakeResp(429), FakeResp(503), FakeResp(200, {"ok": 1})])
    resp = client.get("http://x")
    assert resp.status_code == 200
    assert sleeps == [2.0, 4.0]
    assert client.backoff_total_s == 6.0


def test_backoff_honors_retry_after_and_caps() -> None:
    client, sleeps = _client([FakeResp(429, headers={"Retry-After": "30"}), FakeResp(200)])
    client.get("http://x")
    assert sleeps == [30.0]


def test_gives_up_after_max_retries() -> None:
    client, _ = _client([FakeResp(429)] * (fw.MAX_RETRIES + 1))
    with pytest.raises(fw.RateLimitedError):
        client.get("http://x")


def test_unexpected_status_raises_without_retry() -> None:
    client, sleeps = _client([FakeResp(403)])
    with pytest.raises(RuntimeError, match="403"):
        client.get("http://x")
    assert sleeps == []


def test_resolve_redirects_batches_and_follows_continue() -> None:
    titles = [f"T{i}" for i in range(60)]
    first = {
        "continue": {"rdcontinue": "abc"},
        "query": {"redirects": [{"from": "T0", "to": "Target Zero"}]},
    }
    second = {"query": {"normalized": [{"from": "T1", "to": "T_1"}]}}
    third = {"query": {"redirects": [{"from": "T55", "to": "Target 55"}]}}
    client, _ = _client([FakeResp(200, first), FakeResp(200, second), FakeResp(200, third)])
    mapping = fw.resolve_redirects(client, titles)
    assert mapping["T0"] == "Target Zero"
    assert mapping["T1"] == "T_1"
    assert mapping["T55"] == "Target 55"
    assert mapping["T2"] == "T2"
    calls = client.session.calls
    assert len(calls) == 3  # 50-title batch with one continuation + one 10-title batch
    assert calls[1][1]["rdcontinue"] == "abc"
    assert len(calls[0][1]["titles"].split("|")) == 50


def test_run_resumes_skips_existing_and_writes_404_as_empty(tmp_path: Path) -> None:
    out = tmp_path / "pv"
    out.mkdir()
    (out / "_title_map.json").write_text(
        json.dumps(
            [
                {"ticker": "AAA", "list_title": "Aaa", "title": "Aaa"},
                {"ticker": "BBB", "list_title": "Bbb", "title": "Bbb Corp"},
                {"ticker": "CCC", "list_title": "Ccc", "title": "Ccc"},
            ]
        )
    )
    pl.DataFrame({"date": [], "views": []}, schema=fw.SCHEMA).write_parquet(out / "AAA.parquet")
    payload = {"items": [{"timestamp": "2024010100", "views": 7}]}
    client, _ = _client([FakeResp(200, payload), FakeResp(404)])
    summary = fw.run(client, out, start="2024-01-01", end="2024-01-31", log=lambda m: None)
    assert summary["already_present"] == 1
    assert summary["fetched_now"] == 2
    assert summary["empty_404"] == ["CCC"]
    urls = [c[0] for c in client.session.calls]
    assert urls[0].endswith("/Bbb%20Corp/daily/2024010100/2024013100".replace("%20", "_"))
    assert pl.read_parquet(out / "BBB.parquet")["views"].to_list() == [7]
    assert pl.read_parquet(out / "CCC.parquet").height == 0
    # second call: everything present, no HTTP traffic
    client2, _ = _client([])
    again = fw.run(client2, out, start="2024-01-01", end="2024-01-31", log=lambda m: None)
    assert again["fetched_now"] == 0 and again["already_present"] == 3
    assert client2.session.calls == []


def test_run_limit_stops_early(tmp_path: Path) -> None:
    out = tmp_path / "pv"
    out.mkdir()
    (out / "_title_map.json").write_text(
        json.dumps([{"ticker": t, "list_title": t, "title": t} for t in ("A", "B", "C")])
    )
    client, _ = _client([FakeResp(200, {"items": []})] * 3)
    summary = fw.run(client, out, end="2024-01-31", limit=1, log=lambda m: None)
    assert summary["fetched_now"] == 1
