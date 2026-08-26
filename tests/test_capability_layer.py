from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from open_composer.adapters.events import fetch_capability_events, fetcher
from open_composer.capabilities import evaluate_capabilities, load_registry


def test_capability_registry_loads(sample_workspace: Path) -> None:
    registry = load_registry(sample_workspace)
    ids = {capability.id for capability in registry.capabilities}
    assert "market.alpaca_bars" in ids
    assert "market.longbridge_bars" in ids
    assert "market.cboe_volatility_indices" in ids
    assert "events.sec_filings" in ids
    assert "macro.fred_series" in ids
    assert "macro.cftc_cot" in ids
    assert "news.alpaca" in ids
    assert "news.alpha_vantage" in ids
    assert "options.trial_chain" in ids
    options = next(
        capability for capability in registry.capabilities if capability.id == "options.trial_chain"
    )
    assert options.kind == "options_chain"
    assert options.status == "trial"
    fred = next(
        capability for capability in registry.capabilities if capability.id == "macro.fred_series"
    )
    assert fred.status == "trial"
    assert fred.strict_behavior == "research_only"
    cftc = next(
        capability for capability in registry.capabilities if capability.id == "macro.cftc_cot"
    )
    assert cftc.status == "trial"
    assert cftc.strict_behavior == "research_only"
    cboe = next(
        capability
        for capability in registry.capabilities
        if capability.id == "market.cboe_volatility_indices"
    )
    assert cboe.status == "trial"
    assert cboe.strict_behavior == "research_only"
    assert cboe.paper_ready_timeframes == []


def test_capability_evaluation_passes_with_fixtures(sample_workspace: Path) -> None:
    evaluations = evaluate_capabilities(sample_workspace)
    assert evaluations
    assert all(evaluation.passed for evaluation in evaluations)
    options = next(
        evaluation
        for evaluation in evaluations
        if evaluation.capability_id == "options.trial_chain"
    )
    assert options.records >= 1
    assert (sample_workspace / "reports" / "capabilities" / "evaluation.md").exists()


def test_event_fetch_replays_fixture_and_dedupes(sample_workspace: Path) -> None:
    events = fetch_capability_events("sec", sample_workspace, ["QQQ"], offline=True)
    assert events
    assert all(event.source == "sec" for event in events)
    assert all(event.acquisition_mode == "fixture_replay" for event in events)
    persisted_paths = list((sample_workspace / "data" / "raw" / "events" / "sec").glob("*.jsonl"))
    assert persisted_paths
    persisted = [
        json.loads(line) for line in persisted_paths[0].read_text().splitlines() if line.strip()
    ]
    assert all(record["acquisition_mode"] == "fixture_replay" for record in persisted)


def test_cftc_fixture_is_schema_only_and_survives_macro_symbol_filter(
    sample_workspace: Path,
) -> None:
    events = fetch_capability_events("cftc_cot", sample_workspace, ["QQQ"], offline=True)

    assert len(events) == 1
    assert events[0].symbol == "NQ_COT"
    assert events[0].acquisition_mode == "fixture_replay"
    assert events[0].raw["fixture"] is True
    assert events[0].raw["research_evidence"] is False
    assert events[0].raw["paper_evidence"] is False
    persisted = list((sample_workspace / "data/raw/macro").glob("cftc-*.jsonl"))
    assert persisted


def test_alpha_vantage_live_fetch_expands_requested_ticker_sentiment(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    captured_params: list[dict[str, object]] = []

    def fake_http_get_json(url: str, params: dict[str, object] | None = None):
        captured_params.append(params or {})
        symbol = str((params or {})["tickers"])
        return {
            "feed": [
                {
                    "time_published": "20260515T143000",
                    "title": f"{symbol} news",
                    "summary": "Synthetic Alpha Vantage payload.",
                    "url": f"https://example.test/{symbol.lower()}",
                    "overall_sentiment_label": "Neutral",
                    "ticker_sentiment": [
                        {
                            "ticker": symbol,
                            "relevance_score": "0.91",
                            "ticker_sentiment_label": "Bullish",
                        },
                        {
                            "ticker": "IGNORED",
                            "relevance_score": "0.99",
                            "ticker_sentiment_label": "Bearish",
                        },
                    ],
                }
            ]
        }

    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    monkeypatch.setattr(fetcher, "_http_get_json", fake_http_get_json)

    events = fetch_capability_events(
        "alpha_vantage",
        sample_workspace,
        ["AAPL", "MSFT"],
        offline=False,
        limit=1000,
        sort="EARLIEST",
    )

    assert [event.symbol for event in events] == ["AAPL", "MSFT"]
    assert all(event.sentiment == "positive" for event in events)
    assert all(event.relevance_score == 0.91 for event in events)
    assert [params["tickers"] for params in captured_params] == ["AAPL", "MSFT"]
    assert all(params["limit"] == 1000 for params in captured_params)
    assert all(params["sort"] == "EARLIEST" for params in captured_params)
    assert list((sample_workspace / "data" / "raw" / "events" / "alpha_vantage").glob("*.jsonl"))


def test_alpaca_news_live_fetch_paginates_and_uses_local_first_seen(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    fetched_at = datetime(2026, 8, 5, 1, tzinfo=UTC)
    calls: list[dict[str, object]] = []

    def fake_page(**kwargs):
        calls.append(kwargs)
        page_token = kwargs["page_token"]
        article_id = 101 if page_token is None else 102
        payload = {
            "news": [
                {
                    "id": article_id,
                    "created_at": "2026-08-04T20:00:00Z",
                    "updated_at": f"2026-08-04T2{article_id - 101}:30:00Z",
                    "headline": "AI infrastructure order update",
                    "summary": "Supplier and customer relationships were discussed.",
                    "source": "benzinga",
                    "symbols": ["NVDA", "VRT"],
                    "url": f"https://example.test/{article_id}",
                }
            ],
            "next_page_token": "page-2" if page_token is None else None,
        }
        return payload, fetched_at

    monkeypatch.setattr(fetcher, "_fetch_alpaca_news_page", fake_page)

    events = fetch_capability_events(
        "alpaca_news",
        sample_workspace,
        ["NVDA"],
        offline=False,
        limit=2,
        sort="asc",
    )

    assert len(events) == 2
    assert [call["page_token"] for call in calls] == [None, "page-2"]
    assert all(call["sort"] == "ASC" for call in calls)
    assert all(event.symbol == "NVDA" for event in events)
    assert all(event.visible_at == fetched_at for event in events)
    assert all(event.first_seen_at == fetched_at for event in events)
    assert all(event.acquisition_mode == "live_api_forward_only" for event in events)
    assert all(event.raw["content_requested"] is False for event in events)
    assert len({event.dedupe_key for event in events}) == 2
    assert list((sample_workspace / "data" / "raw" / "events" / "alpaca").glob("*.jsonl"))


def test_alpaca_news_broad_discovery_expands_provider_symbols() -> None:
    fetched_at = datetime(2026, 8, 5, 1, tzinfo=UTC)
    records = fetcher._alpaca_news_records_from_payload(
        {
            "news": [
                {
                    "id": 200,
                    "created_at": "2026-08-04T20:00:00Z",
                    "updated_at": "2026-08-04T20:05:00Z",
                    "headline": "Robotics chain update",
                    "summary": "Component and integrator demand changed.",
                    "source": "benzinga",
                    "symbols": ["ROK", "TER"],
                    "url": "https://example.test/200",
                    "content": "must not be retained in raw metadata",
                }
            ]
        },
        requested_symbols=[],
        fetched_at=fetched_at,
    )

    assert [record.symbol for record in records] == ["ROK", "TER"]
    assert all("content" not in record.raw for record in records)
    assert all(record.published_at < record.visible_at for record in records)


def test_alpaca_news_refetch_preserves_persistent_first_seen(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    first_fetch = datetime(2026, 8, 5, 1, tzinfo=UTC)
    second_fetch = datetime(2026, 8, 5, 2, tzinfo=UTC)
    fetch_times = iter([first_fetch, second_fetch])

    def fake_page(**kwargs):
        return (
            {
                "news": [
                    {
                        "id": 300,
                        "created_at": "2026-08-04T20:00:00Z",
                        "updated_at": "2026-08-04T20:05:00Z",
                        "headline": "AI infrastructure order update",
                        "summary": "The same provider version was fetched again.",
                        "source": "benzinga",
                        "symbols": ["NVDA"],
                        "url": "https://example.test/300",
                    }
                ],
                "next_page_token": None,
            },
            next(fetch_times),
        )

    monkeypatch.setattr(fetcher, "_fetch_alpaca_news_page", fake_page)

    first = fetch_capability_events(
        "alpaca_news",
        sample_workspace,
        ["NVDA"],
        offline=False,
        limit=1,
    )
    second = fetch_capability_events(
        "alpaca_news",
        sample_workspace,
        ["NVDA"],
        offline=False,
        limit=1,
    )

    assert first[0].fetched_at == first_fetch
    assert second[0].fetched_at == first_fetch
    assert second[0].first_seen_at == first_fetch
    assert second[0].visible_at == first_fetch
    assert second[0].raw["last_refetched_at"] == second_fetch.isoformat()
