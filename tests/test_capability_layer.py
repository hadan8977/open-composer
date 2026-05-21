from __future__ import annotations

from pathlib import Path

from open_composer.adapters.events import fetch_capability_events, fetcher
from open_composer.capabilities import evaluate_capabilities, load_registry


def test_capability_registry_loads(sample_workspace: Path) -> None:
    registry = load_registry(sample_workspace)
    ids = {capability.id for capability in registry.capabilities}
    assert "market.alpaca_bars" in ids
    assert "market.longbridge_bars" in ids
    assert "events.sec_filings" in ids
    assert "macro.fred_series" in ids
    assert "news.alpha_vantage" in ids
    assert "options.trial_chain" in ids
    options = next(
        capability for capability in registry.capabilities if capability.id == "options.trial_chain"
    )
    assert options.kind == "options_chain"
    assert options.status == "trial"


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
    assert list((sample_workspace / "data" / "raw" / "events" / "sec").glob("*.jsonl"))


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
