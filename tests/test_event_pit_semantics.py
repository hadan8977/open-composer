from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from open_composer.adapters.events import fetcher
from open_composer.context import _context_from_records
from open_composer.models.event import EventRecord
from open_composer.models.signal import Signal


def _event(**overrides) -> EventRecord:
    values = {
        "id": "event-1",
        "source": "test",
        "symbol": "QQQ",
        "published_at": datetime(2026, 1, 1, 10, tzinfo=UTC),
        "fetched_at": datetime(2026, 1, 1, 11, tzinfo=UTC),
        "event_type": "news",
        "title": "Test event",
        "summary": "Test summary",
        "dedupe_key": "test:event-1",
    }
    values.update(overrides)
    return EventRecord(**values)


def _signal(timestamp: datetime, symbol: str = "QQQ") -> Signal:
    return Signal(
        id="signal-1",
        run_id="run-1",
        strategy_name="test_strategy",
        symbol=symbol,
        timeframe="15m",
        timestamp=timestamp,
        action="entry",
        side="buy",
        source="test",
        price=100.0,
        lifecycle="draft",
        execution_mode="manual_signal",
        fill_assumption="next_bar_open",
    )


def test_event_record_materializes_safe_visibility_and_metadata_defaults() -> None:
    record = _event()

    assert record.visible_at == record.fetched_at
    assert record.first_seen_at == record.fetched_at
    assert record.accepted_at is None
    assert record.revision == "unknown"
    assert record.rights == "unknown"
    assert record.availability_quality == "unknown"
    assert record.availability_basis == "derived_safe_max"
    assert record.acquisition_mode == "unknown"
    assert record.vintage_at is None


def test_sec_uses_acceptance_or_fetch_time_visibility(monkeypatch) -> None:
    def fake_http_get_json(url: str, params=None):
        if url.endswith("company_tickers.json"):
            return {"0": {"ticker": "AAPL", "cik_str": 320193}}
        return {
            "filings": {
                "recent": {
                    "form": ["8-K", "10-Q"],
                    "accessionNumber": ["0001-26-000001", "0001-26-000002"],
                    "filingDate": ["2026-01-02", "2026-01-03"],
                    "acceptanceDateTime": ["2026-01-02T13:45:12.000Z", ""],
                    "primaryDocument": ["first.htm", "second.htm"],
                }
            }
        }

    monkeypatch.setattr(fetcher, "_http_get_json", fake_http_get_json)
    monkeypatch.setenv("SEC_USER_AGENT", "Open Composer test@example.com")

    records = fetcher._fetch_sec_filings(["AAPL"])
    accepted = next(record for record in records if record.event_type == "8-K")
    first_seen = next(record for record in records if record.event_type == "10-Q")

    assert accepted.published_at == datetime(2026, 1, 2, 13, 45, 12, tzinfo=UTC)
    assert accepted.accepted_at == accepted.published_at
    assert accepted.first_seen_at == accepted.fetched_at
    assert accepted.visible_at == accepted.fetched_at
    assert accepted.visible_at > accepted.published_at
    assert accepted.availability_quality == "fetch_time_with_official_acceptance"
    before_first_seen = _context_from_records(
        _signal(accepted.published_at + timedelta(seconds=1), symbol="AAPL"),
        [accepted],
        [],
        max_records=5,
    )
    assert before_first_seen.events == []
    assert first_seen.published_at == first_seen.fetched_at
    assert first_seen.accepted_at is None
    assert first_seen.first_seen_at == first_seen.fetched_at
    assert first_seen.visible_at == first_seen.fetched_at
    assert first_seen.availability_quality == "fetch_time_first_seen"


def test_sec_live_fetch_requires_contact_bearing_user_agent(monkeypatch) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="contact email"):
        fetcher._fetch_sec_filings(["AAPL"])

    monkeypatch.setenv("SEC_USER_AGENT", "open-composer/0.1")
    with pytest.raises(RuntimeError, match="contact email"):
        fetcher._fetch_sec_filings(["AAPL"])


def test_fred_current_observation_uses_fetch_time_vintage(monkeypatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setattr(
        fetcher,
        "_http_get_json",
        lambda url, params=None: {"observations": [{"date": "2020-01-01", "value": "4.25"}]},
    )

    record = fetcher._fetch_fred_series(["DGS10"])[0]

    assert record.published_at == record.fetched_at
    assert record.visible_at == record.fetched_at
    assert record.first_seen_at == record.fetched_at
    assert record.vintage_at is None
    assert record.revision == "latest_snapshot_non_vintage"
    assert record.availability_quality == "forward_only_fetch_time"
    assert record.availability_basis == "collector_first_seen"
    assert record.acquisition_mode == "live_api_forward_only"
    assert record.raw["date"] == "2020-01-01"


def test_alpha_vantage_publication_does_not_imply_visibility() -> None:
    records = fetcher._alpha_vantage_records_from_payload(
        payload={
            "feed": [
                {
                    "time_published": "20200101T120000",
                    "title": "Historical provider item",
                    "ticker_sentiment": [
                        {
                            "ticker": "QQQ",
                            "relevance_score": "0.8",
                            "ticker_sentiment_label": "Neutral",
                        }
                    ],
                }
            ]
        },
        symbols=["QQQ"],
    )

    record = records[0]
    assert record.published_at == datetime(2020, 1, 1, 12, tzinfo=UTC)
    assert record.visible_at == record.fetched_at
    assert record.visible_at > record.published_at
    assert record.availability_quality == "fetch_time_first_seen"


def test_context_rejects_event_visible_after_decision_time() -> None:
    decision_at = datetime(2026, 1, 1, 11, tzinfo=UTC)
    eligible = _event(id="eligible", dedupe_key="test:eligible")
    future_visible = _event(
        id="future",
        dedupe_key="test:future",
        fetched_at=decision_at,
        visible_at=datetime(2026, 1, 1, 12, tzinfo=UTC),
    )

    context = _context_from_records(
        _signal(decision_at),
        [eligible, future_visible],
        [],
        max_records=5,
    )

    assert [record.id for record in context.events] == ["eligible"]
    assert [record.id for record in context.news] == ["eligible"]


def test_event_record_rejects_visibility_before_collector_first_seen() -> None:
    with pytest.raises(ValueError, match="visible_at cannot precede"):
        _event(visible_at=datetime(2026, 1, 1, 10, 30, tzinfo=UTC))


def test_event_record_schema_describes_pit_provenance(repo_root: Path) -> None:
    schema = json.loads((repo_root / "schemas" / "event_record.schema.json").read_text())
    properties = schema["properties"]

    assert (
        "max(published_at, fetched_at, first_seen_at, accepted_at)"
        in properties["visible_at"]["description"]
    )
    assert properties["first_seen_at"]["format"] == "date-time"
    assert properties["accepted_at"]["format"] == "date-time"
    assert properties["vintage_at"]["format"] == "date-time"
    for field in ("revision", "rights", "availability_quality", "acquisition_mode"):
        assert properties[field]["default"] == "unknown"
