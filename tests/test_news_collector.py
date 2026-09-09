"""Tests for open_composer/research/news/collector.py.

Never touches the real Alpaca News API or .env: a small fake ``session``
object stands in for httpx (matching its ``.get(url, params=, headers=,
timeout=)`` -> response-with-``.raise_for_status()``/``.json()`` shape),
and credentials are monkeypatched directly rather than routed through
os.environ/.env.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from open_composer.research.news import collector as c


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeSession:
    """Replays one page of articles per call, keyed by page_token, so a
    test can simulate multi-page pagination deterministically."""

    def __init__(self, pages: dict[str | None, dict]) -> None:
        self.pages = pages
        self.calls: list[dict] = []

    def get(self, url: str, *, params: dict, headers: dict, timeout: float):
        self.calls.append({"url": url, "params": dict(params), "headers": dict(headers)})
        token = params.get("page_token")
        return _FakeResponse(self.pages[token])


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(c, "alpaca_api_key_id", lambda: "test-key")
    monkeypatch.setattr(c, "alpaca_api_secret_key", lambda: "test-secret")
    monkeypatch.setattr(c, "MIN_SECONDS_BETWEEN_REQUESTS", 0.0)


def _article(article_id: str, created_at: str, symbols: list[str], headline: str = "H") -> dict:
    return {
        "id": article_id,
        "created_at": created_at,
        "updated_at": created_at,
        "symbols": symbols,
        "headline": headline,
        "summary": "S",
        "source": "benzinga",
        "url": "https://example.invalid/a",
        "author": "staff",
    }


def test_headers_raise_when_credentials_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(c, "alpaca_api_key_id", lambda: None)
    monkeypatch.setattr(c, "alpaca_api_secret_key", lambda: None)
    with pytest.raises(c.AlpacaCredentialsMissing):
        c._headers()


def test_fetch_window_paginates_via_next_page_token() -> None:
    session = _FakeSession(
        {
            None: {
                "news": [_article("1", "2024-06-03T10:00:00Z", ["AAPL"])],
                "next_page_token": "tok2",
            },
            "tok2": {
                "news": [_article("2", "2024-06-03T11:00:00Z", ["MSFT"])],
                "next_page_token": None,
            },
        }
    )
    packets = c.fetch_window(
        start=datetime(2024, 6, 3, tzinfo=UTC),
        end=datetime(2024, 6, 4, tzinfo=UTC),
        historical=True,
        session=session,
    )
    assert [p["id"] for p in packets] == ["1", "2"]
    assert len(session.calls) == 2
    # No symbols param anywhere -- plan section 4.1: "不做 symbol 过滤".
    assert all("symbols" not in call["params"] for call in session.calls)
    assert session.calls[1]["params"]["page_token"] == "tok2"


def test_historical_visibility_lag_is_15_minutes() -> None:
    session = _FakeSession(
        {None: {"news": [_article("1", "2024-06-03T10:00:00Z", ["AAPL"])], "next_page_token": None}}
    )
    packets = c.fetch_window(
        start=datetime(2024, 6, 3, tzinfo=UTC),
        end=datetime(2024, 6, 4, tzinfo=UTC),
        historical=True,
        session=session,
    )
    packet = packets[0]
    assert packet["visible_at"] == pd.Timestamp("2024-06-03T10:15:00Z")


def test_forward_visibility_is_fetched_at_not_created_at() -> None:
    session = _FakeSession(
        {None: {"news": [_article("1", "2024-06-03T10:00:00Z", ["AAPL"])], "next_page_token": None}}
    )
    before = pd.Timestamp.now(tz="UTC")
    packets = c.fetch_window(
        start=datetime(2024, 6, 3, tzinfo=UTC),
        end=datetime(2024, 6, 4, tzinfo=UTC),
        historical=False,
        session=session,
    )
    after = pd.Timestamp.now(tz="UTC")
    packet = packets[0]
    assert before <= packet["visible_at"] <= after
    assert packet["visible_at"] != pd.Timestamp("2024-06-03T10:00:00Z")


def test_article_missing_id_or_created_at_is_dropped() -> None:
    session = _FakeSession(
        {
            None: {
                "news": [
                    _article("1", "2024-06-03T10:00:00Z", ["AAPL"]),
                    {**_article("2", "", ["MSFT"]), "created_at": ""},
                    {"id": None, "created_at": "2024-06-03T12:00:00Z"},
                ],
                "next_page_token": None,
            }
        }
    )
    packets = c.fetch_window(
        start=datetime(2024, 6, 3, tzinfo=UTC),
        end=datetime(2024, 6, 4, tzinfo=UTC),
        historical=True,
        session=session,
    )
    assert [p["id"] for p in packets] == ["1"]


def test_collect_day_uses_utc_calendar_day_boundaries() -> None:
    session = _FakeSession({None: {"news": [], "next_page_token": None}})
    c.collect_day(date(2024, 6, 3), historical=True, session=session)
    params = session.calls[0]["params"]
    assert params["start"].startswith("2024-06-03T00:00:00")
    assert params["end"].startswith("2024-06-04T00:00:00")


def test_collect_historical_range_is_resumable(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(c, "NEWS_PACKETS_ROOT", tmp_path)
    monkeypatch.setattr(c, "DAILY_ROOT", tmp_path / "_daily")

    calls = {"n": 0}

    def _fake_collect_day(day, *, historical, session=None):
        calls["n"] += 1
        return pd.DataFrame([{**{col: None for col in c.PACKET_COLUMNS}, "id": f"a-{day}"}])

    monkeypatch.setattr(c, "collect_day", _fake_collect_day)

    summary1 = c.collect_historical_range(date(2024, 1, 1), date(2024, 1, 3))
    assert summary1.days_fetched == 3
    assert summary1.days_skipped_already_done == 0
    assert calls["n"] == 3

    # Second run over an overlapping, wider range: the 3 already-done days
    # are skipped, only the new day is actually fetched.
    summary2 = c.collect_historical_range(date(2024, 1, 1), date(2024, 1, 4))
    assert summary2.days_fetched == 1
    assert summary2.days_skipped_already_done == 3
    assert calls["n"] == 4


def test_consolidate_year_dedupes_by_id_keep_last(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(c, "NEWS_PACKETS_ROOT", tmp_path)
    daily_root = tmp_path / "_daily"
    monkeypatch.setattr(c, "DAILY_ROOT", daily_root)
    daily_root.mkdir()

    base = {col: None for col in c.PACKET_COLUMNS}
    day1 = pd.DataFrame(
        [
            {
                **base,
                "id": "1",
                "created_at": pd.Timestamp("2024-06-03T10:00:00Z"),
                "headline": "old",
            },
        ]
    )
    day2 = pd.DataFrame(
        [
            {
                **base,
                "id": "1",
                "created_at": pd.Timestamp("2024-06-03T10:00:00Z"),
                "headline": "updated",
            },
            {
                **base,
                "id": "2",
                "created_at": pd.Timestamp("2024-06-04T09:00:00Z"),
                "headline": "new",
            },
        ]
    )
    day1.to_parquet(daily_root / "2024-06-03.parquet", index=False)
    day2.to_parquet(daily_root / "2024-06-04.parquet", index=False)

    out_path = c.consolidate_year(2024)
    result = pd.read_parquet(out_path)
    assert len(result) == 2
    assert set(result["id"]) == {"1", "2"}
    assert result.loc[result["id"] == "1", "headline"].iloc[0] == "updated"


def test_collect_forward_always_refetches_recent_days(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(c, "NEWS_PACKETS_ROOT", tmp_path)
    monkeypatch.setattr(c, "DAILY_ROOT", tmp_path / "_daily")
    calls = []

    def _fake_collect_day(day, *, historical, session=None):
        calls.append((day, historical))
        return pd.DataFrame([{**{col: None for col in c.PACKET_COLUMNS}, "id": f"a-{day}"}])

    monkeypatch.setattr(c, "collect_day", _fake_collect_day)
    summary = c.collect_forward(lookback_days=3, today=date(2024, 6, 10))
    assert summary.days_fetched == 3
    assert all(historical is False for _, historical in calls)
    assert {day for day, _ in calls} == {date(2024, 6, 8), date(2024, 6, 9), date(2024, 6, 10)}
